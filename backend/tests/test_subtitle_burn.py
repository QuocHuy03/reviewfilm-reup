"""Burn phụ đề không được làm hỏng/bỏ cảnh vì ký tự đặc biệt trong lời."""
import os

import pytest

from conftest import H, W, make_pattern_video, make_wav
from core.video_editor import _find_system_font, _process_one_scene


@pytest.mark.parametrize('text', ['Giảm 50% giá chỉ hôm nay', 'Đường dẫn C:\\phim\\tap1', 'Anh ấy nói: "đi thôi"'])
def test_special_chars_in_subtitle_render(tmp, text):
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [])
    scene = {'clip_start': 0.0, 'clip_end': 2.0, 'tts_duration': 2.0, 'tts_path': make_wav(os.path.join(tmp, 't.wav'), 2.0, freq=700),
             'voiceover': text, 'subtitle': text}
    out = os.path.join(tmp, 'out.mp4')
    ok = _process_one_scene(src, scene, out, f'{W}x{H}', 30, 0.1, True, print, video_total_duration=3.0,
                            font_path=_find_system_font('Segoe UI'))
    assert ok, f'cảnh bị bỏ vì phụ đề: {text!r}'
