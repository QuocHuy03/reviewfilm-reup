"""Phụ đề / dựng video khi ngôn ngữ đầu ra không phải tiếng Việt (target_lang)."""
import os

import numpy as np

from conftest import grab_gray, make_pattern_video, make_wav
from core.video_editor import (_find_system_font, _fit_subtitle, _font_covers, _process_one_scene, _split_subtitle_chunks,
                               script_font)

ZH = '他说今天晚上我们一定要去那个地方看看，因为那里可能藏着我们一直在寻找的秘密。你相信我吗？我们没有时间了。'


def test_chinese_wraps_by_characters_within_max_lines():
    (wrapped, size) = _fit_subtitle(ZH, 1920, 1080, max_lines=2)
    lines = wrapped.split('\n')
    assert 1 < len(lines) <= 2 and all(lines)
    assert ''.join(lines) == ZH.replace(' ', '')                     # không mất / thêm chữ
    assert max(len(l) for l in lines) * size <= 1920 * 0.82 + size    # mỗi chữ Hán ~1 ô vuông → vừa bề ngang


def test_chinese_chunks_split_at_punctuation():
    chunks = _split_subtitle_chunks(ZH, 28, 2)
    assert len(chunks) >= 2 and ''.join(chunks) == ZH
    assert all(c[-1] in '，。？' for c in chunks[:-1])


def test_vietnamese_unchanged():
    t = 'Hôm nay chúng ta sẽ cùng xem một bộ phim cực kỳ hấp dẫn và đầy bất ngờ cho tất cả mọi người'
    (wrapped, _) = _fit_subtitle(t, 1920, 1080)
    assert ' '.join(wrapped.split()) == t and all(not l.startswith(' ') for l in wrapped.split('\n'))


def test_thai_never_splits_leading_vowel():
    th = 'วันนี้เราจะไปดูหนังที่สนุกมากด้วยกันกับเพื่อนๆ ของเราทุกคนที่โรงหนังใหม่ใกล้บ้าน'
    (wrapped, _) = _fit_subtitle(th, 1080, 1920)
    for line in wrapped.split('\n')[:-1]:
        assert line[-1] not in 'เแโใไ'


def test_script_font_has_glyphs():
    zh = script_font('zh')
    assert zh and _font_covers(zh, 'zh')
    assert not _font_covers(_find_system_font('Segoe UI'), 'zh')     # font La-tinh mặc định → phải đổi font


def _render(tmp, text, **kw):
    tts = make_wav(os.path.join(tmp, 'tts.wav'), 2.0, freq=880)
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [])
    scene = {'clip_start': 0.0, 'clip_end': 2.0, 'tts_duration': 2.0, 'tts_path': tts, 'voiceover': text, 'subtitle': text}
    out = os.path.join(tmp, f"out_{kw.get('target_lang', 'vi')}.mp4")
    assert _process_one_scene(src, scene, out, '640x360', 30, 0.1, True, print, i=0, video_total_duration=3.0,
                              font_path=kw.pop('font_path'), **kw)
    return grab_gray(out, 1.0)


def test_chinese_subtitle_renders_real_glyphs(tmp):
    """Font chữ Hán vẽ đúng nét chữ; font La-tinh vẽ ô vuông (tofu) — 2 kết quả phải khác hẳn nhau."""
    good = _render(tmp, '我们没有时间了', font_path=script_font('zh'), target_lang='zh')
    lit = good > 200
    assert lit.sum() > 300, 'không thấy chữ phụ đề'
    tofu = _render(tmp, '我们没有时间了', font_path=_find_system_font('Segoe UI'))
    assert np.abs(good.astype(int) - tofu.astype(int)).sum() > 50000
