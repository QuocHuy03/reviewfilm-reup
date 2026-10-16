
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
LAST_FALLBACK_REASON = None
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