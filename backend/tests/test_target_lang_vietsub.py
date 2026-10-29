"""Ngôn ngữ đầu ra (target_lang) ở Dịch phụ đề / hậu kỳ / bài đăng: tiếng Việt giữ nguyên, Trung / Nhật / Thái chia theo ký tự."""
import os

from app.features.jobs import postedit, publish, vietsub
from core import user_glossary


def test_word_count_units():
    assert postedit.word_count('Xin chào các bạn, hôm nay') == 6          # tiếng Việt: đếm từ như cũ
    assert postedit.word_count('Hello world 2024') == 3
    assert postedit.word_count('大家好，今天我们') == 7                     # chữ Hán: mỗi chữ 1 đơn vị, bỏ dấu câu
    assert postedit.word_count('สวัสดี') == 4                               # dấu nguyên âm / thanh Thái không tính riêng


def test_rates_and_units():
    assert postedit.units_per_sec('vi') == postedit.WORDS_PER_SEC
    assert postedit.units_per_sec('vi', 4.3) == 4.3
    assert 2.0 < postedit.units_per_sec('en') < 3.5                         # từ / giây tiếng Anh
    assert postedit.units_per_sec('zh') > 3                                 # ký tự / giây
    assert postedit.unit_name('vi') == 'từ' and postedit.unit_name('ja') == 'ký tự'
    assert postedit.target_words(10, target_lang='zh') > postedit.target_words(10, target_lang='en')


def test_prompts_vi_unchanged_en_forced():
    fmt = dict(kind='review phim', wps=3.8, tol=25, extra='', scenes='[]')
    vi = postedit.SYSTEM_PROMPT.format(**fmt, lang=postedit.lang_label('vi'), unit='từ', lang_rule=postedit.lang_rule('vi'),
                                       connectors=' ("rồi", "lúc này", "không ngờ")')
    assert 'kênh YouTube review phim tiếng Việt' in vi and 'English' not in vi and '9. NGÔN NGỮ' not in vi
    en = postedit.SYSTEM_PROMPT.format(**fmt, lang=postedit.lang_label('en'), unit='từ', lang_rule=postedit.lang_rule('en'),
                                       connectors='')
    assert 'tiếng Anh (English)' in en and 'Write every voiceover/subtitle in English' in en
    (lang, rules, thumb) = publish._lang_prompt('vi')
    assert lang == 'tiếng Việt' and rules.startswith('Tiếng Việt có dấu') and thumb == '5 từ'
    (lang, rules, thumb) = publish._lang_prompt('ja')
    assert 'Japanese' in lang and 'Japanese' in rules and thumb == '10 ký tự'


def test_split_by_parts_chinese():
    parts = [[0, 1, '甲乙丙'], [1, 2, '丁戊己庚']]
    out = vietsub._split_by_parts('大家好，今天我们一起看电影。', parts)
    assert len(out) == 2 and all(out) and ''.join(out) == '大家好，今天我们一起看电影。'
    assert out[0].endswith('，')                                            # cắt ngay sau dấu câu Trung
    # tiếng Việt: chia theo từ như cũ
    assert vietsub._split_by_parts('Xin chào các bạn, hôm nay xem phim nhé', parts) == ['Xin chào các bạn,', 'hôm nay xem phim nhé']


def test_bare_and_tokens():
    assert vietsub._bare('你好，世界!') == vietsub._bare('你好 世界')
    assert vietsub._bare('Xin chào, bạn!') == ['xin', 'chào', 'bạn']
    (toks, sep) = vietsub._tokens('สวัสดี ทุกคน')
    assert sep == '' and 'วั' in toks                                        # dấu Thái dính ký tự trước, không bị cắt rời


def test_ass_font_and_wrap(tmp_path):
    style = vietsub._sub_style({})
    path = str(tmp_path / 's.ass')
    long_zh = '大家好，今天我们一起来看一部非常精彩的电影，这部电影讲述了一个感人的故事。'
    vietsub._write_ass(path, [{'start': 0, 'end': 2, 'text': long_zh}], style, 1280, 720, target_lang='zh')
    txt = open(path, encoding='utf-8-sig').read()
    assert 'Microsoft YaHei' in txt and '\\N' in txt                       # font đủ chữ Hán + tự xuống dòng
    path2 = str(tmp_path / 'v.ass')
    vietsub._write_ass(path2, [{'start': 0, 'end': 2, 'text': 'Xin chào các bạn'}], style, 1280, 720)
    assert 'Microsoft YaHei' not in open(path2, encoding='utf-8-sig').read()


def test_hashtags_keep_non_latin():
    assert publish._hashtag('#Hoạt hình vui') == '#hoathinhvui'
    assert publish._hashtag('#电影 推荐', 'zh') == '#电影推荐'
    assert publish._hashtag('#Movie Recap', 'en') == '#movierecap'


def test_glossary_cjk_inside_sentence():
    entries = [{'goc': '', 'sai': '小明', 'viet': '小强'}, {'goc': '', 'sai': 'Mệnh Nguyệt', 'viet': 'Minh Nguyệt'}]
    entries = [user_glossary._clean(e) for e in entries]
    assert user_glossary.apply('我叫小明今天', entries) == '我叫小强今天'
    assert user_glossary.apply('vận mệnh nguyệt quang', entries) == 'vận mệnh nguyệt quang'   # chữ Việt vẫn khớp nguyên từ


def test_call_tl_passes_only_when_supported():
    def old(a, b):
        return (a, b)

    def new(a, b, target_lang='vi'):
        return (a, b, target_lang)
    assert vietsub._call_tl(old, 1, 2, tl='en') == (1, 2)
    assert vietsub._call_tl(new, 1, 2, tl='en') == (1, 2, 'en')
    assert vietsub._call_tl(new, 1, 2, tl='vi') == (1, 2, 'vi')


def test_thumbnail_wrap_cjk(tmp_path):
    from PIL import Image
    src = str(tmp_path / 'f.jpg')
    Image.new('RGB', (1280, 720), (90, 120, 150)).save(src)
    out = str(tmp_path / 't.jpg')
    publish.render_thumbnail(src, '震惊！他竟然是幕后黑手，所有人都没想到', out)
    assert os.path.getsize(out) > 1000
