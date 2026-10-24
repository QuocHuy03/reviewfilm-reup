"""Từ điển dịch của người dùng — sửa 1 lần, lần sau dịch tự theo.

Mỗi mục: {"goc": chữ gốc (tiếng Trung…, tuỳ chọn), "sai": cách dịch sai cần thay (tuỳ chọn), "viet": cách dịch đúng}.
- "goc" → AI dịch được dặn BẮT BUỘC dịch đúng "viet" (ưu tiên hơn bảng tên AI tự lập).
- "sai" → dịch xong, mọi chỗ "sai" trong bản dịch tự thay thành "viet" (khớp đúng chữ, riêng chữ cái đầu được khác hoa / thường; giữ hoa đầu câu).
Lưu ở data/glossary.json (dùng chung mọi job, giữ qua các lần cập nhật app).
"""
import json
import os
import re
import threading

from app.config import DATA_DIR

_PATH = os.path.join(DATA_DIR, 'glossary.json')
_lock = threading.Lock()


def _clean(e):
    if not isinstance(e, dict):
        return None
    out = {k: re.sub(r'\s+', ' ', str(e.get(k) or '')).strip()[:120] for k in ('goc', 'sai', 'viet')}
    if not out['viet'] or not (out['goc'] or out['sai']) or out['sai'] == out['viet']:
        return None
    return out


def load():
    try:
        with open(_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [e for e in (_clean(x) for x in (data.get('entries') if isinstance(data, dict) else data) or []) if e]


def save(entries):
    """Ghi đè cả từ điển; mục trùng (cùng goc + sai) giữ mục sau cùng."""
    seen = {}
    for e in (_clean(x) for x in entries or []):
        if e:
            seen[(e['goc'].lower(), e['sai'].lower())] = e
    out = list(seen.values())
    with _lock:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        tmp = _PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'entries': out}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _PATH)
    return out


def add(entries):
    return save(load() + list(entries or []))


def prompt_block(entries=None):
    """Đoạn chèn vào lời nhắc dịch: tên / thuật ngữ người dùng đã chốt ('' nếu không có mục nào có chữ gốc)."""
    pairs = [e for e in (load() if entries is None else entries) if e['goc']]
    if not pairs:
        return ''
    return ('Từ điển của người dùng (ƯU TIÊN TUYỆT ĐỐI, hơn mọi bảng khác — luôn dịch đúng như sau): '
            + '; '.join(f"{e['goc']} = {e['viet']}" for e in pairs[:80]) + '\n')


def _patterns(entries):
    pats = []
    for e in sorted((e for e in entries if e['sai']), key=lambda e: -len(e['sai'])):   # cụm dài thay trước
        s = e['sai']
        # chỉ chữ cái ĐẦU được khác hoa / thường (đầu câu), còn lại khớp đúng y — "Mệnh Nguyệt" không ăn vào "vận mệnh nguyệt quang"
        head = f'[{re.escape(s[0].lower())}{re.escape(s[0].upper())}]' if s[0].lower() != s[0].upper() else re.escape(s[0])
        # không cắt giữa từ: trước / sau không phải chữ cái (kể cả chữ có dấu tiếng Việt)
        pats.append((re.compile(r'(?<!\w)' + head + re.escape(s[1:]) + r'(?!\w)'), e['viet']))
    return pats


def apply(text, entries=None, pats=None):
    """Thay mọi cách dịch "sai" trong text bằng "viet". Chữ sai viết hoa đầu → chữ đúng cũng hoa đầu."""
    if not text:
        return text
    for (rx, good) in (pats if pats is not None else _patterns(load() if entries is None else entries)):
        def _sub(m, good=good):
            s = m.group(0)
            return good[:1].upper() + good[1:] if s[:1].isupper() and not good[:1].isupper() else good
        text = rx.sub(_sub, text)
    return text


def apply_all(texts, entries=None):
    """apply cho cả danh sách → (danh sách mới, số chỗ đã thay)."""
    pats = _patterns(load() if entries is None else entries)
    if not pats:
        return (list(texts), 0)
    out = [apply(t, pats=pats) for t in texts]
    return (out, sum(1 for (a, b) in zip(texts, out) if a != b))
