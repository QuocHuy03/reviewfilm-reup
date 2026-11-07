#!/usr/bin/env python3
"""
ReviewFilm — Trợ lý Telegram (daemon độc lập).

Nhắn cho bot 1 link video + ý muốn ("lồng tiếng", "reup", "review", "phụ đề") →
bot gọi thẳng API của ReviewFilm Studio (app phải đang mở) để tải + dựng + lồng tiếng,
rồi gửi video kết quả về ngay trong Telegram.

MCP không "đẩy" tin nhắn vào cho agent được, nên daemon này đứng nghe Telegram
(long-polling getUpdates) và tự chạy job — đúng kiểu "nhắn là nó tự làm".

Chạy:  python telegram_bot.py       (cần đặt biến môi trường ở .env — xem README.md)
Dừng:  Ctrl+C
"""
import os
import re
import sys
import time
import html
import json
import mimetypes

import requests

# ───────────────────────── Cấu hình (đọc từ môi trường / .env) ─────────────────────────


def _load_dotenv():
    """Nạp .env đơn giản (KEY=VALUE mỗi dòng) — khỏi cần thư viện ngoài."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.isfile(p):
        with open(p, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
ALLOWED = {int(x) for x in re.findall(r'\d+', os.environ.get('TELEGRAM_ALLOWED_IDS', ''))}
RF_PORT = os.environ.get('RF_PORT', '47651').strip()
RF_BASE = f'http://127.0.0.1:{RF_PORT}'
DEFAULT_MODE = os.environ.get('RF_TG_DEFAULT_MODE', 'reup').strip()      # link trơn, không ghi gì → chế độ này
TARGET_LANG = os.environ.get('RF_TG_TARGET_LANG', 'vi').strip()
TG_API = f'https://api.telegram.org/bot{BOT_TOKEN}'
TG_MAX_UPLOAD = 48 * 1024 * 1024        # bot thường gửi tối đa ~50MB — lớn hơn thì trả đường dẫn file

URL_RE = re.compile(r'https?://\S+')

# từ khoá → chế độ của app. "lồng tiếng" = chế độ Lồng tiếng (vietsub + đọc lời), "reup" = thuyết minh từng câu.
MODE_WORDS = [
    (('review', 'rì viu', 'thuyết minh phim'), ('review', {})),
    (('reup', 're up', 'thuyết minh'), ('reup', {})),
    (('lồng tiếng', 'long tieng', 'lồng', 'lt'), ('vietsub', {'dub_voice': True})),
    (('phụ đề', 'phu de', 'vietsub', 'sub', 'srt'), ('vietsub', {})),
    (('tải', 'tai ', 'download', 'cào', 'cao '), ('download', {})),
]


# ───────────────────────── Telegram API ─────────────────────────


def tg(method, **params):
    r = requests.post(f'{TG_API}/{method}', data=params, timeout=65)
    return r.json()


def tg_send(chat_id, text):
    return tg('sendMessage', chat_id=chat_id, text=text, parse_mode='HTML',
              disable_web_page_preview='true').get('result', {})


def tg_edit(chat_id, message_id, text):
    try:
        tg('editMessageText', chat_id=chat_id, message_id=message_id, text=text,
           parse_mode='HTML', disable_web_page_preview='true')
    except Exception:
        pass


def tg_send_file(chat_id, path, caption=''):
    """Gửi video (hoặc file) kèm chú thích. Quá lớn → báo đường dẫn thay vì gửi."""
    try:
        size = os.path.getsize(path)
    except OSError:
        tg_send(chat_id, f'⚠️ Không thấy file xuất: <code>{html.escape(path)}</code>')
        return
    if size > TG_MAX_UPLOAD:
        mb = size / 1024 / 1024
        tg_send(chat_id, f'✅ Xong! File hơi lớn ({mb:.0f}MB, quá hạn gửi của Telegram).\n'
                         f'Lấy ở máy: <code>{html.escape(path)}</code>')
        return
    is_video = os.path.splitext(path)[1].lower() in ('.mp4', '.mkv', '.mov', '.webm')
    method, field = ('sendVideo', 'video') if is_video else ('sendDocument', 'document')
    with open(path, 'rb') as f:
        mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        requests.post(f'{TG_API}/{method}',
                      data={'chat_id': chat_id, 'caption': caption[:1024], 'supports_streaming': 'true'},
                      files={field: (os.path.basename(path), f, mime)}, timeout=600)


# ───────────────────────── ReviewFilm Studio API ─────────────────────────


def rf(method, path, **kw):
    r = requests.request(method, RF_BASE + path, timeout=kw.pop('timeout', 120), **kw)
    if r.status_code >= 400:
        try:
            detail = r.json().get('detail')
        except Exception:
            detail = r.text[:300]
        raise RuntimeError(detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)[:400])
    return r.json() if r.content else {}


def parse_intent(text):
    """Trả (mode, options, url). Không có link → url=None."""
    low = text.lower()
    mode, opts = DEFAULT_MODE, {}
    for words, (m, o) in MODE_WORDS:
        if any(w in low for w in words):
            mode, opts = m, dict(o)
            break
    m = URL_RE.search(text)
    return mode, opts, (m.group(0) if m else None)


def start_job(url, mode, opts):
    """Tạo job (như bấm nút trong app): lấy mặc định từ Cài đặt rồi gửi link vào."""
    if mode == 'download':
        j = rf('POST', '/api/jobs/download', json={'urls': [url], 'quality': 'best', 'subs': '', 'out_dir': ''})
        return j
    st = rf('GET', '/api/settings')
    body = {k: st[k] for k in ('whisper_model', 'device', 'sub_style', 'sub_layout', 'sub_custom') if st.get(k) is not None}
    if TARGET_LANG == 'vi' and st.get('voice'):
        body['voice'] = st['voice']
    body |= {'inp': url, 'mode': mode, 'target_lang': TARGET_LANG, 'minutes': 0, 'film_context': '',
             'script_edit': False, 'scene_preview': False, 'burn_subtitles': True,
             'remove_old_sub': False, 'target_resolution': '1920x1080', 'out_dir': ''}
    body.update(opts)
    return rf('POST', '/api/jobs/video', json=body)


def result_video(job):
    res = job.get('result') or {}
    if isinstance(res.get('video_path'), str):
        return res['video_path']
    for v in res.values():                                   # fallback: file .mp4 bất kỳ trong result
        if isinstance(v, str) and os.path.splitext(v)[1].lower() in ('.mp4', '.mkv', '.mov'):
            return v
    return None


def run_message(chat_id, text):
    mode, opts, url = parse_intent(text)
    if not url:
        tg_send(chat_id, 'Gửi mình <b>link video</b> kèm ý muốn nhé:\n'
                         '• <code>lồng tiếng &lt;link&gt;</code>\n'
                         '• <code>reup &lt;link&gt;</code> — thuyết minh từng câu\n'
                         '• <code>review &lt;link&gt;</code> — AI tóm tắt &amp; review\n'
                         '• <code>phụ đề &lt;link&gt;</code> — chỉ ghép phụ đề\n'
                         '• <code>tải &lt;link&gt;</code> — chỉ tải video')
        return
    try:
        rf('GET', '/api/health', timeout=8)
    except Exception:
        tg_send(chat_id, '⚠️ Chưa kết nối được ReviewFilm Studio — mở app lên rồi gửi lại nhé.')
        return
    label = {'review': 'Review', 'reup': 'Reup (thuyết minh)', 'vietsub': 'Lồng tiếng / phụ đề',
             'download': 'Tải video'}.get(mode, mode)
    msg = tg_send(chat_id, f'▶️ Nhận rồi! Đang <b>{label}</b>…\n<code>{html.escape(url)}</code>')
    mid = msg.get('message_id')
    try:
        job = start_job(url, mode, opts)
        jid = job.get('id')
        if not jid:
            tg_edit(chat_id, mid, '⚠️ Không tạo được job. Thử lại sau nhé.')
            return
        last = ''
        while True:
            time.sleep(4)
            j = rf('GET', f'/api/jobs/{jid}')
            status = j.get('status')
            if status in ('done', 'error', 'cancelled') or j.get('waiting'):
                break
            now = f"⏳ {label}: {j.get('stage') or status or ''} {j.get('progress') or ''}".strip()
            if now != last:
                tg_edit(chat_id, mid, now[:3800])
                last = now
        if j.get('status') == 'error':
            logs = '\n'.join((l.get('msg') or str(l)) for l in (j.get('logs') or [])[-4:])
            tg_edit(chat_id, mid, f'❌ Lỗi: {html.escape(str(j.get("error") or ""))}\n<code>{html.escape(logs[:500])}</code>')
            return
        if j.get('waiting'):
            tg_edit(chat_id, mid, '⏸️ Job đang chờ bạn duyệt trong app (bước kịch bản). Vào app xác nhận giúp nhé.')
            return
        # tải xong hoặc dựng xong
        if mode == 'download':
            items = (j.get('result') or {}).get('items') or []
            paths = [it.get('path') for it in items if it.get('path')]
            tg_edit(chat_id, mid, f'✅ Tải xong {len(paths)} file.')
            for p in paths[:10]:
                tg_send_file(chat_id, p, caption=os.path.basename(p))
            return
        vid = result_video(j)
        tg_edit(chat_id, mid, f'✅ Xong <b>{label}</b>! Đang gửi video…')
        if vid:
            tg_send_file(chat_id, vid, caption=f'{label} — {os.path.basename(vid)}')
        else:
            tg_send(chat_id, 'Xong nhưng không thấy file video trong kết quả — kiểm tra trong app nhé.')
    except Exception as e:
        tg_edit(chat_id, mid, f'❌ {html.escape(str(e)[:500])}')


# ───────────────────────── Vòng lặp long-poll ─────────────────────────


def main():
    if not BOT_TOKEN:
        print('Thiếu TELEGRAM_BOT_TOKEN — xem README.md (tạo bot bằng @BotFather).', file=sys.stderr)
        sys.exit(1)
    me = tg('getMe').get('result') or {}
    print(f"Bot @{me.get('username','?')} đã chạy. Cho phép user ID: {sorted(ALLOWED) or 'MỌI NGƯỜI (nên đặt allowlist!)'}")
    print(f'Nối tới ReviewFilm Studio tại {RF_BASE} (app phải đang mở).')
    offset = None
    while True:
        try:
            params = {'timeout': 50}
            if offset is not None:
                params['offset'] = offset
            r = requests.get(f'{TG_API}/getUpdates', params=params, timeout=60).json()
            for upd in r.get('result', []):
                offset = upd['update_id'] + 1
                m = upd.get('message') or upd.get('edited_message')
                if not m or 'text' not in m:
                    continue
                uid = (m.get('from') or {}).get('id')
                chat_id = m['chat']['id']
                if ALLOWED and uid not in ALLOWED:
                    tg_send(chat_id, f'⛔ Bạn chưa được cấp quyền. Gửi admin ID này để thêm: <code>{uid}</code>')
                    continue
                run_message(chat_id, m['text'])
        except KeyboardInterrupt:
            print('\nDừng bot.')
            break
        except Exception as e:
            print('Lỗi vòng lặp:', e, file=sys.stderr)
            time.sleep(3)


if __name__ == '__main__':
    main()
