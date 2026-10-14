

'Utilities chung'
import os
import sys
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
_HIDE = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
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
def run_subprocess(cmd, timeout=None, **kwargs):
    kwargs.setdefault('creationflags', _HIDE)
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
                    log_fn(f'''   ... {label} (van dang chay, {elapsed}s, chua bi treo)''')
        return subprocess.CompletedProcess(args=cmd, returncode=proc.returncode, stdout=stdout, stderr=stderr)
    finally:
        unregister_process(proc)
def format_time(seconds):
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f'''{h:02d}:{m:02d}:{s:02d},{ms:03d}'''
def get_video_duration(video_path):
    cmd = [FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    try:
        r = run_subprocess(cmd, timeout=30, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        return float(r.stdout.strip())
    except Exception as e:
        print(f'''[LOI] ffprobe khong doc duoc thoi luong video \'{video_path}\': {e}''')
        return 0.0
def _dir_is_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        test = os.path.join(path, '.w_' + uuid.uuid4().hex[slice(None, 8, None)])
        with open(test, 'wb') as f:
            f.write(b'0')
        os.remove(test)
        return True
    except Exception:
        return False
def _first_writable_drive_audio_root():
    import string
    letters = [l for l in string.ascii_uppercase if l != 'C'] + ['C']
    for letter in letters:
        root = f'''{letter}:\\'''
        cand = os.path.join(root, 'AutoReviewStudio_audio')
        if os.path.isdir(root) and _dir_is_writable(cand):
            return cand
    return None
def _audio_home_roots(output_dir=''):
    import string
    roots = set()
    la = os.environ.get('LOCALAPPDATA', '')
    if la:
        roots.add(os.path.join(la, 'AutoReviewStudio', 'audio'))
    if output_dir:
        try:
            roots.add(os.path.join(os.path.abspath(output_dir), 'AutoReviewStudio_audio'))
        except Exception:
            pass
    for letter in string.ascii_uppercase:
        d = f'''{letter}:\\AutoReviewStudio_audio'''
        if os.path.isdir(d):
            roots.add(d)
    return roots
_AUDIO_HOME_PARENTS = {'autoreviewstudio_audio', 'audio'}
def safe_filename(name):
    bad = '<>:"/\\|?*'
    for c in bad:
        name = name.replace(c, '_')
    return name.strip()[slice(None, 100, None)]
# Giọng mẫu: backend/voice_samples/ (Edge/FPT/VieNeu chung), thư mục con cho từng engine.
VOICE_SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'voice_samples')
VOICE_SAMPLE_KINDS = ('', 'vieneu', 'vieneu3_clone', 'vieneu3_ref', 'xtts')


def voice_samples_dir(kind=''):
    """kind: '' (thư mục gốc) | 'vieneu' | 'vieneu3_clone' | 'vieneu3_ref' | 'xtts'."""
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