"""Che chữ Trung tự quét (text_regions): mỗi vùng che ĐÚNG khung & ĐÚNG lúc, không gộp thành khối to.

Lỗi cũ: vùng góc trái (chữ khác nhau hiện lần lượt) bị cộng dồn thành 1 khối ~50% × 20% khung, che suốt cả phim.
"""
import os
import subprocess

import numpy as np

from conftest import H, W, grab_gray, make_pattern_video, make_wav
from core import text_cover
from core.utils import FFMPEG_EXE
from core.video_editor import _process_one_scene, _src_text_blur_chain, group_boxes, src_dims


def _render(tmp, src, regions, style='blur', start=0.0, dur=2.0, src_dur=3.0):
    tts = make_wav(os.path.join(tmp, 'tts.wav'), dur, freq=880)
    scene = {'clip_start': start, 'clip_end': start + dur, 'tts_duration': dur, 'tts_path': tts, 'voiceover': 'x'}
    out = os.path.join(tmp, 'out.mp4')
    assert _process_one_scene(src, scene, out, f'{W}x{H}', 30, 0.1, False, print, i=0, video_total_duration=src_dur,
                              text_regions=regions, cover_style=style)
    return out


def _sharp(frame, rect):
    (x1, y1, x2, y2) = rect
    return int((frame[int(y1 * H):int(y2 * H), int(x1 * W):int(x2 * W)] > 200).sum())


def _shrink(rect, m=0.03):
    """Bỏ mép 3% (khung xuất còn bị phóng 3% chống trùng lặp)."""
    return (rect[0] + m, rect[1] + m, rect[2] - m, rect[3] - m)


def test_each_region_exact_not_merged(tmp):
    top = (0.05, 0.05, 0.25, 0.12)          # chữ góc trái
    near = (0.05, 0.20, 0.25, 0.27)         # chữ khác ngay dưới — KHÔNG có vùng che (cũ: bị gộp chung khối)
    sub = (0.30, 0.80, 0.70, 0.90)
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [top, near, sub])
    regions = [{'box': list(top), 't_start': 0, 't_end': 9}, {'box': list(sub), 't_start': 0, 't_end': 9}]
    frame = grab_gray(_render(tmp, src, regions), 1.0)
    assert _sharp(frame, (0.03, 0.03, 0.27, 0.14)) == 0, 'chữ góc trái chưa được che kín'
    assert _sharp(frame, (0.28, 0.78, 0.72, 0.92)) == 0, 'phụ đề chưa được che kín'
    assert _sharp(frame, _shrink(near, 0.02)) > 300, 'vùng che phình ra làm mờ cả chữ không cần che'


def test_region_only_while_visible(tmp):
    box = (0.30, 0.40, 0.70, 0.55)
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [box])
    out = _render(tmp, src, [{'box': list(box), 't_start': 1.5, 't_end': 9}], dur=3.0)
    assert _sharp(grab_gray(out, 0.5), _shrink(box)) > 300, 'che cả lúc chữ chưa hiện'
    assert _sharp(grab_gray(out, 2.2), (0.28, 0.38, 0.72, 0.57)) == 0


def test_erase_style_covers(tmp):
    box = (0.10, 0.80, 0.90, 0.92)
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [box])
    frame = grab_gray(_render(tmp, src, [{'box': list(box), 't_start': 0, 't_end': 9}], style='erase'), 1.0)
    assert _sharp(frame, (0.08, 0.78, 0.92, 0.94)) == 0


def test_rotated_phone_video(tmp):
    """Video dọc lưu ngang + cờ xoay 90° (điện thoại quay) → vùng che vẫn đúng chỗ, khung không méo."""
    box = (0.10, 0.75, 0.90, 0.85)          # theo khung đã xoay (dọc)
    upright = make_pattern_video(os.path.join(tmp, 'up.mp4'), [box], w=360, h=640)
    stored = os.path.join(tmp, 'stored.mp4')    # lưu nằm ngang 640x360 + cờ xoay → ffmpeg đọc ra lại khung dọc
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-i', upright, '-vf', 'transpose=2', '-c:v', 'libx264', '-qp', '0',
                    '-pix_fmt', 'yuv444p', '-c:a', 'copy', os.path.join(tmp, 'flat.mp4')], check=True)
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-display_rotation', '-90', '-i', os.path.join(tmp, 'flat.mp4'),
                    '-c', 'copy', stored], check=True)
    assert src_dims(stored) == (360, 640)
    frame = grab_gray(_render(tmp, stored, [{'box': list(box), 't_start': 0, 't_end': 9}]), 1.0)
    assert int((frame > 200).sum()) == 0


def test_many_regions_one_blur_layer():
    regions = [{'box': [0.01 * i, 0.5, 0.01 * i + 0.05, 0.55], 't_start': i, 't_end': i + 1} for i in range(60)]
    (chain, last) = _src_text_blur_chain(regions, 0.0, 100.0, src_size=(1920, 1080))
    assert chain.count('gblur') == 1 and chain.count('drawbox=x=') == 60 and last


def test_group_boxes_keeps_far_text_apart():
    logo = ([0.0, 0.0, 0.15, 0.08], [(0, 1000)])
    subs = [([0.30 + 0.01 * (i % 5), 0.82, 0.70 - 0.01 * (i % 3), 0.90], [(i * 3, i * 3 + 2)]) for i in range(40)]
    groups = group_boxes([logo] + subs, max_groups=4)
    assert len(groups) <= 4
    g_logo = [g for g in groups if g[0][1] < 0.1]
    assert len(g_logo) == 1 and g_logo[0][0] == [0.0, 0.0, 0.15, 0.08], 'logo bị gộp với phụ đề'


def test_scan_tracks_do_not_chain_different_text():
    # góc trái: dòng chữ A (0-10s) rồi chữ B dài hơn, thấp hơn (10-20s); logo đứng yên suốt
    dets = [(t, [0.0, 0.0, 0.15, 0.06]) for t in range(0, 10, 2)]
    dets += [(t, [0.0, 0.07, 0.45, 0.14]) for t in range(10, 20, 2)]
    dets += [(t, [0.85, 0.02, 0.98, 0.07]) for t in range(0, 20, 2)]
    tracks = text_cover._tracks(dets, 2.0)
    boxes = sorted(tuple(round(v, 2) for v in tr['box']) for tr in tracks)
    assert (0.0, 0.0, 0.15, 0.06) in boxes and (0.0, 0.07, 0.45, 0.14) in boxes and len(tracks) == 3
    assert np.isclose(max(tr['last'] - tr['first'] for tr in tracks), 18)


def _scan_setup(tmp, monkeypatch):
    import time as _t
    from core import vocal_sep
    monkeypatch.setattr(text_cover, '_cache_path', lambda v, i: os.path.join(tmp, f'scan_{_t.time()}.json'))
    monkeypatch.setattr(text_cover, 'GPU_MIN_FRAMES', 1)
    monkeypatch.setattr(vocal_sep, '_gpu_enabled', lambda: True)
    text_cover._GPU_BAD.clear()
    return make_pattern_video(os.path.join(tmp, 'src.mp4'), [(0.10, 0.80, 0.90, 0.88)], dur=4.0)


def test_scan_gpu_unavailable_falls_back_to_cpu(tmp, monkeypatch):
    """Máy không chạy được DirectML (worker báo mã 3) → quét bằng CPU, ra kết quả như thường, 1 giờ tới không thử GPU nữa."""
    src = _scan_setup(tmp, monkeypatch)
    from core import vocal_sep
    monkeypatch.setattr(vocal_sep, 'ensure_gpu_runtime', lambda log=print: os.path.join(tmp, 'khong_co_dml'))
    logs = []
    regs = text_cover.scan(src, None, 1.0, log_fn=lambda m, *a: logs.append(m))
    assert isinstance(regs, list)
    assert text_cover._GPU_BAD.get('until', 0) > 0
    assert not any('lỗi' in m for m in logs), logs                # mã 3 = chuyển CPU im lặng, không báo lỗi


def test_scan_gpu_partial_failure_resumes_on_cpu(tmp, monkeypatch):
    """GPU lỗi giữa chừng sau khi đã quét 1 phần → CPU chỉ quét phần còn thiếu."""
    src = _scan_setup(tmp, monkeypatch)
    seen = []

    def fake_gpu(video, todo, interval, geom, cache, log_fn, should_stop, progress, total):
        import json as _j
        _j.dump({'scanned': [[0.0, 2.0]], 'dets': []}, open(cache, 'w'))
        return 'fail'
    real = text_cover._detect

    def spy(video, todo, *a, **k):
        seen.append(todo)
        return real(video, todo, *a, **k)
    monkeypatch.setattr(text_cover, '_scan_gpu', fake_gpu)
    monkeypatch.setattr(text_cover, '_detect', spy)
    text_cover.scan(src, None, 1.0, log_fn=lambda *a: None)
    assert seen and all(a >= 2.0 for (a, _) in seen[0]), seen
