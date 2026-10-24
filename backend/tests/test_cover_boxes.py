"""Vùng che phụ đề gốc / logo phải nằm ĐÚNG chỗ người dùng kéo trên khung xem trước.

Khung xem trước (CoverBoxEditor / Monitor) hiện hình gốc co vào khung video xuất (object-contain = scale + viền đen),
không lật gương, không phóng 3%, không zoom theo cảnh → toạ độ % của vùng che là toạ độ trên khung đó.
"""
import os

import numpy as np
import pytest

from conftest import H, W, grab_gray, make_pattern_video, make_wav
from core.video_editor import _process_one_scene


def _render(tmp, src, boxes, mirror=False, scene_extra=None, src_dur=3.0):
    tts = make_wav(os.path.join(tmp, 'tts.wav'), 2.0, freq=880)
    scene = {'clip_start': 0.5, 'clip_end': 2.5, 'tts_duration': 2.0, 'tts_path': tts, 'voiceover': 'x', **(scene_extra or {})}
    out = os.path.join(tmp, 'out.mp4')
    ok = _process_one_scene(src, scene, out, f'{W}x{H}', 30, 0.1, False, print, i=0, video_total_duration=src_dur,
                            remove_old_sub=True, sub_cover_boxes=boxes, mirror_video=mirror)
    assert ok
    return out


def _sharp_pixels(frame, rect):
    """Số điểm ảnh còn trắng sắc (chữ chưa bị che) trong vùng rect (tỉ lệ 0..1 của khung xuất)."""
    (x1, y1, x2, y2) = rect
    roi = frame[int(y1 * H):int(y2 * H), int(x1 * W):int(x2 * W)]
    return int((roi > 200).sum())


def test_box_covers_text_same_aspect(tmp):
    text = (0.10, 0.82, 0.90, 0.92)
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [text])
    frame = grab_gray(_render(tmp, src, [[10, 82, 80, 10]]), 1.0)
    # mở rộng vùng đo thêm 3% mỗi phía: chữ lọt ra mép vùng che cũng tính là lỗi
    assert _sharp_pixels(frame, (0.07, 0.79, 0.93, 0.95)) == 0


def test_box_covers_logo_when_mirrored(tmp):
    logo = (0.05, 0.05, 0.30, 0.15)
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [logo])
    frame = grab_gray(_render(tmp, src, [[5, 5, 25, 10]], mirror=True), 1.0)
    assert int((frame > 200).sum()) == 0, 'logo bị lật sang phía kia nhưng vùng che vẫn ở chỗ cũ'


def test_box_covers_text_letterboxed_vertical_source(tmp):
    # nguồn dọc 9:16 vào khung ngang 16:9 → hình co lại giữa khung, hai bên viền đen
    (sw, sh) = (360, 640)
    text_src = (0.10, 0.80, 0.90, 0.88)
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [text_src], w=sw, h=sh)
    disp_w = sw * H / sh
    off = (W - disp_w) / 2
    bx = (off + text_src[0] * disp_w) / W * 100
    bw = (text_src[2] - text_src[0]) * disp_w / W * 100
    box = [round(bx, 1), text_src[1] * 100, round(bw, 1) + 0.2, (text_src[3] - text_src[1]) * 100]
    frame = grab_gray(_render(tmp, src, [box]), 1.0)
    assert int((frame > 200).sum()) == 0


@pytest.mark.parametrize('scale', [1.2, 0.8])
def test_box_follows_per_scene_zoom(tmp, scale):
    text = (0.20, 0.40, 0.80, 0.50)        # giữa khung để zoom 1.2 không đẩy chữ ra ngoài
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [text])
    frame = grab_gray(_render(tmp, src, [[20, 40, 60, 10]], scene_extra={'_video_scale': scale}), 1.0)
    assert int((frame > 200).sum()) == 0


def test_unboxed_text_stays_sharp(tmp):
    """Đối chứng: chữ ngoài vùng che phải còn nguyên (không làm mờ cả khung)."""
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [(0.10, 0.82, 0.90, 0.92), (0.30, 0.20, 0.70, 0.30)])
    frame = grab_gray(_render(tmp, src, [[10, 82, 80, 10]]), 1.0)
    assert _sharp_pixels(frame, (0.30, 0.20, 0.70, 0.30)) > 1000
    assert np.all(frame[int(0.82 * H):int(0.92 * H), int(0.15 * W):int(0.85 * W)] <= 200)
