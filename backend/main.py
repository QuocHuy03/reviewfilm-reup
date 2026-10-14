"""Entry point của backend ReviewFilm.

- `python main.py [--port 8765]`              → chạy FastAPI (uvicorn)
- `python main.py --whisper-worker args res`  → tiến trình Whisper riêng (core.transcriber gọi)
- `python main.py --xtts-worker ...` / `--vieneu-worker ...` → worker TTS
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def _whisper_worker(args_file, result_file):
    with open(args_file, 'r', encoding='utf-8') as f:
        wargs = json.load(f)
    try:
        from core.transcriber import _run_whisper_py
        res = _run_whisper_py(wargs['audio_path'], wargs['model'], wargs['language'],
                              lambda m: print(m, flush=True), wargs['device'])
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({'ok': True, 'result': res}, f, ensure_ascii=False)
    except Exception as e:
        import traceback
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({'ok': False, 'error': str(e), 'tb': traceback.format_exc()}, f, ensure_ascii=False)


def _run_worker(flag, module):
    import importlib
    idx = sys.argv.index(flag)
    sys.argv = [sys.argv[0]] + sys.argv[idx + 1:]
    try:
        importlib.import_module(module).main()
    except Exception as e:
        print(f'[{flag}] FAIL: {e}', file=sys.stderr, flush=True)
        sys.exit(3)
    sys.exit(0)


def _watch_parent(pid):
    """Tự thoát khi Electron (process cha) biến mất — tránh backend mồ côi giữ cổng."""
    import threading
    import time

    def alive():
        if os.name == 'nt':
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return code.value == 259  # STILL_ACTIVE
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def loop():
        while alive():
            time.sleep(2)
        os._exit(0)

    threading.Thread(target=loop, daemon=True).start()


def main():
    if '--whisper-worker' in sys.argv:
        i = sys.argv.index('--whisper-worker')
        _whisper_worker(sys.argv[i + 1], sys.argv[i + 2])
        sys.exit(0)
    if '--xtts-worker' in sys.argv:
        _run_worker('--xtts-worker', 'workers.xtts_worker')
    if '--vieneu-worker' in sys.argv:
        _run_worker('--vieneu-worker', 'workers.vieneu_worker')

    port = 8765
    if '--port' in sys.argv:
        port = int(sys.argv[sys.argv.index('--port') + 1])
    if '--parent-pid' in sys.argv:
        _watch_parent(int(sys.argv[sys.argv.index('--parent-pid') + 1]))
    import uvicorn
    if os.name == 'nt':
        # Proactor loop in traceback ConnectionResetError mỗi khi client đóng kết nối SSE — vô hại, làm rác log.
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # loop='none': dùng đúng policy Selector đặt ở trên (uvicorn 0.5x mặc định ép Proactor trên Windows)
    uvicorn.run('app.main:app', host='127.0.0.1', port=port, log_level='warning', loop='none' if os.name == 'nt' else 'auto')


if __name__ == '__main__':
    main()
