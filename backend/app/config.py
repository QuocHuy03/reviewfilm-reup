"""Đường dẫn + cài đặt người dùng (lưu JSON) + API key (.env)."""
import json
import os
import threading

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_VERSION = os.environ.get('RF_APP_VERSION', 'dev')

# Bản cài đặt: Electron truyền RF_DATA_DIR = %APPDATA%/reviewfilm/data → cập nhật app (ghi đè thư mục
# cài đặt) không làm mất cài đặt, API key, lịch sử job. Chạy dev: giữ trong backend/ như cũ.
_USER_DATA = os.environ.get('RF_DATA_DIR', '').strip()
DATA_DIR = _USER_DATA or os.path.join(BACKEND_DIR, 'data')
JOBS_DIR = os.path.join(DATA_DIR, 'jobs')
ENV_FILE = os.path.join(DATA_DIR, '.env') if _USER_DATA else os.path.join(BACKEND_DIR, '.env')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
PRESETS_FILE = os.path.join(DATA_DIR, 'presets.json')       # mẫu cấu hình theo kênh

os.makedirs(JOBS_DIR, exist_ok=True)

# Key giọng đọc cao cấp: tên biến môi trường → nhãn hiển thị.
# AI (Vision, viết kịch bản, dịch, phân vai) chạy bằng tài khoản ChatGPT/Gemini đăng nhập trong app — không cần key.
API_KEYS = {
    'FPT_API_KEY': 'FPT.AI (giọng cao cấp)',
    'CAPCUT_COOKIE': 'Tài khoản CapCut (tuỳ chọn)',
}

DEFAULT_SETTINGS = {
    'output_dir': os.path.join(os.path.expanduser('~'), 'Videos', 'ReviewFilm'),
    'whisper_model': 'base',
    'device': 'GPU (NVIDIA)',
    'voice': 'Edge TTS — Nữ Bắc (miễn phí)',
    'sub_style': 'Mặc định (chữ trắng, viền đen)',
    'sub_layout': '2 dòng gọn (khuyên dùng)',
    'light_mode': False,
    'gpu_encode': True,    # dựng video bằng GPU NVIDIA (NVENC) khi dùng được — tự lùi về CPU nếu không   # chế độ nhẹ máy: dùng nửa CPU, dựng 1 clip / lượt — vừa chạy tool vừa làm việc khác
    'sub_custom': {},   # tuỳ chỉnh chữ phụ đề đè lên preset: sub_font_name, sub_font_color, sub_font_size_factor…
}

_lock = threading.Lock()


def load_settings():
    data = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data.update(json.load(f))
    except (OSError, ValueError):
        pass
    return data


def save_settings(patch):
    with _lock:
        data = load_settings()
        data.update({k: v for k, v in patch.items() if k in DEFAULT_SETTINGS})
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data


def load_presets():
    try:
        with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_preset(name, mode, cfg):
    """Thêm / ghi đè mẫu theo tên (không phân biệt hoa thường)."""
    name = (name or '').strip()[:60]
    if not name:
        raise ValueError('Tên mẫu đang trống.')
    with _lock:
        items = [p for p in load_presets() if p.get('name', '').lower() != name.lower()]
        items.append({'name': name, 'mode': mode, 'cfg': cfg})
        items.sort(key=lambda p: p['name'].lower())
        with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return items


def delete_preset(name):
    with _lock:
        items = [p for p in load_presets() if p.get('name', '').lower() != (name or '').strip().lower()]
        with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return items


def _read_env():
    env = {}
    try:
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def load_env_into_process():
    # Chỉ nạp key còn hỗ trợ — .env cũ còn OPENAI/DEEPSEEK/GEMINI cũng bị bỏ qua.
    for k, v in _read_env().items():
        if v and k in API_KEYS:
            os.environ[k] = v


def get_api_keys_masked():
    out = []
    for name, label in API_KEYS.items():
        val = os.environ.get(name, '')
        masked = (val[:4] + '••••' + val[-4:]) if len(val) > 10 else ('••••' if val else '')
        out.append({'name': name, 'label': label, 'set': bool(val), 'masked': masked})
    return out


def save_api_keys(values):
    """values: {ENV_NAME: 'key' | ''}. Chuỗi rỗng = xoá key."""
    with _lock:
        env = _read_env()
        for k, v in values.items():
            if k not in API_KEYS:
                continue
            v = (v or '').strip()
            if k == 'CAPCUT_COOKIE' and v:
                from core.capcut_tts import normalize_cookie
                v = normalize_cookie(v)          # JSON / nhiều dòng → 1 dòng "a=b; c=d"
            if v:
                env[k] = v
                os.environ[k] = v
            else:
                env.pop(k, None)
                os.environ.pop(k, None)
        with open(ENV_FILE, 'w', encoding='utf-8') as f:
            for k, v in env.items():
                f.write(f'{k}={v}\n')


def get_key(name):
    return os.environ.get(name, '').strip()
