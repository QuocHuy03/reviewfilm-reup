"""Giọng CapCut — gọi API TTS của CapCut bằng cookie tài khoản CapCut của người dùng (giống ToolYoutube).

Cookie tuỳ chọn: Cài đặt → Key giọng đọc → CAPCUT_COOKIE (chuỗi "a=b; c=d" hoặc JSON xuất từ extension cookie).
Không có cookie vẫn tạo được giọng (dùng mã thiết bị ẩn danh); có cookie thì dùng phiên đăng nhập của bạn.
Gom vài cảnh trong 1 request (CapCut tốn ~60s cố định mỗi request, quá ~140s thì cắt) — xem synthesize_batch;
tải mp3 về, cắt khoảng lặng đầu/cuối cho lời khít hình.
"""
import hashlib
import json
import os
import random
import subprocess
import time

import requests

TTS_URL = 'https://edit-api-sg.capcut.com/storyboard/v1/tts/multi_platform'
TTS_PATH = '/storyboard/v1/tts/multi_platform'
APPID, APPVR, PF = '348188', '8.4.0', '7'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

# voice_type → (tên hiển thị, resource_id) — bộ giọng tiếng Việt của CapCut
VOICES = {
    'BV421_vivn_streaming': ('Nhỏ Ngọt Ngào', '7252594014782755330'),
    'vi_female_huong': ('Giọng Nữ Phổ Thông', '7264854897953083905'),
    'BV074_streaming': ('Cô Gái Hoạt Ngôn', '7102355709945188865'),
    'BV074_streaming_dsp': ('Giọng Bé', '7550087831092251920'),
    'vi-VN-HoaiMyNeural': ('Hoài My', '7371666434650280464'),
    'vi-VN-NamMinhNeural': ('Nam Minh', '7371666524727153168'),
    'BV562_streaming': ('Mai', '7483736254694035984'),
    'BV075_streaming_vibrato_dsp': ('Việt Méo', '7569450639810465040'),
    'BV075_streaming_demon_dsp': ('Kenny Đại Đế', '7569442422665661712'),
}

MALE = {'vi-VN-NamMinhNeural', 'BV075_streaming_vibrato_dsp', 'BV075_streaming_demon_dsp'}


def edge_fallback(voice_type):
    """Giọng Edge TTS thay thế cùng giới tính khi CapCut lỗi / chưa có cookie."""
    return 'vi-VN-NamMinhNeural' if voice_type in MALE else 'vi-VN-HoaiMyNeural'


def normalize_cookie(raw):
    """JSON (mảng {name, value}) hoặc "a=b; c=d" → "a=b; c=d" một dòng (lưu được vào .env)."""
    raw = (raw or '').strip()
    if raw.startswith('['):
        try:
            return '; '.join(f"{c['name']}={c['value']}" for c in json.loads(raw) if c.get('name'))
        except (ValueError, KeyError, TypeError):
            pass
    parts = [p.strip() for p in raw.replace('\n', ';').split(';')]
    return '; '.join(p for p in parts if '=' in p)


_ANON_COOKIE = f'_tea_web_id={random.randint(7 * 10 ** 18, 8 * 10 ** 18)}'   # mã thiết bị ẩn danh, cố định trong phiên


def _did(cookie):
    for p in cookie.split(';'):
        k, _, v = p.strip().partition('=')
        if k == '_tea_web_id':
            return v
    return ''


def _headers(cookie):
    ts = str(int(time.time()))
    sign = hashlib.md5(f'9e2c|{TTS_PATH[-7:]}|{PF}|{APPVR}|{ts}||11ac'.encode()).hexdigest()
    return {
        'Cookie': cookie, 'appid': APPID, 'appvr': APPVR, 'device-time': ts, 'did': _did(cookie), 'pf': PF,
        'sign': sign, 'sign-ver': '1', 'store-country-code': 'vn', 'store-country-code-src': 'uid', 'tdid': '',
        'Accept': 'application/json, text/plain, */*', 'Content-Type': 'application/json', 'User-Agent': UA,
        'Origin': 'https://www.capcut.com', 'Referer': 'https://www.capcut.com/',
    }


class CapcutError(RuntimeError):
    pass


class CapcutBatchTooBig(CapcutError):
    """CapCut cắt request (504 / hết giờ) — gói quá nhiều chữ, chia nhỏ rồi gửi lại."""


def synthesize_batch(items, voice_type, cookie, speed=1.0, volume=100):
    """Nhiều đoạn trong MỘT request (texts=[...]) → {chỉ số: lỗi hoặc None}.

    CapCut tốn ~60s cố định mỗi request + thêm theo tổng số chữ, quá ~140s thì cắt (504): gửi gói 3 đoạn
    nhanh gần bằng gửi 1 đoạn. items = [(text, out_path), ...]. Cả gói lỗi → ném CapcutError / CapcutBatchTooBig.
    """
    cookie = cookie or _ANON_COOKIE
    name, resource_id = VOICES.get(voice_type, (voice_type, ''))
    body = {'texts': [t for (t, _) in items], 'need_url': True,
            'tts_conf': {'speaker': voice_type, 'rate': round(speed, 2), 'volume': volume, 'name': name, 'platform': 'sami',
                         'effect_id': resource_id, 'resource_id': resource_id, 'is_clone': False}}
    try:
        r = requests.post(TTS_URL, json=body, headers=_headers(cookie), timeout=170)
    except requests.Timeout:
        raise CapcutBatchTooBig('CapCut quá thời gian chờ')
    except requests.RequestException as e:
        raise CapcutError(f'Không gọi được CapCut: {str(e)[:120]}')
    if r.status_code in (502, 503, 504):
        raise CapcutBatchTooBig(f'CapCut cắt request (HTTP {r.status_code})')
    try:
        d = r.json()
    except ValueError:
        raise CapcutError(f'CapCut trả về không đọc được (HTTP {r.status_code})')
    if str(d.get('ret')) != '0':
        raise CapcutError(f"CapCut từ chối: {d.get('errmsg') or 'lỗi không rõ'} (ret={d.get('ret')}) — "
                          'thường do cookie hết hạn: đăng nhập lại capcut.com rồi lấy cookie mới')
    mats = (d.get('data') or {}).get('tts_materials') or []
    errors = {}

    def _save(k):
        (_, out_path) = items[k]
        mat = mats[k] if k < len(mats) else {}
        if mat.get('err_code') == 40402004:
            return 'Giọng này CapCut không hỗ trợ qua web.'
        url = (mat.get('meta_data') or {}).get('url') or (mat.get('extra_map') or {}).get('url_office')
        if not url:
            return f"CapCut không trả link audio (status={mat.get('status')}, err={mat.get('err_code')})."
        try:
            a = requests.get(url, timeout=60)
        except requests.RequestException as e:
            return f'Tải audio CapCut lỗi: {str(e)[:80]}'
        if a.status_code != 200 or len(a.content) < 1000:
            return f'Tải audio CapCut lỗi (HTTP {a.status_code}).'
        with open(out_path, 'wb') as f:
            f.write(a.content)
        trim_silence(out_path)
        return None

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(min(4, len(items)) or 1) as ex:
        for (k, err) in enumerate(ex.map(_save, range(len(items)))):
            errors[k] = err
    return errors


def trim_silence(path, threshold='-50dB', min_dur=0.15):
    """Cắt khoảng lặng đầu/cuối (CapCut hay chèn ~0.3s im lặng) — lỗi thì giữ nguyên file."""
    from core.utils import FFMPEG_EXE
    tmp = path + '.trim.mp3'
    af = (f'silenceremove=start_periods=1:start_duration={min_dur}:start_threshold={threshold},areverse,'
          f'silenceremove=start_periods=1:start_duration={min_dur}:start_threshold={threshold},areverse')
    try:
        r = subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-i', path, '-af', af, '-c:a', 'libmp3lame', '-b:a', '192k', tmp],
                           capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if r.returncode == 0 and os.path.getsize(tmp) > 1000:
            os.replace(tmp, path)
    except Exception:
        pass
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
