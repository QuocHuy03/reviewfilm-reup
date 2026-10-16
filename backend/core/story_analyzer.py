
"""
Story analyzer: dung KE HOACH CHUONG CANH cho toan bo phim + Map-Reduce Vision AI rieng
tung chuong (xem PROGRESS.md).

Muc tieu cot loi:
  Chia TOAN BO phim thanh cac chuong canh LIEN TUC, PHU KIN, KHONG BO SOT canh nao
  (build_scene_plan), roi voi MOI chuong goi lai Vision AI RIENG de sinh tom tat CHINH XAC
  cho dung chuong do (analyze_scenes_with_vision — Map), gop tat ca theo thu tu thanh 1
  outline mach lac cho ca phim (Reduce). Day moi la cach AI hieu DUNG toan bo phim, thay vi
  chi doan qua vai chuc khung hinh mau chung cho ca phim nhu cach cu.

Vai tro cua diem cat canh that (real_cuts tu scene_detector) chi la buoc PHU TRO: neo ranh
gioi chuong canh vao dung cho video cat hinh, tranh clip roi vao giua mot canh — TU THAN no
KHONG giai quyet duoc muc tieu cot loi neu thieu buoc Map-Reduce Vision AI ben tren.

Neu real_cuts RONG (thieu lib scenedetect / video phang) -> build_scene_plan tu lam Y HET
thuat toan cu (_build_scenes_from_beats) de KHONG pha vo hanh vi on dinh khi thieu lib; buoc
Map-Reduce Vision AI van chay binh thuong tren ket qua do (khong phu thuoc scenedetect).
"""
import os
import re
import json
import math
import subprocess
def build_scene_plan(plot_beats, real_cuts, video_duration, target_minutes, log_fn=print):
    from .script_writer import _build_scenes_from_beats, _safe_float, MAX_SCENES, MIN_SCENE_SECONDS, HARD_MAX_SCENES_V2
    video_duration = _safe_float(video_duration, 0.0)
    cuts = sorted({round(_safe_float(c), 1) for c in real_cuts or [] if 0.0 < _safe_float(c) < video_duration})
    if not cuts:
        log_fn('   [SceneV2] Không có điểm cắt cảnh thật -> dùng thuật toán chia cảnh cũ.')
        return _build_scenes_from_beats(plot_beats, video_duration, target_minutes)
    if video_duration <= 0:
        raise ValueError(f'''video_duration khong hop le ({video_duration}) — khong the tao scenes.''')
    min_scenes = int(min(MAX_SCENES, max(4, min(max(6, target_minutes * 5), int(video_duration / MIN_SCENE_SECONDS)))))
    _gap_target = max(MIN_SCENE_SECONDS, MIN_SCENE_SECONDS * math.sqrt(max(video_duration, 1.0) / 900.0))
    scene_cap = min(HARD_MAX_SCENES_V2, max(min_scenes, int(video_duration / _gap_target)))
    bounds = sorted({0.0, *cuts, round(float(video_duration), 1)})
    bounds = _thin_bounds(bounds, MIN_SCENE_SECONDS)
    if len(bounds) - 1 > scene_cap:
        bounds = _thin_bounds(bounds, max(MIN_SCENE_SECONDS, video_duration / scene_cap))
    if len(bounds) - 1 < min_scenes:
        bounds = _split_bounds(bounds, min_scenes)
    beats = sorted(({'t': _safe_float(b.get('timestamp', 0)), 'd': ((b.get('description') or '')).strip()} for b in plot_beats or [] if isinstance(b, dict)), key=lambda x: x['t'])
    scenes = []
    for i in range(len(bounds) - 1):
        start = round(bounds[i], 1)
        end = round(min(bounds[i + 1], float(video_duration)), 1)
        if end - start < 2.0 and scenes:
            scenes[-1]['clip_end'] = end
            continue
        desc = _describe_segment(start, end, beats)
        scenes.append({'clip_start': start, 'clip_end': end, 'description': desc or f'''Canh {len(scenes) + 1}'''})
    log_fn(f'''   [SceneV2] {len(cuts)} điểm cắt thật -> {len(scenes)} chương cảnh phủ kín toàn phim (mục tiêu {min_scenes}, trần {scene_cap}).''')
    return scenes
def _thin_bounds(bounds, min_gap):
    if len(bounds) <= 2:
        return list(bounds)
    kept = [bounds[0]]
    for b in bounds[slice(1, -1, None)]:
        if b - kept[-1] >= min_gap:
            kept.append(b)
    last = bounds[-1]
    if last - kept[-1] < min_gap and len(kept) > 1:
        kept[-1] = last
    else:
        kept.append(last)
    return kept
def _split_bounds(bounds, target):
    bounds = list(bounds)
    guard = 0
    while len(bounds) - 1 < target and guard < 500:
        guard += 1
        idx = max(range(len(bounds) - 1), key=lambda i: bounds[i + 1] - bounds[i])
        seg = bounds[idx + 1] - bounds[idx]
        if seg < 2.0:
            break
        mid = round((bounds[idx] + bounds[idx + 1]) / 2.0, 1)
        if mid <= bounds[idx] or mid >= bounds[idx + 1]:
            break
        bounds.insert(idx + 1, mid)
    return bounds
def _describe_segment(start, end, beats):
    inside = [b['d'] for b in beats if start <= b['t'] < end and b['d']]
    if inside:
        seen = []
        for d in inside:
            if d not in seen:
                seen.append(d)
        joined = ' '.join(seen)
        return joined[slice(None, 400, None)]
    if beats:
        nearest = min(beats, key=lambda b: min(abs(b['t'] - end), abs(b['t'] - start)))
        return nearest['d']
    return ''
def analyze_scenes_with_vision(scenes_meta, video_path, openai_key, temp_dir, log_fn=print, quality='standard', film_context='', char_glossary=None):
    from .gemini_analyzer import _vision_dispatch, _clean_json_newlines, vision_available
    if not vision_available('', openai_key):
        log_fn('   [Map] Chưa có key Vision / tài khoản Gemini web -> không thể phân tích Vision AI riêng từng chương, giữ dàn ý/tóm tắt cũ (chất lượng như bản V1).')
        return ''
    if not scenes_meta:
        return ''
    frames_dir = os.path.join(temp_dir, 'chapter_frames')
    os.makedirs(frames_dir, exist_ok=True)
    ctx_block = ''
    _fc = ((film_context or '')).strip()
    if _fc:
        ctx_block += f'''BỐI CẢNH PHIM DO NGƯỜI DÙNG CUNG CẤP (ƯU TIÊN TUYỆT ĐỐI — bám đúng tên phim/nhân vật dưới đây, chỉ dùng hình ảnh+thoại để xác định diễn biến, không suy diễn khác đi):\n"{_fc}"\n\n'''
    if char_glossary:
        ctx_block += 'BẢNG TÊN NHÂN VẬT CHÍNH XÁC (dùng đúng tên này khi mô tả nhân vật, không tự đặt tên khác):\n' + ''.join((f'''- \'{e.get('src', '')}\' → \'{e.get('vi', '')}\'\n''' for e in char_glossary[slice(None, 8, None)])) + '\n'
    n = len(scenes_meta)
    ok_count = 0
    fail_count = 0
    outline_parts = []
    recent_summaries = []
    log_fn(f'''   [Map] Bắt đầu phân tích Vision AI riêng cho {n} chương cảnh (Map-Reduce)...''')
    for (i, scene) in enumerate(scenes_meta):
        cs = scene['clip_start']
        ce = scene['clip_end']
        dur = max(0.1, ce - cs)
        n_frames = 2 if dur <= 20 else 3 if dur <= 45 else 4
        frames = _extract_chapter_frames(video_path, frames_dir, cs, ce, n_frames, i, log_fn)
        if not frames:
            log_fn(f'''   [Map] [WARN] Chương {i + 1}/{n} ({cs:.1f}s-{ce:.1f}s): không trích được khung hình -> giữ mô tả cũ.''')
            fail_count += 1
            outline_parts.append(scene.get('description', ''))
            continue
        dial =((scene.get('_transcript') or '')).strip()
        dial_block = f'''\nTHOẠI GỐC (Whisper) TRONG ĐOẠN NÀY: "{dial}"''' if dial else ''
        prev_block = ''
        if recent_summaries:
            prev_block = '''DIỄN BIẾN NGAY TRƯỚC ĐOẠN NÀY (để mô tả nối mạch, gọi tên nhân vật NHẤT QUÁN với các đoạn trước — nhưng KHÔNG kể lại nội dung cũ):
''' + '\n'.join((f'''- {s}''' for s in recent_summaries[slice(-2, None, None)])) + '\n\n'
        prompt = f'''Bạn là chuyên gia phân tích phim. Đây là {len(frames)} khung hình trích xuất LIÊN TỤC từ giây {cs:.1f} đến giây {ce:.1f} của một bộ phim (đúng MỘT đoạn cảnh, không xen lẫn cảnh khác).{dial_block}\n\n{ctx_block}{prev_block}Hãy mô tả CHÍNH XÁC diễn biến/hành động đang xảy ra trong đoạn này — bám sát hình ảnh và thoại thực tế ở trên. TUYỆT ĐỐI KHÔNG suy diễn hay bịa thêm tình tiết không có trong hình/thoại. Nếu nhận ra nhân vật nào trong bối cảnh/bảng tên/diễn biến trước thì gọi đúng tên đó. Nếu khung hình chỉ là logo hãng phim/màn hình thông tin sản xuất/màn đen chuyển cảnh thì trả về summary là "(logo/intro sản xuất)".\n\nTrả về JSON thuần túy đúng schema sau (chỉ JSON, không thêm chữ nào khác):\n{{"summary": "mô tả diễn biến của đúng đoạn này bằng tiếng Việt, hai đến bốn câu, đủ chi tiết để hiểu đúng chuyện gì đang xảy ra"}}'''
        text = _vision_dispatch(prompt, frames, '', openai_key, log_fn, detail='low', temperature=0.3, max_tokens=500, quality=quality)
        desc = _parse_chapter_summary(text, _clean_json_newlines)
        if desc:
            scene['description'] = desc
            outline_parts.append(desc)
            if '(logo/intro' not in desc:
                recent_summaries.append(desc)
            ok_count += 1
        else:
            log_fn(f'''   [Map] [WARN] Chương {i + 1}/{n} ({cs:.1f}s-{ce:.1f}s): Vision AI không trả về được mô tả -> giữ mô tả cũ.''')
            fail_count += 1
            outline_parts.append(scene.get('description', ''))
        if (i + 1) % 5 == 0 or i == n - 1:
            log_fn(f'''   [Map] Đã phân tích {i + 1}/{n} chương cảnh...''')
    if ok_count == 0:
        log_fn('   [Map] Không chương nào phân tích Vision AI thành công -> giữ dàn ý/tóm tắt cũ.')
        return ''
    log_fn(f'''   [Map-Reduce] Đã phân tích Vision AI riêng cho {ok_count}/{n} chương cảnh -> gộp thành dàn ý đầy đủ cho cả phim.''' + (f''' ({fail_count} chương lỗi, đã giữ mô tả cũ.)''' if fail_count else ''))
    return '\n'.join((p for p in outline_parts if p))
def _parse_chapter_summary(text, clean_json_newlines):
    if not text:
        return ''
    try:
        cleaned = re.sub('^```(?:json)?\\s*|\\s*```$', '', text.strip())
        cleaned = clean_json_newlines(cleaned)
        data = json.loads(cleaned)
        return ((data.get('summary') or '')).strip()
    except Exception:
        pass
    m = re.search('"summary"\\s*:\\s*"([\\s\\S]+?)"\\s*\\}', text)
    if m:
        return m.group(1).strip().replace('\\n', '\n').replace('\\"', '"')
    return ''
def _extract_chapter_frames(video_path, out_dir, start_ts, end_ts, n_frames, chapter_idx, log_fn=print):
    from .utils import FFMPEG_EXE, _HIDE
    frames = []
    span = max(0.0, end_ts - start_ts)
    if span <= 0:
        return frames
    step = span / max(1, n_frames + 1)
    for k in range(1, n_frames + 1):
        ts = start_ts + step * k
        out_path = os.path.join(out_dir, f'''chap_{chapter_idx:03d}_{k:02d}.jpg''')
        cmd = [FFMPEG_EXE, '-y', '-ss', str(ts), '-i', video_path, '-frames:v', '1', '-q:v', '3', '-vf', 'scale=640:-1', out_path]
        try:
            r = subprocess.run(cmd, capture_output=True, creationflags=_HIDE, timeout=30)
            if r.returncode == 0:
                if os.path.exists(out_path):
                    frames.append((ts, out_path))
        except Exception:
            pass
    return frames