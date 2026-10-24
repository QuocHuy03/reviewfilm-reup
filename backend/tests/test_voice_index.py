"""Giọng đọc phải gắn đúng cảnh: chỉ số cảnh (_original_index) không được bị ghi đè / mất."""
import os
import types

import core.tts_engine as tts
from app.features.jobs import pipelines


def _fake_edge(scenes, voice, rate, log_fn, temp_dir):
    return [{**s, 'tts_path': f"vo_{s['_original_index']}.mp3", 'tts_duration': 1.0} for s in scenes]


def test_tts_keeps_caller_scene_index(monkeypatch, tmp):
    """Tự hậu kỳ gửi lô cảnh [3, 7] kèm _original_index → kết quả phải giữ 3 và 7, không đánh lại 0, 1."""
    monkeypatch.setattr(tts, '_render_edge_parallel', _fake_edge)
    batch = [{'voiceover': 'ba', '_original_index': 3}, {'voiceover': 'bay', '_original_index': 7}]
    out = tts.generate_tts_per_scene(batch, 'vi-VN-HoaiMyNeural', tmp, log_fn=lambda *_: None)
    assert [s['_original_index'] for s in out] == [3, 7]


def test_multi_voice_output_not_duplicated(monkeypatch, tmp):
    """Phân vai xong đủ giọng cho 3 cảnh → _fill_missing_voices không được đọc lại / nhân đôi cảnh."""
    def fake_edge(scenes, voice, rate, log_fn, temp_dir):
        out = []
        for s in scenes:
            p = os.path.join(tmp, f"mv_{len(os.listdir(tmp))}.mp3")
            open(p, 'wb').write(b'0')
            out.append({**s, 'tts_path': p, 'tts_duration': 1.0})
        return out

    monkeypatch.setattr(tts, '_render_edge_parallel', fake_edge)
    monkeypatch.setattr(tts, '_audio_duration', lambda p: 1.0)
    monkeypatch.setattr(pipelines, 'synthesize', lambda scenes, *a, **k: [{**s, 'tts_path': 'x.mp3', 'tts_duration': 1.0} for s in scenes])
    scenes = [{'voiceover': f'cau {i}', 'segments': [{'text': f'cau {i}', 'vai': 'ke'}]} for i in range(3)]
    rendered = tts.generate_tts_multi_voice([dict(s) for s in scenes], {}, 'vi-VN-HoaiMyNeural', tmp, log_fn=lambda *_: None)
    assert len(rendered) == 3            # phân vai đọc đủ 3 cảnh
    job = types.SimpleNamespace(scenes=scenes, log=lambda *a, **k: None, check=lambda: None)
    out = pipelines._fill_missing_voices(job, rendered, 'x', tmp, {})
    assert [s['voiceover'] for s in out] == ['cau 0', 'cau 1', 'cau 2']
