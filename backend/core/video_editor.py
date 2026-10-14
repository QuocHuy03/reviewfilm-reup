
"""
Video editor: cat clip tu video goc theo timestamp script, ghep voiceover, burn sub.
Output: 1 video review hoan chinh.
"""
import hashlib
import json
import os
import functools
import subprocess
import shutil
import sys
import numpy as np
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.utils import FFMPEG_EXE, FFPROBE_EXE, get_video_duration, _HIDE, run_subprocess, run_subprocess_heartbeat
def _resolve_subtitle_text(scene, source_mode='prefer_voiceover'):
    subtitle = ((scene.get('subtitle', '') or '')).strip()
    voiceover = ((scene.get('voiceover', '') or '')).strip()
    if source_mode == 'subtitle':
        return subtitle or voiceover
    if source_mode == 'prefer_subtitle':
        return subtitle or voiceover
    if source_mode == 'voiceover':
        return voiceover or subtitle
    return voiceover or subtitle
def _generate_srt_file(scenes, srt_path, sub_max_chars_per_chunk=56, sub_max_lines=2, sub_source_mode='prefer_voiceover'):
    def format_time_srt(seconds):
        seconds = max(0.0, float(seconds))
        h = int(seconds // 3600)
        m = int(seconds % 3600 // 60)
        s = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        if ms >= 1000:
            ms = 999
        return f'''{h:02d}:{m:02d}:{s:02d},{ms:03d}'''
    with open(srt_path, 'w', encoding='utf-8') as f:
        srt_idx = 1
        for scene in scenes:
            text = _resolve_subtitle_text(scene, sub_source_mode)
            if not text:
                continue
            start_s = scene.get('out_start', scene['clip_start'])
            end_s = scene.get('out_end', scene['clip_end'])
            total_dur = max(0.01, end_s - start_s)
            chunks = _split_subtitle_chunks(text, sub_max_chars_per_chunk, sub_max_lines)
            if not chunks:
                continue
            total_chars = sum((len(c) for c in chunks)) or 1
            t_cursor = start_s
            for chunk in chunks:
                chunk_dur = total_dur * (len(chunk) / total_chars)
                chunk_end = min(end_s, t_cursor + chunk_dur)
                wrapped = _wrap_text(chunk, max_len=max(18, int(max(24, sub_max_chars_per_chunk) / max(1, sub_max_lines))))
                f.write(f'''{srt_idx}\n''')
                f.write(f'''{format_time_srt(t_cursor)} --> {format_time_srt(chunk_end)}\n''')
                f.write(f'''{wrapped}\n\n''')
                srt_idx += 1
                t_cursor = chunk_end
def _create_silent_wav(path, duration, sr=44100):
    num_samples = int(duration * sr)
    data = np.zeros(num_samples, dtype=np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
def _escape_ffmpeg_path(path):
    p = path.replace('\\', '/')
    p = p.replace(':', '\\:')
    p = p.replace("'", "'\\\\''")
    return p
def _move_into(src, dst):
    """File cuối nằm trong thư mục tạm cùng ổ với thư mục xuất → chuyển (tức thì, không tốn gấp đôi ổ đĩa); khác ổ thì chép."""
    try:
        os.replace(src, dst)
    except OSError:
        shutil.copy2(src, dst)


@functools.lru_cache(maxsize=64)   # gọi cho từng cảnh — cùng 1 file nguồn chỉ ffprobe 1 lần
def _has_audio(video_path):
    cmd = [FFPROBE_EXE, '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=codec_type', '-of', 'default=nw=1:nk=1', video_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10, creationflags=_HIDE)
        return 'audio' in r.stdout.lower()
    except Exception:
        return False
def _stretch_audio_to_duration(src, target_dur, out):
    try:
        r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', src], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10, creationflags=_HIDE)
        src_dur = float(r.stdout.strip())
    except Exception:
        src_dur = 0.0
    if src_dur <= 0.1 or target_dur <= 0.1:
        return False
    if src_dur <= target_dur:
        return False
    ratio = src_dur / target_dur
    if ratio > 1.18:
        ratio = 1.18
    if ratio <= 1.02:
        return False
    atempo = f'''atempo={ratio:.4f}'''
    cmd = [FFMPEG_EXE, '-y', '-i', src, '-filter:a', atempo, '-ac', '1', '-ar', '44100', '-acodec', 'pcm_s16le', out]
    r2 = subprocess.run(cmd, capture_output=True, creationflags=_HIDE)
    return r2.returncode == 0 and os.path.getsize(out) > 0
_NVENC_AVAILABLE = None
def _check_nvenc():
    global _NVENC_AVAILABLE
    if _NVENC_AVAILABLE is not None:
        return _NVENC_AVAILABLE
    try:
        r = subprocess.run([FFMPEG_EXE, '-hide_banner', '-encoders'], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE, timeout=10)
        _NVENC_AVAILABLE = 'h264_nvenc' in r.stdout
        if _NVENC_AVAILABLE:
            # Encoder co the duoc liet ke nhung driver qua cu -> thu encode 1 frame that
            t = subprocess.run([FFMPEG_EXE, '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=256x256:d=0.1', '-frames:v', '1', '-c:v', 'h264_nvenc', '-f', 'null', '-'], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE, timeout=20)
            _NVENC_AVAILABLE = t.returncode == 0
    except Exception:
        _NVENC_AVAILABLE = False
    return _NVENC_AVAILABLE
def _video_encode_args(use_nvenc):
    if use_nvenc:
        return ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '24', '-pix_fmt', 'yuv420p']
    return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p']
def _find_font():
    tool_dir = os.path.dirname(os.path.abspath(__file__))
    cache_font = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'AutoReviewStudio', 'cache', 'fonts', 'DejaVuSans.ttf')
    candidates = ['C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/Segoeui.ttf', 'C:/Windows/Fonts/Arial.ttf', 'C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialuni.ttf', 'C:/Windows/Fonts/DejaVuSans.ttf', os.path.join(tool_dir, 'DejaVuSans.ttf').replace('\\', '/'), cache_font.replace('\\', '/')]
    for p in candidates:
        if os.path.exists(p):
            return p
    try:
        os.makedirs(os.path.dirname(cache_font), exist_ok=True)
        import urllib.request
        url = 'https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf'
        urllib.request.urlretrieve(url, cache_font)
        if os.path.exists(cache_font):
            if os.path.getsize(cache_font) > 100000:
                return cache_font.replace('\\', '/')
    except Exception:
        pass
    return None
def _find_system_font(font_name='Segoe UI'):
    font_name_lower = font_name.lower()
    font_map = {'segoe ui': ['C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/Segoeui.ttf'], 'arial': ['C:/Windows/Fonts/Arial.ttf', 'C:/Windows/Fonts/arial.ttf'], 'times new roman': ['C:/Windows/Fonts/times.ttf', 'C:/Windows/Fonts/timesbd.ttf'], 'tahoma': ['C:/Windows/Fonts/tahoma.ttf'], 'verdana': ['C:/Windows/Fonts/verdana.ttf'], 'impact': ['C:/Windows/Fonts/impact.ttf'], 'comic sans': ['C:/Windows/Fonts/comic.ttf', 'C:/Windows/Fonts/comicbd.ttf'], 'montserrat': ['C:/Windows/Fonts/Montserrat-Regular.ttf', 'C:/Windows/Fonts/montserrat.ttf'], 'roboto': ['C:/Windows/Fonts/Roboto-Regular.ttf', 'C:/Windows/Fonts/roboto.ttf']}
    candidates = font_map.get(font_name_lower, [])
    for p in candidates:
        if os.path.exists(p):
            return p
    direct_path = f'''C:/Windows/Fonts/{font_name}.ttf'''
    if os.path.exists(direct_path):
        return direct_path.replace('\\', '/')
    direct_path_lower = f'''C:/Windows/Fonts/{font_name_lower}.ttf'''
    if os.path.exists(direct_path_lower):
        return direct_path_lower.replace('\\', '/')
    try:
        from core.fonts import find_font_file
        found = find_font_file(font_name)
        if found:
            return found.replace('\\', '/')
    except Exception:
        pass
    return _find_font()
def _standardize_clip(src_path, target_path, resolution, fps, log_fn):
    (w, h) = resolution.split('x')
    use_nvenc = _check_nvenc()
    enc = _video_encode_args(use_nvenc)
    vf = f'''scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps}'''
    probe_cmd = [FFPROBE_EXE, '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', src_path]
    try:
        probe_r = subprocess.run(probe_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE, timeout=10)
        has_audio_track = bool(probe_r.stdout.strip())
    except Exception:
        has_audio_track = True
    if has_audio_track:
        cmd = [FFMPEG_EXE, '-y', '-i', src_path, '-vf', vf, *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), target_path]
    else:
        cmd = [FFMPEG_EXE, '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-i', src_path, '-vf', vf, '-map', '1:v', '-map', '0:a', *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), '-shortest', target_path]
    r = run_subprocess(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    if r.returncode == 0:
        if os.path.exists(target_path):
            if os.path.getsize(target_path) > 0:
                return True
    log_fn('   [Branding] NVENC fallback CPU encode cho clip standardize...')
    cpu_enc = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p']
    if has_audio_track:
        cmd_fb = [FFMPEG_EXE, '-y', '-i', src_path, '-vf', vf, *cpu_enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), target_path]
    else:
        cmd_fb = [FFMPEG_EXE, '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-i', src_path, '-vf', vf, '-map', '1:v', '-map', '0:a', *cpu_enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), '-shortest', target_path]
    r2 = subprocess.run(cmd_fb, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
    if r2.returncode != 0:
        log_fn(f'''   [WARN] _standardize_clip that bai: {r2.stderr[slice(-300, None, None)]}''')
    return r2.returncode == 0 and os.path.getsize(target_path) > 0
def recap_length_report(scenes, output_duration_sec):
    n = len(scenes or [])
    total_tts = 0.0
    total_tile = 0.0
    total_words = 0
    for s in scenes or []:
        try:
            total_tts += float(s.get('tts_duration') or 0.0)
        except Exception:
            pass
        try:
            total_tile += max(0.0, float(s.get('clip_end') or 0.0) - float(s.get('clip_start') or 0.0))
        except Exception:
            pass
        try:
            total_words += len(str(s.get('voiceover') or '').split())
        except Exception:
            pass
    try:
        out_dur = max(0.0, float(output_duration_sec or 0.0))
    except Exception:
        out_dur = 0.0
    implied_wpm = total_words / (total_tts / 60.0) if total_tts > 0 else 0.0
    return {'n_scenes': n, 'total_tts_sec': total_tts, 'total_tile_sec': total_tile, 'output_sec': out_dur, 'total_words': total_words, 'implied_tts_wpm': implied_wpm}
def _safe_duration(path):
    try:
        return float(get_video_duration(path) or 0.0)
    except Exception:
        return 0.0
def build_review_video(scenes, source_video, output_path, temp_dir, target_resolution='1920x1080', fps=30, original_volume=0.08, burn_subtitles=True, bgm_path='', bgm_volume=0.05, log_fn=print, is_reup=False, remove_old_sub=False, sub_cover_height=18, mirror_video=False, speed_up_video=False, video_speed=1.0, audio_ducking=True, watermark_path='', intro_path='', outro_path='', ai_sub_box=None, ai_logo_box=None, remove_old_logo=False, manual_logo_corner='Trên-Phải', manual_logo_size=15, watermark_corner='Trên-Phải', watermark_size_pct=14, watermark_margin_x_pct=2.0, watermark_margin_y_pct=2.0, watermark_opacity=0.92, blur_boxes=None, music_clips=None, mute_music=False, mute_sfx=False, **kwargs):
    if not scenes:
        log_fn('   [LOI] Khong co canh nao de dung video')
        return
    if is_reup:
        log_fn('   [Reup Mode] Tien hanh phan tich va cat ghep video theo phuong an B (co gian video)...')
        video_dur = _safe_duration(source_video)
        has_audio = _has_audio(source_video)
        continuous_scenes = []
        sorted_scenes = sorted(scenes, key=lambda x: x['clip_start'])
        last_end = sorted_scenes[0]['clip_start'] if sorted_scenes else 0.0
        accumulated_time = 0.0
        for (idx, s) in enumerate(sorted_scenes):
            start = s['clip_start']
            end = s['clip_end']
            if start > last_end + 0.05:
                gap_dur = start - last_end
                gap_silent_wav = os.path.join(temp_dir, f'''silent_gap_{idx}.wav''')
                _create_silent_wav(gap_silent_wav, gap_dur)
                continuous_scenes.append({'is_reup': True, 'clip_start': last_end, 'clip_end': start, 'voiceover': '', 'subtitle': '', 'tts_path': gap_silent_wav, 'tts_duration': gap_dur, 'orig_volume': 1.0 if original_volume > 0.001 else 0.0, 'has_audio': has_audio, 'out_start': accumulated_time, 'out_end': accumulated_time + gap_dur})
                accumulated_time += gap_dur
            tts_path = s.get('tts_path')
            tts_dur = s.get('tts_duration', end - start)
            if not tts_path or not os.path.exists(tts_path):
                fallback_wav = os.path.join(temp_dir, f'''silent_fail_{idx}.wav''')
                _create_silent_wav(fallback_wav, end - start)
                tts_path = fallback_wav
                tts_dur = end - start
            clip_dur_orig = max(0.05, end - start)
            _pr = max(0.4, min(2.5, tts_dur / clip_dur_orig)) if tts_dur > 0.05 else 1.0
            real_dur = clip_dur_orig * _pr
            continuous_scenes.append({'is_reup': True, 'clip_start': start, 'clip_end': end, 'voiceover': s.get('voiceover', ''), 'subtitle': s.get('subtitle', s.get('voiceover', '')), 'tts_path': tts_path, 'tts_duration': tts_dur, 'orig_volume': original_volume, 'has_audio': has_audio, 'out_start': accumulated_time, 'out_end': accumulated_time + real_dur})
            accumulated_time += real_dur
            last_end = end
        if video_dur > last_end + 0.05:
            gap_dur = video_dur - last_end
            gap_silent_wav = os.path.join(temp_dir, 'silent_end.wav')
            _create_silent_wav(gap_silent_wav, gap_dur)
            continuous_scenes.append({'is_reup': True, 'clip_start': last_end, 'clip_end': video_dur, 'voiceover': '', 'subtitle': '', 'tts_path': gap_silent_wav, 'tts_duration': gap_dur, 'orig_volume': 1.0 if original_volume > 0.001 else 0.0, 'has_audio': has_audio, 'out_start': accumulated_time, 'out_end': accumulated_time + gap_dur})
            accumulated_time += gap_dur
        scenes = continuous_scenes
    else:
        _SRT_TAIL = 0.12
        video_dur_srt = _safe_duration(source_video)
        accumulated_time = 0.0
        for (idx, s) in enumerate(scenes):
            tts_path = s.get('tts_path')
            if not tts_path or not os.path.exists(tts_path):
                fallback_wav = os.path.join(temp_dir, f'''silent_fail_{idx}.wav''')
                _create_silent_wav(fallback_wav, s['clip_end'] - s['clip_start'])
                s['tts_path'] = fallback_wav
                s['tts_duration'] = s['clip_end'] - s['clip_start']
            tts_dur = s.get('tts_duration', s['clip_end'] - s['clip_start'])
            if video_dur_srt > 0:
                max_available = max(0.5, video_dur_srt - s['clip_start'])
                real_clip_dur = max(tts_dur, min(tts_dur + _SRT_TAIL, max_available))
            else:
                real_clip_dur = tts_dur + _SRT_TAIL
            s['out_start'] = accumulated_time
            s['out_end'] = accumulated_time + tts_dur
            accumulated_time += real_clip_dur
    final_srt_path = os.path.splitext(output_path)[0] + '.srt'
    should_stop = kwargs.pop('should_stop', None)        # callable → True khi job bị huỷ
    sub_source_mode = kwargs.get('sub_source_mode', 'prefer_voiceover')
    try:
        speech_scenes = [s for s in scenes if _resolve_subtitle_text(s, sub_source_mode)]
        _generate_srt_file(speech_scenes, final_srt_path, sub_max_chars_per_chunk=kwargs.get('sub_max_chars_per_chunk', 56), sub_max_lines=kwargs.get('sub_max_lines', 2), sub_source_mode=sub_source_mode)
        log_fn(f'''   Da tao file phu de SRT dong bo: {final_srt_path}''')
    except Exception as e:
        log_fn(f'''   [WARN] Loi tao file phu de SRT: {e}''')
    use_nvenc = _check_nvenc()
    if use_nvenc:
        log_fn('   GPU NVIDIA NVENC phat hien — encode bang GPU (nhanh 5-10x)')
    else:
        log_fn('   Encode bang CPU x264 (cai NVIDIA GPU de nhanh hon)')
    clips_dir = os.path.join(temp_dir, 'clips')
    os.makedirs(clips_dir, exist_ok=True)
    sub_font_name = kwargs.get('sub_font_name', 'Segoe UI')
    sub_custom_font_path = kwargs.get('sub_custom_font_path', '')
    if sub_custom_font_path and os.path.exists(sub_custom_font_path):
        font_path = sub_custom_font_path.replace('\\', '/')
    else:
        font_path = _find_system_font(sub_font_name)
    video_total_duration = _safe_duration(source_video)
    workers = max(1, min(4, (os.cpu_count() or 2) // 2))
    if kwargs.get('low_memory_mode'):
        workers = 1
    if use_nvenc:
        workers = min(workers, 3)
    # Dấu vân tay mỗi clip = nội dung cảnh + mọi tuỳ chọn dựng → cảnh không đổi thì dùng lại clip đã dựng
    # (tự sửa / hậu kỳ lại chỉ dựng lại cảnh thay đổi; đổi thứ tự cảnh cũng không phải dựng lại).
    _render_opts = json.dumps({'src': [source_video, os.path.getsize(source_video) if os.path.isfile(source_video) else 0],
                               'res': target_resolution, 'fps': fps, 'vol': original_volume, 'burn': burn_subtitles, 'font': font_path,
                               'nvenc': use_nvenc, 'rm_sub': remove_old_sub, 'cover_h': sub_cover_height, 'wm': watermark_path,
                               'ai_sub': ai_sub_box, 'ai_logo': ai_logo_box, 'rm_logo': remove_old_logo, 'logo': [manual_logo_corner, manual_logo_size],
                               'wm_pos': [watermark_corner, watermark_size_pct, watermark_margin_x_pct, watermark_margin_y_pct, watermark_opacity],
                               'blur': blur_boxes, 'kw': kwargs}, sort_keys=True, default=str)

    def _clip_path(i, scene):
        sc = {k: v for (k, v) in scene.items() if not str(k).startswith('_')}
        sig = hashlib.md5(json.dumps([sc, _render_opts, bool(mirror_video) and i % 2 == 0], sort_keys=True, default=str).encode()).hexdigest()[:20]
        return os.path.join(clips_dir, f'clip_{sig}.mp4')

    reused = [0]
    log_fn(f'''   Cat va xu ly {len(scenes)} clip (song song {workers} FFmpeg)...''')
    results = {}
    done_count = [0]
    def _render_one(args):
        (i, scene) = args
        clip_out = _clip_path(i, scene)
        if os.path.isfile(clip_out) and os.path.getsize(clip_out) > 1000:
            reused[0] += 1
            return (i, clip_out)
        if should_stop and should_stop():
            return (i, None)
        try:
            ok = _process_one_scene(source_video, scene, clip_out, target_resolution, fps, original_volume, burn_subtitles, log_fn, i, font_path, video_total_duration, use_nvenc=use_nvenc, remove_old_sub=remove_old_sub, sub_cover_height=sub_cover_height, mirror_video=bool(mirror_video) and i % 2 == 0, watermark_path=watermark_path, ai_sub_box=ai_sub_box, ai_logo_box=ai_logo_box, remove_old_logo=remove_old_logo, manual_logo_corner=manual_logo_corner, manual_logo_size=manual_logo_size, watermark_corner=watermark_corner, watermark_size_pct=watermark_size_pct, watermark_margin_x_pct=watermark_margin_x_pct, watermark_margin_y_pct=watermark_margin_y_pct, watermark_opacity=watermark_opacity, blur_boxes=blur_boxes, **kwargs)
        except Exception as e:
            log_fn(f'''   [LOI] Canh {i + 1} gap loi: {e}''')
            ok = False
        return (i, clip_out if ok else None)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_render_one, (i, s)): i for (i, s) in enumerate(scenes)}
        for future in as_completed(futures):
            (i, clip_path) = future.result()
            done_count[0] += 1
            if clip_path:
                results[i] = clip_path
            else:
                log_fn(f'''   [WARN] Bo qua canh {i + 1}''')
            n = done_count[0]
            if n % 5 == 0 or n == len(scenes):
                log_fn(f'''   Tien do cat clip: {n}/{len(scenes)}''')
    if should_stop and should_stop():
        log_fn('   [DỪNG] Đã huỷ khi đang dựng video.')
        return
    if reused[0]:
        log_fn(f'   Dùng lại {reused[0]}/{len(scenes)} clip đã dựng trước đó (cảnh không đổi) — chỉ dựng {len(scenes) - reused[0]} cảnh')
    final_clips = [results[k] for k in sorted(results)]
    if not final_clips:
        log_fn('   [LOI] Khong dung duoc clip nao')
        return
    if intro_path and os.path.exists(intro_path):
        intro_std = os.path.join(temp_dir, 'intro_std.mp4')
        log_fn('   [Branding] Đang đồng bộ hóa cấu hình Video Intro đầu kênh...')
        if _standardize_clip(intro_path, intro_std, target_resolution, fps, log_fn):
            final_clips.insert(0, intro_std)
            log_fn('   [Branding] Đã chèn Video Intro thành công.')
        else:
            log_fn('   [WARN] Đồng bộ Video Intro thất bại, bỏ qua.')
    if outro_path and os.path.exists(outro_path):
        outro_std = os.path.join(temp_dir, 'outro_std.mp4')
        log_fn('   [Branding] Đang đồng bộ hóa cấu hình Video Outro cuối kênh...')
        if _standardize_clip(outro_path, outro_std, target_resolution, fps, log_fn):
            final_clips.append(outro_std)
            log_fn('   [Branding] Đã chèn Video Outro thành công.')
        else:
            log_fn('   [WARN] Đồng bộ Video Outro thất bại, bỏ qua.')
    concat_output = os.path.join(temp_dir, 'concat_output.mp4')
    log_fn(f'''   Ghep {len(final_clips)} clip thanh video cuoi...''')
    ok = _concat_clips(final_clips, concat_output, temp_dir, log_fn)
    if not ok:
        log_fn('   [LOI] Ghép nối các phân cảnh video thất bại')
        return
    enc = _video_encode_args(use_nvenc)
    _final_speed = video_speed
    if speed_up_video and video_speed == 1.0:
        _final_speed = 1.03
    try:
        _final_speed = float(_final_speed)
    except (TypeError, ValueError):
        _final_speed = 1.0
    if _final_speed != 1.0:
        _final_speed = max(0.5, min(2.0, _final_speed))
        log_fn(f'''   Đang chỉnh tốc độ toàn bộ video lên {_final_speed:.2f}x...''')
        speed_output = os.path.join(temp_dir, 'speed_output.mp4')
        cmd_speed = [FFMPEG_EXE, '-y', '-i', concat_output, '-filter_complex', f'''[0:v]setpts={1.0 / _final_speed:.4f}*PTS[v];[0:a]atempo={_final_speed:.4f}[a]''', '-map', '[v]', '-map', '[a]', *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), speed_output]
        r_speed = run_subprocess_heartbeat(cmd_speed, log_fn=log_fn, label=f'''Đang chỉnh tốc độ video {_final_speed:.2f}x''', text=True, encoding='utf-8', errors='replace')
        if r_speed.returncode != 0 and use_nvenc:
            cmd_speed_cpu = [x for x in cmd_speed]
            _ei = cmd_speed_cpu.index(enc[0])
            cmd_speed_cpu[_ei:_ei + len(enc)] = _video_encode_args(False)
            r_speed = run_subprocess_heartbeat(cmd_speed_cpu, log_fn=log_fn, label=f'''Đang chỉnh tốc độ video {_final_speed:.2f}x (CPU)''', text=True, encoding='utf-8', errors='replace')
        if r_speed.returncode == 0 and os.path.exists(speed_output):
            concat_output = speed_output
            log_fn(f'''   Chỉnh tốc độ {_final_speed:.2f}x thành công!''')
        else:
            log_fn(f'''   [WARN] Chỉnh tốc độ video thất bại: {(r_speed.stderr or '')[-200:]}''')
    audio_src = concat_output
    if bgm_path and os.path.exists(bgm_path):
        log_fn('   Trộn nhạc nền (BGM)...')
        bgm_out = os.path.join(temp_dir, 'bgm_mixed.mp4')
        ok = _mix_bgm(audio_src, bgm_path, bgm_out, bgm_volume, log_fn, audio_ducking=audio_ducking)
        if ok:
            audio_src = bgm_out
        else:
            log_fn('   [WARN] Trộn BGM thất bại, bỏ qua BGM')
    if music_clips:
        log_fn(f'''   Trộn {len(music_clips)} đoạn Nhạc nền/SFX từ Timeline...''')
        ok2 = _mix_multi_audio(audio_src, music_clips, output_path, log_fn, mute_music=mute_music, mute_sfx=mute_sfx)
        if not ok2:
            log_fn('   [WARN] Trộn Nhạc/SFX từ Timeline thất bại (hoặc không còn đoạn nào dùng được sau khi lọc mute) — giữ nguyên audio trước đó')
            _move_into(audio_src, output_path)
    else:
        _move_into(audio_src, output_path)
    log_fn(f'''   Da xuat video: {output_path}''')
    try:
        _rep = recap_length_report(scenes, _safe_duration(output_path))
        log_fn(f'''   [ĐO ĐỘ DÀI] {_rep['n_scenes']} cảnh | giọng đọc {_rep['total_tts_sec'] / 60:.1f}′ | lát gạch nguồn {_rep['total_tile_sec'] / 60:.1f}′ | video xuất {_rep['output_sec'] / 60:.1f}′ | {_rep['total_words']} từ (~{_rep['implied_tts_wpm']:.0f} từ/phút thực).''')
    except Exception:
        pass
    return output_path
def _mix_bgm(video_in, bgm_path, video_out, bgm_volume, log_fn=print, audio_ducking=True):
    if audio_ducking:
        filter_str = f'''[1:a]volume={bgm_volume}[bgm];[bgm][0:a]sidechaincompress=threshold=-25dB:ratio=10:attack=100:release=400[bgm_ducked];[0:a][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=0[a]'''
    else:
        filter_str = f'''[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]'''
    cmd = [FFMPEG_EXE, '-y', '-i', video_in, '-stream_loop', '-1', '-i', bgm_path, '-filter_complex', filter_str, '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-shortest', video_out]
    r = run_subprocess_heartbeat(cmd, log_fn=log_fn, label='Trộn nhạc nền (BGM)', text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        log_fn(f'''   [WARN] Mix BGM loi: {r.stderr[slice(-300, None, None)]}''')
        return False
    return os.path.exists(video_out) and os.path.getsize(video_out) > 0
def _mix_multi_audio(video_in, clips, video_out, log_fn=print, mute_music=False, mute_sfx=False):
    def _clip_dur(c):
        try:
            return float(c.get('duration') or 0)
        except (TypeError, ValueError):
            return 0.0
    usable = [c for c in (clips or []) if c.get('source') and os.path.exists(c['source']) and _clip_dur(c) > 0 and not (c.get('track') == 'music' and mute_music) and not (c.get('track') == 'sfx' and mute_sfx)]
    if not usable:
        return False
    cmd = [FFMPEG_EXE, '-y', '-i', video_in]
    for c in usable:
        cmd += ['-i', c['source']]
    chains = []
    labels = []
    for (i, c) in enumerate(usable, start=1):
        dur = max(0.05, float(c.get('duration') or 0))
        vol_raw = c.get('volume')
        vol = max(0.0, float(vol_raw if vol_raw is not None else 1.0))
        start_ms = max(0, int(round(float(c.get('start', 0.0) or 0.0) * 1000)))
        chain = f'''[{i}:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={vol:.3f}'''
        fade_in = max(0.0, float(c.get('fadeIn', 0.0) or 0.0))
        fade_out = max(0.0, float(c.get('fadeOut', 0.0) or 0.0))
        if fade_in > 0:
            chain += f''',afade=t=in:st=0:d={min(fade_in, dur):.2f}'''
        if fade_out > 0:
            st = max(0.0, dur - fade_out)
            chain += f''',afade=t=out:st={st:.2f}:d={min(fade_out, dur):.2f}'''
        chain += f''',adelay={start_ms}|{start_ms}[a{i}]'''
        chains.append(chain)
        labels.append(f'''[a{i}]''')
    n_inputs = len(usable) + 1
    filter_str = ';'.join(chains) + f''';[0:a]{''.join(labels)}amix=inputs={n_inputs}:duration=first:dropout_transition=0[a]'''
    cmd += ['-filter_complex', filter_str, '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-shortest', video_out]
    r = run_subprocess_heartbeat(cmd, log_fn=log_fn, label=f'''Trộn {len(usable)} đoạn Nhạc/SFX''', text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        log_fn(f'''   [WARN] Mix nhieu am thanh loi: {r.stderr[slice(-300, None, None)]}''')
        return False
    return os.path.exists(video_out) and os.path.getsize(video_out) > 0
def _process_one_scene(source_video, scene, out_path, resolution, fps, original_volume, burn_subtitles, log_fn, i=0, font_path=None, video_total_duration=0, use_nvenc=False, remove_old_sub=False, sub_cover_height=18, mirror_video=False, watermark_path='', ai_sub_box=None, ai_logo_box=None, remove_old_logo=False, manual_logo_corner='Trên-Phải', manual_logo_size=15, watermark_corner='Trên-Phải', watermark_size_pct=14, watermark_margin_x_pct=2.0, watermark_margin_y_pct=2.0, watermark_opacity=0.92, blur_boxes=None, **kwargs):
    clip_start = scene['clip_start']
    clip_end = scene['clip_end']
    tts_duration = scene['tts_duration']
    _raw_tts_duration = tts_duration
    tts_path = scene['tts_path']
    subtitle = _resolve_subtitle_text(scene, kwargs.get('sub_source_mode', 'prefer_voiceover'))
    is_reup = scene.get('is_reup', False)
    if is_reup:
        clip_duration = max(0.05, clip_end - clip_start)
        if tts_duration <= 0.05:
            tts_duration = clip_duration
        if tts_duration > clip_duration:
            stretched_wav = out_path + '_stretched.wav'
            ok_stretch = _stretch_audio_to_duration(tts_path, clip_duration, stretched_wav)
            if ok_stretch:
                tts_path = stretched_wav
                ratio = tts_duration / clip_duration
                if ratio > 1.18:
                    tts_duration = tts_duration / 1.18
                else:
                    tts_duration = clip_duration
        pts_ratio = tts_duration / clip_duration
        pts_ratio = max(0.4, min(2.5, pts_ratio))
        tts_duration = clip_duration * pts_ratio
        sub_span_duration = min(_raw_tts_duration, tts_duration) if _raw_tts_duration > 0.1 else tts_duration
    else:
        if tts_duration <= 0.1:
            return False
        if video_total_duration > 0:
            max_available = max(0.5, video_total_duration - clip_start)
        else:
            max_available = tts_duration + 5
        TAIL = 0.12
        clip_duration = min(tts_duration + TAIL, max_available)
        if clip_duration < tts_duration:
            clip_duration = min(tts_duration, max_available)
        pts_ratio = 1.0
        sub_span_duration = clip_duration
    (w, h) = resolution.split('x')
    vf = f'''scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps}'''
    _v_scale = scene.get('_video_scale')
    _v_pos = str(scene.get('_video_position') or 'center').strip().lower()
    if _v_scale is not None:
        try:
            _v_scale = max(0.5, min(2.0, float(_v_scale)))
        except (TypeError, ValueError):
            _v_scale = 1.0
        if abs(_v_scale - 1.0) > 0.001:
            vf += f''',scale=iw*{_v_scale:.4f}:ih*{_v_scale:.4f}'''
            if _v_scale > 1.0:
                if _v_pos == 'top':
                    crop_y = '0'
                elif _v_pos == 'bottom':
                    crop_y = 'in_h-out_h'
                else:
                    crop_y = '(in_h-out_h)/2'
                vf += f''',crop={w}:{h}:(in_w-out_w)/2:{crop_y}'''
            else:
                if _v_pos == 'top':
                    pad_y = '0'
                elif _v_pos == 'bottom':
                    pad_y = 'oh-ih'
                else:
                    pad_y = '(oh-ih)/2'
                vf += f''',pad={w}:{h}:(ow-iw)/2:{pad_y}:color=black'''
    if pts_ratio != 1.0:
        vf += f''',setpts={pts_ratio:.4f}*PTS'''
    if mirror_video:
        vf += ',hflip'
    _extra_blur_boxes = []
    sub_cover_boxes = kwargs.get('sub_cover_boxes')
    if sub_cover_boxes is None:
        _legacy_box = kwargs.get('sub_cover_box')
        sub_cover_boxes = [_legacy_box] if _legacy_box else None
    if remove_old_sub and sub_cover_boxes:
        for box in sub_cover_boxes:
            if not box or len(box) != 4:
                continue
            try:
                (x_pct, y_pct, w_pct, h_pct) = [max(0, min(100, float(v))) / 100.0 for v in box]
            except (TypeError, ValueError):
                continue
            if w_pct > 0.01 and h_pct > 0.01:
                _extra_blur_boxes.append([x_pct, y_pct, x_pct + w_pct, y_pct + h_pct])
    elif remove_old_sub:
        pct = max(5, min(50, int(sub_cover_height))) / 100.0
        _extra_blur_boxes.append([0.0, 1.0 - pct, 1.0, 1.0])
    elif ai_sub_box:
        if len(ai_sub_box) == 2:
            (ymin, ymax) = ai_sub_box
            if ymax - ymin > 0.01:
                _extra_blur_boxes.append([0.0, ymin, 1.0, ymax])
    if remove_old_logo:
        size_pct = max(5, min(50, int(manual_logo_size))) / 100.0
        if manual_logo_corner == 'Trên-Trái':
            vf += f''',drawbox=x=0:y=0:w=iw*{size_pct:.4f}:h=ih*{size_pct:.4f}:color=black:t=fill'''
        elif manual_logo_corner == 'Trên-Phải':
            vf += f''',drawbox=x=iw-iw*{size_pct:.4f}:y=0:w=iw*{size_pct:.4f}:h=ih*{size_pct:.4f}:color=black:t=fill'''
        elif manual_logo_corner == 'Dưới-Trái':
            vf += f''',drawbox=x=0:y=ih-ih*{size_pct:.4f}:w=iw*{size_pct:.4f}:h=ih*{size_pct:.4f}:color=black:t=fill'''
        elif manual_logo_corner == 'Dưới-Phải':
            vf += f''',drawbox=x=iw-iw*{size_pct:.4f}:y=ih-ih*{size_pct:.4f}:w=iw*{size_pct:.4f}:h=ih*{size_pct:.4f}:color=black:t=fill'''
    elif ai_logo_box:
        if len(ai_logo_box) == 4:
            (ymin, xmin, ymax, xmax) = ai_logo_box
            w_pct = xmax - xmin
            h_pct = ymax - ymin
            if w_pct > 0.01:
                if h_pct > 0.01:
                    vf += f''',drawbox=x=iw*{xmin:.4f}:y=ih*{ymin:.4f}:w=iw*{w_pct:.4f}:h=ih*{h_pct:.4f}:color=black:t=fill'''
    vf += ',eq=brightness=0.02:saturation=1.06'
    vf += f''',crop=iw*0.97:ih*0.97,scale={w}:{h}'''
    if not is_reup:
        if clip_duration < tts_duration:
            pad_dur = tts_duration - clip_duration
            if pad_dur > 0.01:
                vf += f''',tpad=stop_mode=clone:stop_duration={pad_dur:.4f}'''
    has_audio = _has_audio(source_video)
    orig_vol = scene.get('orig_volume', original_volume)
    mute_orig = float(orig_vol) <= 0.001 or not has_audio
    atempo_filter = ''
    if is_reup and pts_ratio != 1.0 and not mute_orig:
        audio_speed = 1.0 / pts_ratio
        if audio_speed < 0.5:
            atempo_filter = f''',atempo=0.5,atempo={audio_speed / 0.5:.4f}'''
        elif audio_speed > 2.0:
            atempo_filter = f''',atempo=2.0,atempo={audio_speed / 2.0:.4f}'''
        else:
            atempo_filter = f''',atempo={audio_speed:.4f}'''
    subtitle_files = []
    sub_filters = []
    if burn_subtitles and subtitle and not font_path:
        log_fn('   [WARN] Khong tim thay font Unicode, bo qua burn subtitle canh nay')
        burn_subtitles = False
    if burn_subtitles and subtitle:
        if True:
            try:
                vid_h = int(h)
                vid_w = int(w)
            except Exception:
                (vid_h, vid_w) = (1080, 1920)
            sub_font_color = kwargs.get('sub_font_color', 'white')
            sub_font_size_factor = kwargs.get('sub_font_size_factor', 1.0)
            sub_border_width = kwargs.get('sub_border_width', 3)
            sub_border_color = kwargs.get('sub_border_color', 'black')
            sub_box_enabled = kwargs.get('sub_box_enabled', True)
            sub_box_color = kwargs.get('sub_box_color', 'black@0.5')
            sub_box_padding = kwargs.get('sub_box_padding', 12)
            sub_margin_v_pct = kwargs.get('sub_margin_v_pct', 0.06)
            sub_line_spacing = kwargs.get('sub_line_spacing', 6)
            sub_text_transform = kwargs.get('sub_text_transform', 'none')
            sub_position_mode = str(kwargs.get('sub_position_mode', 'bottom') or 'bottom').lower()
            sub_max_chars_per_chunk = kwargs.get('sub_max_chars_per_chunk', 56)
            sub_max_lines = kwargs.get('sub_max_lines', 2)
            sub_max_width_pct = max(0.3, min(0.95, float(kwargs.get('sub_max_width_pct', 0.82) or 0.82)))
            margin_v = max(20, int(vid_h * sub_margin_v_pct))
            _sub_dur = sub_span_duration if sub_span_duration is not None else clip_duration
            _manual_chunks = scene.get('_manual_sub_chunks')
            chunks_timed = []
            if _manual_chunks:
                _dur_timeline = max(clip_end - clip_start, _raw_tts_duration, 0.5)
                _scale = _sub_dur / _dur_timeline if _dur_timeline > _sub_dur + 0.01 else 1.0
                for c in _manual_chunks:
                    ctext = str(c.get('text', '')).strip()
                    if not ctext:
                        continue
                    cs = max(0.0, min(_sub_dur, float(c.get('t_start', 0.0) or 0.0) * _scale))
                    ce = max(0.0, min(_sub_dur, float(c.get('t_end', 0.0) or 0.0) * _scale))
                    if ce > cs:
                        chunks_timed.append((ctext, cs, ce, c.get('style')))
            if not chunks_timed:
                chunks = _split_subtitle_chunks(subtitle, sub_max_chars_per_chunk, sub_max_lines)
                if chunks:
                    total_chars = sum((len(c) for c in chunks)) or 1
                    t_cur = 0.0
                    for (ci, chunk) in enumerate(chunks):
                        chunk_dur = _sub_dur * (len(chunk) / total_chars)
                        t_end = _sub_dur if ci == len(chunks) - 1 else min(_sub_dur, t_cur + chunk_dur)
                        chunks_timed.append((chunk, t_cur, t_end, None))
                        t_cur = t_end
            sub_filters = []
            for (ci, (chunk, t_cur, t_end, c_style)) in enumerate(chunks_timed):
                c_style = c_style or {}
                eff_font_color = c_style.get('color') or sub_font_color
                eff_size_factor = float(c_style.get('fontSize') or sub_font_size_factor or 1.0)
                eff_position_mode = str(c_style.get('position') or sub_position_mode or 'bottom').lower()
                eff_box_enabled = c_style['backgroundEnabled'] if c_style.get('backgroundEnabled') is not None else sub_box_enabled
                eff_box_color = c_style.get('background') or sub_box_color
                eff_font_name = c_style.get('fontName') or ''
                if eff_font_name:
                    eff_font_path = _find_system_font(eff_font_name) or font_path
                else:
                    eff_font_path = font_path
                if eff_font_path:
                    eff_font_esc = eff_font_path.replace('\\', '/').replace(':', '\\:')
                    eff_font_str = f'''fontfile=\'{eff_font_esc}\':'''
                else:
                    eff_font_str = ''
                eff_box_str = f'''box=1:boxcolor={eff_box_color}:boxborderw={sub_box_padding}:''' if eff_box_enabled else ''
                (wrapped, fontsize) = _fit_subtitle(chunk.upper() if str(sub_text_transform).lower() == 'uppercase' else chunk, vid_w, vid_h, font_size_factor=eff_size_factor, max_lines=sub_max_lines, line_spacing=sub_line_spacing, max_width_pct=sub_max_width_pct)
                subtitle_file = f'''{out_path}.subtxt{ci}'''
                subtitle_files.append(subtitle_file)
                with open(subtitle_file, 'w', encoding='utf-8') as _sf:
                    _sf.write(wrapped)
                subtxt_esc = subtitle_file.replace('\\', '/').replace(':', '\\:')
                if eff_position_mode == 'top':
                    y_expr = f"{margin_v}"
                elif eff_position_mode == 'middle':
                    y_expr = '(h-text_h)/2'
                else:
                    y_expr = f'''h-text_h-{margin_v}'''
                clause = f'''drawtext={eff_font_str}textfile=\'{subtxt_esc}\':fontcolor={eff_font_color}:fontsize={fontsize}:borderw={sub_border_width}:bordercolor={sub_border_color}:line_spacing={sub_line_spacing}:x=(w-text_w)/2:y={y_expr}:{eff_box_str}enable=\'between(t\\,{t_cur:.3f}\\,{t_end:.3f})\''''
                sub_filters.append(clause)
    _all_blur_boxes = list(blur_boxes or []) + _extra_blur_boxes
    (blur_chain, blur_last) = _build_blur_chain('vbase', _all_blur_boxes, clip_start=clip_start, clip_end=clip_end)
    has_wm = bool(watermark_path and os.path.exists(watermark_path))
    fc = f'''[0:v]{vf}[vbase]'''
    last = 'vbase'
    if blur_chain:
        fc += ';' + blur_chain
        last = blur_last
    for (si, sub_filter) in enumerate(sub_filters):
        out_lbl = f'''vsub{si}'''
        fc += f'''; [{last}]{sub_filter}[{out_lbl}]'''
        last = out_lbl
    wm_size_pct = max(5, min(40, int(watermark_size_pct or 14))) / 100.0
    wm_margin_x_pct = max(0.0, min(20.0, float(watermark_margin_x_pct or 0.0))) / 100.0
    wm_margin_y_pct = max(0.0, min(20.0, float(watermark_margin_y_pct or 0.0))) / 100.0
    wm_opacity = max(0.2, min(1.0, float(watermark_opacity or 1.0)))
    wm_width_px = max(48, int(int(w) * wm_size_pct))
    wm_margin_x_px = max(0, int(int(w) * wm_margin_x_pct))
    wm_margin_y_px = max(0, int(int(h) * wm_margin_y_pct))
    if watermark_corner == 'Trên-Trái':
        wm_x_expr = f"{wm_margin_x_px}"
        wm_y_expr = f"{wm_margin_y_px}"
    elif watermark_corner == 'Dưới-Trái':
        wm_x_expr = f"{wm_margin_x_px}"
        wm_y_expr = f'''H-h-{wm_margin_y_px}'''
    elif watermark_corner == 'Dưới-Phải':
        wm_x_expr = f'''W-w-{wm_margin_x_px}'''
        wm_y_expr = f'''H-h-{wm_margin_y_px}'''
    else:
        wm_x_expr = f'''W-w-{wm_margin_x_px}'''
        wm_y_expr = f"{wm_margin_y_px}"
    if has_wm:
        fc += f'''; [2:v]scale={wm_width_px}:-1,colorchannelmixer=aa={wm_opacity:.3f}[wm]; [{last}][wm]overlay={wm_x_expr}:{wm_y_expr}[v]'''
    else:
        fc += f'''; [{last}]copy[v]'''
    filter_complex_v = fc
    map_v = '[v]'
    enc = _video_encode_args(use_nvenc)
    if mute_orig:
        filter_complex = f'''{filter_complex_v};[1:a]apad[a]'''
        cmd = [FFMPEG_EXE, '-y', '-ss', str(clip_start), '-t', str(clip_duration), '-i', source_video, '-i', tts_path]
        if watermark_path:
            if os.path.exists(watermark_path):
                cmd.append('-i')
                cmd.append(watermark_path)
        cmd.extend(['-filter_complex', filter_complex, '-map', map_v, '-map', '[a]', '-t', str(tts_duration), *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), out_path])
    else:
        af_src = f'''[0:a]volume={orig_vol}{atempo_filter},atrim=duration={tts_duration},asetpts=N/SR/TB[ao]'''
        filter_complex = f'''{filter_complex_v};{af_src};[1:a]asetpts=N/SR/TB[vo];[vo]asplit=2[vo_sc][vo_mix];[ao][vo_sc]sidechaincompress=threshold=-35dB:ratio=20:attack=50:release=400[ao_ducked];[ao_ducked][vo_mix]amix=inputs=2:duration=longest:weights=1 3[a]'''
        cmd = [FFMPEG_EXE, '-y', '-ss', str(clip_start), '-t', str(clip_duration), '-i', source_video, '-i', tts_path]
        if watermark_path:
            if os.path.exists(watermark_path):
                cmd.append('-i')
                cmd.append(watermark_path)
        cmd.extend(['-filter_complex', filter_complex, '-map', map_v, '-map', '[a]', '-t', str(tts_duration), *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), out_path])
    r = run_subprocess(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        fc_fb = f'''[0:v]{vf}[vbase]'''
        last_fb = 'vbase'
        if blur_chain:
            fc_fb += ';' + blur_chain
            last_fb = blur_last
        for (si_fb, sf_fb) in enumerate(sub_filters):
            out_lbl_fb = f'''vsub_fb{si_fb}'''
            fc_fb += f'''; [{last_fb}]{sf_fb}[{out_lbl_fb}]'''
            last_fb = out_lbl_fb
        if has_wm:
            fc_fb += f'''; [2:v]scale={wm_width_px}:-1,colorchannelmixer=aa={wm_opacity:.3f}[wm]; [{last_fb}][wm]overlay={wm_x_expr}:{wm_y_expr}[v]'''
        else:
            fc_fb += f'''; [{last_fb}]copy[v]'''
        filter_complex_fb = fc_fb + '; [1:a]apad[a]'
        cmd_fb = [FFMPEG_EXE, '-y', '-ss', str(clip_start), '-t', str(clip_duration), '-i', source_video, '-i', tts_path]
        if watermark_path:
            if os.path.exists(watermark_path):
                cmd_fb.append('-i')
                cmd_fb.append(watermark_path)
        cmd_fb.extend(['-filter_complex', filter_complex_fb, '-map', map_v, '-map', '[a]', '-t', str(tts_duration), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), out_path])
        r2 = run_subprocess(cmd_fb, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if r2.returncode != 0:
            log_fn(f'''   [WARN] FFmpeg loi clip {i + 1}: {r2.stderr[slice(-300, None, None)]}''')
            _cleanup_files(subtitle_files)
            return False
    _cleanup_files(subtitle_files)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 0
def _cleanup_files(paths):
    for sf in paths:
        try:
            if os.path.exists(sf):
                os.remove(sf)
        except OSError:
            pass
def _concat_clips(clips, output_path, temp_dir, log_fn):
    list_file = os.path.join(temp_dir, 'concat_list.txt')
    with open(list_file, 'w', encoding='utf-8') as f:
        for c in clips:
            safe = c.replace('\\', '/').replace("'", "\\'")
            f.write(f'''file \'{safe}\'\n''')
    cmd = [FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', output_path]
    r = run_subprocess_heartbeat(cmd, log_fn=log_fn, label='Ghép clip cuối', text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        log_fn('   Concat copy/re-encode audio that bai, tien hanh re-encode toan bo...')
        cmd2 = [FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', output_path]
        r2 = run_subprocess_heartbeat(cmd2, log_fn=log_fn, label='Ghép clip cuối (re-encode toàn bộ)', text=True, encoding='utf-8', errors='replace')
        if r2.returncode != 0:
            log_fn(f'''   [LOI] Concat: {r2.stderr[slice(None, 300, None)]}''')
            return False
    return os.path.exists(output_path)
def _escape_drawtext(text):
    text = text.replace('\\', '\\\\')
    text = text.replace("'", '’')
    text = text.replace(':', '\\:')
    text = text.replace('%', '\\%')
    return text
def _build_blur_chain(in_label, boxes, clip_start=0.0, clip_end=None):
    if not boxes:
        return ('', in_label)
    parts = []
    cur = in_label
    idx = 0
    for b in boxes:
        (t_start, t_end) = (None, None)
        if isinstance(b, dict):
            box_xy = b.get('box')
            t_start = b.get('t_start')
            t_end = b.get('t_end')
        else:
            box_xy = b
        try:
            (x1, y1, x2, y2) = [float(v) for v in box_xy]
        except Exception:
            continue
        (x1, x2) = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
        (y1, y2) = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))
        dw = x2 - x1
        dh = y2 - y1
        if dw < 0.01 or dh < 0.01:
            continue
        enable_clause = ''
        if t_start is not None or t_end is not None:
            t_start = float(t_start) if t_start is not None else 0.0
            t_end = float(t_end) if t_end is not None else 1000000000.0
            if clip_end is not None and (t_start >= clip_end or t_end <= clip_start):
                continue
            rel_start = max(0.0, t_start - clip_start)
            rel_end = t_end - clip_start if clip_end is None else min(clip_end - clip_start, t_end - clip_start)
            enable_clause = f''':enable=\'between(t\\,{rel_start:.3f}\\,{rel_end:.3f})\''''
        a = f'''ba{idx}'''
        c = f'''bc{idx}'''
        nxt = f'''bm{idx}'''
        cw = f'''trunc(iw*{dw:.4f}/2)*2'''
        ch = f'''trunc(ih*{dh:.4f}/2)*2'''
        cx = f'''trunc(iw*{x1:.4f}/2)*2'''
        cy = f'''trunc(ih*{y1:.4f}/2)*2'''
        parts.append(f'''[{cur}]split[{a}][{c}]''')
        parts.append(f'''[{c}]crop={cw}:{ch}:{cx}:{cy},gblur=sigma=20:steps=3[{c}b]''')
        parts.append(f'''[{a}][{c}b]overlay=W*{x1:.4f}:H*{y1:.4f}{enable_clause}[{nxt}]''')
        cur = nxt
        idx += 1
    if idx == 0:
        return ('', in_label)
    return (';'.join(parts), cur)
def _fit_subtitle(text, vid_w, vid_h, font_size_factor=1.0, max_lines=2, line_spacing=6, max_width_pct=0.82):
    text = ' '.join(((text or '')).split())
    if not text:
        return ('', max(24, int(vid_h // 24 * font_size_factor)))
    max_block_h = vid_h * 0.28
    base_font = max(24, int(vid_h // 26 * font_size_factor))
    min_font = max(18, int(vid_h // 42 * font_size_factor))
    safe_w = vid_w * max(0.3, min(0.95, float(max_width_pct or 0.82)))
    fontsize = base_font
    while True:
        chars_per_line = max(16, int(safe_w / (fontsize * 0.6)))
        wrapped = _wrap_text(text, max_len=chars_per_line)
        n_lines = wrapped.count('\n') + 1
        line_h = fontsize * 1.15 + max(0, int(line_spacing))
        if n_lines <= max_lines and n_lines * line_h <= max_block_h:
            return (wrapped, int(fontsize))
        if fontsize <= min_font:
            return (wrapped, int(fontsize))
        fontsize -= 2
def _split_subtitle_chunks(text, max_chars_per_chunk=56, max_lines_per_chunk=2):
    text = text or ''
    if '||' in text:
        out = []
        for part in text.split('||'):
            part = part.strip()
            if part:
                out.extend(_auto_split_subtitle_chunks(part, max_chars_per_chunk, max_lines_per_chunk))
        return out
    return _auto_split_subtitle_chunks(text, max_chars_per_chunk, max_lines_per_chunk)
def _auto_split_subtitle_chunks(text, max_chars_per_chunk=56, max_lines_per_chunk=2):
    text = ' '.join(((text or '')).split())
    max_chars_per_chunk = max(18, int(max_chars_per_chunk or 56))
    max_lines_per_chunk = max(1, int(max_lines_per_chunk or 2))
    if not text:
        return []
    if len(text) <= max_chars_per_chunk:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars_per_chunk:
            chunks.append(remaining)
            break
        window = remaining[slice(None, max_chars_per_chunk + 1, None)]
        cut = -1
        for i in range(len(window) - 1, int(len(window) * 0.4), -1):
            if window[i] in '.!?,;':
                cut = i + 1
                break
        if cut == -1:
            sp = window.rfind(' ')
            cut = sp if sp > 0 else max_chars_per_chunk
        chunks.append(remaining[slice(None, cut, None)].strip())
        remaining = remaining[slice(cut, None, None)].strip()
    chunks = [c for c in chunks if c]
    _MIN_CHUNK_CHARS = 20
    merged = []
    for c in chunks:
        if merged and len(c) < _MIN_CHUNK_CHARS:
            combined = ((merged[-1] + ' ' + c)).strip()
            if len(combined) <= max_chars_per_chunk:
                merged[-1] = combined
                continue
        merged.append(c)
    return merged
def _wrap_text(text, max_len=50):
    if len(text) <= max_len:
        return text
    words = text.split()
    lines = []
    cur = ''
    for w in words:
        if len(cur) + len(w) + 1 <= max_len:
            cur = ((cur + ' ' + w)).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return '\n'.join(lines)