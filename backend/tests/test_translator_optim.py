"""Tối ưu lấy từ SubForge: (1) tách câu dài theo dấu câu + cân đều thời lượng, gộp mẩu vụn;
(2) dịch Google gộp dòng + chốt chặn số dòng + dò chữ Hán sót."""
from core import translator


# ───────────────────────── #1 Tách câu dài ─────────────────────────

def test_long_block_splits_at_sentences():
    # 1 block 18s, 3 câu → phải tách ra >1 mẩu, không câu nào quá dài, giữ nguyên chữ, mốc thời gian nối liền
    b = {'start': 0.0, 'end': 18.0,
         'text': '他说今天晚上我们一定要去那个地方看看。因为那里藏着我们一直在寻找的秘密。你相信我吗？'}
    out = translator._split_one_block(b)
    assert len(out) > 1
    assert ''.join(p['text'].replace(' ', '') for p in out) == b['text'].replace(' ', '')
    assert abs(out[0]['start'] - 0.0) < 1e-6 and abs(out[-1]['end'] - 18.0) < 1e-6
    for i in range(len(out) - 1):                       # nối liền, không chồng/hở
        assert abs(out[i]['end'] - out[i + 1]['start']) < 1e-6
    assert all(p['end'] - p['start'] <= 12.0 + 2.0 for p in out)   # mỗi mẩu ~ ≤ 12s (cho dư chút)


def test_short_block_untouched():
    b = {'start': 0.0, 'end': 4.0, 'text': '你好，今天天气不错。'}
    assert translator._split_one_block(b) == [b]


def test_long_block_no_punct_kept_when_not_extreme():
    # dài 14s nhưng không có dấu câu → không bịa mốc thời gian, giữ nguyên
    b = {'start': 0.0, 'end': 14.0, 'text': '啊' * 40}
    assert translator._split_one_block(b) == [b]


def test_number_not_split_at_comma():
    # "1,500" không được cắt giữa số; mẩu "3.5" cũng vậy
    parts = translator._clause_parts('他花了1,500元，买了3.5公斤的东西。')
    assert any('1,500' in p for p in parts)
    assert all('1,' != p[-2:] for p in parts)


def test_tiny_tail_merged():
    # mẩu cuối cực ngắn phải được gộp vào mẩu trước
    pieces = translator._balance_pieces(['这是一个比较长的句子用来测试分割', '好'], 10.0)
    assert '好' in pieces[-1] and len(pieces) == 1


# ───────────────────────── #4 Dịch Google gộp dòng ─────────────────────────

def test_batch_lines_roundtrip(monkeypatch):
    # gộp nhiều dòng 1 request (nối \n); echo giữ đúng số dòng → map đúng từng dòng
    calls = []
    monkeypatch.setattr(translator, '_google_translate',
                        lambda text, sl, tl: calls.append(text) or '\n'.join('T:' + l for l in text.split('\n')))
    out = translator._google_translate_lines(['a', 'b', 'c'], 'zh', 'vi')
    assert out == ['T:a', 'T:b', 'T:c']
    assert len(calls) == 1                              # cả 3 dòng trong 1 request


def test_batch_lines_fallback_on_count_mismatch(monkeypatch):
    # dịch trả về lệch số dòng → phải lùi về dịch TỪNG dòng (chống lệch dòng làm sai hết)
    calls = []

    def fake(text, sl, tl):
        calls.append(text)
        if '\n' in text:
            return 'chỉ một dòng'                       # cố tình nuốt mất dòng
        return 'X:' + text

    monkeypatch.setattr(translator, '_google_translate', fake)
    out = translator._google_translate_lines(['a', 'b'], 'zh', 'vi')
    assert out == ['X:a', 'X:b']
    assert calls[0] == 'a\nb' and calls[1:] == ['a', 'b']


def test_has_han():
    assert translator._has_han('还有中文')
    assert not translator._has_han('khong con chu Han 123 .,!')


def test_google_free_flags_han_residue(monkeypatch):
    # còn chữ Hán trong bản dịch tiếng Việt → ghi cảnh báo ra log
    monkeypatch.setattr(translator, '_google_translate', lambda text, sl, tl: '还没翻译')
    logs = []
    translator._translate_via_google_free([{'start': 0, 'end': 2, 'text': '你好'}], 'zh',
                                          lambda m: logs.append(m), '', '', target_lang='vi')
    assert any('còn chữ Hán' in m for m in logs)
