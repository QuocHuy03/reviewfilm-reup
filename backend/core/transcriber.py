"""
Module trích xuất âm thanh từ video và nhận diện giọng nói bằng Whisper / Faster-Whisper.
"""
import os
import sys
import subprocess
import json
import logging
import traceback
from core.utils import FFMPEG_EXE, _HIDE, audio_lead_filter

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

def prefetch_model(model_name, out_dir):
    """Tải sẵn model Whisper (ngầm, lúc mở app) vào đúng chỗ job sẽ tìm — job đầu tiên không phải chờ tải."""
    if model_name == 'capcut':
        return                    # nhận dạng online, không có model để tải
    try:
        from huggingface_hub import snapshot_download
        drive = os.path.splitdrive(os.path.abspath(out_dir or os.path.expanduser('~')))[0]
        local_dir = os.path.join(get_whisper_cache_dir(os.path.join(drive + os.sep, 'x') if drive else '~'), f'fw-{model_name}')
        if os.path.exists(os.path.join(local_dir, 'model.bin')):
            return
        hub = {'large': 'Systran/faster-whisper-large-v3'}.get(model_name, f'Systran/faster-whisper-{model_name}')
        snapshot_download(hub, local_dir=local_dir)
    except Exception:
        pass                      # mất mạng / thiếu chỗ → job sẽ tự tải lại như cũ


def _has_nvidia_gpu():
    try:
        r = subprocess.run(['nvidia-smi'], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
        return r.returncode == 0
    except Exception:
        return False

# Tên hiển thị cho người dùng (không lộ tên kỹ thuật) + dung lượng tải lần đầu (MB)
ASR_LABELS = {'capcut': 'Online · nhanh nhất', 'tiny': 'Siêu nhanh', 'base': 'Nhanh', 'small': 'Cân bằng', 'medium': 'Chính xác',
              'large': 'Chính xác nhất', 'large-v2': 'Chính xác cao', 'large-v3': 'Chính xác nhất'}
_MODEL_MB = {'tiny': 75, 'base': 145, 'small': 484, 'medium': 1530, 'large': 3090, 'large-v2': 3090, 'large-v3': 3090}


def asr_label(model):
    return ASR_LABELS.get(model, model)


def _report(p, text=None):
    """Báo tiến độ nhận dạng (0–1) cho job — đặt bởi transcribe_audio(progress=…)."""
    if _progress:
        try:
            _progress(max(0.0, min(1.0, p)), text)
        except Exception:
            pass


def cuda_compute_type():
    """Kiểu tính Whisper hợp với card: card mới (Volta trở lên) → float16; card đời cũ (GTX 10xx Pascal… không có float16
    nhanh) → int8 (đo trên GTX 1060: nhanh gấp 5 lần CPU, ít VRAM). Trước đây luôn xin float16 → card cũ lỗi, lặng lẽ chạy CPU."""
    try:
        import ctranslate2
        types = ctranslate2.get_supported_compute_types('cuda')
    except Exception:
        return 'float16'
    for t in ('float16', 'int8_float16', 'int8', 'int8_float32', 'float32'):
        if t in types:
            return t
    return 'float32'


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

_word_ts = False


def _split_by_words(words, pause=0.3):
    """Đoạn Whisper có thời gian từng chữ → thời gian đúng lúc mở miệng / ngậm miệng, tách đôi ở chỗ ngừng nói ≥ pause giây
    (thường là chuyển người nói hoặc hết câu) — câu lồng tiếng bắt đầu đúng lúc, không sớm. Tách hơi kỹ cũng được:
    Whisper tiếng Trung hay không có dấu câu & 2 người đối đáp nhanh chỉ ngừng ~0.3s — phân vai xong mảnh cùng người được gộp lại."""
    out = []
    cur = [words[0]]
    ends = ('。', '！', '？', '!', '?', '…')
    for w in words[1:]:
        # ngừng nói đủ lâu, hoặc hết câu (。？！ — trong phim thường là chuyển người nói) khi câu đã đủ dài
        # câu dài ≥ 2.5s tách cả ở dấu phẩy (2 người nói nối nhau hay chỉ cách dấu phẩy) — phân vai xong mảnh cùng người được gộp lại
        last = cur[-1].word.strip()
        dur = float(cur[-1].end) - float(cur[0].start)
        if (float(w.start) - float(cur[-1].end) >= pause
                or (last.endswith(ends) and dur >= 0.4)
                or (last.endswith((',', '，', '、')) and dur >= 2.5)):
            out.append(cur)
            cur = [w]
        else:
            cur.append(w)
    out.append(cur)
    segs = []
    for grp in out:
        text = ''.join(w.word for w in grp).strip()
        if text:
            segs.append({'start': float(grp[0].start), 'end': max(float(grp[-1].end), float(grp[0].start) + 0.2), 'text': text,
                         'words': [[round(float(w.start), 3), round(float(w.end), 3), w.word] for w in grp]})
    return segs


# Câu gợi ý cho Whisper ĐÚNG ngôn ngữ nguồn (câu tiếng Việt cho audio Trung / Hàn dễ kéo Whisper ra chữ sai ngôn ngữ
# hoặc tự bịa). Tự nhận ngôn ngữ ('auto') → không gợi ý.
_PROMPTS = {'zh': '以下是电影对白，请勿重复句子。', 'ja': '以下は映画の台詞です。', 'ko': '다음은 영화 대사입니다.',
            'en': 'The following is movie dialogue.', 'vi': 'Dưới đây là đoạn phim, xin vui lòng không lặp lại câu.',
            'th': 'ต่อไปนี้คือบทสนทนาในภาพยนตร์', 'es': 'El siguiente es el diálogo de una película.',
            'fr': "Voici les dialogues d'un film.", 'de': 'Im Folgenden der Filmdialog.', 'ru': 'Далее следуют диалоги из фильма.'}


def _cpu_threads(device):
    """faster-whisper trên CPU: số luồng theo ngân sách CPU chung (mặc định nó lấy hết lõi, tranh với tách giọng chạy song song)."""
    if device != 'cpu':
        return {}
    try:
        from core import perf
        return {'cpu_threads': perf.threads_for(2)}
    except Exception:
        return {}


def _prompt_for(language):
    return _PROMPTS.get(str(language or '').lower()[:2]) if language and language != 'auto' else None


def transcribe_audio(video_path, model, temp_dir, language='auto', log_fn=print, device='GPU (NVIDIA)', beam_size=5, should_stop=None,
                     word_timestamps=False, progress=None):
    """word_timestamps=True (lồng tiếng): đầu / cuối đoạn bám đúng chữ đầu / chữ cuối, tách đoạn ở chỗ ngừng nói dài.
    progress(p 0–1, text|None): tiến độ thật (tải mô hình theo MB, nhận dạng theo giây đã nghe / tổng thời lượng)."""
    global _should_stop, _word_ts, _progress
    _should_stop = should_stop
    _progress = progress
    _word_ts = bool(word_timestamps)
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
        r = subprocess.run([FFMPEG_EXE, '-y', '-i', video_path, '-vn', *audio_lead_filter(video_path), '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_path], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
        if r.returncode != 0 or not os.path.exists(audio_path):
            log_fn(f'   [LỖI] Trích audio: {r.stderr[:200] if r.stderr else "Không tạo được file audio"}')
            return False
        log_fn(f'   Audio: {os.path.getsize(audio_path) / 1024 / 1024:.1f} MB')
        return True

    if not _extract():
        return None

    if model == 'capcut':
        from core.capcut_stt import CapcutSttError, transcribe as capcut_transcribe
        try:
            return capcut_transcribe(audio_path, temp_dir, language, log_fn, should_stop, word_timestamps)
        except CapcutSttError as e:
            log_fn(f'   [WARN] Nhận dạng online lỗi ({e}) — chuyển sang nhận dạng trên máy (mức Nhanh)...')
            model = 'base'

    log_fn(f"   Nhận dạng giọng nói — mức '{asr_label(model)}'...")
    def _run_whisper():
        try:
            return _run_whisper_py(audio_path, model, language, log_fn, device, beam_size)
        except WhisperCancelled:
            log_fn('   [DỪNG] Đã huỷ khi đang nhận dạng giọng nói.')
            return None
        except Exception as e:
            log_fn(f'   [WARN] Bộ nhận dạng lỗi ({str(e)[:120]}) — thử chạy ở tiến trình riêng...')
            try:
                return _run_whisper_subprocess(audio_path, model, language, log_fn, device, beam_size)
            except Exception as e2:
                log_fn(f'   [LỖI] Không khởi động được bộ nhận dạng giọng nói: {e2}')
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
        
    log_fn(f'   (Nhận dạng giọng nói ở tiến trình riêng — {device})')
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
                log_fn(f"   [LỖI] Bộ nhận dạng giọng nói: {data.get('error', '')}")
                if data.get('tb'):
                    log_fn(data['tb'])
        else:
            log_fn(f'   [LỖI] Bộ nhận dạng giọng nói thoát đột ngột (mã lỗi {proc.returncode}).')
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
        log_fn(f'   [WARN] Bộ nhận dạng chính lỗi ({str(e)[:120]}) — thử bộ dự phòng...')
        
    try:
        import whisper
        whisper_cache = get_whisper_cache_dir(audio_path)
        model = whisper.load_model(model_name, download_root=whisper_cache)
        kwargs = {'verbose': False, 'fp16': False, 'condition_on_previous_text': False, 'initial_prompt': _prompt_for(language)}
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
        log_fn(f'   [LỖI] Nhận dạng giọng nói: {e}')
        return None

_MODEL_CACHE = {}          # (thư mục model, thiết bị, kiểu tính) → WhisperModel đã nạp — job sau khỏi nạp lại
_should_stop = None        # callable do transcribe_audio đặt → True khi job bị huỷ
_progress = None           # callable do transcribe_audio đặt → báo tiến độ (0–1, chữ)


class WhisperCancelled(RuntimeError):
    pass


def _collect(segments_gen, total=0.0, log_fn=None):
    """Đọc dần kết quả nhận dạng: dừng ngay khi job bị huỷ, báo % theo giây đã nghe / tổng thời lượng
    (trước đây đứng yên ở 10% tới khi nhận dạng xong cả phim → tưởng app treo)."""
    import time as _t
    out = []
    (last_t, last_log) = (0.0, -1)
    for seg in segments_gen:
        if _should_stop and _should_stop():
            raise WhisperCancelled('Đã huỷ khi đang nhận dạng giọng nói.')
        out.append(seg)
        if total > 0:
            p = min(1.0, float(getattr(seg, 'end', 0) or 0) / total)
            now = _t.time()
            if now - last_t > 0.7:
                last_t = now
                _report(p, f'Nhận dạng giọng nói · {int(p * 100)}%')
            step = int(p * 4)                       # nhật ký mỗi 25%
            if log_fn and step > last_log and 0 < step < 4:
                last_log = step
                log_fn(f'   Nhận dạng giọng nói: {step * 25}% ({len(out)} đoạn thoại)')
    return out


def _download_with_progress(fn, folder, need_mb, log_fn):
    """Tải mô hình ở luồng riêng, đo dung lượng thư mục mỗi giây → báo 'Tải mô hình · 120/484 MB' (không còn đứng im)."""
    import threading
    import time as _t
    box = {}

    def run():
        try:
            fn()
        except BaseException as e:      # noqa: BLE001
            box['e'] = e
    th = threading.Thread(target=run, daemon=True)
    th.start()
    last = -1
    while th.is_alive():
        th.join(1.0)
        if _should_stop and _should_stop():
            raise WhisperCancelled('Đã huỷ khi đang tải mô hình nhận dạng.')
        mb = 0
        for (root, _, files) in os.walk(folder):
            for f in files:
                try:
                    mb += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        mb //= 1048576
        if need_mb:
            _report(0.0, f'Tải mô hình nhận dạng · {min(mb, need_mb)}/{need_mb} MB')
        step = int(mb / max(1, need_mb) * 4) if need_mb else 0
        if step > last and 0 < step < 4:
            last = step
            log_fn(f'   Đã tải {mb}/{need_mb} MB')
    if 'e' in box:
        raise box['e']


def _load_wav_16k(path):
    """WAV PCM 16-bit mono 16kHz (do ffmpeg trích) → numpy float32 [-1, 1]; None nếu không đúng định dạng."""
    import wave
    import numpy as np
    try:
        with wave.open(path, 'rb') as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1 or w.getframerate() != 16000:
                return None
            data = w.readframes(w.getnframes())
        return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    except Exception:
        return None


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
            device, compute_type = 'cuda', cuda_compute_type()
            log_fn(f'   Nhận dạng chạy trên GPU NVIDIA ({compute_type})')
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
            need = _MODEL_MB.get(model_name, 0)
            log_fn(f"   Tải mô hình nhận dạng giọng nói (mức '{asr_label(model_name)}'"
                   + (f', ~{need} MB' if need else '') + ') — chỉ lần đầu, sau đó dùng lại...')
            _download_with_progress(lambda: snapshot_download(hub_name, local_dir=local_dir, local_dir_use_symlinks=False),
                                    local_dir, need, log_fn)
            
        key = (local_dir, device, compute_type)
        model = _MODEL_CACHE.get(key)
        if model is not None:
            log_fn(f"   Dùng lại model '{model_name}' đã nạp sẵn trong bộ nhớ")
        else:
            log_fn(f"   Nạp mô hình nhận dạng (mức '{asr_label(model_name)}')...")
        try:
            if model is None:
                _MODEL_CACHE.clear()           # chỉ giữ 1 model — đổi model thì nhả model cũ cho đỡ RAM/VRAM
                model = WhisperModel(local_dir, device=device, compute_type=compute_type, **_cpu_threads(device))
                _MODEL_CACHE[key] = model
        except Exception as e:
            if device == 'cuda':
                log_fn(f'   [WARN] CUDA không dùng được ({str(e)[:60]}) — lùi về CPU (int8)')
                device, compute_type = 'cpu', 'int8'
                model = WhisperModel(local_dir, device=device, compute_type=compute_type, **_cpu_threads(device))
            else:
                raise e

        # CPU: beam 1 nhanh ~1.8 lần beam 5 mà số đoạn nhận được gần như nhau (đo trên phim 3 phút: 120s vs 220s).
        # GPU nhanh sẵn → giữ beam gốc cho chính xác.
        beams = max(1, int(beam_size or 5)) if device == 'cuda' else 1
        if device != 'cuda':
            log_fn('   CPU: nhận dạng chế độ nhanh (beam 1)')
        kwargs = {
            'beam_size': beams,
            'vad_filter': True,
            'vad_parameters': {'min_silence_duration_ms': 500},
            'condition_on_previous_text': False,
            'initial_prompt': _prompt_for(language),
        }
        if language and language != 'auto':
            kwargs['language'] = language
        if _word_ts:
            kwargs['word_timestamps'] = True

        # Tự đọc WAV (đã trích sẵn 16kHz mono) → mảng số đưa thẳng cho Whisper. Không để faster-whisper tự mở file
        # bằng PyAV: PyAV bản mới bỏ tham số metadata_errors mà faster-whisper còn dùng → máy cài mới chết ngay ở đây.
        audio_in = _load_wav_16k(audio_path)
        if audio_in is None:
            audio_in = audio_path
        try:
            if _should_stop and _should_stop():
                raise WhisperCancelled('Đã huỷ trước khi nhận dạng.')
            segments_gen, info = model.transcribe(audio_in, **kwargs)
            segments_list = _collect(segments_gen, float(getattr(info, 'duration', 0) or 0), log_fn)
        except WhisperCancelled:
            raise
        except Exception as run_err:
            log_fn(f'   [WARN] Lỗi transcribe với VAD ({str(run_err)[:80]}), thử tắt VAD hoặc lùi CPU...')
            kwargs['vad_filter'] = False
            kwargs.pop('vad_parameters', None)
            if device == 'cuda':
                device, compute_type = 'cpu', 'int8'
                model = WhisperModel(local_dir, device=device, compute_type=compute_type, **_cpu_threads(device))
            segments_gen, info = model.transcribe(audio_in, **kwargs)
            segments_list = _collect(segments_gen, float(getattr(info, 'duration', 0) or 0), log_fn)

        detected_lang = getattr(info, 'language', 'vi')
        log_fn(f'   Ngôn ngữ phát hiện: {detected_lang}')
        segments = []
        for seg in segments_list:
            text = seg.text.strip()
            if not text:
                continue
            words = [w for w in (getattr(seg, 'words', None) or []) if (w.word or '').strip()]
            if words:
                segments.extend(_split_by_words(words))
            else:
                segments.append({'start': float(seg.start), 'end': float(seg.end), 'text': text})
        full_text = ' '.join((s['text'] for s in segments))
        _report(1.0, 'Nhận dạng giọng nói · 100%')
        log_fn(f'   Đã nhận dạng {len(segments)} đoạn thoại')
        return {'language': detected_lang, 'segments': segments, 'full_text': full_text}
    except Exception as e:
        tb = traceback.format_exc()
        log_fn(f'   [DEBUG] Chi tiết lỗi nhận dạng:\n{tb}')
        raise e
    finally:
        for n, lvl in _saved.items():
            try:
                logging.getLogger(n).setLevel(lvl)
            except Exception:
                pass