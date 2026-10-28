"""Đọc phụ đề cứng (chữ Trung in sẵn trên hình) thành SRT: đúng nội dung + đúng lúc hiện / tắt từng câu.

Phụ đề cứng do người làm phim căn tay theo miệng nhân vật → thời gian chuẩn hơn nhận dạng giọng (Whisper hay lệch, gộp câu,
nghe nhầm chữ). Cách làm: cắt riêng dải phụ đề, lấy mẫu `step` giây / khung; chỉ OCR khi dải phụ đề ĐỔI (so ảnh nét chữ sáng)
→ gộp các khung cùng câu thành 1 dòng (bắt đầu = khung đầu thấy, kết thúc = khung cuối thấy + step).
"""
import difflib
import re
import subprocess

from .text_cover import CJK, _probe
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
    key = json.dumps([os.path.abspath(video), st.st_size, int(st.st_mtime), [round(v, 3) for v in band], step, 3])
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


def _threads():
    """Luồng cho bộ đọc chữ: ~8 là nhanh nhất (16 chậm hơn; chia nhiều bộ 1 luồng chạy song song cũng chậm hơn — đã đo),
    trong ngân sách CPU chung của app (chế độ nhẹ máy tự giảm)."""
    from . import perf
    return max(1, min(8, perf.budget()))


def _reader(threads):
    """Bộ nhận dạng chữ của RapidOCR, nhưng BẬT vùng nhớ đệm của onnxruntime (RapidOCR tắt sẵn): ảnh dòng chữ mỗi lần một cỡ
    → không có vùng đệm thì mỗi lần đọc phải xin / trả bộ nhớ hệ điều hành → chậm ~8 lần (286 → 37 ms / khung, đã đo)."""
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR(intra_op_num_threads=threads)
    rec = ocr.text_rec
    try:
        import onnxruntime as ort
        old = rec.session.session
        so = ort.SessionOptions()
        so.log_severity_level = 4
        so.enable_cpu_mem_arena = True
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.intra_op_num_threads = threads
        rec.session.session = ort.InferenceSession(old._model_path, sess_options=so, providers=['CPUExecutionProvider'])
    except Exception:
        pass                                       # bản RapidOCR / onnxruntime khác → dùng bộ đọc mặc định (chỉ chậm hơn)

    def read(crops):
        (res, _) = rec(crops)
        return _clean(''.join(txt for (txt, sc) in res if sc > 0.5))
    return read


def _extract(video, band, step, log, should_stop, progress):
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
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
    total = int(dur / step) + 1
    log(f'   Đọc phụ đề cứng: {total} khung ({1 / step:g} khung/giây, dải phụ đề {band[1] * 100:.0f}–{band[3] * 100:.0f}% '
        f'chiều cao)...')
    # Khung đổi câu → gửi sang luồng đọc chữ, trong lúc đó giải mã / so nét khung tiếp (2 việc chạy chồng nhau). Việc "có cần
    # đọc không" chỉ dựa vào nét chữ (không cần chữ của khung trước) nên kết quả y hệt đọc lần lượt; khung "không đổi" lấy chữ
    # khung trước khi ghép lại theo thứ tự.
    frames = []                        # (t, chữ | Future | None = như khung trước, box)
    pending = []
    (prev_sig, n_ocr, k, cancelled) = (None, 0, 0, False)
    read = _reader(_threads())
    n_workers = 1
    pool = ThreadPoolExecutor(max_workers=n_workers)
    try:
        while True:
            if should_stop and should_stop():
                cancelled = True
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
                text = None                     # dải phụ đề không đổi → cùng câu, khỏi đọc lại
            else:
                crops = _line_crops(img, pix)
                n_ocr += 1
                text = pool.submit(read, crops) if crops else ''
                if crops:
                    pending.append(text)
            box = None
            if text != '':                           # khung bao nét chữ của câu (để che đúng chỗ nếu xoá nét còn sót)
                rows = np.where(pix.sum(axis=1) >= 3)[0]
                cols = np.where(pix.sum(axis=0) > 0)[0]
                if len(rows) and len(cols):
                    (bw_, bh_) = (band[2] - band[0], band[3] - band[1])
                    box = (band[0] + cols[0] / W * bw_, band[1] + rows[0] / H * bh_,
                           band[0] + (cols[-1] + 1) / W * bw_, band[1] + (rows[-1] + 1) / H * bh_)
            frames.append((t, text, box))
            prev_sig = sig
            if len(pending) > n_workers * 4:            # hàng chờ đọc không dồn quá dài (giữ RAM ảnh cắt, báo tiến độ đúng)
                pending.pop(0).result()
                pending = [f for f in pending if not f.done()]
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
        pool.shutdown(wait=True, cancel_futures=cancelled)
    if proc.returncode not in (0, None) or k * step < dur - max(2.0, 3 * step):
        log(f'   [WARN] Đọc phụ đề cứng dừng giữa chừng ({k * step:.0f}/{dur:.0f}s) — bỏ kết quả, chuyển sang nghe giọng nói', 'warn')
        return []
    resolved = []
    prev_text = ''
    for (t, text, box) in frames:
        if text is None:
            text = prev_text
        elif not isinstance(text, str):
            text = text.result()
        resolved.append((t, text, box))
        prev_text = text
    out = _build_cues(resolved, step, k * step)
    log(f'   Đọc phụ đề cứng xong: {len(out)} câu (OCR {n_ocr} lần / {len(frames)} khung)', 'ok')
    return out


MAX_CUE = 20.0          # 1 lần hiện > 20s liền → chữ đứng yên (tên kênh, tiêu đề), không phải 1 câu thoại
STATIC_SHARE = 0.15     # 1 dòng chữ hiện tổng cộng ≥ 15% thời lượng (và ≥ 30s) → chữ cố định chen giữa các câu thoại
STATIC_MIN_SEC = 30.0
LONG_REPEAT = (6, 6.0)  # lặp ≥ 6 lần VÀ mỗi lần (trung vị) ≥ 6s → chú thích / tiêu đề lặp lại; câu thoại hiện 1–3s


def _build_cues(frames, step, scanned):
    """frames = [(t, chữ, box)] theo thứ tự thời gian → gộp khung liên tiếp cùng câu thành dòng phụ đề, bỏ chữ cố định.
    Câu thoại ngắn hay lặp ("什么", "走吧"…) được GIỮ dù lặp bao nhiêu lần: chỉ bỏ dòng hiện quá lâu (1 lần > 20s), dòng tổng
    thời gian chiếm phần lớn video, hoặc dòng lặp nhiều lần mà lần nào cũng dài."""
    import statistics
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
    lens = {}
    for c in cues:
        c['text'] = max(c['votes'], key=c['votes'].get)       # bản đọc gặp nhiều nhất (OCR khung lẻ hay sai 1–2 chữ)
        lens.setdefault(c['text'], []).append(c['end'] - c['start'])
    static = {txt for (txt, ls) in lens.items()
              if (len(ls) >= 2 and sum(ls) >= max(STATIC_MIN_SEC, STATIC_SHARE * scanned))
              or (len(ls) >= LONG_REPEAT[0] and statistics.median(ls) >= LONG_REPEAT[1])}
    return [{'start': round(c['start'], 2), 'end': round(c['end'], 2), 'text': c['text'],
             **({'box': [round(float(v), 4) for v in c['box']]} if c.get('box') else {})} for c in cues
            if 0.3 <= c['end'] - c['start'] <= MAX_CUE and c['text'] not in static]
