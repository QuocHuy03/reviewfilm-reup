"""Khung 9:16 nền mờ · logo chuyển động / logo chữ · che phụ đề kiểu phản chiếu."""
import os
import subprocess

import numpy as np

from conftest import grab_gray, make_pattern_video, make_wav
from core.utils import FFMPEG_EXE
from core.video_editor import _process_one_scene, watermark_xy


def _render(tmp, src, res, dur=2.0, scene_extra=None, **kw):
    tts = make_wav(os.path.join(tmp, 'tts.wav'), dur, freq=880)
    scene = {'clip_start': 0.0, 'clip_end': dur, 'tts_duration': dur, 'tts_path': tts, 'voiceover': 'x', **(scene_extra or {})}
    out = os.path.join(tmp, 'out.mp4')
    assert _process_one_scene(src, scene, out, res, 30, 0.1, False, print, i=0, video_total_duration=3.0, **kw)
    return out


def test_vertical_frame_blur_background(tmp):
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [(0.0, 0.0, 1.0, 1.0)])     # sọc trắng phủ cả khung
    (w, h) = (360, 640)
    blur = grab_gray(_render(tmp, src, f'{w}x{h}'), 1.0, w, h)
    assert blur[:h // 6].mean() > 40, 'trên / dưới phải là nền mờ của chính video, không phải viền đen'
    black = grab_gray(_render(tmp, src, f'{w}x{h}', frame_bg='black'), 1.0, w, h)
    assert black[:h // 6].mean() < 8


def _logo(tmp):
    p = os.path.join(tmp, 'logo.png')
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=white:s=64x64', '-frames:v', '1', p], check=True)
    return p


def _where(frame):
    (ys, xs) = np.where(frame > 200)
    assert len(xs) > 50, 'không thấy logo'
    (H, W) = frame.shape
    return ('right' if xs.mean() > W / 2 else 'left', 'bottom' if ys.mean() > H / 2 else 'top')


def test_logo_hop_moves_on_output_timeline(tmp):
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [])                      # video đen
    # cảnh bắt đầu ở giây 14 của video xuất → giây 15 (t=1.0 trong clip) logo nhảy từ góc trên-phải sang dưới-phải
    out = _render(tmp, src, '640x360', dur=2.0, scene_extra={'out_start': 14.0}, watermark_path=_logo(tmp),
                  watermark_corner='Trên-Phải', watermark_opacity=1.0, watermark_motion='hop')
    assert _where(grab_gray(out, 0.5)) == ('right', 'top')
    assert _where(grab_gray(out, 1.5)) == ('right', 'bottom')


def test_text_logo_drawn(tmp):
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [])
    out = _render(tmp, src, '640x360', watermark_text='@KenhReview', watermark_corner='Dưới-Trái', watermark_opacity=1.0,
                  watermark_size_pct=20)
    assert _where(grab_gray(out, 1.0)) == ('left', 'bottom')


def test_bounce_starts_in_chosen_corner():
    (x, y) = watermark_xy('bounce', 'Trên-Trái', 10, 10)
    ev = lambda e, W=640, w=64, H=360, h=64: eval(e.strip("'").replace('max', 'max').replace('mod', '_mod'),
                                                   {'t': 0.0, 'W': W, 'w': w, 'H': H, 'h': h, 'abs': abs, 'max': max,
                                                    '_mod': lambda a, b: a % b})
    assert abs(ev(x) - 10) < 1e-6 and abs(ev(y) - 10) < 1e-6


def test_reflect_cover_hides_subtitle(tmp):
    sub = (0.10, 0.80, 0.90, 0.90)
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [sub])                   # phía trên phụ đề là nền đen trơn
    cover = [[10, 80, 80, 10]]
    region = (int(0.81 * 360), int(0.89 * 360), int(0.12 * 640), int(0.88 * 640))      # (hàng trên, dưới, cột trái, phải)
    refl = grab_gray(_render(tmp, src, '640x360', remove_old_sub=True, sub_cover_boxes=cover, box_style='reflect'), 1.0)
    blur = grab_gray(_render(tmp, src, '640x360', remove_old_sub=True, sub_cover_boxes=cover), 1.0)
    (a, b, c, d) = region
    assert (refl[a:b, c:d] > 200).sum() == 0, 'phản chiếu chưa che hết chữ'
    assert refl[a:b, c:d].mean() < 25, 'vùng che phải giống nền trơn phía trên (đen), không thành khối xám'
    assert blur[a:b, c:d].mean() > refl[a:b, c:d].mean() + 20


def test_vietsub_reflect_box_chain(tmp):
    from app.features.jobs.vietsub import _box_chain
    sub = (0.10, 0.80, 0.90, 0.90)
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [sub])
    (chain, last) = _box_chain('0:v', [10, 80, 80, 10], 640, 360, 'reflect', [(0.0, 9.0)], 'sb')
    out = os.path.join(tmp, 'vs.mp4')
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-i', src, '-filter_complex', chain, '-map', f'[{last}]', '-t', '2',
                    '-c:v', 'libx264', '-qp', '0', '-pix_fmt', 'yuv444p', out], check=True)
    f = grab_gray(out, 1.0)
    reg = f[int(0.81 * 360):int(0.89 * 360), int(0.12 * 640):int(0.88 * 640)]
    assert (reg > 200).sum() == 0 and reg.mean() < 25
