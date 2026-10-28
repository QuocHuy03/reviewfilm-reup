"""Mã hoá video: GPU NVIDIA (NVENC) khi dùng được, không thì CPU (libx264).

- Dò 1 lần rồi nhớ (cache): mã hoá thử 1 khung bằng ĐÚNG bộ tham số sẽ dùng → card / driver không hỗ trợ tuỳ chọn nào là biết ngay.
- Không dùng được GPU → nêu lý do dễ hiểu (driver quá cũ, không có card NVIDIA, đã tắt trong Cài đặt…) để hiện trong app.
- Đang dựng mà GPU lỗi (hết phiên NVENC, driver treo…) → nơi gọi chạy lại bằng CPU (`cpu_args`), video vẫn ra.
Bật / tắt: Cài đặt → Mặc định → "Dựng bằng GPU (NVENC)" (settings['gpu_encode'], mặc định bật).
"""
import re
import shutil
import subprocess
import threading

MIN_DRIVER = 570          # ffmpeg 8.x dùng NVENC API 13 → driver NVIDIA ≥ 570

# chất lượng ~ ngang libx264 veryfast cùng mức (cq ≈ crf + 1)
_GPU = {
    'final': ['-c:v', 'h264_nvenc', '-preset', 'p5', '-tune', 'hq', '-rc', 'vbr', '-cq', '21', '-b:v', '0',
              '-spatial-aq', '1', '-rc-lookahead', '20', '-pix_fmt', 'yuv420p'],
    'scene': ['-c:v', 'h264_nvenc', '-preset', 'p4', '-tune', 'hq', '-rc', 'vbr', '-cq', '23', '-b:v', '0', '-pix_fmt', 'yuv420p'],
    'intermediate': ['-c:v', 'h264_nvenc', '-preset', 'p5', '-tune', 'hq', '-rc', 'vbr', '-cq', '16', '-b:v', '0',
                     '-spatial-aq', '1', '-pix_fmt', 'yuv420p'],
}
_CPU = {
    'final': ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p'],
    'scene': ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p'],
    'intermediate': ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '15', '-pix_fmt', 'yuv420p'],
}

_lock = threading.Lock()
_state = None


def _nvidia_smi():
    """(tên card, phiên bản driver) — không có nvidia-smi / không có card NVIDIA → ('', '')."""
    exe = shutil.which('nvidia-smi')
    if not exe:
        return ('', '')
    try:
        from core.utils import _HIDE
        r = subprocess.run([exe, '--query-gpu=name,driver_version', '--format=csv,noheader'], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=8, creationflags=_HIDE)
        line = (r.stdout or '').strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ''
        (name, _, drv) = line.partition(',')
        return (name.strip(), drv.strip())
    except Exception:
        return ('', '')


def _enabled():
    try:
        from app.config import load_settings
        return load_settings().get('gpu_encode', True) is not False
    except Exception:
        return True


def probe(force=False):
    """{'available', 'gpu', 'driver', 'reason'} — reason rỗng khi dùng được GPU."""
    global _state
    with _lock:
        if _state is not None and not force:
            return dict(_state, available=_state['available'] and _enabled(), reason=_state['reason'] or ('' if _enabled() else 'Đã tắt trong Cài đặt'))
        from core.utils import FFMPEG_EXE, _HIDE
        (gpu, drv) = _nvidia_smi()
        st = {'available': False, 'gpu': gpu, 'driver': drv, 'reason': ''}
        try:
            enc = subprocess.run([FFMPEG_EXE, '-hide_banner', '-encoders'], capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=15, creationflags=_HIDE).stdout
            if 'h264_nvenc' not in enc:
                st['reason'] = 'Bản ffmpeg trong app không có bộ mã hoá NVENC'
            elif not gpu:
                st['reason'] = 'Không thấy card NVIDIA (dựng bằng CPU)'
            else:
                t = subprocess.run([FFMPEG_EXE, '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=1280x720:d=0.2',
                                    *_GPU['final'], '-f', 'null', '-'], capture_output=True, text=True, encoding='utf-8',
                                   errors='replace', timeout=40, creationflags=_HIDE)
                err = (t.stderr or '').strip()
                if t.returncode == 0:
                    st['available'] = True
                elif re.search(r'minimum required Nvidia driver|nvenc API version', err, re.I):
                    st['reason'] = f'Driver NVIDIA {drv or ""} quá cũ — cần bản {MIN_DRIVER} trở lên'.replace('  ', ' ')
                elif re.search(r'No capable devices|not supported|OpenEncodeSessionEx failed|out of memory', err, re.I):
                    st['reason'] = f'Card {gpu} không mở được phiên mã hoá NVENC (card quá cũ hoặc đang bận)'
                elif re.search(r'Cannot load nvcuda|nvEncodeAPI|libcuda', err, re.I):
                    st['reason'] = 'Thiếu driver NVIDIA (cài driver mới từ nvidia.com)'
                else:
                    st['reason'] = 'GPU thử mã hoá không thành công: ' + (err.splitlines()[-1][:140] if err else 'không rõ lỗi')
        except Exception as e:
            st['reason'] = f'Không kiểm tra được GPU: {str(e)[:120]}'
        _state = st
        return dict(st, available=st['available'] and _enabled(), reason=st['reason'] or ('' if _enabled() else 'Đã tắt trong Cài đặt'))


def use_gpu():
    return probe()['available']


def video_args(kind='final', gpu=None):
    """Tham số mã hoá video. kind: final (video xuất) | scene (clip từng cảnh) | intermediate (file trung gian chất lượng cao)."""
    if gpu is None:
        gpu = use_gpu()
    return list((_GPU if gpu else _CPU)[kind])


def cpu_args(kind='final'):
    return list(_CPU[kind])


def is_gpu_args(args):
    return 'h264_nvenc' in args


def describe():
    """Dòng nhật ký: mã hoá bằng gì (+ lý do khi không dùng được GPU)."""
    st = probe()
    if st['available']:
        return f"Mã hoá video: GPU NVENC ({st['gpu']})"
    return 'Mã hoá video: CPU' + (f" — {st['reason']}" if st['reason'] else '')
