"""Mix âm thanh không được tự hạ âm lượng giọng đọc / tiếng gốc (amix mặc định chia đều cho số input)."""
import os
import re
import subprocess

import pytest

from conftest import FFMPEG_EXE, make_pattern_video, make_wav
from core.video_editor import _mix_bgm, _mix_multi_audio, _process_one_scene


def _db(path, ss=0.1, t=0.8):
    r = subprocess.run([FFMPEG_EXE, '-ss', str(ss), '-t', str(t), '-i', path, '-af', 'volumedetect', '-f', 'null', '-'],
                       capture_output=True, text=True)
    m = re.search(r'mean_volume: (-?[\d.]+) dB', r.stderr)
    assert m, f'volumedetect không đọc được {path}: {r.stderr[-300:]}'
    return float(m.group(1))


@pytest.fixture
def voiced_clip(tmp):
    """Clip 2s chỉ có giọng đọc (tiếng gốc tắt) — mốc so sánh."""
    src = os.path.join(tmp, 'src.mp4')
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=640x360:d=3', '-f', 'lavfi',
                    '-i', 'anullsrc=r=44100:cl=mono', '-t', '3', '-c:v', 'libx264', '-c:a', 'aac', src], check=True)
    voice = make_wav(os.path.join(tmp, 'v.wav'), 2.0, freq=880)
    out = os.path.join(tmp, 'clip.mp4')
    assert _process_one_scene(src, {'clip_start': 0.0, 'clip_end': 2.0, 'tts_duration': 2.0, 'tts_path': voice, 'voiceover': 'x'},
                              out, '640x360', 30, 0.0, False, print, video_total_duration=3.0)
    return out


def test_bgm_does_not_halve_voice(tmp, voiced_clip):
    out = os.path.join(tmp, 'bgm.mp4')
    assert _mix_bgm(voiced_clip, make_wav(os.path.join(tmp, 'bgm.wav'), 5.0), out, 0.05, print)
    assert _db(out) == pytest.approx(_db(voiced_clip), abs=1.0)


def test_timeline_sfx_do_not_duck_voice(tmp, voiced_clip):
    clips = [{'source': make_wav(os.path.join(tmp, f's{i}.wav'), 1.0), 'duration': 1.0, 'start': 0.0, 'track': 'sfx', 'volume': 1.0}
             for i in range(4)]
    out = os.path.join(tmp, 'sfx.mp4')
    assert _mix_multi_audio(voiced_clip, clips, out, print)
    assert _db(out) == pytest.approx(_db(voiced_clip), abs=1.0)


def test_reup_gap_keeps_original_audio_level(tmp):
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [], dur=3.0)
    gap = {'clip_start': 0.0, 'clip_end': 2.0, 'tts_duration': 2.0, 'tts_path': make_wav(os.path.join(tmp, 'sil.wav'), 2.0),
           'voiceover': '', 'is_reup': True, 'orig_volume': 1.0}
    out = os.path.join(tmp, 'gap.mp4')
    assert _process_one_scene(src, gap, out, '640x360', 30, 1.0, False, print, video_total_duration=3.0)
    assert _db(out) == pytest.approx(_db(src), abs=1.5)
