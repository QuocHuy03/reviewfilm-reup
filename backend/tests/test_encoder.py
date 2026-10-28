"""Mã hoá video: chọn GPU / CPU đúng theo kết quả dò, tham số hợp lệ cho ffmpeg, lý do rõ khi không dùng được GPU."""
from core import encoder


def _fake(monkeypatch, available, reason=''):
    st = {'available': available, 'gpu': 'NVIDIA GeForce GTX 1060' if available or reason else '', 'driver': '575.0', 'reason': reason}
    monkeypatch.setattr(encoder, 'probe', lambda force=False: dict(st))


def test_gpu_args_when_available(monkeypatch):
    _fake(monkeypatch, True)
    a = encoder.video_args('final')
    assert a[:2] == ['-c:v', 'h264_nvenc'] and encoder.is_gpu_args(a) and 'yuv420p' in a
    assert 'GPU NVENC' in encoder.describe()


def test_cpu_args_and_reason_when_unavailable(monkeypatch):
    _fake(monkeypatch, False, 'Driver NVIDIA 560.94 quá cũ — cần bản 570 trở lên')
    a = encoder.video_args('final')
    assert a[:2] == ['-c:v', 'libx264'] and not encoder.is_gpu_args(a)
    assert 'quá cũ' in encoder.describe()


def test_every_kind_has_both_backends():
    for kind in ('final', 'scene', 'intermediate'):
        assert encoder.video_args(kind, gpu=True)[1] == 'h264_nvenc'
        assert encoder.cpu_args(kind)[1] == 'libx264'
        # cặp '-cờ giá trị' đầy đủ (ffmpeg không nhận cờ thiếu giá trị)
        for args in (encoder.video_args(kind, gpu=True), encoder.cpu_args(kind)):
            assert len(args) % 2 == 0 and all(x.startswith('-') for x in args[::2])


def test_intermediate_aac_uses_fast_coder():
    from core.utils import _budgeted, fast_aac
    cmd = _budgeted(['ffmpeg', '-i', 'a.mp4', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', 'o.mp4'])
    assert cmd[cmd.index('aac') + 1:cmd.index('aac') + 3] == ['-aac_coder', 'fast']
    final = ['ffmpeg', '-i', 'a.mp4', '-c:a', 'aac', '-aac_coder', 'twoloop', 'o.mp4']   # lượt cuối tự chọn bộ chất lượng cao
    assert fast_aac(final) == final
    assert fast_aac(['ffmpeg', '-i', 'x', '-c', 'copy', '-bsf:a', 'aac_adtstoasc', 'o']) == ['ffmpeg', '-i', 'x', '-c', 'copy', '-bsf:a', 'aac_adtstoasc', 'o']
