"""Review đọc liền: nhóm cảnh, cắt lại đúng chỗ nghỉ; khoảng nghỉ theo dấu câu."""
import numpy as np

from core.tts_engine import flow_groups, split_at_pauses
from core.video_editor import REVIEW_TAIL_END, REVIEW_TAIL_MID, review_tail

SR = 16000


def voice(*parts):
    """parts: (giây có tiếng | -giây nghỉ)."""
    rng = np.random.default_rng(1)
    return np.concatenate([(rng.standard_normal(int(p * SR)) * 0.2 if p > 0 else np.zeros(int(-p * SR))).astype(np.float32) for p in parts])


def test_groups_stop_at_size_gaps_and_open_sentences():
    sc = [{'voiceover': f'Câu {i}.'} for i in range(7)]
    assert flow_groups(sc) == [[0, 1, 2], [3, 4, 5], [6]]
    sc[1]['voiceover'] = ''                                     # cảnh trống: không nối qua
    assert flow_groups(sc)[0] == [0]
    sc = [{'voiceover': 'Chưa hết câu,'}, {'voiceover': 'hết câu.'}]
    assert flow_groups(sc) == [[0], [1]]                        # không có chỗ nghỉ chắc chắn để cắt
    assert [len(g) for g in flow_groups([{'voiceover': 'x' * 400 + '.'} for _ in range(3)])] == [1, 1, 1]


def test_split_picks_scene_pause_not_longer_comma_pause():
    # cảnh 1 = 3s + nghỉ dấu phẩy DÀI 0.4s + 3s · nghỉ hết cảnh 0.2s · cảnh 2 = 6s
    x = voice(3, -0.4, 3, -0.2, 6)
    cuts = split_at_pauses(x, SR, [100, 100])
    assert cuts and abs(cuts[0] / SR - 6.5) < 0.15


def test_split_gives_up_when_no_pause_near():
    assert split_at_pauses(voice(12), SR, [100, 100]) is None
    assert split_at_pauses(voice(1, -0.3, 11), SR, [100, 100]) is None      # chỗ nghỉ xa vị trí dự kiến


def test_scene_pause_follows_punctuation():
    assert review_tail({'voiceover': 'Hết câu.'}) == REVIEW_TAIL_END
    assert review_tail({'voiceover': 'Thật sao?'}) == REVIEW_TAIL_END
    assert review_tail({'voiceover': 'chưa hết,'}) == REVIEW_TAIL_MID
    assert review_tail({}) == REVIEW_TAIL_MID
