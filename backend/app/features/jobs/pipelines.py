"""Các pipeline xử lý — viết lại sạch từ AutoReviewApp._process_single_video (main_qt.py).

review : tải → Whisper → Vision AI → viết kịch bản → (sửa) → TTS → (xem trước) → dựng video
reup   : tải → Whisper → dịch → (sửa) → TTS → (xem trước) → dựng video
srt    : Whisper → (dịch) → xuất SRT
burn   : ghép file SRT vào video bằng ffmpeg

Mỗi bước là một hàm `_step_*` nhận `Run` (ngữ cảnh chung của một lần chạy) — thêm/bớt bước chỉ cần sửa
danh sách trong `_video_pipeline`, không phải lần trong một hàm dài.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

from app import constants as C
from app.config import get_key, load_settings
from app.srt_utils import cues_to_srt, parse_srt, rechunk_cues, scenes_to_cues, segments_to_cues
from .manager import JobCancelled

VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v', '.ts', '.wmv')
DEFAULT_LAYOUT = '2 dòng gọn (khuyên dùng)'
DEFAULT_STYLE = 'Mặc định (chữ trắng, viền đen)'
MULTI_VOICE_HINT = ('Ở những phân cảnh quan trọng, hãy giữ lại 1-2 câu thoại đắt giá của nhân vật dưới dạng trích dẫn '
                    'trực tiếp trong ngoặc kép (ví dụ: Nàng nói: "..."), thay vì kể gián tiếp toàn bộ.')


# ═════════════════════════════════════════════════════════════════ helpers
def _is_url(s):
    return s.startswith(('http://', 'https://'))


def validate_input(inp):
    inp = (inp or '').strip()
    if not inp:
        raise ValueError('Chưa chọn video hoặc URL.')
    if _is_url(inp):
        return inp
    if not os.path.isfile(inp):
        raise ValueError(f'Không tìm thấy file: {inp}')
    if not inp.lower().endswith(VIDEO_EXTS):
        raise ValueError('File không phải định dạng video hỗ trợ: ' + ', '.join(VIDEO_EXTS))
    if os.path.getsize(inp) == 0:
        raise ValueError('File video rỗng (0 byte).')
    return inp


def _out_dir(cfg):
    out = cfg.get('out_dir') or load_settings()['output_dir']
    os.makedirs(out, exist_ok=True)
    return out


@contextmanager
def _workspace(job, out_dir, resumable=False):
    """Thư mục tạm cùng ổ với thư mục xuất (tránh copy chéo ổ khi dựng video).

    Xong → dọn. resumable=True: lỗi/huỷ thì GIỮ LẠI (video tải về, audio TTS…) để "Tiếp tục" dùng lại,
    và lần tiếp tục dùng đúng thư mục cũ. Xoá job trong Lịch sử sẽ dọn thư mục này.
    """
    if resumable and job.temp_dir and os.path.isdir(job.temp_dir):
        path = job.temp_dir
    else:
        drive = os.path.splitdrive(os.path.abspath(out_dir))[0] or os.path.splitdrive(tempfile.gettempdir())[0]
        path = os.path.join(drive + os.sep, 'ReviewFilm_Temp', f"_temp_{time.strftime('%Y%m%d_%H%M%S')}_{job.id}")
        os.makedirs(path, exist_ok=True)
        job.temp_dir = path
    try:
        yield path
    except BaseException:
        if not resumable:
            shutil.rmtree(path, ignore_errors=True)
        raise
    if not job.config.get('keep_temp'):
        shutil.rmtree(path, ignore_errors=True)
        job.temp_dir = ''


def _layout(cfg):
    return C.SUBTITLE_LAYOUT_PRESETS.get(cfg.get('sub_layout'), C.SUBTITLE_LAYOUT_PRESETS[DEFAULT_LAYOUT])


def _rechunk(cues, layout):
    return rechunk_cues(cues, layout['sub_max_chars_per_chunk'], layout['sub_max_lines'])


def _write_srt(path, cues):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(cues_to_srt(cues))
    return path


def _unique_path(path):
    """Không ghi đè kết quả cũ: 'a.mp4' đã có → 'a (2).mp4', 'a (3).mp4'…
    Ghi đè còn hỏng khi file cũ đang mở (đang phát) — Windows khoá file, ffmpeg báo lỗi."""
    if not os.path.exists(path):
        return path
    (root, ext) = os.path.splitext(path)
    n = 2
    while os.path.exists(f'{root} ({n}){ext}'):
        n += 1
    return f'{root} ({n}){ext}'


def _base_name(video_path):
    from core.utils import safe_filename
    return safe_filename(os.path.splitext(os.path.basename(video_path))[0])


def _voice_id(label):
    return C.VOICE_OPTIONS.get(label, label or 'vi-VN-HoaiMyNeural')


def _speed(cfg):
    try:
        return float(str(cfg.get('video_speed', '1.0x')).split('x')[0] or 1.0)
    except ValueError:
        return 1.0


def _clean_scene(s):
    """Bỏ field nội bộ không serialize được, giữ field cần thiết cho UI."""
    out = {}
    for (k, v) in s.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, (list, dict)):
            try:
                json.dumps(v)
                out[k] = v
            except (TypeError, ValueError):
                pass
    return out


def _sub_style(cfg):
    style = dict(C.SUBTITLE_STYLE_PRESETS.get(cfg.get('sub_style')) or C.SUBTITLE_STYLE_PRESETS[DEFAULT_STYLE])
    style.update({k: v for (k, v) in (cfg.get('sub_custom') or {}).items() if k.startswith('sub_')})
    if cfg.get('sub_margin_pct') is not None:
        style['sub_margin_v_pct'] = float(cfg['sub_margin_pct']) / 100.0
    if cfg.get('sub_width_pct') is not None:
        style['sub_max_width_pct'] = float(cfg['sub_width_pct']) / 100.0
    style.pop('sub_max_lines', None)
    return style


# AI chạy bằng tài khoản ChatGPT/Gemini đăng nhập trong app (core.web_llm) — các tham số key của
# core để trống, engine 'web' được chèn tự động.
NO_KEY = ''


def _web_ai():
    from core import web_llm
    return web_llm


# ═════════════════════════════════════════════════════════════════ bước dùng chung
def _resolve_video(job, inp, temp_dir):
    if not _is_url(inp):
        job.log(f'[1] Tệp video: {os.path.basename(inp)}', 'info')
        return inp
    from core.downloader import download_video
    job.log('[1] Tải video từ URL...', 'info')
    job.set_progress(4, 'Tải video')
    path = download_video(inp, temp_dir, job.log)
    if not path or not os.path.isfile(path):
        raise RuntimeError('Tải video thất bại.')
    return path


def _is_hallucination(text):
    """Whisper 'ảo giác' trên nhạc/tiếng ngân: một chữ/âm lặp lại dày đặc (哼哼哼…, ừ ừ ừ…, la la la…)."""
    t = ''.join(ch for ch in (text or '') if not ch.isspace() and ch not in '.,!?…~-—，。！？、')
    if len(t) < 8:
        return False
    if len(set(t)) / len(t) < 0.15:            # rất ít ký tự khác nhau so với độ dài
        return True
    words = (text or '').split()
    return len(words) >= 6 and len(set(w.lower() for w in words)) / len(words) < 0.2


def _transcribe(job, video_path, temp_dir, cfg, beam, allow_empty=False):
    """Whisper. allow_empty=True (Review): video không có lời thoại vẫn chạy tiếp — AI viết kịch bản từ hình ảnh."""
    from core.transcriber import transcribe_audio
    job.set_progress(10, 'Nhận dạng giọng nói (Whisper)')
    job.log('[2] Whisper nhận dạng giọng nói...', 'info')
    lang = C.LANGUAGE_MAP.get(cfg.get('source_lang', 'Tự động'), 'auto')
    transcript = transcribe_audio(video_path, cfg.get('whisper_model', 'base'), temp_dir, lang, job.log,
                                  device=cfg.get('device', 'GPU (NVIDIA)'), beam_size=beam, should_stop=lambda: job.cancelled)
    job.check()
    if transcript is None:
        # None = Whisper/trích audio LỖI (khác với "không có lời thoại"). Chỉ coi là không lời khi video không có tiếng.
        from core.video_editor import _has_audio
        if _has_audio(video_path):
            raise RuntimeError('Whisper chạy lỗi (xem nhật ký phía trên) — bấm Tiếp tục để thử lại, hoặc đổi Whisper model nhỏ hơn.')
        job.log('   Video không có track âm thanh.', 'warn')
    if transcript and transcript.get('segments'):
        kept = [seg for seg in transcript['segments'] if not _is_hallucination(seg.get('text', ''))]
        dropped = len(transcript['segments']) - len(kept)
        if dropped:
            job.log(f'   [LỌC] Bỏ {dropped} đoạn Whisper nghe nhầm (chữ lặp vô nghĩa, thường do nhạc/tiếng ngân)', 'warn')
            transcript = {**transcript, 'segments': kept}
    if not transcript or not transcript.get('segments'):
        if not allow_empty:
            raise RuntimeError('Whisper không nhận dạng được lời thoại (video có thể không có tiếng nói).')
        job.log('   [CẢNH BÁO] Video không có lời thoại (chỉ nhạc/hiệu ứng) — AI sẽ viết kịch bản chỉ dựa vào hình ảnh.', 'warn')
        transcript = {**(transcript or {}), 'segments': []}
    return transcript, lang


def _translate(job, segments, lang, cfg, video_path):
    """Dịch + Việt hoá phụ đề. AI khi bật ai_translate và có engine; không thì Google miễn phí."""
    from core.translator import translate_and_localize_transcript
    use_ai = bool(cfg.get('ai_translate')) and _web_ai().available()
    job.log(f"   Dịch phụ đề ({'AI — tài khoản web' if use_ai else 'Google miễn phí'})...", 'info')
    return translate_and_localize_transcript(
        segments, api_key=NO_KEY, source_lang=lang, log_fn=job.log, openai_key=NO_KEY, user_context=(cfg.get('film_context') or '').strip(),
        video_filename=os.path.basename(video_path), allow_web=use_ai)


def voice_in_use(job):
    """Giọng để tạo lại câu: giọng đã đọc thật cho video (khác giọng đã chọn khi CapCut lỗi phải đọc bằng Edge)."""
    return job.result.get('voice_fallback') or job.config.get('voice', '')


def _note_voice_fallback(job, rendered):
    """Đã chọn CapCut mà cả video phải đọc bằng Edge → nhớ lại để tạo lại câu không bị lẫn 2 giọng."""
    voice = _voice_id(job.config.get('voice', ''))
    if not str(voice).lower().startswith('capcut-') or not rendered:
        return
    if all(s.get('_tts_engine_used') == 'edge' for s in rendered):
        from core.capcut_tts import edge_fallback
        job.result['voice_fallback'] = edge_fallback(voice[len('capcut-'):])
        job.log('   Video đã đọc bằng Edge thay CapCut — các câu tạo lại sau này cũng dùng Edge cho đồng đều giọng', 'warn')
    else:
        job.result.pop('voice_fallback', None)


def synthesize(scenes, voice_label, out_dir, log, strict=False):
    from core.tts_engine import generate_tts_per_scene
    voice = _voice_id(voice_label)
    return generate_tts_per_scene(scenes, voice, out_dir, log_fn=log, fptai_key=get_key('FPT_API_KEY'), strict_voice=strict)


# ═════════════════════════════════════════════════════════════════ review / reup
@dataclass
class Run:
    """Ngữ cảnh một lần chạy review/reup — truyền giữa các bước thay cho chục biến cục bộ."""
    job: object
    cfg: dict
    out_dir: str
    temp_dir: str
    is_review: bool
    video_path: str = ''
    base: str = ''
    transcript: dict = field(default_factory=dict)
    lang: str = 'auto'
    layout: dict = field(default_factory=dict)
    mixer: dict = field(default_factory=dict)

    def log(self, msg, tag=None):
        self.job.log(msg, tag)


# Các bước review/reup theo thứ tự: (khoá checkpoint, nhãn hiển thị).
VIDEO_STEPS = (
    ('source', 'Tải video & Whisper'),
    ('script', 'Phân tích & viết kịch bản / dịch'),
    ('edit', 'Sửa kịch bản'),
    ('voice', 'Tạo giọng đọc'),
    ('autopost', 'Tự hậu kỳ'),
    ('preview', 'Xem trước'),
    ('render', 'Dựng video'),
)


def _step_funcs(run):
    return {'source': _step_source, 'script': _step_script if run.is_review else _step_translate,
            'edit': _step_edit, 'voice': _step_voice, 'autopost': _step_autopost, 'preview': _step_preview,
            'render': _step_render}


def _save_checkpoint(run, done_key):
    """Ghi lại trạng thái sau bước `done_key` — lỗi ở bước sau thì "Tiếp tục" bắt đầu từ đây."""
    keys = [k for (k, _) in VIDEO_STEPS]
    i = keys.index(done_key)
    run.job.checkpoint = {
        'done': done_key,
        'next_label': VIDEO_STEPS[i + 1][1] if i + 1 < len(VIDEO_STEPS) else '',
        'video_path': run.video_path, 'base': run.base, 'lang': run.lang,
        'transcript': run.transcript, 'mixer': run.mixer,
    }
    run.job.save()


def _restore_checkpoint(run):
    """Nạp lại trạng thái từ checkpoint. Trả về vị trí bước bắt đầu (0 = chạy từ đầu)."""
    ck = run.job.checkpoint or {}
    keys = [k for (k, _) in VIDEO_STEPS]
    if ck.get('done') not in keys:
        return 0
    if not ck.get('video_path') or not os.path.isfile(ck['video_path']):
        run.log('   [CẢNH BÁO] Không còn file video của lần trước — chạy lại từ đầu.', 'warn')
        return 0
    (run.video_path, run.base, run.lang) = (ck['video_path'], ck.get('base', ''), ck.get('lang', 'auto'))
    run.transcript = ck.get('transcript') or {'segments': []}
    run.mixer = ck.get('mixer') or {}
    start = keys.index(ck['done']) + 1
    run.log(f'   Bỏ qua {start} bước đã xong — tiếp tục từ: {VIDEO_STEPS[start][1]}', 'ok')
    return start


def run_video_pipeline(job):
    cfg = job.config
    out_dir = _out_dir(cfg)
    with _workspace(job, out_dir, resumable=True) as temp_dir:
        run = Run(job, cfg, out_dir, temp_dir, is_review=cfg.get('mode', 'review') == 'review',
                  layout=_layout(cfg))
        funcs = _step_funcs(run)
        start = _restore_checkpoint(run)
        for (key, _) in VIDEO_STEPS[start:]:
            funcs[key](run)
            job.check()
            _save_checkpoint(run, key)
    job.checkpoint = {}


def _step_source(run):
    """Tải/nhận video → Whisper → lưu SRT gốc."""
    run.video_path = _resolve_video(run.job, run.cfg['inp'], run.temp_dir)
    run.job.result['video_path'] = run.video_path
    run.job.check()
    (run.transcript, run.lang) = _transcribe(run.job, run.video_path, run.temp_dir, run.cfg,
                                             beam=1 if run.is_review else 5, allow_empty=run.is_review)
    run.base = _base_name(run.video_path)
    if run.transcript['segments']:
        cues = _rechunk(segments_to_cues(run.transcript['segments']), run.layout)
        run.job.result['original_srt'] = _write_srt(os.path.join(run.out_dir, run.base + '_original.srt'), cues)
        run.log(f"   Đã lưu SRT gốc: {run.job.result['original_srt']}", 'ok')


def _step_script(run):
    """Review: Vision AI phân tích phim → viết kịch bản thuyết minh."""
    from core.gemini_analyzer import analyze_video, vision_available
    from core.script_writer import write_review_script, write_review_script_v2
    from core.utils import get_video_duration
    (job, cfg) = (run.job, run.cfg)
    if not vision_available(NO_KEY, NO_KEY):
        raise RuntimeError('Chế độ Review cần đăng nhập Gemini — vào Cài đặt → Tài khoản AI.')
    vid_dur = get_video_duration(run.video_path)
    if vid_dur <= 0:
        raise RuntimeError('Không đọc được thời lượng video (ffprobe lỗi).')
    mins = int(cfg.get('minutes', 12))
    # Lời đọc không được dài hơn video gốc: video 1 phút mà xin review 12 phút → mỗi cảnh ~500 từ cho ~13s hình,
    # hình bị kéo chậm/lặp và lời lệch cảnh. Giới hạn ≈ 95% độ dài video gốc.
    src_min = vid_dur / 60.0
    if mins > src_min:
        capped = max(0.3, round(src_min * 0.95, 2))
        run.log(f'   [GIỚI HẠN] Video gốc chỉ {vid_dur:.0f}s — rút độ dài kịch bản từ ~{mins} phút xuống ~{capped * 60:.0f}s '
                'để lời đọc khớp hình từng cảnh.', 'warn')
        mins = capped
    film_ctx = (cfg.get('film_context') or '').strip()
    if cfg.get('multi_voice'):
        film_ctx = (film_ctx + '\n' if film_ctx else '') + MULTI_VOICE_HINT

    job.set_progress(30, 'Phân tích nội dung (Vision AI)')
    frames = int(min(180, max(15, mins * 5, int(vid_dur / 60.0) * 2)))
    run.log(f'[3] Phân tích nội dung phim bằng Vision AI — {frames} khung hình, phim {vid_dur / 60:.0f} phút', 'info')
    analysis = analyze_video(run.video_path, run.transcript, NO_KEY, run.temp_dir, max_frames=frames, log_fn=job.log,
                             openai_key=NO_KEY, quality='standard', film_context=film_ctx)
    if not analysis:
        raise RuntimeError('Phân tích nội dung thất bại.')
    if isinstance(analysis, dict):     # giữ phần tóm tắt cho bước viết bài đăng
        job.result['film'] = {k: analysis.get(k) for k in ('title_guess', 'genre', 'setting', 'themes', 'summary') if analysis.get(k)}
    job.check()

    job.set_progress(45, 'Viết kịch bản')
    run.log('[4] Viết kịch bản thuyết minh...', 'info')
    if cfg.get('scene_accurate'):
        run.log('   → Cắt cảnh theo scene thật + phân tích từng chương (V2)', 'info')
        script = write_review_script_v2(analysis, run.transcript, vid_dur, run.video_path, target_minutes=mins,
                                        log_fn=job.log, deepseek_key=NO_KEY, openai_key=NO_KEY,
                                        gemini_key=NO_KEY, film_context=film_ctx, temp_dir=run.temp_dir)
    else:
        script = write_review_script(analysis, run.transcript, vid_dur, target_minutes=mins, log_fn=job.log,
                                     deepseek_key=NO_KEY, openai_key=NO_KEY, gemini_key=NO_KEY,
                                     film_context=film_ctx)
    scenes = script.get('scenes') if isinstance(script, dict) else script
    if not scenes:
        raise RuntimeError('AI không tạo được cảnh nào — thử lại hoặc đổi video khác.')
    job.scenes = [_clean_scene(s) for s in scenes]


def _step_translate(run):
    """Reup: dịch phụ đề gốc sang tiếng Việt."""
    run.job.set_progress(30, 'Dịch phụ đề')
    run.log('[3] Dịch phụ đề...', 'info')
    scenes = _translate(run.job, run.transcript['segments'], run.lang, run.cfg, run.video_path)
    if not scenes:
        raise RuntimeError('Dịch phụ đề thất bại.')
    run.job.scenes = [_clean_scene(s) for s in scenes]


def _step_edit(run):
    """Dừng cho người dùng sửa kịch bản/bản dịch (nếu bật)."""
    job = run.job
    if not run.cfg.get('script_edit', True):
        return
    run.log('   Chờ bạn xem & sửa kịch bản/bản dịch...', 'info')
    reply = job.wait_for('script', 'Chờ sửa kịch bản')
    if reply.get('scenes') is not None:
        job.scenes = [s for s in reply['scenes'] if (s.get('voiceover') or '').strip()]
    if not job.scenes:
        raise RuntimeError('Không còn câu nào để tạo giọng đọc.')
    run.log(f'   Đã xác nhận {len(job.scenes)} câu.', 'ok')


def _step_voice(run):
    """TTS một giọng, hoặc phân vai nhiều giọng (review + multi_voice + có engine phân vai)."""
    (job, cfg) = (run.job, run.cfg)
    job.set_progress(55, 'Tạo giọng đọc')
    audio_dir = os.path.join(run.temp_dir, 'audio')
    voice_label = cfg.get('voice', '')
    web = _web_ai()
    cast_key = web.WEB_KEY if web.available() else ''
    if cfg.get('multi_voice') and run.is_review and cast_key:
        run.log('[5] Phân vai nhân vật...', 'info')
        rendered = _multi_voice(job, voice_label, audio_dir, cast_key, cfg)
    else:
        run.log(f'[5] Tạo giọng đọc: {voice_label}', 'info')
        rendered = synthesize([dict(s) for s in job.scenes], voice_label, audio_dir, job.log, strict=cfg.get('strict_voice', False))
    if not rendered:
        raise RuntimeError('Tạo giọng đọc thất bại.')
    _note_voice_fallback(job, rendered)
    rendered = _fill_missing_voices(job, rendered, voice_in_use(job), audio_dir, cfg)
    job.scenes = [_clean_scene(s) for s in rendered]


EDGE_BACKUP_VOICE = 'Edge TTS — Nữ Bắc (miễn phí)'


def _fill_missing_voices(job, rendered, voice_label, audio_dir, cfg):
    """Engine TTS bỏ qua cảnh lỗi (mạng, bị chặn tần suất…) → video sẽ mất đoạn mà không ai biết.
    Đọc lại riêng từng cảnh thiếu; vẫn lỗi thì đọc bằng Edge; vẫn không được thì dừng job, báo rõ cảnh nào."""
    wanted = [(i, s) for (i, s) in enumerate(job.scenes) if (s.get('voiceover') or '').strip()]
    got = {int(s.get('_original_index', -1)) for s in rendered}
    missing = [(i, s) for (i, s) in wanted if i not in got]
    if not missing:
        return rendered
    job.log(f"   [WARN] {len(missing)} cảnh chưa có giọng ({', '.join(f'#{i + 1}' for (i, _) in missing[:10])}) — đọc lại từng cảnh...", 'warn')
    strict = cfg.get('strict_voice', False)
    fixed, still = [], []
    for (i, s) in missing:
        out = None
        for label in [voice_label] + ([] if strict or voice_label == EDGE_BACKUP_VOICE else [EDGE_BACKUP_VOICE]):
            job.check()
            r = synthesize([dict(s)], label, os.path.join(audio_dir, f'retry_{i}'), job.log, strict=strict)
            if r and r[0].get('tts_path'):
                out = {**r[0], '_original_index': i}
                if label != voice_label:
                    job.log(f'   Cảnh #{i + 1}: đọc bằng {label} thay giọng đã chọn', 'warn')
                break
        (fixed if out else still).append(out or i)
    if still:
        raise RuntimeError(f"Không tạo được giọng cho cảnh {', '.join(f'#{i + 1}' for i in still[:10])} — "
                           'kiểm tra mạng / đổi giọng rồi bấm Tiếp tục.')
    job.log(f'   Đã đọc bù {len(fixed)} cảnh', 'ok')
    return sorted(rendered + fixed, key=lambda s: int(s.get('_original_index', 0)))


def _step_autopost(run):
    """Tự hậu kỳ: căn hình theo lời → AI sửa kịch bản (nếu đã kết nối) → tạo lại giọng câu đã sửa → căn lại."""
    from core.utils import get_video_duration
    from .postedit import fix_durations, suggest_edits
    (job, cfg) = (run.job, run.cfg)
    if not cfg.get('auto_post', True):
        return
    job.set_progress(70, 'Tự hậu kỳ')
    run.log('[5b] Tự hậu kỳ: căn hình theo lời đọc, AI rà kịch bản...', 'info')
    scenes = [dict(s) for s in job.scenes]
    vdur = get_video_duration(run.video_path)
    fixed = set(fix_durations(scenes, vdur))

    ai_count, regen_ok, regen_fail = 0, 0, 0
    if _web_ai().available():
        try:
            edits = suggest_edits(scenes, job.kind, '', job.log)
        except RuntimeError as e:
            edits = []
            run.log(f'   [WARN] AI hậu kỳ bỏ qua: {e}', 'warn')
        multi = bool(cfg.get('multi_voice'))
        (to_voice, old_text) = ([], {})
        for e in edits:
            sc = scenes[e['id']]
            if e.get('exclude'):
                sc['excluded'] = True
                ai_count += 1
                continue
            if multi:          # đã phân vai nhiều giọng: không đọc lại 1 giọng, chỉ nhận đề xuất bỏ cảnh
                continue
            if e.get('subtitle'):
                sc['subtitle'] = e['subtitle']
            if e.get('voiceover'):
                old_text[e['id']] = (sc.get('voiceover'), sc.get('subtitle'))
                sc['voiceover'] = e['voiceover']
                if run.is_review:
                    sc['subtitle'] = e['voiceover']
                to_voice.append(e['id'])
            ai_count += 1
        if to_voice:
            job.check()
            run.log(f'   Tạo lại giọng {len(to_voice)} câu đã sửa (một lượt, song song)...', 'step')
            batch = [{**scenes[i], '_original_index': i} for i in to_voice]
            out_dir = os.path.join(run.temp_dir, 'audio', f'autopost_{uuid.uuid4().hex[:6]}')
            rendered = synthesize(batch, voice_in_use(job), out_dir, job.log, strict=cfg.get('strict_voice', False))
            by_idx = {int(r['_original_index']): r for r in rendered or [] if r.get('tts_path') and '_original_index' in r}
            for i in to_voice:
                if i in by_idx:
                    scenes[i].update({k: v for (k, v) in by_idx[i].items() if k.startswith('tts_') or k == '_tts_engine_used'})
                    regen_ok += 1
                else:
                    # lời mới chưa đọc được → giữ nguyên lời + phụ đề cũ cho khớp giọng cũ
                    (scenes[i]['voiceover'], scenes[i]['subtitle']) = old_text[i]
                    regen_fail += 1
    else:
        run.log('   (Chưa kết nối ChatGPT/Gemini — chỉ căn hình theo lời đọc)', 'info')
    fixed |= set(fix_durations(scenes, vdur))
    job.scenes = [_clean_scene(s) for s in scenes if not s.get('excluded')]
    run.log(f'   Tự hậu kỳ xong: căn {len(fixed)} đoạn hình, AI sửa {ai_count} mục, tạo lại {regen_ok} giọng'
            + (f' ({regen_fail} lỗi)' if regen_fail else ''), 'ok')


def _step_preview(run):
    """Dừng cho người dùng nghe lại, bỏ câu, chỉnh mixer (nếu bật)."""
    job = run.job
    if not run.cfg.get('scene_preview', True):
        return
    job.set_progress(80, 'Chờ xác nhận xuất video')
    run.log('   Chờ bạn nghe lại & xác nhận trước khi dựng video...', 'info')
    reply = job.wait_for('preview', 'Chờ xác nhận xuất video')
    if reply.get('scenes') is not None:
        job.scenes = [s for s in reply['scenes'] if not s.get('excluded')]
    run.mixer = reply.get('mixer') or {}
    # Vùng che sub gốc / vị trí phụ đề mới chỉnh ở Hậu kỳ → ghi vào cấu hình job (tự sửa lỗi, hậu kỳ lại dùng tiếp)
    cover = run.mixer.pop('cover', None) or {}
    if 'cover_boxes' in cover:
        boxes = [[float(v) for v in b][:4] for b in cover['cover_boxes'] if isinstance(b, (list, tuple)) and len(b) >= 4]
        run.cfg['cover_boxes'] = boxes
        run.cfg['remove_old_sub'] = bool(cover.get('remove_old_sub', True)) and bool(boxes)
    if cover.get('sub_margin_pct') is not None:
        run.cfg['sub_margin_pct'] = max(1.0, min(60.0, float(cover['sub_margin_pct'])))
    # Hiệu ứng / chuyển cảnh chọn ở Hậu kỳ (job tạo trước khi có tuỳ chọn này vẫn bật được)
    fx = run.mixer.pop('fx', None) or {}
    for (key, conv) in (('transition', str), ('transition_duration', float), ('color_preset', str),
                        ('ken_burns', bool), ('ken_burns_zoom', float), ('vignette', bool)):
        if key in fx:
            run.cfg[key] = conv(fx[key])
    if not job.scenes:
        raise RuntimeError('Không còn câu nào được chọn để xuất video.')


def _render_options(cfg, mixer):
    """Tham số tuỳ chọn cho build_review_video: che sub cũ, mixer âm thanh, tắt burn sub."""
    opts = {}
    if cfg.get('remove_old_sub') and cfg.get('cover_boxes'):
        opts.update(remove_old_sub=True, sub_cover_boxes=cfg['cover_boxes'])
    if mixer:
        opts['original_volume'] = float(mixer.get('original_volume', 0.08))
        if mixer.get('bgm_path') and os.path.isfile(mixer['bgm_path']):
            opts.update(bgm_path=mixer['bgm_path'], bgm_volume=float(mixer.get('bgm_volume', 0.05)),
                        audio_ducking=bool(mixer.get('audio_ducking', True)))
    if not cfg.get('burn_subtitles', True):
        opts['burn_subtitles'] = False
    # Thương hiệu: logo/watermark, intro, outro (file không tồn tại thì bỏ qua)
    if cfg.get('watermark_path') and os.path.isfile(cfg['watermark_path']):
        opts.update(watermark_path=cfg['watermark_path'], watermark_corner=cfg.get('watermark_corner', 'Trên-Phải'),
                    watermark_size_pct=float(cfg.get('watermark_size_pct', 14)), watermark_opacity=float(cfg.get('watermark_opacity', 0.92)))
    for key in ('intro_path', 'outro_path'):
        if cfg.get(key) and os.path.isfile(cfg[key]):
            opts[key] = cfg[key]
    # Hiệu ứng: màu, zoom chậm, tối viền, chuyển cảnh (tắt hết → giống bản cũ, dùng lại clip đã dựng)
    if cfg.get('color_preset', 'none') != 'none':
        opts['color_preset'] = cfg['color_preset']
    if cfg.get('ken_burns'):
        opts.update(ken_burns=True, ken_burns_zoom=float(cfg.get('ken_burns_zoom', 0.08)))
    if cfg.get('vignette'):
        opts['vignette'] = True
    if cfg.get('transition', 'none') != 'none':
        opts.update(transition=cfg['transition'], transition_duration=float(cfg.get('transition_duration', 0.5)))
    return opts


def _step_render(run):
    """Dựng video hoàn chỉnh + xuất SRT tiếng Việt → QA soi video → tự sửa chỗ lỗi (nếu bật)."""
    (job, cfg) = (run.job, run.cfg)
    job.set_progress(85, 'Dựng video')
    run.log('[6] Dựng video hoàn chỉnh...', 'info')
    out_path = _unique_path(os.path.join(run.out_dir, run.base + ('_review.mp4' if run.is_review else '_reup.mp4')))
    _render(run, out_path)
    _write_job_srt(run)
    run.log(f'[OK] Video: {out_path}', 'ok')
    job.set_progress(96, 'Kiểm tra video')
    try:
        qa = run_qa(job)
        if cfg.get('auto_fix', True) and any(c['status'] != 'ok' for c in qa['checks']):
            job.set_progress(97, 'Tự sửa lỗi video')
            _auto_fix(run, qa)
    except JobCancelled:
        raise
    except Exception as e:               # QA/tự sửa chỉ để nâng chất lượng — không làm hỏng video đã dựng xong
        run.log(f'   [WARN] Kiểm tra/tự sửa video lỗi: {e}', 'warn')
    if cfg.get('auto_publish', True) and _web_ai().available():
        job.set_progress(99, 'Viết bài đăng')
        try:
            from .publish import generate
            generate(job, log=job.log)
        except Exception as e:           # bài đăng viết lại được ở màn Hoàn thành
            run.log(f'   [WARN] Chưa viết được bài đăng: {e} — bấm "Bài đăng AI" ở màn Hoàn thành để thử lại.', 'warn')


def _render(run, out_path):
    """Dựng job.scenes ra out_path."""
    from core.video_editor import build_review_video
    (job, cfg) = (run.job, run.cfg)
    sub_source = C.SUBTITLE_SOURCE_OPTIONS.get(cfg.get('sub_source'), 'voiceover')
    result = build_review_video([dict(s) for s in job.scenes], run.video_path, out_path, run.temp_dir, log_fn=job.log,
                                target_resolution=cfg.get('target_resolution') or '1920x1080',
                                sub_source_mode=sub_source, is_reup=not run.is_review,
                                mirror_video=bool(cfg.get('mirror_video')), video_speed=_speed(cfg),
                                should_stop=lambda: job.cancelled,
                                **_sub_style(cfg), **run.layout, **_render_options(cfg, run.mixer))
    job.check()
    if not result or not os.path.isfile(out_path):
        raise RuntimeError('Dựng video thất bại.')
    job.result['output_path'] = out_path


def _write_job_srt(run):
    out_path = run.job.result['output_path']
    sub_source = C.SUBTITLE_SOURCE_OPTIONS.get(run.cfg.get('sub_source'), 'voiceover')
    run.job.result['srt_path'] = _write_srt(os.path.splitext(out_path)[0] + '.vi.srt', scenes_to_cues(run.job.scenes, sub_source))


def _auto_fix(run, qa):
    """QA thấy lỗi → sửa đúng chỗ (căn hình / AI viết lại lời / âm lượng / phụ đề) → dựng lại vào cùng file."""
    from core.utils import get_video_duration
    from .autofix import auto_fix
    (job, cfg) = (run.job, run.cfg)
    out_path = job.result['output_path']

    def render():
        job.check()
        tmp = os.path.splitext(out_path)[0] + '.fixing.mp4'
        try:
            _render(run, tmp)
        except BaseException:
            for f in (tmp, os.path.splitext(tmp)[0] + '.srt', os.path.splitext(tmp)[0] + '.ass'):
                if os.path.isfile(f):
                    os.remove(f)
            raise
        os.replace(tmp, out_path)
        for ext in ('.srt', '.ass'):       # video_editor ghi kèm phụ đề cạnh file tạm → thay vào bản chính
            side = os.path.splitext(tmp)[0] + ext
            if os.path.isfile(side):
                os.replace(side, os.path.splitext(out_path)[0] + ext)
        job.result['output_path'] = out_path
        _write_job_srt(run)

    def synth(scene, tag):
        job.check()
        rendered = synthesize([scene], voice_in_use(job), os.path.join(run.temp_dir, 'audio', tag), job.log, strict=cfg.get('strict_voice', False))
        if rendered and rendered[0].get('tts_path'):
            return _clean_scene({**scene, **rendered[0]})
        return None

    job.result['qa'] = auto_fix(job, qa, video_duration=get_video_duration(run.video_path), render=render, synth=synth,
                                write_srt=lambda: _write_job_srt(run), log=job.log)


def run_qa(job):
    """Kiểm tra chất lượng video vừa xuất, lưu vào job.result['qa'] và ghi tóm tắt ra log."""
    from .qa import check_video
    qa = check_video(job.result.get('output_path'), job.scenes, job.config, job.result.get('srt_path', ''))
    job.result['qa'] = qa
    bad = [c for c in qa['checks'] if c['status'] != 'ok']
    job.log(f"[QA] Điểm {qa['score']}/100 — {len(qa['checks']) - len(bad)}/{len(qa['checks'])} mục đạt", 'ok' if not bad else 'warn')
    for c in bad:
        job.log(f"   [{'LỖI' if c['status'] == 'fail' else 'CẢNH BÁO'}] {c['label']}: {c['detail']}", 'warn')
    return qa


def _multi_voice(job, voice_label, audio_dir, cast_key, cfg):
    from core.casting import analyze_characters
    from core.tts_engine import generate_tts_multi_voice
    scenes = [dict(s) for s in job.scenes]
    try:
        characters = analyze_characters(scenes, cast_key, job.log)
    except Exception as e:
        job.log(f'   [WARN] Phân vai lỗi ({e}) — đọc 1 giọng.', 'warn')
        characters = None
    if not characters:
        return synthesize(scenes, voice_label, audio_dir, job.log,
                          strict=cfg.get('strict_voice', False))
    (vmap, mi, fi) = ({}, 0, 0)
    for c in characters:
        if c.get('gioi_tinh') == 'nu':
            vmap[c['ten']] = C.VOICE_OPTIONS[C.VIENEU_CAST_FEMALE[fi % len(C.VIENEU_CAST_FEMALE)]]
            fi += 1
        else:
            vmap[c['ten']] = C.VOICE_OPTIONS[C.VIENEU_CAST_MALE[mi % len(C.VIENEU_CAST_MALE)]]
            mi += 1
    narrator = voice_label if voice_label in C.VIENEU_CAST_MALE + C.VIENEU_CAST_FEMALE else 'VieNeu — Bình An (Nam)'
    job.log(f"   Phân vai: người kể + {len(characters)} nhân vật ({', '.join(vmap)})", 'ok')
    return generate_tts_multi_voice(scenes, vmap, C.VOICE_OPTIONS[narrator], audio_dir, log_fn=job.log,
                                    strict_voice=cfg.get('strict_voice', False))


def regenerate_scene(job, idx, text, scene=None):
    """Tạo lại giọng 1 câu khi đang ở bước xem trước.

    `scene` = bản cảnh ở client (đã có thể đổi thứ tự / cắt trên timeline): dùng nó làm gốc và KHÔNG ghi đè
    job.scenes[idx] — thứ tự phía server có thể đã khác; client gửi cả kịch bản khi xác nhận xuất.
    """
    if job.waiting != 'preview':
        raise ValueError('Chỉ tạo lại giọng được khi job đang chờ xác nhận xuất video.')
    from_client = isinstance(scene, dict)
    if not from_client and (idx < 0 or idx >= len(job.scenes)):
        raise IndexError('Sai số thứ tự câu.')
    scene = dict(scene if from_client else job.scenes[idx])
    scene['voiceover'] = text
    if scene.get('subtitle') in (None, '') or job.config.get('mode') == 'review':
        scene['subtitle'] = text
    out_dir = os.path.join(job.temp_dir, 'audio', f'regen_{uuid.uuid4().hex[:6]}')
    rendered = synthesize([scene], voice_in_use(job), out_dir, job.log, strict=job.config.get('strict_voice', False))
    if not rendered or not rendered[0].get('tts_path'):
        raise RuntimeError('Không tạo được giọng cho câu này.')
    new = _clean_scene({**scene, **rendered[0]})
    if not from_client:
        job.scenes[idx] = new
        job.save()
    return new


# ═════════════════════════════════════════════════════════════════ srt only
def run_srt_pipeline(job):
    cfg = job.config
    out_dir = _out_dir(cfg)
    layout = _layout(cfg)
    with _workspace(job, out_dir) as temp_dir:
        video_path = _resolve_video(job, cfg['inp'], temp_dir)
        (transcript, lang) = _transcribe(job, video_path, temp_dir, cfg, beam=5)
        base = _base_name(video_path)
        cues = _rechunk(segments_to_cues(transcript['segments']), layout)
        job.result['original_srt'] = _write_srt(os.path.join(out_dir, base + '_original.srt'), cues)
        job.result['video_path'] = '' if _is_url(cfg['inp']) else video_path
        job.log(f"   SRT gốc: {job.result['original_srt']} ({len(cues)} dòng)", 'ok')
        job.check()
        if cfg.get('translate') and lang != 'vi':
            job.set_progress(60, 'Dịch sang tiếng Việt')
            scenes = _translate(job, transcript['segments'], lang, cfg, video_path)
            if scenes:
                cues = _rechunk(scenes_to_cues(scenes, 'subtitle'), layout)
                job.result['vi_srt'] = _write_srt(os.path.join(out_dir, base + '_vi.srt'), cues)
                job.log(f"   SRT tiếng Việt: {job.result['vi_srt']}", 'ok')
        job.scenes = [{'clip_start': c['start'], 'clip_end': c['end'], 'voiceover': c['text'], 'subtitle': c['text']} for c in cues]


# ═════════════════════════════════════════════════════════════════ burn subtitles
def _ass_color(spec, default_alpha=1.0):
    """'white' | '#ffd400' | 'black@0.5' → &HAABBGGRR (ASS)."""
    names = {'white': 'ffffff', 'black': '000000', 'yellow': 'ffff00', 'red': 'ff0000'}
    spec = (spec or 'white').strip()
    alpha = default_alpha
    if '@' in spec:
        (spec, a) = spec.split('@', 1)
        try:
            alpha = float(a)
        except ValueError:
            pass
    hexv = names.get(spec.lower(), spec.lstrip('#'))
    if len(hexv) != 6:
        hexv = 'ffffff'
    (r, g, b) = (hexv[0:2], hexv[2:4], hexv[4:6])
    aa = format(int(round((1 - alpha) * 255)), '02X')
    return f'&H{aa}{b}{g}{r}'.upper()


def _force_style(style):
    """Preset phụ đề của app → chuỗi force_style ASS cho filter subtitles= của ffmpeg."""
    box = bool(style.get('sub_box_enabled'))
    outline = (max(1, int(style.get('sub_box_padding', 12)) // 6) if box
               else int(style.get('sub_border_width', 3)) // 2 + 1)
    return ','.join([
        f"FontName={style.get('sub_font_name', 'Arial')}",
        f"FontSize={round(16 * float(style.get('sub_font_size_factor', 1.0)))}",
        f"PrimaryColour={_ass_color(style.get('sub_font_color'))}",
        f"OutlineColour={_ass_color(style.get('sub_box_color'), 0.5) if box else _ass_color('black')}",
        f"BackColour={_ass_color(style.get('sub_box_color'), 0.5)}",
        f'BorderStyle={3 if box else 1}', f'Outline={outline}',
        'Shadow=0', 'Bold=1', 'Alignment=2',
        f"MarginV={int(float(style.get('sub_margin_v_pct', 0.06)) * 288)}",
    ])


def run_download_pipeline(job):
    """Tải nhiều video từ link (YouTube, TikTok, Douyin, Bilibili, Kuaishou, Tiểu Hồng Thư…) — lần lượt, có tiến độ."""
    from core.downloader import detect_platform, download, normalize
    cfg = job.config
    urls = [normalize(u) for u in cfg.get('urls') or [] if u.strip()]
    out_dir = cfg.get('out_dir') or os.path.join(load_settings()['output_dir'], 'Downloads')
    os.makedirs(out_dir, exist_ok=True)
    items = [{'url': u, 'platform': detect_platform(u)[1]} for u in urls]
    job.result['items'] = items
    job.result['out_dir'] = out_dir
    n = len(urls)
    for (i, it) in enumerate(items):
        job.check()
        job.log(f"[{i + 1}/{n}] Tải {it['platform']}...", 'info')

        def prog(pct, size, speed, eta, i=i):
            job.progress = int((i + pct / 100) / n * 100)
            job.stage = f'Đang tải {i + 1}/{n} · {pct:.0f}%' + (f' · {size}' if size else '') + (f' · {speed}' if speed else '')
            job.save(throttle=True)

        try:
            path = download(it['url'], out_dir, job.log, cfg.get('quality', 'best'), prog, should_stop=lambda: job.cancelled,
                            title=(cfg.get('titles') or {}).get(it['url'], ''))
            it.update(path=path, size=os.path.getsize(path))
            job.log(f'   [OK] {os.path.basename(path)} ({os.path.getsize(path) / 1_048_576:.1f} MB)', 'ok')
        except RuntimeError as e:
            job.check()
            it['error'] = str(e)
            job.log(f'   [LỖI] {e}', 'err')
        job.save()
    ok = sum(1 for it in items if it.get('path'))
    if not ok:
        raise RuntimeError(items[0].get('error') if n == 1 else f'Không tải được video nào ({n} link) — xem chi tiết từng link.')
    job.result['output_path'] = next(it['path'] for it in items if it.get('path'))
    job.log(f'[XONG] Tải được {ok}/{n} video → {out_dir}', 'ok')


def _audio_codec(path):
    """Codec âm thanh của file — AAC/MP3 chép thẳng vào .mp4 được; WMA/PCM/Vorbis phải mã hoá lại."""
    from core.utils import FFPROBE_EXE
    try:
        r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_name',
                            '-of', 'default=nw=1:nk=1', path], capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return r.stdout.strip().lower()
    except Exception:
        return ''


def run_burn_pipeline(job):
    from core.utils import FFMPEG_EXE, get_video_duration, run_subprocess
    cfg = job.config
    video = validate_input(cfg['inp'])
    srt = cfg.get('srt_path', '')
    if not os.path.isfile(srt):
        raise ValueError('Không tìm thấy file SRT.')
    out_dir = _out_dir(cfg)
    with _workspace(job, out_dir) as temp_dir:
        style = _sub_style(cfg)
        with open(srt, 'r', encoding='utf-8-sig', errors='replace') as f:
            cues = parse_srt(f.read())
        if not cues:
            raise ValueError('File SRT rỗng hoặc sai định dạng.')
        if style.get('sub_text_transform') == 'uppercase':
            cues = [{**c, 'text': c['text'].upper()} for c in cues]
        cues = _rechunk(cues, _layout(cfg))
        _write_srt(os.path.join(temp_dir, 'subs.srt'), cues)
        # Font người dùng thêm (<data>/fonts) không nằm trong Windows Fonts → chép cạnh file sub, trỏ fontsdir tương đối
        from core.fonts import custom_font_files
        fonts_tmp = os.path.join(temp_dir, 'fonts')
        os.makedirs(fonts_tmp, exist_ok=True)
        for fp in custom_font_files():
            shutil.copy2(fp, fonts_tmp)
        out_path = _unique_path(os.path.join(out_dir, _base_name(video) + '_sub.mp4'))
        job.set_progress(15, 'Ghép phụ đề (ffmpeg)')
        job.log(f'[1] Ghép {len(cues)} dòng phụ đề vào video...', 'info')
        # cwd=temp_dir + đường dẫn tương đối: filter subtitles= của ffmpeg không chịu ký tự ':' của ổ Windows.
        cmd = [FFMPEG_EXE, '-y', '-i', video, '-vf', f"subtitles=subs.srt:fontsdir=fonts:force_style='{_force_style(style)}'",
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
               *(['-c:a', 'copy'] if _audio_codec(video) in ('aac', 'mp3') else ['-c:a', 'aac', '-b:a', '192k']), out_path]
        dur = get_video_duration(video)
        r = run_subprocess(cmd, timeout=max(600, int(dur * 6)) if dur > 0 else None, cwd=temp_dir,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        job.check()
        if r is None or r.returncode != 0 or not os.path.isfile(out_path):
            raise RuntimeError(f"ffmpeg ghép phụ đề lỗi: {(getattr(r, 'stderr', '') or '')[-600:]}")
        job.result['output_path'] = out_path
        job.log(f'[OK] Video: {out_path}', 'ok')
