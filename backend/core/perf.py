"""Ngân sách CPU chung cho cả app — cách các app dựng / mã hoá video chuyên nghiệp làm (HandBrake, DaVinci Resolve, OBS):

1. Việc nặng (ffmpeg, Whisper, VieNeu, tách giọng, xoá chữ) chạy ở mức ƯU TIÊN THẤP → Windows, trình duyệt, app khác luôn
   được phục vụ trước: máy không đơ; khi máy rảnh thì tốc độ dựng như cũ.
2. Một NGÂN SÁCH luồng tính từ số lõi (chừa lõi cho hệ thống), CHIA cho các tiến trình chạy song song — thay vì mỗi ffmpeg
   tự mở luồng bằng số lõi (4 ffmpeg × 56 luồng tranh nhau → tốn thêm ~37% CPU mà không nhanh hơn, đã đo).
3. "Chế độ nhẹ máy" (Cài đặt): dùng một nửa ngân sách, dựng 1 clip / lượt — vừa chạy tool vừa làm việc khác.
4. Đo CPU / thời gian từng job → ghi log (biết ngay bước nào nặng khi người dùng báo chậm).
"""
import os
import subprocess
import sys
import threading
import time

CPU_COUNT = os.cpu_count() or 4
# Windows: BELOW_NORMAL_PRIORITY_CLASS — chạy nền, nhường CPU cho app đang dùng (giống HandBrake "Priority: Below Normal")
BELOW_NORMAL = 0x00004000 if sys.platform == 'win32' else 0

_light = None                 # None = đọc Cài đặt; True / False = ép (job / test)


def light_mode():
    if _light is not None:
        return _light
    try:
        from app.config import load_settings
        return bool(load_settings().get('light_mode'))
    except Exception:
        return False


def set_light_mode(on):
    global _light
    _light = None if on is None else bool(on)


def budget():
    """Số luồng dành cho việc nặng: chừa 1 lõi (máy ≤ 4 lõi) / 2 lõi cho hệ thống; chế độ nhẹ máy → một nửa."""
    reserve = 1 if CPU_COUNT <= 4 else 2
    b = max(1, CPU_COUNT - reserve)
    return max(1, b // 2) if light_mode() else b


MAX_FF_THREADS = 8        # 1 ffmpeg 1080p hiệu quả nhất ~4–8 luồng; nhiều hơn chỉ tốn CPU chờ / đồng bộ (đã đo)


def render_workers(cap=4):
    """Số clip dựng song song: mỗi clip ngắn (vài giây) nên chạy song song vài clip × ~3+ luồng hiệu quả hơn 1 clip × nhiều
    luồng → budget // 3, tối đa cap. Chế độ nhẹ máy: 1 clip / lượt."""
    if light_mode():
        return 1
    return max(1, min(cap, budget() // 3))


def threads_for(parallel=1):
    """Số luồng cho MỖI tiến trình khi có `parallel` tiến trình chạy cùng lúc (tổng ≤ ngân sách)."""
    return max(1, budget() // max(1, int(parallel)))


def ffmpeg_threads(cmd, parallel=1):
    """Giới hạn luồng cho 1 lệnh ffmpeg (giải mã + bộ lọc + mã hoá) theo ngân sách. Lệnh đã tự đặt -threads thì giữ nguyên.
    → lệnh mới (list)."""
    if not cmd or '-threads' in cmd or not str(cmd[0]).lower().replace('\\', '/').rsplit('/', 1)[-1].startswith('ffmpeg'):
        return cmd
    n = str(min(MAX_FF_THREADS, threads_for(parallel)))
    out = [cmd[0], '-filter_threads', n, '-filter_complex_threads', n]
    rest = list(cmd[1:])
    # -threads trước MỖI -i = luồng giải mã của input đó; -threads ngay trước tên file đầu ra = luồng mã hoá
    for (k, x) in enumerate(rest):
        if x == '-i' and (k == 0 or rest[k - 1] != '-threads'):
            out += ['-threads', n]
        out.append(x)
    if len(out) > 1 and not str(out[-1]).startswith('-'):
        out = out[:-1] + ['-threads', n, out[-1]]
    return out


_parallel = [1]


class parallel:
    """with perf.parallel(n): mọi ffmpeg chạy qua run_subprocess* trong khối này chia ngân sách cho n tiến trình."""

    def __init__(self, n):
        self.n = max(1, int(n))

    def __enter__(self):
        (self.old, _parallel[0]) = (_parallel[0], self.n)
        return self

    def __exit__(self, *a):
        _parallel[0] = self.old


def current_parallel():
    return _parallel[0]


def lower_priority(pid=None):
    """Hạ ưu tiên 1 tiến trình (mặc định: chính backend) xuống dưới bình thường. Lỗi → bỏ qua."""
    try:
        import psutil
        p = psutil.Process(pid) if pid else psutil.Process()
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == 'win32' else 10)
        return True
    except Exception:
        return False


def low_priority_flags(flags=0):
    """creationflags cho subprocess: thêm ưu tiên thấp (Windows)."""
    return int(flags or 0) | BELOW_NORMAL


class Meter:
    """Đo CPU máy + thời gian một job (lấy mẫu mỗi 2s ở luồng nền). summary() → câu tóm tắt cho log."""

    def __init__(self):
        self.t0 = time.time()
        self.samples = []
        self._stop = threading.Event()
        self._th = None

    def start(self):
        try:
            import psutil
            psutil.cpu_percent(None)
        except Exception:
            return self

        def run():
            import psutil
            while not self._stop.wait(2.0):
                try:
                    self.samples.append(psutil.cpu_percent(None))
                except Exception:
                    break
        self._th = threading.Thread(target=run, daemon=True)
        self._th.start()
        return self

    def stop(self):
        self._stop.set()

    def summary(self):
        self.stop()
        dt = time.time() - self.t0
        mm = f'{int(dt // 60)} phút {int(dt % 60)} giây' if dt >= 60 else f'{dt:.0f} giây'
        cpu = (f' · CPU máy trung bình {sum(self.samples) / len(self.samples):.0f}%, đỉnh {max(self.samples):.0f}%'
               if self.samples else '')
        return (f'[HIỆU NĂNG] Thời gian {mm}{cpu} · ngân sách {budget()}/{CPU_COUNT} luồng'
                + (' · chế độ nhẹ máy' if light_mode() else ''))
