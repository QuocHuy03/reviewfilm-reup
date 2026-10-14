"""Tải video từ link — không cần đăng nhập.

  Douyin / TikTok → API mở của dự án Douyin_TikTok_Download_API (github.com/Evil0ctal, bản demo công khai
                    demo.douyin.wtf) → link video gốc trên CDN (1080p, không logo) → tải thẳng bằng HTTP.
                    Lỗi thì lùi về yt-dlp.
  Nền tảng khác   → yt-dlp (Bilibili, Weibo, AcFun, YouTube, Facebook, Instagram, X… hơn 1.800 trang).
  Link CDN / .mp4 → tải thẳng bằng HTTP.
"""
import json
import os
import re
import subprocess
import sys
import urllib.parse

from core.utils import _HIDE, register_process, unregister_process

# nền tảng: (tên hiển thị, các tên miền)
PLATFORMS = {
    'douyin': ('Douyin', ('douyin.com', 'iesdouyin.com')),
    'tiktok': ('TikTok', ('tiktok.com',)),
    'bilibili': ('Bilibili', ('bilibili.com', 'b23.tv')),
    'kuaishou': ('Kuaishou', ('kuaishou.com', 'gifshow.com')),
    'xiaohongshu': ('Tiểu Hồng Thư', ('xiaohongshu.com', 'xhslink.com')),
    'weibo': ('Weibo', ('weibo.com', 'weibo.cn')),
    'ixigua': ('Xigua', ('ixigua.com',)),
    'youku': ('Youku', ('youku.com',)),
    'iqiyi': ('iQiyi', ('iqiyi.com', 'iq.com')),
    'acfun': ('AcFun', ('acfun.cn',)),
    'youtube': ('YouTube', ('youtube.com', 'youtu.be')),
    'facebook': ('Facebook', ('facebook.com', 'fb.watch')),
    'instagram': ('Instagram', ('instagram.com',)),
    'x': ('X / Twitter', ('twitter.com', 'x.com')),
    'vimeo': ('Vimeo', ('vimeo.com',)),
    'dailymotion': ('Dailymotion', ('dailymotion.com', 'dai.ly')),
}
QUALITY = {
    'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
    '1080': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
    '720': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best',
    'audio': 'bestaudio[ext=m4a]/bestaudio',
}
_URL_RE = re.compile(r'https?://[^\s"\'<>，。]+', re.I)


# ── Douyin / TikTok: API mở Douyin_TikTok_Download_API (bản demo công khai, tài khoản demo do chính trang cấp) ──
DTK_BASE = 'https://demo.douyin.wtf'
DTK_PLATFORMS = ('douyin',)       # TikTok: link CDN gắn phiên của máy chủ demo (403) → dùng yt-dlp
_dtk = {'session': None}


def _dtk_session(fresh=False):
    import requests
    if _dtk['session'] is not None and not fresh:
        return _dtk['session']
    sess = requests.Session()
    sess.headers.update({'User-Agent': 'ReviewFilmStudio/2 (+https://github.com/Evil0ctal/Douyin_TikTok_Download_API)', 'Accept': 'application/json'})
    cred = sess.get(f'{DTK_BASE}/api/v1/auth/demo', timeout=20).json().get('data') or {}
    if not cred.get('enabled'):
        raise RuntimeError('nguồn demo đang tắt')
    r = sess.post(f'{DTK_BASE}/api/v1/auth/login', json={'username': cred['username'], 'password': cred['password']}, timeout=20)
    if not (r.ok and r.json().get('success')):
        raise RuntimeError(f'đăng nhập demo lỗi (HTTP {r.status_code})')
    _dtk['session'] = sess
    return sess


def dtk_resolve(url):
    """Douyin/TikTok → {title, author, duration, cover, video (link CDN có tiếng), width, height, size}. RuntimeError nếu lỗi."""
    import requests
    for attempt in range(2):
        try:
            r = _dtk_session(fresh=attempt > 0).post(f'{DTK_BASE}/api/v1/parse?wait=25', json={'url': url}, timeout=60)
        except (requests.RequestException, ValueError) as e:
            raise RuntimeError(f'không kết nối được ({str(e)[:80]})')
        if r.status_code in (401, 403) and attempt == 0:
            continue                   # phiên demo hết hạn → đăng nhập lại 1 lần
        try:
            d = r.json()
        except ValueError:
            raise RuntimeError(f'HTTP {r.status_code}')
        if not d.get('success'):
            err = d.get('error') or {}
            raise RuntimeError(str(err.get('message') if isinstance(err, dict) else err)[:150] or f'HTTP {r.status_code}')
        data = d.get('data') or {}
        if data.get('kind') != 'video':
            raise RuntimeError('link này là bài ảnh, không phải video')
        media = data.get('media') or {}
        v = media.get('video') or {}
        if not v.get('url'):
            raise RuntimeError('không có link video')
        cover = (media.get('covers') or [{}])[0].get('url', '')
        return {'title': data.get('title') or data.get('description') or '', 'author': (data.get('author') or {}).get('nickname', ''),
                'duration': (data.get('duration_ms') or 0) / 1000 or None, 'cover': cover, 'video': v['url'],
                'width': v.get('width'), 'height': v.get('height'), 'size': v.get('size_bytes'),
                'platform_label': PLATFORMS.get(data.get('platform'), ('Douyin',))[0]}
    raise RuntimeError('phiên demo bị từ chối')


def extract_url(text):
    """Lấy link từ đoạn chia sẻ ("7.43 复制打开抖音… https://v.douyin.com/xxx/ …") hoặc trả nguyên chuỗi."""
    m = _URL_RE.search(text or '')
    return m.group(0).rstrip('.,;)') if m else (text or '').strip()


_DIRECT_HOSTS = ('zjcdn.com', 'douyinvod.com', 'bytecdn.cn', 'snssdk.com', 'tiktokcdn.com', 'tiktokcdn-us.com',
                 'byteicdn.com', 'ibytedtos.com', 'bilivideo.com', 'akamaized.net')
_MEDIA_EXT = ('.mp4', '.m4v', '.mov', '.webm', '.mkv', '.flv')


def is_direct_media(url):
    """Link thẳng tới file video (CDN Douyin/TikTok… hoặc .mp4) — tải bằng HTTP, không cần trình trích xuất."""
    u = urllib.parse.urlparse(url)
    host, path = (u.hostname or '').lower(), u.path.lower()
    return (any(host == d or host.endswith('.' + d) for d in _DIRECT_HOSTS) or 'mime_type=video_mp4' in u.query
            or path.endswith(_MEDIA_EXT))


def detect_platform(url):
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    if is_direct_media(url):
        return 'direct', 'Link video trực tiếp'
    for (key, (label, domains)) in PLATFORMS.items():
        if any(host == d or host.endswith('.' + d) for d in domains):
            return key, label
    return 'other', host or 'Khác'


def normalize(url):
    """Douyin: link trang người dùng (?modal_id=) / link rút gọn → link video chuẩn."""
    url = extract_url(url)
    if 'douyin.com' in url:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        vid = (q.get('modal_id') or q.get('vid') or [None])[0]
        if vid:
            return f'https://www.douyin.com/video/{vid}'
    return url


def _ytdlp(args, timeout=None, proc_cb=None):
    cmd = [sys.executable, '-m', 'yt_dlp', '--no-warnings', '--encoding', 'utf-8'] + args
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                         creationflags=_HIDE)
    register_process(p)
    try:
        if proc_cb:
            return proc_cb(p)
        out, err = p.communicate(timeout=timeout)
        return p.returncode, out, err
    finally:
        unregister_process(p)


def _friendly(err, url):
    e = (err or '').lower()
    (key, label) = detect_platform(url)
    if 'cookie' in e or 'login' in e or 'sign in' in e or 'logged' in e:
        return f'{label} chặn tải tự động với video này — thử lại sau ít phút, hoặc dán link video trực tiếp (.mp4).'
    if 'ip address is blocked' in e or 'geo' in e or 'not available in your country' in e:
        return f'{label} chặn truy cập từ khu vực/IP này — thử lại sau hoặc dùng VPN.'
    if '412' in e or '403' in e or 'forbidden' in e:
        return f'{label} từ chối yêu cầu (chống tải tự động) — thử lại sau ít phút.'
    if 'unsupported url' in e:
        return 'Link này chưa được hỗ trợ (kiểm tra lại link, hoặc mở link trên trình duyệt xem còn xem được không).'
    if 'private' in e or 'deleted' in e or 'removed' in e or 'unavailable' in e:
        return 'Video riêng tư / đã bị xoá / không còn xem được.'
    last = [l for l in (err or '').strip().split('\n') if l.strip()]
    return (last[-1] if last else 'Lỗi không rõ')[:240]


def _probe_direct(url):
    import requests
    from core.utils import FFPROBE_EXE
    info = {'url': url, 'platform': 'direct', 'platform_label': 'Link video trực tiếp', 'title': 'Video (link trực tiếp)'}
    try:
        r = requests.get(url, headers={'User-Agent': UA, 'Range': 'bytes=0-0'}, timeout=15, stream=True)
        if r.status_code not in (200, 206):
            return {**info, 'error': f'Link không tải được (HTTP {r.status_code}) — link trực tiếp thường hết hạn sau 1–2 giờ, hãy lấy link mới.'}
        total = r.headers.get('Content-Range', '').rpartition('/')[2] or r.headers.get('Content-Length', '')
        info['size'] = int(total) if total.isdigit() else None
        r.close()
    except requests.RequestException as e:
        return {**info, 'error': f'Không kết nối được: {str(e)[:120]}'}
    try:
        out = subprocess.run([FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration:stream=width,height', '-of', 'json', url],
                             capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30, creationflags=_HIDE).stdout
        d = json.loads(out or '{}')
        v = next((x for x in d.get('streams', []) if x.get('height')), {})
        info.update(duration=float(d.get('format', {}).get('duration') or 0) or None, width=v.get('width'), height=v.get('height'))
    except Exception:
        pass
    return info


def probe(url):
    """Thông tin video (không tải): tiêu đề, thời lượng, ảnh bìa, tác giả, nền tảng. Lỗi → {'error': ...}."""
    url = normalize(url)
    if is_direct_media(url):
        return _probe_direct(url)
    (key, label) = detect_platform(url)
    if key in DTK_PLATFORMS:
        try:
            v = dtk_resolve(url)
            return {'url': url, 'platform': key, 'platform_label': label, 'title': v['title'], 'duration': v['duration'],
                    'thumbnail': v['cover'], 'uploader': v['author'], 'width': v['width'], 'height': v['height'], 'source': 'dtk'}
        except RuntimeError:
            pass                       # lùi về yt-dlp
    code, out, err = _ytdlp(['-J', '--no-playlist', '--skip-download', url], timeout=60)
    if code != 0:
        return {'url': url, 'platform': key, 'platform_label': label, 'error': _friendly(err, url)}
    try:
        d = json.loads(out)
    except ValueError:
        return {'url': url, 'platform': key, 'platform_label': label, 'error': 'Không đọc được thông tin video.'}
    return {'url': url, 'platform': key, 'platform_label': label, 'title': d.get('title') or d.get('description', '')[:80],
            'duration': d.get('duration'), 'thumbnail': d.get('thumbnail'), 'uploader': d.get('uploader') or d.get('channel'),
            'width': d.get('width'), 'height': d.get('height')}


UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'


def _safe_name(title):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', ' ', title or '').strip()
    name = re.sub(r'\s+', ' ', re.sub(r'#\S+', '', name)).strip()[:80].rstrip('. ')
    return name or 'video'


def download_direct(url, output_dir, title='', log_fn=print, progress_fn=None, should_stop=None):
    """Tải link video trực tiếp (CDN) bằng HTTP — có tiến độ, huỷ giữa chừng, file dở được xoá."""
    import time
    import requests
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, _safe_name(title))
    path, k = base + '.mp4', 2
    while os.path.exists(path):
        path, k = f'{base} ({k}).mp4', k + 1
    part = path + '.part'
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    headers = {'User-Agent': UA}
    if 'douyin' in host or 'zjcdn' in host or 'bytecdn' in host:
        headers['Referer'] = 'https://www.douyin.com/'
    log_fn(f'   Link trực tiếp: {host}')
    try:
        with requests.get(url, headers=headers, stream=True, timeout=30) as r:
            if r.status_code != 200:
                raise RuntimeError(f'Link không tải được (HTTP {r.status_code}) — link trực tiếp thường hết hạn sau 1–2 giờ, hãy lấy link mới.')
            total = int(r.headers.get('Content-Length') or 0)
            got, t0, last = 0, time.time(), 0.0
            with open(part, 'wb') as f:
                for chunk in r.iter_content(1 << 20):
                    if should_stop and should_stop():
                        raise RuntimeError('Đã huỷ.')
                    f.write(chunk)
                    got += len(chunk)
                    now = time.time()
                    if progress_fn and (now - last > 0.5 or got == total):
                        last = now
                        speed = got / max(0.001, now - t0)
                        eta = (total - got) / speed if total and speed else 0
                        progress_fn(got / total * 100 if total else 0, f'{total / 1048576:.1f}MiB' if total else '',
                                    f'{speed / 1048576:.2f}MiB/s', f'{int(eta // 60):02d}:{int(eta % 60):02d}' if total else '')
        if total and got < total:
            raise RuntimeError(f'Tải chưa đủ ({got / 1048576:.0f}/{total / 1048576:.0f} MB) — mạng bị ngắt, thử lại.')
        os.replace(part, path)
        return path
    except requests.RequestException as e:
        raise RuntimeError(f'Lỗi mạng khi tải: {str(e)[:150]}')
    finally:
        if os.path.exists(part):
            os.remove(part)


def download(url, output_dir, log_fn=print, quality='best', progress_fn=None, should_stop=None, title=''):
    """Tải 1 video → đường dẫn file. Ném RuntimeError (thông báo dễ hiểu) nếu lỗi."""
    url = normalize(url)
    if is_direct_media(url):
        return download_direct(url, output_dir, title, log_fn, progress_fn, should_stop)
    if detect_platform(url)[0] in DTK_PLATFORMS:
        try:
            v = dtk_resolve(url)
            log_fn(f"   {v['platform_label']}: {v['height']}p, không logo — {v['title'][:50]}")
            return download_direct(v['video'], output_dir, title or v['title'], log_fn, progress_fn, should_stop)
        except RuntimeError as e:
            log_fn(f'   [WARN] Nguồn API mở lỗi ({e}) — thử yt-dlp...')
    (key, label) = detect_platform(url)
    os.makedirs(output_dir, exist_ok=True)
    template = os.path.join(output_dir, '%(title).80B [%(id)s].%(ext)s')
    fmt = QUALITY.get(quality, QUALITY['best'])
    base = ['--no-playlist', '-f', fmt, '-o', template, '--newline', '--progress', '--print', 'after_move:filepath', '--windows-filenames',
            '--progress-template', 'download:RFPROG %(progress._percent_str)s|%(progress._total_bytes_str)s%(progress._total_bytes_estimate_str)s|%(progress._speed_str)s|%(progress._eta_str)s']
    if quality != 'audio':
        base += ['--merge-output-format', 'mp4']
    # trang đòi phiên trình duyệt → thử thêm cookie của trình duyệt có sẵn trên máy (không cần đăng nhập trong app)
    attempts = [[]] + [['--cookies-from-browser', b] for b in ('chrome', 'edge', 'firefox')]
    log_fn(f'   {label}: {url}')
    last_err = ''
    for (k, extra) in enumerate(attempts):
        if should_stop and should_stop():
            raise RuntimeError('Đã huỷ.')
        if k:
            log_fn(f'   Thử dùng cookie trình duyệt {extra[-1]}...')
        lines_out, err_lines = [], []

        def run(p):
            for line in p.stdout:
                line = line.strip()
                if should_stop and should_stop():
                    p.kill()
                    break
                if line.startswith('RFPROG'):
                    if progress_fn:
                        parts = [x.strip() for x in line[6:].split('|')]
                        try:
                            pct = float(parts[0].rstrip('%'))
                        except ValueError:
                            continue
                        clean = [re.sub(r'N/?A|Unknown( B/s)?', '', x).strip() for x in parts[1:4]] + ['', '', '']
                        progress_fn(pct, clean[0], clean[1], clean[2])
                elif line and not line.startswith('['):
                    lines_out.append(line)
            err_lines.append(p.stderr.read())
            p.wait()
            return p.returncode

        code = _ytdlp(base + extra + [url], proc_cb=run)
        if should_stop and should_stop():
            raise RuntimeError('Đã huỷ.')
        if code == 0:
            for line in reversed(lines_out):
                if os.path.isfile(line):
                    return line
        last_err = ''.join(err_lines)
        if k == 0 and not any(w in last_err.lower() for w in ('cookie', 'login', 'sign in', '403', 'blocked')):
            break                      # lỗi không liên quan đăng nhập → thử cookie trình duyệt cũng vô ích
    raise RuntimeError(_friendly(last_err, url))


def download_video(url, output_dir, log_fn=print):
    """Giữ tương thích cho pipeline Review/Reup (nhập link ở trang Tạo video)."""
    try:
        path = download(url, output_dir, log_fn)
        log_fn(f'   File: {os.path.basename(path)}')
        return path
    except RuntimeError as e:
        log_fn(f'   [LỖI] {e}')
        return None


def tool_version():
    code, out, _ = _ytdlp(['--version'], timeout=30)
    return out.strip() if code == 0 else ''


def update_tool():
    """Cập nhật yt-dlp lên bản mới nhất (các nền tảng đổi cách chống tải liên tục)."""
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-U', 'yt-dlp'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=300, creationflags=_HIDE)
    return r.returncode == 0, (r.stderr or r.stdout)[-300:], tool_version()


def auto_update(max_age_days=7):
    """Tự cập nhật yt-dlp ngầm khi mở app, tối đa 1 lần / tuần — các nền tảng đổi cách chống tải liên tục."""
    import threading
    import time
    from app.config import DATA_DIR
    mark = os.path.join(DATA_DIR, 'ytdlp_updated.txt')
    try:
        if os.path.isfile(mark) and time.time() - os.path.getmtime(mark) < max_age_days * 86400:
            return
    except OSError:
        return

    def run():
        try:
            ok, _, version = update_tool()
            if ok:
                with open(mark, 'w', encoding='utf-8') as f:
                    f.write(version)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True, name='ytdlp-update').start()
