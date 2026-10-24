import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils import FFMPEG_EXE, FFPROBE_EXE  # noqa: E402

W, H = 640, 360


def make_pattern_video(path, rects, w=W, h=H, dur=3.0, fps=30):
    """Video đen có các ô 'chữ cứng' (sọc trắng/đen 2px — làm mờ thì thành xám, không còn điểm trắng)
    tại rects = [(x1, y1, x2, y2) theo tỉ lệ 0..1]. Kèm tiếng sine để có luồng audio."""
    img = np.zeros((h, w), dtype=np.uint8)
    for (x1, y1, x2, y2) in rects:
        (a, b, c, d) = (int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h))
        block = np.zeros((d - b, c - a), dtype=np.uint8)
        block[:, ::4] = 255
        block[:, 1::4] = 255
        img[b:d, a:c] = block
    raw = path + '.gray'
    img.tofile(raw)
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'gray', '-s', f'{w}x{h}', '-r', str(fps),
                    '-stream_loop', '-1', '-i', raw, '-f', 'lavfi', '-i', f'sine=frequency=440:duration={dur}',
                    '-t', str(dur), '-c:v', 'libx264', '-qp', '0', '-pix_fmt', 'yuv444p', '-c:a', 'aac', '-shortest', path],
                   check=True)
    os.remove(raw)
    return path


def make_wav(path, dur, freq=None, sr=44100):
    src = f'sine=frequency={freq}:duration={dur}' if freq else f'anullsrc=r={sr}:cl=mono'
    cmd = [FFMPEG_EXE, '-y', '-v', 'error', '-f', 'lavfi', '-i', src, '-t', str(dur), '-ar', str(sr), '-ac', '1', path]
    subprocess.run(cmd, check=True)
    return path


def grab_gray(path, t, w=W, h=H):
    r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-ss', str(t), '-i', path, '-frames:v', '1', '-vf', f'scale={w}:{h}',
                        '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(h, w)


def duration(path, stream=None):
    args = [FFPROBE_EXE, '-v', 'error']
    if stream:
        args += ['-select_streams', stream, '-show_entries', 'stream=duration']
    else:
        args += ['-show_entries', 'format=duration']
    r = subprocess.run(args + ['-of', 'csv=p=0', path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip().splitlines()[0])


@pytest.fixture
def tmp(tmp_path):
    return str(tmp_path)
