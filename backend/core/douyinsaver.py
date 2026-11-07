"""Nguồn tải douyinsaver.com (reverse API) — Douyin, không logo, không cần đăng nhập.

Trang là SPA Next.js, không có <form>; nút Download bắn fetch tới API host RIÊNG:

  POST https://api.douyinsaver.com/api/parse
    body JSON {url, cf_turnstile_token?}  (token Cloudflare Turnstile TUỲ CHỌN — bỏ qua được)
    → {aweme_id, title, author, cover, duration(ms), media_type, images,
       qualities:[{label, codec(h264/h265), height, width, bitrate, url, size}]}
    qualities[].url là LINK CDN Douyin gốc, không logo, đã ký sẵn (x-expires/x-signature).

  Dự phòng (khi link CDN trực tiếp lỗi/hết hạn):
    GET https://api.douyinsaver.com/api/download/video/{aweme_id}?quality={label}
    → máy chủ proxy tải MP4 về.

Không cần API key / chữ ký. Bản không token bị giới hạn lượt (HTTP 429 {"detail":"tokenless_cap"});
lỗi link → HTTP 422 {"detail":"..."}. Mọi lỗi → RuntimeError (tiếng Việt) để nơi gọi lùi về cách khác.
"""
import os
import time
import urllib.parse

API = 'https://api.douyinsaver.com'
SITE = 'https://douyinsaver.com'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

# Chỉ nhận Douyin (TikTok/YouTube để nguồn khác lo)
_DOUYIN = ('douyin.com', 'iesdouyin.com', 'v.douyin.com')


def dys_type(url):
    """Link → 'douyin' nếu trang này nhận, không thì None."""
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    if any(host == d or host.endswith('.' + d) for d in _DOUYIN):
        return 'douyin'
    return None


def _parse(url):
    """Gọi /api/parse → dict thô. RuntimeError nếu trang báo lỗi."""
    import requests
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Origin': SITE, 'Referer': SITE + '/',
                      'Accept': 'application/json', 'Content-Type': 'application/json'})
    try:
        r = s.post(API + '/api/parse', json={'url': url}, timeout=60)
    except requests.RequestException as e:
        raise RuntimeError(f'không kết nối được douyinsaver.com ({str(e)[:80]})')
    if r.status_code == 429:
        raise RuntimeError('douyinsaver.com đã hết lượt tải miễn phí hôm nay (tokenless_cap).')
    try:
        j = r.json()
    except ValueError:
        raise RuntimeError(f'máy chủ trả dữ liệu không hợp lệ (HTTP {r.status_code})')
    if r.status_code != 200 or not isinstance(j, dict) or j.get('detail') or j.get('error'):
        msg = str(j.get('detail') or j.get('error') or f'HTTP {r.status_code}').strip()
        raise RuntimeError(msg[:160])
    return j, s


def _pick_video(data):
    """Chọn quality tốt nhất: ưu tiên độ phân giải cao, cùng độ phân giải thì h264 (dễ xử lý),
    rồi bitrate/size lớn hơn. Trả dict quality hoặc None."""
    qs = [q for q in (data.get('qualities') or [])
          if isinstance(q, dict) and isinstance(q.get('url'), str) and q['url'].startswith('http')]
    if not qs:
        return None
    def key(q):
        h = q.get('height') or 0
        w = q.get('width') or 0
        h264 = 1 if str(q.get('codec') or '').lower().startswith('h264') else 0
        return (max(h, w), h264, q.get('bitrate') or 0, q.get('size') or 0)
    return max(qs, key=key)


def _norm_info(data, url):
    """data thô → dict gọn cho app (giống probe của downloader)."""
    dur = data.get('duration')
    dur = round(dur / 1000.0, 2) if isinstance(dur, (int, float)) and dur > 1000 else (dur or None)
    cover = data.get('cover') or ''
    images = data.get('images') if (data.get('media_type') == 'image' or data.get('images')) else None
    return {'url': url, 'platform': 'douyin', 'platform_label': 'Douyin', 'source': 'dys',
            'title': data.get('title') or '', 'duration': dur if isinstance(dur, (int, float)) else None,
            'thumbnail': cover if str(cover).startswith('http') else '',
            'uploader': data.get('author') or '', 'images': images}


def probe(url, typ='douyin'):
    """Metadata không tải (tiêu đề, ảnh bìa, thời lượng…). RuntimeError nếu lỗi."""
    data, _ = _parse(url)
    return _norm_info(data, url)


def download(url, typ='douyin', output_dir='.', title='', log_fn=print,
             progress_fn=None, should_stop=None, meta=None):
    """Phân tích rồi tải video về → đường dẫn file. RuntimeError (thông báo rõ) nếu lỗi → nơi gọi tự lùi về cách khác."""
    import requests
    meta = meta if meta is not None else {}
    data, sess = _parse(url)
    cover = data.get('cover') or ''
    if str(cover).startswith('http'):
        meta['thumbnail'] = cover
    if data.get('media_type') == 'image' or (data.get('images') and not data.get('qualities')):
        raise RuntimeError('Link này là bài ảnh (slideshow), không phải video.')
    q = _pick_video(data)
    if not q:
        raise RuntimeError('Nguồn douyinsaver không trả link video (video riêng tư / bị chặn / đã xoá).')

    os.makedirs(output_dir, exist_ok=True)
    from core.downloader import _safe_name          # dùng chung quy tắc đặt tên với phần tải còn lại
    base = os.path.join(output_dir, _safe_name(title or data.get('title') or 'video'))
    k = 1
    while True:                                      # giữ chỗ tên file (.part độc quyền) — tránh trùng
        path = base + '.mp4' if k == 1 else f'{base} ({k}).mp4'
        part = path + '.part'
        if not os.path.exists(path):
            try:
                open(part, 'xb').close()
                break
            except FileExistsError:
                pass
        k += 1

    log_fn(f'   douyinsaver · Douyin: {(data.get("title") or "")[:50]}')
    # link CDN trực tiếp (đã ký); hỏng thì lùi về proxy máy chủ /api/download/video/{id}
    candidates = [(q['url'], {'User-Agent': UA, 'Referer': 'https://www.douyin.com/', 'Accept': '*/*'})]
    aid = data.get('aweme_id')
    if aid:
        proxy = f'{API}/api/download/video/{aid}'
        lbl = q.get('label')
        if lbl:
            proxy += '?quality=' + urllib.parse.quote(str(lbl))
        candidates.append((proxy, {'User-Agent': UA, 'Origin': SITE, 'Referer': SITE + '/', 'Accept': '*/*'}))

    last_err = None
    for src_url, headers in candidates:
        try:
            with sess.get(src_url, headers=headers, stream=True, timeout=120) as r:
                if r.status_code != 200:
                    last_err = f'HTTP {r.status_code}'
                    continue
                total = int(r.headers.get('Content-Length') or 0)
                got, t0, last = 0, time.time(), 0.0
                with open(part, 'wb') as f:
                    for chunk in r.iter_content(1 << 20):
                        if should_stop and should_stop():
                            raise RuntimeError('Đã huỷ.')
                        if not chunk:
                            continue
                        f.write(chunk)
                        got += len(chunk)
                        now = time.time()
                        if progress_fn and (now - last > 0.5 or got == total):
                            last = now
                            speed = got / max(0.001, now - t0)
                            eta = (total - got) / speed if total and speed else 0
                            progress_fn(got / total * 100 if total else 0,
                                        f'{total / 1048576:.1f}MiB' if total else '',
                                        f'{speed / 1048576:.2f}MiB/s',
                                        f'{int(eta // 60):02d}:{int(eta % 60):02d}' if total else '')
            if got < 65536:                           # body rỗng/quá nhỏ = bị chặn → thử nguồn kế
                last_err = f'tải về rỗng/quá nhỏ ({got} byte)'
                continue
            os.replace(part, path)
            return path
        except requests.RequestException as e:
            last_err = f'lỗi mạng ({str(e)[:100]})'
            continue
        finally:
            if os.path.exists(part) and not os.path.exists(path):
                open(part, 'wb').close()              # dọn body hỏng, giữ chỗ cho lần thử kế
    if os.path.exists(part):
        os.remove(part)
    raise RuntimeError(f'Nguồn douyinsaver không tải được ({last_err or "không rõ"}).')
