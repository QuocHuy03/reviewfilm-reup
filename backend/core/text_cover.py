"""Tự tìm mọi chữ tiếng Trung hiện trên video (phụ đề cứng, dải tiêu đề, chữ chèn…) để làm mờ.

Cách làm: lấy mẫu khung hình (mỗi `interval` giây) → RapidOCR tìm vị trí dòng chữ → đọc chữ ở dòng MỚI
(dòng nằm đúng chỗ đã xác nhận là chữ Trung thì không đọc lại — nhanh hơn ~3 lần) → gộp các lần xuất hiện
liên tiếp thành vùng che có thời gian. Kết quả theo % hình GỐC + giây trên video gốc, lưu cache theo file video.
"""
import hashlib
import json
import os
import re
import subprocess
import threading

from .utils import FFMPEG_EXE, FFPROBE_EXE, _HIDE

CJK = re.compile(r'[㐀-鿿豈-﫿぀-ヿ]')   # Hán tự + kana
SCAN_WIDTH = 640                 # đủ rõ để tìm chữ phụ đề, nhanh hơn 960px
_ocr = None
_ocr_lock = threading.Lock()


def _engine():
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
        return _ocr


def available():
    import importlib.util
    return importlib.util.find_spec('rapidocr_onnxruntime') is not None


def _probe(path):
    r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height:format=duration',
                        '-of', 'json', path], capture_output=True, text=True, creationflags=_HIDE)
    d = json.loads(r.stdout or '{}')
    s = (d.get('streams') or [{}])[0]
    return int(s.get('width') or 0), int(s.get('height') or 0), float((d.get('format') or {}).get('duration') or 0)


def _merge_ranges(ranges, dur):
    out = []
    for (a, b) in sorted((max(0.0, a), min(dur, b)) for (a, b) in ranges if b > a):
        if b <= a:
            continue
        if out and a <= out[-1][1] + 1.0:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _cache_path(video, interval):
    """1 file cache / video + khoảng quét: lưu các đoạn ĐÃ quét và mọi chữ Trung tìm được → lần sau chỉ quét phần thiếu."""
    from app.config import DATA_DIR
    st = os.stat(video)
    key = json.dumps([os.path.abspath(video), st.st_size, int(st.st_mtime), interval, 3])
    d = os.path.join(DATA_DIR, 'text_scan')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.md5(key.encode()).hexdigest()[:20] + '.json')


def _subtract(ranges, scanned, interval):
    """Các đoạn trong `ranges` chưa nằm trong `scanned` (bỏ qua mẩu ngắn hơn 1 khoảng quét)."""
    out = []
    for (a, b) in ranges:
        cur = a
        for (sa, sb) in sorted(scanned):
            if sb <= cur or sa >= b:
                continue
            if sa > cur:
                out.append([cur, sa])
            cur = max(cur, sb)
        if b - cur >= interval:
            out.append([cur, b])
    return out


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _same_band(a, b):
    """Cùng dải ngang (vd vị trí phụ đề): chồng dọc ≥ 60% dòng thấp hơn và có chồng ngang."""
    oy = min(a[3], b[3]) - max(a[1], b[1])
    ox = min(a[2], b[2]) - max(a[0], b[0])
    return oy >= 0.6 * min(a[3] - a[1], b[3] - b[1]) and ox > -0.05


def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _tracks(dets, interval):
    """Gộp các lần thấy chữ theo thời gian → vùng có thời gian. Chỉ nối khi đúng là CÙNG dòng chữ còn đứng đó
    (chồng khít khung lần thấy trước, cách nhau ≤ 1.6 lần khoảng quét). Trước gộp cả "cùng dải": câu phụ đề / chữ khác
    nhau hiện nối tiếp ở gần nhau bị cộng dồn thành 1 khối to (vd góc trái 50% × 20% khung) che suốt cả phim."""
    tracks = []
    for (t, box) in sorted(dets, key=lambda x: x[0]):
        best = None
        for tr in tracks:
            gap = t - tr['last']
            if gap > interval * 2.6 + 1e-6:
                continue
            same = _iou(box, tr['prev']) > 0.45 or _iou(box, tr['box']) > 0.6
            # cùng chỗ → nối qua 1 lần quét hụt (OCR bỏ sót 1 khung → trước lộ chữ ~1 khoảng quét giữa 2 câu phụ đề)
            if not same or (gap > interval * 1.6 + 1e-6 and _iou(box, tr['prev']) < 0.6):
                continue
            u = [min(tr['box'][0], box[0]), min(tr['box'][1], box[1]), max(tr['box'][2], box[2]), max(tr['box'][3], box[3])]
            if _area(u) > 1.5 * max(_area(tr['box']), _area(box)):
                continue            # khung rung / nhích dần không được kéo vùng phình mãi
            score = _iou(box, tr['prev'])
            if best is None or score > best[0]:
                best = (score, tr, u)
        if best:
            (_, tr, u) = best
            (tr['box'], tr['prev'], tr['last']) = (u, list(box), t)
        else:
            tracks.append({'box': list(box), 'prev': list(box), 'first': t, 'last': t})
    return tracks


def scan(video, ranges=None, interval=1.0, log_fn=print, should_stop=None, progress=None):
    """→ [{'box': [x1, y1, x2, y2] (0-1, hình gốc), 't_start', 't_end' (giây video gốc)}]."""
    import numpy as np
    (sw, sh, dur) = _probe(video)
    if not sw or not sh or dur <= 0:
        log_fn('   [WARN] Quét chữ: không đọc được thông tin video — bỏ qua')
        return []
    # căn theo lưới khoảng quét → các lần gọi khác nhau lấy mẫu đúng cùng mốc giây, dùng lại được cache
    ranges = _merge_ranges([(int(a // interval) * interval, (int(b // interval) + 1) * interval) for (a, b) in (ranges or [(0.0, dur)])], dur)
    cache = _cache_path(video, interval)
    (scanned, dets) = ([], [])                      # dets: (t, box)
    try:
        with open(cache, encoding='utf-8') as f:
            c = json.load(f)
        (scanned, dets) = (c.get('scanned') or [], [(d[0], d[1:5]) for d in c.get('dets') or []])
    except (OSError, ValueError):
        pass
    todo_ranges = _subtract(ranges, scanned, interval)
    if not todo_ranges:
        log_fn('   Quét chữ Trung: dùng lại kết quả đã quét')
    W = SCAN_WIDTH
    H = max(2, int(round(sh * W / sw / 2)) * 2)
    total = sum(int((b - a) / interval) + 1 for (a, b) in todo_ranges)
    if total:
        log_fn(f'   Quét chữ Trung trên video: ~{total} khung hình (mỗi {interval:g} giây)...')
    ocr = _engine() if total else None
    bands = []         # [box, t_last] dải đã xác nhận là chữ Trung
    done = 0
    for (a, b) in todo_ranges:
        cmd = [FFMPEG_EXE, '-v', 'error', '-ss', f'{a:.3f}', '-t', f'{b - a:.3f}', '-i', video,
               '-vf', f'fps=1/{interval},scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-']
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_HIDE)
        k = 0
        try:
            while True:
                if should_stop and should_stop():
                    proc.kill()
                    log_fn('   Quét chữ: đã huỷ')
                    return []
                raw = proc.stdout.read(W * H * 3)
                if len(raw) < W * H * 3:
                    break
                t = a + k * interval
                k += 1
                done += 1
                if progress:
                    progress(done, total)
                img = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
                det, _ = ocr(img, use_det=True, use_cls=False, use_rec=False)
                todo = []
                for poly in det or []:
                    p = np.asarray(poly, dtype=float)
                    box = [p[:, 0].min() / W, p[:, 1].min() / H, p[:, 0].max() / W, p[:, 1].max() / H]
                    if (box[3] - box[1]) < 0.012 or (box[2] - box[0]) < 0.02 or (box[3] - box[1]) > 0.16:
                        continue            # vụn quá nhỏ / khối quá cao (không phải dòng chữ)
                    known = any(_same_band(box, bb) and t - tl <= 15 for (bb, tl) in bands)
                    if known:
                        dets.append((t, box))
                        for band in bands:
                            if _same_band(box, band[0]):
                                band[1] = t
                    else:
                        todo.append(box)
                if todo:
                    crops = [img[max(0, int(bx[1] * H)):int(bx[3] * H) + 1, max(0, int(bx[0] * W)):int(bx[2] * W) + 1] for bx in todo]
                    (rec, _) = ocr.text_rec(crops)
                    for (bx, (txt, sc)) in zip(todo, rec):
                        if sc > 0.45 and CJK.search(txt or ''):
                            dets.append((t, bx))
                            bands.append([bx, t])
                if done % max(1, total // 10) == 0:
                    log_fn(f'   Quét chữ: {done}/{total} khung')
        finally:
            if proc.poll() is None:
                proc.kill()
        scanned = _merge_ranges(scanned + [[a, b]], dur)
        try:                                         # lưu sau mỗi đoạn — huỷ giữa chừng vẫn giữ phần đã quét
            with open(cache, 'w', encoding='utf-8') as f:
                json.dump({'scanned': scanned, 'dets': [[round(t, 2), *[round(float(v), 4) for v in bx]] for (t, bx) in dets]}, f)
        except OSError:
            pass
    # chỉ lấy chữ trong các đoạn cần (cache có thể chứa đoạn khác của cùng video)
    dets = [(t, bx) for (t, bx) in dets if bx[3] - bx[1] <= 0.16 and any(a - interval <= t <= b + interval for (a, b) in ranges)]
    tracks = _tracks(dets, interval)
    regions = []
    for tr in tracks:
        (x1, y1, x2, y2) = tr['box']
        (ph, pw) = ((y2 - y1) * 0.35, (y2 - y1) * 0.5)          # nới lề cho kín viền chữ
        regions.append({'box': [round(float(v), 4) for v in (max(0.0, x1 - pw), max(0.0, y1 - ph), min(1.0, x2 + pw), min(1.0, y2 + ph))],
                        't_start': round(max(0.0, tr['first'] - interval * 0.6), 2), 't_end': round(min(dur, tr['last'] + interval * 0.6), 2)})
    log_fn(f'   Quét chữ Trung xong: {len(regions)} vùng chữ sẽ được làm mờ')
    return regions


def subtitle_band(regions, min_center=0.55):
    """Dải phụ đề cứng (theo hình gốc, 0-1) từ các vùng chữ đã quét: chỉ vùng nửa dưới, trọng số theo thời gian hiện.
    → [x1, y1, x2, y2] đã nới lề cho trùm kín cả dòng cao / dòng thấp, hoặc None nếu không thấy phụ đề."""
    rows = [(r['box'], max(0.1, float(r['t_end']) - float(r['t_start']))) for r in regions or []
            if (r['box'][1] + r['box'][3]) / 2 >= min_center]
    if not rows:
        return None

    def wpct(vals, q):
        pairs = sorted(vals)
        total = sum(w for (_, w) in pairs)
        acc = 0.0
        for (v, w) in pairs:
            acc += w
            if acc >= q * total:
                return v
        return pairs[-1][0]
    y1 = wpct([(b[1], w) for (b, w) in rows], 0.08)
    y2 = wpct([(b[3], w) for (b, w) in rows], 0.92)
    x1 = wpct([(b[0], w) for (b, w) in rows], 0.05)
    x2 = wpct([(b[2], w) for (b, w) in rows], 0.95)
    hgt = max(0.02, y2 - y1)
    (y1, y2) = (max(0.0, y1 - hgt * 0.12), min(1.0, y2 + hgt * 0.12))
    (x1, x2) = (max(0.0, x1 - 0.03), min(1.0, x2 + 0.03))
    return [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)]


def sample_ranges(dur, n=24, length=1.0):
    """n đoạn ngắn rải đều cả phim (bỏ 5% đầu/cuối — thường là intro/outro) để dò nhanh vị trí phụ đề."""
    if dur <= 0:
        return []
    (a, b) = (dur * 0.05, dur * 0.95)
    step = (b - a) / max(1, n)
    return [(a + i * step, min(dur, a + i * step + length)) for i in range(n)]
