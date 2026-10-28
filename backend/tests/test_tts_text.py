from core.tts_text import clean_for_tts, expand_abbreviations, prepare_tts_text


def test_clean_strips_junk_at_edges():
    assert clean_for_tts('- Anh ấy đã đi rồi,') == 'Anh ấy đã đi rồi'
    assert clean_for_tts('﻿• Cô ấy khóc;  ') == 'Cô ấy khóc'
    assert clean_for_tts('Hắn nói: "') == 'Hắn nói'
    assert clean_for_tts('Thật sao?!') == 'Thật sao?!'           # dấu kết câu giữ nguyên
    assert clean_for_tts('Cô ấy nói "đi đi".') == 'Cô ấy nói "đi đi".'
    assert clean_for_tts('a​b||c') == 'ab c'
    assert clean_for_tts(' , ') == ','                            # toàn rác → giữ câu gốc, không làm mất câu


def test_abbreviations_whole_word_uppercase_only():
    assert expand_abbreviations('Anh làm HLV ở TP.HCM') == 'Anh làm huấn luyện viên ở Thành phố Hồ Chí Minh'
    assert expand_abbreviations('Về VN rồi') == 'Về Việt Nam rồi'
    assert expand_abbreviations('vn, VNA, VN2, abc.VN') == 'vn, VNA, VN2, abc.VN'   # chữ thường / dính chữ khác → giữ


def test_prepare_combines_numbers():
    assert prepare_tts_text('- Có 2 HLV,') == 'Có hai huấn luyện viên'
