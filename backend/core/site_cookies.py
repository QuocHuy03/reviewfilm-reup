"""Cookie trang web do NGƯỜI DÙNG tự nạp (xuất từ trình duyệt của họ) — để bộ tải dùng phiên của chính họ.

Douyin bắt yt-dlp phải có "phiên trình duyệt mới" (cookie khách s_v_web_id / ttwid, không cần đăng nhập).
App không tự đọc được cookie Chrome/Edge trên Windows (trình duyệt khoá file + mã hoá theo app), nên cho người
dùng xuất file cookies.txt bằng extension rồi nạp vào đây.

Nhận 3 dạng:
  - Netscape cookies.txt (extension "Get cookies.txt LOCALLY", yt-dlp --cookies)
  - JSON mảng [{name, value, domain, path, expirationDate…}] (Cookie-Editor, EditThisCookie)
  - Chuỗi header "k=v; k2=v2" (copy từ DevTools)
Lưu thành Netscape cookies.txt ở data/cookies/<nền tảng>.txt — chỉ giữ cookie của đúng tên miền nền tảng.
"""
import json
import os
import time

from app.config import DATA_DIR

COOKIE_DIR = os.path.join(DATA_DIR, 'cookies')
SITES = {
    'douyin': {'label': 'Douyin', 'domain': '.douyin.com', 'match': ('douyin.com',),
               'keys': ('s_v_web_id', 'ttwid', 'sessionid', 'sessionid_ss', 'passport_csrf_token', 'msToken')},
}


def path(site):
    return os.path.join(COOKIE_DIR, f'{site}.txt')


def _in_site(domain, site):
    d = (domain or '').lstrip('.').lower()
    return any(d == m or d.endswith('.' + m) for m in SITES[site]['match'])


def parse(text, site):
    """Văn bản người dùng dán → [(domain, path, secure, expires, name, value)] của đúng nền tảng. ValueError nếu không đọc được."""
    text = (text or '').strip().lstrip('﻿')
    if not text:
        raise ValueError('Chưa có nội dung cookie.')
    out = []
    if text[:1] in '[{':
        try:
            data = json.loads(text)
        except ValueError:
            raise ValueError('JSON cookie không hợp lệ.')
        if isinstance(data, dict):
            data = data.get('cookies') or [data]
        for c in data if isinstance(data, list) else []:
            if not isinstance(c, dict) or not c.get('name'):
                continue
            dom = c.get('domain') or SITES[site]['domain']
            if not _in_site(dom, site):
                continue
            exp = c.get('expirationDate') or c.get('expires') or 0
            try:
                exp = int(float(exp)) if exp and float(exp) > 0 else 0
            except (TypeError, ValueError):
                exp = 0
            out.append((dom, c.get('path') or '/', bool(c.get('secure')), exp, str(c['name']), str(c.get('value', ''))))
    elif '\t' in text:                                  # Netscape cookies.txt
        for line in text.splitlines():
            line = line.strip()
            http_only = line.startswith('#HttpOnly_')
            if http_only:
                line = line[len('#HttpOnly_'):]
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 7 or not _in_site(parts[0], site):
                continue
            try:
                exp = int(float(parts[4] or 0))
            except ValueError:
                exp = 0
            out.append((parts[0], parts[2] or '/', parts[3].upper() == 'TRUE', exp, parts[5], parts[6]))
    else:                                               # "k=v; k2=v2"
        for kv in text.replace('\n', ';').split(';'):
            if '=' in kv:
                k, v = kv.split('=', 1)
                if k.strip():
                    out.append((SITES[site]['domain'], '/', True, 0, k.strip(), v.strip()))
    if not out:
        raise ValueError(f"Không thấy cookie nào của {SITES[site]['label']} — xuất cookie khi đang mở trang {SITES[site]['match'][0]}.")
    return out


def _netscape(rows):
    lines = ['# Netscape HTTP Cookie File', '# Nạp từ ReviewFilm Studio — cookie trình duyệt của người dùng', '']
    far = int(time.time()) + 180 * 86400               # cookie phiên (không hạn) → giữ 180 ngày để yt-dlp không bỏ qua
    for (dom, p, sec, exp, name, value) in rows:
        sub = 'TRUE' if dom.startswith('.') else 'FALSE'
        lines.append('\t'.join([dom, sub, p, 'TRUE' if sec else 'FALSE', str(exp or far), name, value]))
    return '\n'.join(lines) + '\n'


def save(site, text):
    """Lưu cookie → trạng thái mới. ValueError (thông báo dễ hiểu) nếu nội dung sai / thiếu cookie cần thiết."""
    if site not in SITES:
        raise ValueError('Nền tảng không hỗ trợ nạp cookie.')
    rows = parse(text, site)
    names = {r[4] for r in rows}
    if not names & set(SITES[site]['keys']):
        raise ValueError(f"Cookie thiếu phần phiên của {SITES[site]['label']} (vd {', '.join(SITES[site]['keys'][:2])}) — "
                         f"mở {SITES[site]['match'][0]}, xem 1 video rồi xuất lại.")
    os.makedirs(COOKIE_DIR, exist_ok=True)
    tmp = path(site) + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(_netscape(rows))
    os.replace(tmp, path(site))
    return status(site)


def _mark_path(site):
    return os.path.join(COOKIE_DIR, f'{site}.state.json')


def mark(site, ok):
    """Ghi kết quả lần tải gần nhất bằng cookie này (nền tảng có nhận không) — để báo người dùng xuất lại khi bị từ chối."""
    if site not in SITES or not os.path.isfile(path(site)):
        return
    try:
        with open(_mark_path(site), 'w', encoding='utf-8') as f:
            json.dump({'ok': bool(ok), 't': time.time()}, f)
    except OSError:
        pass


def delete(site):
    for p in (path(site), _mark_path(site)):
        try:
            os.remove(p)
        except OSError:
            pass
    return status(site)


def status(site):
    """{site, label, has, count, updated (epoch), expires_in_days (sớm nhất của cookie phiên chính; None = không rõ)}."""
    p = path(site)
    info = {'site': site, 'label': SITES[site]['label'], 'has': False, 'count': 0, 'updated': None, 'expires_in_days': None,
            'rejected': False, 'last_used': None}
    if not os.path.isfile(p):
        return info
    try:
        with open(p, encoding='utf-8') as f:
            rows = parse(f.read(), site)
    except (OSError, ValueError):
        return info
    now = time.time()
    keys = [r for r in rows if r[4] in SITES[site]['keys'] and r[3]]
    soon = min((r[3] for r in keys), default=0)
    info.update(has=True, count=len(rows), updated=os.path.getmtime(p),
                expires_in_days=round((soon - now) / 86400, 1) if soon else None)
    try:                                       # kết quả lần dùng gần nhất (chỉ tính nếu sau lần nạp cookie)
        with open(_mark_path(site), encoding='utf-8') as f:
            m = json.load(f)
        if m.get('t', 0) >= info['updated'] - 1:
            info['rejected'] = not m.get('ok', True)
            info['last_used'] = m.get('t')
    except (OSError, ValueError):
        pass
    return info


def ytdlp_args(site):
    """['--cookies', file] nếu người dùng đã nạp cookie cho nền tảng này (yt-dlp tự ghi lại cookie mới vào file)."""
    return ['--cookies', path(site)] if site in SITES and os.path.isfile(path(site)) else []


def all_status():
    return [status(s) for s in SITES]
