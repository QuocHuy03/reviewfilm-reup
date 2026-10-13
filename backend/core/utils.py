

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
_FFMPEG_SEARCH_DIRS += ['C:\\ffmpeg\\bin', 'C:\\Program Files\\ffmpeg\\bin', os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AutoReviewStudio', 'cache', 'ffmpeg', 'bin'), 'C:\\Users\\Admin\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-8.1.1-full_build\\bin']
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
        r = run_subprocess(cmd, timeout=30, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(r.stdout.strip())
    except Exception as e:
        print(f'''[LOI] ffprobe khong doc duoc thoi luong video \'{video_path}\': {e}''')
        return 0.0
def get_audio_duration(audio_path):
    return get_video_duration(audio_path)
def new_studio_temp_dir(output_dir, prefix):
    import tempfile as _tm
    out_drive = os.path.splitdrive(os.path.abspath(output_dir))[0]
    if not out_drive:
        out_drive = os.path.splitdrive(_tm.gettempdir())[0]
    temp_root = os.path.join(out_drive + os.sep, 'AutoReviewStudio_Temp')
    os.makedirs(temp_root, exist_ok=True)
    run_id = time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[slice(None, 6, None)]
    temp_dir = os.path.join(temp_root, f'''_temp_{prefix}_{run_id}''')
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir
def audio_file_ok(path):
    try:
        return bool(path) and os.path.getsize(path) > 44
    except Exception:
        return False
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
def studio_audio_dir(output_dir='', run_id=None):
    if not run_id:
        run_id = time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[slice(None, 6, None)]
    root = None
    if output_dir:
        try:
            base = os.path.join(os.path.abspath(output_dir), 'AutoReviewStudio_audio')
            if _dir_is_writable(base):
                root = base
        except Exception:
            pass
    if root is None:
        la = os.environ.get('LOCALAPPDATA', '')
        if la:
            base = os.path.join(la, 'AutoReviewStudio', 'audio')
            if _dir_is_writable(base):
                root = base
    if root is None:
        root = _first_writable_drive_audio_root()
    if root is None:
        root = os.path.join(os.path.expanduser('~'), 'AutoReviewStudio', 'audio')
    if 'temp' in os.path.basename(os.path.normpath(root)).lower():
        root = os.path.join(os.path.expanduser('~'), 'AutoReviewStudio', 'audio')
    audio_dir = os.path.join(root, run_id)
    os.makedirs(audio_dir, exist_ok=True)
    return audio_dir
def cleanup_temp(temp_dir, log_fn=print, retries=5, delay=0.8):
    if not os.path.exists(temp_dir):
        return
    for attempt in range(retries):
        try:
            shutil.rmtree(temp_dir)
            log_fn('   [DON DEP] Da xoa thu muc temp')
            return
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                log_fn(f'''   [WARN] Khong xoa duoc temp sau {retries} lan thu: {e}''')
def cleanup_old_temp_dirs(log_fn=print, max_age_hours=2.0):
    import string
    import tempfile as _tempfile_mod
    cutoff = time.time() - max_age_hours * 3600
    prefixes = ('_temp_', 'vieneu_prev_')
    _referenced_dirs = set()
    try:
        from core import session_store as _session_store
        _live_data = _session_store.load_session()
        if _live_data:
            _audio_temp = _live_data.get('audio_temp_dir') or ''
            if _audio_temp:
                _referenced_dirs.add(os.path.normcase(os.path.normpath(_audio_temp)))
            for _s in _live_data.get('scenes') or []:
                _tp = _s.get('tts_path') if isinstance(_s, dict) else None
                if _tp:
                    _referenced_dirs.add(os.path.normcase(os.path.normpath(os.path.dirname(_tp))))
    except Exception:
        pass
    def _is_referenced(candidate_full):
        cnorm = os.path.normcase(os.path.normpath(candidate_full))
        cbound = cnorm + os.sep
        for ref in _referenced_dirs:
            if ref == cnorm or ref.startswith(cbound):
                return True
        return False
    scan_dirs = set()
    scan_dirs.add(_tempfile_mod.gettempdir())
    scan_dirs.add(os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'AutoReviewStudio', 'cache'))
    for letter in string.ascii_uppercase:
        d = f'''{letter}:\\AutoReviewStudio_Temp'''
        if os.path.isdir(d):
            scan_dirs.add(d)
    removed = 0
    for base in scan_dirs:
        if not os.path.isdir(base):
            continue
        try:
            entries = os.listdir(base)
        except Exception:
            continue
        for name in entries:
            if not name.startswith(prefixes):
                continue
            full = os.path.join(base, name)
            if not os.path.isdir(full):
                continue
            if _is_referenced(full):
                continue
            try:
                if os.path.getmtime(full) >= cutoff:
                    continue
            except Exception:
                continue
            try:
                shutil.rmtree(full)
                removed += 1
            except Exception as e:
                log_fn(f'''   [WARN] Khong xoa duoc rac cu {full}: {e}''')
    if removed:
        log_fn(f'''   [DON DEP] Da xoa {removed} thu muc tam rac cu (>{max_age_hours:.0f}h)''')
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
def cleanup_orphan_audio_dirs(output_dir='', extra_referenced=None, log_fn=print, max_age_days=14.0, roots=None):
    ref_set = set()
    try:
        from core import session_store as _session_store
        ref_set |= _session_store.referenced_audio_dirs()
    except Exception:
        pass
    for r in extra_referenced or ():
        ref_set.add(os.path.normcase(os.path.normpath(r)))
    if roots is None:
        roots = _audio_home_roots(output_dir)
    def _referenced(full):
        cnorm = os.path.normcase(os.path.normpath(full))
        cbound = cnorm + os.sep
        for k in ref_set:
            if k == cnorm or k.startswith(cbound):
                return True
        return False
    removed = 0
    for base in roots:
        if not os.path.isdir(base):
            continue
        if os.path.basename(os.path.normpath(base)).lower() not in _AUDIO_HOME_PARENTS:
            continue
        try:
            entries = os.listdir(base)
        except Exception:
            continue
        for name in entries:
            full = os.path.join(base, name)
            if not os.path.isdir(full):
                continue
            referenced = _referenced(full)
            try:
                age_days = (time.time() - os.path.getmtime(full)) / 86400.0
            except Exception:
                age_days = -1.0
            try:
                nfiles = sum((len(fs) for (_, _, fs) in os.walk(full)))
            except Exception:
                nfiles = -1
            if referenced or age_days < 0 or age_days <= max_age_days:
                continue
            try:
                shutil.rmtree(full)
                removed += 1
                log_fn(f'''   [GC-AUDIO] XOA {full} | tuoi={age_days:.1f}d | files={nfiles} | ly_do=mo_coi+qua_han | referenced={referenced}''')
            except Exception as e:
                log_fn(f'''   [GC-AUDIO][WARN] Khong xoa duoc {full}: {e}''')
    if removed:
        log_fn(f'''   [GC-AUDIO] Tong xoa {removed} thu muc audio mo coi (>{max_age_days:.0f} ngay)''')
    return removed
def safe_filename(name):
    bad = '<>:"/\\|?*'
    for c in bad:
        name = name.replace(c, '_')
    return name.strip()[slice(None, 100, None)]
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path
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