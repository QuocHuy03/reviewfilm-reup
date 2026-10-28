"""Chuẩn âm lượng video xuất theo mức nền tảng khuyến nghị (EBU R128 / loudnorm 2 lượt).

YouTube / TikTok / Facebook đều chuẩn về ~-14 LUFS: video to hơn bị nền tảng tự hạ, nhỏ hơn thì nghe lép so với video khác.
  Lượt 1 đo độ to thật (LUFS, đỉnh thật, độ biến thiên) → lượt 2 chỉnh TUYẾN TÍNH (không nén động, giữ nguyên chất tiếng);
  chỉ khi đỉnh sẽ vượt -1.5 dBTP mới để loudnorm nén nhẹ.
Hình chép nguyên (-c:v copy) → nhanh, không giảm chất lượng hình. Đã đạt chuẩn (±0.7 LU) thì bỏ qua, không mã hoá lại.
"""
import json
import os
import re
import subprocess

from core.utils import FFMPEG_EXE, FFPROBE_EXE, _HIDE, run_subprocess

TARGETS = {'youtube': -14.0}          # LUFS
TRUE_PEAK = -1.5
LRA = 11
TOLERANCE = 0.7


def measure(path, timeout=1800):
    """→ {'input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset'} (float) hoặc None (không có tiếng / lỗi)."""
    r = run_subprocess([FFMPEG_EXE, '-hide_banner', '-nostats', '-i', path, '-vn', '-af',
                        f'loudnorm=I=-14:TP={TRUE_PEAK}:LRA={LRA}:print_format=json', '-f', 'null', '-'],
                       timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', (r.stderr if r else '') or '')
    if r is None or r.returncode != 0 or not m:
        return None
    try:
        d = json.loads(m.group(0))
        out = {k: float(d[k]) for k in ('input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset')}
    except (KeyError, ValueError):
        return None
    if out['input_i'] < -70:                   # im lặng hoàn toàn → không có gì để chỉnh
        return None
    return out


def _audio_info(path):
    r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=sample_rate,channels',
                        '-of', 'json', path], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
    try:
        s = json.loads(r.stdout)['streams'][0]
        return int(s.get('sample_rate') or 48000), int(s.get('channels') or 2)
    except (ValueError, KeyError, IndexError):
        return 48000, 2


def normalize_file(path, target='youtube', log=print):
    """Chuẩn âm lượng file video tại chỗ. → dict kết quả {'before', 'after'?, 'skipped'?} hoặc None (lỗi / không có tiếng).
    Lỗi giữa chừng không làm hỏng file gốc."""
    lufs = TARGETS.get(target)
    if lufs is None or not os.path.isfile(path):
        return None
    m = measure(path)
    if not m:
        return None
    if abs(m['input_i'] - lufs) <= TOLERANCE and m['input_tp'] <= TRUE_PEAK + 0.3:
        log(f"   Âm lượng đã chuẩn ({m['input_i']:.1f} LUFS) — giữ nguyên")
        return {'before': m['input_i'], 'skipped': True}
    (sr, ch) = _audio_info(path)
    af = (f"loudnorm=I={lufs}:TP={TRUE_PEAK}:LRA={LRA}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
          f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    tmp = os.path.splitext(path)[0] + '.loudnorm' + os.path.splitext(path)[1]
    r = run_subprocess([FFMPEG_EXE, '-y', '-v', 'error', '-i', path, '-map', '0', '-c', 'copy', '-c:a', 'aac', '-b:a', '192k',
                        '-aac_coder', 'twoloop',             # lượt mã hoá CUỐI ra file giao → bộ chất lượng cao nhất
                        '-af', af, '-ar', str(sr), '-ac', str(ch), '-movflags', '+faststart', tmp],
                       timeout=1800, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    if r is None or r.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) < 1000:
        if os.path.isfile(tmp):
            os.remove(tmp)
        log(f"   [WARN] Chuẩn âm lượng lỗi — giữ nguyên âm thanh ({(getattr(r, 'stderr', '') or '')[-160:]})", 'warn')
        return None
    os.replace(tmp, path)
    log(f"   Chuẩn âm lượng: {m['input_i']:.1f} → {lufs:.0f} LUFS (mức YouTube / TikTok)")
    return {'before': m['input_i'], 'after': lufs}
