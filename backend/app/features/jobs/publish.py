"""Bài đăng AI theo nền tảng: tiêu đề / mô tả / hashtag cho YouTube, Shorts, TikTok, Facebook, Instagram + thumbnail.

Chạy bằng tài khoản ChatGPT/Gemini đăng nhập trong app (core.web_llm). Kết quả lưu vào job.result['publish']
và xuất ra thư mục "<tên video>_dang-bai" cạnh video (mỗi nền tảng 1 file .txt + ảnh thumbnail).
"""
import json
import os
import re
import subprocess
import unicodedata
from datetime import datetime

from .postedit import _extract_json
from .qa import media_duration, video_speed

PLATFORMS = {
    'youtube': {'label': 'YouTube', 'title': 100, 'body': 5000},
    'shorts': {'label': 'YouTube Shorts', 'title': 100, 'body': 1000},
    'tiktok': {'label': 'TikTok', 'title': 0, 'body': 2200},
    'facebook': {'label': 'Facebook Reels', 'title': 0, 'body': 2000},
    'instagram': {'label': 'Instagram Reels', 'title': 0, 'body': 2200},
}
TONES = {
    'hap-dan': 'hấp dẫn, gợi tò mò nhưng không lừa người xem',
    'hai-huoc': 'hài hước, dí dỏm, gần gũi',
    'nghiem-tuc': 'nghiêm túc, chuyên nghiệp, phân tích',
    'cam-xuc': 'giàu cảm xúc, chạm vào cảm xúc người xem',
}

PROMPT = """# VAI TRÒ
Bạn là chuyên gia nội dung mạng xã hội cho kênh {kind} phim tiếng Việt. Viết bài đăng cho video dưới đây
theo đúng thói quen của TỪNG nền tảng. Giọng văn: {tone}.

# VIDEO
- Thời lượng: {duration}
- Phim: {film}
- Nội dung lời thuyết minh (tóm lược theo cảnh, kèm mốc thời gian trong video):
{scenes}

# YÊU CẦU TỪNG NỀN TẢNG
- youtube: "title" ≤ 70 ký tự, có từ khoá tên phim/thể loại, KHÔNG tiết lộ kết thúc, không viết hoa toàn bộ.
  "description": 2–3 đoạn ngắn (mở đầu gợi tò mò → tóm ý chính → kêu gọi like/sub), KHÔNG chứa mốc thời gian (app tự chèn).
  "chapters": 4–8 chương, mỗi chương {{"t": "<mốc lấy ĐÚNG từ danh sách trên>", "title": "<≤ 40 ký tự>"}}, chương đầu "00:00".
  "tags": 10–15 từ khoá tìm kiếm (không có #), tổng ≤ 450 ký tự. "hashtags": 3 hashtag.
- shorts: "title" ≤ 60 ký tự, cuốn ngay; "description" 1–2 câu; "hashtags" 3–5 (có #shorts).
- tiktok: "caption" 1–2 câu hook ≤ 150 ký tự; "hashtags" 4–6 (trộn hashtag rộng + ngách phim).
- facebook: "caption" 2–4 câu kể chuyện + câu hỏi gợi bình luận; "hashtags" 3–5.
- instagram: "caption" 1–3 câu + 1 dòng kêu gọi; "hashtags" 8–12.
- "thumbnail_texts": 3 phương án chữ trên ảnh thumbnail, mỗi phương án ≤ 5 từ, mạnh, dễ đọc.

# QUY TẮC
Tiếng Việt có dấu, tự nhiên. Hashtag viết liền không dấu, bắt đầu bằng #. Không bịa tình tiết không có trong nội dung.
Không markdown. Chỉ trả về JSON đúng mẫu:
{{"youtube": {{"title": "", "description": "", "chapters": [], "tags": [], "hashtags": []}},
 "shorts": {{"title": "", "description": "", "hashtags": []}},
 "tiktok": {{"caption": "", "hashtags": []}},
 "facebook": {{"caption": "", "hashtags": []}},
 "instagram": {{"caption": "", "hashtags": []}},
 "thumbnail_texts": []}}
{extra}"""


def _fmt(t):
    t = int(round(t))
    return f'{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}' if t >= 3600 else f'{t // 60:02d}:{t % 60:02d}'


def scene_marks(job):
    """Mốc thời gian (giây trên video xuất) bắt đầu từng cảnh — tính như video_editor dựng: intro + cộng dồn lời, chia tốc độ."""
    cfg = job.config
    t = media_duration(cfg.get('intro_path'))
    speed = video_speed(cfg)
    out = []
    for s in job.scenes:
        if s.get('excluded'):
            continue
        out.append((t / speed, (s.get('voiceover') or '').strip()))
        t += float(s.get('tts_duration') or 0)
    return out


def _hashtag(h):
    """'#Hoạt hình vui' → '#hoathinhvui' — hashtag không dấu, viết liền (tìm kiếm trên nền tảng chuẩn hơn)."""
    h = unicodedata.normalize('NFD', str(h or '').replace('đ', 'd').replace('Đ', 'D'))
    h = re.sub(r'[^0-9A-Za-z_]', '', ''.join(c for c in h if unicodedata.category(c) != 'Mn'))
    return f'#{h.lower()}' if h else ''


def _clean(data, marks, total):
    """Chuẩn hoá kết quả AI: cắt theo giới hạn ký tự, sửa hashtag, chỉ giữ chương có mốc hợp lệ."""
    valid = {_fmt(t) for (t, _) in marks}
    out = {}
    for (key, spec) in PLATFORMS.items():
        d = data.get(key) or {}
        item = {'hashtags': [x for x in dict.fromkeys(_hashtag(h) for h in d.get('hashtags') or []) if x]}
        if spec['title']:
            item['title'] = str(d.get('title') or '').strip()[:spec['title']]
        body = str(d.get('description') or d.get('caption') or '').strip()
        if key == 'youtube':
            chapters, last = [], -999
            for c in d.get('chapters') or []:
                t = str(c.get('t') or '').strip()
                if t not in valid:
                    continue
                sec = sum(int(x) * 60 ** k for (k, x) in enumerate(reversed(t.split(':'))))
                if sec - last >= 10 and (chapters or sec == 0):
                    chapters.append({'t': t, 'title': str(c.get('title') or '').strip()[:60]})
                    last = sec
            item['chapters'] = chapters if len(chapters) >= 3 and total >= 60 else []   # YouTube cần ≥3 chương, video ≥ 1 phút
            tags, n = [], 0
            for tg in d.get('tags') or []:
                tg = str(tg).strip().lstrip('#')
                if tg and n + len(tg) + 1 <= 480:
                    tags.append(tg)
                    n += len(tg) + 1
            item['tags'] = tags
        item['body'] = body
        item['text'] = compose(key, item)[:spec['body']]
        out[key] = item
    out['thumbnail_texts'] = [str(x).strip() for x in (data.get('thumbnail_texts') or []) if str(x).strip()][:3]
    return out


def compose(key, item):
    """Văn bản dán thẳng lên nền tảng (mô tả + chương + hashtag)."""
    parts = [item.get('body', '')]
    if item.get('chapters'):
        parts.append('\n'.join(f"{c['t']} {c['title']}" for c in item['chapters']))
    if item.get('hashtags'):
        parts.append(' '.join(item['hashtags']))
    return '\n\n'.join(p for p in parts if p).strip()


# ─────────────────────────────── thumbnail ───────────────────────────────

_BOLD_FONTS = [r'C:\Windows\Fonts\seguibl.ttf', r'C:\Windows\Fonts\ariblk.ttf', r'C:\Windows\Fonts\arialbd.ttf',
               r'C:\Windows\Fonts\segoeuib.ttf', r'C:\Windows\Fonts\arial.ttf']


def _frame(video, t, out, mirror=False):
    from core.utils import FFMPEG_EXE
    subprocess.run([FFMPEG_EXE, '-y', '-v', 'error', '-ss', f'{max(0.0, t):.2f}', '-i', video, '-frames:v', '1', '-q:v', '2']
                   + (['-vf', 'hflip'] if mirror else []) + [out],
                   capture_output=True, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return os.path.isfile(out)


def _score(path):
    """Ảnh nét, đủ sáng, nhiều màu điểm cao — tránh khung đen / mờ / chuyển cảnh."""
    from PIL import Image, ImageFilter, ImageStat
    im = Image.open(path).convert('RGB').resize((320, 180))
    edges = ImageStat.Stat(im.convert('L').filter(ImageFilter.FIND_EDGES)).mean[0]
    st = ImageStat.Stat(im)
    bright = sum(st.mean) / 3
    color = sum(st.stddev) / 3
    return edges * 2 + color - abs(bright - 125) * 0.6


def _wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ''
    for w in words:
        nxt = f'{cur} {w}'.strip()
        if draw.textlength(nxt, font=font) <= width or not cur:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def render_thumbnail(src, text, out, size=(1280, 720)):
    """Cắt khung đúng tỉ lệ, phủ nền tối phía dưới, chữ to viền đen — kiểu thumbnail kênh review."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(src).convert('RGB')
    W, H = size
    r = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    im = im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H))
    if text:
        shade = Image.new('L', (1, H))
        for y in range(H):
            shade.putpixel((0, y), int(max(0, (y - H * 0.45) / (H * 0.55)) * 200))
        im.paste(Image.new('RGB', (W, H), (0, 0, 0)), (0, 0), shade.resize((W, H)))
        draw = ImageDraw.Draw(im)
        font_path = next((f for f in _BOLD_FONTS if os.path.isfile(f)), None)
        fs = int(H * (0.13 if W > H else 0.075))
        while True:
            font = ImageFont.truetype(font_path, fs) if font_path else ImageFont.load_default()
            lines = _wrap(draw, text.upper(), font, W * 0.88)
            if len(lines) <= 2 or fs < 30:
                break
            fs = int(fs * 0.88)
        lh = int(fs * 1.12)
        y = H - int(H * 0.07) - lh * len(lines)
        for ln in lines:
            w = draw.textlength(ln, font=font)
            draw.text(((W - w) / 2, y), ln, font=font, fill=(255, 221, 0), stroke_width=max(3, fs // 14), stroke_fill=(0, 0, 0))
            y += lh
    im.save(out, quality=92)
    return out


def _candidates(job):
    """Khung ứng viên (video, giây): ưu tiên VIDEO GỐC ở giữa đoạn hình từng cảnh — hình sạch, không dính phụ đề / logo.
    Không có video gốc → lấy giữa từng cảnh trên video xuất."""
    from core.utils import get_video_duration
    src = job.result.get('video_path') or job.config.get('inp')
    scenes = [s for s in job.scenes if not s.get('excluded')]
    if src and os.path.isfile(src) and scenes:
        sdur = get_video_duration(src)
        out = []
        for s in scenes:
            a = float(s.get('clip_start') or 0)
            span = min(float(s.get('tts_duration') or 0) or 4, max(0.5, float(s.get('clip_end') or 0) - a))
            out.append((src, min(sdur - 0.5, a + span / 2)))
        return out, True
    video = job.result.get('output_path')
    dur = get_video_duration(video)
    marks = [t for (t, _) in scene_marks(job)] or [dur * k / 6 for k in range(1, 6)]
    return [(video, min(dur - 0.5, max(3.0, (t + (marks[k + 1] if k + 1 < len(marks) else dur)) / 2))) for (k, t) in enumerate(marks)], False


def make_thumbnails(job, out_dir, texts, log):
    video = job.result.get('output_path')
    if not video or not os.path.isfile(video):
        return []
    from core.utils import get_video_duration
    dur = max(1.0, get_video_duration(video))
    all_cands, from_source = _candidates(job)
    step = max(1, len(all_cands) // 12)
    cands = all_cands[::step][:12]
    mirror = from_source and bool(job.config.get('mirror_video'))
    tmp = os.path.join(out_dir, '_frames')
    os.makedirs(tmp, exist_ok=True)
    scored = []
    for (k, (vid, t)) in enumerate(cands):
        p = os.path.join(tmp, f'f{k}.jpg')
        if _frame(vid, t, p, mirror):
            try:
                scored.append((_score(p), t, p, vid))
            except Exception:
                pass
    scored.sort(reverse=True)
    picks = []
    span = get_video_duration(cands[0][0]) if cands else dur
    for (sc, t, p, vid) in scored:                 # 3 khung đẹp nhất, cách nhau ≥ 8% thời lượng
        if all(abs(t - q[1]) >= span * 0.08 for q in picks):
            picks.append((sc, t, p, vid))
        if len(picks) == 3:
            break
    vertical = str(job.config.get('target_resolution', '')).endswith('1920')
    out = []
    for (k, (_, t, p, vid)) in enumerate(picks):
        text = texts[k] if k < len(texts) else (texts[0] if texts else '')
        dst = os.path.join(out_dir, f'thumbnail_{k + 1}.jpg')
        render_thumbnail(p, text, dst, (1080, 1920) if vertical else (1280, 720))
        out.append({'path': dst, 'time': round(t, 2), 'src': vid, 'mirror': mirror, 'text': text})
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    log(f'   [Bài đăng] {len(out)} thumbnail {"9:16" if vertical else "16:9"}', 'info')
    return out


def redo_thumbnail(job, index, text, log=print):
    """Vẽ lại 1 thumbnail với chữ mới (lấy lại đúng khung hình đã chọn)."""
    pack = job.result.get('publish') or {}
    thumbs = pack.get('thumbnails') or []
    if not (0 <= index < len(thumbs)):
        raise ValueError('Sai số thứ tự thumbnail.')
    th = thumbs[index]
    tmp = os.path.join(pack['dir'], f'_frame_{index}.jpg')
    if not _frame(th.get('src') or job.result['output_path'], th['time'], tmp, th.get('mirror', False)):
        raise RuntimeError('Không lấy được khung hình từ video.')
    vertical = str(job.config.get('target_resolution', '')).endswith('1920')
    render_thumbnail(tmp, text.strip(), th['path'], (1080, 1920) if vertical else (1280, 720))
    os.remove(tmp)
    th['text'] = text.strip()
    th['v'] = th.get('v', 0) + 1          # đổi số → giao diện tải lại ảnh
    return pack


# ─────────────────────────────── chính ───────────────────────────────

def generate(job, platforms=None, tone='hap-dan', extra='', log=print):
    """→ job.result['publish']. RuntimeError nếu chưa đăng nhập AI / AI lỗi."""
    from core import web_llm
    if not web_llm.available():
        raise RuntimeError('Chưa đăng nhập tài khoản ChatGPT hoặc Gemini (Cài đặt → Tài khoản AI).')
    video = job.result.get('output_path')
    if not video or not os.path.isfile(video):
        raise RuntimeError('Job chưa có video để viết bài đăng.')
    platforms = [p for p in (platforms or list(PLATFORMS)) if p in PLATFORMS] or list(PLATFORMS)
    marks = scene_marks(job)
    total = media_duration(video)
    film = job.result.get('film') or {}
    film_txt = ', '.join(f'{k}: {v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}' for (k, v) in film.items()) or \
        (job.config.get('film_context') or 'không rõ — suy ra từ nội dung')
    scenes_txt = '\n'.join(f'  [{_fmt(t)}] {vo[:160]}' for (t, vo) in marks[:60])[:6000]
    extra_txt = f'\n# YÊU CẦU THÊM CỦA NGƯỜI DÙNG (ưu tiên)\n{extra.strip()}' if extra.strip() else ''
    prompt = PROMPT.format(kind='review' if job.kind == 'review' else 'dịch & reup', tone=TONES.get(tone, TONES['hap-dan']),
                           duration=_fmt(total), film=film_txt[:1500], scenes=scenes_txt, extra=extra_txt)
    log('[Bài đăng] AI đang viết tiêu đề, mô tả, hashtag theo từng nền tảng...', 'info')
    data = _extract_json(web_llm.chat(prompt, log))
    if not isinstance(data, dict):
        raise RuntimeError('AI không trả về bài đăng hợp lệ — thử lại.')
    posts = _clean(data, marks, total)

    out_dir = os.path.splitext(video)[0] + '_dang-bai'
    os.makedirs(out_dir, exist_ok=True)
    try:
        thumbs = make_thumbnails(job, out_dir, posts['thumbnail_texts'], log)
    except Exception as e:
        thumbs = []
        log(f'   [WARN] Không tạo được thumbnail: {e}', 'warn')
    for key in platforms:
        item = posts[key]
        with open(os.path.join(out_dir, f'{key}.txt'), 'w', encoding='utf-8') as f:
            if item.get('title'):
                f.write(f"TIÊU ĐỀ:\n{item['title']}\n\n")
            f.write(f"NỘI DUNG:\n{item['text']}\n")
            if item.get('tags'):
                f.write(f"\nTAGS:\n{', '.join(item['tags'])}\n")
    pack = {'platforms': {k: posts[k] for k in platforms}, 'thumbnail_texts': posts['thumbnail_texts'], 'thumbnails': thumbs,
            'dir': out_dir, 'tone': tone, 'at': datetime.now().isoformat(timespec='seconds')}
    with open(os.path.join(out_dir, 'bai-dang.json'), 'w', encoding='utf-8') as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)
    job.result['publish'] = pack
    log(f'   [Bài đăng] Xong {len(platforms)} nền tảng → {out_dir}', 'ok')
    return pack
