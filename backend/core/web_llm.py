"""
Tài khoản AI web (ChatGPT / Gemini đã đăng nhập trong app) — gọi qua server loopback của Electron.

Electron truyền RF_WEB_LLM_URL + RF_WEB_LLM_TOKEN khi spawn backend (electron/ai/localServer.js).
Chạy backend riêng (không qua Electron) thì available() = False và mọi thứ rơi về API key như cũ.

Engine 'web' dùng chung khuôn (engine, key) của script_writer/translator: key là WEB_KEY (giá trị giả,
chỉ để lọt qua các bộ lọc `if k`).
"""
import math
import os
import re
import time
import unicodedata

import requests

WEB_KEY = 'web'
_status_cache = {'t': 0.0, 'v': {'chatgpt': False, 'gemini': False}}


def _base():
    return (os.environ.get('RF_WEB_LLM_URL') or '').rstrip('/')


def _headers():
    return {'Authorization': f"Bearer {os.environ.get('RF_WEB_LLM_TOKEN', '')}", 'Content-Type': 'application/json'}


def status(force=False):
    """{'chatgpt': bool, 'gemini': bool} — cache 10s để không hỏi Electron mỗi lượt gọi."""
    if not _base():
        return {'chatgpt': False, 'gemini': False}
    if not force and time.time() - _status_cache['t'] < 10:
        return _status_cache['v']
    try:
        r = requests.get(_base() + '/rf/status', headers=_headers(), timeout=5)
        v = r.json() if r.status_code == 200 else {}
    except Exception:
        v = {}
    v = {'chatgpt': bool(v.get('chatgpt')), 'gemini': bool(v.get('gemini'))}
    _status_cache.update(t=time.time(), v=v)
    return v


def available():
    s = status()
    return s['chatgpt'] or s['gemini']


def gemini_ready():
    return status()['gemini']




def with_web(engines):
    """Đặt ('web', WEB_KEY) lên đầu chuỗi engine. engines: [(name, key), ...]."""
    engines = [(e, k) for (e, k) in engines if k and e != 'web']
    return [('web', WEB_KEY)] + engines if available() else engines


# ChatGPT web hay bọc câu trả lời dài trong khối "writing/canvas":
#   :::writing{variant="document" id="48291" title="..."}  …nội dung…  :::
# Không bóc ra thì dòng đó lọt vào kịch bản, bị đổi số thành chữ và đọc thành giọng.
_BLOCK_OPEN = re.compile(r'^\s*:::[\w-]+(?:\{[^}\n]*\})?\s*$', re.M)
_BLOCK_CLOSE = re.compile(r'^\s*:::\s*$', re.M)
_ZERO_WIDTH = re.compile('[​‌‍⁠﻿]')
_DEBUG_KEEP = 30


def clean_reply(text):
    """Chuẩn hoá câu trả lời AI web: Unicode NFC, bỏ ký tự vô hình, bỏ khung khối writing/canvas."""
    text = unicodedata.normalize('NFC', text or '')
    text = _ZERO_WIDTH.sub('', text)
    text = _BLOCK_OPEN.sub('', text)
    text = _BLOCK_CLOSE.sub('', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _dump_debug(prompt, raw, model):
    """Lưu nguyên văn N lượt gần nhất vào <data>/llm_debug — để chẩn đoán khi kịch bản/bản dịch ra lạ."""
    try:
        from app.config import DATA_DIR
        d = os.path.join(DATA_DIR, 'llm_debug')
        os.makedirs(d, exist_ok=True)
        name = time.strftime('%Y%m%d_%H%M%S') + f'_{int(time.time() * 1000) % 1000:03d}.txt'
        with open(os.path.join(d, name), 'w', encoding='utf-8') as f:
            f.write(f'# model: {model}\n# ===== PROMPT ({len(prompt)} ký tự) =====\n{prompt}\n\n'
                    f'# ===== RAW REPLY ({len(raw)} ký tự) =====\n{raw}\n')
        for old in sorted(os.listdir(d))[:-_DEBUG_KEEP]:
            os.remove(os.path.join(d, old))
    except Exception:
        pass


def chat(prompt, log_fn=print, model='auto', timeout=900):
    """Một lượt text. model: 'auto' (ChatGPT → Gemini) | 'chatgpt' | 'gemini'. Lỗi → ''."""
    if not _base():
        return ''
    payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}]}
    for attempt in range(2):
        try:
            from core import cancel
            r = cancel.run(lambda: requests.post(_base() + '/v1/chat/completions', headers=_headers(), json=payload, timeout=timeout))
            if r.status_code == 200:
                rj = r.json()
                raw = ((rj.get('choices') or [{}])[0].get('message', {}).get('content') or '')
                _dump_debug(prompt, raw, rj.get('model', '?'))
                txt = clean_reply(raw)
                if txt:
                    log_fn(f"   [AI web] {rj.get('model', '?')} trả {len(txt)} ký tự")
                    return txt
                log_fn('   [WARN] Tài khoản AI web trả về rỗng.')
            else:
                msg = _err_msg(r)
                log_fn(f'   [WARN] Tài khoản AI web HTTP {r.status_code}: {msg}')
                if r.status_code in (401, 403):
                    _status_cache['t'] = 0
                    return ''
        except Exception as e:
            from core import cancel
            if isinstance(e, cancel.Cancelled):
                raise
            log_fn(f'   [WARN] Tài khoản AI web lỗi (lần {attempt + 1}/2): {str(e)[:150]}')
        time.sleep(3)
    return ''


def gemini_files(prompt, files, log_fn=print, timeout=900):
    """Gửi prompt + file trên máy (ảnh/video) cho Gemini web. Lỗi → ''."""
    if not _base():
        return ''
    payload = {'prompt': prompt, 'files': [os.path.abspath(f) for f in files], 'timeout': timeout * 1000}
    for attempt in range(2):
        try:
            from core import cancel
            r = cancel.run(lambda: requests.post(_base() + '/rf/gemini/files', headers=_headers(), json=payload, timeout=timeout + 60))
            if r.status_code == 200:
                raw = r.json().get('content') or ''
                _dump_debug(prompt, raw, 'gemini-web')
                txt = clean_reply(raw)
                if txt:
                    return txt
                log_fn('   [WARN] Gemini web trả về rỗng.')
            else:
                log_fn(f'   [WARN] Gemini web HTTP {r.status_code}: {_err_msg(r)}')
                if r.status_code in (401, 403):
                    _status_cache['t'] = 0
                    return ''
        except Exception as e:
            from core import cancel
            if isinstance(e, cancel.Cancelled):
                raise
            log_fn(f'   [WARN] Gemini web lỗi (lần {attempt + 1}/2): {str(e)[:150]}')
        time.sleep(5)
    return ''




def _err_msg(r):
    try:
        return str(r.json().get('error', {}).get('message', ''))[:200]
    except Exception:
        return r.text[:200]


# Gemini web nhận tối đa ~10 file/lượt → ghép nhiều khung hình thành "contact sheet" có nhãn thời gian.
MAX_SHEETS = 10
TILE_W = 384


def build_contact_sheets(frames, out_dir, max_sheets=MAX_SHEETS, cols=4):
    """frames: [(ts, path), ...] → [sheet_path, ...]. Mỗi ô ghi '#N  12.3s' khớp thứ tự khung hình."""
    import cv2
    import numpy as np
    os.makedirs(out_dir, exist_ok=True)
    n = len(frames)
    if not n:
        return []
    per = max(1, math.ceil(n / max_sheets))
    if n <= 4:
        cols = n
    sheets = []
    for s in range(0, n, per):
        chunk = list(enumerate(frames))[s:s + per]
        tiles = []
        for (idx, (ts, fp)) in chunk:
            img = cv2.imread(fp)
            if img is None:
                continue
            h = int(img.shape[0] * TILE_W / img.shape[1])
            img = cv2.resize(img, (TILE_W, h), interpolation=cv2.INTER_AREA)
            label = f'#{idx + 1}  {ts:.1f}s'
            cv2.putText(img, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(img, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            tiles.append(img)
        if not tiles:
            continue
        th = max(t.shape[0] for t in tiles)
        c = min(cols, len(tiles))
        rows = math.ceil(len(tiles) / c)
        sheet = np.zeros((rows * th, c * TILE_W, 3), dtype=np.uint8)
        for (k, t) in enumerate(tiles):
            (r_, c_) = divmod(k, c)
            sheet[r_ * th:r_ * th + t.shape[0], c_ * TILE_W:(c_ + 1) * TILE_W] = t
        out = os.path.join(out_dir, f'sheet_{len(sheets):02d}_{int(time.time() * 1000) % 100000}.jpg')
        cv2.imwrite(out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
        sheets.append(out)
    return sheets


def gemini_vision(prompt, frames, log_fn=print, work_dir=None):
    """Thay cho OpenAI Vision: ghép khung hình → contact sheet → Gemini web."""
    if not frames:
        return ''
    first = frames[0][1] if isinstance(frames[0], (tuple, list)) else frames[0]
    norm = [(f[0], f[1]) if isinstance(f, (tuple, list)) else (float(i), f) for (i, f) in enumerate(frames)]
    work_dir = work_dir or os.path.join(os.path.dirname(first), '_sheets')
    try:
        sheets = build_contact_sheets(norm, work_dir)
    except Exception as e:
        log_fn(f'   [WARN] Không ghép được contact sheet: {str(e)[:120]}')
        return ''
    if not sheets:
        return ''
    note = (f'\n\nGHI CHÚ ẢNH ĐÍNH KÈM: {len(norm)} khung hình được ghép thành {len(sheets)} ảnh lưới. '
            'Mỗi ô có nhãn "#N  T s" ở góc trên trái = Khung hình thứ N, trích tại giây T. '
            'Đọc các ô theo thứ tự trái→phải, trên→dưới. Chỉ trả lời bằng JSON đúng yêu cầu ở trên, không thêm chữ nào khác.')
    log_fn(f'   [AI web] Gửi {len(norm)} khung hình ({len(sheets)} ảnh lưới) cho Gemini...')
    return gemini_files(prompt + note, sheets, log_fn)
