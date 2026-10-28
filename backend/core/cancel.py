"""Huỷ job từ bất kỳ đâu — kể cả luồng phụ (ThreadPool tạo giọng) và thư viện sâu (gọi AI, TTS) không có đường truyền `job`.

Job đang giữ lượt chạy (WorkSlot, mỗi lúc 1 job nặng) đăng ký hàm "đã bấm Dừng chưa?" ở đây; code ở mọi nơi gọi
`requested()` (đọc) hoặc `check()` (ném `Cancelled`, được quản lý job xử lý như huỷ). Không có job nào đăng ký → không bao giờ huỷ.
"""
import threading
import time


class Cancelled(Exception):
    """Người dùng bấm Dừng — quản lý job bắt lỗi này và đánh dấu job 'Đã huỷ'."""


_lock = threading.Lock()
_active = None          # hàm () -> bool của job đang chạy


def set_active(fn):
    global _active
    with _lock:
        _active = fn


def clear_active(fn=None):
    """Bỏ đăng ký (chỉ khi đúng hàm của job đó — job khác đã chiếm lượt thì giữ nguyên)."""
    global _active
    with _lock:
        if fn is None or _active is fn:
            _active = None


def requested():
    f = _active
    try:
        return bool(f and f())
    except Exception:
        return False


def check():
    if requested():
        raise Cancelled()


def sleep(seconds, step=0.25):
    """Ngủ nhưng thức ngay khi bị huỷ → True nếu bị huỷ."""
    end = time.time() + seconds
    while time.time() < end:
        if requested():
            return True
        time.sleep(min(step, max(0.0, end - time.time())))
    return requested()


def run(fn, poll=0.3):
    """Chạy hàm chặn lâu (vd gọi HTTP chờ AI tới 15 phút) ở luồng nền, chờ có kiểm tra huỷ.
    Bị huỷ → ném Cancelled ngay (luồng nền tự kết thúc sau, kết quả bỏ đi)."""
    box = {}

    def work():
        try:
            box['v'] = fn()
        except BaseException as e:      # noqa: BLE001 — trả lỗi về luồng gọi
            box['e'] = e
    t = threading.Thread(target=work, daemon=True)
    t.start()
    while t.is_alive():
        t.join(poll)
        if t.is_alive() and requested():
            raise Cancelled()
    if 'e' in box:
        raise box['e']
    return box.get('v')
