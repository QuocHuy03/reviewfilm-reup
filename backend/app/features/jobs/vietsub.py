"""Dịch phụ đề (Vietsub): Whisper → dịch tiếng Việt → ghép phụ đề Việt lên video, GIỮ tiếng gốc (không lồng tiếng).

Dựng một lượt cho cả phim: làm mờ chữ Trung (AI quét, theo hình gốc) → cắt khung / co về khung xuất → che phụ đề cũ
(vùng che % khung xuất) → phụ đề Việt (nằm giữa vùng che nếu bật). Xuất video + SRT gốc + SRT tiếng Việt.
"""
import os
import re
import shutil
import subprocess
import time

from core.video_editor import enable_expr

from .pipelines import (_audio_codec, _base_name, _force_style, _is_url, _layout, _out_dir, _rechunk, _resolve_video,
                        _sub_style, _transcribe, _translate, _unique_path, _workspace, _write_srt, clean_regions,
                        sub_cover_center)


def _ass_time(t):
    t = max(0.0, float(t))
    return f'{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}'


def _box_chain(cur, box, w, h, style='erase', spans=None, tag='bx'):
    """Che 1 vùng (% khung xuất [x, y, rộng, cao]).
    style 'erase': delogo lấp bằng điểm ảnh xung quanh + mờ nhẹ cho mượt viền (tự nhiên, gần như không thấy);
    'blur': làm mờ mạnh. spans = [(a, b)] giây → chỉ che lúc đó (None = suốt video)."""
    try:
        (x, y, bw, bh) = [max(0.0, min(100.0, float(v))) / 100.0 for v in box[:4]]
    except (TypeError, ValueError):
        return ('', cur)
    (px, py) = (max(1, int(x * w)), max(1, int(y * h)))
    (pw, ph) = (min(int((x + bw) * w), w - 2) - px, min(int((y + bh) * h), h - 2) - py)
    (pw, ph) = (pw // 2 * 2, ph // 2 * 2)
    if pw < 8 or ph < 8:
        return ('', cur)
    en = ''
    if spans is not None:
        merged = []
        for (a, b) in sorted(spans):
            if merged and a <= merged[-1][1] + 0.6:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        if not merged:
            return ('', cur)
        en = ":enable='" + enable_expr(merged) + "'"   # gộp cho đủ ngắn (phim dài hàng trăm câu → ffmpeg hết bộ nhớ)
    parts = []
    if style == 'erase':
        parts.append(f'[{cur}]delogo=x={px}:y={py}:w={pw}:h={ph}{en}[{tag}d]')
        cur = f'{tag}d'
    sigma = max(4, round(ph * 0.09)) if style == 'erase' else 20     # 'blur' = y như Review phim (gblur 20); 'erase' vùng lớn mờ thêm cho hết vệt sọc
    parts.append(f'[{cur}]split[{tag}a][{tag}b]')
    parts.append(f'[{tag}b]crop={pw}:{ph}:{px}:{py},gblur=sigma={sigma}:steps=3[{tag}c]')
    parts.append(f'[{tag}a][{tag}c]overlay={px}:{py}{en}[{tag}o]')
    return (';'.join(parts), f'{tag}o')


def _write_ass(path, cues, style, w, h, center_y=None):
    """File ASS có PlayRes = đúng khung video → toạ độ / cỡ chữ chính xác (SRT qua ffmpeg dùng lưới 384x288, lệch dọc ~2%).
    center_y (0-1): tâm phụ đề đặt đúng chỗ (giữa vùng che); không có → đáy giữa, cách đáy theo kiểu phụ đề."""
    kv = dict(p.split('=', 1) for p in _force_style(style).split(','))
    k = h / 288.0                                # kiểu chữ của app tính theo lưới 288 dòng
    fields = ['Default', kv['FontName'], str(round(float(kv['FontSize']) * k)), kv['PrimaryColour'], kv['PrimaryColour'],
              kv['OutlineColour'], kv['BackColour'], '-1', '0', '0', '0', '100', '100', '0', '0', kv['BorderStyle'],
              str(round(float(kv['Outline']) * k, 1)), '0', '2', str(round(w * 0.06)), str(round(w * 0.06)),
              str(round(float(kv['MarginV']) * k)), '1']
    pos = '{\\an5\\pos(%d,%d)}' % (w // 2, round(center_y * h)) if center_y is not None else ''
    lines = ['[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {w}', f'PlayResY: {h}', 'WrapStyle: 0', 'ScaledBorderAndShadow: yes', '',
             '[V4+ Styles]',
             'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, '
             'StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
             'Style: ' + ','.join(fields), '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    for c in cues:
        text = str(c['text']).replace('\r', '').replace('{', '(').replace('}', ')').replace('\n', '\\N')
        lines.append(f"Dialogue: 0,{_ass_time(c['start'])},{_ass_time(c['end'])},Default,,0,0,0,,{pos}{text}")
    with open(path, 'w', encoding='utf-8-sig') as f:
        f.write('\n'.join(lines) + '\n')


def _text_widths(cues, style, w, h):
    """Bề ngang (px) từng câu phụ đề khi vẽ bằng kiểu chữ ASS ở khung w x h (dòng dài nhất; libass tự xuống dòng ở ~88% khung)."""
    from PIL import ImageFont
    from core.fonts import find_font_file
    from core.video_editor import _find_font, _find_system_font
    kv = dict(p.split('=', 1) for p in _force_style(style).split(','))
    size = max(8, round(float(kv['FontSize']) * h / 288.0))
    path = find_font_file(kv['FontName']) or _find_system_font(kv['FontName']) or _find_font()
    try:
        font = ImageFont.truetype(path, size)
    except Exception:
        font = None
    out = []
    for c in cues:
        lines = str(c['text']).split('\n') or ['']
        tw = max((font.getlength(ln) if font else len(ln) * size * 0.55) for ln in lines) * 1.06   # chữ đậm (Bold) rộng hơn ~6%
        out.append(min(w * 0.88, tw))
    return (out, size)


def _src_to_out(cfg, sw, sh, w, h):
    """Hàm đổi toạ độ hình GỐC (0-1) → px khung xuất (tính cả cắt khung + co / viền đen như lúc dựng) → (fx, fy)."""
    (cx, cy, cw, ch) = (0.0, 0.0, 1.0, 1.0)
    fill = False
    box = cfg.get('crop_box') or []
    try:
        if len(box) >= 4:
            (bx, by, bw, bh) = [max(0.0, min(100.0, float(v))) / 100.0 for v in box[:4]]
            if bw >= 0.05 and bh >= 0.05 and not (bw > 0.995 and bh > 0.995):
                (cx, cy, cw, ch, fill) = (bx, by, min(bw, 1 - bx), min(bh, 1 - by), bool(cfg.get('crop_fill', True)))
    except (TypeError, ValueError):
        pass
    k = (max if fill else min)(w / (cw * sw), h / (ch * sh))
    (ox, oy) = ((w - cw * sw * k) / 2, (h - ch * sh * k) / 2)
    return (lambda x: ox + (x - cx) * sw * k, lambda y: oy + (y - cy) * sh * k)


def _fit_cover_chain(cur, band, cues, style, w, h, old=None):
    """Khung mờ ngang VỪA THEO CHỮ: dải dọc = vùng che phụ đề (y, cao), bề ngang = câu Việt đang hiện + lề,
    nới cho trùm cả chữ Trung cũ cùng lúc (old = [(x1px, x2px, t0, t1)] trong dải) → không lòi chữ cũ hai bên.
    Làm mờ cả dải 1 lần rồi cắt theo từng khoảng ngang (gom câu cùng khoảng) → ít bước lọc, cả phim vẫn dựng nhanh."""
    try:
        (_, y, _, bh) = [max(0.0, min(100.0, float(v))) / 100.0 for v in band[:4]]
    except (TypeError, ValueError):
        return ('', cur)
    bh = min(bh, 1.0 - y)
    if bh < 0.01 or not cues:
        return ('', cur)
    (py, ph) = (int(y * h) // 2 * 2, max(2, int(bh * h) // 2 * 2))
    py = min(py, h - ph)
    (widths, size) = _text_widths(cues, style, w, h)
    pad = round(size * 0.9)
    step = 24                                   # gom theo bậc 24px → vài chục nhóm cho cả phim
    groups = {}
    for (c, tw) in zip(cues, widths):
        (a, b) = (float(c['start']), float(c['end']))
        (left, right) = (w / 2 - tw / 2 - pad, w / 2 + tw / 2 + pad)
        for (x1, x2, t0, t1) in old or []:
            if t0 <= b + 0.5 and t1 >= a - 0.5:  # chữ cũ hiện cùng lúc (nới 0.5s vì quét theo mẫu từng giây)
                (left, right) = (min(left, x1 - pad / 2), max(right, x2 + pad / 2))
        if right - left < step * 4:
            (left, right) = (w / 2 - step * 2, w / 2 + step * 2)
        x = max(0, int(left // step * step) // 2 * 2)
        bw = min(w - x, int(-(-(right - x) // step) * step) // 2 * 2)
        groups.setdefault((x, bw), []).append((a, b))
    parts = [f'[{cur}]split[fta][ftb]', f'[ftb]crop={w}:{ph}:0:{py},gblur=sigma=24:steps=3,split={len(groups)}' +
             ''.join(f'[ftg{i}]' for i in range(len(groups)))]
    prev = 'fta'
    for (i, ((x, bw), spans)) in enumerate(sorted(groups.items())):
        merged = []
        for (a, b) in sorted(spans):
            if merged and a <= merged[-1][1] + 0.05:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        en = enable_expr(merged)                 # gộp cho đủ ngắn (phim dài hàng trăm câu → ffmpeg hết bộ nhớ)
        parts.append(f'[ftg{i}]crop={bw}:{ph}:{x}:0[ftc{i}]')
        parts.append(f"[{prev}][ftc{i}]overlay={x}:{py}:enable='{en}'[fto{i}]")
        prev = f'fto{i}'
    return (';'.join(parts), prev)


def _cover_chain(cur, boxes, w, h):
    """Vùng che (% khung xuất [x, y, rộng, cao]) → làm mờ mạnh, suốt video."""
    parts = []
    for (i, b) in enumerate(boxes or []):
        try:
            (x, y, bw, bh) = [max(0.0, min(100.0, float(v))) / 100.0 for v in b[:4]]
        except (TypeError, ValueError):
            continue
        (bw, bh) = (min(bw, 1.0 - x), min(bh, 1.0 - y))
        if bw < 0.01 or bh < 0.01:
            continue
        (px, py, pw, ph) = [max(2, int(v) // 2 * 2) for v in (x * w, y * h, bw * w, bh * h)]
        (px, py) = (min(px, w - pw), min(py, h - ph))
        parts.append(f'[{cur}]split[cva{i}][cvb{i}]')
        parts.append(f'[cvb{i}]crop={pw}:{ph}:{px}:{py},gblur=sigma=24:steps=3[cvc{i}]')
        parts.append(f'[cva{i}][cvc{i}]overlay={px}:{py}[cv{i}]')
        cur = f'cv{i}'
    return (';'.join(parts), cur)


# ───────────────────────────── Lồng tiếng giữ đúng thời gian video (không kéo giãn hình) ─────────────────────────────
DUB_RATE = 44100
# Giọng đọc luôn ở TỐC ĐỘ GỐC (không tua nhanh / chậm). Câu dài hơn chỗ trống → AI viết gọn lại; còn dư thì lấn khoảng lặng sau.


def _sentences(cues):
    """Gộp các dòng phụ đề liền nhau thành câu để đọc liền mạch (giọng không ngắt giữa câu)."""
    units = []
    for c in cues:
        text = str(c['text']).replace('\n', ' ').strip()
        if not text:
            continue
        u = units[-1] if units else None
        if (u and float(c['start']) - u['end'] < 0.35 and float(c['end']) - u['start'] < 9.0
                and not u['text'].rstrip().endswith(('.', '!', '?', '…', '。', '！', '？'))):
            u['text'] += ' ' + text
            u['end'] = float(c['end'])
        else:
            units.append({'start': float(c['start']), 'end': float(c['end']), 'text': text})
    return units


def _pitch(samples, sr=16000):
    """Cao độ trung vị (Hz) của đoạn tiếng nói — tự tương quan từng khung 40ms, chỉ khung đủ to & có chu kỳ rõ."""
    import numpy as np
    x = samples.astype(np.float32)
    (n, hop) = (int(0.04 * sr), int(0.02 * sr))
    (lo, hi) = (int(sr / 400), int(sr / 70))           # 70–400 Hz
    if len(x) < n:
        return 0.0
    rms_all = np.sqrt(np.mean(x ** 2)) + 1e-9
    f0 = []
    for i in range(0, len(x) - n, hop):
        fr = x[i:i + n] - x[i:i + n].mean()
        if np.sqrt(np.mean(fr ** 2)) < 0.6 * rms_all:    # khung lặng / nhỏ → bỏ
            continue
        ac = np.correlate(fr, fr, 'full')[n - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        k = int(np.argmax(seg))
        if seg[k] / ac[0] > 0.45:                       # có chu kỳ rõ (giọng nói, không phải tiếng ồn)
            f0.append(sr / (k + lo))
    return float(np.median(f0)) if len(f0) >= 5 else 0.0


def _genders(video, units, log):
    """Nam / nữ cho từng câu theo cao độ giọng gốc (>165Hz ≈ nữ). Câu không rõ → theo câu trước (đỡ đổi giọng lung tung)."""
    import numpy as np
    from core.utils import FFMPEG_EXE, _HIDE
    out, prev = [], 'male'
    for u in units:
        r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-ss', f"{u['start']:.2f}", '-t', f"{max(0.3, u['end'] - u['start']):.2f}",
                            '-i', video, '-vn', '-ac', '1', '-ar', '16000', '-af', 'highpass=f=70,lowpass=f=1000',
                            '-f', 's16le', '-'], capture_output=True, creationflags=_HIDE)
        hz = _pitch(np.frombuffer(r.stdout, '<i2')) if r.returncode == 0 else 0.0
        g = prev if hz <= 0 else ('female' if hz > 165 else 'male')
        out.append(g)
        prev = g
    log(f"   Nhận giọng gốc: {out.count('male')} câu nam · {out.count('female')} câu nữ", 'info')
    return out


SHORTEN_PROMPT = """Bạn biên tập lời lồng tiếng phim (tiếng Việt). Mỗi câu dưới đây đọc LÂU HƠN thời gian nhân vật nói câu gốc.
Viết lại TỪNG câu ngắn gọn hơn, KHÔNG vượt quá "toi_da_tu" từ (đếm theo chữ), giữ nguyên ý chính, tên riêng, giọng điệu
tự nhiên như người Việt nói; bỏ từ đệm, ý phụ. Không thêm ý mới, không markdown.
TUYỆT ĐỐI không đổi / bịa nghĩa: câu nào không thể gọn hơn mà vẫn đúng nghĩa thì giữ nguyên câu đó.
Chỉ trả về JSON đúng dạng: {{"cau": [{{"i": <số>, "loi": "<câu mới>"}}]}}

{rows}"""


def _shorten(units, todo, wps, log):
    """AI viết gọn các câu lồng tiếng dài hơn chỗ trống. todo = {chỉ số câu: số giây có}. wps = từ/giây của giọng đang dùng.
    Gửi từng gói 20 câu (gói lớn dễ bị cắt cụt), đọc JSON dễ dãi, gói lỗi thử lại 1 lần. → {chỉ số: câu mới}."""
    import json as _json
    from core import web_llm
    from .postedit import _extract_json, word_count
    if not web_llm.available():
        log('   [WARN] Chưa đăng nhập ChatGPT / Gemini (Cài đặt → Tài khoản AI) — không rút gọn được câu dài, giọng sẽ lấn thời gian', 'warn')
        return {}
    keys = sorted(todo)
    out = {}
    for k in range(0, len(keys), 20):
        batch = keys[k:k + 20]
        rows = [{'i': i, 'toi_da_tu': max(3, int(todo[i] * wps * 1.1)), 'cau': units[i]['text']} for i in batch]
        for attempt in range(2):
            raw = web_llm.chat(SHORTEN_PROMPT.format(rows=_json.dumps(rows, ensure_ascii=False, indent=0)), log)
            data = _extract_json(raw) or {}
            items = data.get('cau') or data.get('items') or data.get('edits') or (data if isinstance(data, list) else [])
            (got, parsed) = (0, 0)
            for it in items if isinstance(items, list) else []:
                try:
                    i = int(it.get('i', it.get('id')))
                except (TypeError, ValueError, AttributeError):
                    continue
                t = str(it.get('loi') or it.get('text') or it.get('voiceover') or '').strip()
                parsed += bool(t)
                if i in todo and t and word_count(t) < word_count(units[i]['text']):
                    out[i] = t
                    got += 1
            if got:
                break
            if parsed:                           # đọc được nhưng câu đã gọn hết mức (câu quá ngắn so với chỗ trống) → thôi
                break
            log(f'   [WARN] AI trả kết quả không đọc được (gói {k // 20 + 1}, lần {attempt + 1}): {str(raw)[:160]!r}', 'warn')
    return out


def _orig_texts(srt_path, units):
    """Lời gốc (tiếng Trung) ứng với từng câu lồng tiếng — ghép các dòng SRT gốc trùng thời gian."""
    if not srt_path or not os.path.isfile(srt_path):
        return [''] * len(units)
    from app.srt_utils import parse_srt
    with open(srt_path, encoding='utf-8-sig', errors='replace') as f:
        cues = parse_srt(f.read())
    out = []
    for u in units:
        hit = [c['text'] for c in cues if min(float(c['end']), u['end']) - max(float(c['start']), u['start']) > 0.15]
        out.append(' '.join(hit).replace('\n', ' ').strip())
    return out


def _pcm(path, tempo):
    """File giọng → PCM s16 mono 44.1kHz (đã đổi tốc độ)."""
    from core.utils import FFMPEG_EXE, _HIDE
    af = f'atempo={tempo:.4f},' if tempo > 1.001 else ''
    r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-i', path, '-af', f'{af}aresample={DUB_RATE}', '-ac', '1', '-f', 's16le', '-'],
                       capture_output=True, creationflags=_HIDE)
    return r.stdout if r.returncode == 0 else b''


# Căn thời gian lồng tiếng theo VideoLingo: câu được mượn khoảng lặng phía sau tối đa TOLERANCE giây; dài hơn khung thì
# đọc nhanh nhẹ tối đa MAX_SPEED (atempo, giữ cao độ giọng); tua tối đa vẫn không vừa mới nhờ AI viết gọn.
TOLERANCE = 1.5
MAX_SPEED = 1.2
MIN_DUR = 2.5                                    # câu ngắn hơn (cùng người, sát nhau) gộp với câu sau
SPEED_MARGIN = 0.1


def _trim_voice(path):
    """Cắt im lặng 2 đầu file giọng (Edge chèn ~0.25s đầu + ~1s cuối mỗi câu → câu nào cũng 'dài hơn chỗ trống').
    → (file wav đã cắt, thời lượng giây) hoặc (path cũ, 0) nếu lỗi."""
    from core.utils import FFMPEG_EXE, _HIDE
    out = os.path.splitext(path)[0] + '_trim.wav'
    sr = 'silenceremove=start_periods=1:start_threshold=-45dB:start_silence={}'
    af = f'{sr.format(0.04)},areverse,{sr.format(0.12)},areverse,aresample={DUB_RATE}'
    r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-y', '-i', path, '-af', af, '-ac', '1', '-c:a', 'pcm_s16le', out],
                       capture_output=True, creationflags=_HIDE)
    try:
        dur = (os.path.getsize(out) - 44) / 2 / DUB_RATE if r.returncode == 0 else 0
    except OSError:
        dur = 0
    return (out, dur) if dur > 0.1 else (path, 0)


def _cast_voices(res, units, voices, overrides):
    """Giọng từng nhân vật: NGƯỜI DÙNG chọn (bước duyệt theo vai / Lồng tiếng lại); chưa chọn thì nhân vật nam đọc giọng nam,
    nữ đọc giọng nữ đã chọn ở tab Lồng tiếng — không tự gán giọng khác. overrides = {mã nhân vật | tên: giọng}.
    → [{'id', 'name', 'gender', 'count', 'voice', 'samples'}] theo số câu giảm dần."""
    labels = res['labels']
    cast = []
    for (k, s) in sorted(res['speakers'].items(), key=lambda kv: -int(kv[1].get('count') or 0)):
        g = 'female' if s.get('gender') == 'female' else 'male'
        name = str(s.get('name') or f'NV{k + 1}')
        voice = overrides.get(str(k)) or overrides.get(name) or voices[g]
        lines = sorted((units[i]['text'] for (i, lab) in enumerate(labels) if lab == k), key=len, reverse=True)
        cast.append({'id': k, 'name': name, 'gender': g, 'count': sum(1 for lab in labels if lab == k),
                     'voice': voice, 'samples': [t[:90] for t in lines[:2]]})
    return cast


def _start_separation(job, cfg, video, temp_dir):
    """Lồng tiếng + tách giọng: chạy tách giọng ở luồng nền ngay từ đầu (song song Whisper / AI phân vai / dịch / xoá chữ)."""
    import threading
    if not (cfg.get('dub_voice') and cfg.get('dub_separate', True) and _audio_codec(video)):
        return None
    box = {'pct': 0}

    def run():
        from core import vocal_sep

        def prog(p):
            if p >= box['pct'] + 25 or p == 100:
                box['pct'] = p
                job.log(f'   Tách giọng gốc (chạy nền): {p}%', 'step')
        try:
            box['res'] = vocal_sep.separate(video, os.path.join(temp_dir, 'sep'), job.log, prog, lambda: job.cancelled)
        except Exception as e:
            box['err'] = e
    box['thread'] = threading.Thread(target=run, daemon=True)
    box['thread'].start()
    return box


def _finish_separation(job, box):
    """Đợi tách giọng xong → (vocals.wav, music.wav) hoặc (None, None) (lỗi / không bật → hạ nhỏ cả tiếng gốc như cũ)."""
    if not box:
        return (None, None)
    if box['thread'].is_alive():
        job.set_progress(55, 'Đợi tách giọng gốc')
        box['thread'].join()
    job.check()
    if box.get('err'):
        job.log(f"   [WARN] Tách giọng lỗi ({str(box['err'])[:120]}) — hạ nhỏ cả tiếng gốc như cũ", 'warn')
    return box.get('res') or (None, None)


def _norm_res(res):
    """Phân vai lưu trong job (JSON → mã nhân vật thành chuỗi) → dạng dùng được; thiếu → None."""
    if not res or not res.get('speakers') or not res.get('labels'):
        return None
    return {'labels': [int(k) for k in res['labels']], 'speakers': {int(k): v for (k, v) in res['speakers'].items()}}


def _analyze_cast(job, video, units, orig_texts, vi_texts=None):
    """Ai nói câu nào: nghe giọng (CAM++) rồi AI đọc kịch bản (xưng hô, tên gọi, mạch hội thoại) sửa chỗ nghe nhầm
    và đánh dấu dòng không phải lời thoại. → {'labels', 'speakers'} hoặc None."""
    from core import speakers
    res = None
    try:
        job.set_progress(job.progress, 'Phân tích nhân vật (ai nói câu nào)')
        res = speakers.analyze(video, [(u['start'], u['end']) for u in units], job.log)
    except Exception as e:
        job.log(f'   [WARN] Phân tích nhân vật lỗi ({str(e)[:120]}) — chỉ dựa vào kịch bản', 'warn')
    try:
        job.set_progress(job.progress, 'AI phân vai theo kịch bản')
        ai = speakers.refine_with_script(vi_texts, orig_texts, res, job.log)
        if ai:
            res = ai
    except Exception as e:
        job.log(f'   [WARN] AI phân vai lỗi ({str(e)[:120]}) — dùng kết quả nghe giọng', 'warn')
    return res


def _band_or_corner(box, band, corner_x=0.3, corner_y=0.22):
    """Vùng chữ (0-1 hình gốc) thuộc dải phụ đề cũ, hoặc nằm ở 1 trong 4 góc (logo / watermark)."""
    if band and min(box[3], band[3]) - max(box[1], band[1]) > 0.3 * (box[3] - box[1]):
        return True
    (cx, cy) = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    return (cx < corner_x or cx > 1 - corner_x) and (cy < corner_y or cy > 1 - corner_y)


def _subtitle_spans(job, cfg, video):
    """Lúc nào trên hình có phụ đề Trung (dải phụ đề, quét chữ cả phim) → [(giây bắt đầu, giây kết thúc)], hoặc None nếu không
    quét được / video không có phụ đề cứng. Dùng cùng khoảng quét với bước che chữ → bước đó dùng lại cache, không quét 2 lần."""
    from core import text_cover
    if not text_cover.available():
        return None
    interval = float(cfg.get('text_scan_interval') or 2.0)
    job.set_progress(job.progress, 'Quét phụ đề Trung trên video')
    try:
        regions = clean_regions(text_cover.scan(video, None, interval, job.log, should_stop=lambda: job.cancelled))
    except Exception as e:
        job.log(f'   [WARN] Quét phụ đề lỗi ({str(e)[:100]}) — lồng tiếng mọi câu thoại', 'warn')
        return None
    job.check()
    band = text_cover.subtitle_band(regions) if regions else None
    if not band:
        job.log('   Video không có phụ đề cứng — lồng tiếng mọi câu thoại', 'info')
        return None
    spans = []
    pad = interval * 0.6                         # 2 lần quét cách nhau `interval` giây → câu có thể bắt đầu / hết giữa 2 lần
    for r in regions:
        b = r['box']
        if min(b[3], band[3]) - max(b[1], band[1]) > 0.3 * (b[3] - b[1]):
            spans.append([max(0.0, float(r['t_start']) - pad), float(r['t_end']) + pad])
    spans.sort()
    merged = []
    for (a, b) in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def _mark_unsubtitled(job, units, res, spans):
    """Chỉ lồng tiếng câu CÓ phụ đề Trung trên hình (lời nhân vật); câu không có (đám đông, lời nền, nhạc) → vai -1, giữ tiếng gốc.
    Ít câu có phụ đề quá (< 30%) thì coi như phụ đề không đủ tin → không lọc. → res (tạo mới nếu chưa có phân vai)."""
    has = []
    for u in units:
        ov = sum(max(0.0, min(u['end'], b) - max(u['start'], a)) for (a, b) in spans)
        has.append(ov >= min(0.3, 0.3 * (u['end'] - u['start'])))
    if sum(has) < 0.3 * len(units):
        job.log(f'   Chỉ {sum(has)}/{len(units)} câu có phụ đề Trung trên hình — không lọc, lồng tiếng mọi câu thoại', 'info')
        return res
    n_skip = sum(1 for h in has if not h)
    if not n_skip:
        job.log(f'   Mọi câu thoại ({len(units)}) đều có phụ đề Trung trên hình — lồng tiếng tất cả', 'info')
        return res
    if res is None:
        res = {'labels': [0] * len(units), 'speakers': {0: {'name': 'Lời thoại', 'gender': 'male', 'count': len(units), 'minor': False}}}
    res = {'labels': [lab if h else -1 for (lab, h) in zip(res['labels'], has)], 'speakers': res['speakers']}
    job.log(f'   {n_skip} câu không có phụ đề Trung trên hình (đám đông, lời nền, nhạc…) — không lồng tiếng, giữ tiếng gốc', 'info')
    return res


def _hardsub_segments(job, cfg, video):
    """Video có phụ đề cứng tiếng Trung → đọc thẳng phụ đề trên hình làm lời gốc: đúng nội dung (không nghe nhầm) và đúng lúc
    từng câu hiện / tắt (người làm phim căn tay theo miệng nhân vật — chuẩn hơn Whisper). → [{'start', 'end', 'text'}] hoặc None."""
    from core import hardsub, text_cover
    from core.utils import get_video_duration
    if not text_cover.available():
        return None
    interval = float(cfg.get('text_scan_interval') or 2.0)
    job.set_progress(10, 'Tìm phụ đề cứng trên video')
    job.log('[2] Tìm phụ đề cứng tiếng Trung trên video (có thì lấy làm lời gốc — chuẩn thời gian hơn nhận dạng giọng)...', 'info')
    try:
        regions = clean_regions(text_cover.scan(video, None, interval, job.log, should_stop=lambda: job.cancelled))
        job.check()
        band = text_cover.subtitle_band(regions) if regions else None
        if not band:
            job.log('   Không thấy phụ đề cứng — nhận dạng giọng nói bằng Whisper', 'info')
            return None
        segs = hardsub.extract(video, band, 0.2, job.log, should_stop=lambda: job.cancelled,
                               progress=lambda p: job.set_progress(12 + int(p * 0.25), f'Đọc phụ đề cứng · {p}%'))
    except Exception as e:
        if job.cancelled:
            raise
        job.log(f'   [WARN] Đọc phụ đề cứng lỗi ({str(e)[:120]}) — dùng Whisper', 'warn')
        return None
    job.check()
    dur = get_video_duration(video) or 60
    if len(segs) < max(5, dur / 60 * 3):          # quá ít câu so với độ dài phim → phụ đề không đủ tin
        job.log(f'   Chỉ đọc được {len(segs)} câu phụ đề cứng — dùng Whisper cho chắc', 'warn')
        return None
    return segs


def _translate_for_dub(job, cfg, video, transcript, lang, layout):
    """Quy trình lồng tiếng: SRT gốc → phân vai (ai nói, nam / nữ, dòng không phải thoại) → AI dịch theo đúng người nói,
    mỗi câu vừa thời gian câu gốc. Câu lồng tiếng = từng đoạn Whisper (thời gian nói thật), phụ đề chia dòng riêng.
    → (cues phụ đề, plan) hoặc ([], None) khi không dịch theo vai được (chưa đăng nhập AI…) → dùng cách dịch thường."""
    from app.srt_utils import scenes_to_cues
    from core import dub_translate, web_llm
    if not web_llm.available():
        job.log('   Chưa đăng nhập ChatGPT / Gemini — dịch thường (không dịch theo vai)', 'warn')
        return ([], None)
    src = [sg for sg in transcript['segments'] if str(sg.get('text') or '').strip()]
    try:                                         # đoạn dài gộp lời 2 người (đối đáp nhanh) → tách ở chỗ đổi giọng
        from core import speakers
        src = speakers.split_turns(video, src, job.log)
    except Exception as e:
        job.log(f'   [WARN] Tách lượt lời lỗi ({str(e)[:100]}) — bỏ qua', 'warn')
    units = [{'start': float(sg['start']), 'end': float(sg['end']), 'text': str(sg['text']).strip()} for sg in src]
    if not units:
        return ([], None)
    job.set_progress(30, 'Phân tích nhân vật trên SRT gốc')
    job.log(f'[3] Phân tích nhân vật trên SRT gốc ({len(units)} câu) — ai nói câu nào, trước khi dịch...', 'info')
    res = _analyze_cast(job, video, units, [u['text'] for u in units])
    job.check()
    if transcript.get('hardsub') and res and -1 in res['labels']:
        # lời gốc lấy từ phụ đề cứng → câu nào có phụ đề cũng phải lồng tiếng: dòng AI cho là "không phải thoại"
        # (lời dẫn, chữ chèn, câu cảm thán…) gán vai "Người dẫn" — đổi vai / giọng được ở bước duyệt
        nid = max(res['speakers']) + 1 if res['speakers'] else 0
        n_x = res['labels'].count(-1)
        res = {'labels': [nid if k == -1 else k for k in res['labels']],
               'speakers': {**res['speakers'], nid: {'name': 'Người dẫn', 'gender': 'male', 'count': n_x, 'minor': False}}}
        job.log(f'   {n_x} dòng phụ đề không rõ nhân vật — vẫn lồng tiếng (vai "Người dẫn", đổi được ở bước duyệt)', 'info')
    if cfg.get('dub_only_subbed', True) and not transcript.get('hardsub'):   # chỉ lồng câu có phụ đề Trung trên hình
        spans = _subtitle_spans(job, cfg, video)
        if spans:
            res = _mark_unsubtitled(job, units, res, spans)
    (units, src, res) = _merge_utterances(units, src, res)
    for u in units:
        u['orig'] = u['text']                    # lời gốc (hiện ở bước duyệt kịch bản theo vai)
    job.log(f'   Gộp mẩu câu liền nhau của cùng người nói → {len(units)} câu thoại', 'step')
    job.set_progress(42, 'AI dịch theo vai')
    job.log('[4] AI dịch theo vai: đúng xưng hô từng nhân vật, mỗi câu vừa thời gian câu gốc...', 'info')
    vi = dub_translate.translate(units, res, job.log, cfg.get('film_context') or '')
    if not vi or sum(1 for t in vi if t) < len(units) * 0.8:
        job.log('   [WARN] AI dịch theo vai không đủ câu — dùng cách dịch thường', 'warn')
        return ([], None)
    miss = [i for (i, t) in enumerate(vi) if not t]
    if miss:                                     # vài câu AI bỏ sót → dịch Google cho đủ
        job.log(f'   {len(miss)} câu AI bỏ sót — dịch bổ sung', 'info')
        try:
            extra = _translate(job, [src[i] for i in miss], lang, {**cfg, 'ai_translate': False}, video) or []
        except Exception as e:
            job.log(f'   [WARN] Dịch bổ sung lỗi ({str(e)[:100]}) — giữ câu gốc', 'warn')
            extra = []
        for (i, sc) in zip(miss, extra):
            vi[i] = (sc.get('subtitle') or sc.get('voiceover') or '').strip() or units[i]['text']
    for (u, t) in zip(units, vi):
        u['text'] = t or u['text']
    # ước lượng độ dài TRƯỚC khi tạo giọng (như estimate_duration của VideoLingo): câu dịch quá khung kể cả khi đọc nhanh 1.2×
    # → AI viết gọn ngay, khỏi phải tạo giọng → rút gọn → tạo lại (chậm, dễ mất ý)
    try:
        from .postedit import word_count
        rooms = []
        for (i, u) in enumerate(units):
            nxt = units[i + 1]['start'] if i + 1 < len(units) else u['end'] + TOLERANCE
            rooms.append(max(0.4, u['end'] - u['start'] + min(max(0.0, nxt - u['end']), TOLERANCE)))
        # thời lượng đọc ước tính = số từ / tốc độ đọc + ~0.2s đệm đầu/cuối câu; so đúng điều kiện bước lồng tiếng
        # (khung − 0.1s) × 1.2 — câu ngắn hay lọt nếu bỏ qua phần đệm
        over = {i: rooms[i] for (i, u) in enumerate(units)
                if (res is None or res['labels'][i] != -1)
                and word_count(u['text']) / dub_translate.WPS + 0.2 > (rooms[i] - SPEED_MARGIN) * MAX_SPEED}
        if over:
            job.log(f'   {len(over)} câu dịch dài quá khung thời gian — AI viết gọn trước khi tạo giọng', 'info')
            for (i, t) in _shorten(units, over, dub_translate.WPS, job.log).items():
                units[i]['text'] = t
    except Exception as e:
        job.log(f'   [WARN] Ước lượng độ dài lỗi ({str(e)[:100]}) — bỏ qua', 'warn')
    scenes = [{'clip_start': u['start'], 'clip_end': u['end'], 'subtitle': u['text'], 'voiceover': u['text']} for u in units]
    cues = _rechunk(scenes_to_cues(scenes, 'subtitle'), layout)
    if res:
        job.result['dub_cast'] = res
    return (cues, {'units': units, 'res': res})


def _merge_utterances(units, src, res, gap=0.4, max_len=8.0):
    """Whisper hay cắt 1 câu thành nhiều mẩu ngắn → gộp mẩu liền nhau (cách < gap giây) của CÙNG người nói thành 1 câu
    (≤ max_len giây) để dịch & đọc liền mạch; câu vẫn bắt đầu đúng lúc nhân vật mở miệng. → (units, src, res) đã gộp."""
    labels = res['labels'] if res else [0] * len(units)
    (out_u, out_s, out_l) = ([], [], [])
    for (u, sg, lab) in zip(units, src, labels):
        # cùng người nói, sát nhau (< gap giây) — hoặc câu trước quá ngắn (< MIN_DUR, 2 câu bắt đầu cách nhau < MIN_DUR, như
        # min_subtitle_duration của VideoLingo) thì gộp làm 1 câu đọc liền
        prev = out_u[-1] if out_u else None
        short = prev and prev['end'] - prev['start'] < MIN_DUR and u['start'] - prev['start'] < MIN_DUR and u['start'] - prev['end'] < 1.0
        if (prev and lab == out_l[-1] and lab != -1 and (u['start'] - prev['end'] < gap or short)
                and u['end'] - prev['start'] <= max_len):
            out_u[-1]['end'] = u['end']
            out_u[-1]['text'] += '，' + u['text']
            out_s[-1] = {**out_s[-1], 'end': sg.get('end'), 'text': out_s[-1]['text'] + '，' + str(sg['text']).strip()}
        else:
            out_u.append(dict(u))
            out_s.append({**sg, 'text': str(sg['text']).strip()})
            out_l.append(lab)
    return (out_u, out_s, {'labels': out_l, 'speakers': res['speakers']} if res else None)


def _remap_plan(plan, cues):
    """Bản dịch đã sửa tay → câu lồng tiếng lấy theo bản sửa (gộp dòng thành câu), vai từng câu = vai của câu cũ trùng thời gian nhất."""
    units = _sentences(cues)
    old = plan['units']
    res = _norm_res(plan.get('res'))
    if not res or len(res['labels']) != len(old) or not old:
        return {'units': units, 'res': None}
    labels = []
    for u in units:
        best = max(range(len(old)), key=lambda j: min(u['end'], old[j]['end']) - max(u['start'], old[j]['start']))
        labels.append(res['labels'][best])
    return {'units': units, 'res': {'labels': labels, 'speakers': res['speakers']}}


def _dub(job, cfg, cues, temp_dir, video_dur, video='', plan=None, orig_level=None):
    """Đọc từng câu đúng lúc nhân vật nói (tốc độ gốc, không tua); câu dài hơn chỗ trống → AI rút gọn rồi đọc lại.
    plan = {'units', 'res'} từ bước phân vai + dịch theo vai (câu = đoạn Whisper, thời gian nói thật).
    → (voice.wav, env.wav): track giọng Việt + đường cong âm lượng tiếng gốc (hạ nhỏ khi có lời Việt, mượt)."""
    import wave
    from .pipelines import synthesize
    res = None
    if plan and plan.get('units'):
        units = [dict(u) for u in plan['units']]
        res = _norm_res(plan.get('res'))
        if res and len(res['labels']) != len(units):
            res = None
    else:
        units = _sentences(cues)
    if not units:
        return (None, None)
    job.set_progress(56, 'Lồng tiếng Việt')
    # nam 1 giọng, nữ 1 giọng: chưa chọn giọng nữ → Nữ Bắc; "giọng nam" lỡ là giọng nữ (mặc định dùng chung với Review) → Nam Bắc
    by_gender = bool(cfg.get('dub_by_gender') and video)
    (v_male, v_female) = (cfg.get('voice', '') or 'Edge TTS — Nam Bắc (miễn phí)', cfg.get('voice_female', '') or 'Edge TTS — Nữ Bắc (miễn phí)')
    if by_gender and ('Nữ' in v_male or v_male == v_female):
        job.log(f'   Giọng cho nhân vật nam đang là giọng nữ ({v_male}) — dùng Edge Nam Bắc cho nhân vật nam', 'warn')
        v_male = 'Edge TTS — Nam Bắc (miễn phí)'
    voices = {'male': v_male, 'female': v_female if by_gender else v_male}
    job.log(f"[5] Lồng tiếng: {len(units)} câu · " + (f"nam: {voices['male']} · nữ: {voices['female']}" if by_gender else f"giọng {voices['male']}"), 'info')
    genders = ['male'] * len(units)
    reuse = _norm_res(cfg.get('cast_reuse'))
    if res:
        job.log(f"   Vai từng câu theo phân tích SRT gốc: {len(res['speakers'])} nhân vật", 'info')
    elif reuse and len(reuse['labels']) == len(units):
        # lồng tiếng lại (đổi giọng nhân vật) — giữ nguyên phân vai lần trước, không phân tích lại
        res = reuse
        job.log(f"   Dùng lại phân vai lần trước: {len(res['speakers'])} nhân vật", 'info')
    elif by_gender:
        orig = _orig_texts(job.result.get('original_srt') or cfg.get('orig_srt_path') or '', units)
        res = _analyze_cast(job, video, units, orig, [u['text'] for u in units])
        if not res:
            genders = _genders(video, units, job.log)
    uvoice = [voices[g] for g in genders]        # giọng đọc từng câu; None = không đọc
    if res and by_gender:
        genders = [res['speakers'][k]['gender'] if k in res['speakers'] else 'male' for k in res['labels']]
        cast = _cast_voices(res, units, voices, cfg.get('char_voices') or {})
        vmap = {c['id']: c['voice'] for c in cast}
        uvoice = [vmap.get(k) for k in res['labels']]   # None = không phải lời thoại (nhạc, tiếng động…) → không lồng tiếng
        job.log('   Giọng từng nhân vật: ' + ' · '.join(f"{c['name']} → {c['voice']}" for c in cast[:8])
                + (f' · +{len(cast) - 8} nhân vật' if len(cast) > 8 else ''), 'info')
        job.result['cast'] = cast
        job.result['cast_labels'] = res['labels']
    elif res:                                    # 1 giọng cho cả phim — vẫn bỏ dòng không phải lời thoại
        uvoice = [voices['male'] if k in res['speakers'] else None for k in res['labels']]
    uvoice = [v if str(u.get('text') or '').strip() else None for (u, v) in zip(units, uvoice)]
    batch = [0]

    def voice_all(idx):
        # mỗi lượt tạo giọng một thư mục riêng — file đặt tên theo thứ tự trong lượt (vo_0000…), dùng chung sẽ ghi đè câu khác
        from core.tts_engine import generate_vieneu_cast, vieneu_voice_key
        from .pipelines import _voice_id

        def put(sub, out):
            for s in out:
                j = int(s.get('_original_index', -1))
                if 0 <= j < len(sub) and s.get('tts_path'):
                    (p, d) = _trim_voice(s['tts_path'])
                    units[sub[j]].update(path=p, dur=d or float(s.get('tts_duration') or 0))
            job.check()

        def scene(i, **kw):
            return {'voiceover': units[i]['text'], 'subtitle': units[i]['text'], 'clip_start': units[i]['start'], 'clip_end': units[i]['end'], **kw}
        # nhiều nhân vật giọng VieNeu → đọc chung 1 lần nạp model (mỗi giọng nạp lại ~13s)
        vn = [i for i in idx if uvoice[i] and vieneu_voice_key(_voice_id(uvoice[i]))]
        if len({uvoice[i] for i in vn}) > 1:
            batch[0] += 1
            put(vn, generate_vieneu_cast([scene(i, _vn_voice=vieneu_voice_key(_voice_id(uvoice[i])), _original_index=j) for (j, i) in enumerate(vn)],
                                         os.path.join(temp_dir, 'dub', f'b{batch[0]}'), job.log))
            idx = [i for i in idx if i not in set(vn)]
        for v in dict.fromkeys(uvoice[i] for i in idx if uvoice[i]):
            sub = [i for i in idx if uvoice[i] == v]
            batch[0] += 1
            put(sub, synthesize([scene(i) for i in sub], v, os.path.join(temp_dir, 'dub', f'b{batch[0]}'), job.log,
                                strict=cfg.get('strict_voice', False)) or [])

    def slot(i):
        # khung của câu = thời lượng câu + mượn khoảng lặng phía sau tối đa TOLERANCE giây (như VideoLingo)
        nxt = units[i + 1]['start'] if i + 1 < len(units) else (video_dur or units[i]['end'] + 5)
        gap = max(0.0, nxt - units[i]['end'])
        return max(0.3, units[i]['end'] - units[i]['start'] + min(gap, TOLERANCE))

    voice_all(list(range(len(units))))
    for _ in range(2):                           # Edge hay lỗi lẻ tẻ khi gửi dồn → đọc lại riêng các câu còn thiếu
        miss = [i for (i, u) in enumerate(units) if not u.get('path') and uvoice[i]]
        if not miss:
            break
        job.log(f'   {len(miss)} câu chưa tạo được giọng — thử đọc lại...')
        time.sleep(8)                            # Edge hay chặn tạm khi gửi dồn — đợi chút cho hồi
        voice_all(miss)
    # VieNeu vẫn lỗi vài câu → đọc bằng Edge đúng giới tính nhân vật (thà khác giọng chút còn hơn mất tiếng)
    from core.tts_engine import vieneu_voice_key
    from .pipelines import _voice_id
    def swap_voice(still, pick, why):
        # giọng nào còn câu lỗi → đổi giọng đó cho MỌI câu đang dùng nó (cả câu đã đọc được) rồi đọc lại:
        # mỗi nhân vật luôn 1 giọng cả phim, không để câu Edge câu VieNeu lẫn lộn
        bad = {}
        for i in still:
            bad.setdefault(uvoice[i], genders[i])
        idx = [i for (i, v) in enumerate(uvoice) if v in bad]
        job.log(f'   {len(still)} câu {why} — đổi hẳn giọng cho {len(idx)} câu cùng giọng (giữ 1 nhân vật 1 giọng)', 'warn')
        repl = {v: pick(g) for (v, g) in bad.items()}
        for i in idx:
            uvoice[i] = repl[uvoice[i]]
            units[i].pop('path', None)
            units[i].pop('dur', None)
        voice_all(idx)
    still = [i for (i, u) in enumerate(units) if not u.get('path') and uvoice[i] and vieneu_voice_key(_voice_id(uvoice[i]))]
    if still:
        swap_voice(still, lambda g: 'Edge TTS — Nữ Bắc (miễn phí)' if g == 'female' else 'Edge TTS — Nam Bắc (miễn phí)', 'VieNeu lỗi')
    # ngược lại: Edge / dịch vụ online lỗi (bị chặn tạm "No audio was received") → đọc bằng VieNeu (offline) cùng giới tính
    still = [i for (i, u) in enumerate(units) if not u.get('path') and uvoice[i] and not vieneu_voice_key(_voice_id(uvoice[i]))]
    if still:
        try:
            from core import vieneu_setup
            has_vn = vieneu_setup.installed()
        except Exception:
            has_vn = False
        if has_vn:
            from app import constants as C
            swap_voice(still, lambda g: C.VIENEU_CAST_FEMALE[0] if g == 'female' else C.VIENEU_CAST_MALE[0], 'giọng online lỗi (đọc bằng VieNeu offline)')
    # Câu dài hơn chỗ trống (đọc ở tốc độ gốc) → AI viết gọn cho vừa rồi đọc lại; 2 lượt (cần tài khoản AI)
    from .postedit import word_count
    for rnd in range(3):
        # chỉ câu tua tối đa (MAX_SPEED) vẫn không vừa khung mới nhờ AI viết gọn — giữ nghĩa bản dịch nhiều nhất
        long_ = {i: slot(i) for (i, u) in enumerate(units)
                 if uvoice[i] and u.get('dur', 0) > (slot(i) - SPEED_MARGIN) * MAX_SPEED * (1.0, 1.03, 1.06)[rnd]}
        if not long_:
            break
        # tốc độ đọc THẬT của từng giọng (từ/giây) — số từ tối đa mỗi câu tính theo đó
        wps = {}
        for v in set(filter(None, uvoice)):
            r = sorted(word_count(u['text']) / u['dur'] for (i, u) in enumerate(units)
                       if uvoice[i] == v and u.get('dur', 0) >= 1.0 and word_count(u['text']) >= 3)
            wps[v] = r[len(r) // 2] if r else 3.5
        job.log(f'   {len(long_)} câu dài hơn chỗ trống — AI rút gọn (lượt {rnd + 1}, giọng đọc ~{max(wps.values()):.1f} từ/giây)...', 'info')
        new = {}
        for v in set(filter(None, uvoice)):
            part = {i: s for (i, s) in long_.items() if uvoice[i] == v}
            if part:
                try:
                    new.update(_shorten(units, part, wps[v], job.log))
                except Exception as e:
                    job.log(f'   [WARN] AI rút gọn lỗi ({str(e)[:100]}) — câu dài sẽ lấn sang khoảng lặng sau', 'warn')
        if not new:
            break
        for (i, t) in new.items():
            units[i]['text'] = t
        voice_all(sorted(new))
        job.log(f'   Đã rút gọn & đọc lại {len(new)} câu', 'ok')
    missing = sum(1 for (i, u) in enumerate(units) if not u.get('path') and uvoice[i])
    if missing:
        job.log(f'   [WARN] {missing} câu không tạo được giọng — để trống', 'warn')

    # Tốc độ đọc CỐ ĐỊNH cho cả video: mỗi câu cần nhanh bao nhiêu để vừa khung → lấy mức đa số câu cần (75%), trong 1.0–1.2×.
    # Mọi câu đọc cùng 1 nhịp (tua từng câu một khác nhau nghe giọng "nhảy"); câu còn dài thì lấn khoảng lặng sau.
    needs = sorted(u['dur'] / max(0.3, slot(i) - SPEED_MARGIN) for (i, u) in enumerate(units) if uvoice[i] and u.get('dur', 0) > 0)
    steady = min(MAX_SPEED, max(1.0, needs[int(len(needs) * 0.75)] if needs else 1.0))
    steady = round(steady, 2)

    # Xếp lịch: không chồng tiếng — câu trễ thì đọc ngay sau câu trước; ghi track giọng tuần tự (ít RAM cả phim dài)
    voice_wav = os.path.join(temp_dir, 'voice.wav')
    spans = []
    (spilled, max_lag) = (0, 0.0)
    with wave.open(voice_wav, 'wb') as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(DUB_RATE)
        (written, prev_end) = (0, 0.0)
        for (i, u) in enumerate(units):
            if not u.get('path') or u.get('dur', 0) <= 0:
                continue
            t = max(u['start'], prev_end + 0.05)
            # khung còn lại tính từ lúc thật sự bắt đầu đọc (câu trước lấn thì khung ngắn lại) — trừ hao 0.1s như VideoLingo
            avail = max(0.3, u['start'] + slot(i) - t - SPEED_MARGIN)
            tempo = steady                           # cùng 1 tốc độ cho mọi câu
            spilled += u['dur'] / tempo > avail + 0.05
            max_lag = max(max_lag, t - u['start'])
            pcm = _pcm(u['path'], tempo)
            if not pcm:
                continue
            start_sample = int(t * DUB_RATE)
            if start_sample > written:
                wv.writeframes(b'\x00\x00' * (start_sample - written))
                written = start_sample
            wv.writeframes(pcm)
            written += len(pcm) // 2
            prev_end = written / DUB_RATE
            spans.append((t, prev_end))
    job.log((f'   Tốc độ đọc cố định cả video: {steady:.2f}× (mọi câu cùng nhịp, tối đa {MAX_SPEED}×)' if steady > 1.001 else '   Mọi câu đọc ở tốc độ gốc')
            + (f' · {spilled} câu lấn sang khoảng lặng sau, trễ nhất {max_lag:.1f}s' if spilled else ' · mọi câu vừa khung thời gian'), 'info')

    # Đường cong âm lượng tiếng gốc (1000 điểm/giây): hạ xuống mức đã chọn khi có lời Việt, lên xuống mượt
    level = max(0.0, min(1.0, float(cfg.get('dub_orig_volume', 20)) / 100.0)) if orig_level is None else orig_level
    env_rate = 1000
    n = int((video_dur or (spans[-1][1] if spans else 1)) * env_rate) + env_rate
    import numpy as np
    gain = np.ones(n, dtype=np.float32)
    (att, rel) = (int(0.15 * env_rate), int(0.35 * env_rate))
    for (a, b) in spans:
        (i0, i1) = (max(0, int(a * env_rate) - att), min(n, int(b * env_rate) + rel))
        if i1 - i0 < 2:                          # câu lấn quá cuối video → bỏ qua (bị cắt theo độ dài video)
            continue
        seg = np.full(i1 - i0, level, dtype=np.float32)
        ramp_in = min(att, len(seg))
        seg[:ramp_in] = np.minimum(seg[:ramp_in], np.linspace(1.0, level, ramp_in, dtype=np.float32))
        ramp_out = min(rel, len(seg))
        if ramp_out:
            seg[-ramp_out:] = np.linspace(level, 1.0, ramp_out, dtype=np.float32)
        gain[i0:i1] = np.minimum(gain[i0:i1], seg)
    env_wav = os.path.join(temp_dir, 'env.wav')
    with wave.open(env_wav, 'wb') as we:
        we.setnchannels(1)
        we.setsampwidth(2)
        we.setframerate(env_rate)
        we.writeframes((gain * 32767).astype('<i2').tobytes())
    nskip = sum(1 for v in uvoice if not v)
    job.log(f'   Lồng tiếng xong: {len(spans)}/{len(units) - nskip} câu thoại' + (f' (bỏ {nskip} dòng nhạc / tiếng động, giữ tiếng gốc)' if nskip else '') + (' · giọng gốc tắt khi có lời Việt, giữ nhạc nền' if orig_level is not None else f' · tiếng gốc hạ còn {int(level * 100)}% khi có lời Việt'), 'ok')
    return (voice_wav, env_wav)


def _out_to_src(cfg, sw, sh, w, h):
    """Ngược với _src_to_out: px khung xuất → toạ độ hình GỐC (0-1)."""
    (fx, fy) = _src_to_out(cfg, sw, sh, w, h)
    (ax, bx) = (fx(0.0), fx(1.0) - fx(0.0))
    (ay, by) = (fy(0.0), fy(1.0) - fy(0.0))
    return (lambda X: (X - ax) / bx if bx else 0.0, lambda Y: (Y - ay) / by if by else 0.0)


def auto_cover_box(cfg, regions, video, w, h):
    """Vùng chữ đã quét → dải phụ đề cũ → vùng che [x, y, rộng, cao] theo % KHUNG XUẤT (tính cả cắt khung / viền đen)."""
    from core import text_cover
    band = text_cover.subtitle_band(regions)
    (sw, sh, _) = text_cover_probe(video)
    if not band or not sw or not sh:
        return None
    (fx, fy) = _src_to_out(cfg, sw, sh, w, h)
    (x1, x2) = (max(0.0, fx(band[0])), min(float(w), fx(band[2])))
    (y1, y2) = (max(0.0, fy(band[1])), min(float(h), fy(band[3])))
    if x2 - x1 < w * 0.05 or y2 - y1 < h * 0.02:
        return None
    return [round(x1 / w * 100, 1), round(y1 / h * 100, 1), round((x2 - x1) / w * 100, 1), round((y2 - y1) / h * 100, 1)]


def text_cover_probe(video):
    from core import text_cover
    try:
        return text_cover._probe(video)
    except Exception:
        return (0, 0, 0.0)


def run_vietsub_pipeline(job):
    from app.srt_utils import scenes_to_cues, segments_to_cues
    from core.utils import FFMPEG_EXE, get_video_duration
    from core.video_editor import _crop_prefix, _src_text_blur_chain
    cfg = job.config
    out_dir = _out_dir(cfg)
    layout = _layout(cfg)
    (w, h) = [int(v) for v in str(cfg.get('target_resolution') or '1920x1080').split('x')]
    with _workspace(job, out_dir) as temp_dir:
        video = _resolve_video(job, cfg['inp'], temp_dir)
        job.result['video_path'] = video
        base = _base_name(video)
        sep = _start_separation(job, cfg, video, temp_dir)   # tách giọng chạy nền song song (không phụ thuộc hình)
        reuse = cfg.get('vi_srt_path') or ''
        dub_plan = None                          # lồng tiếng: câu đọc (thời gian nói thật) + vai từng câu
        if reuse and os.path.isfile(reuse):
            # Lồng tiếng lại / dựng lại từ bản dịch đã có → bỏ qua Whisper + dịch
            from app.srt_utils import parse_srt
            with open(reuse, encoding='utf-8-sig', errors='replace') as f:
                cues = parse_srt(f.read())
            if not cues:
                raise RuntimeError('File SRT tiếng Việt rỗng hoặc sai định dạng.')
            if cfg.get('orig_srt_path') and os.path.isfile(cfg['orig_srt_path']):
                job.result['original_srt'] = cfg['orig_srt_path']
            job.log(f'[1] Dùng lại bản dịch {len(cues)} dòng — bỏ qua Whisper & dịch', 'info')
            (transcript, lang) = (None, 'reuse')
            dub_plan = cfg.get('dub_plan_reuse') or None
        else:
            segs = _hardsub_segments(job, cfg, video) if cfg.get('hardsub_source', True) else None
            if segs:
                transcript = {'language': 'zh', 'segments': segs, 'full_text': ' '.join(x['text'] for x in segs), 'hardsub': True}
                lang = 'zh'
                job.result['hardsub_source'] = True
            else:
                (transcript, lang) = _transcribe(job, video, temp_dir, cfg, beam=5, words=bool(cfg.get('dub_voice')))
            orig = _rechunk(segments_to_cues(transcript['segments']), layout)
            job.result['original_srt'] = _write_srt(os.path.join(out_dir, base + '_original.srt'), orig)
            job.log(f'   SRT gốc: {len(orig)} dòng', 'ok')
        job.check()

        # 1. Dịch — có lồng tiếng: phân vai trên SRT gốc TRƯỚC, rồi dịch theo đúng người nói & vừa thời gian câu gốc
        if lang not in ('reuse', 'vi'):
            dub_plan = None
            if cfg.get('dub_voice') and cfg.get('ai_translate', True):
                (cues, dub_plan) = _translate_for_dub(job, cfg, video, transcript, lang, layout)
        if lang == 'reuse' or dub_plan:
            pass
        elif lang == 'vi':
            job.log('   Video đã là tiếng Việt — giữ nguyên phụ đề', 'info')
            cues = orig
        else:
            job.set_progress(40, 'Dịch sang tiếng Việt')
            job.log('[3] Dịch phụ đề sang tiếng Việt...', 'info')
            scenes = _translate(job, transcript['segments'], lang, cfg, video)
            if not scenes:
                raise RuntimeError('Dịch phụ đề thất bại.')
            cues = _rechunk(scenes_to_cues(scenes, 'subtitle'), layout)
        if dub_plan and dub_plan.get('units'):
            # lồng tiếng: duyệt theo CÂU LỒNG TIẾNG (thời gian nói thật) kèm vai từng câu — sửa vai / lời rồi mới tạo giọng
            labs = (_norm_res(dub_plan.get('res')) or {}).get('labels') or [0] * len(dub_plan['units'])
            job.scenes = [{'clip_start': u['start'], 'clip_end': u['end'], 'voiceover': u['text'], 'subtitle': u['text'],
                           'orig_text': u.get('orig', ''), 'speaker_id': int(k)} for (u, k) in zip(dub_plan['units'], labs)]
        else:
            job.scenes = [{'clip_start': c['start'], 'clip_end': c['end'], 'voiceover': c['text'], 'subtitle': c['text']} for c in cues]

        # 2. Cho sửa bản dịch trước khi ghép (nếu bật)
        before = [(round(c['start'], 2), c['text']) for c in cues]
        if cfg.get('script_edit', True):
            job.log('   Chờ bạn xem & sửa bản dịch' + (' theo vai (đổi được nhân vật từng câu)' if dub_plan else '') + '...', 'info')
            reply = job.wait_for('script', 'Chờ sửa bản dịch')
            if reply.get('char_voices'):            # giọng từng nhân vật người dùng chọn ở bước duyệt theo vai
                cfg['char_voices'] = {str(k): str(v) for (k, v) in reply['char_voices'].items() if v}
            if reply.get('scenes') is not None:
                job.scenes = [s for s in reply['scenes'] if (s.get('subtitle') or s.get('voiceover') or '').strip()]
            if dub_plan and dub_plan.get('units') and all('speaker_id' in s for s in job.scenes):
                # câu đã duyệt = câu lồng tiếng (đúng vai người dùng chọn); phụ đề chia dòng lại từ đó
                from app.srt_utils import scenes_to_cues
                units = [{'start': float(s['clip_start']), 'end': float(s['clip_end']), 'text': (s.get('voiceover') or s.get('subtitle') or '').strip(),
                          'orig': s.get('orig_text', '')} for s in job.scenes]
                res0 = _norm_res(dub_plan.get('res'))
                labels = [int(s.get('speaker_id', 0)) for s in job.scenes]
                dub_plan = {'units': units, 'res': {'labels': labels, 'speakers': res0['speakers']} if res0 else None}
                if res0:
                    job.result['dub_cast'] = dub_plan['res']
                cues = _rechunk(scenes_to_cues([{**s, 'subtitle': u['text']} for (s, u) in zip(job.scenes, units)], 'subtitle'), layout)
                before = [(round(c['start'], 2), c['text']) for c in cues]
            else:
                cues = [{'start': float(s['clip_start']), 'end': float(s['clip_end']), 'text': (s.get('subtitle') or s.get('voiceover') or '').strip()}
                        for s in job.scenes]
        if not cues:
            raise RuntimeError('Không có dòng phụ đề nào để ghép.')
        if dub_plan and [(round(c['start'], 2), c['text']) for c in cues] != before:
            dub_plan = _remap_plan(dub_plan, cues)      # đã sửa bản dịch → câu lồng tiếng theo bản đã sửa, giữ vai từng câu
        if dub_plan:
            job.result['dub_units'] = [{'start': u['start'], 'end': u['end'], 'text': u['text'], 'orig': u.get('orig', '')} for u in dub_plan['units']]
        job.result['vi_srt'] = _write_srt(os.path.join(out_dir, base + '_vi.srt'), cues)
        job.log(f"   SRT tiếng Việt: {job.result['vi_srt']}", 'ok')
        job.check()

        # 3. Chữ Trung trên hình (AI quét cả phim). Khung mờ vừa theo chữ cũng cần biết chữ cũ rộng tới đâu → quét luôn
        dur = get_video_duration(video)
        regions = []
        scanned = False                         # đã quét được (kể cả không thấy chữ) → biết chắc chỗ nào / lúc nào có phụ đề cũ
        fit_mode = bool(cfg.get('remove_old_sub') and cfg.get('cover_fit_text', False) and cfg.get('burn_subtitles', True)
                        and sub_cover_center(cfg) is not None)
        auto_box = bool(cfg.get('remove_old_sub') and cfg.get('auto_sub_box', True))
        want_clean = (cfg.get('cover_style') or 'erase') == 'clean' and bool(cfg.get('remove_old_sub') or cfg.get('auto_cover_text'))
        if cfg.get('auto_cover_text') or fit_mode or auto_box or want_clean:
            from core import text_cover
            if text_cover.available():
                job.set_progress(55, 'Quét chữ Trung trên video')
                try:
                    regions = text_cover.scan(video, None, float(cfg.get('text_scan_interval') or 2.0), job.log,
                                              should_stop=lambda: job.cancelled)
                    scanned = not job.cancelled
                except Exception as e:
                    job.log(f'   [WARN] Quét chữ Trung lỗi ({str(e)[:120]}) — ghép không che', 'warn')
                job.check()
            else:
                job.log('   [WARN] Chưa cài bộ quét chữ (rapidocr) — bỏ qua tự che chữ Trung', 'warn')
        regions = clean_regions(regions)
        if auto_box and regions:
            # AI tự căn vùng che phụ đề theo chỗ phụ đề cũ THẬT (cả phim) → không lòi chữ cũ trên / dưới khung
            box = auto_cover_box(cfg, regions, video, w, h)
            if box:
                boxes = [b for b in (cfg.get('cover_boxes') or []) if isinstance(b, (list, tuple)) and len(b) >= 4]
                if boxes:
                    k = max(range(len(boxes)), key=lambda i: float(boxes[i][2]))
                    boxes[k] = box
                else:
                    boxes = [box]
                cfg['cover_boxes'] = boxes
                job.log(f'   AI căn vùng che phụ đề: ngang {box[0]:g}% · dọc {box[1]:g}% · rộng {box[2]:g}% · cao {box[3]:g}%', 'ok')

        # 3b. Xoá sạch nét chữ (kiểu đẹp nhất): lấp đúng điểm ảnh của chữ Trung từng khung → video trung gian sạch chữ
        render_src = video
        cleaned = False
        if want_clean and regions:
            from core import text_cover, text_inpaint
            band_src = text_cover.subtitle_band(regions)
            # chỉ xoá phụ đề cũ + chữ / logo ở 4 góc (watermark kênh, "nội dung hư cấu"…); chữ trong cảnh (biển hiệu, màn hình…)
            # giữ nguyên — trừ khi bật "che mọi chữ Trung"
            erase = list(regions) if cfg.get('auto_cover_text') else [r for r in regions if _band_or_corner(r['box'], band_src)]
            if len(erase) < len(regions):
                job.log(f'   Giữ nguyên {len(regions) - len(erase)} vùng chữ trong cảnh — chỉ xoá phụ đề cũ & chữ ở 4 góc', 'info')
            if band_src:
                # cả dải phụ đề trong suốt từng đoạn có phụ đề (nới 1 giây) — câu ngắn lọt giữa 2 lần quét vẫn được xoá
                spans = []
                for r in regions:
                    b = r['box']
                    if min(b[3], band_src[3]) - max(b[1], band_src[1]) > 0.3 * (b[3] - b[1]):
                        spans.append([float(r['t_start']) - 1.0, float(r['t_end']) + 1.0])
                spans.sort()
                merged = []
                for (a, b) in spans:
                    if merged and a <= merged[-1][1] + 1.5:
                        merged[-1][1] = max(merged[-1][1], b)
                    else:
                        merged.append([a, b])
                erase += [{'box': band_src, 't_start': max(0.0, a), 't_end': b} for (a, b) in merged]
            # vùng logo / watermark người dùng vẽ: xoá theo nét chữ suốt video (không xoá cả khung chữ nhật — lộ vệt)
            all_boxes = [bx for bx in (cfg.get('cover_boxes') or []) if isinstance(bx, (list, tuple)) and len(bx) >= 4] if cfg.get('remove_old_sub') else []
            if len(all_boxes) > 1:
                sub_box = max(all_boxes, key=lambda bx: float(bx[2]))
                (sw0, sh0, _) = text_cover_probe(video)
                if sw0 and sh0:
                    (gx, gy) = _out_to_src(cfg, sw0, sh0, w, h)
                    for bx in all_boxes:
                        if bx is sub_box:
                            continue
                        (X1, Y1) = (float(bx[0]) / 100 * w, float(bx[1]) / 100 * h)
                        (X2, Y2) = (X1 + float(bx[2]) / 100 * w, Y1 + float(bx[3]) / 100 * h)
                        src_box = [max(0.0, gx(X1)), max(0.0, gy(Y1)), min(1.0, gx(X2)), min(1.0, gy(Y2))]
                        if src_box[2] - src_box[0] > 0.01 and src_box[3] - src_box[1] > 0.01:
                            erase.append({'box': src_box, 't_start': 0.0, 't_end': (dur or 1e6) + 1})
            job.set_progress(58, 'Xoá sạch nét chữ')
            job.log(f'[4] Xoá sạch nét chữ Trung ({len(erase)} vùng) — xử lý từng khung hình...', 'info')
            clean_path = os.path.join(temp_dir, 'clean.mp4')
            res = text_inpaint.clean_video(video, erase, clean_path, job.log,
                                           progress=lambda p: job.set_progress(58 + int(6 * p), f'Xoá sạch nét chữ · {int(p * 100)}%'),
                                           should_stop=lambda: job.cancelled)
            job.check()
            if res:
                (render_src, cleaned) = (res, True)
            else:
                job.log('   [WARN] Xoá sạch không thành công — dùng kiểu xoá nhẹ', 'warn')

        # 4. Phụ đề: kiểu chữ của app, file ASS đúng khung video; nằm giữa vùng che → tâm phụ đề = tâm vùng che
        style = _sub_style(cfg)
        upper = style.get('sub_text_transform') == 'uppercase'
        sub_cues = [{**c, 'text': c['text'].upper() if upper else c['text']} for c in cues]
        _write_ass(os.path.join(temp_dir, 'subs.ass'), sub_cues, style, w, h, sub_cover_center(cfg))
        from core.fonts import render_font_files
        fonts_tmp = os.path.join(temp_dir, 'fonts')
        os.makedirs(fonts_tmp, exist_ok=True)
        for fp in render_font_files(style.get('sub_font_name', '')):
            shutil.copy2(fp, fonts_tmp)

        # 5. Một lượt dựng: xoá / mờ chữ Trung (hình gốc) → cắt / co về khung xuất → che phụ đề cũ → phụ đề Việt
        cstyle = cfg.get('cover_style') or 'erase'
        if cstyle == 'clean':
            cstyle = 'erase'                     # logo / phần còn lại (chưa xoá sạch được) dùng xoá nhẹ
        from core.video_editor import src_dims
        (src_chain, cur) = _src_text_blur_chain(regions if cfg.get('auto_cover_text') and not cleaned else [], 0.0, dur or 1e9,
                                                float(cfg.get('text_blur_strength') or 22),
                                                max_groups=16, max_spans=3000, merge_gap=0.8, style=cstyle, src_size=src_dims(video))
        crop = _crop_prefix(cfg.get('crop_box'), cfg.get('crop_fill', True), w, h)
        fit = crop or f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black'
        graph = [src_chain] if src_chain else []
        graph.append(f'[{cur}]{fit},setsar=1[vfit]')
        boxes = [b for b in (cfg.get('cover_boxes') or []) if isinstance(b, (list, tuple)) and len(b) >= 4] if cfg.get('remove_old_sub') else []
        cur = 'vfit'
        band_covered = False
        if boxes:
            band = max(boxes, key=lambda b: float(b[2]))         # vùng phụ đề = vùng rộng nhất; còn lại là logo…
            (by1, by2) = (float(band[1]) / 100 * h, (float(band[1]) + float(band[3])) / 100 * h)
            old = []                                             # chữ cũ trong dải phụ đề: (x1px, x2px, t0, t1) khung xuất
            (sw, sh, _) = text_cover_probe(video)
            if sw and sh:
                (fx, fy) = _src_to_out(cfg, sw, sh, w, h)
                for r in regions:
                    (x1, y1, x2, y2) = r['box']
                    if min(fy(y2), by2) - max(fy(y1), by1) > 0.3 * (fy(y2) - fy(y1)):
                        old.append((max(0.0, fx(x1)), min(float(w), fx(x2)), r['t_start'], r['t_end']))
            if cleaned:
                (chain, cur) = ('', cur)          # chữ cũ đã xoá sạch ở bước trên
            elif fit_mode:
                (chain, cur) = _fit_cover_chain(cur, band, sub_cues, style, w, h, old)
            elif scanned and not old:
                # quét cả phim mà không thấy phụ đề cứng → không che dải phụ đề (đỡ mờ vô ích)
                (chain, cur) = ('', cur)
                job.log('   Không thấy phụ đề cứng trong video — không che dải phụ đề', 'info')
            else:
                # 'blur' = y như Review phim: làm mờ cố định cả dải suốt video. Kiểu khác: chỉ che LÚC có phụ đề cũ (theo kết quả quét)
                spans = sorted((max(0.0, t0 - 0.3), t1 + 0.3) for (_, _, t0, t1) in old) if scanned and cstyle != 'blur' else None
                (chain, cur) = _box_chain(cur, band, w, h, cstyle, spans, 'sb')
            if chain:
                graph.append(chain)
                band_covered = True
            logos = [b for b in boxes if b is not band and not cleaned]
            if not cleaned and regions and sw and sh:
                # chữ / logo đứng yên ở 4 góc (watermark kênh, "nội dung hư cấu"…) quét được → tự che suốt video như vùng vẽ tay
                for r in regions:
                    (x1, y1, x2, y2) = r['box']
                    if (float(r['t_end']) - float(r['t_start'])) < 0.3 * (dur or 1) or not _band_or_corner(r['box'], None):
                        continue
                    (X1, Y1, X2, Y2) = (fx(x1), fy(y1), fx(x2), fy(y2))
                    (padx, pady) = ((X2 - X1) * 0.08 + 4, (Y2 - Y1) * 0.15 + 4)
                    (X1, Y1, X2, Y2) = (max(0.0, X1 - padx), max(0.0, Y1 - pady), min(float(w), X2 + padx), min(float(h), Y2 + pady))
                    if X2 - X1 > 8 and Y2 - Y1 > 8:
                        logos.append([X1 / w * 100, Y1 / h * 100, (X2 - X1) / w * 100, (Y2 - Y1) / h * 100])
            for (k, b) in enumerate(logos):     # logo / chữ cố định: che suốt video (đã xoá sạch thì thôi)
                (chain, cur) = _box_chain(cur, b, w, h, cstyle, None, f'lg{k}')
                if chain:
                    graph.append(chain)
        if cfg.get('burn_subtitles', True):
            graph.append(f'[{cur}]subtitles=subs.ass:fontsdir=fonts[vout]')
        else:
            graph.append(f'[{cur}]null[vout]')

        # 6. Lồng tiếng (tuỳ chọn): giọng Việt đúng lúc câu thoại + tiếng gốc tự hạ nhỏ khi có lời Việt
        has_audio = bool(_audio_codec(video))
        (voc_wav, music_wav) = _finish_separation(job, sep)
        (voice_wav, env_wav) = (_dub(job, cfg, cues, temp_dir, dur, video, plan=dub_plan, orig_level=0.0 if voc_wav else None)
                                if cfg.get('dub_voice') else (None, None))
        extra_in, amap = [], ['-map', '0:a?']
        if voice_wav:
            extra_in = ['-i', voice_wav, '-i', env_wav]
            st = 'aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo'
            # mono → stereo bằng pan (chép nguyên kênh): để ffmpeg tự đổi thì mỗi kênh còn 0.707 → tiếng gốc nhỏ đi 3dB
            mono = 'aresample=48000,pan=stereo|c0=c0|c1=c0,aformat=sample_fmts=fltp'
            if has_audio and voc_wav:
                # nhạc nền nguyên vẹn + giọng gốc (tắt khi có lời Việt, còn lại giữ: tiếng cười, bài hát…) + giọng Việt
                extra_in += ['-i', music_wav, '-i', voc_wav]
                graph.append(f'[3:a]{st}[am];[4:a]{st}[ao];[2:a]{mono}[ae];[ao][ae]amultiply[ad];[1:a]{mono},volume=0.9[av];'
                             '[am][ad][av]amix=inputs=3:normalize=0:duration=first,alimiter=limit=0.97:level=disabled[aout]')
            elif has_audio:
                graph.append(f'[0:a]{st}[ao];[2:a]{mono}[ae];[ao][ae]amultiply[ad];[1:a]{mono},volume=0.9[av];'
                             '[ad][av]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.97:level=disabled[aout]')
            else:
                graph.append(f'[1:a]{mono},alimiter=limit=0.97:level=disabled[aout]')
            amap = ['-map', '[aout]']
        fg = os.path.join(temp_dir, 'graph.txt')
        with open(fg, 'w', encoding='utf-8') as f:
            f.write(';'.join(graph))
        out_path = _unique_path(os.path.join(out_dir, base + ('_longtieng.mp4' if voice_wav else '_vietsub.mp4')))
        job.set_progress(65, 'Dựng video')
        job.log(f'[6] Dựng video: {len(cues)} dòng phụ đề' + (f', che {len(regions)} vùng chữ Trung' if regions and cfg.get('auto_cover_text') else '') +
                (', đã xoá sạch nét chữ cũ' if cleaned else ', che phụ đề cũ (' + ('xoá nhẹ' if cstyle == 'erase' else 'làm mờ') + ')' if band_covered else '') + (', lồng tiếng Việt' if voice_wav else ''), 'info')
        acodec = (['-c:a', 'copy'] if not voice_wav and _audio_codec(video) in ('aac', 'mp3') else ['-c:a', 'aac', '-b:a', '192k'])
        cmd = [FFMPEG_EXE, '-y', '-i', render_src, *extra_in, '-/filter_complex', 'graph.txt', '-map', '[vout]', *amap,
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', *acodec,
               '-movflags', '+faststart', out_path]
        _run_ffmpeg(job, cmd, temp_dir, dur)
        job.result['output_path'] = out_path
        job.log(f'[OK] Video: {out_path}', 'ok')
        job.set_progress(100, 'Hoàn thành')
        if _is_url(cfg['inp']):
            job.result['video_path'] = ''       # video tải về nằm trong thư mục tạm, sẽ bị dọn


def _run_ffmpeg(job, cmd, cwd, dur):
    """Chạy ffmpeg, cập nhật % theo thời gian đã dựng (65 → 99), huỷ được."""
    from core.utils import _HIDE, register_process, unregister_process
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                            encoding='utf-8', errors='replace', creationflags=_HIDE)
    register_process(proc)
    tail = []
    try:
        buf = ''
        while True:
            ch = proc.stderr.read(256)
            if not ch:
                break
            buf += ch
            lines = re.split(r'[\r\n]', buf)
            buf = lines.pop()
            for ln in lines:
                if not ln.strip():
                    continue
                tail = (tail + [ln])[-20:]
                m = re.search(r'time=(\d+):(\d+):(\d+(?:\.\d+)?)', ln)
                if m and dur:
                    t = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
                    job.set_progress(65 + int(34 * min(1.0, t / dur)), f'Ghép phụ đề vào video · {int(100 * min(1.0, t / dur))}%')
            if job.cancelled:
                proc.kill()
                break
        proc.wait()
    finally:
        unregister_process(proc)
    job.check()
    if proc.returncode != 0:
        raise RuntimeError('ffmpeg dựng video lỗi: ' + ' | '.join(tail[-4:])[-600:])
