"""Tách giọng nói khỏi nhạc nền / tiếng động (UVR MDX-Net, model Kim_Vocal_2 ONNX ~64MB, chạy CPU).
Lồng tiếng chuyên nghiệp bỏ hẳn giọng gốc mà vẫn giữ nhạc nền & hiệu ứng — thay vì chỉ hạ nhỏ cả track gốc."""
import os
import subprocess
import wave

import numpy as np

MODEL_NAME = 'Kim_Vocal_2.onnx'
MODEL_URL = 'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/Kim_Vocal_2.onnx'
SR = 44100
N_FFT, HOP, DIM_F, DIM_T = 7680, 1024, 3072, 256
COMPENSATE = 1.009                     # hệ số bù của model (theo UVR) khi lấy nhạc nền = gốc − giọng
CHUNK = HOP * (DIM_T - 1)              # 261120 mẫu ≈ 5.9 giây mỗi lượt
TRIM = N_FFT // 2
GEN = CHUNK - 2 * TRIM                 # phần giữa mỗi lượt được giữ (bỏ mép để không vỡ tiếng nối)


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


def _stft(x):
    """x [2, CHUNK] → [1, 4, DIM_F, DIM_T] (thực / ảo từng kênh) — giống torch.stft(center=True)."""
    xp = np.pad(x, ((0, 0), (TRIM, TRIM)), mode='reflect')
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(DIM_T)[:, None]
    spec = np.fft.rfft(xp[:, idx] * _WIN, axis=-1)           # [2, DIM_T, bins]
    spec = spec.transpose(0, 2, 1)[:, :DIM_F]                 # [2, DIM_F, DIM_T]
    out = np.stack([spec.real, spec.imag], axis=1)            # [2, 2, DIM_F, DIM_T]
    return out.reshape(1, 4, DIM_F, DIM_T).astype(np.float32)


def _istft(s):
    """[1, 4, DIM_F, DIM_T] → [2, CHUNK]."""
    s = s.reshape(2, 2, DIM_F, DIM_T)
    spec = s[:, 0] + 1j * s[:, 1]
    full = np.zeros((2, N_FFT // 2 + 1, DIM_T), dtype=np.complex64)
    full[:, :DIM_F] = spec
    frames = np.fft.irfft(full.transpose(0, 2, 1), n=N_FFT, axis=-1) * _WIN   # [2, DIM_T, N_FFT]
    length = N_FFT + HOP * (DIM_T - 1)
    out = np.zeros((2, length), dtype=np.float32)
    norm = np.zeros(length, dtype=np.float32)
    for t in range(DIM_T):
        out[:, t * HOP:t * HOP + N_FFT] += frames[:, t]
        norm[t * HOP:t * HOP + N_FFT] += _WIN ** 2
    out /= np.maximum(norm, 1e-8)
    return out[:, TRIM:TRIM + CHUNK]


def separate(media, out_dir, log=print, progress=None, should_stop=None):
    """Tách track tiếng của video/audio → (vocals.wav, music.wav) 44.1kHz stereo, hoặc (None, None) nếu không tách được."""
    from core.utils import FFMPEG_EXE, _HIDE
    mp = ensure_model(log)
    if not mp:
        return (None, None)
    import onnxruntime as ort
    r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-i', media, '-vn', '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'],
                       capture_output=True, creationflags=_HIDE)
    mix = np.frombuffer(r.stdout, dtype=np.float32)
    if r.returncode != 0 or mix.size < SR:
        return (None, None)
    mix = mix.reshape(-1, 2).T                                 # [2, n]
    n = mix.shape[1]
    so = ort.SessionOptions()
    from core import perf
    so.intra_op_num_threads = max(1, min(16, perf.threads_for(2)))   # chạy song song Whisper / xoá chữ → nửa ngân sách CPU chung
    sess = ort.InferenceSession(mp, so, providers=['CPUExecutionProvider'])
    pad = GEN - n % GEN
    mixp = np.concatenate([np.zeros((2, TRIM), np.float32), mix, np.zeros((2, pad + TRIM), np.float32)], axis=1)
    os.makedirs(out_dir, exist_ok=True)
    (vp, mp_out) = (os.path.join(out_dir, 'vocals.wav'), os.path.join(out_dir, 'music.wav'))
    total = (n + pad) // GEN
    log(f'   Tách giọng nói khỏi nhạc nền ({n / SR / 60:.1f} phút âm thanh)...')
    with wave.open(vp, 'wb') as wv, wave.open(mp_out, 'wb') as wm:
        for w in (wv, wm):
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
        done = 0
        for (k, i) in enumerate(range(0, n + pad, GEN)):
            if should_stop and should_stop():
                raise RuntimeError('Đã huỷ')
            seg = mixp[:, i:i + CHUNK]
            spec = _stft(seg)
            voc = _istft(sess.run(None, {'input': spec})[0])[:, TRIM:-TRIM]
            keep = min(GEN, n - done)
            voc = voc[:, :keep] * COMPENSATE
            orig = mix[:, done:done + keep]
            music = orig - voc
            for (w, a) in ((wv, voc), (wm, music)):
                w.writeframes((np.clip(a.T, -1, 1) * 32767).astype('<i2').tobytes())
            done += keep
            if progress and (k % 5 == 0 or k == total - 1):
                progress(min(100, int((k + 1) * 100 / total)))
    return (vp, mp_out)
