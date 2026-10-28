"""Xoá sạch chữ cứng trên video theo NÉT CHỮ (không xoá cả khung) — cách các bản vietsub "sạch" làm.

1. Mặt nạ nét chữ: chữ trắng / vàng sáng + VIỀN TỐI ngay sát chữ (tự theo độ dày viền từng chữ) + 2px chống răng cưa.
2. Lấp bằng hình THẬT ở khung lân cận (trước / sau ≤ ~0.5s): căn độ dịch hình bằng vùng nền quanh chữ (phase
   correlation), chỉ nhận khi khớp tốt — khi máy quay lia / chữ đổi câu, nền sau chữ lộ ra ở khung khác → chép sang.
3. Điểm ảnh khung nào cũng bị chữ che → lấp từ điểm xung quanh (OpenCV Telea), viền mặt nạ hoà mềm.
Khung không có chữ → mặt nạ rỗng → giữ nguyên hình (không che sớm / muộn). Chạy song song nhiều nhân CPU.
Ra một video trung gian sạch chữ (giữ tiếng) để bước dựng dùng thay video gốc.
"""
import json
import subprocess

from .utils import FFMPEG_EXE, FFPROBE_EXE, _HIDE, register_process, unregister_process

OFFSETS = (3, -3, 8, -8, 15, -15)                     # khung lân cận thử lần lượt (gần trước)
MAX_OFF = max(abs(o) for o in OFFSETS)


def _probe(path):
    r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                        'stream=width,height,avg_frame_rate:format=duration', '-of', 'json', path],
                       capture_output=True, text=True, creationflags=_HIDE)
    d = json.loads(r.stdout or '{}')
    s = (d.get('streams') or [{}])[0]
    try:
        (n, m) = (s.get('avg_frame_rate') or '30/1').split('/')
        fps = float(n) / float(m or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    return int(s.get('width') or 0), int(s.get('height') or 0), (fps if 5 <= fps <= 120 else 30.0), float((d.get('format') or {}).get('duration') or 0)


def stroke_mask(roi, edges=(False, False, False, False)):
    """Mặt nạ nét chữ (BGR roi → uint8 0/255 hoặc None).
    Điểm sáng trắng / vàng → giữ những mảng GIỐNG NÉT CHỮ: nằm gọn trong vùng (không chạm mép — vỏ dưa, mảng sáng
    nền thường tràn ra ngoài vùng) và nét mảnh (chữ mảnh, mảng sáng nền thì dày). Nới một vòng mỏng trùm viền + răng cưa.
    edges = (trái, trên, phải, dưới): cạnh vùng trùng mép khung hình — chữ (vd watermark ở góc) chạm cạnh đó vẫn là chữ."""
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    white = (gray > 200) & (hsv[..., 1] < 70)
    yellow = (hsv[..., 0] >= 15) & (hsv[..., 0] <= 40) & (hsv[..., 1] > 110) & (hsv[..., 2] > 170)
    bright = (white | yellow).astype(np.uint8) * 255
    if cv2.countNonZero(bright) < 20:
        return None
    (rh, rw) = roi.shape[:2]
    line_h = rh / 1.6                                 # vùng đã nới 0.3 lần cao dòng mỗi phía
    (n, labels, st, _) = cv2.connectedComponentsWithStats(bright, connectivity=8)
    dist = cv2.distanceTransform(bright, cv2.DIST_L2, 3)
    keep = np.zeros(n, bool)
    max_half = max(2.0, line_h * 0.09)                # nửa độ dày nét chữ tối đa (~18% cao dòng)
    for k in range(1, n):
        (x, y, w, h, area) = st[k]
        if area < 4:
            continue
        # chạm cạnh vùng (cạnh nằm TRONG khung hình) → nền tràn vào, không phải chữ
        if (x <= 0 and not edges[0]) or (y <= 0 and not edges[1]) or (x + w >= rw and not edges[2]) or (y + h >= rh and not edges[3]):
            continue
        if h > line_h * 1.3:                          # cao hơn cả dòng chữ
            continue
        if float(dist[y:y + h, x:x + w][labels[y:y + h, x:x + w] == k].max()) > max_half:   # mảng dày → không phải nét
            continue
        keep[k] = True
    text = (keep[labels] * 255).astype(np.uint8)
    if cv2.countNonZero(text) < 20:
        return None
    # nét chữ + một vòng mỏng quanh (~12% cao dòng ≈ viền đen + răng cưa + bóng) — không lan ra nền tối xung quanh
    k = max(5, int(line_h * 0.12)) | 1
    return cv2.dilate(text, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))


def _soft(img):
    import cv2
    return cv2.blur(img, (15, 15))


def _telea(img, mask):
    """Lấp mặt nạ từ điểm xung quanh (Telea) — ở ½ độ phân giải cho nhanh (vùng lấp vốn mịn)."""
    import cv2
    (rh, rw) = img.shape[:2]
    if rh >= 60 and rw >= 60:
        small = cv2.resize(img, (rw // 2, rh // 2), interpolation=cv2.INTER_AREA)
        msmall = cv2.resize(mask, (rw // 2, rh // 2), interpolation=cv2.INTER_NEAREST)
        return cv2.resize(cv2.inpaint(small, msmall, 3, cv2.INPAINT_TELEA), (rw, rh), interpolation=cv2.INTER_LINEAR)
    return cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)


def _fill(roi, mask, neighbors):
    """Lấp vùng mặt nạ: điểm ảnh THẬT ở khung lân cận (đã căn độ dịch) nếu hợp với ước lượng Telea, còn lại Telea.
    Mỗi điểm chép sang phải gần màu ước lượng → loại được phần sót của chữ ở khung lân cận và chỗ căn lệch."""
    import cv2
    import numpy as np
    (rh, rw) = roi.shape[:2]
    remaining = mask > 0
    tel = _telea(roi, mask)
    # Telea để lại mảng góc cạnh (nhất là nền bokeh / chi tiết) → làm mịn phần lấp cho tan vào nền
    tel = cv2.GaussianBlur(tel, (0, 0), max(1.5, rh * 0.015))
    out = roi.copy()
    out[remaining] = tel[remaining]
    tg = cv2.cvtColor(tel, cv2.COLOR_BGR2GRAY).astype(np.int16)
    g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    ring = (cv2.dilate(mask, np.ones((15, 15), np.uint8)) > 0) & ~remaining      # nền ngay quanh chữ — để kiểm tra khớp
    if ring.sum() > 50 and neighbors:
        (sw, sh) = (max(16, rw // 2), max(16, rh // 2))
        small = lambda a: cv2.resize(a, (sw, sh), interpolation=cv2.INTER_AREA).astype(np.float32)
        base = small(np.where(remaining, tg.astype(np.uint8), g).astype(np.uint8))      # chữ thay bằng ước lượng khi đo độ dịch
        grow = np.ones((9, 9), np.uint8)
        for (nroi, nmask) in neighbors:
            if not remaining.any():
                break
            ng = cv2.cvtColor(nroi, cv2.COLOR_BGR2GRAY)
            nm8 = nmask if nmask is not None else np.zeros((rh, rw), np.uint8)
            nfill = small(np.where(nm8 > 0, cv2.blur(ng, (15, 15)), ng).astype(np.uint8))
            ((dx, dy), _) = cv2.phaseCorrelate(base, nfill)
            (dx, dy) = (dx * rw / sw, dy * rh / sh)
            if abs(dx) > rw * 0.25 or abs(dy) > rh * 0.4:
                continue
            M = np.float32([[1, 0, -dx], [0, 1, -dy]])
            warped = cv2.warpAffine(nroi, M, (rw, rh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            wmask = cv2.warpAffine(cv2.dilate(nm8, grow), M, (rw, rh), flags=cv2.INTER_NEAREST,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=255) > 0     # nới mặt nạ khung lân cận: không chép viền chữ sót
            wg = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY).astype(np.int16)
            chk = ring & ~wmask
            if chk.sum() < 50 or float(np.mean(np.abs(wg[chk] - g[chk].astype(np.int16)))) > 8.0:   # căn không khớp
                continue
            use = remaining & ~wmask & (np.abs(wg - tg) < 32)                 # điểm chép phải hợp với ước lượng xung quanh
            out[use] = warped[use]
            remaining &= ~use
    a = cv2.GaussianBlur(mask, (0, 0), 1.5).astype(np.float32)[..., None] / 255.0   # viền mặt nạ hoà mềm
    return (out * a + roi * (1 - a)).astype(np.uint8)


def _masks(raw, w, h, items, templates=None):
    """Mặt nạ nét chữ của 1 khung cho các vùng {chỉ số vùng: (x1, y1, x2, y2)}.
    Vùng watermark cố định có MẪU (học từ nhiều khung) → luôn dùng mẫu, kể cả cảnh nền sáng chữ hoà vào nền."""
    import cv2
    import numpy as np
    img = np.frombuffer(raw, np.uint8).reshape(h, w, 3)
    out = {}
    for (i, (x1, y1, x2, y2)) in items.items():
        mk = stroke_mask(img[y1:y2, x1:x2], (x1 <= 0, y1 <= 0, x2 >= w, y2 >= h))
        tpl = (templates or {}).get(i)
        if tpl is not None:
            mk = tpl if mk is None else cv2.bitwise_or(mk, tpl)
        out[i] = mk
    return out


def _learn_templates(video, items, w, h, dur, log):
    """Watermark / logo cố định (hiện ≥ ½ video): lấy ~40 khung rải đều, điểm nào là nét chữ ở ≥ 30% số khung
    nhận ra được → mẫu nét chữ cố định. Cảnh nền sáng (chữ trắng trên trời trắng) không tự nhận ra được vẫn xoá đúng."""
    import cv2
    import numpy as np
    out = {}
    for (i, (t0, t1, x1, y1, x2, y2)) in enumerate(items):
        if dur <= 0 or (min(t1, dur) - max(t0, 0.0)) < 0.5 * dur:
            continue
        (a, b) = (max(0.0, t0) + 0.5, min(dur, t1) - 0.5)
        cnt = np.zeros((y2 - y1, x2 - x1), np.float32)
        valid = 0
        for k in range(40):
            t = a + (b - a) * (k + 0.5) / 40
            raw = subprocess.run([FFMPEG_EXE, '-v', 'error', '-ss', f'{t:.2f}', '-i', video, '-frames:v', '1', '-f', 'rawvideo',
                                  '-pix_fmt', 'bgr24', '-'], capture_output=True, creationflags=_HIDE).stdout
            if len(raw) < w * h * 3:
                continue
            img = np.frombuffer(raw[:w * h * 3], np.uint8).reshape(h, w, 3)
            mk = stroke_mask(img[y1:y2, x1:x2], (x1 <= 0, y1 <= 0, x2 >= w, y2 >= h))
            if mk is not None:
                cnt += mk > 0
                valid += 1
        if valid >= 5:
            tpl = ((cnt >= max(3, 0.3 * valid)) * 255).astype(np.uint8)
            if cv2.countNonZero(tpl) > 30:
                out[i] = cv2.dilate(tpl, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
                log(f'   Học mẫu watermark cố định (vùng {i + 1}): {valid}/40 khung nhận ra chữ')
    return out


def _clean_frame(k, frames, w, h, active):
    """Xoá nét chữ ở khung k (frames: {chỉ số khung: (raw, future mặt nạ)}). Chạy song song — OpenCV nhả GIL khi tính."""
    import numpy as np
    (raw, mfut) = frames[k]
    if not active:
        return (raw, 0)
    masks = mfut.result()
    img = np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy()
    n = 0
    for (i, (x1, y1, x2, y2)) in active.items():
        mk = masks.get(i)
        if mk is None:
            continue
        neigh = []
        for off in OFFSETS:
            nb = frames.get(k + off)
            if nb is None:
                continue
            nimg = np.frombuffer(nb[0], np.uint8).reshape(h, w, 3)
            neigh.append((nimg[y1:y2, x1:x2], nb[1].result().get(i)))
        img[y1:y2, x1:x2] = _fill(img[y1:y2, x1:x2], mk, neigh)
        n += 1
    return (img.tobytes(), n)


class _Done:
    """Future đã xong sẵn (khung không có vùng chữ nào gần)."""
    def __init__(self, v):
        self._v = v

    def result(self):
        return self._v


def clean_video(video, regions, out_path, log=print, progress=None, should_stop=None):
    """→ out_path (video sạch chữ, giữ tiếng) hoặc None nếu không có gì để xoá / lỗi."""
    import os
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor
    (w, h, fps, dur) = _probe(video)
    if not w or not h or not regions:
        return None
    items = []                                   # (t0, t1, x1, y1, x2, y2) — nới 0.6s; mặt nạ theo nét chữ nên khung không chữ giữ nguyên
    for r in regions:
        (x1, y1, x2, y2) = r['box']
        bh = (y2 - y1) * h
        (px1, py1) = (max(0, int(x1 * w - bh * 0.3)), max(0, int(y1 * h - bh * 0.3)))
        (px2, py2) = (min(w, int(x2 * w + bh * 0.3)), min(h, int(y2 * h + bh * 0.3)))
        if px2 - px1 > 8 and py2 - py1 > 8:
            items.append((float(r['t_start']) - 0.6, float(r['t_end']) + 0.6, px1, py1, px2, py2))
    if not items:
        return None
    # gộp vùng sát nhau cùng lúc (vd watermark 2 dòng có "&" ở giữa — ký tự không phải chữ Trung nên không quét ra)
    merged = True
    while merged:
        merged = False
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                (A, B) = (items[a], items[b])
                (ha, hb) = (A[5] - A[3], B[5] - B[3])
                gap_y = max(A[3], B[3]) - min(A[5], B[5])
                ox = min(A[4], B[4]) - max(A[2], B[2])
                if A[0] <= B[1] and B[0] <= A[1] and gap_y < 0.6 * min(ha, hb) and ox > 0.5 * min(A[4] - A[2], B[4] - B[2]):
                    items[a] = (min(A[0], B[0]), max(A[1], B[1]), min(A[2], B[2]), min(A[3], B[3]), max(A[4], B[4]), max(A[5], B[5]))
                    del items[b]
                    merged = True
                    break
            if merged:
                break
    items.sort()
    templates = _learn_templates(video, items, w, h, dur, log)
    pad = (MAX_OFF + 2) / fps                    # khung lân cận cần mặt nạ của cùng vùng

    def active_at(t, extra=0.0):
        return {i: it[2:] for (i, it) in enumerate(items) if it[0] - extra <= t <= it[1] + extra}

    from core.utils import _budgeted
    from core import perf as _perf
    with _perf.parallel(4):                      # giải mã + mã hoá chỉ cần ít luồng — phần lớn CPU cho các luồng xoá chữ
        dec_cmd = _budgeted([FFMPEG_EXE, '-v', 'error', '-i', video, '-vf', f'fps={fps:.6f}', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'])
        from core import encoder as _encoder
        _enc_args = _encoder.video_args('intermediate')[:-2]   # bỏ -pix_fmt (đã đặt riêng ở dưới)
        enc_cmd = _budgeted([FFMPEG_EXE, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', f'{fps:.6f}',
                             '-i', '-', '-i', video, '-map', '0:v', '-map', '1:a?', *_enc_args,
                             '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-shortest', out_path])
    dec = subprocess.Popen(dec_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_HIDE)
    enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_HIDE)
    register_process(dec)
    register_process(enc)
    size = w * h * 3
    total = int(dur * fps) or 1
    from core import perf
    workers = max(2, min(20, perf.budget()))     # ngân sách CPU chung (chế độ nhẹ máy → một nửa)
    try:                                         # máy thiếu RAM (app khác chiếm nhiều) → bớt luồng, khỏi sập app giữa chừng
        import psutil
        free_gb = psutil.virtual_memory().available / 1024 ** 3
        cap = max(2, int((free_gb - 1.5) / 0.35))   # ~0.35GB / luồng ở 1080p, chừa 1.5GB cho máy
        if cap < workers:
            log(f'   RAM trống còn {free_gb:.1f}GB — xoá chữ chạy {cap} luồng (thay vì {workers}) cho an toàn')
            workers = cap
    except Exception:
        pass
    mask_pool = ThreadPoolExecutor(max(2, workers // 2))
    fill_pool = ThreadPoolExecutor(workers)
    frames = {}                                  # chỉ số khung → (raw, future mặt nạ)
    actives = {}
    pending = deque()                            # (chỉ số khung, future kết quả) theo thứ tự ghi
    stats = {'touched': 0, 'written': 0}
    ok = False

    def flush(force=False):
        while pending and (force or len(pending) >= workers * 2 or pending[0][1].done()):
            (k, fut) = pending.popleft()
            (out, n) = fut.result()
            enc.stdin.write(out)
            stats['touched'] += n
            stats['written'] += 1
            for old in [x for x in frames if x < k - MAX_OFF]:     # bỏ khung không còn dùng làm lân cận
                del frames[old]
                actives.pop(old, None)
            if progress and stats['written'] % 60 == 0:
                progress(min(1.0, stats['written'] / total))

    def submit(k):
        win = {j: frames[j] for j in range(k - MAX_OFF, k + MAX_OFF + 1) if j in frames}
        pending.append((k, fill_pool.submit(_clean_frame, k, win, w, h, actives.get(k) or {})))

    try:
        (read_n, next_submit) = (0, 0)
        while True:
            if should_stop and should_stop():
                return None
            raw = dec.stdout.read(size)
            if len(raw) < size:
                break
            t = read_n / fps
            near = active_at(t, pad)
            frames[read_n] = (raw, mask_pool.submit(_masks, raw, w, h, near, templates) if near else _Done({}))
            actives[read_n] = active_at(t)
            read_n += 1
            while next_submit <= read_n - 1 - MAX_OFF:   # đủ khung phía sau làm lân cận
                submit(next_submit)
                next_submit += 1
            flush()
        while next_submit < read_n:
            submit(next_submit)
            next_submit += 1
        flush(force=True)
        ok = True
    except (BrokenPipeError, OSError) as e:
        log(f'   [WARN] Xoá nét chữ lỗi: {e}')
    finally:
        fill_pool.shutdown(wait=False, cancel_futures=True)
        mask_pool.shutdown(wait=False, cancel_futures=True)
        try:
            enc.stdin.close()
        except OSError:
            pass
        enc.wait()
        if dec.poll() is None:
            dec.kill()
        unregister_process(dec)
        unregister_process(enc)
    if not ok or enc.returncode != 0:
        log('   [WARN] Không tạo được video sạch chữ: ' + (enc.stderr.read().decode('utf-8', 'replace')[-300:] if enc.stderr else ''))
        return None
    log(f"   Xoá sạch nét chữ: {stats['touched']} lượt vùng chữ trên {stats['written']} khung hình (lấp bằng khung lân cận + Telea)")
    return out_path
