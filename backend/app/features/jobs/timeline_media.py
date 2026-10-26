"""Dữ liệu cho timeline chỉnh tay (Dịch phụ đề): sóng âm + điểm chuyển cảnh của video gốc.

Tính 1 lần rồi lưu cache theo file video (đường dẫn + cỡ + giờ sửa) → mở lại / sửa lại job khác cùng video là có ngay.
Chạy theo ngân sách CPU chung (ffmpeg ưu tiên thấp) như mọi bước nặng khác.
"""
import base64
import hashlib
import json
import os
import subprocess
import threading

from app.config import DATA_DIR

CACHE_DIR = os.path.join(DATA_DIR, 'cache', 'timeline')
PEAKS_PER_SEC = 50          # 20 ms / điểm — đủ mịn để canh mép phụ đề (Aegisub / Subtitle Edit dùng mức tương tự)
_SR = 8000
_locks = {}
_glock = threading.Lock()


def _cache_path(video, kind):
    st = os.stat(video)
    h = hashlib.sha1(f'{os.path.abspath(video).lower()}|{st.st_size}|{int(st.st_mtime)}'.encode()).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f'{h}.{kind}.json')


def _cached(video, kind, build):
    """1 lần tính / video / loại — 2 yêu cầu cùng lúc thì yêu cầu sau chờ rồi đọc cache, không tính trùng."""
    path = _cache_path(video, kind)
    with _glock:
        lock = _locks.setdefault(path, threading.Lock())
    with lock:
        if os.path.isfile(path):
            try:
                with open(path, encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        data = build(video)
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp, path)
        return data


def _build_peaks(video):
    """Đỉnh âm lượng mỗi 20 ms (0-255, base64). Đọc luồng từng khúc → phim 2 tiếng cũng chỉ tốn vài MB RAM."""
    import numpy as np
    from core.utils import FFMPEG_EXE, _HIDE, _budgeted
    hop = _SR // PEAKS_PER_SEC
    chunk = hop * PEAKS_PER_SEC * 20                      # 20 giây / lần đọc
    # chỉ dải tần giọng nói (250-3400 Hz): bass / trống của nhạc nền bị bỏ → chỗ có lời nổi rõ hơn
    cmd = _budgeted([FFMPEG_EXE, '-v', 'error', '-i', video, '-vn', '-sn', '-dn', '-ac', '1', '-af', 'highpass=f=250,lowpass=f=3400',
                     '-ar', str(_SR), '-f', 's16le', '-'])
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_HIDE)
    out = []
    rest = np.zeros(0, np.int16)
    try:
        while True:
            buf = p.stdout.read(chunk * 2)
            if not buf:
                break
            a = np.concatenate([rest, np.frombuffer(buf[: len(buf) // 2 * 2], np.int16)])
            n = a.size // hop
            if n:
                out.append(np.abs(a[: n * hop].astype(np.int32)).reshape(n, hop).max(axis=1))
            rest = a[n * hop:]
        p.wait()
    finally:
        if p.poll() is None:
            p.kill()
    if not out:
        return {'rate': PEAKS_PER_SEC, 'n': 0, 'peaks': ''}
    pk = np.concatenate(out).astype(np.float32)
    # trừ "nền" (nhạc / tiếng ồn đều đều, ~mức 30% thấp nhất trong 3s quanh đó) → khoảng lặng thoại xuống thấp, lời nói nổi lên
    k = PEAKS_PER_SEC * 3
    pad = np.pad(pk, (k // 2, k - k // 2 - 1), mode='edge')
    win = np.lib.stride_tricks.sliding_window_view(pad, k)[:, ::5]
    floor = np.percentile(win, 30, axis=1)
    sig = np.clip(pk - floor * 0.9, 0, None)
    ref = max(1.0, float(np.percentile(sig, 99.5)))      # bỏ vài tiếng nổ lớn
    v = np.sqrt(np.clip(sig / ref, 0, 1))                 # cong căn bậc 2: lời nói nhỏ vẫn nhìn thấy
    return {'rate': PEAKS_PER_SEC, 'n': int(v.size), 'peaks': base64.b64encode((v * 255).astype(np.uint8).tobytes()).decode()}


def _build_shots(video):
    from core.scene_detector import _detect_ffmpeg
    try:
        cuts = _detect_ffmpeg(video, 27.0)
    except Exception:
        cuts = None
    if cuts is None:
        cuts = _shots_numpy(video)
    return {'cuts': sorted(set(cuts or []))}


def _shots_numpy(video, threshold=27.0, min_frames=15):
    """Dự phòng khi thiếu PySceneDetect: cùng công thức ContentDetector (trung bình chênh H, S, V giữa 2 khung liền nhau,
    ≥ ngưỡng và cách lần cắt trước ≥ 15 khung = chuyển cảnh), giải mã 160px qua ffmpeg."""
    try:
        import cv2
        import numpy as np
        from core.utils import FFMPEG_EXE, FFPROBE_EXE, _HIDE, _budgeted
        r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,avg_frame_rate',
                            '-of', 'default=nw=1', video], capture_output=True, text=True, creationflags=_HIDE, timeout=30)
        info = dict(l.split('=', 1) for l in r.stdout.splitlines() if '=' in l)
        (a, _, b) = info.get('avg_frame_rate', '0/1').partition('/')
        fps = float(a) / float(b or 1) if float(b or 1) else 0
        (w0, h0) = (int(info.get('width') or 0), int(info.get('height') or 0))
        if not (fps and w0 and h0) or fps > 240:
            return []
        (W, H) = (160, max(2, int(round(h0 * 160 / w0 / 2)) * 2))
        p = subprocess.Popen(_budgeted([FFMPEG_EXE, '-v', 'error', '-i', video, '-an', '-sn', '-vf', f'scale={W}:{H}:flags=area',
                                        '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-']), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_HIDE)
        (size, prev, n, last, cuts) = (W * H * 3, None, 0, -min_frames, [])
        try:
            while True:
                buf = p.stdout.read(size)
                if len(buf) < size:
                    break
                hsv = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(H, W, 3), cv2.COLOR_BGR2HSV).astype(np.int16)
                if prev is not None:
                    score = float(np.abs(hsv - prev).reshape(-1, 3).mean(axis=0).mean())
                    if score >= threshold and n - last >= min_frames:
                        cuts.append(round(n / fps, 2))
                        last = n
                prev = hsv
                n += 1
            p.wait()
        finally:
            if p.poll() is None:
                p.kill()
        return [t for t in cuts if t > 0.05]
    except Exception:
        return []


def waveform(video):
    return _cached(video, 'peaks2', _build_peaks)


def shots(video):
    return _cached(video, 'shots', _build_shots)
