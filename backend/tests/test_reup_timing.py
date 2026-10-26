"""Reup (lồng tiếng): hình phải chạy tốc độ thật, lời Việt bắt đầu đúng lúc câu gốc bắt đầu, và không lệch cộng dồn."""
import os

import pytest

from conftest import duration, make_pattern_video, make_wav
from core.video_editor import build_review_video


def _scene(tmp, i, start, end, tts_dur):
    p = make_wav(os.path.join(tmp, f'tts{i}.wav'), tts_dur, freq=600 + 50 * i)
    return {'clip_start': start, 'clip_end': end, 'voiceover': f'cau {i}', 'subtitle': f'cau {i}', 'tts_path': p, 'tts_duration': tts_dur}


def _build(tmp, src, scenes, **kw):
    out = os.path.join(tmp, 'out.mp4')
    os.makedirs(os.path.join(tmp, 'work'), exist_ok=True)
    r = build_review_video(scenes, src, out, os.path.join(tmp, 'work'), target_resolution='640x360', burn_subtitles=False,
                           log_fn=lambda *_: None, **kw)
    assert r == out
    return out


def test_reup_short_voice_does_not_fast_forward_video(tmp):
    """Lời Việt 1s cho câu gốc 4s → hình KHÔNG được tua nhanh 2.5x; video reup dài bằng video gốc."""
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [], dur=6.0)
    out = _build(tmp, src, [_scene(tmp, 0, 1.0, 5.0, 1.0)], is_reup=True)
    assert duration(out) == pytest.approx(6.0, abs=0.15)


def test_reup_srt_matches_rendered_clip_lengths(tmp):
    """Lời dài hơn câu gốc (bị nén atempo 1.18 trong lúc dựng) → mốc SRT phải tính theo độ dài clip THẬT."""
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [], dur=8.0)
    scenes = [_scene(tmp, 0, 0.0, 2.0, 3.0), _scene(tmp, 1, 4.0, 6.0, 2.0)]
    out = _build(tmp, src, scenes, is_reup=True)
    srt = open(os.path.splitext(out)[0] + '.srt', encoding='utf-8').read()
    total = duration(out)
    # sau câu 2 (lời 2s = hình 2s, tốc độ thường) còn đoạn hình gốc 6→8s → câu 2 bắt đầu ở (tổng − 2 − 2)
    cue2_start = srt.strip().split('\n\n')[-1].split('\n')[1].split(' --> ')[0]
    (h, m, s) = cue2_start.replace(',', '.').split(':')
    assert int(h) * 3600 + int(m) * 60 + float(s) == pytest.approx(total - 4.0, abs=0.08)



def test_reup_fit_rules():
    """Luật căn câu Reup: ngắn → giữ câu gốc; dài vừa → mượn khoảng lặng; quá dài → giọng nhanh ≤1.35× rồi hình chậm ≤1.25×."""
    from core.video_editor import reup_fit
    assert reup_fit(4.0, 6.0, 1.0) == (4.0, 4.0, 1.0, 1.0)                     # lời ngắn: hình 1x, không tua nhanh
    assert reup_fit(2.0, 4.0, 3.0) == (3.0, 3.0, 1.0, 1.0)                     # mượn 1s khoảng lặng phía sau
    (span, out, pts, at) = reup_fit(2.0, 2.5, 3.0)                             # 3s lời / 2.5s chỗ → giọng 1.2×, hình 1x
    assert pts == 1.0 and at == pytest.approx(1.2) and out == pytest.approx(2.5)
    (span, out, pts, at) = reup_fit(2.0, 2.0, 4.0)                             # 4s lời / 2s chỗ → giọng 1.35×, hình chậm 1.25×, giữ khung
    assert at == pytest.approx(1.35) and pts == pytest.approx(1.25) and out == pytest.approx(4.0 / 1.35)


def test_reup_borrowed_silence_keeps_total_length(tmp):
    """Lời dài hơn câu gốc nhưng vừa khoảng lặng phía sau → mượn khoảng lặng: tổng video vẫn bằng video gốc, hình không chậm."""
    src = make_pattern_video(os.path.join(tmp, 'src.mp4'), [], dur=8.0)
    out = _build(tmp, src, [_scene(tmp, 0, 1.0, 3.0, 3.5), _scene(tmp, 1, 5.0, 6.0, 1.0)], is_reup=True)
    assert duration(out) == pytest.approx(8.0, abs=0.15)
