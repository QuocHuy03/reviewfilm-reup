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

# voice_type → (tên hiển thị, resource_id, platform) — bộ giọng tiếng Việt của CapCut.
# platform: 'sami' / '11labs' = API web · 'pc' = API bản PC (giọng web từ chối, xem core/capcut_pc_tts.py)
VOICES = {
    'BV421_vivn_streaming': ('Nhỏ Ngọt Ngào', '7252594014782755330', 'sami'),
    'vi_female_huong': ('Giọng Nữ Phổ Thông', '7264854897953083905', 'sami'),
    'BV074_streaming': ('Cô Gái Hoạt Ngôn', '7102355709945188865', 'sami'),
    'BV074_streaming_dsp': ('Giọng Bé', '7550087831092251920', 'sami'),
    'vi-VN-HoaiMyNeural': ('Hoài My', '7371666434650280464', 'sami'),
    'vi-VN-NamMinhNeural': ('Nam Minh', '7371666524727153168', 'sami'),
    'BV562_streaming': ('Mai', '7483736254694035984', 'sami'),
    'BV075_streaming_vibrato_dsp': ('Việt Méo', '7569450639810465040', 'sami'),
    'BV075_streaming_demon_dsp': ('Kenny Đại Đế', '7569442422665661712', 'sami'),
    'ICL_uranus_vi_male_yuenan7': ('Chị Điềm Đạm', '7675973655645506823', 'sami'),
    'ICL_uranus_vi_female_wnns': ('Cô Gái Dịu Dàng', '7673002097943629077', 'sami'),
    'ICL_uranus_vi_female_yuenan1': ('Chị Dịu Dàng', '7675984617253375253', 'sami'),
    'ICL_uranus_vi_female_edujiyi': ('Mẹ Kế Khó Tính', '7668610635436969237', 'sami'),
    'ICL_uranus_vi_female_qcns': ('Nàng Tươi Tắn', '7673047160434330900', 'sami'),
    'multi_female_ling_uranus_bigtts': ('Cô bạn quốc dân', '7654506093162351888', 'pc'),
    'multi_female_ruan_uranus_bigtts': ('Bạn Vui', '7654500156078968065', 'pc'),
    'multi_female_hong_uranus_bigtts': ('Quan tòa minh mẫn', '7654504622752632081', 'pc'),
    'multi_female_partner_uranus_bigtts': ('Quản lý vững vàng', '7654501692376993040', 'pc'),
    'multi_female_linh_uranus_bigtts': ('Nàng tinh ranh', '7654503888757771536', 'pc'),
    'multi_female_wu_uranus_bigtts': ('Cô bạn khô cứng', '7654504114906238228', 'pc'),
    'ICL_uranus_vi_female_youxichuangzuozhe': ('Thủ Lĩnh Sáng Suốt', '7668610590360866069', 'sami'),
    'xPEfmymXC4WdBxGMznS7': ('Sài Nữ', '7491607853086544400', '11labs'),
    'pGapy9MNHCukzJtjavF0': ('Hà Nữ', '7491607926562361857', '11labs'),
    'ICL_uranus_vi_female_xfns': ('Cô Gái Năng Động', '7673039258290081045', 'sami'),
    'ICL_uranus_vi_female_cmns': ('Nàng Cá Tính', '7673043182887718165', 'sami'),
    'ICL_uranus_vi_female_shayazhiyu': ('Nhám Thơ', '7652257219190263056', 'sami'),
    'ICL_uranus_vi_female_gushinv': ('Thẳm Ẩn Nữ', '7652255965168897298', 'sami'),
    'ICL_uranus_vi_female_yuenan4': ('Nàng Điềm Tĩnh', '7675974812837219592', 'sami'),
    'ICL_uranus_vi_female_yuenan2': ('Chị Trưởng Thành', '7675924436867927312', 'sami'),
    'ICL_uranus_vi_female_yuenan3': ('Em Gái Ngọt Ngào', '7675982579366956308', 'sami'),
    'ICL_uranus_vi_female_xuemei': ('Mềm Họa Sĩ', '7652257336777542919', 'sami'),
    'ICL_uranus_vi_male_xinluyin': ('Người Kể Điềm Tĩnh', '7668606732947574036', 'sami'),
    'ICL_uranus_vi_male_kbpb': ('Chàng Trai Trầm Lắng', '7673045014242430215', 'sami'),
    'ICL_uranus_vi_male_yuenan9': ('Chàng Trai Sôi Nổi', '7675963775794564373', 'sami'),
    'ICL_uranus_vi_male_lizhipangbai': ('Người Kể Trầm Ấm', '7668606416185265428', 'sami'),
    'BV075_streaming': ('Giọng nam tự tin', '7102355803792740865', 'sami'),
    'multi_male_wumg_uranus_bigtts': ('Anh hiền lành', '7654506044130888981', 'pc'),
    'BV560_streaming': ('Anh Dũng', '7483736167565758992', 'sami'),
    'ICL_uranus_vi_male_byns': ('Chàng Trai U Sầu', '7673064079883259156', 'sami'),
    'ICL_uranus_vi_male_cfzc': ('Chàng Trai Ấm Áp', '7673075012848405761', 'sami'),
    'ICL_uranus_vi_male_jtcf': ('Chàng Trai Điềm Đạm', '7673036731419036948', 'sami'),
    '7hsfEc7irDn6E8br0qfw': ('Ly Nam', '7491608014181372417', '11labs'),
    '1d5Bb0SMBPB10Gx6iQeu': ('Duy Bắc', '7491608109043945985', '11labs'),
    'ueSxRO0nLF1bj93J2hVt': ('Trung Caha', '7491607775621943824', '11labs'),
    '9EE00wK5qV6tPtpQIxvy': ('Nam Trầm', '7493478233703191041', '11labs'),
    'ICL_uranus_vi_male_zhiyunan': ('Dịu Nhân Tử', '7652257230330416400', 'sami'),
    'BV075_streaming_robot_dsp': ('Robot VN', '7569440437006650641', 'sami'),
    'ICL_uranus_vi_male_shenchendiyu': ('Thánh nhân nhân hậu', '7660409721450417428', 'sami'),
    'ICL_uranus_vi_male_yuenan8': ('Anh Điềm Đạm', '7675941550794247442', 'sami'),
    'ICL_uranus_vi_male_qingxiunanhai': ('Dịu Trí Giả', '7652254612514180360', 'sami'),
}

MALE = {
    'vi-VN-NamMinhNeural',
    'BV075_streaming_vibrato_dsp',
    'BV075_streaming_demon_dsp',
    'ICL_uranus_vi_male_xinluyin',
    'ICL_uranus_vi_male_kbpb',
    'ICL_uranus_vi_male_yuenan9',
    'ICL_uranus_vi_male_lizhipangbai',
    'BV075_streaming',
    'multi_male_wumg_uranus_bigtts',
    'BV560_streaming',
    'ICL_uranus_vi_male_byns',
    'ICL_uranus_vi_male_cfzc',
    'ICL_uranus_vi_male_jtcf',
    '7hsfEc7irDn6E8br0qfw',
    '1d5Bb0SMBPB10Gx6iQeu',
    'ueSxRO0nLF1bj93J2hVt',
    '9EE00wK5qV6tPtpQIxvy',
    'ICL_uranus_vi_male_zhiyunan',
    'BV075_streaming_robot_dsp',
    'ICL_uranus_vi_male_shenchendiyu',
    'ICL_uranus_vi_male_yuenan8',
    'ICL_uranus_vi_male_qingxiunanhai',
}


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
    name, resource_id, platform = VOICES.get(voice_type, (voice_type, '', 'sami'))
    if platform == 'pc':
        return _synthesize_pc(items, voice_type, resource_id, speed)
    body = {'texts': [t for (t, _) in items], 'need_url': True,
            'tts_conf': {'speaker': voice_type, 'rate': round(speed, 2), 'volume': volume, 'name': name, 'platform': platform,
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


def _synthesize_pc(items, voice_type, resource_id, speed):
    """Giọng chỉ chạy qua API bản PC: mỗi đoạn 1 tác vụ (chạy song song) → {chỉ số: lỗi hoặc None}."""
    from concurrent.futures import ThreadPoolExecutor
    from core import capcut_pc_tts

    def _one(k):
        (text, out_path) = items[k]
        try:
            audio = capcut_pc_tts.synthesize(text, voice_type, resource_id, speed=speed)
        except Exception as e:
            return str(e)[:160]
        with open(out_path, 'wb') as f:
            f.write(audio)
        trim_silence(out_path)
        return None

    with ThreadPoolExecutor(min(4, len(items)) or 1) as ex:
        return dict(enumerate(ex.map(_one, range(len(items)))))


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
