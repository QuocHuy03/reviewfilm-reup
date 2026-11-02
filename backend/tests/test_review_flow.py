"""Review: cảnh sát nhau không đứng hình / tắt nhạc; nhạc nền chỉ tách đoạn được dùng vẫn tra đúng chỗ."""
import os
import re
import subprocess

from conftest import make_wav
from core.utils import FFMPEG_EXE
from core.video_editor import _process_one_scene, plan_review_clips
from core.vocal_sep import locate, merge_ranges


def test_close_scenes_are_pushed_not_frozen():
    sc = [{'clip_start': x, 'tts_duration': 10} for x in (20, 26, 60, 64, 100)]
    plan = plan_review_clips(sc, 600)
    assert [p[1] for p in plan] == [None] * 5, 'không cảnh nào phải chiếu chậm / đứng hình'
    starts = [p[0] for p in plan]
    assert starts[1] >= starts[0] + 10 and starts[3] >= starts[2] + 10, 'cảnh sau bắt đầu sau khi cảnh trước hết hình'
    assert starts[1] - 26 <= 20 and starts[0] == 20 and starts[4] == 100


def test_drift_is_bounded_and_film_end_fits():
    dense = [{'clip_start': x, 'tts_duration': 12} for x in range(0, 40, 2)]
    assert all(st - x <= 20.01 for ((st, _), x) in zip(plan_review_clips(dense, 600), range(0, 40, 2)))
    assert plan_review_clips([{'clip_start': 590, 'tts_duration': 12}], 600)[0][0] <= 600 - 12.12 + 1e-6


def test_locate_and_merge():
    rs = merge_ranges([(10, 20), (22, 30), (100, 110)], pad=1.0, join=4.0)
    assert rs == [(9.0, 31.0), (99.0, 111.0)]
    segs = [(9.0, 31.0, 0.0), (99.0, 111.0, 23.0)]
    assert locate(segs, 12, 5) == 3.0 and locate(segs, 100, 10) == 24.0
    assert locate(segs, 28, 10) is None


def test_music_keeps_playing_when_picture_runs_out(tmp):
    """Lời 6s, hình chỉ có 3s (cảnh sau sát bên) → hình chậm / giữ khung, nhạc nền vẫn chạy đủ 6s (trước: tắt ở giây 3)."""
    src = os.path.join(tmp, 'src.mp4')
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=25', '-f', 'lavfi',
                    '-i', 'sine=frequency=330:sample_rate=44100', '-t', '12', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', src], check=True)
    tts = make_wav(os.path.join(tmp, 'vo.wav'), 6.0)                    # lời đọc = lặng → tiếng ra chỉ là tiếng gốc
    scene = {'clip_start': 1.0, 'clip_end': 4.0, 'tts_duration': 6.0, 'tts_path': tts, 'voiceover': 'x', 'review_cap': 3.0}
    out = os.path.join(tmp, 'o.mp4')
    assert _process_one_scene(src, scene, out, '320x240', 25, 0.5, False, print, i=0, video_total_duration=12.0)
    r = subprocess.run([FFMPEG_EXE, '-v', 'info', '-i', out, '-af', 'silencedetect=n=-40dB:d=0.3', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert not re.findall(r'silence_start: ([\d.]+)', r.stderr), 'tiếng gốc / nhạc nền bị tắt giữa cảnh'
