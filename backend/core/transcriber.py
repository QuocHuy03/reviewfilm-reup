"""
Module trích xuất âm thanh từ video và nhận diện giọng nói bằng Whisper / Faster-Whisper.
"""
import os
import sys
import subprocess
import json
import logging
import traceback
from core.utils import FFMPEG_EXE, _HIDE

def _inject_ffmpeg_to_path():
    ffmpeg_dir = os.path.dirname(FFMPEG_EXE)
    if not os.path.exists(ffmpeg_dir):
        return
    current_path = os.environ.get('PATH', '')
    if ffmpeg_dir.lower() not in current_path.lower():
        os.environ['PATH'] = ffmpeg_dir + os.pathsep + current_path

def get_whisper_cache_dir(audio_path):
    drive = os.path.splitdrive(os.path.abspath(audio_path))[0]
    if drive:
        cache_base = os.path.join(drive + os.sep, 'AutoReviewStudio_Cache')
    else:
        cache_base = os.path.expanduser('~/.cache')
    whisper_dir = os.path.join(cache_base, 'whisper')
    os.makedirs(whisper_dir, exist_ok=True)
    return whisper_dir

def _has_nvidia_gpu():
    try:
        r = subprocess.run(['nvidia-smi'], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
        return r.returncode == 0
    except Exception:
        return False

def _add_cuda_dll_dirs(log_fn=print):
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except Exception:
        pass
    # faster-whisper khong can torch: hoi thang ctranslate2 (neu load model CUDA loi
    # thi _run_faster_whisper van tu lui ve CPU int8).
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        pass
    return False

def transcribe_audio(video_path, model, temp_dir, language='auto', log_fn=print, device='GPU (NVIDIA)', beam_size=5, should_stop=None):
    global _should_stop
    _should_stop = should_stop
    _inject_ffmpeg_to_path()
    drive = os.path.splitdrive(os.path.abspath(temp_dir))[0]
    if drive:
        cache_base = os.path.join(drive + os.sep, 'AutoReviewStudio_Cache')
        os.makedirs(os.path.join(cache_base, 'whisper'), exist_ok=True)
        os.environ['XDG_CACHE_HOME'] = cache_base
        os.environ['TORCH_HOME'] = os.path.join(cache_base, 'torch')
        os.environ['HF_HOME'] = os.path.join(cache_base, 'huggingface')
        os.environ['TRANSFORMERS_CACHE'] = os.path.join(cache_base, 'huggingface')
    
    audio_path = os.path.join(temp_dir, 'audio_extracted.wav')
    def _extract():
        log_fn('   Trích xuất audio từ video...')
        r = subprocess.run([FFMPEG_EXE, '-y', '-i', video_path, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_path], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
        if r.returncode != 0 or not os.path.exists(audio_path):
            log_fn(f'   [LỖI] Trích audio: {r.stderr[:200] if r.stderr else "Không tạo được file audio"}')
            return False
        log_fn(f'   Audio: {os.path.getsize(audio_path) / 1024 / 1024:.1f} MB')
        return True

    if not _extract():
        return None

    log_fn(f"   Chạy Whisper model '{model}'...")
    def _run_whisper():
        try:
            return _run_whisper_py(audio_path, model, language, log_fn, device, beam_size)
        except WhisperCancelled:
            log_fn('   [DỪNG] Đã huỷ khi đang nhận dạng giọng nói.')
            return None
        except Exception as e:
            log_fn(f'   [WARN] In-process whisper lỗi ({e}), thử subprocess...')
            try:
                return _run_whisper_subprocess(audio_path, model, language, log_fn, device, beam_size)
            except Exception as e2:
                log_fn(f'   [LỖI] Không khởi động được Whisper: {e2}')
                return None

    result = _run_whisper()
    if result is None and not os.path.exists(audio_path):
        log_fn('   [CẢNH BÁO] File audio bị mất trước khi nhận dạng xong — thử trích xuất lại...')
        if _extract():
            result = _run_whisper()
    return result

def _run_whisper_subprocess(audio_path, model, language, log_fn, device, beam_size=5):
    result = _run_whisper_worker_once(audio_path, model, language, log_fn, device, beam_size)
    if result is not None:
        return result
    log_fn('   >>> Tự động thử lại với CPU (int8)...')
    result = _run_whisper_worker_once(audio_path, model, language, log_fn, 'CPU', beam_size)
    if result is None:
        log_fn('   [LỖI] Transcribe thất bại hoàn toàn.')
    return result

def _run_whisper_worker_once(audio_path, model, language, log_fn, device, beam_size=5):
    args_file = audio_path + '.args.json'
    result_file = audio_path + '.result.json'
    with open(args_file, 'w', encoding='utf-8') as f:
        json.dump({'audio_path': audio_path, 'model': model, 'language': language, 'device': device, 'beam_size': beam_size}, f)
    
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable, '--whisper-worker', args_file, result_file]
    else:
        main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py')
        cmd = [sys.executable, main_py, '--whisper-worker', args_file, result_file]
    
    env = dict(os.environ)
    env['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
    env.setdefault('OMP_NUM_THREADS', '4')
    drive = os.path.splitdrive(os.path.abspath(audio_path))[0]
    if drive:
        cache_base = os.path.join(drive + os.sep, 'AutoReviewStudio_Cache')
        os.makedirs(cache_base, exist_ok=True)
        env['XDG_CACHE_HOME'] = cache_base
        env['TORCH_HOME'] = os.path.join(cache_base, 'torch')
        env['HF_HOME'] = os.path.join(cache_base, 'huggingface')
        env['TRANSFORMERS_CACHE'] = os.path.join(cache_base, 'huggingface')
    
    if 'CPU' in str(device).upper():
        env['CUDA_VISIBLE_DEVICES'] = '-1'
        
    log_fn(f'   (Chạy Whisper trong tiến trình riêng — chế độ: {device})')
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', env=env, creationflags=_HIDE)
    
    try:
        for line in proc.stdout:
            line = line.rstrip()
            log_fn(line)
        proc.wait()
    except Exception:
        pass

    result = None
    try:
        if os.path.exists(result_file):
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('ok'):
                result = data.get('result')
            else:
                log_fn(f"   [LỖI Whisper worker]: {data.get('error', '')}")
                if data.get('tb'):
                    log_fn(data['tb'])
        else:
            log_fn(f'   [LỖI] Whisper worker thoát đột ngột (mã lỗi {proc.returncode}).')
    except Exception as e:
        log_fn(f'   [LỖI ĐỌC PHẢN HỒI WORKER]: {e}')
    
    for f in (args_file, result_file):
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass
            
    return result

def _run_whisper_py(audio_path, model_name, language, log_fn, device, beam_size=5):
    _inject_ffmpeg_to_path()
    if not os.path.exists(audio_path):
        log_fn('   [LỖI] File audio_extracted.wav bị mất trước khi nhận dạng giọng nói.')
        return None
    
    try:
        from faster_whisper import WhisperModel
        return _run_faster_whisper(audio_path, model_name, language, log_fn, device, beam_size)
    except WhisperCancelled:
        raise
    except Exception as e:
        log_fn(f'   [WARN] faster-whisper lỗi ({e}), thử openai-whisper...')
        
    try:
        import whisper
        whisper_cache = get_whisper_cache_dir(audio_path)
        model = whisper.load_model(model_name, download_root=whisper_cache)
        kwargs = {'verbose': False, 'fp16': False, 'condition_on_previous_text': False, 'initial_prompt': 'Dưới đây là đoạn phim, xin vui lòng không lặp lại câu.'}
        if language and language != 'auto':
            kwargs['language'] = language
        result = model.transcribe(audio_path, **kwargs)
        detected_lang = result.get('language', 'unknown')
        log_fn(f'   Ngôn ngữ phát hiện: {detected_lang}')
        segments = []
        for seg in result.get('segments', []):
            text = seg.get('text', '').strip()
            if text:
                segments.append({'start': float(seg['start']), 'end': float(seg['end']), 'text': text})
        full_text = ' '.join((s['text'] for s in segments))
        log_fn(f'   Đã nhận dạng {len(segments)} đoạn thoại')
        return {'language': detected_lang, 'segments': segments, 'full_text': full_text}
    except Exception as e:
        log_fn(f'   [LỖI] Whisper: {e}')
        return None

_MODEL_CACHE = {}          # (thư mục model, thiết bị, kiểu tính) → WhisperModel đã nạp — job sau khỏi nạp lại
_should_stop = None        # callable do transcribe_audio đặt → True khi job bị huỷ


class WhisperCancelled(RuntimeError):
    pass


def _collect(segments_gen):
    """Đọc dần kết quả Whisper, dừng ngay khi job bị huỷ (trước đây phải chờ nhận dạng hết cả phim)."""
    out = []
    for seg in segments_gen:
        if _should_stop and _should_stop():
            raise WhisperCancelled('Đã huỷ khi đang nhận dạng giọng nói.')
        out.append(seg)
    return out


def _run_faster_whisper(audio_path, model_name, language, log_fn, device_pref, beam_size=5):
    from faster_whisper import WhisperModel
    from huggingface_hub import snapshot_download

    _quiet = ['huggingface_hub', 'filelock', 'urllib3', 'fsspec', 'ctranslate2', 'faster_whisper']
    _saved = {}
    for n in _quiet:
        try:
            logger = logging.getLogger(n)
            _saved[n] = logger.level
            logger.setLevel(logging.ERROR)
        except Exception:
            pass

    try:
        device, compute_type = 'cpu', 'int8'
        if 'CPU' in str(device_pref).upper():
            log_fn('   Chạy ở chế độ CPU (int8) theo yêu cầu')
        elif _has_nvidia_gpu():
            device, compute_type = 'cuda', 'float16'
            log_fn('   Phát hiện GPU NVIDIA — dùng CUDA (float16) qua ctranslate2')
            if not _add_cuda_dll_dirs(log_fn):
                log_fn('   [WARN] Không tìm thấy cuBLAS/cuDNN DLL — lùi về CPU (int8) cho an toàn')
                device, compute_type = 'cpu', 'int8'
        else:
            log_fn('   [INFO] Không thấy GPU NVIDIA — chạy CPU (int8). Ôn định & đủ nhanh.')

        _HUB = {
            'tiny': 'Systran/faster-whisper-tiny',
            'base': 'Systran/faster-whisper-base',
            'small': 'Systran/faster-whisper-small',
            'medium': 'Systran/faster-whisper-medium',
            'large': 'Systran/faster-whisper-large-v3',
            'large-v2': 'Systran/faster-whisper-large-v2',
            'large-v3': 'Systran/faster-whisper-large-v3'
        }
        hub_name = _HUB.get(model_name, f'Systran/faster-whisper-{model_name}')
        whisper_cache = get_whisper_cache_dir(audio_path)
        local_dir = os.path.join(whisper_cache, f'fw-{model_name}')
        
        if not os.path.exists(os.path.join(local_dir, 'model.bin')):
            log_fn(f"   Tải model '{model_name}' từ HuggingFace (lần đầu, sau đó dùng cache)...")
            snapshot_download(hub_name, local_dir=local_dir, local_dir_use_symlinks=False)
            
        key = (local_dir, device, compute_type)
        model = _MODEL_CACHE.get(key)
        if model is not None:
            log_fn(f"   Dùng lại model '{model_name}' đã nạp sẵn trong bộ nhớ")
        else:
            log_fn(f'   Load faster-whisper từ: {local_dir}')
        try:
            if model is None:
                _MODEL_CACHE.clear()           # chỉ giữ 1 model — đổi model thì nhả model cũ cho đỡ RAM/VRAM
                model = WhisperModel(local_dir, device=device, compute_type=compute_type)
                _MODEL_CACHE[key] = model
        except Exception as e:
            if device == 'cuda':
                log_fn(f'   [WARN] CUDA không dùng được ({str(e)[:60]}) — lùi về CPU (int8)')
                device, compute_type = 'cpu', 'int8'
                model = WhisperModel(local_dir, device=device, compute_type=compute_type)
            else:
                raise e

        kwargs = {
            'beam_size': max(1, int(beam_size or 5)),
            'vad_filter': True,
            'vad_parameters': {'min_silence_duration_ms': 500},
            'condition_on_previous_text': False,
            'initial_prompt': 'Dưới đây là đoạn phim, xin vui lòng không lặp lại câu.'
        }
        if language and language != 'auto':
            kwargs['language'] = language

        try:
            if _should_stop and _should_stop():
                raise WhisperCancelled('Đã huỷ trước khi nhận dạng.')
            segments_gen, info = model.transcribe(audio_path, **kwargs)
            segments_list = _collect(segments_gen)
        except WhisperCancelled:
            raise
        except Exception as run_err:
            log_fn(f'   [WARN] Lỗi transcribe với VAD ({str(run_err)[:80]}), thử tắt VAD hoặc lùi CPU...')
            kwargs['vad_filter'] = False
            kwargs.pop('vad_parameters', None)
            if device == 'cuda':
                device, compute_type = 'cpu', 'int8'
                model = WhisperModel(local_dir, device=device, compute_type=compute_type)
            segments_gen, info = model.transcribe(audio_path, **kwargs)
            segments_list = _collect(segments_gen)

        detected_lang = getattr(info, 'language', 'vi')
        log_fn(f'   Ngôn ngữ phát hiện: {detected_lang}')
        segments = []
        for seg in segments_list:
            text = seg.text.strip()
            if text:
                segments.append({'start': float(seg.start), 'end': float(seg.end), 'text': text})
        full_text = ' '.join((s['text'] for s in segments))
        log_fn(f'   Đã nhận dạng {len(segments)} đoạn thoại (faster-whisper)')
        return {'language': detected_lang, 'segments': segments, 'full_text': full_text}
    except Exception as e:
        tb = traceback.format_exc()
        log_fn(f'   [DEBUG] faster-whisper traceback:\n{tb}')
        raise e
    finally:
        for n, lvl in _saved.items():
            try:
                logging.getLogger(n).setLevel(lvl)
            except Exception:
                pass