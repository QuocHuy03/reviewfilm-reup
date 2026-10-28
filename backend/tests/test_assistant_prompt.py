"""Prompt Trợ lý AI: đủ các phần, đúng thứ tự, không còn chỗ trống chưa điền, cắt hội thoại đúng giới hạn."""
from app.features.assistant.guide import APP_GUIDE
from app.features.assistant.router import MAX_TURNS, AskReq, Msg, build_prompt


def _ask(*texts, **kw):
    msgs = [Msg(role='user' if i % 2 == 0 else 'assistant', content=t) for (i, t) in enumerate(texts)]
    return AskReq(messages=msgs, **kw)


def test_prompt_sections_in_order():
    p = build_prompt(_ask('Làm sao lồng tiếng?', page='create'))
    order = ['# VAI TRÒ', '# NGUỒN SỰ THẬT', '# CÁCH TRẢ LỜI', '# CHẨN ĐOÁN', '# VĂN PHONG', '# GIỚI HẠN',
             '===== CẨM NANG APP =====', '===== NGỮ CẢNH HIỆN TẠI =====', '===== CUỘC TRÒ CHUYỆN =====', '===== NHIỆM VỤ =====']
    pos = [p.index(x) for x in order]
    assert pos == sorted(pos)
    assert '{version}' not in p
    assert 'Tạo video' in p                       # tên trang đang mở
    assert 'Người dùng: Làm sao lồng tiếng?' in p


def test_guide_covers_current_features():
    for key in ('Phụ đề song ngữ', 'Xuất thêm bản dọc 9:16', 'Xuất phụ đề', 'khoá làn', 'con mắt', 'Thông báo khi job xong',
                'TRỢ LÝ AI', 'Tải lại N lỗi', 'poster'):
        assert key.lower() in APP_GUIDE.lower(), key


def test_history_is_trimmed():
    texts = [f'câu {i}' for i in range(40)]
    p = build_prompt(_ask(*texts))
    convo = p.split('===== CUỘC TRÒ CHUYỆN =====')[1]
    assert 'câu 39' in convo and f'câu {39 - MAX_TURNS}' not in convo


def test_unknown_job_is_ignored():
    p = build_prompt(_ask('lỗi gì vậy', job_id='khong-ton-tai'))
    assert 'Job đang mở' not in p
