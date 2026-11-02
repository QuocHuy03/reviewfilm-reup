"""MCP server của ReviewFilm Studio — cho AI (Claude Desktop / Claude Code / Cursor…) điều khiển tool.

Hai cách kết nối, dùng CHUNG bộ lệnh dưới đây (mỗi lệnh gọi lại đúng REST API của backend đang chạy — chung hàng đợi job,
chung lịch sử với giao diện):
  • Streamable HTTP:  http://127.0.0.1:<cổng>/mcp  (header Authorization: Bearer <token>) — nhúng sẵn trong backend.
  • stdio:            python main.py --mcp-stdio — cho client chỉ chạy lệnh (Claude Desktop). Đọc cổng + token từ
                      DATA_DIR/mcp.json do backend ghi lúc khởi động → app phải đang mở.
Chỉ nghe 127.0.0.1; token chống trang web lạ gọi vào (DNS rebinding) — xem connection_info / ensure_token.
"""
import json
import os
import secrets
import time
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

from app.config import DATA_DIR

INFO_FILE = os.path.join(DATA_DIR, 'mcp.json')

INSTRUCTIONS = """ReviewFilm Studio: biến phim (thường là phim Trung) thành video Review có thuyết minh, video Reup lồng tiếng,
hoặc video Dịch phụ đề (che phụ đề cũ, ghép phụ đề mới, lồng tiếng theo nhân vật) — 17 ngôn ngữ đầu ra, >1.200 giọng đọc.
Quy trình gợi ý: (1) download_videos nếu người dùng đưa link → wait_for_job lấy đường dẫn file; (2) list_voices để chọn
giọng hợp ngôn ngữ; (3) create_video_job; (4) wait_for_job — nếu job dừng ở bước chờ ('script' = duyệt kịch bản/bản
dịch, 'preview' = nghe lại trước khi dựng) thì get_script → update_script (nếu cần sửa) → approve_step; (5) get_outputs.
Một job dài vài phút tới hàng chục phút: gọi wait_for_job lặp lại (mỗi lần ≤ 50 giây) tới khi xong."""

mcp = FastMCP('ReviewFilm Studio', instructions=INSTRUCTIONS, streamable_http_path='/', stateless_http=True, json_response=True,
              log_level='WARNING')


def tool(fn):
    """Đăng ký lệnh MCP chạy ở LUỒNG RIÊNG: lệnh gọi lại REST của chính backend (đồng bộ) — chạy thẳng trong vòng lặp
    sự kiện của server sẽ tự khoá (server chờ chính nó trả lời)."""
    import functools

    import anyio

    @functools.wraps(fn)
    async def run(*a, **kw):
        return await anyio.to_thread.run_sync(functools.partial(fn, *a, **kw))
    mcp.tool()(run)
    return fn


# ───────────────────────── kết nối ─────────────────────────
def ensure_token():
    """Token cố định theo máy (tạo 1 lần) — client lưu trong cấu hình, đổi cổng không phải dán lại."""
    info = read_info()
    if not info.get('token'):
        info['token'] = secrets.token_urlsafe(24)
        _write_info(info)
    return info['token']


def read_info():
    try:
        with open(INFO_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_info(info):
    os.makedirs(os.path.dirname(INFO_FILE), exist_ok=True)
    tmp = INFO_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(info, f)
    os.replace(tmp, INFO_FILE)


def publish_port(port):
    """Backend gọi lúc khởi động: ghi cổng hiện tại cho chế độ stdio + nút "Sao chép cấu hình"."""
    info = read_info()
    info['port'] = int(port)
    info.setdefault('token', secrets.token_urlsafe(24))
    _write_info(info)
    os.environ['RF_PORT'] = str(port)


def _base_url():
    port = os.environ.get('RF_PORT') or read_info().get('port')
    if not port:
        raise RuntimeError('ReviewFilm Studio chưa chạy — mở app lên rồi thử lại.')
    return f'http://127.0.0.1:{port}'


def _call(method, path, **kw):
    try:
        # trust_env=False: gọi thẳng 127.0.0.1 — máy có HTTP_PROXY / proxy công ty thì httpx có thể đẩy cả localhost qua proxy
        r = httpx.request(method, _base_url() + path, timeout=kw.pop('timeout', 120), trust_env=False, **kw)
    except httpx.ConnectError:
        raise RuntimeError('Không kết nối được ReviewFilm Studio — app có đang mở không?')
    if r.status_code >= 400:
        try:
            detail = r.json().get('detail')
        except ValueError:
            detail = r.text[:300]
        raise RuntimeError(f'{detail}' if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)[:500])
    return r.json() if r.content else {}


def _job_brief(j, logs=8):
    out = {k: j.get(k) for k in ('id', 'kind', 'title', 'status', 'waiting', 'stage', 'progress', 'error') if j.get(k) not in (None, '')}
    res = j.get('result') or {}
    files = {k: v for (k, v) in res.items() if isinstance(v, str) and os.path.splitext(v)[1].lower() in
             ('.mp4', '.mkv', '.mov', '.srt', '.vtt', '.ass', '.mp3', '.wav', '.txt', '.json', '.jpg', '.png')}
    if files:
        out['files'] = files
    if res.get('items'):
        out['downloaded'] = [{'path': it.get('path'), 'title': it.get('title') or it.get('series'), 'error': it.get('error')}
                             for it in res['items']][:50]
    if logs and j.get('logs'):
        out['recent_log'] = [(l.get('msg') or l.get('text') or '' if isinstance(l, dict) else str(l)).strip() for l in j['logs'][-logs:]]
    return out


def _langs_codes():
    from core import langs
    return set(langs.LANGS)


def _voice_label(voice):
    """Nhận nhãn ("CapCut EN — Raya (Nữ)") hoặc mã kỹ thuật ("capcut-…", "en-US-AriaNeural") → nhãn app dùng."""
    if not voice:
        return voice
    voices = _call('GET', '/api/voices')
    for v in voices:
        if voice in (v['label'], v['id']):
            return v['label']
    low = voice.lower()
    hits = [v for v in voices if low in v['label'].lower()]
    if len(hits) == 1:
        return hits[0]['label']
    raise RuntimeError(f'Không tìm thấy giọng "{voice}" — dùng list_voices để lấy đúng tên.')


# ───────────────────────── giọng & ngôn ngữ ─────────────────────────
@tool
def list_languages() -> list[dict]:
    """Các ngôn ngữ lồng tiếng / phụ đề đầu ra (target_lang) và số giọng đọc mỗi ngôn ngữ."""
    from core import langs
    voices = _call('GET', '/api/voices')
    fits = lambda v, c: (v.get('lang') or 'vi') == c or (c != 'vi' and v.get('lang') == 'multi')
    return [{'code': c, 'name': row[0], 'english': row[1], 'voices': sum(1 for v in voices if fits(v, c))}
            for (c, row) in langs.LANGS.items()]


@tool
def list_voices(lang: str = 'vi', query: str = '', gender: str = '', only_ready: bool = True, limit: int = 60) -> dict:
    """Giọng đọc theo ngôn ngữ. lang: mã ngôn ngữ (vi, en, zh, ja, ko, id, th, es…). query: lọc theo tên.
    gender: 'male' | 'female'. Trả về 'label' — dùng đúng chuỗi này cho create_video_job / test_voice."""
    voices = _call('GET', '/api/voices')
    fits = lambda v: (v.get('lang') or 'vi') == lang or (lang != 'vi' and v.get('lang') == 'multi')
    q = query.lower().strip()
    sel = [v for v in voices if fits(v) and (not only_ready or v.get('available'))
           and (not q or q in v['label'].lower()) and (not gender or v.get('gender') == gender)]
    return {'total': len(sel), 'voices': [{'label': v['label'], 'group': v['group'], 'gender': v.get('gender'),
                                           'free': v.get('free'), 'available': v.get('available'),
                                           **({'need': v['need']} if v.get('need') else {})} for v in sel[:max(1, limit)]]}


@tool
def test_voice(voice: str, text: str = '') -> dict:
    """Đọc thử 1 câu bằng giọng → đường dẫn file audio. text trống → câu mẫu theo ngôn ngữ của giọng."""
    r = _call('POST', '/api/voices/test', json={'voice': _voice_label(voice), 'text': text}, timeout=300)
    return {'audio_path': r.get('path'), 'duration': r.get('duration'), 'engine': r.get('engine')}


# ───────────────────────── tải video ─────────────────────────
@tool
def download_videos(urls: list[str], quality: str = 'best', subs: str = '', out_dir: str = '') -> dict:
    """Tải video từ link (Douyin, TikTok, Bilibili, YouTube, Weibo, phim ngắn DramaBox…). Dán nguyên đoạn chia sẻ cũng
    được. quality: 'best' | '1080' | '720' | 'audio'. subs: '' (không) | 'zh' | 'en' | 'ko' | 'ja' — tạo phụ đề kèm dịch.
    Trả job_id → wait_for_job để lấy đường dẫn file đã tải."""
    if quality not in ('best', '1080', '720', 'audio'):
        raise RuntimeError("quality phải là 'best', '1080', '720' hoặc 'audio'")
    if subs not in ('', 'zh', 'en', 'ko', 'ja'):
        raise RuntimeError("subs phải là '', 'zh', 'en', 'ko' hoặc 'ja'")
    j = _call('POST', '/api/jobs/download', json={'urls': urls, 'quality': quality, 'subs': subs, 'out_dir': out_dir})
    return _job_brief(j, logs=0)


# ───────────────────────── tạo & theo dõi job ─────────────────────────
@tool
def create_video_job(input: str, mode: str = 'review', target_lang: str = 'vi', voice: str = '', voice_female: str = '',
                     minutes: int = 0, film_context: str = '', auto: bool = True, burn_subtitles: bool = True,
                     remove_old_sub: bool = False, target_resolution: str = '1920x1080', out_dir: str = '',
                     options: Optional[dict[str, Any]] = None) -> dict:
    """Tạo job làm video. input: đường dẫn file video trên máy (hoặc link). mode:
      'review'  — AI xem phim, viết lời thuyết minh, lồng tiếng, dựng video review (minutes: độ dài mong muốn, 0 = tự động);
      'reup'    — nhận dạng lời thoại, dịch, lồng tiếng thuyết minh theo từng câu;
      'vietsub' — dịch phụ đề: đọc phụ đề cứng / nhận dạng giọng, dịch, ghép phụ đề mới (+ lồng tiếng nếu options.dub_voice).
    target_lang: ngôn ngữ đầu ra (list_languages). voice: nhãn giọng từ list_voices (trống = mặc định của ngôn ngữ).
    voice_female: Dịch phụ đề — giọng cho nhân vật nữ (bật options.dub_by_gender).
    auto=True: chạy thẳng tới video xong; False: dừng ở bước duyệt kịch bản / nghe lại (approve_step để đi tiếp).
    target_resolution: '1920x1080' | '1280x720' | '1080x1920' (dọc). options: các tuỳ chọn nâng cao khác của app
    (vd {"dub_voice": true, "keep_bg": true, "watermark_text": "@kenh", "watermark_motion": "hop", "cover_style": "blur"})."""
    if mode not in ('review', 'reup', 'vietsub'):
        raise RuntimeError("mode phải là 'review', 'reup' hoặc 'vietsub'")
    if target_lang not in _langs_codes():
        raise RuntimeError(f'target_lang "{target_lang}" không hỗ trợ — xem list_languages')
    # như giao diện: điền sẵn theo Cài đặt → Mặc định (nhận dạng giọng, GPU/CPU, kiểu phụ đề, giọng mặc định…)
    st = _call('GET', '/api/settings')
    body: dict[str, Any] = {k: st[k] for k in ('whisper_model', 'device', 'sub_style', 'sub_layout', 'sub_custom') if st.get(k) is not None}
    if target_lang == 'vi' and st.get('voice'):
        body['voice'] = st['voice']
    body |= {'inp': input, 'mode': mode, 'target_lang': target_lang, 'minutes': minutes, 'film_context': film_context,
                            'script_edit': not auto, 'scene_preview': not auto, 'burn_subtitles': burn_subtitles,
                            'remove_old_sub': remove_old_sub, 'target_resolution': target_resolution, 'out_dir': out_dir}
    if voice:
        body['voice'] = _voice_label(voice)
    elif target_lang != 'vi':
        body['voice'] = f'Edge TTS {target_lang.upper()} — Nữ (miễn phí)'
    if voice_female:
        body['voice_female'] = _voice_label(voice_female)
    body.update(options or {})
    return _job_brief(_call('POST', '/api/jobs/video', json=body), logs=0)


@tool
def list_jobs(limit: int = 20, status: str = '') -> list[dict]:
    """Các job gần đây (mới nhất trước). status: lọc 'queued' | 'running' | 'waiting' | 'done' | 'error' | 'cancelled'."""
    jobs = _call('GET', '/api/jobs')
    if status:
        jobs = [j for j in jobs if j.get('status') == status]
    return [_job_brief(j, logs=0) for j in jobs[:max(1, limit)]]


@tool
def get_job(job_id: str, log_lines: int = 15) -> dict:
    """Trạng thái 1 job: tiến độ %, bước đang chạy, bước đang chờ duyệt, file xuất, vài dòng nhật ký cuối."""
    return _job_brief(_call('GET', f'/api/jobs/{job_id}'), logs=log_lines)


@tool
def wait_for_job(job_id: str, timeout_sec: int = 50) -> dict:
    """Chờ job xong / lỗi / dừng ở bước chờ duyệt, tối đa timeout_sec (mặc định 50 — nhiều app AI tự ngắt lệnh sau 60s;
    client không giới hạn thì tăng được tới 600). Hết giờ mà job vẫn chạy → trả tiến độ hiện tại; gọi lại để chờ tiếp."""
    end = time.time() + max(5, min(600, timeout_sec))
    while True:
        j = _call('GET', f'/api/jobs/{job_id}')
        if j.get('status') not in ('running', 'queued', 'pending') or j.get('waiting') or time.time() >= end:
            return _job_brief(j, logs=6)
        time.sleep(3)


@tool
def get_outputs(job_id: str) -> dict:
    """Đường dẫn các file job đã xuất (video, phụ đề .srt, bài đăng, thumbnail…)."""
    j = _call('GET', f'/api/jobs/{job_id}')
    return {'status': j.get('status'), 'result': j.get('result') or {}}


@tool
def cancel_job(job_id: str) -> dict:
    """Dừng job đang chạy / đang chờ."""
    return _call('POST', f'/api/jobs/{job_id}/cancel')


@tool
def retry_job(job_id: str, resume: bool = True) -> dict:
    """Job lỗi / đã dừng: resume=True chạy tiếp từ bước hỏng (Review / Reup); False = chạy lại từ đầu (job mới)."""
    if resume:
        try:
            return _job_brief(_call('POST', f'/api/jobs/{job_id}/resume'), logs=0)
        except RuntimeError:
            pass
    return _job_brief(_call('POST', f'/api/jobs/{job_id}/retry'), logs=0)


# ───────────────────────── duyệt & sửa kịch bản ─────────────────────────
def _scenes_of(j):
    d = j.get('draft') or {}
    return d.get('scenes') if d.get('scenes') else (j.get('scenes') or [])


@tool
def get_script(job_id: str, start: int = 0, count: int = 200) -> dict:
    """Kịch bản / bản dịch của job (từng câu: lời đọc, phụ đề, thời gian trong phim gốc). Dùng khi job dừng ở bước chờ
    duyệt để đọc / sửa trước khi đi tiếp."""
    j = _call('GET', f'/api/jobs/{job_id}')
    sc = _scenes_of(j)
    rows = []
    for (i, s) in enumerate(sc[start:start + max(1, count)], start):
        rows.append({'index': i, 'voiceover': s.get('voiceover', ''), 'subtitle': s.get('subtitle', ''),
                     'start': s.get('clip_start'), 'end': s.get('clip_end'),
                     **({'original': s['orig_text']} if s.get('orig_text') else {}),
                     **({'excluded': True} if s.get('excluded') else {})})
    return {'waiting': j.get('waiting'), 'total': len(sc), 'lines': rows}


@tool
def update_script(job_id: str, edits: list[dict]) -> dict:
    """Sửa kịch bản ở bước chờ duyệt. edits: [{"index": 3, "voiceover": "...", "subtitle": "...", "excluded": false}, …]
    — chỉ trường có mặt mới đổi. Bỏ 1 câu: ở bước 'script' đặt voiceover = "" ; ở bước 'preview' đặt excluded = true.
    Ở bước 'preview', câu đổi lời được đọc lại giọng tự động. Lưu bản nháp (giao diện thấy ngay); approve_step để đi tiếp."""
    j = _call('GET', f'/api/jobs/{job_id}')
    if not j.get('waiting'):
        raise RuntimeError('Job không ở bước chờ duyệt — chỉ sửa được khi wait_for_job báo "waiting".')
    sc = [dict(s) for s in _scenes_of(j)]
    n = 0
    for e in edits:
        i = int(e.get('index', -1))
        if not 0 <= i < len(sc):
            raise RuntimeError(f'index {i} ngoài khoảng 0…{len(sc) - 1}')
        for k in ('voiceover', 'subtitle', 'excluded'):
            if k in e:
                sc[i][k] = e[k]
        n += 1
    mixer = (j.get('draft') or {}).get('mixer')
    _call('PUT', f'/api/jobs/{job_id}/draft', json={'scenes': sc, 'mixer': mixer})
    return {'ok': True, 'edited': n}


@tool
def approve_step(job_id: str) -> dict:
    """Duyệt bước đang chờ (kịch bản / nghe lại) với nội dung hiện tại (kể cả phần đã sửa bằng update_script) → job chạy tiếp."""
    j = _call('GET', f'/api/jobs/{job_id}')
    if not j.get('waiting'):
        raise RuntimeError('Job không ở bước chờ duyệt.')
    body: dict[str, Any] = {'confirmed': True, 'scenes': _scenes_of(j)}
    if (j.get('draft') or {}).get('mixer'):
        body['mixer'] = j['draft']['mixer']
    _call('POST', f'/api/jobs/{job_id}/confirm', json=body)
    return {'ok': True, 'approved': j.get('waiting')}


@tool
def export_subtitles(job_id: str, fmt: str = 'srt') -> dict:
    """Xuất phụ đề của job Dịch phụ đề (mode 'vietsub') đã xong. fmt: 'srt' | 'vtt' | 'ass' | 'bilingual' (song ngữ).
    Job Review / Reup: file .srt có sẵn trong get_outputs."""
    return _call('POST', f'/api/jobs/{job_id}/export-subs', json={'fmt': fmt})


@tool
def app_status() -> dict:
    """Thông tin máy & app: phiên bản, GPU, ổ đĩa xuất còn trống, tài khoản AI đã đăng nhập, thư mục xuất mặc định."""
    st = _call('GET', '/api/system')
    s = _call('GET', '/api/settings')
    return {'system': st, 'output_dir': s.get('output_dir'), 'default_voice': s.get('voice')}


# ───────────────────────── chạy ─────────────────────────
def run_stdio():
    """python main.py --mcp-stdio — cho client chỉ chạy lệnh (Claude Desktop). App ReviewFilm phải đang mở."""
    mcp.run(transport='stdio')
