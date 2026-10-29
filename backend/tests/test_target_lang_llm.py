"""Ngôn ngữ lồng tiếng (target_lang) ở các bước AI viết / dịch: tiếng Việt giữ nguyên lời nhắc cũ, ngôn ngữ khác yêu cầu
đúng ngôn ngữ đó, ngân sách độ dài đếm ký tự với tiếng Trung / Nhật / Thái."""
import copy

from core import dub_translate, script_writer, translator

META = [{'clip_start': 0, 'clip_end': 20, 'description': 'Một người đàn ông bước vào', '_transcript': '你好'},
        {'clip_start': 20, 'clip_end': 50, 'description': 'Cuộc chiến bắt đầu'}]
AN = {'_vi_title': 'Phim X', 'origin': 'han', 'genre': 'hành động', 'summary': 'abc', 'main_characters': ['A']}


def _script_prompt(monkeypatch, target_lang):
    cap = []
    monkeypatch.setattr(script_writer, '_llm_text_call', lambda eng, key, prompt, *a, **k: cap.append(prompt) or '')
    script_writer._write_unified_marked_script(copy.deepcopy(META), dict(AN), 30, 60, [('web', 'k')], lambda *a: None,
                                               target_lang=target_lang)
    return cap[0]


def test_review_script_vi_prompt_unchanged(monkeypatch):
    p = _script_prompt(monkeypatch, 'vi')
    assert 'kênh YouTube Movie Recap hàng đầu Việt Nam' in p
    assert 'Thay mọi chữ số bằng chữ tiếng Việt' in p
    assert 'Cảnh 1 (viết ~' in p and ' từ)' in p


def test_review_script_other_language(monkeypatch):
    for (code, name) in (('en', 'English'), ('ja', 'Japanese')):
        p = _script_prompt(monkeypatch, code)
        assert name in p and '[Cảnh N]' in p
        assert 'Hán-Việt' not in p and 'chữ tiếng Việt' not in p        # không quy tắc Hán Việt / đọc số tiếng Việt
    assert 'ký tự)' in _script_prompt(monkeypatch, 'zh')                # Trung: ngân sách theo ký tự


def test_dub_prompts():
    assert dub_translate._prompts('vi') == (dub_translate.PROMPT, dub_translate.GLOSSARY_PROMPT)
    (p, g) = dub_translate._prompts('ja')
    filled = p.format(chars='', context='', glossary='', prev='', rows='[]')
    assert 'Japanese' in filled and 'tiếng Việt' not in filled and 'ký tự' in filled
    assert 'Japanese' in g.format(script='x')


def test_budgets_by_language():
    seg = [{'start': 0.0, 'end': 2.0, 'text': 'x'}]
    assert dub_translate.budgets(seg) == dub_translate.budgets(seg, dub_translate.WPS)       # tiếng Việt như cũ
    assert dub_translate.rate('zh') == (4.5, 'chars') and dub_translate.rate('vi') == (4.3, 'words')
    assert dub_translate.text_units('大家好，今天', 'zh') == 5
    assert dub_translate.text_units('Hello there, you', 'en') == 3
    blocks = [{'start': 0, 'end': 3, 'text': 'a'}, {'start': 3.2, 'end': 6, 'text': 'b'}]
    assert translator._block_budgets(blocks, 'zh') != translator._block_budgets(blocks, 'vi')


def test_trim_counts_chars_for_chinese():
    out = script_writer._trim_to_word_limit('今天天气很好。我们去公园玩吧，然后吃饭。', 8, 'zh')
    assert out == '今天天气很好。'
    assert script_writer._trim_to_word_limit('one two three four. five six', 5, 'en') == 'one two three four.'
    assert script_writer._wpm('vi') == script_writer.TTS_WPM


def test_translator_other_language_skips_vietnamese_steps(monkeypatch):
    calls = []
    monkeypatch.setattr(translator, '_blocks_to_english', lambda blocks, *a: ['hello'] * len(blocks))
    monkeypatch.setattr(translator, '_localize_to_vietnamese', lambda *a, **k: calls.append('vi') or [])
    monkeypatch.setattr(translator, '_localize_to_target', lambda *a, **k: calls.append('target') or ['xin'] * len(a[0]))
    monkeypatch.setattr(translator, '_polish_blocks_target', lambda tr, *a: calls.append('polish') or tr)
    monkeypatch.setattr(translator, '_analyze_film_context', lambda *a, **k: {'title': 'T', 'origin': 'han'})
    monkeypatch.setattr(translator, '_save_film_glossary', lambda *a: None)
    monkeypatch.setattr(translator, '_load_film_glossary', lambda key: calls.append(key) or [])
    from core import web_llm
    monkeypatch.setattr(web_llm, 'with_web', lambda engs: [('web', 'k')])
    seg = [{'start': 0, 'end': 2, 'text': '你好'}]
    out = translator.translate_and_localize_transcript(seg, log_fn=lambda *a: None, allow_web=True, target_lang='ja')
    assert 'vi' not in calls and 'target' in calls and 'polish' in calls
    assert any(str(c).endswith('__ja') for c in calls)                  # bảng tên đã chốt riêng cho tiếng Nhật
    assert out and out[0]['voiceover'] == 'xin'
    calls.clear()
    out = translator.translate_and_localize_transcript(seg, log_fn=lambda *a: None, allow_web=True, target_lang='en')
    assert 'target' not in calls and out[0]['voiceover'] == 'hello'     # tiếng Anh: dùng luôn bản tiếng Anh


def test_google_free_target(monkeypatch):
    seen = []
    monkeypatch.setattr(translator, '_google_translate', lambda text, sl, tl: seen.append((sl, tl)) or f'{tl}:{text}')
    seg = [{'start': 0, 'end': 2, 'text': '你好'}]
    out = translator._translate_via_google_free(seg, 'zh', lambda *a: None, '', '', target_lang='zh')
    assert seen[-1] == ('en', 'zh-CN') and out[0]['voiceover'].startswith('zh-CN:')
    seen.clear()
    translator._translate_via_google_free(seg, 'zh', lambda *a: None, '', '')
    assert seen[-1] == ('en', 'vi')
