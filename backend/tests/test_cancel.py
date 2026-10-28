"""Bấm Dừng: job luôn dừng — bước hợp tác dừng ngay; bước kẹt (không kiểm tra huỷ) bị chốt 'Đã huỷ' sau FORCE_STOP_SECS và nhả lượt."""
import threading
import time

import pytest

from app.features.jobs import manager as M
from core import cancel


@pytest.fixture(autouse=True)
def _jobs_in_tmp(tmp_path, monkeypatch):
    """Job giả của test ghi vào thư mục tạm — không lẫn vào danh sách job thật (luồng chốt huỷ có thể lưu sau khi test dọn)."""
    monkeypatch.setattr(M, 'JOBS_DIR', str(tmp_path))


def _wait_status(job, statuses, limit):
    t0 = time.time()
    while job.status not in statuses and time.time() - t0 < limit:
        time.sleep(0.05)
    return time.time() - t0


def _start(runner, title):
    job = M.manager.start('srt', {}, runner, title)
    _wait_status(job, ('running',), 10)
    return job


def _cleanup(*jobs):
    for j in jobs:
        try:
            M.manager.jobs.pop(j.id, None)
            import os
            os.remove(os.path.join(M.JOBS_DIR, f'{j.id}.json'))
        except OSError:
            pass


def test_stuck_step_is_force_stopped_and_slot_released(monkeypatch):
    monkeypatch.setattr(M, 'FORCE_STOP_SECS', 1.0)
    release = threading.Event()

    def stuck(job):                       # bước "kẹt": không hề kiểm tra huỷ
        release.wait(30)
    job = _start(stuck, 'TEST kẹt')
    M.manager.cancel(job.id)
    took = _wait_status(job, ('cancelled',), 10)
    assert job.status == 'cancelled' and took < 3
    nxt = _start(lambda j: None, 'TEST job sau')       # lượt đã nhả → job sau chạy ngay
    assert _wait_status(nxt, ('done',), 5) < 5 and nxt.status == 'done'
    release.set()
    time.sleep(0.3)
    assert job.status == 'cancelled'                    # luồng cũ chạy nốt cũng không đổi trạng thái
    _cleanup(job, nxt)


def test_blocking_call_wrapped_in_cancel_run_stops_fast():
    def waits_ai(job):
        cancel.run(lambda: time.sleep(60))     # như chờ AI trả lời
    job = _start(waits_ai, 'TEST chờ AI')
    t0 = time.time()
    M.manager.cancel(job.id)
    _wait_status(job, ('cancelled',), 10)
    assert job.status == 'cancelled' and time.time() - t0 < 2
    _cleanup(job)


def test_worker_threads_see_cancel():
    seen = []

    def pool(job):
        from concurrent.futures import ThreadPoolExecutor

        def work(i):
            for _ in range(200):
                if cancel.requested():
                    seen.append(i)
                    return
                time.sleep(0.05)
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(work, range(3)))
        cancel.check()
    job = _start(pool, 'TEST luồng phụ')
    time.sleep(0.3)
    t0 = time.time()
    M.manager.cancel(job.id)
    _wait_status(job, ('cancelled',), 10)
    assert job.status == 'cancelled' and time.time() - t0 < 2 and sorted(seen) == [0, 1, 2]
    _cleanup(job)
