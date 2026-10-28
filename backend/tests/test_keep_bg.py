"""Giữ nhạc nền gốc (đã tách giọng) khi dựng Review/Reup: đoạn có lời Việt dùng nhạc nền (không lẫn giọng gốc),
đoạn để tiếng gốc 100% vẫn dùng tiếng gốc thật, cắt đúng chỗ, giọng Việt chỉ hạ nhạc nhẹ (không tắt hẳn)."""
import os
import re
import subprocess

import pytest

from conftest import FFMPEG_EXE, make_pattern_video, make_wav
from core.video_editor import _process_one_scene


def _band_db(path, freq, ss=0.2, t=1.2):
    """Âm lượng quanh 1 tần số (lọc dải hẹp) — phân biệt 'giọng gốc' 440Hz / 'nhạc' 220Hz / 660Hz / giọng Việt 1500Hz."""
    r = subprocess.run([FFMPEG_EXE, '-ss', str(ss), '-t', str(t), '-i', path, '-af',
                        f'bandpass=f={freq}:width_type=q:width=8,bandpass=f={freq}:width_type=q:width=8,volumedetect', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    m = re.search(r'mean_volume: (-?[\d.]+) dB', r.stderr)
    assert m, r.stderr[-300:]
    return float(m.group(1))


@pytest.fixture
def src(tmp):
    return make_pattern_video(os.path.join(tmp, 'src.mp4'), [], dur=5.0)          # tiếng gốc = sine 440Hz


@pytest.fixture
def bg(tmp):
    """'Nhạc nền đã tách': 0–2.5s là 220Hz, 2.5–5s là 660Hz (stereo, như file tách giọng)."""
    p = os.path.join(tmp, 'music.flac')
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=2.5', '-f', 'lavfi',
                    '-i', 'sine=frequency=660:duration=2.5', '-filter_complex', '[0:a][1:a]concat=n=2:v=0:a=1,pan=stereo|c0=c0|c1=c0[a]',
                    '-map', '[a]', '-ar', '44100', p], check=True)
    return p


def _scene(tmp, start, voice_freq=None, **kw):
    v = make_wav(os.path.join(tmp, f'v{start}.wav'), 2.0, freq=voice_freq)
    return {'clip_start': start, 'clip_end': start + 2.0, 'tts_duration': 2.0, 'tts_path': v, 'voiceover': 'x', **kw}


def test_voiced_scene_uses_background_not_original(tmp, src, bg):
    out = os.path.join(tmp, 'a.mp4')
    assert _process_one_scene(src, _scene(tmp, 0.0), out, '640x360', 30, 0.08, False, print, video_total_duration=5.0,
                              bg_audio=bg, bg_volume=0.9)
    assert _band_db(out, 220) > _band_db(out, 440) + 20          # có nhạc nền, không còn "giọng gốc"


def test_background_is_cut_at_scene_position(tmp, src, bg):
    out = os.path.join(tmp, 'b.mp4')
    assert _process_one_scene(src, _scene(tmp, 2.8), out, '640x360', 30, 0.08, False, print, video_total_duration=5.0,
                              bg_audio=bg, bg_volume=0.9)
    assert _band_db(out, 660, ss=0.2, t=1.0) > _band_db(out, 220, ss=0.2, t=1.0) + 20   # đoạn 2.8s+ là 660Hz


def test_full_original_gap_ignores_background(tmp, src, bg):
    out = os.path.join(tmp, 'c.mp4')
    gap = _scene(tmp, 0.0, is_reup=True, orig_volume=1.0)
    assert _process_one_scene(src, gap, out, '640x360', 30, 0.08, False, print, video_total_duration=5.0, bg_audio=bg, bg_volume=0.9)
    assert _band_db(out, 440) > _band_db(out, 220) + 20          # khoảng trống không lời Việt: tiếng gốc thật


def test_voice_only_dips_background_gently(tmp, src, bg):
    quiet = os.path.join(tmp, 'q.mp4')
    loud = os.path.join(tmp, 'l.mp4')
    assert _process_one_scene(src, _scene(tmp, 0.0), quiet, '640x360', 30, 0.08, False, print, video_total_duration=5.0,
                              bg_audio=bg, bg_volume=0.9)
    assert _process_one_scene(src, _scene(tmp, 0.0, voice_freq=1500), loud, '640x360', 30, 0.08, False, print,
                              video_total_duration=5.0, bg_audio=bg, bg_volume=0.9)
    dip = _band_db(quiet, 220) - _band_db(loud, 220)
    assert 1.0 < dip < 12.0                                       # nhạc hạ nhẹ dưới lời, không bị nén mất
    assert _band_db(loud, 1500) > _band_db(loud, 220) - 3         # lời Việt vẫn rõ


def test_no_background_keeps_old_behaviour(tmp, src):
    out = os.path.join(tmp, 'd.mp4')
    assert _process_one_scene(src, _scene(tmp, 0.0), out, '640x360', 30, 0.08, False, print, video_total_duration=5.0)
    assert _band_db(out, 440) > -60                               # vẫn là tiếng gốc hạ nhỏ như cũ
