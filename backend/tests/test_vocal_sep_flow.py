"""Tách giọng: GPU lỗi → CPU, bị dừng → không lưu dở, đã tách → dùng lại (giả lập, không chạy model)."""
import os

import pytest

from core import vocal_sep as V


@pytest.fixture
def env(tmp_path, monkeypatch):
    media = tmp_path / 'film.mp4'
    media.write_bytes(b'x' * 2000)
    monkeypatch.setattr(V, '_cache_root', lambda: str(tmp_path / 'cache'))
    monkeypatch.setattr(V, 'ensure_model', lambda log=print: 'model.onnx')
    monkeypatch.setattr(V, '_GPU_BAD', {})
    calls = []

    def fake(kind, ok=True, stop=False):
        def run(media_, vp, mp_out, *a):
            calls.append(kind)
            if stop:
                raise RuntimeError('Đã huỷ')
            if ok:
                for p in (vp, mp_out):
                    open(p, 'wb').write(b'flac')
            return ok
        return run
    return str(media), calls, fake, monkeypatch


def test_gpu_failure_falls_back_to_cpu(env):
    (media, calls, fake, mp) = env
    mp.setattr(V, '_gpu_enabled', lambda: True)
    mp.setattr(V, '_run_gpu', lambda m, vp, mo, log, prog, stop: (calls.append('gpu'), False)[1])
    mp.setattr(V, '_run_cpu', fake('cpu'))
    (vp, mo) = V.separate(media, None, lambda *a: None)
    assert calls == ['gpu', 'cpu'] and os.path.isfile(vp) and os.path.isfile(mo)


def test_result_is_reused(env):
    (media, calls, fake, mp) = env
    mp.setattr(V, '_gpu_enabled', lambda: False)
    mp.setattr(V, '_run_cpu', fake('cpu'))
    first = V.separate(media, None, lambda *a: None)
    assert V.separate(media, None, lambda *a: None) == first and calls == ['cpu']


def test_cancel_leaves_no_finished_marker(env):
    (media, calls, fake, mp) = env
    mp.setattr(V, '_gpu_enabled', lambda: False)
    mp.setattr(V, '_run_cpu', fake('cpu', stop=True))
    with pytest.raises(RuntimeError, match='huỷ'):
        V.separate(media, None, lambda *a: None)
    assert V.cached(media) is None
    mp.setattr(V, '_run_cpu', fake('cpu'))                      # chạy lại → tách lại từ đầu, xong mới đánh dấu
    assert V.separate(media, None, lambda *a: None)[1] and V.cached(media)


def test_changed_source_is_not_mistaken_for_cached(env):
    (media, calls, fake, mp) = env
    mp.setattr(V, '_gpu_enabled', lambda: False)
    mp.setattr(V, '_run_cpu', fake('cpu'))
    V.separate(media, None, lambda *a: None)
    with open(media, 'ab') as f:                                # file nguồn đổi (cùng tên)
        f.write(b'more')
    assert V.cached(media) is None


def test_cache_trim_keeps_current(env, monkeypatch):
    (media, calls, fake, mp) = env
    root = V._cache_root()
    for k in range(3):
        d = os.path.join(root, f'old{k}')
        os.makedirs(d)
        open(os.path.join(d, 'music.flac'), 'wb').write(b'x' * 1000)
        os.utime(d, (k, k))
    keep = os.path.join(root, 'cur')
    os.makedirs(keep)
    open(os.path.join(keep, 'music.flac'), 'wb').write(b'x' * 1000)
    monkeypatch.setattr(V, 'CACHE_MAX_BYTES', 2500)
    V._trim_cache(keep)
    assert sorted(os.listdir(root)) == ['cur', 'old2']          # xoá bản cũ nhất trước, không xoá bản đang dùng
