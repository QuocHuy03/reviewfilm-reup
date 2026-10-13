

'Tai video tu URL bang yt-dlp'
import os
import sys
import subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.utils import _HIDE
def download_video(url, output_dir, log_fn=print):
    url = url.strip()
    if 'douyin.com' in url:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        video_id = None
        if 'modal_id' in params:
            video_id = params['modal_id'][0]
        elif 'vid' in params:
            video_id = params['vid'][0]
        if video_id:
            new_url = f'''https://www.douyin.com/video/{video_id}'''
            log_fn(f'''   [Douyin Link Optimizer] Chuyen doi link user sang dang video: {new_url}''')
            url = new_url
    log_fn(f'''   URL: {url}''')
    log_fn('   Dang lay thong tin video...')
    os.makedirs(output_dir, exist_ok=True)
    template = os.path.join(output_dir, '%(title).50s.%(ext)s')
    base_args = ['--no-playlist', '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', '--merge-output-format', 'mp4', '-o', template, '--no-warnings', '--print', 'after_move:filepath', url]
    cmd = [sys.executable, '-m', 'yt_dlp'] + base_args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
        need_cookies = False
        if r.returncode != 0:
            err_msg = r.stderr.lower()
            if 'cookies' in err_msg or 'cookie' in err_msg or '403' in err_msg or 'forbidden' in err_msg or 'token' in err_msg:
                need_cookies = True
                log_fn('   [Yêu cầu Cookie] Phat hien yeu cau xac thuc cookie. Thu trich xuat tu trinh duyet...')
            else:
                log_fn(f'''   [LOI] yt-dlp: {r.stderr[slice(None, 300, None)]}''')
        if need_cookies:
            for browser in ('chrome', 'edge', 'firefox', 'opera', 'brave'):
                log_fn(f'''   Dang thu dung cookie tu trinh duyet: {browser}...''')
                cookie_cmd = [sys.executable, '-m', 'yt_dlp', '--cookies-from-browser', browser] + base_args
                r_cookie = subprocess.run(cookie_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
                if r_cookie.returncode == 0:
                    r = r_cookie
                    log_fn(f'''   [OK] Tai video thanh cong nho lay cookie tu {browser}!''')
                    break
                else:
                    err_clean = r_cookie.stderr.strip().split('\n')[-1] if r_cookie.stderr.strip() else 'Unknown error'
                    log_fn(f'''   Thu qua {browser} khong thanh cong: {err_clean[slice(None, 120, None)]}''')
        if r.returncode != 0:
            log_fn(f'''   [LOI] yt-dlp (da thu cac trinh duyet): {r.stderr[slice(None, 300, None)]}''')
            return
        for line in reversed([l.strip() for l in r.stdout.strip().split('\n') if l.strip()]):
            if os.path.isfile(line):
                log_fn(f'''   File: {os.path.basename(line)}''')
                return line
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.lower().endswith('.mp4')]
        if files:
            newest = max(files, key=os.path.getmtime)
            return newest
        return
    except Exception as e:
        log_fn(f'''   [LOI] Download: {e}''')