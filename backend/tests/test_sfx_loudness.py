"""Hiệu ứng âm thanh tự động (vị trí vút / bùm) + chuẩn âm lượng -14 LUFS."""
import os
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from conftest import FFMPEG_EXE
from core import loudness, sfx


@pytest.fixture(autouse=True)
def sfx_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sfx, '_cache_dir', lambda: str(tmp_path))


def _scenes(spec):
    """spec: [(clip_start, clip_end, out_start)]"""
    return [{'clip_start': a, 'clip_end': b, 'out_start': o} for (a, b, o) in spec]


def test_assets_are_generated_and_audible():
    for name in ('whoosh', 'boom'):
        (x, sr) = sf.read(sfx.asset(name))
        assert sr == sfx.SR and len(x) == pytest.approx(sfx.asset_duration(name) * sr, abs=sr * 0.01)
        assert 0.5 < np.abs(x).max() <= 0.9                                  # đủ to, không bị cắt đỉnh
    (b, sr) = sf.read(sfx.asset('boom'))
    p = np.abs(np.fft.rfft(b)) ** 2
    f = np.fft.rfftfreq(len(b), 1 / sr)
    assert p[(f >= 150) & (f < 1000)].sum() / p.sum() > 0.1                 # loa điện thoại vẫn nghe "bùm"


def test_whoosh_only_on_jump_cuts_and_spaced():
    # cảnh 2 nối liền cảnh 1 (không vút) · cảnh 3 nhảy đoạn (vút) · cảnh 4 nhảy nhưng sát cảnh 3 (<6s, bỏ)
    sc = _scenes([(0, 10, 0), (10, 20, 10), (50, 60, 20), (90, 94, 24), (120, 130, 40)])
    fx = sfx.plan(sc, [-30, -30, -30, -30, -30], 60)
    whoosh = [f for f in fx if f['kind'] == 'whoosh']
    assert [round(f['start'] + sfx.WHOOSH_PEAK, 2) for f in whoosh] == [20.0, 40.0]   # đỉnh tiếng vút đúng điểm cắt


def test_boom_on_loudest_scene_after_intro_part():
    sc = _scenes([(0, 10, 0), (10, 20, 10), (20, 30, 20), (30, 40, 30), (40, 50, 40), (50, 60, 50)])
    energies = [-10, -30, -30, -30, -12, -30]                               # cảnh 1 to nhất nhưng ở 20% đầu → bỏ
    fx = sfx.plan(sc, energies, 60)
    booms = [f for f in fx if f['kind'] == 'boom']
    assert [f['start'] for f in booms] == [40.0]
    assert all(f['kind'] != 'whoosh' for f in fx)                           # các cảnh nối liền nhau → không vút


def test_no_boom_when_nothing_stands_out():
    sc = _scenes([(0, 10, 0), (10, 20, 10), (20, 30, 20), (30, 40, 30)])
    assert not [f for f in sfx.plan(sc, [-30, -30, -30, -30], 40) if f['kind'] == 'boom']


def _tone_video(path, db):
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=320x240:d=8', '-f', 'lavfi',
                    '-i', f'sine=frequency=300:duration=8,volume={db}dB', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', path], check=True)
    return path


@pytest.mark.parametrize('db', [-30, -3])
def test_normalize_reaches_target(tmp, db):
    p = _tone_video(os.path.join(tmp, 'v.mp4'), db)
    r = loudness.normalize_file(p, 'youtube', lambda *a: None)
    assert r and not r.get('skipped')
    m = loudness.measure(p)
    assert m['input_i'] == pytest.approx(-14, abs=1.0) and m['input_tp'] <= -1.0


def test_already_normalized_is_left_alone(tmp):
    p = _tone_video(os.path.join(tmp, 'v.mp4'), -20)
    loudness.normalize_file(p, 'youtube', lambda *a: None)
    before = os.path.getmtime(p)
    assert loudness.normalize_file(p, 'youtube', lambda *a: None)['skipped']
    assert os.path.getmtime(p) == before


def test_silent_or_off_is_untouched(tmp):
    p = os.path.join(tmp, 's.mp4')
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=320x240:d=3', '-f', 'lavfi',
                    '-i', 'anullsrc=r=44100:cl=mono', '-c:v', 'libx264', '-c:a', 'aac', '-t', '3', p], check=True)
    shutil.copy(p, p + '.bak')
    assert loudness.normalize_file(p, 'youtube', lambda *a: None) is None
    assert loudness.normalize_file(p, 'off', lambda *a: None) is None
    assert open(p, 'rb').read() == open(p + '.bak', 'rb').read()
