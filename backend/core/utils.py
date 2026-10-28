

'Utilities chung'
import os
import sys
import shutil
import subprocess
import threading
import time
# ẩn cửa sổ console + ƯU TIÊN THẤP cho mọi tiến trình con (ffmpeg, worker…) — chạy nền như HandBrake, máy không đơ
_HIDE = (subprocess.CREATE_NO_WINDOW | 0x00004000) if sys.platform == 'win32' else 0
def _ffmpeg_base_dirs():
    dirs = []
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        dirs.append(exe_dir)
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            dirs.append(meipass)
    else:
        dirs.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return dirs
_FFMPEG_SEARCH_DIRS = []
for _b in _ffmpeg_base_dirs():
    _FFMPEG_SEARCH_DIRS.append(os.path.join(_b, 'bin'))
    _FFMPEG_SEARCH_DIRS.append(_b)
_FFMPEG_SEARCH_DIRS += ['C:\\ffmpeg\\bin', 'C:\\Program Files\\ffmpeg\\bin', os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AutoReviewStudio', 'cache', 'ffmpeg', 'bin')]
def _find_exe(name):
    for d in _FFMPEG_SEARCH_DIRS:
        p = os.path.join(d, name + '.exe')
        if os.path.isfile(p):
            return p
    found = shutil.which(name)
    if found:
        return found
    return name
FFMPEG_EXE = _find_exe('ffmpeg')
FFPROBE_EXE = _find_exe('ffprobe')
_active_procs: set = set()
_active_procs_lock = threading.Lock()
def register_process(proc):
    with _active_procs_lock:
        _active_procs.add(proc)
def unregister_process(proc):
    with _active_procs_lock:
        _active_procs.discard(proc)
def kill_all_active_processes():
    with _active_procs_lock:
        procs = list(_active_procs)
        _active_procs.clear()
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(0.3)
    for p in procs:
        try:
            p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
def fast_aac(cmd):
    """Mã hoá AAC trung gian bằng bộ "fast" (nhanh ~2.5–4 lần bộ mặc định "twoloop", ở 192k nghe không khác) — tiếng của
    1 video qua 4–5 lượt mã hoá (clip → ghép → nhạc nền → hiệu ứng → chuẩn âm lượng), lượt twoloop ghép 3 phút tiếng mất
    13s. Lệnh đã tự chọn bộ mã hoá (vd lượt cuối chuẩn âm lượng: twoloop) thì giữ nguyên."""
    if '-aac_coder' in cmd:
        return cmd
    out = []
    for (k, x) in enumerate(cmd):
        out.append(x)
        if x == 'aac' and k > 0 and str(cmd[k - 1]).startswith(('-c:a', '-acodec', '-codec:a')):
            out += ['-aac_coder', 'fast']
    return out


def _budgeted(cmd):
    """ffmpeg → giới hạn luồng theo ngân sách CPU chung (core/perf.py) + AAC trung gian mã hoá nhanh; lệnh khác giữ nguyên."""
    try:
        from core import perf
        if not isinstance(cmd, (list, tuple)):
            return cmd
        cmd = perf.ffmpeg_threads(list(cmd), perf.current_parallel())
        return fast_aac(cmd) if str(cmd[0]).lower().replace('\\', '/').rsplit('/', 1)[-1].startswith('ffmpeg') else cmd
    except Exception:
        return cmd


def run_subprocess(cmd, timeout=None, **kwargs):
    kwargs.setdefault('creationflags', _HIDE)
    cmd = _budgeted(cmd)
    proc = None
    try:
        proc = subprocess.Popen(*(cmd,), **{k: v for (k, v) in kwargs.items() if k not in ('timeout',)})
        register_process(proc)
        try:
            (stdout, stderr) = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            (stdout, stderr) = proc.communicate()
        return subprocess.CompletedProcess(args=cmd, returncode=proc.returncode, stdout=stdout, stderr=stderr)
    finally:
        if proc is not None:
            unregister_process(proc)
def run_subprocess_heartbeat(cmd, log_fn=print, label='', heartbeat_sec=8.0, timeout=None, **kwargs):
    kwargs.setdefault('creationflags', _HIDE)
    cmd = _budgeted(cmd)
    kwargs.setdefault('stdout', subprocess.PIPE)
    kwargs.setdefault('stderr', subprocess.PIPE)
    proc = subprocess.Popen(*(cmd,), **kwargs)
    register_process(proc)
    start = time.monotonic()
    try:
        while True:
            try:
                (stdout, stderr) = proc.communicate(timeout=heartbeat_sec)
                break
            except subprocess.TimeoutExpired:
                elapsed = int(time.monotonic() - start)
                if timeout and elapsed >= timeout:
                    proc.kill()
                    (stdout, stderr) = proc.communicate()
                    break
                if label:
                    log_fn(f'''   ... {label} (vẫn đang chạy, {elapsed}s, chưa bị treo)''')
        return subprocess.CompletedProcess(args=cmd, returncode=proc.returncode, stdout=stdout, stderr=stderr)
    finally:
        unregister_process(proc)
def get_video_duration(video_path):
    cmd = [FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    try:
        r = run_subprocess(cmd, timeout=30, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        return float(r.stdout.strip())
    except Exception as e:
        print(f'''[LỖI] ffprobe không đọc được thời lượng video \'{video_path}\': {e}''')
        return 0.0
def safe_filename(name):
    bad = '<>:"/\\|?*'
    for c in bad:
        name = name.replace(c, '_')
    return name.strip()[slice(None, 100, None)]
# Giọng mẫu: backend/voice_samples/ (Edge/FPT/VieNeu chung), thư mục con cho từng engine.
VOICE_SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'voice_samples')
VOICE_SAMPLE_KINDS = ('', 'vieneu', 'vieneu3_clone', 'vieneu3_ref')


def voice_samples_dir(kind=''):
    """kind: '' (thư mục gốc) | 'vieneu' | 'vieneu3_clone' | 'vieneu3_ref'."""
    return os.path.join(VOICE_SAMPLES_DIR, kind) if kind else VOICE_SAMPLES_DIR


def get_free_space_gb(path):
    import shutil as _shutil
    try:
        target = path if os.path.isdir(path) else '.'
        drive = os.path.splitdrive(os.path.abspath(target))[0] + os.sep
        usage = _shutil.disk_usage(drive)
        return usage.free / 1073741824
    except Exception:
        return -1.0

def audio_lead_filter(path):
    """File TS / HLS hay có luồng TIẾNG bắt đầu muộn hơn hình. Trích âm thanh thì mất khoảng trễ đó → mọi mốc câu nhận
    dạng giọng nói sớm hơn hình đúng bằng khoảng trễ. → ['-af', 'adelay=…'] chèn lặng đầu cho tiếng khớp hình, [] nếu không lệch."""
    try:
        r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-show_entries', 'stream=codec_type,start_time', '-show_entries', 'format=start_time',
                            '-of', 'json', path], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20, creationflags=_HIDE)
        import json as _j
        d = _j.loads(r.stdout or '{}')
        base = float((d.get('format') or {}).get('start_time') or 0)
        a = [float(s['start_time']) for s in d.get('streams') or [] if s.get('codec_type') == 'audio' and s.get('start_time') not in (None, 'N/A')]
        lead = (a[0] - base) if a else 0.0
    except Exception:
        return []
    if 0.02 < lead < 30:
        return ['-af', f'adelay={int(round(lead * 1000))}:all=1']
    return []
