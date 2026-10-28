"""Đọc phụ đề cứng: gộp khung thành câu và bỏ chữ cố định — KHÔNG được bỏ câu thoại ngắn hay lặp ("什么", "走吧").

Lỗi cũ: câu nào xuất hiện > 6 lần trong cả phim bị coi là watermark và bỏ → phim dài mất các câu thoại ngắn hay gặp.
"""
from core.hardsub import _build_cues

STEP = 0.2


def _frames(spans):
    """spans = [(bắt đầu, kết thúc, chữ)] → khung mẫu mỗi STEP giây trên toàn bộ khoảng thời gian."""
    end = max(e for (_, e, _) in spans)
    out = []
    for i in range(int(end / STEP) + 2):
        t = round(i * STEP, 3)
        txt = next((x for (s, e, x) in spans if s <= t < e), '')
        out.append((t, txt, (0.3, 0.8, 0.7, 0.9) if txt else None))
    return out


def _count(cues, text):
    return sum(1 for c in cues if c['text'] == text)


def test_short_repeated_dialogue_is_kept():
    spans = []
    t = 0.0
    for i in range(25):                                    # "什么" 25 lần, mỗi lần 1.4s, xen câu khác
        spans.append((t, t + 1.4, '什么'))
        spans.append((t + 2.0, t + 4.0, f'第{i}句不同的台词'))
        t += 30.0
    cues = _build_cues(_frames(spans), STEP, t)
    assert _count(cues, '什么') == 25
    assert len(cues) == 50


def test_static_overlay_between_lines_is_dropped():
    # tên kênh nằm trong dải phụ đề, chỉ đọc được lúc không có thoại → nhiều mẩu, tổng thời gian chiếm phần lớn video
    spans = []
    t = 0.0
    for i in range(20):
        spans.append((t, t + 8.0, '关注频道'))
        spans.append((t + 8.0, t + 10.0, f'台词{i}号'))
        t += 10.0
    cues = _build_cues(_frames(spans), STEP, t)
    assert _count(cues, '关注频道') == 0
    assert len(cues) == 20


def test_long_single_cue_and_long_repeats_dropped():
    spans = [(0.0, 25.0, '片头字幕标题')]                     # 1 lần > 20s liền
    t = 30.0
    for i in range(6):                                     # chú thích 7s lặp 6 lần (tổng < 15% video)
        spans.append((t, t + 7.0, '本故事纯属虚构'))
        spans.append((t + 8.0, t + 9.5, f'台词{i}号'))
        t += 60.0
    cues = _build_cues(_frames(spans), STEP, 600.0)
    assert _count(cues, '片头字幕标题') == 0
    assert _count(cues, '本故事纯属虚构') == 0
    assert len(cues) == 6


def test_merge_votes_and_timing():
    # cùng 1 câu, 1 khung đọc sai 1 chữ → gộp thành 1 dòng, lấy bản đọc nhiều nhất; thời gian = khung đầu → khung cuối + step
    frames = [(0.0, '', None), (0.2, '我们走吧朋友', None), (0.4, '我们走吧朋友', None), (0.6, '我们走巴朋友', None),
              (0.8, '我们走吧朋友', None), (1.0, '', None)]
    cues = _build_cues(frames, STEP, 1.2)
    assert cues == [{'start': 0.2, 'end': 1.0, 'text': '我们走吧朋友'}]
