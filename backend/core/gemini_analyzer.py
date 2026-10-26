

"""
Phân tích nội dung phim qua khung hình chính + lời thoại.
Giữ tên module / chữ ký hàm cũ cho tương thích; chạy bằng tài khoản Gemini đăng nhập trong app.
"""
import os
import subprocess
import json
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.utils import FFMPEG_EXE, FFPROBE_EXE, _HIDE
def _clean_json_newlines(s):
    result = []
    in_quotes = False
    escape = False
    for c in s:
        if escape:
            result.append(c)
            escape = False
            continue
        if c == '\\':
            result.append(c)
            escape = True
            continue
        if c == '"':
            in_quotes = not in_quotes
            result.append(c)
            continue
        if c == '\n' and in_quotes:
            result.append('\\n')
            continue
        result.append(c)
    return ''.join(result)
def _vision_dispatch(prompt, frames, gemini_key, openai_key, log_fn, detail='low', temperature=0.3, max_tokens=6000, quality='standard'):
    """Phân tích khung hình = tài khoản Gemini đăng nhập trong app."""
    from core import web_llm
    return web_llm.gemini_vision(prompt, frames, log_fn) if web_llm.gemini_ready() else ''
def vision_available(gemini_key='', openai_key=''):
    from core import web_llm
    return web_llm.gemini_ready()
def analyze_video(video_path, transcript, gemini_key, temp_dir, max_frames=16, log_fn=print, openai_key='', quality='standard', film_context=''):
    openai_key = ((openai_key or '')).strip()
    if not vision_available(gemini_key, openai_key):
        log_fn('   [LỖI] Chưa có OPENAI_API_KEY / GEMINI_API_KEY hoặc tài khoản Gemini web để phân tích phim')
        return
    frames_dir = os.path.join(temp_dir, 'frames')
    os.makedirs(frames_dir, exist_ok=True)
    duration = _get_duration(video_path)
    if duration <= 0:
        log_fn('   [LỖI] Không đọc được thời lượng video')
        return
    log_fn(f'''   Trích {max_frames} khung hình chính từ video ({duration:.0f}s)...''')
    frames = _extract_keyframes(video_path, frames_dir, duration, max_frames, log_fn)
    if not frames:
        log_fn('   [LỖI] Không trích được khung hình chính')
        return
    log_fn(f'''   Đã có {len(frames)} khung hình chính. Gọi Vision AI để phân tích...''')
    transcript_sample = _make_transcript_sample(transcript, max_chars=16000)
    film_context = ((film_context or '')).strip()
    _ctx_block = ''
    if film_context:
        _ctx_block = f'''\nNGỮ CẢNH PHIM DO NGƯỜI DÙNG CUNG CẤP (thông tin CHÍNH XÁC, ƯU TIÊN TUYỆT ĐỐI — bám sát tên phim/nhân vật/cốt truyện dưới đây thay vì tự đoán, chỉ dùng hình ảnh + phụ đề để XÁC ĐỊNH THỜI ĐIỂM diễn ra các tình tiết đã biết này, không suy diễn tình tiết khác mâu thuẫn với ngữ cảnh):\n"""\n{film_context}\n"""\n'''
    prompt = f'''Bạn là chuyên gia phân tích phim ảnh chuyên nghiệp. Tôi sẽ gửi {len(frames)} khung hình được trích xuất từ bộ phim,\nkèm theo phần phụ đề hội thoại được nhận dạng từ âm thanh gốc của phim. Hãy phân tích kỹ cốt truyện, diễn biến và bối cảnh để trả về JSON theo đúng schema dưới đây.\n{_ctx_block}\nPHỤ ĐỀ HỘI THOẠI (trích đoạn):\n"""\n{transcript_sample}\n"""\n\nTHỜI ĐIỂM CỦA TỪNG FRAME (giây): {[round(ts, 1) for (ts, _) in frames]}\n\nCHÚ Ý QUAN TRỌNG VỀ ĐỐI CHIẾU HÌNH ẢNH VÀ THOẠI:\n1. Đối chiếu kỹ mỗi Khung hình thứ N (kèm nhãn thời gian tương ứng) với phần PHỤ ĐỀ HỘI THOẠI ở mốc thời gian gần đó.\n2. Phải đảm bảo nội dung của "description" tại mỗi timestamp trong mảng "plot_beats" phản ánh chính xác hành động hoặc diễn biến cốt truyện thực tế diễn ra trong Khung hình thứ N và phụ đề thoại tại thời điểm đó.\n3. Tuyệt đối không bịa ra kịch bản sai lệch, không bịa ra cốt truyện không có trong hình ảnh và thoại. Phải bám sát diễn biến thật của video đầu vào để viết kịch bản đúng trọng tâm phim.\n\nYÊU CẦU TRẢ VỀ JSON CHÍNH XÁC THEO SCHEMA NÀY (chỉ trả về chuỗi JSON thuần túy, không thêm bất kỳ văn bản giải thích nào khác):\n{{\n  "genre": "thể loại phim (ví dụ: kinh dị, giật gân, hành động, trinh thám...)",\n  "title_guess": "đoán tên phim (ví dụ: Chú Nguyền, Incantation... nếu không rõ thì ghi \'Không xác định\')",\n  "origin": "nước sản xuất gốc: \\"han\\" (Hàn Quốc) / \\"trung\\" (Trung Quốc) / \\"nhat\\" (Nhật) / \\"thai\\" (Thái Lan) / \\"au-my\\" / \\"khac\\". DẤU HIỆU NHẬN BIẾT: (1) Phụ đề chứa ký tự Hangul (가나다...) → CHẮC CHẮN là phim Hàn, ghi \\"han\\". (2) Phụ đề chứa chữ Hán/tiếng Trung nhưng bối cảnh có bầu cử Tổng thống + Quốc hội dân bầu = Hàn Quốc lồng tiếng Trung, ghi \\"han\\". (3) Phụ đề chứa chữ Hiragana/Katakana (あいう/アイウ) → Nhật, ghi \\"nhat\\". ĐỪNG chỉ dựa vào ngôn ngữ thoại — dựa vào bối cảnh văn hóa, trang phục, thể chế chính trị, kiến trúc, món ăn, tên riêng. Không chắc thì ghi \\"khac\\".",\n  "main_characters": ["danh sách nhân vật kèm vai trò chính của họ trong cốt truyện"],\n  "setting": "bối cảnh thời gian và địa điểm diễn ra các sự kiện chính trong phim",\n  "plot_beats": [\n    {{"timestamp": <giây>, "description": "sự kiện chính hoặc diễn biến cốt truyện đang xảy ra ở thời điểm này (nêu rõ hành động, động cơ hoặc ý nghĩa cốt truyện liên quan, tránh miêu tả hình ảnh tĩnh đơn sơ)"}}\n  ],\n  "themes": ["các chủ đề, thông điệp chính của bộ phim"],\n  "summary": "tóm tắt cốt truyện chi tiết của phim (khoảng 15-20 câu, bằng tiếng Việt, kể từ đầu phim đến cái kết hoàn chỉnh, giải thích rõ các tình tiết quan trọng, nút thắt và bí ẩn chính của phim)"\n}}\n\nTất cả nội dung văn bản trong JSON đều phải viết bằng TIẾNG VIỆT có dấu chuẩn xác.\nQUY TẮC TÊN NHÂN VẬT trong main_characters & summary: CHỈ phiên âm Hán Việt khi phim XÁC ĐỊNH là Trung Quốc/Hoa ngữ. Với phim Hàn (Kim Min Jae, Lee Soo Jin), Nhật (Tanaka, Sakura), Thái (Somchai, Ploy), Âu-Mỹ (John, Anna) HOẶC khi KHÔNG CHẮC xuất xứ → GIỮ NGUYÊN tên romanized gốc, TUYỆT ĐỐI KHÔNG phiên âm Hán Việt dù thoại gốc là tiếng Trung (phim lồng tiếng).\nPHIM HÀN audio gốc (Hangul trong phụ đề): Tên nhân vật Hàn phải viết theo Revised Romanization of Korean — ví dụ: 이민준 → "Lee Min Jun" (KHÔNG phải "Lý Dân Tuấn"), 김수현 → "Kim Soo Hyun" (KHÔNG phải "Kim Tú Hiền"), 나화진 → "Na Hwa Jin". Tên Hàn có gốc Hán (Sino-Korean) vẫn đọc theo phát âm Hàn, KHÔNG đọc theo âm Hán Việt.\nĐẶC BIỆT với phim Hàn/Nhật/Thái LỒNG TIẾNG TRUNG: phụ đề sẽ có tên pinyin dạng "Xiao Piao", "Xiao Min", "Xiao Ba" — TUYỆT ĐỐI KHÔNG chuyển thành "Phiêu", "Minh", "Bá". Giữ nguyên "Xiao Piao", "Xiao Min" HOẶC dùng mô tả vai trò (ví dụ: "cậu bé chuyển trường", "trùm lớp", "bạn thân nhân vật chính"). Lý do: người xem Việt sẽ nhầm tưởng đây là tên nhân vật Việt Nam.\nQUAN TRỌNG: Mảng plot_beats phải có đúng {len(frames)} mục — mỗi mục tương ứng với một frame đã gửi, theo đúng thứ tự thời gian.\n"timestamp" của mỗi beat phải lấy chính xác từ danh sách THỜI ĐIỂM ở trên (kiểu số thực hoặc số nguyên).\n"description" phải mô tả sự kiện liên kết chặt chẽ với tình tiết cốt truyện tại thời điểm đó dựa trên phụ đề và hình ảnh.\n'''
    max_tok = min(16000, 3000 + len(frames) * 120)
    text = _vision_dispatch(prompt, frames, gemini_key, openai_key, log_fn, detail='low', temperature=0.3, max_tokens=max_tok, quality=quality)
    if not text:
        log_fn('   [LỖI] Vision AI không trả về kết quả phân tích.')
        return
    data = _parse_analysis_json(text, log_fn)
    if not data:
        return
    try:
        from .translator import _find_known_titles as _fkt
        _lookup = data.get('title_guess', '') + ' ' + data.get('summary', '')
        _known = _fkt(_lookup)
        if _known:
            (vi_t, src_t) = _known[0]
            data['title_guess'] = f'''{vi_t} ({src_t})'''
            data['_vi_title'] = vi_t
            data['_vi_title_src'] = src_t
    except Exception:
        pass
    log_fn(f'''   Phân tích xong. Thể loại: {data.get('genre', '?')} | Phim: {data.get('title_guess', '?')}''')
    return data
def _parse_analysis_json(text, log_fn=print):
    text = re.sub('^```(?:json)?\\s*', '', text)
    text = re.sub('\\s*```$', '', text).strip()
    content_cleaned = _clean_json_newlines(text)
    try:
        return json.loads(content_cleaned)
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search('\\{.*\\}', content_cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            content_cleaned = m.group(0)
    mapping = {}
    genre_m = re.search('"genre"\\s*:\\s*"([^"]+)"', content_cleaned)
    mapping['genre'] = genre_m.group(1).strip() if genre_m else 'Không xác định'
    title_m = re.search('"title_guess"\\s*:\\s*"([^"]+)"', content_cleaned)
    mapping['title_guess'] = title_m.group(1).strip() if title_m else 'Không xác định'
    origin_m = re.search('"origin"\\s*:\\s*"([^"]+)"', content_cleaned)
    mapping['origin'] = origin_m.group(1).strip() if origin_m else ''
    setting_m = re.search('"setting"\\s*:\\s*"([^"]+)"', content_cleaned)
    mapping['setting'] = setting_m.group(1).strip() if setting_m else 'Không xác định'
    summary_m = re.search('"summary"\\s*:\\s*"([\\s\\S]+?)"\\s*\\}', content_cleaned)
    mapping['summary'] = summary_m.group(1).strip().replace('\\n', '\n').replace('\\"', '"') if summary_m else 'Không xác định'
    chars_block_m = re.search('"main_characters"\\s*:\\s*\\[([\\s\\S]*?)\\]', content_cleaned)
    mapping['main_characters'] = [c.strip().strip('"').replace('\\"', '"') for c in chars_block_m.group(1).split(',') if c.strip()] if chars_block_m else []
    themes_block_m = re.search('"themes"\\s*:\\s*\\[([\\s\\S]*?)\\]', content_cleaned)
    mapping['themes'] = [t.strip().strip('"').replace('\\"', '"') for t in themes_block_m.group(1).split(',') if t.strip()] if themes_block_m else []
    plot_beats = []
    beats_block_m = re.search('"plot_beats"\\s*:\\s*\\[([\\s\\S]*?)\\]', content_cleaned)
    if beats_block_m:
        beat_matches = re.findall('\\{\\s*"timestamp"\\s*:\\s*(\\d+\\.?\\d*)\\s*,\\s*"description"\\s*:\\s*"([\\s\\S]*?)"\\s*\\}', beats_block_m.group(1))
        for (ts, desc) in beat_matches:
            plot_beats.append({'timestamp': float(ts), 'description': desc.strip().replace('\\n', '\n').replace('\\"', '"')})
    mapping['plot_beats'] = plot_beats
    if plot_beats or mapping.get('summary') not in ('', 'Không xác định') or mapping.get('title_guess') not in ('', 'Không xác định'):
        log_fn(f'''   [WARN] JSON phân tích phim bị lỗi định dạng -> đã khôi phục bằng regex ({len(plot_beats)} plot beats).''')
        return mapping
    log_fn('   [WARN] Không phân tích được JSON kết quả phân tích phim.')
    return {}
def _get_duration(video_path):
    cmd = [FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, creationflags=_HIDE)
        return float(r.stdout.strip())
    except Exception:
        return 0.0
def _extract_keyframes(video_path, out_dir, duration, n_frames, log_fn):
    frames = []
    start = min(duration * 0.01, 3.0)          # từ đầu phim (trước bỏ 5% đầu → đoạn mở đầu không bao giờ được kể)
    end = duration * 0.97
    if end - start < 5:
        start = 0
        end = duration
    step = (end - start) / max(1, n_frames - 1)
    for i in range(n_frames):
        ts = start + step * i
        out_path = os.path.join(out_dir, f'''frame_{i:03d}.jpg''')
        cmd = [FFMPEG_EXE, '-y', '-ss', str(ts), '-i', video_path, '-frames:v', '1', '-q:v', '3', '-vf', 'scale=640:-1', out_path]
        r = subprocess.run(cmd, capture_output=True, creationflags=_HIDE)
        if r.returncode == 0 and os.path.exists(out_path):
            frames.append((ts, out_path))
    return frames
def _make_transcript_sample(transcript, max_chars=8000):
    if not transcript or not transcript.get('segments'):
        return ''
    lines = [f'''[{float(seg.get('start', 0) or 0):.0f}s] {seg.get('text', '')}''' for seg in transcript['segments']]
    full = '\n'.join(lines)
    if len(full) <= max_chars:
        return full
    # lấy mẫu ĐỀU cả phim cho vừa max_chars (trước lấy 1/200 rồi cắt cụt ở max_chars → mất hẳn thoại cuối phim)
    step = max(1, -(-len(full) // max_chars))
    while step < len(lines):
        sampled = '\n'.join(lines[::step])
        if len(sampled) <= max_chars:
            return sampled
        step += 1
    return '\n'.join(lines[::max(1, len(lines) // 50)])[:max_chars]