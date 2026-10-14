"""JobManager — chạy pipeline trong thread, giữ log/progress, hỗ trợ dừng chờ người dùng xác nhận."""
import json
import re
import os
import threading
import time
import uuid
from datetime import datetime, timezone

from app.config import JOBS_DIR

MAX_LOGS = 4000
# Emoji/ký hiệu trang trí bị lọc khỏi log (log của core, yt-dlp, Whisper...)
_EMOJI_RANGES = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0x2300, 0x23FF), (0xFE0F, 0xFE0F), (0x200D, 0x200D), (0x20E3, 0x20E3))
_EMOJI = re.compile('[' + ''.join(f'{chr(a)}-{chr(b)}' for a, b in _EMOJI_RANGES) + ']')
TERMINAL = ('done', 'error', 'cancelled')


class JobCancelled(Exception):
    pass


class WorkSlot:
    """Lượt dùng tài nguyên nặng (GPU/ffmpeg/Whisper) — tối đa `capacity` job chạy cùng lúc.

    Hàng chờ có ưu tiên: job vừa được người dùng xác nhận (RESUME) chạy trước job mới (NEW), cùng mức thì
    vào trước ra trước. Job đang chờ người dùng (sửa kịch bản / xem trước) TRẢ lượt để job sau chạy.
    """
    RESUME, NEW = 0, 1

    def __init__(self, capacity=1):
        self.capacity = capacity
        self._holders = set()
        self._waiters = []              # [(priority, seq, job_id)]
        self._seq = 0
        self._cond = threading.Condition()

    def acquire(self, job, priority):
        with self._cond:
            self._seq += 1
            ticket = (priority, self._seq, job.id)
            self._waiters.append(ticket)
            self._waiters.sort()
            try:
                while not (len(self._holders) < self.capacity and self._waiters[0] == ticket):
                    if job.cancelled:
                        raise JobCancelled()
                    self._cond.wait(timeout=0.5)
                self._holders.add(job.id)
            finally:
                self._waiters.remove(ticket)
                self._cond.notify_all()

    def release(self, job):
        with self._cond:
            self._holders.discard(job.id)
            self._cond.notify_all()

    def position(self, job_id):
        """Thứ tự trong hàng chờ (1 = kế tiếp), 0 nếu không chờ."""
        with self._cond:
            ids = [t[2] for t in self._waiters]
        return ids.index(job_id) + 1 if job_id in ids else 0


slot = WorkSlot(capacity=1)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _guess_tag(msg):
    m = msg.upper()
    if '[LỖI]' in m or '[ERR' in m or '[LOI]' in m or 'THẤT BẠI' in m:
        return 'err'
    if '[WARN' in m or '[CẢNH BÁO]' in m or '[KHOÁ]' in m:
        return 'warn'
    if '[OK]' in m or 'HOÀN TẤT' in m or 'HOÀN THÀNH' in m:
        return 'ok'
    if msg.lstrip().startswith('['):
        return 'info'
    return 'step'


class Job:
    def __init__(self, kind, config, title=''):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title or kind
        self.config = config
        self.status = 'queued'          # queued|running|waiting|done|error|cancelled
        self.waiting = None             # 'script' | 'preview' | None
        self.stage = ''
        self.progress = 0
        self.logs = []
        self.log_offset = 0             # số log đã bị cắt bớt khỏi đầu danh sách
        self.scenes = []
        self.result = {}
        self.error = ''
        self.created_at = _now()
        self.updated_at = self.created_at
        self.started = 0.0
        self.finished = 0.0
        self.temp_dir = ''
        self.checkpoint = {}            # trạng thái sau bước cuối đã xong — để tiếp tục khi lỗi (pipelines.py)
        self.draft = {}                 # bản nháp chỉnh sửa ở bước chờ (script/preview) — rời màn hình / tắt app không mất
        self.cancelled = False
        self._event = threading.Event()
        self._reply = None
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()   # log() được gọi từ nhiều luồng (dựng song song, API) — ghi file lần lượt
        self._last_save = 0.0

    # ---------- log / progress ----------
    def log(self, msg, tag=None):
        msg = _EMOJI.sub('', str(msg)).replace('  ', ' ') if _EMOJI.search(str(msg)) else str(msg)
        with self._lock:
            self.logs.append({'t': time.time(), 'msg': msg, 'tag': tag or _guess_tag(msg)})
            if len(self.logs) > MAX_LOGS:
                drop = len(self.logs) - MAX_LOGS
                self.logs = self.logs[drop:]
                self.log_offset += drop
            self.updated_at = _now()
        self.save(throttle=True)        # ghi xuống đĩa tối đa mỗi 2s — app tắt đột ngột vẫn còn log

    def set_progress(self, value, stage=''):
        self.progress = int(max(0, min(100, value)))
        if stage:
            self.stage = stage
        self.updated_at = _now()
        self.save(throttle=True)

    def check(self):
        if self.cancelled:
            raise JobCancelled()

    # ---------- chờ người dùng ----------
    def wait_for(self, what, stage):
        """Dừng pipeline cho tới khi người dùng xác nhận/huỷ. Trả về payload người dùng gửi."""
        self._event.clear()
        self._reply = None
        self.waiting = what
        self.status = 'waiting'
        self.stage = stage
        self.save()
        slot.release(self)
        self._event.wait()
        self.waiting = None
        self.check()
        reply = self._reply or {}
        if not reply.get('confirmed'):
            raise JobCancelled()
        self.status = 'queued'
        self.stage = 'Chờ lượt chạy'
        slot.acquire(self, WorkSlot.RESUME)
        self.status = 'running'
        return reply

    def resolve(self, payload):
        self.draft = {}                 # đã xác nhận → bản nháp hết tác dụng
        self._reply = payload
        self._event.set()

    def cancel(self):
        self.cancelled = True
        self._event.set()

    # ---------- serialize ----------
    def summary(self):
        return {
            'id': self.id, 'kind': self.kind, 'title': self.title, 'status': self.status,
            'waiting': self.waiting, 'stage': self.stage, 'progress': self.progress,
            'error': self.error, 'result': self.result, 'created_at': self.created_at,
            'updated_at': self.updated_at, 'elapsed': self.elapsed(),
            'scene_count': len(self.scenes),
            'queue_pos': slot.position(self.id) if self.status == 'queued' else 0,
            'resumable': self.resumable(),
            'resume_from': self.checkpoint.get('next_label', '') if self.resumable() else '',
        }

    def resumable(self):
        return (self.status in ('error', 'cancelled') and bool(self.checkpoint.get('done'))
                and bool(self.temp_dir) and os.path.isdir(self.temp_dir))

    def detail(self, with_logs=False):
        d = self.summary()
        d['config'] = self.config
        d['scenes'] = self.scenes
        d['draft'] = self.draft
        if with_logs:
            d['logs'] = self.logs[-3000:]
            d['log_cursor'] = self.log_offset + len(self.logs)
        return d

    def elapsed(self):
        if not self.started:
            return getattr(self, '_saved_elapsed', 0)
        return round((self.finished or time.time()) - self.started, 1)

    def save(self, throttle=False):
        with self._save_lock:
            now = time.time()
            if throttle and now - self._last_save < 2.0:
                return
            self._last_save = now
            data = self.detail()
            data['logs'] = self.logs[-1500:]
            data['temp_dir'] = self.temp_dir
            data['checkpoint'] = self.checkpoint
            path = os.path.join(JOBS_DIR, f'{self.id}.json')
            tmp = f'{path}.{threading.get_ident()}.tmp'
            try:
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, path)
            except (OSError, TypeError, ValueError):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    @classmethod
    def from_file(cls, path):
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        j = cls(d.get('kind', ''), d.get('config', {}), d.get('title', ''))
        j.id = d['id']
        j.status = d.get('status', 'error')
        if j.status not in TERMINAL:
            j.status = 'error'
            j.error = 'Ứng dụng đã tắt khi job đang chạy.'
        else:
            j.error = d.get('error', '')
        j.stage = d.get('stage', '')
        j.progress = d.get('progress', 0)
        j.scenes = d.get('scenes', [])
        j.result = d.get('result', {})
        j.logs = d.get('logs', [])
        j.temp_dir = d.get('temp_dir', '')
        j.checkpoint = d.get('checkpoint') or {}
        j.draft = d.get('draft') or {}
        j._saved_elapsed = d.get('elapsed', 0)
        j.created_at = d.get('created_at', j.created_at)
        j.updated_at = d.get('updated_at', j.updated_at)
        return j


class JobManager:
    def __init__(self):
        self.jobs = {}
        self._lock = threading.Lock()
        self._load()
        threading.Thread(target=self._cleanup_stale, daemon=True, name='temp-cleanup').start()

    def _load(self):
        for name in os.listdir(JOBS_DIR):
            if name.endswith('.tmp'):          # file ghi dở khi app tắt đột ngột
                try:
                    os.remove(os.path.join(JOBS_DIR, name))
                except OSError:
                    pass
                continue
            if not name.endswith('.json'):
                continue
            try:
                j = Job.from_file(os.path.join(JOBS_DIR, name))
                self.jobs[j.id] = j
            except Exception:
                continue

    def _cleanup_stale(self, max_age_days=1):
        """Dọn thư mục tạm cũ không job nào còn dùng (job lỗi/huỷ đã xoá, app tắt giữa chừng…) + giọng thử cũ.
        Mỗi thư mục tạm có thể chứa cả bộ phim tải về — để lâu ngày đầy ổ."""
        import shutil
        keep = {os.path.normcase(os.path.abspath(j.temp_dir)) for j in list(self.jobs.values()) if j.temp_dir}
        cutoff = time.time() - max_age_days * 86400
        roots = set()
        for d in ('C', 'D', 'E', 'F', 'G'):
            r = os.path.join(f'{d}:' + os.sep, 'ReviewFilm_Temp')
            if os.path.isdir(r):
                roots.add(r)
        freed, n = 0, 0
        for root in roots:
            for name in os.listdir(root):
                path = os.path.join(root, name)
                try:
                    if not name.startswith('_temp_') or os.path.normcase(path) in keep or os.path.getmtime(path) > cutoff:
                        continue
                    size = sum(os.path.getsize(os.path.join(a, f)) for (a, _, fs) in os.walk(path) for f in fs)
                    shutil.rmtree(path, ignore_errors=True)
                    freed, n = freed + size, n + 1
                except OSError:
                    continue
        preview = os.path.join(os.path.dirname(JOBS_DIR), 'voice_preview')
        if os.path.isdir(preview):
            for name in os.listdir(preview):
                path = os.path.join(preview, name)
                try:
                    if os.path.getmtime(path) < cutoff:
                        shutil.rmtree(path, ignore_errors=True)
                except OSError:
                    pass
        if n:
            try:
                print(f'[don dep] da xoa {n} thu muc tam cu ({freed / 1_048_576:.0f} MB)', flush=True)
            except Exception:
                pass

    def list(self):
        return sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get(self, job_id):
        j = self.jobs.get(job_id)
        if not j:
            raise KeyError(f'Job không tồn tại: {job_id}')
        return j

    def start(self, kind, config, runner, title=''):
        """Tạo job và xếp hàng. Job chạy khi tới lượt (xem WorkSlot)."""
        job = Job(kind, config, title)
        with self._lock:
            self.jobs[job.id] = job
        return self._launch(job, runner)

    def start_seeded(self, kind, config, runner, title, scenes, checkpoint, result=None):
        """Tạo job mới đã có sẵn kịch bản + checkpoint → pipeline bỏ qua các bước đã xong (dùng cho "Mở lại hậu kỳ")."""
        job = Job(kind, config, title)
        job.scenes = scenes
        job.checkpoint = checkpoint
        job.result = dict(result or {})
        with self._lock:
            self.jobs[job.id] = job
        return self._launch(job, runner)

    def resume(self, job_id, runner):
        """Chạy tiếp job lỗi/đã huỷ từ bước sau checkpoint — cùng job, giữ log và kết quả cũ."""
        job = self.get(job_id)
        if not job.resumable():
            raise ValueError('Job này không tiếp tục được (chưa xong bước nào, hoặc thư mục tạm đã bị xoá) — hãy chạy lại từ đầu.')
        job.cancelled = False
        job.error = ''
        job.waiting = None
        job.finished = 0.0
        job._event = threading.Event()
        job.log(f"[TIẾP TỤC] Chạy tiếp từ bước: {job.checkpoint.get('next_label') or '?'}", 'info')
        return self._launch(job, runner)

    def _launch(self, job, runner):
        job.status = 'queued'
        job.stage = 'Chờ lượt chạy'
        job.save()

        def _run():
            holding = False
            try:
                slot.acquire(job, WorkSlot.NEW)
                holding = True
                job.status = 'running'
                job.stage = 'Bắt đầu'
                job.started = time.time()
                job.log(f'[BẮT ĐẦU] {job.title}', 'info')
                job.save()
                runner(job)
                job.status = 'done'
                job.progress = 100
                job.stage = 'Hoàn thành'
                job.log(f'[HOÀN THÀNH] Xong sau {job.elapsed():.0f}s', 'ok')
            except JobCancelled:
                job.status = 'cancelled'
                job.stage = 'Đã huỷ'
                job.log('[DỪNG] Job đã bị huỷ.', 'warn')
            except Exception as e:
                import traceback
                job.status = 'error'
                job.error = str(e) or e.__class__.__name__
                job.stage = 'Lỗi'
                job.log(f'[LỖI] {job.error}', 'err')
                job.log(traceback.format_exc(), 'err')
            finally:
                if holding:
                    slot.release(job)
                job.finished = time.time()
                job.waiting = None
                job.save()

        threading.Thread(target=_run, daemon=True, name=f'job-{job.id}').start()
        return job

    def cancel(self, job_id):
        job = self.get(job_id)
        was_running = job.status == 'running'
        job.cancel()
        if not was_running:
            return job
        try:
            from core.utils import kill_all_active_processes
            threading.Thread(target=kill_all_active_processes, daemon=True).start()
        except Exception:
            pass
        return job

    def delete(self, job_id):
        job = self.get(job_id)
        if job.status not in TERMINAL:
            raise ValueError('Job đang chạy — hãy dừng trước khi xoá.')
        self.jobs.pop(job_id, None)
        try:
            os.remove(os.path.join(JOBS_DIR, f'{job_id}.json'))
        except OSError:
            pass
        if job.temp_dir and os.path.isdir(job.temp_dir):
            import shutil
            shutil.rmtree(job.temp_dir, ignore_errors=True)


manager = JobManager()
