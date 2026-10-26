"""
Scene detector: tim DIEM CAT CANH THAT trong video bang PySceneDetect (ContentDetector).

Muc dich (xem PROGRESS.md): de chia phim thanh cac chuong canh lien tuc theo dung ranh
gioi hinh anh that — thay vi cat theo timestamp uoc luong cua Gemini (co the roi vao GIUA
mot canh, lam loi doc lech hinh). Day chi la MOT buoc phu tro: viec chia chuong + tom tat
Gemini Vision + gop outline van do story_analyzer + pipeline dam nhan.

AN TOAN TUYET DOI: thieu lib scenedetect / video loi / khong doc duoc -> tra ve [] + log
canh bao, KHONG raise. Pipeline se tu roi ve hanh vi cu (_build_scenes_from_beats), khong
lam gay ban on dinh ma khach dang dung.
"""
import subprocess
LAST_FALLBACK_REASON = None
def _detect_ffmpeg(video_path, threshold, width=320):
    """Dò cắt cảnh nhanh: ffmpeg giải mã ĐA LUỒNG + thu nhỏ 320px → đưa từng khung cho đúng bộ dò ContentDetector của
    PySceneDetect. Nhanh hơn ~4× so với để PySceneDetect tự giải mã đủ 1080p 1 luồng (12.4s → 2.9s mỗi phút phim), ra cùng
    các điểm cắt (đã đối chiếu 22/22, lệch tối đa 1 khung hình). Lỗi → None (dùng cách cũ)."""
    import numpy as np
    from scenedetect import ContentDetector, FrameTimecode
    from .utils import FFMPEG_EXE, FFPROBE_EXE, _HIDE, _budgeted, register_process, unregister_process
    r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,avg_frame_rate,r_frame_rate',
                        '-of', 'default=nw=1', video_path], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE, timeout=30)
    info = dict(l.split('=', 1) for l in r.stdout.splitlines() if '=' in l)
    (w0, h0) = (int(info.get('width') or 0), int(info.get('height') or 0))

    def _rate(v):
        (a, _, b) = str(v or '0/1').partition('/')
        return float(a) / float(b or 1) if float(b or 1) else 0.0
    fps = _rate(info.get('avg_frame_rate')) or _rate(info.get('r_frame_rate'))
    if not w0 or not h0 or not fps or fps > 240:
        return None
    (W, H) = (width, max(2, int(round(h0 * width / w0 / 2)) * 2))
    cmd = _budgeted([FFMPEG_EXE, '-v', 'error', '-i', video_path, '-an', '-sn', '-vf', f'scale={W}:{H}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'])
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_HIDE)
    register_process(p)
    det = ContentDetector(threshold=threshold)
    (cuts, n, size) = ([], 0, W * H * 3)
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            for c in det.process_frame(FrameTimecode(n, fps), np.frombuffer(buf, np.uint8).reshape(H, W, 3)) or []:
                cuts.append(c.get_seconds() if hasattr(c, 'get_seconds') else float(c) / fps)
            n += 1
        p.wait()
    finally:
        unregister_process(p)
    if p.returncode != 0 or n < 2:
        return None
    return [round(t, 2) for t in cuts if t > 0.05]


def detect_scene_cuts(video_path, log_fn=print, threshold=27.0):
    global LAST_FALLBACK_REASON
    LAST_FALLBACK_REASON = None
    if not video_path:
        LAST_FALLBACK_REASON = 'no_cuts'
        return []
    try:
        from scenedetect import detect, ContentDetector
    except Exception as e:
        log_fn(f'''   [WARN] Không nạp được PySceneDetect ({str(e)[slice(None, 80, None)]}) — bỏ qua cắt cảnh thật, dùng timestamp Gemini như cũ.''')
        LAST_FALLBACK_REASON = 'missing_lib'
        return []
    try:
        cuts_fast = _detect_ffmpeg(video_path, threshold)
        if cuts_fast is not None:
            cuts_fast = sorted(set(cuts_fast))
            log_fn(f'''   [SceneCut] PySceneDetect tìm được {len(cuts_fast)} điểm cắt cảnh thật.''' if cuts_fast
                   else '   [SceneCut] Không tìm thấy điểm cắt cảnh rõ ràng (video phẳng/tĩnh) — sẽ dùng timestamp Gemini.')
            if not cuts_fast:
                LAST_FALLBACK_REASON = 'no_cuts'
            return cuts_fast
        scene_list = detect(video_path, ContentDetector(threshold=threshold))
    except Exception as e:
        log_fn(f'''   [WARN] PySceneDetect lỗi khi phân tích video ({str(e)[slice(None, 100, None)]}) — dùng timestamp Gemini như cũ.''')
        LAST_FALLBACK_REASON = 'detect_error'
        return []
    cuts = []
    try:
        for (start, _end) in scene_list:
            s = float(start.get_seconds())
            if s > 0.05:
                cuts.append(round(s, 2))
    except Exception as e:
        log_fn(f'''   [WARN] Lọc điểm cắt cảnh lỗi ({str(e)[slice(None, 80, None)]}) — dùng timestamp Gemini như cũ.''')
        LAST_FALLBACK_REASON = 'detect_error'
        return []
    cuts = sorted(set(cuts))
    if cuts:
        log_fn(f'''   [SceneCut] PySceneDetect tìm được {len(cuts)} điểm cắt cảnh thật.''')
    else:
        log_fn('   [SceneCut] Không tìm thấy điểm cắt cảnh rõ ràng (video phẳng/tĩnh) — sẽ dùng timestamp Gemini.')
        LAST_FALLBACK_REASON = 'no_cuts'
    return cuts