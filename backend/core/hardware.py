"""Dò cấu hình máy và đề xuất cài đặt hợp nhất (Whisper chạy GPU hay CPU, model nào vừa VRAM, mã hoá GPU, chế độ nhẹ máy).

Kết quả cache trong phiên (dò lại khi force=True — vd vừa cập nhật driver). Không bao giờ ném lỗi: thiếu thông tin thì để trống.
"""
import os
import shutil
import subprocess
import threading

_lock = threading.Lock()
_cache = None


def _gpu_info():
    """(tên card, VRAM GB, driver) qua nvidia-smi; không có card NVIDIA → ('', 0, '')."""
    exe = shutil.which('nvidia-smi')
    if not exe:
        return ('', 0.0, '')
    try:
        from core.utils import _HIDE
        r = subprocess.run([exe, '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits'], capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=8, creationflags=_HIDE)
        (name, mem, drv) = [x.strip() for x in r.stdout.strip().splitlines()[0].split(',')][:3]
        return (name, round(float(mem) / 1024, 1), drv)
    except Exception:
        return ('', 0.0, '')


def _whisper_cuda():
    """Whisper (faster-whisper / ctranslate2) chạy CUDA được không → (được?, kiểu tính)."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() <= 0:
            return (False, '')
        from core.transcriber import _add_cuda_dll_dirs, cuda_compute_type
        if not _add_cuda_dll_dirs(lambda *_: None):
            return (False, '')
        return (True, cuda_compute_type())
    except Exception:
        return (False, '')


def profile(force=False):
    global _cache
    with _lock:
        if _cache is not None and not force:
            return dict(_cache)
        cores = os.cpu_count() or 4
        try:
            import psutil
            ram = round(psutil.virtual_memory().total / 2 ** 30)
        except Exception:
            ram = 0
        (gpu, vram, drv) = _gpu_info()
        (wcuda, wtype) = _whisper_cuda()
        from core import encoder
        from core.transcriber import asr_label
        enc = encoder.probe(force=force)
        # ── đề xuất ──
        if wcuda:
            model = 'large-v3' if vram >= 8 else 'medium' if vram >= 5 else 'small'
        else:
            model = 'small' if cores >= 12 else 'base'
        light = cores <= 4 or (0 < ram < 8)
        notes = []
        if wcuda:
            notes.append(f'Nhận dạng giọng nói chạy GPU ({wtype}) — nhanh gấp ~5 lần CPU; mức "{asr_label(model)}" vừa {vram:g} GB VRAM.')
        elif gpu:
            notes.append('Có card NVIDIA nhưng nhận dạng giọng nói chưa dùng được GPU — chạy CPU.')
        else:
            notes.append(f'Không có card NVIDIA — nhận dạng giọng nói chạy CPU; mức "{asr_label(model)}" hợp với {cores} luồng CPU (cần nhanh nhất thì chọn "Online · nhanh nhất").')
        notes.append('Mã hoá video bằng GPU (NVENC).' if enc['available'] else f"Mã hoá video bằng CPU — {enc['reason']}." if enc['reason'] else 'Mã hoá video bằng CPU.')
        if light:
            notes.append('Máy ít nhân / ít RAM → nên bật "Chế độ nhẹ máy" để vừa chạy vừa làm việc khác.')
        _cache = {
            'cpu_threads': cores, 'ram_gb': ram, 'gpu': gpu, 'vram_gb': vram, 'driver': drv,
            'whisper_cuda': wcuda, 'whisper_compute': wtype, 'nvenc': enc['available'], 'nvenc_reason': enc['reason'],
            'recommend': {'device': 'GPU (NVIDIA)' if wcuda else 'CPU', 'whisper_model': model, 'gpu_encode': True, 'light_mode': light},
            'notes': notes,
        }
        return dict(_cache)
