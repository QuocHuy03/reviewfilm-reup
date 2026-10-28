"""Đọc phụ đề cứng (chữ Trung in sẵn trên hình) thành SRT: đúng nội dung + đúng lúc hiện / tắt từng câu.

Phụ đề cứng do người làm phim căn tay theo miệng nhân vật → thời gian chuẩn hơn nhận dạng giọng (Whisper hay lệch, gộp câu,
nghe nhầm chữ). Cách làm: cắt riêng dải phụ đề, lấy mẫu `step` giây / khung; chỉ OCR khi dải phụ đề ĐỔI (so ảnh nét chữ sáng)
→ gộp các khung cùng câu thành 1 dòng (bắt đầu = khung đầu thấy, kết thúc = khung cuối thấy + step).
"""
import difflib
import re
import subprocess

from .text_cover import CJK, _engine, _probe
from .utils import FFMPEG_EXE, _HIDE

BAND_W = 960                       # bề ngang dải phụ đề khi đọc — đủ nét cho chữ Hán nhỏ


def _text_pixels(gray):
    """Điểm ảnh nét chữ phụ đề: sáng hẳn VÀ có viền tối sát bên (chữ trắng viền đen) — nền sáng (trời, đèn) không bị nhầm."""
    import cv2
    import numpy as np
    dark = cv2.dilate((gray < 60).astype(np.uint8), np.ones((5, 5), np.uint8))
    return ((gray > 190) & (dark > 0)).astype(np.uint8)


def _signature(pix):
    """Ảnh nét chữ thu nhỏ (khối 4×8) — so 2 khung để biết dải phụ đề có đổi câu không mà khỏi đọc lại."""
    h, w = pix.shape
    return pix[: h - h % 4, : w - w % 8].reshape(h // 4, 4, w // 8, 8).mean(axis=(1, 3))


def _line_crops(img, pix):
    """Cắt sát từng dòng chữ (theo nét chữ tìm được) để đưa thẳng vào bước nhận dạng chữ — bỏ bước dò vị trí (chậm)."""
    import numpy as np
    rows = np.where(pix.sum(axis=1) >= 3)[0]
    if not len(rows):
        return []
    (groups, start) = ([], rows[0])
    for (a, b) in zip(rows, rows[1:]):
        if b - a > 4:                            # khoảng trống giữa 2 dòng phụ đề
            groups.append((start, a))
            start = b
    groups.append((start, rows[-1]))
    crops = []
    (H, W) = pix.shape
    for (r0, r1) in groups:
        if r1 - r0 < 8:
            continue
        cols = np.where(pix[r0:r1 + 1].sum(axis=0) > 0)[0]
        if not len(cols):
            continue
        pad = max(4, (r1 - r0) // 4)
        crops.append(img[max(0, r0 - pad):min(H, r1 + pad + 1), max(0, cols[0] - pad):min(W, cols[-1] + pad + 1)])
    return crops


def _clean(txt):
    """Chỉ giữ chữ Hán / số / dấu câu tiếng Trung — bỏ ký tự OCR nhiễu."""
    t = re.sub(r'\s+', '', txt or '')
    t = re.sub(r'[^\w　-〿＀-￯，。！？、：；“”‘’《》…—·]', '', t)
    return t if CJK.search(t) else ''


def _same(a, b):
    return a == b or (a and b and difflib.SequenceMatcher(None, a, b).ratio() >= 0.7)


def _cache_file(video, band, step):
    import hashlib
    import json
    import os
    from app.config import DATA_DIR
    st = os.stat(video)
    key = json.dumps([os.path.abspath(video), st.st_size, int(st.st_mtime), [round(v, 3) for v in band], step, 2])
    d = os.path.join(DATA_DIR, 'cache', 'hardsub')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.md5(key.encode()).hexdigest() + '.json')


def extract(video, band, step=0.2, log=print, should_stop=None, progress=None):
    """band = [x1, y1, x2, y2] (0-1 hình gốc) dải phụ đề. → [{'start', 'end', 'text'}] theo thời gian video gốc.
    Lưu cache theo video + dải + bước → chạy lại (lồng tiếng lại, app tắt giữa chừng) khỏi đọc lại cả phim."""
    import json
    try:
        cache = _cache_file(video, band, step)
    except OSError:
        cache = None
    if cache:
        try:
            with open(cache, encoding='utf-8') as f:
                cues = json.load(f)
            log(f'   Đọc phụ đề cứng: dùng lại kết quả đã đọc ({len(cues)} câu)', 'ok')
            return cues
        except (OSError, ValueError):
            pass
    cues = _extract(video, band, step, log, should_stop, progress)
    if cues and cache and not (should_stop and should_stop()):
        try:
            with open(cache, 'w', encoding='utf-8') as f:
                json.dump(cues, f, ensure_ascii=False)
        except OSError:
            pass
    return cues


def _extract(video, band, step, log, should_stop, progress):
    import numpy as np
    (sw, sh, dur) = _probe(video)
    if not sw or not sh or not dur:
        return []
    (x1, y1, x2, y2) = (int(band[0] * sw), int(band[1] * sh), int(band[2] * sw), int(band[3] * sh))
    (cw, ch) = (max(16, (x2 - x1) // 2 * 2), max(8, (y2 - y1) // 2 * 2))
    W = BAND_W
    H = max(16, int(round(ch * W / cw / 2)) * 2)
    cmd = [FFMPEG_EXE, '-v', 'error', '-i', video, '-vf', f'fps=1/{step},crop={cw}:{ch}:{x1}:{y1},scale={W}:{H}',
           '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_HIDE)
    ocr = _engine()
    total = int(dur / step) + 1
    log(f'   Đọc phụ đề cứng: {total} khung ({1 / step:g} khung/giây, dải phụ đề {band[1] * 100:.0f}–{band[3] * 100:.0f}% chiều cao)...')
    frames = []                        # (t, text)
    (prev_sig, prev_text, n_ocr, k) = (None, '', 0, 0)
    try:
        while True:
            if should_stop and should_stop():
                proc.kill()
                return []
            raw = proc.stdout.read(W * H * 3)
            if len(raw) < W * H * 3:
                break
            t = k * step
            k += 1
            img = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
            pix = _text_pixels(img.max(axis=2))
            sig = _signature(pix)
            if int(pix.sum()) < 60:
                text = ''                       # không có nét chữ phụ đề
            elif prev_sig is not None and float(np.abs(sig - prev_sig).mean()) < 0.006:
                text = prev_text                # dải phụ đề không đổi → cùng câu, khỏi đọc lại
            else:
                crops = _line_crops(img, pix)
                n_ocr += 1
                (rec, _) = ocr.text_rec(crops) if crops else ([], 0)
                text = _clean(''.join(txt for (txt, sc) in rec if sc > 0.5))
            box = None
            if text:                                 # khung bao nét chữ của câu (để che đúng chỗ nếu xoá nét còn sót)
                rows = np.where(pix.sum(axis=1) >= 3)[0]
                cols = np.where(pix.sum(axis=0) > 0)[0]
                if len(rows) and len(cols):
                    (bw_, bh_) = (band[2] - band[0], band[3] - band[1])
                    box = (band[0] + cols[0] / W * bw_, band[1] + rows[0] / H * bh_,
                           band[0] + (cols[-1] + 1) / W * bw_, band[1] + (rows[-1] + 1) / H * bh_)
            frames.append((t, text, box))
            (prev_sig, prev_text) = (sig, text)
            if progress and k % 50 == 0:
                progress(min(100, int(k * 100 / total)))
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.stdout.close()
            proc.wait(timeout=10)
        except Exception:
            pass
    if proc.returncode not in (0, None) or k * step < dur - max(2.0, 3 * step):
        log(f'   [WARN] Đọc phụ đề cứng dừng giữa chừng ({k * step:.0f}/{dur:.0f}s) — bỏ kết quả, chuyển sang nghe giọng nói', 'warn')
        return []
    # gộp khung liên tiếp cùng câu → dòng phụ đề
    cues = []
    for (t, text, box) in frames:
        if not text:
            continue
        c = cues[-1] if cues else None
        if c and _same(text, c['text']) and t - c['end'] <= step * 1.5 + 1e-6:
            c['end'] = t + step
            c['votes'][text] = c['votes'].get(text, 0) + 1
            if box:
                c['box'] = box if not c.get('box') else (min(c['box'][0], box[0]), min(c['box'][1], box[1]),
                                                          max(c['box'][2], box[2]), max(c['box'][3], box[3]))
        else:
            cues.append({'start': t, 'end': t + step, 'text': text, 'votes': {text: 1}, 'box': box})
    # chữ đứng yên quá lâu (watermark / tiêu đề nằm trong dải) hoặc lặp lại khắp phim → không phải lời thoại
    seen = {}
    for c in cues:
        c['text'] = max(c['votes'], key=c['votes'].get)       # bản đọc gặp nhiều nhất (OCR khung lẻ hay sai 1–2 chữ)
        seen[c['text']] = seen.get(c['text'], 0) + 1
    out = [{'start': round(c['start'], 2), 'end': round(c['end'], 2), 'text': c['text'],
            **({'box': [round(float(v), 4) for v in c['box']]} if c.get('box') else {})} for c in cues
           if c['end'] - c['start'] >= 0.3 and c['end'] - c['start'] <= 20 and seen[c['text']] <= 6]
    log(f'   Đọc phụ đề cứng xong: {len(out)} câu (OCR {n_ocr} lần / {len(frames)} khung)', 'ok')
    return out
