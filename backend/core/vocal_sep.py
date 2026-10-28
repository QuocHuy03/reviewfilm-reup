"""Tách giọng nói khỏi nhạc nền / tiếng động (UVR MDX-Net, model Kim_Vocal_2 ONNX ~64MB).
Lồng tiếng chuyên nghiệp bỏ hẳn giọng gốc mà vẫn giữ nhạc nền & hiệu ứng — thay vì chỉ hạ nhỏ cả track gốc.

Tốc độ:
  - GPU (mọi card DirectX 12: NVIDIA / AMD / Intel) qua onnxruntime-directml — ~5× thời lượng trên GTX 1060.
    Gói này trùng tên module với onnxruntime thường (OCR đang dùng) → cài riêng vào data/runtime/ort_dml
    (~25MB, tự tải lần đầu) và chạy trong TIẾN TRÌNH RIÊNG (workers/vocal_sep_worker.py).
  - Không có GPU / lỗi → CPU ngay trong tiến trình như cũ (~0.7× thời lượng).
Kết quả lưu ở data/cache/sep theo file nguồn (FLAC) → làm lại job / lồng tiếng lại / Review rồi Reup cùng phim không tách lại.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

import numpy as np

MODEL_NAME = 'Kim_Vocal_2.onnx'
MODEL_URL = 'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/Kim_Vocal_2.onnx'
SR = 44100
N_FFT, HOP, DIM_F, DIM_T = 7680, 1024, 3072, 256
COMPENSATE = 1.009                     # hệ số bù của model (theo UVR) khi lấy nhạc nền = gốc − giọng
CHUNK = HOP * (DIM_T - 1)              # 261120 mẫu ≈ 5.9 giây mỗi lượt
TRIM = N_FFT // 2
GEN = CHUNK - 2 * TRIM                 # phần giữa mỗi lượt được giữ (bỏ mép để không vỡ tiếng nối)
DML_PKG = 'onnxruntime-directml==1.24.4'
CACHE_MAX_BYTES = 6 << 30              # bộ nhớ đệm tách giọng tối đa ~6GB (xoá bản dùng lâu nhất)


def model_path():
    from app.config import DATA_DIR
    return os.path.join(DATA_DIR, 'models', MODEL_NAME)


def ensure_model(log=print):
    """Tải model lần đầu (~64MB) → đường dẫn, lỗi → ''."""
    p = model_path()
    if os.path.isfile(p) and os.path.getsize(p) > 50_000_000:
        return p
    import requests
    os.makedirs(os.path.dirname(p), exist_ok=True)
    log('   Tải model tách giọng (~64MB, chỉ lần đầu)...')
    tmp = p + '.part'
    try:
        with requests.get(MODEL_URL, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, 'wb') as f:
                for b in r.iter_content(1 << 20):
                    f.write(b)
        if os.path.getsize(tmp) < 50_000_000:
            raise RuntimeError('file tải về thiếu')
        os.replace(tmp, p)
        return p
    except Exception as e:
        log(f'   [WARN] Không tải được model tách giọng ({str(e)[:100]})', 'warn')
        try:
            os.remove(tmp)
        except OSError:
            pass
        return ''


_WIN = np.hanning(N_FFT + 1)[:-1].astype(np.float32)   # hann tuần hoàn (giống torch.hann_window)
_IDX = np.arange(N_FFT)[None, :] + HOP * np.arange(DIM_T)[:, None]
_NORM = None


def _stft(x):
    """x [2, CHUNK] → [1, 4, DIM_F, DIM_T] (thực / ảo từng kênh) — giống torch.stft(center=True)."""
    xp = np.pad(x, ((0, 0), (TRIM, TRIM)), mode='reflect')
    spec = np.fft.rfft(xp[:, _IDX] * _WIN, axis=-1)          # [2, DIM_T, bins]
    spec = spec.transpose(0, 2, 1)[:, :DIM_F]                 # [2, DIM_F, DIM_T]
    out = np.stack([spec.real, spec.imag], axis=1)            # [2, 2, DIM_F, DIM_T]
    return out.reshape(1, 4, DIM_F, DIM_T).astype(np.float32)


def _istft(s):
    """[1, 4, DIM_F, DIM_T] → [2, CHUNK]."""
    global _NORM
    s = s.reshape(2, 2, DIM_F, DIM_T)
    spec = s[:, 0] + 1j * s[:, 1]
    full = np.zeros((2, N_FFT // 2 + 1, DIM_T), dtype=np.complex64)
    full[:, :DIM_F] = spec
    frames = np.fft.irfft(full.transpose(0, 2, 1), n=N_FFT, axis=-1).astype(np.float32) * _WIN   # [2, DIM_T, N_FFT]
    length = N_FFT + HOP * (DIM_T - 1)
    out = np.zeros((2, length), dtype=np.float32)
    for t in range(DIM_T):
        out[:, t * HOP:t * HOP + N_FFT] += frames[:, t]
    if _NORM is None:                                         # tổng cửa sổ² chỉ phụ thuộc kích thước → tính 1 lần
        norm = np.zeros(length, dtype=np.float32)
        for t in range(DIM_T):
            norm[t * HOP:t * HOP + N_FFT] += _WIN ** 2
        _NORM = np.maximum(norm, 1e-8)
    out /= _NORM
    return out[:, TRIM:TRIM + CHUNK]


def _read_mix(media):
    from core.utils import FFMPEG_EXE, _HIDE
    r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-i', media, '-vn', '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'],
                       capture_output=True, creationflags=_HIDE)
    mix = np.frombuffer(r.stdout, dtype=np.float32)
    if r.returncode != 0 or mix.size < SR:
        return None
    return mix.reshape(-1, 2).T                               # [2, n]


def run_core(sess, media, vp, mp_out, progress=None, should_stop=None):
    """Vòng tách chính (dùng chung cho CPU trong tiến trình và worker GPU). STFT lượt sau chạy song song lúc model đang chạy.
    → số giây âm thanh, hoặc 0 nếu không đọc được âm thanh."""
    import threading

    import soundfile as sf
    mix = _read_mix(media)
    if mix is None:
        return 0
    n = mix.shape[1]
    pad = GEN - n % GEN
    mixp = np.concatenate([np.zeros((2, TRIM), np.float32), mix, np.zeros((2, pad + TRIM), np.float32)], axis=1)
    starts = list(range(0, n + pad, GEN))
    name = sess.get_inputs()[0].name
    nxt = {}

    def prep(i):
        nxt[i] = _stft(mixp[:, i:i + CHUNK])

    th = threading.Thread(target=prep, args=(starts[0],))
    th.start()
    done = 0
    with sf.SoundFile(vp, 'w', SR, 2, format='FLAC', subtype='PCM_16') as wv, \
            sf.SoundFile(mp_out, 'w', SR, 2, format='FLAC', subtype='PCM_16') as wm:
        for (k, i) in enumerate(starts):
            if should_stop and should_stop():
                raise RuntimeError('Đã huỷ')
            th.join()
            spec = nxt.pop(i)
            if k + 1 < len(starts):
                th = threading.Thread(target=prep, args=(starts[k + 1],))
                th.start()
            voc = _istft(sess.run(None, {name: spec})[0])[:, TRIM:-TRIM]
            keep = min(GEN, n - done)
            if keep <= 0:
                break
            voc = voc[:, :keep] * COMPENSATE
            music = mix[:, done:done + keep] - voc
            wv.write(np.clip(voc.T, -1, 1))
            wm.write(np.clip(music.T, -1, 1))
            done += keep
            if progress and (k % 3 == 0 or k == len(starts) - 1):
                progress(min(100, int((k + 1) * 100 / len(starts))))
    return n / SR


# ── GPU (DirectML) trong tiến trình riêng ──

def _dml_dir():
    from app.config import DATA_DIR
    return os.path.join(DATA_DIR, 'runtime', 'ort_dml')


def _gpu_enabled():
    if sys.platform != 'win32':
        return False
    try:
        from app.config import load_settings
        return bool(load_settings().get('gpu_separate', True))
    except Exception:
        return True


def ensure_gpu_runtime(log=print):
    """Cài onnxruntime-directml vào thư mục riêng (1 lần, ~25MB) → đường dẫn, lỗi → ''."""
    d = _dml_dir()
    if os.path.isfile(os.path.join(d, 'onnxruntime', 'capi', 'DirectML.dll')):
        return d
    log('   Tải bộ tăng tốc GPU cho tách giọng (~25MB, chỉ lần đầu)...')
    from core.utils import _HIDE
    tmp = d + '.part'
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--target', tmp, DML_PKG],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600, creationflags=_HIDE)
    if r.returncode != 0 or not os.path.isfile(os.path.join(tmp, 'onnxruntime', 'capi', 'DirectML.dll')):
        shutil.rmtree(tmp, ignore_errors=True)
        log(f"   [WARN] Không cài được bộ tăng tốc GPU ({(r.stderr or r.stdout or '').strip()[-120:]}) — tách bằng CPU", 'warn')
        return ''
    shutil.rmtree(d, ignore_errors=True)
    os.replace(tmp, d)
    return d


_GPU_BAD = {}


def _run_gpu(media, vp, mp_out, log, progress, should_stop):
    """→ True nếu tách xong bằng GPU; False → để CPU làm. Ném RuntimeError('Đã huỷ') khi bị dừng."""
    from core.utils import _HIDE, register_process, unregister_process
    rt = ensure_gpu_runtime(log)
    if not rt:
        return False
    worker = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'workers', 'vocal_sep_worker.py')
    env = {**os.environ, 'RF_ORT_DIR': rt, 'PYTHONIOENCODING': 'utf-8'}
    p = subprocess.Popen([sys.executable, worker, model_path(), media, vp, mp_out], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding='utf-8', errors='replace', env=env, creationflags=_HIDE)
    register_process(p)
    import threading
    err = []
    t_err = threading.Thread(target=lambda: err.append(p.stderr.read()), daemon=True)
    t_err.start()
    provider = ''
    try:
        for line in p.stdout:
            line = line.strip()
            if should_stop and should_stop():
                p.kill()
                raise RuntimeError('Đã huỷ')
            if line.startswith('PROV '):
                provider = line[5:]
                if provider != 'DmlExecutionProvider':
                    log('   [WARN] Card đồ hoạ không chạy được tăng tốc — tách bằng CPU', 'warn')
            elif line.startswith('PROG ') and progress:
                try:
                    progress(int(line[5:]))
                except ValueError:
                    pass
        p.wait()
    finally:
        unregister_process(p)
    t_err.join(timeout=5)
    if should_stop and should_stop():
        raise RuntimeError('Đã huỷ')
    if p.returncode == 0 and os.path.isfile(vp) and os.path.isfile(mp_out):
        return True
    _GPU_BAD['until'] = time.time() + 3600                    # GPU lỗi → 1 giờ tới tách bằng CPU luôn, khỏi thử lại
    if p.returncode == 3:                                     # máy không có card hỗ trợ (đã báo ở dòng PROV)
        return False
    log(f"   [WARN] Tách giọng bằng GPU lỗi ({''.join(err).strip()[-160:]}) — chuyển sang CPU", 'warn')
    return False


def _run_cpu(media, vp, mp_out, progress, should_stop):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    from core import perf
    so.intra_op_num_threads = max(1, min(16, perf.threads_for(2)))   # chạy song song Whisper / xoá chữ → nửa ngân sách CPU chung
    sess = ort.InferenceSession(model_path(), so, providers=['CPUExecutionProvider'])
    return run_core(sess, media, vp, mp_out, progress, should_stop) > 0


# ── bộ nhớ đệm theo file nguồn ──

def _cache_root():
    from app.config import DATA_DIR
    return os.path.join(DATA_DIR, 'cache', 'sep')


def _cache_dir(media):
    st = os.stat(media)
    key = hashlib.sha1(f'{os.path.abspath(media).lower()}|{st.st_size}|{int(st.st_mtime)}|{MODEL_NAME}'.encode()).hexdigest()[:20]
    return os.path.join(_cache_root(), key)


def _trim_cache(keep):
    """Giữ bộ nhớ đệm dưới CACHE_MAX_BYTES — xoá bản dùng lâu nhất (trừ bản đang dùng)."""
    import shutil
    root = _cache_root()
    try:
        items = []
        for name in os.listdir(root):
            d = os.path.join(root, name)
            if not os.path.isdir(d) or os.path.abspath(d) == os.path.abspath(keep):
                continue
            size = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d))
            items.append((os.path.getmtime(d), size, d))
        total = sum(s for (_, s, _) in items) + sum(os.path.getsize(os.path.join(keep, f)) for f in os.listdir(keep))
        for (_, size, d) in sorted(items):
            if total <= CACHE_MAX_BYTES:
                break
            shutil.rmtree(d, ignore_errors=True)
            total -= size
    except OSError:
        pass


def cached(media):
    """Đã tách sẵn file này chưa → (vocals, music) hoặc None."""
    try:
        d = _cache_dir(media)
    except OSError:
        return None
    (vp, mp_out) = (os.path.join(d, 'vocals.flac'), os.path.join(d, 'music.flac'))
    if os.path.isfile(os.path.join(d, 'done.json')) and os.path.isfile(vp) and os.path.isfile(mp_out):
        return (vp, mp_out)
    return None


def separate(media, out_dir=None, log=print, progress=None, should_stop=None):
    """Tách track tiếng của video/audio → (vocals, music) 44.1kHz stereo (FLAC, trong bộ nhớ đệm), hoặc (None, None) nếu không tách được.
    out_dir: giữ cho tương thích (kết quả nằm trong data/cache/sep để các job sau dùng lại)."""
    hit = cached(media)
    if hit:
        os.utime(os.path.dirname(hit[0]))
        log('   Tách giọng: dùng lại kết quả đã tách trước đó.')
        if progress:
            progress(100)
        return hit
    if not ensure_model(log):
        return (None, None)
    d = _cache_dir(media)
    os.makedirs(d, exist_ok=True)
    (vp, mp_out) = (os.path.join(d, 'vocals.flac'), os.path.join(d, 'music.flac'))
    t0 = time.time()
    how = 'CPU'
    ok = False
    if _gpu_enabled() and _GPU_BAD.get('until', 0) < time.time():
        log('   Tách giọng nói khỏi nhạc nền bằng GPU...')
        ok = _run_gpu(media, vp, mp_out, log, progress, should_stop)
        how = 'GPU' if ok else how
    if not ok:
        log('   Tách giọng nói khỏi nhạc nền bằng CPU (máy chậm có thể mất vài chục phút với phim dài)...')
        ok = _run_cpu(media, vp, mp_out, progress, should_stop)
    if not ok:
        return (None, None)
    took = time.time() - t0
    try:
        import soundfile as sf
        dur = sf.info(mp_out).duration
    except Exception:
        dur = 0
    with open(os.path.join(d, 'done.json'), 'w', encoding='utf-8') as f:
        json.dump({'source': media, 'model': MODEL_NAME, 'seconds': dur, 'took': round(took, 1), 'device': how}, f)
    log(f'   [OK] Tách giọng xong bằng {how} sau {took:.0f}s' + (f' (nhanh gấp {dur / max(took, 1e-3):.1f} lần thời lượng)' if dur else ''))
    _trim_cache(d)
    return (vp, mp_out)
