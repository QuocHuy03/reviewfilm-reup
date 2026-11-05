"""Reup: tiếng không trễ dần so với hình khi ghép nhiều clip; dịch phim Trung đi thẳng từ chữ Hán; dòng rác từ logo bị bỏ."""
import os
import subprocess

import numpy as np

from core import video_editor as ve
from core.utils import FFMPEG_EXE


def _beep_starts(path):
    r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-i', path, '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], capture_output=True)
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
    loud = np.abs(x[:len(x) // 80 * 80]).reshape(-1, 80).max(1) > 0.02
    return (np.where(loud[1:] & ~loud[:-1])[0] + 1) * 0.005


def test_voice_does_not_drift_over_many_clips(tmp):
    """24 câu, mỗi câu là 1 tiếng bíp → bíp phải nằm đúng mốc hình của câu, kể cả câu cuối (trước: trễ dần tới ~0,7s)."""
    src = os.path.join(tmp, 'src.mp4')
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=25', '-f', 'lavfi',
                    '-i', 'anullsrc=r=44100:cl=mono', '-t', '50', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', src], check=True)
    scenes = []
    for i in range(24):
        (start, length) = (1.0 + i * 2.0, 0.8 + (i % 5) * 0.13)
        wav = os.path.join(tmp, f'v{i}.wav')
        subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-f', 'lavfi', '-i', f'sine=frequency=1000:sample_rate=44100:duration={length}', '-ac', '1', wav], check=True)
        scenes.append({'clip_start': start, 'clip_end': start + length + 0.2, 'tts_path': wav, 'tts_duration': length, 'voiceover': 'x', 'subtitle': 'x'})
    (out, timeline) = (os.path.join(tmp, 'o.mp4'), [])
    ve.build_review_video(scenes, src, out, tmp, target_resolution='320x180', fps=30, original_volume=0.0, burn_subtitles=False,
                          is_reup=True, log_fn=lambda *a: None, timeline_out=timeline)
    marks = [t['out_start'] for t in sorted(timeline, key=lambda t: t['i'])]
    beeps = _beep_starts(out)
    assert len(beeps) == len(marks) == 24
    assert max(abs(b - m) for (b, m) in zip(beeps, marks)) < 0.03
    assert abs(ve._stream_duration(out, 'v:0') - ve._stream_duration(out, 'a:0')) < 0.05


def test_logo_noise_lines_dropped_but_real_short_lines_kept():
    from app.features.jobs.vietsub import drop_logo_noise
    lines = ['江凡多次检测都无灵根小', '悠然更出众小', '动', '今日就此退婚吧漫', '小', '只有悠然不眠不休动', '小凡', '爹', '小麟', '我病了七天七夜动',
             '你不该答应漫', '漫', '鹿麟动', '不', '等等老爷子定的婚约']
    segs = [{'start': float(i), 'end': float(i) + 0.8, 'text': t} for (i, t) in enumerate(lines)]
    segs[8].update(start=66.8, end=68.0)         # dòng hiện đúng 1,2s (số thực ra 1,2000000000000028)
    left = [s['text'] for s in drop_logo_noise(segs)]
    assert not {'动', '小', '漫', '小麟', '鹿麟动'} & set(left), 'dòng rác từ logo'
    assert {'小凡', '爹', '不'} <= set(left), 'câu ngắn thật vẫn giữ'


def test_chinese_translates_directly_and_falls_back(monkeypatch):
    from app.features.jobs import pipelines
    from core import dub_translate

    class Job:
        def log(self, *a):
            pass
    segs = [{'start': 0.0, 'end': 1.0, 'text': '江凡'}, {'start': 5.0, 'end': 6.0, 'text': '悠然'}]
    monkeypatch.setattr(dub_translate, 'translate', lambda blocks, *a, **k: ['Giang Phàm', 'Du Nhiên'])
    scenes = pipelines._translate_direct(Job(), segs, {})
    assert [s['voiceover'] for s in scenes] == ['Giang Phàm', 'Du Nhiên'] and scenes[1]['clip_start'] == 5.0
    monkeypatch.setattr(dub_translate, 'translate', lambda blocks, *a, **k: ['Giang Phàm', None])
    assert pipelines._translate_direct(Job(), segs, {}) is None, 'thiếu nhiều câu thì dùng cách dịch cũ, không mất câu'
    from app.features.jobs import vietsub
    many = [{'start': i * 9.0, 'end': i * 9.0 + 1, 'text': f'句{i}'} for i in range(20)]
    monkeypatch.setattr(dub_translate, 'translate', lambda blocks, *a, **k: [None if i == 7 else f'câu {i}' for i in range(len(blocks))])
    monkeypatch.setattr(vietsub, '_google_lines', lambda job, segs, lang: [{'voiceover': 'câu Google'} for _ in segs])
    scenes = pipelines._translate_direct(Job(), many, {})
    assert scenes[7]['voiceover'] == 'câu Google' and scenes[8]['voiceover'] == 'câu 8', 'thiếu 1 câu: chỉ vá câu đó, không dịch lại cả phim'


def test_ai_wait_limit_grows_and_respects_caller():
    from core.web_llm import _wait_limit
    assert _wait_limit('x' * 1000, 0, 900) == 190 and _wait_limit('x' * 1000, 1, 900) == 380
    assert _wait_limit('x' * 1000, 0, 60) == 60


def test_chinese_film_names_are_sino_vietnamese_only_for_chinese_films():
    from core.script_writer import _no_hanviet_note, _origin_name_rule
    for origin in ('trung', 'Trung Quốc', 'China'):
        assert 'Han Viet' in _origin_name_rule(origin) and 'Jiang Fan' in _origin_name_rule(origin)
        assert _no_hanviet_note(origin) == ''
    assert 'KHÔNG phiên âm' in _no_hanviet_note('han') and 'KHÔNG phiên âm' in _no_hanviet_note('')


def test_reup_postedit_only_shortens_and_never_pads(monkeypatch):
    """Bản dịch: câu ngắn hơn hình giữ nguyên (không thêm chữ cho đủ hình); chỉ câu dài quá mới gửi AI, kèm lời gốc."""
    import json
    from app.features.jobs import postedit
    from core import web_llm
    sent = []

    def chat(prompt, log=None):
        sent.append(prompt)
        return json.dumps({'edits': []})
    monkeypatch.setattr(web_llm, 'available', lambda: True)
    monkeypatch.setattr(web_llm, 'chat', chat)
    scenes = [{'clip_start': 0, 'clip_end': 5, 'voiceover': 'xin chào nhé', 'orig_text': '短句'},
              {'clip_start': 5, 'clip_end': 6, 'voiceover': ' '.join(['từ'] * 30), 'orig_text': '长句子'}]
    postedit.suggest_edits(scenes, 'reup', '', lambda *a: None, wps=4.0)
    assert len(sent) == 1 and '长句子' in sent[0] and 'xin chào nhé' not in sent[0] and 'ĐÂY LÀ BẢN DỊCH' in sent[0]
    sent.clear()
    assert postedit.suggest_edits(scenes[:1], 'reup', '', lambda *a: None, wps=4.0) == [] and not sent, 'câu ngắn: không gọi AI'
    postedit.suggest_edits(scenes[:1], 'review', '', lambda *a: None, wps=4.0)
    assert sent and 'ĐÂY LÀ BẢN DỊCH' not in sent[0], 'Review vẫn được kể thêm cho đủ hình'
    sent.clear()
    postedit.suggest_edits(scenes[:1], 'reup', 'đổi xưng hô thành anh em', lambda *a: None, wps=4.0)
    assert sent and 'xin chào nhé' in sent[0] and 'đổi xưng hô' in sent[0], 'yêu cầu người dùng tự gõ vẫn áp dụng cho mọi câu'


def test_reup_autofix_keeps_repeated_dialogue():
    from app.features.jobs.autofix import plan
    qa = {'checks': [{'id': 'repeat', 'status': 'warn', 'data': {'issues': [{'scene': 0, 'why': 'lặp', 'with': 1}]}}]}
    scenes = [{'clip_start': 0, 'clip_end': 2, 'tts_duration': 2}, {'clip_start': 2, 'clip_end': 4, 'tts_duration': 2}]
    assert plan(qa, scenes, {'mode': 'reup'})['scenes'] == {}
    assert 0 in plan(qa, scenes, {'mode': 'review'})['scenes']


def test_cut_off_ai_reply_keeps_finished_lines_and_asks_only_missing(monkeypatch):
    """Gemini web cắt ngang JSON dài: câu đã xong vẫn lấy, lượt sau chỉ hỏi câu thiếu (trước: mất cả gói → dịch lại cả phim)."""
    import json
    from core import dub_translate, web_llm
    cut = '```json\n{"cau": [\n{"i": 0, "sat": "a", "viet": "Câu \\"một\\""},\n{"i": 1, "sat": "b", "viet": "Câu hai"},\n{"i": 2, "sat": "c", "viet": "Câu đang viết d'
    assert dub_translate.reply_rows(cut) == {0: 'Câu "một"', 1: 'Câu hai'}
    asked = []

    def chat(prompt, log=None):
        if 'tom_tat' in prompt:
            return '{}'
        rows = json.loads(prompt[prompt.rindex('[\n{'):])
        asked.append([r['i'] for r in rows])
        return cut if len(asked) == 1 else json.dumps({'cau': [{'i': r['i'], 'viet': f"xong {r['i']}"} for r in rows]})
    monkeypatch.setattr(web_llm, 'available', lambda: True)
    monkeypatch.setattr(web_llm, 'chat', chat)
    segs = [{'start': i * 3.0, 'end': i * 3.0 + 2, 'text': f'句{i}'} for i in range(4)]
    out = dub_translate.translate(segs, None, lambda *a: None)
    assert asked == [[0, 1, 2, 3], [2, 3]] and out == ['Câu "một"', 'Câu hai', 'xong 2', 'xong 3']
