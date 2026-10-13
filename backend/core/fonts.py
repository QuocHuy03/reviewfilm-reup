"""Danh mục font cho phụ đề: font hệ thống Windows + font người dùng thêm vào (<data>/fonts).

Đọc tên họ font thật (bảng 'name') và kiểm tra có đủ dấu tiếng Việt không (bảng 'cmap'),
lưu cache theo thời gian sửa file để lần sau không phải đọc lại ~150 file.
"""
import json
import logging
import os
import shutil
import threading

logging.getLogger('fontTools').setLevel(logging.ERROR)

FONT_EXTS = ('.ttf', '.otf', '.ttc')
VI_PROBE = 'ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹĐ'
_lock = threading.Lock()
_index = None


def _dirs():
    from app.config import DATA_DIR
    windir = os.environ.get('WINDIR', r'C:\Windows')
    return {
        'system': os.path.join(windir, 'Fonts'),
        'user': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts'),
        'custom': os.path.join(DATA_DIR, 'fonts'),
    }


def custom_dir():
    d = _dirs()['custom']
    os.makedirs(d, exist_ok=True)
    return d


def _read_font(path):
    """→ (family, subfamily, vi) hoặc None nếu không đọc được."""
    from fontTools.ttLib import TTFont
    try:
        f = TTFont(path, lazy=True, fontNumber=0)
    except Exception:
        return None
    try:
        names = f['name']

        def pick(*ids):
            for nid in ids:
                rec = names.getName(nid, 3, 1, 0x409) or names.getName(nid, 3, 1) or names.getName(nid, 1, 0)
                if rec:
                    return str(rec).strip()
            return ''
        family = pick(16, 1)
        sub = pick(17, 2) or 'Regular'
        cmap = f.getBestCmap() or {}
        vi = all(ord(ch) in cmap for ch in VI_PROBE)
        return (family, sub, vi) if family else None
    except Exception:
        return None
    finally:
        f.close()


def _cache_file():
    from app.config import DATA_DIR
    return os.path.join(DATA_DIR, 'fonts_cache.json')


def _scan():
    try:
        with open(_cache_file(), encoding='utf-8') as fh:
            cache = json.load(fh)
    except (OSError, ValueError):
        cache = {}
    fresh, out = {}, []
    for (src, d) in _dirs().items():
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not name.lower().endswith(FONT_EXTS):
                continue
            path = os.path.join(d, name)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            hit = cache.get(path)
            info = hit['info'] if hit and hit.get('mtime') == mtime else _read_font(path)
            fresh[path] = {'mtime': mtime, 'info': info}
            if info:
                out.append({'family': info[0], 'style': info[1], 'vi': info[2], 'path': path, 'source': src})
    try:
        with open(_cache_file(), 'w', encoding='utf-8') as fh:
            json.dump(fresh, fh, ensure_ascii=False)
    except OSError:
        pass
    return out


def _style_rank(style):
    s = style.lower()
    return 0 if s in ('regular', 'normal', 'book', 'roman') else 1 if s == 'medium' else 2 if 'bold' in s and 'italic' not in s else 3


def families(refresh=False):
    """→ [{family, vi, path (file đại diện, ưu tiên Regular), styles, source}] sắp theo tên."""
    global _index
    with _lock:
        if _index is None or refresh:
            fams = {}
            for f in _scan():
                cur = fams.setdefault(f['family'], {'family': f['family'], 'vi': False, 'styles': [], 'source': f['source'], 'path': f['path'], '_rank': 9})
                cur['vi'] = cur['vi'] or f['vi']
                cur['styles'].append(f['style'])
                r = _style_rank(f['style'])
                if r < cur['_rank']:
                    cur.update(path=f['path'], _rank=r)
                if f['source'] == 'custom':
                    cur['source'] = 'custom'
            _index = sorted(({k: v for (k, v) in x.items() if k != '_rank'} for x in fams.values()), key=lambda x: x['family'].lower())
        return _index


def find_font_file(family):
    """Tên họ font → đường dẫn file (Regular nếu có). '' nếu không có trên máy."""
    key = (family or '').strip().lower()
    for f in families():
        if f['family'].lower() == key:
            return f['path']
    return ''


def import_font(src_path):
    """Chép file font người dùng chọn vào <data>/fonts. → họ font vừa thêm."""
    if not os.path.isfile(src_path) or not src_path.lower().endswith(FONT_EXTS):
        raise ValueError('Chỉ nhận file font .ttf / .otf / .ttc')
    info = _read_font(src_path)
    if not info:
        raise ValueError('File font hỏng hoặc không đọc được.')
    dest = os.path.join(custom_dir(), os.path.basename(src_path))
    shutil.copy2(src_path, dest)
    families(refresh=True)
    return {'family': info[0], 'vi': info[2], 'path': dest}


def custom_font_files():
    d = _dirs()['custom']
    return [os.path.join(d, n) for n in os.listdir(d) if n.lower().endswith(FONT_EXTS)] if os.path.isdir(d) else []
