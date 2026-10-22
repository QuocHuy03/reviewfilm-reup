"""Cài VieNeu TTS ngay trong app (nút "Tải model" ở trang Giọng đọc).

VieNeu chạy trong môi trường Python RIÊNG (DATA_DIR/vieneu/env) — thư viện của nó không đụng tới thư viện
của app, cài hỏng thì xoá đi cài lại không ảnh hưởng gì. Bản ONNX chạy CPU, không cần torch / card màn hình.

Các bước: tạo môi trường → cài thư viện (~570 MB) → tải model từ HuggingFace (~610 MB) → đọc thử 1 câu.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from app.config import DATA_DIR

from .utils import _HIDE

VERSION = '3.8.3'                    # khoá phiên bản: danh sách giọng trong app khớp với model của bản này
ROOT = os.path.join(DATA_DIR, 'vieneu')
ENV = os.path.join(ROOT, 'env')
HUB = os.path.join(ROOT, 'hf')
READY = os.path.join(ROOT, 'ready.json')
PY = os.path.join(ENV, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(ENV, 'bin', 'python')
# thư viện vieneu cần khi chạy (bỏ gradio — chỉ dùng cho giao diện web demo của họ, rất nặng)
DEPS = ['sea-g2p>=0.9.1', 'onnxruntime>=1.20.0', 'numpy', 'soundfile', 'soxr', 'kaldi-native-fbank>=1.20',
        'tokenizers>=0.20', 'huggingface_hub', 'PyYAML', 'librosa>=0.11.0']
NEED_GB = 1.5
MODEL_MB = 610
WORKER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'workers', 'vieneu_worker.py')
STEPS = [('env', 'Tạo môi trường'), ('pip', 'Cài thư viện'), ('model', 'Tải model'), ('test', 'Đọc thử')]

_lock = threading.Lock()
_state = {'running': False, 'step': '', 'progress': 0, 'message': '', 'error': '', 'log': []}
_proc = None
_cancel = False


def hf_env(offline=False):
    env = os.environ.copy()
    env.update({'HF_HOME': HUB, 'HUGGINGFACE_HUB_CACHE': os.path.join(HUB, 'hub'), 'HF_HUB_DISABLE_XET': '1',
                'HF_HUB_DISABLE_TELEMETRY': '1', 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1', 'PYTHONWARNINGS': 'ignore'})
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    if offline:
        env['HF_HUB_OFFLINE'] = '1'      # đã tải đủ → không gọi mạng mỗi lần tạo giọng (nhanh hơn, chạy được khi mất mạng)
    return env


def installed():
    return os.path.isfile(PY) and os.path.isfile(READY)


def worker_cmd():
    """→ (lệnh chạy worker, thư mục model) nếu đã cài qua app, ngược lại None."""
    if not installed():
        return None
    return ([PY, '-W', 'ignore', WORKER], HUB)


def _dir_mb(path):
    total = 0
    for (root, _, files) in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 1048576


def status():
    with _lock:
        st = {k: (list(v) if isinstance(v, list) else v) for (k, v) in _state.items()}
    st['installed'] = installed()
    st['steps'] = [{'id': i, 'label': l} for (i, l) in STEPS]
    st['size_mb'] = MODEL_MB + 570
    if st['installed']:
        try:
            with open(READY, encoding='utf-8') as f:
                st['info'] = json.load(f)
        except (OSError, ValueError):
            st['info'] = {}
    return st


def _set(**kw):
    with _lock:
        _state.update(kw)
        msg = kw.get('message')
        if msg:
            _state['log'] = (_state['log'] + [msg])[-40:]


def _run(cmd, on_line=None, env=None, timeout=3600):
    """Chạy lệnh con (huỷ được). Lỗi → RuntimeError kèm vài dòng cuối."""
    global _proc
    if _cancel:
        raise InterruptedError()
    _proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                             errors='replace', creationflags=_HIDE, env=env or hf_env())
    tail = []
    deadline = time.time() + timeout
    try:
        for line in _proc.stdout:
            line = line.strip()
            if not line:
                continue
            tail = (tail + [line])[-12:]
            if on_line:
                on_line(line)
            if time.time() > deadline:
                _proc.kill()
                raise RuntimeError('quá thời gian')
        code = _proc.wait()
    finally:
        _proc = None
    if _cancel:
        raise InterruptedError()
    if code != 0:
        raise RuntimeError('\n'.join(tail[-6:]) or f'mã lỗi {code}')
    return tail


def _base_python():
    # đang chạy trong venv của app → tạo venv mới từ Python gốc (venv lồng venv vẫn chạy, nhưng gốc sạch hơn)
    base = getattr(sys, '_base_executable', '') or sys.executable
    return base if os.path.isfile(base) else sys.executable


def _install():
    global _cancel
    try:
        os.makedirs(ROOT, exist_ok=True)
        free_gb = shutil.disk_usage(ROOT).free / 1024 ** 3
        if free_gb < NEED_GB:
            raise RuntimeError(f'Ổ đĩa chứa dữ liệu app chỉ còn {free_gb:.1f} GB — cần khoảng {NEED_GB:g} GB trống.')
        if os.path.isfile(READY):
            os.remove(READY)

        # 1. môi trường Python riêng (bỏ qua nếu đã có và chạy được)
        _set(step='env', progress=3, message='Tạo môi trường Python riêng cho VieNeu…')
        ok = False
        if os.path.isfile(PY):
            ok = subprocess.run([PY, '-c', 'import sys'], capture_output=True, creationflags=_HIDE).returncode == 0
        if not ok:
            shutil.rmtree(ENV, ignore_errors=True)
            _run([_base_python(), '-m', 'venv', ENV])

        # 2. thư viện
        _set(step='pip', progress=8, message='Cài thư viện VieNeu (~570 MB, vài phút)…')
        n = [0]

        def pip_line(line):
            if line.startswith(('Collecting', 'Downloading', 'Installing', 'Successfully')):
                n[0] += 1
                _set(progress=min(45, 8 + n[0]), message=line[:140])
        pip = [PY, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location', '--progress-bar', 'off']
        _run(pip + ['--upgrade', 'pip'])
        _run(pip + DEPS, pip_line)
        _run(pip + ['--no-deps', f'vieneu=={VERSION}'], pip_line)

        # 3. model: nạp 1 lần là thư viện tự tải về HUB; theo dõi dung lượng thư mục để hiện %
        _set(step='model', progress=47, message=f'Tải model VieNeu (~{MODEL_MB} MB)…')
        done = threading.Event()

        def watch():
            while not done.wait(1.5):
                mb = _dir_mb(HUB)
                _set(progress=47 + int(min(1.0, mb / MODEL_MB) * 38), message=f'Tải model: {min(mb, MODEL_MB):.0f}/{MODEL_MB} MB' if mb < MODEL_MB else 'Tải model: đang hoàn tất…')
        threading.Thread(target=watch, daemon=True).start()
        try:
            # đọc thử cả giọng có sẵn lẫn clone → tải luôn phần mã hoá giọng mẫu (clone tải riêng nếu không làm bước này)
            _test(online=True)
        finally:
            done.set()

        # 4. kiểm tra chạy offline đúng như lúc tạo video
        _set(step='test', progress=92, message='Đọc thử bằng VieNeu…')
        secs = _test(online=False)
        with open(READY, 'w', encoding='utf-8') as f:
            json.dump({'version': VERSION, 'at': time.strftime('%Y-%m-%d %H:%M'), 'test_seconds': round(secs, 1),
                       'size_mb': round(_dir_mb(ENV) + _dir_mb(HUB))}, f)
        _set(running=False, step='done', progress=100, message='VieNeu đã sẵn sàng — giọng VieNeu dùng được ngay.', error='')
        _reset_cache()
    except InterruptedError:
        _set(running=False, step='', progress=0, message='Đã huỷ cài VieNeu.', error='')
    except Exception as e:
        _set(running=False, error=str(e)[:600], message='Cài VieNeu lỗi.')
    finally:
        _cancel = False


def _test(online):
    """Chạy đúng worker mà lúc tạo video dùng: 1 câu giọng có sẵn + 1 câu clone từ file mẫu."""
    from .utils import voice_samples_dir
    tmp = tempfile.mkdtemp(prefix='vieneu_test_')
    try:
        t0 = time.time()
        jobs = [('hai-dang', '')]
        ref = os.path.join(voice_samples_dir(), 'trung_dung.wav')
        if os.path.isfile(ref):
            jobs.append(('clone', ref))
        for (k, (voice, ref_path)) in enumerate(jobs):
            out = os.path.join(tmp, f'{k}.wav')
            batch = os.path.join(tmp, f'{k}.json')
            with open(batch, 'w', encoding='utf-8') as f:
                json.dump([{'text': 'Xin chào, đây là giọng đọc VieNeu.', 'out': out}], f, ensure_ascii=False)
            _run([PY, '-W', 'ignore', WORKER, batch, voice, ref_path, HUB], env=hf_env(offline=not online), timeout=1800)
            if not os.path.isfile(out) or os.path.getsize(out) < 2000:
                raise RuntimeError(f'Đọc thử ({"clone" if voice == "clone" else voice}) không ra âm thanh — xem log.')
        return time.time() - t0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _reset_cache():
    try:
        from app.features.voices import router
        router._vieneu_ready = None
    except Exception:
        pass


def start():
    global _cancel
    with _lock:
        if _state['running']:
            return False
        _state.update(running=True, step='env', progress=1, message='Bắt đầu cài VieNeu…', error='', log=[])
    _cancel = False
    threading.Thread(target=_install, daemon=True).start()
    return True


def cancel():
    global _cancel
    _cancel = True
    p = _proc
    if p and p.poll() is None:
        p.kill()


def uninstall():
    if _state['running']:
        raise RuntimeError('Đang cài — huỷ trước khi gỡ.')
    shutil.rmtree(ROOT, ignore_errors=True)
    _set(step='', progress=0, message='Đã gỡ VieNeu.', error='')
    _reset_cache()
