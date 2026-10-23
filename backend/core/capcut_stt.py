"""Nhận dạng giọng nói bằng CapCut (online) — thay Whisper: nhanh (~10s / tập phim ngắn), không cần GPU, tiếng Trung rất chuẩn.

Dùng SDK capcut_tts_api (github.com/K07VN/capcut-tts-api): upload audio lên kho VOD của CapCut → task "nhận dạng phụ đề"
→ câu + thời gian từng chữ. Không cần cookie (mã thiết bị ẩn danh). CapCut KHÔNG tự nhận ngôn ngữ (để trống = coi là
tiếng Anh, câu bị cắt nát) → "Tự động" hiểu là tiếng Trung. Phần dịch của CapCut là dịch máy từng câu, không dùng —
khâu dịch vẫn do core/translator.py (AI có ngữ cảnh phim).
"""
import os
import subprocess
import time
from types import SimpleNamespace

from core.utils import FFMPEG_EXE, _HIDE

MODEL = 'capcut'                   # tên "model" trong danh sách Whisper model của app
LANGS = {'auto': 'zh-CN', 'zh': 'zh-CN', 'en': 'en-US', 'ja': 'ja-JP', 'ko': 'ko-KR', 'vi': 'vi-VN'}
_CJK = ('zh', 'ja')


class CapcutSttError(RuntimeError):
    pass


def _client():
    from capcut_tts_api import CapCutClient
    c = CapCutClient(timeout=60)
    # CAPCUT_COOKIE của app là cookie web cho giọng đọc (khác máy chủ) — gửi kèm sang API ứng dụng chỉ gây lỗi
    for k in ('Cookie', 'Authorization'):
        c.extra_headers.pop(k, None)
    return c


def _to_mp3(audio_path, temp_dir):
    """WAV 16kHz → MP3 mono 48kbps: file upload nhỏ ~10 lần, CapCut nhận dạng như nhau."""
    out = os.path.join(temp_dir, 'audio_capcut.mp3')
    r = subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-i', audio_path, '-vn', '-ac', '1', '-ar', '16000', '-b:a', '48k', out],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
    if r.returncode != 0 or not os.path.isfile(out):
        raise CapcutSttError(f'không chuyển được audio sang mp3: {(r.stderr or "").strip()[-200:]}')
    return out


def _recognize(mp3, lang, log_fn, should_stop=None, translate_to=None):
    """MP3 → SubtitleResult của SDK (None nếu bị huỷ). translate_to='vi-VN' → kèm bản dịch máy từng câu."""
    from capcut_tts_api import CapCutError
    try:
        c = _client()
        log_fn(f'   Tải audio lên CapCut ({os.path.getsize(mp3) / 1048576:.1f} MB)...')
        up = c.upload_audio(mp3)
        created = c.create_stt_task(up.vid, up.md5, up.duration_ms or 10000, language=lang,
                                    translation_language=translate_to or 'vi-VN', use_translation=bool(translate_to))
        task = ((created.get('data') or {}).get('tasks') or [{}])[0]
        if not task.get('id'):
            raise CapcutSttError(f'CapCut không tạo được task: {str(created)[:200]}')
        bind = task.get('bind_id') or (created.get('data') or {}).get('bind_id') or ''
        log_fn(f'   CapCut đang nhận dạng ({lang}, {(up.duration_ms or 0) / 60000:.1f} phút audio)...')
        deadline = time.time() + max(180, (up.duration_ms or 0) / 1000 * 1.5)
        while True:
            if should_stop and should_stop():
                return None
            res = c.query_stt_task(task['id'], task['token'], bind)
            status = str((((res.get('data') or {}).get('tasks') or [{}])[0]).get('status') or '').lower()
            if status in ('success', 'succeed', 'succeeded', 'completed', 'done'):
                break
            if status in ('failed', 'failure', 'error'):
                raise CapcutSttError('CapCut báo nhận dạng lỗi')
            if time.time() > deadline:
                raise CapcutSttError('CapCut nhận dạng quá lâu (hết thời gian chờ)')
            time.sleep(2)
        return c.extract_subtitles(res)
    except CapCutError as e:
        raise CapcutSttError(str(e)[:300])
    except (OSError, ValueError, KeyError) as e:
        raise CapcutSttError(f'{type(e).__name__}: {str(e)[:250]}')


def transcribe(audio_path, temp_dir, language='auto', log_fn=print, should_stop=None, word_timestamps=False):
    """Audio → {'language', 'segments': [{start, end, text}], 'full_text'} như Whisper. Lỗi → CapcutSttError."""
    lang = LANGS.get(language, 'zh-CN')
    if language == 'auto':
        log_fn('   CapCut không tự nhận ngôn ngữ → nhận dạng tiếng Trung (chọn ngôn ngữ gốc nếu phim nói tiếng khác)')
    subs = _recognize(_to_mp3(audio_path, temp_dir), lang, log_fn, should_stop)
    if subs is None:
        return None
    sep = '' if language in _CJK or language == 'auto' else ' '
    segments = []
    for u in subs.utterances:
        text = (u.text or '').strip()
        if not text:
            continue
        words = [SimpleNamespace(word=(sep if i else '') + w.text, start=w.start_time / 1000, end=w.end_time / 1000)
                 for (i, w) in enumerate(u.words) if w.text]
        if word_timestamps and words:
            # như Whisper word_timestamps: đầu / cuối câu bám đúng chữ, tách ở chỗ ngừng nói
            from core.transcriber import _split_by_words
            segments += _split_by_words(words)
        else:
            segments.append({'start': u.start_time / 1000, 'end': max(u.end_time, u.start_time + 200) / 1000, 'text': text})
    log_fn(f'   CapCut nhận dạng {len(segments)} đoạn thoại')
    return {'language': lang.split('-')[0], 'segments': segments, 'full_text': ' '.join(s['text'] for s in segments)}


def make_srt(video_path, language='zh', translate=True, log_fn=print, should_stop=None):
    """Video → '<tên>.<ngôn ngữ gốc>.srt' (+ '<tên>.vi.srt' dịch máy của CapCut). Đã có thì bỏ qua. Trả các file đã có."""
    import tempfile
    lang = LANGS.get(language, 'zh-CN')
    translate = translate and not lang.startswith('vi')
    stem = os.path.splitext(video_path)[0]
    src, vi = f"{stem}.{lang.split('-')[0]}.srt", f'{stem}.vi.srt'
    want = [src] + ([vi] if translate else [])
    if all(os.path.isfile(p) for p in want):
        return want
    with tempfile.TemporaryDirectory() as tmp:
        subs = _recognize(_to_mp3(video_path, tmp), lang, log_fn, should_stop, 'vi-VN' if translate else None)
    if not subs or not subs.utterances:
        return []
    out = [str(subs.write_srt(src))]
    if translate and any(u.translation_text for u in subs.utterances):
        out.append(str(subs.write_srt(vi, use_translation=True)))
    return out
