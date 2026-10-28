"""Hiệu ứng âm thanh tự động cho video Review: "vút" khi chuyển cảnh nhảy đoạn, "bùm" ở đoạn cao trào.

Âm thanh TỰ SINH bằng numpy (không dùng file của ai → không dính bản quyền), lưu 1 lần ở data/cache/sfx:
  whoosh — tiếng xì lọc dải quét trầm → cao → trầm, to dần rồi tắt (đỉnh ở ~0.38s → canh đúng điểm cắt)
  boom   — tiếng trầm rơi 60→32Hz tắt dần + tiếng đập ngắn ở đầu (kiểu "impact" trailer phim)
Vị trí:
  vút — chỗ cắt mà cảnh sau KHÔNG nối tiếp cảnh trước trong phim gốc (nhảy đoạn), cách nhau ≥ MIN_GAP giây
  bùm — các cảnh có tiếng gốc mạnh nhất (nhạc dồn / hành động — thường là cao trào), sau 20% đầu video, cách nhau ≥ 30s
"""
import os
import subprocess

import numpy as np

SR = 44100
VERSION = 1
WHOOSH_PEAK = 0.38          # giây — đỉnh tiếng vút trong file (đặt vào đúng điểm cắt)
MIN_GAP = 6.0               # 2 hiệu ứng gần nhau tối thiểu (giây) — dày quá nghe rối
VOLUME = {'whoosh': 0.32, 'boom': 0.55}


def _cache_dir():
    from app.config import DATA_DIR
    d = os.path.join(DATA_DIR, 'cache', 'sfx')
    os.makedirs(d, exist_ok=True)
    return d


def _whoosh(rng):
    n = int(SR * 0.75)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n).astype(np.float32)
    # lọc dải quét: trộn các dải tần theo thời gian (FFT từng khung ngắn)
    frame, hop = 1024, 256
    out = np.zeros(n + frame, np.float32)
    win = np.hanning(frame).astype(np.float32)
    freqs = np.fft.rfftfreq(frame, 1 / SR)
    for s in range(0, n - frame, hop):
        x = (s + frame / 2) / n
        fc = 250 * (14 ** np.sin(np.pi * min(1.0, x / 0.85)))          # 250Hz → ~3.5kHz → về lại
        bw = fc * 0.9
        spec = np.fft.rfft(noise[s:s + frame] * win)
        spec *= np.exp(-0.5 * ((freqs - fc) / bw) ** 2)
        out[s:s + frame] += np.fft.irfft(spec, n=frame).astype(np.float32) * win
    out = out[:n]
    env = np.where(t < WHOOSH_PEAK, (t / WHOOSH_PEAK) ** 2.2, np.exp(-(t - WHOOSH_PEAK) * 9))
    return out * env


def _boom(rng):
    n = int(SR * 1.6)
    t = np.arange(n) / SR
    f = 32 + 28 * np.exp(-t * 6)                                      # 60Hz rơi về 32Hz
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) * np.exp(-t * 2.6)
    # hoà âm bậc cao + "thịch" tầm trung: loa điện thoại / laptop không phát được <150Hz, thiếu phần này là "bùm" câm
    for (h, a, d) in ((2, 0.5, 4.5), (3, 0.32, 6.5), (4, 0.2, 9.0)):
        body += a * np.sin(h * phase) * np.exp(-t * d)
    thud = 1.2 * (np.sin(2 * np.pi * 170 * t) + 0.5 * np.sin(2 * np.pi * 340 * t)) * np.exp(-t * 7.5)
    hit = rng.standard_normal(n) * np.exp(-t * 40)                    # tiếng đập đầu
    k = np.exp(-np.arange(24) / 5.0)
    hit = np.convolve(hit, k / k.sum(), mode='same')                  # cắt bớt chói (lọc thấp ~1.5kHz)
    sig = body + thud + 1.4 * hit
    sig *= np.minimum(1.0, t / 0.003)                                 # không bị "click" ở đầu
    # bão hoà cho dày; ~75% năng lượng <150Hz (rung), ~22% tầm trung (loa nhỏ vẫn nghe "thịch")
    return np.tanh(sig * 2.4) / np.tanh(2.4)


def asset(name):
    """Đường dẫn wav hiệu ứng (tự sinh nếu chưa có)."""
    import soundfile as sf
    p = os.path.join(_cache_dir(), f'{name}_v{VERSION}.wav')
    if not os.path.isfile(p):
        rng = np.random.default_rng(7)
        x = {'whoosh': _whoosh, 'boom': _boom}[name](rng)
        x = x / (np.abs(x).max() + 1e-9) * 0.89
        tmp = p + '.tmp.wav'
        sf.write(tmp, x.astype(np.float32), SR, subtype='PCM_16')
        os.replace(tmp, p)
    return p


def asset_duration(name):
    return {'whoosh': 0.75, 'boom': 1.6}[name]


def scene_energy(source, scenes, sr=4000):
    """RMS tiếng gốc (dB) trong đoạn [clip_start, clip_end] của từng cảnh — đọc âm thanh 1 lần ở 4kHz mono (nhẹ)."""
    from core.utils import FFMPEG_EXE, _HIDE
    r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-i', source, '-vn', '-ac', '1', '-ar', str(sr), '-f', 's16le', '-'],
                       capture_output=True, creationflags=_HIDE)
    a = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768 if r.returncode == 0 else np.zeros(0, np.float32)
    out = []
    for s in scenes:
        (i, j) = (int(float(s.get('clip_start') or 0) * sr), int(float(s.get('clip_end') or 0) * sr))
        seg = a[max(0, i):max(i + 1, j)]
        out.append(float(20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-6)) if seg.size else -120.0)
    return out


def plan(scenes, energies, total, intro=0.0):
    """→ danh sách đoạn hiệu ứng [{'source','start','duration','track':'sfx','volume','kind'}] theo mốc out_start trên video xuất.
    scenes: các cảnh ĐÃ dựng, theo thứ tự xuất, có out_start (giây trên video xuất) + clip_start/clip_end (giây phim gốc)."""
    if len(scenes) < 2 or total <= 0:
        return []
    picks = []                                           # (thời điểm, loại)
    # bùm: cảnh tiếng gốc mạnh nhất, sau 20% video, cách nhau ≥ 30s; số lượng theo độ dài (1 / 3 phút, tối đa 4)
    n_boom = max(1, min(4, int(total // 180) + 1))
    order = sorted(range(1, len(scenes)), key=lambda k: energies[k] if k < len(energies) else -120, reverse=True)
    loud_ref = np.median(energies) if energies else -60
    for k in order:
        if len([p for p in picks if p[1] == 'boom']) >= n_boom:
            break
        t = float(scenes[k].get('out_start') or 0)
        if t < max(intro, total * 0.2) or t > total - 3 or energies[k] < loud_ref + 3:
            continue
        if all(abs(t - p[0]) >= 30 for p in picks):
            picks.append((t, 'boom'))
    # vút: chỗ cắt nhảy đoạn trong phim gốc (cảnh sau không nối liền cảnh trước)
    for k in range(1, len(scenes)):
        (prev, cur) = (scenes[k - 1], scenes[k])
        jump = abs(float(cur.get('clip_start') or 0) - float(prev.get('clip_end') or 0))
        t = float(cur.get('out_start') or 0)
        if jump < 2.0 or t < WHOOSH_PEAK + 0.05 or t > total - 1:
            continue
        if all(abs(t - p[0]) >= MIN_GAP for p in picks):
            picks.append((t, 'whoosh'))
    out = []
    for (t, kind) in sorted(picks):
        start = t - WHOOSH_PEAK if kind == 'whoosh' else t
        out.append({'source': asset(kind), 'start': round(max(0.0, start), 3), 'duration': asset_duration(kind), 'track': 'sfx',
                    'volume': VOLUME[kind], 'kind': kind})
    return out
