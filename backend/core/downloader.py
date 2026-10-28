"""Tải video từ link — không cần đăng nhập.

  Douyin / TikTok → API mở của dự án Douyin_TikTok_Download_API (github.com/Evil0ctal, bản demo công khai
                    demo.douyin.wtf) → link video gốc trên CDN (1080p, không logo) → tải thẳng bằng HTTP.
                    Lỗi thì lùi về yt-dlp.
  Nền tảng khác   → yt-dlp (Bilibili, Weibo, AcFun, YouTube, Facebook, Instagram, X… hơn 1.800 trang).
  Link CDN / .mp4 → tải thẳng bằng HTTP.
  Phim ngắn       → core/drama_downloader (DramaBox, GoodShort, ShortMax, NetShort, FreeReels, KissKH, Hồng Quả…):
                    1 link = cả bộ, chọn tập bằng đuôi "#ep=1-10,15"; mỗi tập tải thẳng (mp4) hoặc qua ffmpeg (m3u8).
"""
import json
import os
import re
import subprocess
import sys
import urllib.parse

from core import site_cookies
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


def _dtk_video(data):
    """Kết quả phân tích (data.kind/media…) → dict gọn cho app. RuntimeError nếu không phải video."""
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


def _find_result(x):
    """Tìm khối kết quả (có 'kind') trong phản hồi task — tên khoá có thể là result / data / output."""
    if isinstance(x, dict):
        if 'kind' in x and ('media' in x or 'platform' in x):
            return x
        for k in ('result', 'data', 'output', 'content'):
            r = _find_result(x.get(k))
            if r:
                return r
    return None


class DtkBusy(RuntimeError):
    """Nguồn Douyin tạm nghỉ — `minutes`: nên thử lại sau bao lâu (0 = không rõ)."""
    def __init__(self, msg, minutes=0):
        super().__init__(msg)
        self.minutes = minutes


_DTK_LOCK = __import__('threading').Lock()      # nhiều link Douyin → hỏi nguồn lần lượt, không dồn dập


def dtk_resolve(url, log_fn=None, should_stop=None, budget=240):
    """Douyin → {title, author, duration, cover, video (link CDN có tiếng), width, height, size}. RuntimeError nếu lỗi.

    Gửi việc rồi hỏi kết quả (không giữ 1 kết nối chờ lâu → Cloudflare cắt thành 502). Nguồn báo lỗi tạm thời
    (bị Douyin cho nghỉ, đang quá tải…) thì tự chờ đúng thời gian nguồn yêu cầu rồi thử lại, trong `budget` giây."""
    import time
    import requests
    from core import cancel
    log = log_fn or (lambda *_: None)
    stopped = lambda: (should_stop and should_stop()) or cancel.requested()
    deadline = time.time() + budget
    last, relogin, waited_note = 'không rõ', False, False
    retry_at = [0.0]

    def pause(sec, why):
        nonlocal waited_note
        retry_at[0] = time.time() + sec
        if time.time() + sec > deadline:             # nguồn bắt chờ lâu hơn thời gian còn lại → thôi, báo giờ thử lại
            return False
        sec = max(3, sec)
        log(f'   Nguồn Douyin {why} — tự thử lại sau {int(sec)} giây...' if not waited_note else f'   Vẫn bận ({why}) — thử lại sau {int(sec)} giây...')
        waited_note = True
        if cancel.sleep(sec) or stopped():
            raise RuntimeError('Đã huỷ.')
        return True

    with _DTK_LOCK:
        while time.time() < deadline:
            if stopped():
                raise RuntimeError('Đã huỷ.')
            try:
                sess = _dtk_session(fresh=relogin)
                relogin = False
                r = sess.post(f'{DTK_BASE}/api/v1/parse', json={'url': url}, timeout=30)
            except (requests.RequestException, ValueError, KeyError) as e:
                last = f'không kết nối được ({str(e)[:80]})'
                if not pause(15, 'không kết nối được'):
                    break
                continue
            except RuntimeError as e:                # đăng nhập demo lỗi / nguồn tắt
                last = str(e)
                if not pause(30, str(e)):
                    break
                continue
            if r.status_code in (401, 403) and not relogin:
                relogin = True
                continue
            if r.status_code >= 500:
                last = f'HTTP {r.status_code}'
                if not pause(15, 'đang quá tải'):
                    break
                continue
            try:
                d = r.json()
            except ValueError:
                last = f'HTTP {r.status_code}'
                if not pause(15, 'trả dữ liệu lỗi'):
                    break
                continue
            res = _find_result(d)
            if res:                                  # trả kết quả ngay (không qua hàng đợi)
                return _dtk_video(res)
            tid = ((d.get('data') or {}) if isinstance(d.get('data'), dict) else {}).get('task_id')
            if not d.get('success') or not tid:
                err = d.get('error')
                msg = (err.get('message') if isinstance(err, dict) else err) or d.get('title') or f'HTTP {r.status_code}'
                raise RuntimeError(str(msg)[:160])
            # hỏi kết quả tới khi xong (thường 2–10 giây)
            x, t_end = {}, time.time() + 90
            while time.time() < t_end:
                if cancel.sleep(1.5) or stopped():
                    raise RuntimeError('Đã huỷ.')
                try:
                    j = sess.get(f'{DTK_BASE}/api/v1/tasks/{tid}', timeout=20).json()
                except (requests.RequestException, ValueError):
                    continue
                x = j.get('data') or {}
                if x.get('state') not in ('queued', 'running', 'pending', 'started'):
                    break
            res = _find_result(x)
            if res:
                return _dtk_video(res)
            err = x.get('error') or {}
            code = err.get('code') or x.get('state') or 'không rõ'
            last = f"{code}: {err.get('message') or ''}".strip(': ')
            if x.get('state') in ('queued', 'running', 'pending', 'started') or err.get('retryable'):
                why = {'UPSTREAM_RISK_CONTROL': 'đang bị Douyin cho nghỉ', 'ENDPOINT_CIRCUIT_OPEN': 'đang tạm ngắt',
                       'RATE_LIMITED': 'đang giới hạn lượt'}.get(code, 'đang bận')
                if not pause(err.get('retry_after') or 20, why):
                    break
                continue
            raise RuntimeError(last[:160])
    mins = max(1, round((retry_at[0] - time.time()) / 60)) if retry_at[0] > time.time() else 0
    raise DtkBusy(f'nguồn Douyin đang tạm nghỉ ({last[:80]})', mins)


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
    dp = drama_platform(url)
    if dp:
        return 'drama', dp.display_name
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


_JS = {}


def _js_runtime():
    """Trình chạy JavaScript cho yt-dlp (YouTube bắt buộc để giải mã chữ ký): deno cài kèm qua pip → deno/node trên máy."""
    if 'v' in _JS:
        return _JS['v']
    import shutil
    v = []
    try:
        import deno
        exe = deno.find_deno_bin()
        if exe and os.path.isfile(exe):
            v = ['--js-runtimes', f'deno:{exe}']
    except Exception:
        pass
    if not v:
        for name in ('deno', 'node'):
            exe = shutil.which(name)
            if exe:
                v = ['--js-runtimes', f'{name}:{exe}']
                break
    _JS['v'] = v
    return v


def _base_args():
    """ffmpeg kèm app (ghép hình + tiếng — máy người dùng thường không có ffmpeg trong PATH) + trình chạy JS."""
    from core.utils import FFMPEG_EXE
    a = ['--ffmpeg-location', FFMPEG_EXE] if os.path.isfile(FFMPEG_EXE) else []
    return a + _js_runtime()


def _ytdlp(args, timeout=None, proc_cb=None):
    cmd = [sys.executable, '-m', 'yt_dlp', '--no-warnings', '--encoding', 'utf-8'] + _base_args() + args
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
    if key == 'douyin' and 'fresh cookies' in e:
        return ('Nguồn tải Douyin đang lỗi, cách dự phòng thì Douyin bắt đăng nhập trình duyệt. '
                'Bấm "Tải lại" sau vài phút, hoặc dán link video trực tiếp (.mp4).')
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
    if 'no video formats found' in e:
        # trang tải được nhưng không có luồng video: thường do video chỉ phát cho khu vực khác / bị ẩn
        return (f'{label} không trả về video cho link này — thường do video chỉ cho xem ở khu vực khác (vd kênh nước ngoài), '
                'bị ẩn hoặc giới hạn. Mở link trên trình duyệt kiểm tra; nếu bị chặn khu vực thì cần VPN.')
    if 'ffmpeg' in e and ('not installed' in e or 'not found' in e):
        return 'Thiếu ffmpeg để ghép hình + tiếng — cài lại app hoặc chọn chất lượng thấp hơn.'
    last = [l for l in (err or '').strip().split('\n') if l.strip()]
    errs = [l for l in last if l.startswith('ERROR')]
    return ((errs or last)[-1] if last else 'Bộ tải dừng mà không báo lỗi — bấm "Cập nhật bộ tải" trong Cài đặt rồi thử lại.')[:240]


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
    if key == 'drama':
        return _probe_drama(url, label)
    cookie = site_cookies.ytdlp_args(key)
    if cookie:
        code, out, err = _ytdlp(['-J', '--no-playlist', '--skip-download'] + cookie + [url], timeout=60)
        if code == 0:
            try:
                d = json.loads(out)
                return {'url': url, 'platform': key, 'platform_label': label, 'title': d.get('title') or d.get('description', '')[:80],
                        'duration': d.get('duration'), 'thumbnail': d.get('thumbnail'), 'uploader': d.get('uploader') or d.get('channel'),
                        'width': d.get('width'), 'height': d.get('height')}
            except ValueError:
                pass
    if key in DTK_PLATFORMS:
        try:
            v = dtk_resolve(url, budget=25)
            return {'url': url, 'platform': key, 'platform_label': label, 'title': v['title'], 'duration': v['duration'],
                    'thumbnail': v['cover'], 'uploader': v['author'], 'width': v['width'], 'height': v['height'], 'source': 'dtk'}
        except RuntimeError:
            pass                       # lùi về yt-dlp
    if key == 'douyin' and not cookie:        # không cookie thì Douyin chắc chắn đòi phiên → khỏi chạy thử, báo luôn
        code, out, err = 1, '', 'Fresh cookies (not necessarily logged in) are needed'
    else:
        code, out, err = _ytdlp(['-J', '--no-playlist', '--skip-download', url], timeout=60)
    if code != 0:
        msg = _friendly(err, url)
        if key == 'douyin' and 'fresh cookies' in (err or '').lower():
            # lúc tải, app chờ nguồn rảnh tới vài phút (xem trước chỉ chờ ngắn) → vẫn nên bấm Tải
            msg = ('Chưa xem trước được — nguồn Douyin đang bận. Vẫn bấm "Tải video" được: app tự chờ nguồn rảnh rồi tải'
                   + (' (cookie Douyin đã nạp không còn dùng được).' if cookie else '.'))
        soft = key == 'douyin' and 'fresh cookies' in (err or '').lower()
        return {'url': url, 'platform': key, 'platform_label': label, 'error': msg, **({'soft': True} if soft else {})}
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


def platform_folder(output_dir, url):
    """Video lẻ: '<thư mục tải>/<Nền tảng>/' (YouTube, Douyin…) — nhiều nguồn không lẫn vào nhau."""
    if is_direct_media(url):
        return os.path.join(output_dir, 'Video khác')
    label = detect_platform(url)[1] or 'Video khác'
    return os.path.join(output_dir, _safe_name(label.split(' (')[0]))


def _poster_candidates(url):
    """Link ảnh bìa thường là bản thu nhỏ → thử bản gốc trước: bỏ hậu tố resize của CDN (…jpg@w=360&h=640, x-oss-process,
    imageView2, ~tplv-…), YouTube hqdefault → maxresdefault."""
    out = []
    u = re.sub(r'(\.(?:jpe?g|png|webp))@[^/?#]*$', r'\1', url, flags=re.I)
    u = re.sub(r'[?&](?:x-oss-process|imageView2|image_process|imageMogr2)=[^&]*', '', u)
    if 'ytimg.com' in u:
        out.append(re.sub(r'/(?:hq|mq|sd)?default(\.jpg|\.webp)', r'/maxresdefault\1', u))
    out += [u, url]
    return list(dict.fromkeys(out))


def save_poster(image_url, path, referer=''):
    """Tải ảnh bìa → JPEG chất lượng cao (webp / png đổi sang jpg để mọi trình xem / Plex / Kodi đọc được). Lỗi → None."""
    import io
    import requests
    if not image_url or not str(image_url).startswith('http'):
        return None
    try:
        headers = {'User-Agent': UA, **({'Referer': referer} if referer else {})}
        data = None
        for u in _poster_candidates(image_url):      # bản gốc nét nhất trước, lỗi thì lùi về link thường
            try:
                r = requests.get(u, headers=headers, timeout=20)
                if r.status_code == 200 and len(r.content) >= 500 and r.headers.get('Content-Type', 'image').startswith('image'):
                    data = r.content
                    break
            except requests.RequestException:
                continue
        if not data:
            return None
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        if data[:3] == b'\xff\xd8\xff':                   # đã là JPEG → giữ nguyên, không nén lại
            with open(path, 'wb') as f:
                f.write(data)
            return path
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if im.mode not in ('RGB', 'L'):
            bg = Image.new('RGB', im.size, (0, 0, 0))
            im = im.convert('RGBA')
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im.convert('RGB').save(path, 'JPEG', quality=95)
        return path
    except Exception:
        return None


def unique_path(path):
    (stem, ext) = os.path.splitext(path)
    k = 2
    while os.path.exists(path):
        path = f'{stem} ({k}){ext}'
        k += 1
    return path


def write_series_info(series, folder, link=''):
    """Phim nhiều tập: poster.jpg + 'Thông tin phim.txt' trong thư mục phim (1 lần, có rồi thì thôi)."""
    import datetime
    os.makedirs(folder, exist_ok=True)
    poster = os.path.join(folder, 'poster.jpg')
    if series.cover and not os.path.isfile(poster):
        save_poster(series.cover, poster)
    info = os.path.join(folder, 'Thông tin phim.txt')
    if not os.path.isfile(info):
        lines = [f'Tên phim: {series.name}', f'Nền tảng: {series.platform}',
                 f'Số tập: {series.episode_count or len(series.episodes)}' + (f' (xem được {series.accessible_count})' if series.accessible_count else ''),
                 f'Link: {link or series.url or ""}', f'Tải lúc: {datetime.datetime.now():%Y-%m-%d %H:%M}']
        if series.description:
            lines += ['', 'Nội dung:', str(series.description).strip()]
        with open(info, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    return poster if os.path.isfile(poster) else None


def series_folder(output_dir, series):
    return os.path.join(output_dir, _safe_name(series.name))


_VIDEO_EXTS = ('.mp4', '.webm', '.mkv', '.mov', '.m4v', '.flv', '.ts', '.avi')
_CTYPE_EXT = {'video/mp4': '.mp4', 'video/webm': '.webm', 'video/x-matroska': '.mkv', 'video/quicktime': '.mov',
              'video/x-flv': '.flv', 'video/mp2t': '.ts', 'video/x-msvideo': '.avi', 'video/x-m4v': '.m4v'}


def download_direct(url, output_dir, title='', log_fn=print, progress_fn=None, should_stop=None):
    """Tải link video trực tiếp (CDN) bằng HTTP — có tiến độ, huỷ giữa chừng, file dở được xoá."""
    import time
    import requests
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, _safe_name(title))
    # đuôi theo link (.webm / .mkv / .mov…), không có thì .mp4 — sửa lại theo Content-Type khi máy chủ trả về
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    ext = ext if ext in _VIDEO_EXTS else '.mp4'
    # GIỮ CHỖ tên file ngay (tạo .part độc quyền): 2 lượt tải cùng lúc cùng tên không chọn trùng file / ghi đè nhau
    k = 1
    while True:
        path = base + ext if k == 1 else f'{base} ({k}){ext}'
        part = path + '.part'
        if not os.path.exists(path):
            try:
                open(part, 'xb').close()
                break
            except FileExistsError:
                pass
        k += 1
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
            ctype = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            real_ext = _CTYPE_EXT.get(ctype)
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
        if real_ext and real_ext != ext:          # máy chủ báo định dạng khác đuôi đã đặt → đổi đuôi cho đúng
            new = os.path.splitext(path)[0] + real_ext
            if not os.path.exists(new):
                path = new
        os.replace(part, path)
        return path
    except requests.RequestException as e:
        raise RuntimeError(f'Lỗi mạng khi tải: {str(e)[:150]}')
    finally:
        if os.path.exists(part):
            os.remove(part)


def download(url, output_dir, log_fn=print, quality='best', progress_fn=None, should_stop=None, title='', meta=None):
    """Tải 1 video → đường dẫn file. Ném RuntimeError (thông báo dễ hiểu) nếu lỗi.
    meta (dict, tuỳ chọn): điền thêm {'thumbnail': link ảnh bìa} nếu nguồn có — để lưu poster."""
    url = normalize(url)
    meta = meta if meta is not None else {}
    if is_direct_media(url):
        return download_direct(url, output_dir, title, log_fn, progress_fn, should_stop)
    if detect_platform(url)[0] == 'drama':     # 1 file → tập đầu tiên xem được (trong các tập đã chọn bằng #ep=)
        try:
            s, eps = drama_episodes(url)
        except Exception as e:
            raise RuntimeError(f'Không đọc được phim: {str(e)[:160]}')
        ep = next((e for e in eps if not e.locked), None)
        if not ep:
            raise RuntimeError('Không có tập nào tải được (tập bị khoá hoặc sai số tập).')
        log_fn(f'   {s.name} · tập {ep.num}')
        meta['thumbnail'] = s.cover
        return download_drama_episode(s, ep, output_dir, log_fn, progress_fn, should_stop)
    (key, label) = detect_platform(url)
    user_cookie = site_cookies.ytdlp_args(key)
    if user_cookie:                            # người dùng đã nạp cookie nền tảng này → dùng phiên của họ trước (nhanh, ổn định)
        log_fn(f'   {label}: tải bằng cookie đã nạp...')
        path, err = _ytdlp_download(url, output_dir, quality, user_cookie, log_fn, progress_fn, should_stop, meta)
        cookie_bad = 'fresh cookies' in err.lower() or 'cookie' in err.lower() or 'login' in err.lower()
        if path or cookie_bad:                 # lỗi khác (video bị xoá, mạng…) không nói gì về cookie → không ghi
            site_cookies.mark(key, bool(path))
        if path:
            return path
        why = 'hết hạn hoặc thiếu phiên' if cookie_bad else _friendly(err, url)[:100]
        log_fn(f'   [WARN] {label} không nhận cookie đã nạp ({why}) — thử cách khác...')
    busy = None
    if key in DTK_PLATFORMS:
        try:
            v = dtk_resolve(url, log_fn=log_fn, should_stop=should_stop)
            log_fn(f"   {v['platform_label']}: {v['height']}p, không logo — {v['title'][:50]}")
            meta['thumbnail'] = v.get('cover')
            return download_direct(v['video'], output_dir, title or v['title'], log_fn, progress_fn, should_stop)
        except RuntimeError as e:
            if str(e) == 'Đã huỷ.':
                raise
            busy = e
            log_fn(f'   [WARN] Nguồn tải Douyin lỗi ({e}) — thử cách dự phòng...')
    log_fn(f'   {label}: {url}')
    if key == 'douyin' and user_cookie:
        path, last_err = None, err             # không cookie thì Douyin chắc chắn từ chối — bỏ lượt thừa
    else:
        path, last_err = _ytdlp_download(url, output_dir, quality, [], log_fn, progress_fn, should_stop, meta)
    if path:
        return path
    # trang đòi phiên trình duyệt → thử cookie của trình duyệt có sẵn trên máy (bỏ qua trình duyệt đã biết là đọc không được)
    if any(w in last_err.lower() for w in ('cookie', 'login', 'sign in', '403', 'blocked')):
        for b in ('chrome', 'edge', 'firefox'):
            if _BROWSER_BAD.get(b, 0) > _now():
                continue
            if should_stop and should_stop():
                raise RuntimeError('Đã huỷ.')
            log_fn(f'   Thử dùng cookie trình duyệt {b}...')
            path, err = _ytdlp_download(url, output_dir, quality, ['--cookies-from-browser', b], log_fn, progress_fn, should_stop, meta)
            if path:
                return path
            if re.search(r'could not (copy|find|open)|failed to (decrypt|load)|cookie database|unsupported browser', err, re.I):
                _BROWSER_BAD[b] = _now() + 1800      # trình duyệt đang mở (khoá file) / chưa cài → 30 phút sau mới thử lại
            else:
                last_err = err
    msg = _friendly(last_err, url)
    if key == 'douyin' and 'fresh cookies' in last_err.lower():
        mins = getattr(busy, 'minutes', 0) if isinstance(busy, DtkBusy) else 0
        wait = f'sau khoảng {mins} phút' if mins else 'sau vài phút'
        msg = (f'Nguồn tải Douyin miễn phí đang tạm nghỉ (Douyin chặn lượt tải dồn dập) — bấm "Tải lại" {wait}, '
               'hoặc nạp cookie Douyin (khung "Cookie Douyin" bên phải) để tải ổn định.' if not user_cookie else
               'Cookie Douyin đã hết hạn — mở douyin.com trên trình duyệt, xuất lại cookie rồi nạp lại.')
    raise RuntimeError(msg)


_BROWSER_BAD = {}


def _now():
    import time
    return time.time()


def _ytdlp_download(url, output_dir, quality, extra, log_fn, progress_fn, should_stop, meta):
    """1 lượt yt-dlp → (đường dẫn file | None, stderr)."""
    os.makedirs(output_dir, exist_ok=True)
    template = os.path.join(output_dir, '%(title).80B [%(id)s].%(ext)s')
    fmt = QUALITY.get(quality, QUALITY['best'])
    base = ['--no-playlist', '-f', fmt, '-o', template, '--newline', '--progress', '--print', 'after_move:filepath', '--windows-filenames',
            '--print', 'after_move:RFTHUMB %(thumbnail)s',
            '--progress-template', 'download:RFPROG %(progress._percent_str)s|%(progress._total_bytes_str)s%(progress._total_bytes_estimate_str)s|%(progress._speed_str)s|%(progress._eta_str)s']
    if quality != 'audio':
        base += ['--merge-output-format', 'mp4']
    lines_out, err_lines = [], []

    def run(p):
        # đọc stderr ở luồng riêng SONG SONG: đọc hết stdout rồi mới đọc stderr thì yt-dlp in nhiều lỗi (đầy bộ đệm
        # stderr) sẽ đứng chờ ghi, còn ta đứng chờ stdout → treo mãi
        import threading
        t_err = threading.Thread(target=lambda: err_lines.append(p.stderr.read()), daemon=True)
        t_err.start()
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
            elif line.startswith('RFTHUMB '):
                meta['thumbnail'] = line[8:].strip() if line[8:].strip() not in ('NA', 'None') else None
            elif line and not line.startswith('['):
                lines_out.append(line)
        p.wait()
        t_err.join(timeout=10)
        return p.returncode

    code = _ytdlp(base + extra + [url], proc_cb=run)
    if should_stop and should_stop():
        raise RuntimeError('Đã huỷ.')
    if code == 0:
        for line in reversed(lines_out):
            if os.path.isfile(line):
                return line, ''
    return None, ''.join(err_lines)


def download_video(url, output_dir, log_fn=print):
    """Giữ tương thích cho pipeline Review/Reup (nhập link ở trang Tạo video)."""
    try:
        path = download(url, output_dir, log_fn)
        log_fn(f'   File: {os.path.basename(path)}')
        return path
    except RuntimeError as e:
        log_fn(f'   [LỖI] {e}')
        return None


# ── Phim ngắn (core/drama_downloader): 1 link = cả bộ phim, tải từng tập ──
_EP_RE = re.compile(r'#ep=([\d,\s-]*)$', re.I)
_SERIES = {}                       # link phim → (thời điểm, Series) — xem trước rồi tải không phải đọc lại


def drama_platform(url):
    """Nền tảng phim ngắn xử lý được link này (theo tên miền), không thì None."""
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    if not host:
        return None
    try:
        from core.drama_downloader import detect_platform as _detect
    except ImportError:            # thiếu thư viện cryptography
        return None
    return _detect(host)


def split_eps(url):
    """'https://…/phim#ep=1-10,15' → ('https://…/phim', '1-10,15')."""
    m = _EP_RE.search(url)
    return (url[:m.start()], m.group(1).replace(' ', '')) if m else (url, '')


def parse_eps(spec):
    """'1-10,15' → {1..10, 15}; rỗng → None (tất cả tập)."""
    want = set()
    for part in (spec or '').split(','):
        a, _, b = part.partition('-')
        if a.isdigit():
            want.update(range(int(a), int(b) + 1) if b.isdigit() else [int(a)])
    return want or None


def drama_series(url, max_age=1200):
    import time
    from core.drama_downloader import load_series
    hit = _SERIES.get(url)
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    s = load_series(url)
    _SERIES[url] = (time.time(), s)
    return s


def drama_episodes(url):
    """Link phim (có thể kèm #ep=…) → (Series, các tập được chọn)."""
    base, spec = split_eps(url)
    s = drama_series(base)
    want = parse_eps(spec)
    return s, [e for e in s.episodes if not want or e.num in want]


def _probe_drama(url, label):
    base, spec = split_eps(url)
    info = {'url': base, 'platform': 'drama', 'platform_label': label}
    try:
        s = drama_series(base)
    except Exception as e:
        return {**info, 'error': f'Không đọc được phim: {str(e)[:160]}'}
    if not s.episodes:
        return {**info, 'error': 'Không tìm thấy tập nào — sai link, phim bị gỡ hoặc nền tảng đổi API.'}
    return {**info, 'title': s.name, 'thumbnail': s.cover, 'uploader': f'{s.accessible_count}/{s.episode_count} tập xem được',
            'episodes': [{'num': e.num, 'title': e.title, 'locked': e.locked} for e in s.episodes], 'ep': spec}


def _download_hls(url, path, log_fn, should_stop=None):
    """Luồng m3u8 → .mp4 bằng ffmpeg (chép nguyên luồng, không mã hoá lại)."""
    import time
    from core.utils import FFMPEG_EXE
    part = path + '.part.mp4'
    log_fn('   Luồng m3u8 — ghép bằng ffmpeg...')
    p = subprocess.Popen([FFMPEG_EXE, '-y', '-loglevel', 'error', '-user_agent', UA, '-i', url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', part],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
    register_process(p)
    try:
        while p.poll() is None:
            if should_stop and should_stop():
                p.kill()
                p.wait()
                raise RuntimeError('Đã huỷ.')
            time.sleep(0.5)
        if p.returncode != 0 or not os.path.isfile(part):
            raise RuntimeError(f'ffmpeg không tải được luồng m3u8: {(p.stderr.read() or "").strip()[-200:]}')
        os.replace(part, path)
        return path
    finally:
        unregister_process(p)
        if os.path.exists(part):
            os.remove(part)


def _save_drama_subs(ep, video_path, log_fn):
    """Phụ đề đi kèm tập (nếu nền tảng có) → '<tên video>.<ngôn ngữ>.srt' cạnh video."""
    import base64
    import requests
    from core.drama_downloader import vtt_to_srt
    stem = os.path.splitext(video_path)[0]
    for sub in ep.subs:
        try:
            if sub.url.startswith('data:'):
                raw = base64.b64decode(sub.url.split(',', 1)[1])
            else:
                r = requests.get(sub.url, headers={'User-Agent': UA}, timeout=30)
                r.raise_for_status()
                raw = r.content
            text = raw.decode('utf-8-sig', errors='replace')
            if 'WEBVTT' in text[:50] or sub.url.split('?')[0].lower().endswith('.vtt'):
                text = vtt_to_srt(text)
            lang = re.sub(r'[^\w-]+', '', sub.lang)[:20] or 'sub'
            with open(f'{stem}.{lang}.srt', 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            log_fn(f'   [WARN] Phụ đề {sub.lang}: {str(e)[:120]}')


def download_drama_episode(series, ep, output_dir, log_fn=print, progress_fn=None, should_stop=None):
    """Tải 1 tập phim ngắn vào '<output_dir>/<tên phim>/EP01.mp4' (+ phụ đề). Tập đã tải rồi thì bỏ qua."""
    from core.drama_downloader import get_video_url
    folder = series_folder(output_dir, series)
    name = f'EP{ep.num:0{3 if len(series.episodes) >= 100 else 2}d}'
    path = os.path.join(folder, name + '.mp4')
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        log_fn('   Đã có sẵn — bỏ qua')
        return path
    if ep.locked:
        raise RuntimeError('Tập này bị khoá (phải trả phí trên nền tảng) — không tải được.')
    try:
        stream = get_video_url(ep, series.platform)
    except Exception:
        stream = None
    if not stream:
        raise RuntimeError('Không lấy được link video của tập này (link hết hạn / nền tảng đổi API) — thử lại sau.')
    os.makedirs(folder, exist_ok=True)
    if '.m3u8' in stream.split('?')[0].lower():
        path = _download_hls(stream, path, log_fn, should_stop)
    else:
        path = download_direct(stream, folder, name, log_fn, progress_fn, should_stop)
    _save_drama_subs(ep, path, log_fn)
    return path


def tool_version():
    code, out, _ = _ytdlp(['--version'], timeout=30)
    return out.strip() if code == 0 else ''


def update_tool():
    """Cập nhật yt-dlp lên bản mới nhất (các nền tảng đổi cách chống tải liên tục)."""
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-U', 'yt-dlp[default]'], capture_output=True, text=True,
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
