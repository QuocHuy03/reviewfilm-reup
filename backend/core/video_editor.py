
"""
Video editor: cat clip tu video goc theo timestamp script, ghep voiceover, burn sub.
Output: 1 video review hoan chinh.
"""
import hashlib
import json
import os
import functools
import subprocess
import shutil
import sys
import numpy as np
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.utils import FFMPEG_EXE, FFPROBE_EXE, get_video_duration, _HIDE, run_subprocess, run_subprocess_heartbeat
def _resolve_subtitle_text(scene, source_mode='prefer_voiceover'):
    subtitle = ((scene.get('subtitle', '') or '')).strip()
    voiceover = ((scene.get('voiceover', '') or '')).strip()
    if source_mode == 'subtitle':
        return subtitle or voiceover
    if source_mode == 'prefer_subtitle':
        return subtitle or voiceover
    if source_mode == 'voiceover':
        return voiceover or subtitle
    return voiceover or subtitle
def _generate_srt_file(scenes, srt_path, sub_max_chars_per_chunk=56, sub_max_lines=2, sub_source_mode='prefer_voiceover'):
    from app.srt_utils import fmt_ts as format_time_srt   # làm tròn ms trước khi tách giờ/phút/giây
    with open(srt_path, 'w', encoding='utf-8') as f:
        srt_idx = 1
        for scene in scenes:
            text = _resolve_subtitle_text(scene, sub_source_mode)
            if not text:
                continue
            start_s = scene.get('out_start', scene['clip_start'])
            end_s = scene.get('out_end', scene['clip_end'])
            total_dur = max(0.01, end_s - start_s)
            chunks = _split_subtitle_chunks(text, sub_max_chars_per_chunk, sub_max_lines)
            if not chunks:
                continue
            total_chars = sum((len(c) for c in chunks)) or 1
            t_cursor = start_s
            for chunk in chunks:
                chunk_dur = total_dur * (len(chunk) / total_chars)
                chunk_end = min(end_s, t_cursor + chunk_dur)
                wrapped = _wrap_lines(chunk, max(18, int(max(24, sub_max_chars_per_chunk) / max(1, sub_max_lines))), sub_max_lines)
                f.write(f'''{srt_idx}\n''')
                f.write(f'''{format_time_srt(t_cursor)} --> {format_time_srt(chunk_end)}\n''')
                f.write(f'''{wrapped}\n\n''')
                srt_idx += 1
                t_cursor = chunk_end
def _create_silent_wav(path, duration, sr=44100):
    num_samples = int(duration * sr)
    data = np.zeros(num_samples, dtype=np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
def _move_into(src, dst):
    """File cuối nằm trong thư mục tạm cùng ổ với thư mục xuất → chuyển (tức thì, không tốn gấp đôi ổ đĩa); khác ổ thì chép."""
    try:
        os.replace(src, dst)
    except OSError:
        shutil.copy2(src, dst)


@functools.lru_cache(maxsize=64)   # gọi cho từng cảnh — cùng 1 file nguồn chỉ ffprobe 1 lần
def _has_audio(video_path):
    cmd = [FFPROBE_EXE, '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=codec_type', '-of', 'default=nw=1:nk=1', video_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10, creationflags=_HIDE)
        return 'audio' in r.stdout.lower()
    except Exception:
        return False
def _stretch_audio_to_duration(src, target_dur, out, max_ratio=1.18):
    try:
        r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', src], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10, creationflags=_HIDE)
        src_dur = float(r.stdout.strip())
    except Exception:
        src_dur = 0.0
    if src_dur <= 0.1 or target_dur <= 0.1:
        return False
    if src_dur <= target_dur:
        return False
    ratio = min(src_dur / target_dur, max_ratio)
    if ratio <= 1.005:
        return False
    # đệm đuôi trước atempo: bộ co giãn nuốt phần cuối file → mất âm cuối chữ (đuôi lặng thừa bị -t cắt khi dựng)
    atempo = f'''apad=pad_dur=0.4,atempo={ratio:.4f}'''
    cmd = [FFMPEG_EXE, '-y', '-i', src, '-filter:a', atempo, '-ac', '1', '-ar', '44100', '-acodec', 'pcm_s16le', out]
    r2 = subprocess.run(cmd, capture_output=True, creationflags=_HIDE)
    return r2.returncode == 0 and os.path.getsize(out) > 0
def _check_nvenc():
    """GPU NVIDIA (NVENC) dùng được không — dò 1 lần ở core.encoder (đúng tham số, tôn trọng Cài đặt bật / tắt)."""
    from core import encoder
    return encoder.use_gpu()
def _video_encode_args(use_nvenc):
    from core import encoder
    return encoder.video_args('scene', gpu=use_nvenc)
def _find_font():
    tool_dir = os.path.dirname(os.path.abspath(__file__))
    cache_font = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'AutoReviewStudio', 'cache', 'fonts', 'DejaVuSans.ttf')
    candidates = ['C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/Segoeui.ttf', 'C:/Windows/Fonts/Arial.ttf', 'C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialuni.ttf', 'C:/Windows/Fonts/DejaVuSans.ttf', os.path.join(tool_dir, 'DejaVuSans.ttf').replace('\\', '/'), cache_font.replace('\\', '/')]
    for p in candidates:
        if os.path.exists(p):
            return p
    try:
        os.makedirs(os.path.dirname(cache_font), exist_ok=True)
        import urllib.request
        url = 'https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf'
        urllib.request.urlretrieve(url, cache_font)
        if os.path.exists(cache_font):
            if os.path.getsize(cache_font) > 100000:
                return cache_font.replace('\\', '/')
    except Exception:
        pass
    return None
def _find_system_font(font_name='Segoe UI'):
    font_name_lower = font_name.lower()
    font_map = {'segoe ui': ['C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/Segoeui.ttf'], 'arial': ['C:/Windows/Fonts/Arial.ttf', 'C:/Windows/Fonts/arial.ttf'], 'times new roman': ['C:/Windows/Fonts/times.ttf', 'C:/Windows/Fonts/timesbd.ttf'], 'tahoma': ['C:/Windows/Fonts/tahoma.ttf'], 'verdana': ['C:/Windows/Fonts/verdana.ttf'], 'impact': ['C:/Windows/Fonts/impact.ttf'], 'comic sans': ['C:/Windows/Fonts/comic.ttf', 'C:/Windows/Fonts/comicbd.ttf'], 'montserrat': ['C:/Windows/Fonts/Montserrat-Regular.ttf', 'C:/Windows/Fonts/montserrat.ttf'], 'roboto': ['C:/Windows/Fonts/Roboto-Regular.ttf', 'C:/Windows/Fonts/roboto.ttf']}
    candidates = font_map.get(font_name_lower, [])
    for p in candidates:
        if os.path.exists(p):
            return p
    direct_path = f'''C:/Windows/Fonts/{font_name}.ttf'''
    if os.path.exists(direct_path):
        return direct_path.replace('\\', '/')
    direct_path_lower = f'''C:/Windows/Fonts/{font_name_lower}.ttf'''
    if os.path.exists(direct_path_lower):
        return direct_path_lower.replace('\\', '/')
    try:
        from core.fonts import find_font_file
        found = find_font_file(font_name)
        if found:
            return found.replace('\\', '/')
    except Exception as e:
        print(f'[font] Lỗi tìm font "{font_name}": {e}')
    fb = _find_font()
    print(f'[font] Không tìm thấy font "{font_name}" — dùng font mặc định {fb}')
    return fb
def cap_spans(spans, max_terms=50):
    """Gộp khoảng thời gian [(a, b)] cho còn tối đa `max_terms` (gộp 2 khoảng sát nhau nhất trước) — biểu thức
    enable='between(..)+between(..)…' quá dài (phim dài có hàng trăm câu phụ đề) làm ffmpeg báo "Cannot allocate memory".
    Không bỏ khoảng nào: gộp chỉ che dư phần hở giữa 2 khoảng, vẫn che đủ mọi lúc có chữ."""
    merged = []
    for (a, b) in sorted((float(a), float(b)) for (a, b) in spans if float(b) > float(a)):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    while len(merged) > max_terms:
        k = min(range(len(merged) - 1), key=lambda i: merged[i + 1][0] - merged[i][1])
        merged[k][1] = max(merged[k][1], merged[k + 1][1])
        del merged[k + 1]
    return merged


def enable_expr(spans, max_terms=50):
    """[(a, b)] → biểu thức enable của ffmpeg (between(t,a,b)+…), đã gộp cho đủ ngắn; '' nếu không có khoảng nào."""
    return '+'.join(f'between(t\\,{a:.3f}\\,{b:.3f})' for (a, b) in cap_spans(spans, max_terms))


def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _box_area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def group_boxes(items, max_groups=12):
    """[(box [x1, y1, x2, y2], [(a, b), …])] → nhóm làm mờ chung 1 lớp lọc (ít bước lọc, dựng nhanh).
    Chỉ gộp vùng gần như trùng chỗ (khung hợp ≤ 1.2 lần vùng lớn hơn) → vùng mờ đúng cỡ chữ. Còn quá max_groups nhóm
    (vd cả phim hàng trăm câu phụ đề) thì gộp dần cặp tốn ít "diện tích × giây" che thừa nhất — câu phụ đề cùng dải
    gộp trước, logo đứng suốt phim không bị nối với chữ khác. Trước gộp theo "cùng dải / cùng cột" → chữ khác nhau ở gần
    nhau thành 1 khối to che suốt (góc trái 50% × 20% khung), và nhóm thứ 13 trở đi bị bỏ (chữ lộ ra)."""
    groups = []
    for (box, spans) in items:
        for g in groups:
            u = _union(g[0], box)
            if _box_area(u) <= 1.2 * max(_box_area(g[0]), _box_area(box)):
                (g[0], g[1]) = (u, g[1] + list(spans))
                break
        else:
            groups.append([list(box), list(spans)])
    if len(groups) > max_groups:
        import numpy as np
        bx = np.array([g[0] for g in groups], dtype=float)
        du = np.array([max(0.05, sum(b - a for (a, b) in g[1])) for g in groups])
        alive = np.ones(len(groups), bool)
        while alive.sum() > max_groups:
            ar = (bx[:, 2] - bx[:, 0]) * (bx[:, 3] - bx[:, 1])
            ux = np.minimum.outer(bx[:, 0], bx[:, 0]); uy = np.minimum.outer(bx[:, 1], bx[:, 1])
            uw = np.maximum.outer(bx[:, 2], bx[:, 2]) - ux; uh = np.maximum.outer(bx[:, 3], bx[:, 3]) - uy
            cost = uw * uh * np.add.outer(du, du) - (ar * du)[:, None] - (ar * du)[None, :]
            cost[~alive, :] = np.inf; cost[:, ~alive] = np.inf
            np.fill_diagonal(cost, np.inf)
            (i, j) = np.unravel_index(np.argmin(cost), cost.shape)
            groups[i] = [_union(groups[i][0], groups[j][0]), groups[i][1] + groups[j][1]]
            bx[i] = groups[i][0]
            du[i] += du[j]
            alive[j] = False
        groups = [g for (g, ok) in zip(groups, alive) if ok]
    return groups


def _merge_spans(spans, gap=0.0):
    out = []
    for (a, b) in sorted(spans):
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _mask_blur_chain(items, src_size, sigma, style, max_spans, merge_gap):
    """Làm mờ MỌI vùng chữ bằng 1 lớp mờ + mặt nạ: thu nhỏ khung 1/4 → làm mờ → mặt nạ (mỗi vùng 1 ô trắng, chỉ bật
    đúng lúc vùng đó có chữ) → phóng lại, dán 1 lần. Mỗi vùng che đúng khung, đúng lúc — không phải gộp vùng thành khối to,
    bao nhiêu vùng cũng gần như không thêm thời gian dựng (268 vùng: +3s / 40s 1080p; cách cắt-dán 16 nhóm cũ: +17s).
    Mặt nạ phóng từ 1/4 → mép mờ mềm ~4px, ô nới thêm 1 điểm ảnh nhỏ mỗi phía cho kín chữ."""
    (sw, sh) = (int(src_size[0]), int(src_size[1]))
    down = 4 if max(sw, sh) >= 1000 else 2
    boxes = {}                                   # cùng khung (vd logo quét được nhiều lần) → 1 ô, nhiều khoảng thời gian
    for (box, spans) in items:
        boxes.setdefault(tuple(round(v, 4) for v in box), []).extend(spans)
    (parts, cur, all_spans, hs) = ([], '0:v', [], [])
    erase = style == 'erase'
    draws = []
    for (k, ((x1, y1, x2, y2), spans)) in enumerate(boxes.items()):
        merged = _merge_spans(spans, merge_gap)
        all_spans += merged
        en = enable_expr(merged, min(50, max_spans))
        if erase:
            # Xoá nhẹ: delogo lấp vùng chữ bằng điểm ảnh xung quanh, lớp mờ nhẹ phía sau làm mượt viền.
            # delogo cần toạ độ px nằm hẳn trong khung (không chạm mép).
            (px, py) = (max(1, int(x1 * sw)), max(1, int(y1 * sh)))
            (pw, ph) = (max(4, min(int(x2 * sw), sw - 2) - px), max(4, min(int(y2 * sh), sh - 2) - py))
            parts.append(f"[{cur}]delogo=x={px}:y={py}:w={pw}:h={ph}:enable='{en}'[tsd{k}]")
            cur = f'tsd{k}'
            hs.append(ph)
        # toạ độ theo cỡ khung thật (iw/ih) — nới 1 điểm ảnh (khung nhỏ) mỗi phía; drawbox tự cắt phần lòi ra ngoài khung
        draws.append(f"drawbox=x=iw*{x1:.4f}-1:y=ih*{y1:.4f}-1:w=iw*{x2 - x1:.4f}+3:h=ih*{y2 - y1:.4f}+3:c=white:t=fill:enable='{en}'")
    if erase:                                    # vùng lớn mờ thêm chút cho hết vệt sọc của delogo
        sigma = max(4, round(sorted(hs)[len(hs) // 2] * 0.09))
    any_en = enable_expr(_merge_spans(all_spans, 0.5), min(50, max_spans))
    parts.append(f'[{cur}]split=3[tsm][tsl][tsr]')
    parts.append(f'[tsl]scale=trunc(iw/{down * 2})*2:trunc(ih/{down * 2})*2:flags=area,split[tsb][tsk]')
    parts.append(f"[tsb]gblur=sigma={max(1.0, sigma / down):.2f}:steps=2:enable='{any_en}'[tsbb]")
    parts.append('[tsk]format=gray,drawbox=c=black:t=fill,' + ','.join(draws) + '[tsmk]')
    # phóng lại đúng cỡ khung gốc (lấy theo chính khung hình — video quay dọc có cờ xoay cũng khớp)
    parts.append('[tsbb][tsmk]alphamerge[tsa0]')
    parts.append('[tsa0][tsr]scale=rw:rh:flags=bilinear[tsa]')
    parts.append(f"[tsm][tsa]overlay=0:0:enable='{any_en}'[tsout]")
    return (';'.join(parts), 'tsout')


def _src_text_blur_chain(regions, clip_start, src_dur, sigma=22, max_groups=12, max_spans=40, merge_gap=0.0, style='blur', src_size=None):
    """Vùng chữ (box % hình gốc, giây video gốc) → chuỗi lọc làm mờ trên [0:v] của clip (t tính từ clip_start).
    Vùng cùng dải (vd mọi câu phụ đề ở đáy) gộp thành 1 lớp mờ với nhiều khoảng thời gian → ít bước lọc, dựng nhanh."""
    if not regions:
        return ('', '0:v')
    items = []
    for r in regions:
        try:
            (x1, y1, x2, y2) = [max(0.0, min(1.0, float(v))) for v in r['box']]
            (a, b) = (float(r['t_start']) - clip_start, float(r['t_end']) - clip_start)
        except (KeyError, TypeError, ValueError):
            continue
        if b <= 0 or a >= src_dur or x2 - x1 < 0.01 or y2 - y1 < 0.01:
            continue
        items.append(([x1, y1, x2, y2], [(max(0.0, a), min(src_dur, b))]))
    if not items:
        return ('', '0:v')
    if src_size and src_size[0] > 8 and src_size[1] > 8:
        return _mask_blur_chain(items, src_size, sigma, style, max_spans, merge_gap)
    groups = group_boxes(items, max_groups)       # không đọc được cỡ video → cách cũ: cắt từng nhóm, làm mờ, dán lại
    erase = style == 'erase' and src_size and src_size[0] > 8 and src_size[1] > 8
    (parts, cur, blurs) = ([], '0:v', [])
    for (i, ((x1, y1, x2, y2), spans)) in enumerate(groups):
        merged = []                              # gộp khoảng sát nhau (cả phim một lượt có hàng trăm câu phụ đề)
        for (a, b) in sorted(spans):
            if merged and a <= merged[-1][1] + merge_gap:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        en = enable_expr(merged, min(50, max_spans))       # gộp cho đủ ngắn — không bỏ khoảng nào (trước cắt bớt → cuối phim lộ chữ)
        (dw, dh) = (x2 - x1, y2 - y1)
        if erase:
            # Xoá nhẹ: delogo lấp vùng chữ bằng điểm ảnh xung quanh (gần như không thấy), phủ thêm mờ nhẹ cho mượt viền.
            # delogo cần toạ độ px nằm hẳn trong khung (không chạm mép).
            (sw, sh) = src_size
            (px, py) = (max(1, int(x1 * sw)), max(1, int(y1 * sh)))
            (pw, ph) = (max(4, min(int(x2 * sw), sw - 2) - px), max(4, min(int(y2 * sh), sh - 2) - py))
            parts.append(f"[{cur}]delogo=x={px}:y={py}:w={pw}:h={ph}:enable='{en}'[tsd{i}]")
            cur = f'tsd{i}'
            sigma_i = max(4, round(ph * 0.09))       # vùng lớn mờ thêm chút cho hết vệt sọc của delogo
        else:
            sigma_i = sigma
        blurs.append((x1, y1, dw, dh, sigma_i, en))
    if not blurs:
        return ('', '0:v')
    # Split 1 lần → N nhánh cắt + làm mờ → dán lần lượt. Mỗi vùng 1 cặp split → overlay nối tiếp làm ffmpeg kéo khung hình
    # nhân đôi qua từng cặp (thời gian dựng tăng theo 2^số vùng). gblur cũng chỉ chạy lúc vùng đó cần che.
    n = len(blurs)
    parts.append(f'[{cur}]split[tsm][tss]')
    parts.append(f'[tss]split={n}' + ''.join(f'[tss{i}]' for i in range(n)) if n > 1 else '[tss]null[tss0]')
    cur = 'tsm'
    for (i, (x1, y1, dw, dh, sigma_i, en)) in enumerate(blurs):
        parts.append(f'[tss{i}]crop=trunc(iw*{dw:.4f}/2)*2:trunc(ih*{dh:.4f}/2)*2:trunc(iw*{x1:.4f}/2)*2:trunc(ih*{y1:.4f}/2)*2,'
                     f"gblur=sigma={sigma_i:g}:steps=3:enable='{en}'[tsc{i}]")
        parts.append(f"[{cur}][tsc{i}]overlay=trunc(W*{x1:.4f}/2)*2:trunc(H*{y1:.4f}/2)*2:enable='{en}'[ts{i}]")
        cur = f'ts{i}'
    return (';'.join(parts), cur)


_DIMS = {}


def src_dims(path):
    """(rộng, cao) px của video gốc — nhớ theo file (xoá chữ kiểu delogo cần toạ độ px)."""
    if path not in _DIMS:
        try:
            r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                'stream=width,height:stream_side_data=rotation', '-of', 'json', path],
                               capture_output=True, text=True, creationflags=_HIDE, timeout=20)
            s = (json.loads(r.stdout or '{}').get('streams') or [{}])[0]
            (w, h) = (int(s['width']), int(s['height']))
            rot = next((int(float(d.get('rotation') or 0)) for d in s.get('side_data_list') or [] if 'rotation' in d), 0)
            # video quay điện thoại có cờ xoay 90° → ffmpeg tự xoay khung khi đọc → rộng / cao đổi chỗ
            _DIMS[path] = (h, w) if abs(rot) % 180 == 90 else (w, h)
        except Exception:
            _DIMS[path] = (0, 0)
    return _DIMS[path]


def _text_region(text, font_path, fontsize, line_spacing, border, vid_w, vid_h, position, margin_v, center_y=None):
    """Khung (x, y, w, h — px, số chẵn) bao dòng phụ đề như drawtext vẽ, nới thêm lề — để làm mờ nền sau chữ."""
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(font_path, int(fontsize)) if font_path else ImageFont.load_default()
        (_, top, _, bottom) = font.getbbox('Ây')                   # cao 1 dòng (có dấu tiếng Việt)
        lines = text.split('\n')
        tw = max(font.getlength(ln) for ln in lines) if lines else 0
        th = (bottom - top) * len(lines) + max(0, int(line_spacing)) * (len(lines) - 1)
    except Exception:
        return None
    pad = int(fontsize * 0.45) + int(border)
    (bw, bh) = (min(vid_w, int(tw) + 2 * pad), min(vid_h, int(th) + 2 * pad))
    x = (vid_w - bw) // 2
    if center_y is not None:
        y = int(vid_h * center_y - th / 2) - pad
    elif position == 'top':
        y = margin_v - pad
    elif position == 'middle':
        y = (vid_h - th) // 2 - pad
    else:
        y = vid_h - int(th) - margin_v - pad
    (x, y) = (max(0, x), max(0, min(vid_h - bh, y)))
    even = lambda v: int(v) // 2 * 2
    return (even(x), even(y), max(2, even(bw)), max(2, even(bh)))


def _crop_prefix(crop_box, fill, w, h):
    """Cắt khung hình gốc trước khi đưa về khung xuất. crop_box = [x, y, rộng, cao] theo % hình GỐC.
    fill=True: phóng phần đã cắt cho phủ kín khung (cắt bớt mép thừa nếu khác tỉ lệ); False: giữ trọn, thêm viền đen.
    '' nếu không cắt / khung không hợp lệ."""
    try:
        (x, y, cw, ch) = [max(0.0, min(100.0, float(v))) / 100.0 for v in (crop_box or [])[:4]]
    except (TypeError, ValueError):
        return ''
    if cw < 0.05 or ch < 0.05 or (cw > 0.995 and ch > 0.995):
        return ''
    (cw, ch) = (min(cw, 1.0 - x), min(ch, 1.0 - y))
    crop = f'crop=trunc(iw*{cw:.4f}/2)*2:trunc(ih*{ch:.4f}/2)*2:trunc(iw*{x:.4f}/2)*2:trunc(ih*{y:.4f}/2)*2'
    if fill:
        return f'{crop},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}'
    return f'{crop},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black'


def _standardize_clip(src_path, target_path, resolution, fps, log_fn):
    (w, h) = resolution.split('x')
    use_nvenc = _check_nvenc()
    enc = _video_encode_args(use_nvenc)
    vf = f'''scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps}'''
    probe_cmd = [FFPROBE_EXE, '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', src_path]
    try:
        probe_r = subprocess.run(probe_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE, timeout=10)
        has_audio_track = bool(probe_r.stdout.strip())
    except Exception:
        has_audio_track = True
    if has_audio_track:
        cmd = [FFMPEG_EXE, '-y', '-i', src_path, '-vf', vf, *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), target_path]
    else:
        cmd = [FFMPEG_EXE, '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-i', src_path, '-vf', vf, '-map', '1:v', '-map', '0:a', *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), '-shortest', target_path]
    r = run_subprocess(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    if r.returncode == 0:
        if os.path.exists(target_path):
            if os.path.getsize(target_path) > 0:
                return True
    log_fn('   [Branding] NVENC lỗi, chuyển sang encode bằng CPU cho clip chuẩn hóa...')
    cpu_enc = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p']
    if has_audio_track:
        cmd_fb = [FFMPEG_EXE, '-y', '-i', src_path, '-vf', vf, *cpu_enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), target_path]
    else:
        cmd_fb = [FFMPEG_EXE, '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-i', src_path, '-vf', vf, '-map', '1:v', '-map', '0:a', *cpu_enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), '-shortest', target_path]
    r2 = subprocess.run(cmd_fb, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE)
    if r2.returncode != 0:
        log_fn(f'''   [WARN] _standardize_clip thất bại: {r2.stderr[slice(-300, None, None)]}''')
    return r2.returncode == 0 and os.path.getsize(target_path) > 0
def recap_length_report(scenes, output_duration_sec):
    n = len(scenes or [])
    total_tts = 0.0
    total_tile = 0.0
    total_words = 0
    for s in scenes or []:
        try:
            total_tts += float(s.get('tts_duration') or 0.0)
        except Exception:
            pass
        try:
            total_tile += max(0.0, float(s.get('clip_end') or 0.0) - float(s.get('clip_start') or 0.0))
        except Exception:
            pass
        try:
            total_words += len(str(s.get('voiceover') or '').split())
        except Exception:
            pass
    try:
        out_dur = max(0.0, float(output_duration_sec or 0.0))
    except Exception:
        out_dur = 0.0
    implied_wpm = total_words / (total_tts / 60.0) if total_tts > 0 else 0.0
    return {'n_scenes': n, 'total_tts_sec': total_tts, 'total_tile_sec': total_tile, 'output_sec': out_dur, 'total_words': total_words, 'implied_tts_wpm': implied_wpm}
def _safe_duration(path):
    try:
        return float(get_video_duration(path) or 0.0)
    except Exception:
        return 0.0
_RENDER_PRIVATE_KEYS = ('_video_scale', '_video_position', '_manual_sub_chunks')
REUP_MAX_VOICE = 1.35     # Reup: giọng nhanh tối đa
REUP_MAX_SLOW = 1.25      # Reup: hình chậm tối đa (sau khi đã mượn khoảng lặng + tăng tốc giọng)


def reup_fit(src, room, tts):
    """Căn 1 câu Reup (dùng chung cho dựng video, SRT, QA, xem trước). src = độ dài câu gốc, room = khoảng tới câu sau,
    tts = độ dài lời Việt → (span: đoạn hình gốc dùng, out: độ dài trong video xuất, pts: hình chậm ×, at: giọng nhanh ×)."""
    src = max(0.05, float(src))
    room = max(src, float(room))
    tts = float(tts)
    if tts <= src:
        return (src, src, 1.0, 1.0)
    if tts <= room:
        return (tts, tts, 1.0, 1.0)
    at = min(REUP_MAX_VOICE, tts / room)
    voice = tts / at
    if voice <= room + 0.01:
        return (voice, voice, 1.0, at)
    pts = min(REUP_MAX_SLOW, voice / room)
    return (room, max(room * pts, voice), pts, at)


def build_review_video(scenes, source_video, output_path, temp_dir, target_resolution='1920x1080', fps=30, original_volume=0.08, burn_subtitles=True, bgm_path='', bgm_volume=0.05, log_fn=print, is_reup=False, remove_old_sub=False, sub_cover_height=18, mirror_video=False, speed_up_video=False, video_speed=1.0, audio_ducking=True, watermark_path='', intro_path='', outro_path='', ai_sub_box=None, ai_logo_box=None, remove_old_logo=False, manual_logo_corner='Trên-Phải', manual_logo_size=15, watermark_corner='Trên-Phải', watermark_size_pct=14, watermark_margin_x_pct=2.0, watermark_margin_y_pct=2.0, watermark_opacity=0.92, blur_boxes=None, music_clips=None, mute_music=False, mute_sfx=False, **kwargs):
    if not scenes:
        log_fn('   [LỖI] Không có cảnh nào để dựng video')
        return
    # mốc thật trên video xuất của từng cảnh trả về cho pipeline (QA / tự sửa tìm đúng cảnh) — không vào khoá cache clip
    timeline_out = kwargs.pop('timeline_out', None)
    muted_spans = sorted((float(a), float(b)) for (a, b) in (kwargs.pop('muted_spans', None) or []) if float(b) > float(a))
    for (k, s) in enumerate(scenes):
        s.setdefault('_job_index', k)
    if is_reup:
        # Căn thời gian Reup (như pyVideoTrans / VideoLingo): hình LUÔN chạy tốc độ thật trừ khi buộc phải chậm lại.
        #  lời ≤ câu gốc            → hình 1x dài bằng câu gốc, lời ở đầu, phần còn lại lặng;
        #  câu gốc < lời ≤ khoảng trống tới câu sau → hình 1x dài bằng lời (mượn khoảng lặng phía sau);
        #  lời > khoảng trống        → giọng nhanh tối đa REUP_MAX_VOICE; vẫn thiếu → hình chậm tối đa REUP_MAX_SLOW;
        #                              vẫn thiếu nữa → giữ khung cuối. Không bao giờ tua nhanh hình.
        # Kết quả (đoạn hình dùng, tốc độ hình, tốc độ giọng, độ dài xuất) ghi vào cảnh → _process_one_scene chỉ áp dụng,
        # và SRT tính từ đúng các độ dài đó (không mỗi bên tự tính một kiểu).
        log_fn('   [Reup] Căn lời theo câu gốc: hình tốc độ thật, lời dài thì mượn khoảng lặng → giọng nhanh nhẹ → hình chậm nhẹ')
        video_dur = _safe_duration(source_video)
        has_audio = _has_audio(source_video)
        continuous_scenes = []
        sorted_scenes = sorted(scenes, key=lambda x: x['clip_start'])
        last_end = sorted_scenes[0]['clip_start'] if sorted_scenes else 0.0
        if sorted_scenes and last_end > 0.05:
            last_end = 0.0                       # đoạn hình trước câu đầu tiên vẫn giữ (tiếng gốc)
        accumulated_time = 0.0
        (n_borrow, n_fast, n_slow) = (0, 0, 0)

        def _gap(a, b, tag):
            # đoạn không có lời Việt: tiếng gốc 100% — trừ chỗ là câu thoại gốc đã bị bỏ (muted_spans) → giữ mức nhỏ
            nonlocal accumulated_time
            cuts = sorted({a, b} | {x for sp in muted_spans for x in sp if a < x < b})
            for (k, (p, q)) in enumerate(zip(cuts, cuts[1:])):
                if q - p < 0.02:
                    continue
                muted = any(ma <= (p + q) / 2 <= mb for (ma, mb) in muted_spans)
                d = q - p
                wav = os.path.join(temp_dir, f'silent_{tag}_{k}.wav')
                _create_silent_wav(wav, d)
                continuous_scenes.append({'is_reup': True, 'clip_start': p, 'clip_end': q, 'voiceover': '', 'subtitle': '', 'tts_path': wav,
                                          'tts_duration': d, 'reup_out': d, 'reup_pts': 1.0, 'reup_atempo': 1.0,
                                          'orig_volume': (original_volume if muted else 1.0) if original_volume > 0.001 else 0.0,
                                          'has_audio': has_audio, 'out_start': accumulated_time, 'out_end': accumulated_time + d})
                accumulated_time += d
        for (idx, s) in enumerate(sorted_scenes):
            start = max(float(s['clip_start']), last_end)
            end = max(start + 0.05, float(s['clip_end']))
            if start > last_end + 0.05:
                _gap(last_end, start, f'gap_{idx}')
            tts_path = s.get('tts_path')
            tts_dur = float(s.get('tts_duration') or 0)
            if not tts_path or not os.path.exists(tts_path) or tts_dur <= 0.05:
                tts_path = os.path.join(temp_dir, f'silent_fail_{idx}.wav')
                tts_dur = end - start
                _create_silent_wav(tts_path, tts_dur)
            src = end - start
            nxt = float(sorted_scenes[idx + 1]['clip_start']) if idx + 1 < len(sorted_scenes) else (video_dur or end + tts_dur)
            room = max(src, nxt - start)
            (span, out, pts, at) = reup_fit(src, room, tts_dur)
            if pts > 1.0:
                n_slow += 1
            elif at > 1.0:
                n_fast += 1
            elif tts_dur > src:
                n_borrow += 1
            continuous_scenes.append({'is_reup': True, 'clip_start': start, 'clip_end': start + span, 'voiceover': s.get('voiceover', ''),
                                      'subtitle': s.get('subtitle', s.get('voiceover', '')), 'tts_path': tts_path, 'tts_duration': tts_dur,
                                      '_job_index': s.get('_job_index'),
                                      'reup_out': round(out, 4), 'reup_pts': round(pts, 4), 'reup_atempo': round(at, 4),
                                      'orig_volume': original_volume, 'has_audio': has_audio,
                                      'out_start': accumulated_time, 'out_end': accumulated_time + min(out, tts_dur / at)})
            accumulated_time += out
            last_end = start + span
        if video_dur > last_end + 0.05:
            _gap(last_end, video_dur, 'end')
        if n_borrow or n_fast or n_slow:
            log_fn(f'   [Reup] {n_borrow} câu mượn khoảng lặng · {n_fast} câu giọng nhanh nhẹ (≤{REUP_MAX_VOICE}×) · '
                   f'{n_slow} câu phải chậm hình (≤{REUP_MAX_SLOW}×) — nên rút gọn lời các câu này')
        scenes = continuous_scenes
    else:
        _SRT_TAIL = 0.12
        video_dur_srt = _safe_duration(source_video)
        accumulated_time = 0.0
        for (idx, s) in enumerate(scenes):
            tts_path = s.get('tts_path')
            if not tts_path or not os.path.exists(tts_path):
                fallback_wav = os.path.join(temp_dir, f'''silent_fail_{idx}.wav''')
                _create_silent_wav(fallback_wav, s['clip_end'] - s['clip_start'])
                s['tts_path'] = fallback_wav
                s['tts_duration'] = s['clip_end'] - s['clip_start']
            tts_dur = s.get('tts_duration', s['clip_end'] - s['clip_start'])
            if video_dur_srt > 0:
                max_available = max(0.5, video_dur_srt - s['clip_start'])
                real_clip_dur = max(tts_dur, min(tts_dur + _SRT_TAIL, max_available))
            else:
                real_clip_dur = tts_dur + _SRT_TAIL
            # hình của cảnh không lấn sang điểm bắt đầu của cảnh khác phía sau (B11): lấn thì cảnh kia chiếu lại đúng
            # đoạn đó → lặp hình. _process_one_scene đọc 'review_cap' (đoạn hình tối đa) → lời dư thì chậm hình / giữ khung
            later = [float(x['clip_start']) for x in scenes if float(x['clip_start']) > float(s['clip_start']) + 0.05]
            s['review_cap'] = round(min(later) - float(s['clip_start']), 3) if later else None
            s['out_start'] = accumulated_time
            s['out_end'] = accumulated_time + tts_dur
            accumulated_time += real_clip_dur
    final_srt_path = os.path.splitext(output_path)[0] + '.srt'
    should_stop = kwargs.pop('should_stop', None)        # callable → True khi job bị huỷ
    sub_source_mode = kwargs.get('sub_source_mode', 'prefer_voiceover')
    # SRT ghi SAU khi dựng (đo độ dài clip thật, cộng intro, chia tốc độ video) — xem _write_synced_srt
    _srt_opts = (final_srt_path, kwargs.get('sub_max_chars_per_chunk', 56), kwargs.get('sub_max_lines', 2), sub_source_mode)
    use_nvenc = _check_nvenc()
    from core import encoder
    log_fn('   ' + encoder.describe())
    clips_dir = os.path.join(temp_dir, 'clips')
    os.makedirs(clips_dir, exist_ok=True)
    sub_font_name = kwargs.get('sub_font_name', 'Segoe UI')
    sub_custom_font_path = kwargs.get('sub_custom_font_path', '')
    if sub_custom_font_path and os.path.exists(sub_custom_font_path):
        font_path = sub_custom_font_path.replace('\\', '/')
    else:
        font_path = _find_system_font(sub_font_name)
    video_total_duration = _safe_duration(source_video)
    # chuyển cảnh chỉ dùng lúc ghép → tách khỏi kwargs để đổi kiểu chuyển cảnh không phải dựng lại clip
    transition = str(kwargs.pop('transition', 'none') or 'none')
    transition_duration = kwargs.pop('transition_duration', 0.5)
    auto_sfx = bool(kwargs.pop('auto_sfx', False))   # hiệu ứng âm thanh trộn sau khi ghép → không vào khoá clip
    from core import perf
    workers = perf.render_workers()              # theo ngân sách CPU chung (chế độ nhẹ máy → 1)
    if kwargs.get('low_memory_mode'):
        workers = 1
    if use_nvenc:
        workers = min(workers, 3)
    # Dấu vân tay mỗi clip = nội dung cảnh + mọi tuỳ chọn dựng → cảnh không đổi thì dùng lại clip đã dựng
    # (tự sửa / hậu kỳ lại chỉ dựng lại cảnh thay đổi; đổi thứ tự cảnh cũng không phải dựng lại).
    _render_opts = json.dumps({'src': [source_video, os.path.getsize(source_video) if os.path.isfile(source_video) else 0],
                               'res': target_resolution, 'fps': fps, 'vol': original_volume, 'burn': burn_subtitles, 'font': font_path,
                               'nvenc': use_nvenc, 'rm_sub': remove_old_sub, 'cover_h': sub_cover_height, 'wm': watermark_path,
                               'ai_sub': ai_sub_box, 'ai_logo': ai_logo_box, 'rm_logo': remove_old_logo, 'logo': [manual_logo_corner, manual_logo_size],
                               'wm_pos': [watermark_corner, watermark_size_pct, watermark_margin_x_pct, watermark_margin_y_pct, watermark_opacity],
                               'blur': blur_boxes, 'kw': kwargs}, sort_keys=True, default=str)

    def _clip_path(i, scene):
        # trường '_' là dữ liệu tạm (bỏ khỏi khoá) — TRỪ các trường ảnh hưởng hình dựng ra (zoom / vị trí / chia phụ đề tay)
        sc = {k: v for (k, v) in scene.items() if not str(k).startswith('_') or k in _RENDER_PRIVATE_KEYS}
        sig = hashlib.md5(json.dumps([sc, _render_opts, bool(mirror_video)], sort_keys=True, default=str).encode()).hexdigest()[:20]
        return os.path.join(clips_dir, f'clip_{sig}.mp4')

    reused = [0]
    log_fn(f'''   Cắt và xử lý {len(scenes)} clip (song song {workers} FFmpeg)...''')
    results = {}
    done_count = [0]
    def _render_one(args):
        (i, scene) = args
        clip_out = _clip_path(i, scene)
        if os.path.isfile(clip_out) and os.path.getsize(clip_out) > 1000:
            reused[0] += 1
            return (i, clip_out)
        if should_stop and should_stop():
            return (i, None)
        try:
            ok = _process_one_scene(source_video, scene, clip_out, target_resolution, fps, original_volume, burn_subtitles, log_fn, i, font_path, video_total_duration, use_nvenc=use_nvenc, remove_old_sub=remove_old_sub, sub_cover_height=sub_cover_height, mirror_video=bool(mirror_video), watermark_path=watermark_path, ai_sub_box=ai_sub_box, ai_logo_box=ai_logo_box, remove_old_logo=remove_old_logo, manual_logo_corner=manual_logo_corner, manual_logo_size=manual_logo_size, watermark_corner=watermark_corner, watermark_size_pct=watermark_size_pct, watermark_margin_x_pct=watermark_margin_x_pct, watermark_margin_y_pct=watermark_margin_y_pct, watermark_opacity=watermark_opacity, blur_boxes=blur_boxes, **kwargs)
        except Exception as e:
            log_fn(f'''   [LỖI] Cảnh {i + 1} gặp lỗi: {e}''')
            ok = False
        return (i, clip_out if ok else None)
    from core import perf
    with perf.parallel(workers), ThreadPoolExecutor(max_workers=workers) as executor:   # mỗi ffmpeg = ngân sách ÷ workers luồng
        futures = {executor.submit(_render_one, (i, s)): i for (i, s) in enumerate(scenes)}
        for future in as_completed(futures):
            (i, clip_path) = future.result()
            done_count[0] += 1
            if clip_path:
                results[i] = clip_path
            else:
                log_fn(f'''   [WARN] Bỏ qua cảnh {i + 1}''')
            n = done_count[0]
            if n % 5 == 0 or n == len(scenes):
                log_fn(f'''   Tiến độ cắt clip: {n}/{len(scenes)}''')
    if should_stop and should_stop():
        log_fn('   [DỪNG] Đã huỷ khi đang dựng video.')
        return
    if reused[0]:
        log_fn(f'   Dùng lại {reused[0]}/{len(scenes)} clip đã dựng trước đó (cảnh không đổi) — chỉ dựng {len(scenes) - reused[0]} cảnh')
    final_clips = [results[k] for k in sorted(results)]
    if not final_clips:
        log_fn('   [LỖI] Không dựng được clip nào')
        return
    if len(results) < len(scenes):
        log_fn(f'   [WARN] {len(scenes) - len(results)} cảnh dựng lỗi bị bỏ khỏi video — phụ đề vẫn khớp các cảnh còn lại')
    _intro_used = [0.0]
    if intro_path and os.path.exists(intro_path):
        intro_std = os.path.join(temp_dir, 'intro_std.mp4')
        log_fn('   [Branding] Đang đồng bộ hóa cấu hình Video Intro đầu kênh...')
        if _standardize_clip(intro_path, intro_std, target_resolution, fps, log_fn):
            final_clips.insert(0, intro_std)
            _intro_used[0] = _stream_duration(intro_std, 'v:0') or _safe_duration(intro_std)
            log_fn('   [Branding] Đã chèn Video Intro thành công.')
        else:
            log_fn('   [WARN] Đồng bộ Video Intro thất bại, bỏ qua.')
    if outro_path and os.path.exists(outro_path):
        outro_std = os.path.join(temp_dir, 'outro_std.mp4')
        log_fn('   [Branding] Đang đồng bộ hóa cấu hình Video Outro cuối kênh...')
        if _standardize_clip(outro_path, outro_std, target_resolution, fps, log_fn):
            final_clips.append(outro_std)
            log_fn('   [Branding] Đã chèn Video Outro thành công.')
        else:
            log_fn('   [WARN] Đồng bộ Video Outro thất bại, bỏ qua.')
    concat_output = os.path.join(temp_dir, 'concat_output.mp4')
    log_fn(f'''   Ghép {len(final_clips)} clip thành video cuối...''')
    ok = False
    if transition != 'none' and len(final_clips) > 1:
        ok = _concat_with_transitions(final_clips, concat_output, temp_dir, log_fn, transition, transition_duration, fps, use_nvenc)
        if not ok:
            log_fn('   [WARN] Ghép có chuyển cảnh lỗi — ghép thường (không chuyển cảnh)')
    if not ok:
        ok = _concat_clips(final_clips, concat_output, temp_dir, log_fn)
    if not ok:
        log_fn('   [LOI] Ghép nối các phân cảnh video thất bại')
        return
    enc = _video_encode_args(use_nvenc)
    _final_speed = video_speed
    _applied_speed = 1.0                         # tốc độ thật sự đã áp (đổi tốc độ lỗi → video vẫn 1x, SRT cũng không chia)
    if speed_up_video and video_speed == 1.0:
        _final_speed = 1.03
    try:
        _final_speed = float(_final_speed)
    except (TypeError, ValueError):
        _final_speed = 1.0
    if _final_speed != 1.0:
        _final_speed = max(0.5, min(2.0, _final_speed))
        log_fn(f'''   Đang chỉnh tốc độ toàn bộ video lên {_final_speed:.2f}x...''')
        speed_output = os.path.join(temp_dir, 'speed_output.mp4')
        cmd_speed = [FFMPEG_EXE, '-y', '-i', concat_output, '-filter_complex', f'''[0:v]setpts={1.0 / _final_speed:.4f}*PTS[v];[0:a]atempo={_final_speed:.4f}[a]''', '-map', '[v]', '-map', '[a]', *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), speed_output]
        r_speed = run_subprocess_heartbeat(cmd_speed, log_fn=log_fn, label=f'''Đang chỉnh tốc độ video {_final_speed:.2f}x''', text=True, encoding='utf-8', errors='replace')
        if r_speed.returncode != 0 and use_nvenc:
            cmd_speed_cpu = [x for x in cmd_speed]
            _ei = cmd_speed_cpu.index(enc[0])
            cmd_speed_cpu[_ei:_ei + len(enc)] = _video_encode_args(False)
            r_speed = run_subprocess_heartbeat(cmd_speed_cpu, log_fn=log_fn, label=f'''Đang chỉnh tốc độ video {_final_speed:.2f}x (CPU)''', text=True, encoding='utf-8', errors='replace')
        if r_speed.returncode == 0 and os.path.exists(speed_output):
            concat_output = speed_output
            _applied_speed = _final_speed
            log_fn(f'''   Chỉnh tốc độ {_final_speed:.2f}x thành công!''')
        else:
            log_fn(f'''   [WARN] Chỉnh tốc độ video thất bại: {(r_speed.stderr or '')[-200:]}''')
    _write_synced_srt(scenes, results, _intro_used[0], _applied_speed, _srt_opts, log_fn)
    if timeline_out is not None:
        timeline_out.extend({'i': s['_job_index'], 'out_start': s['out_start'], 'out_end': s['out_end']}
                            for (k, s) in enumerate(scenes) if k in results and s.get('_job_index') is not None)
    if auto_sfx and not is_reup:
        try:
            from core import sfx
            done = [scenes[k] for k in sorted(results)]
            energies = sfx.scene_energy(kwargs.get('bg_audio') or source_video, done)
            fx = sfx.plan(done, energies, _safe_duration(concat_output), intro=_intro_used[0] / (_applied_speed or 1.0))
            if fx:
                n_w = sum(1 for f in fx if f['kind'] == 'whoosh')
                log_fn(f'   Hiệu ứng âm thanh tự động: {n_w} "vút" khi chuyển cảnh · {len(fx) - n_w} "bùm" ở cao trào')
                music_clips = list(music_clips or []) + fx
        except Exception as e:
            log_fn(f'   [WARN] Không thêm được hiệu ứng âm thanh: {str(e)[:120]}')
    audio_src = concat_output
    if bgm_path and os.path.exists(bgm_path):
        log_fn('   Trộn nhạc nền (BGM)...')
        bgm_out = os.path.join(temp_dir, 'bgm_mixed.mp4')
        ok = _mix_bgm(audio_src, bgm_path, bgm_out, bgm_volume, log_fn, audio_ducking=audio_ducking)
        if ok:
            audio_src = bgm_out
        else:
            log_fn('   [WARN] Trộn BGM thất bại, bỏ qua BGM')
    if music_clips:
        log_fn(f'''   Trộn {len(music_clips)} đoạn Nhạc nền/SFX từ Timeline...''')
        ok2 = _mix_multi_audio(audio_src, music_clips, output_path, log_fn, mute_music=mute_music, mute_sfx=mute_sfx)
        if not ok2:
            log_fn('   [WARN] Trộn Nhạc/SFX từ Timeline thất bại (hoặc không còn đoạn nào dùng được sau khi lọc mute) — giữ nguyên audio trước đó')
            _move_into(audio_src, output_path)
    else:
        _move_into(audio_src, output_path)
    log_fn(f'''   Đã xuất video: {output_path}''')
    try:
        _rep = recap_length_report(scenes, _safe_duration(output_path))
        log_fn(f'''   [ĐO ĐỘ DÀI] {_rep['n_scenes']} cảnh | giọng đọc {_rep['total_tts_sec'] / 60:.1f}′ | lát gạch nguồn {_rep['total_tile_sec'] / 60:.1f}′ | video xuất {_rep['output_sec'] / 60:.1f}′ | {_rep['total_words']} từ (~{_rep['implied_tts_wpm']:.0f} từ/phút thực).''')
    except Exception:
        pass
    return output_path
def _write_synced_srt(scenes, clips, intro_dur, speed, opts, log_fn):
    """SRT khớp video XUẤT: mốc mỗi câu = tổng độ dài THẬT các clip đã dựng trước nó (đo từng file — tính cả nén giọng,
    chậm hình, giữ khung cuối, cảnh dựng lỗi bị bỏ) + intro, rồi chia tốc độ video toàn cục. Phần có lời trong clip =
    độ dài lời đã tính lúc lên lịch (không vượt clip). Ghi lại out_start / out_end vào cảnh."""
    (path, max_chars, max_lines, mode) = opts
    try:
        t = float(intro_dur or 0.0)
        sp = float(speed or 1.0) or 1.0
        timed = []
        for i in sorted(clips):
            s = scenes[i]
            d = _stream_duration(clips[i], 'v:0') or _safe_duration(clips[i]) or 0.0
            speech = max(0.0, float(s.get('out_end', 0) or 0) - float(s.get('out_start', 0) or 0)) or d
            s['out_start'] = t / sp
            s['out_end'] = (t + min(speech, d)) / sp
            if _resolve_subtitle_text(s, mode):
                timed.append(s)
            t += d
        _generate_srt_file(timed, path, sub_max_chars_per_chunk=max_chars, sub_max_lines=max_lines, sub_source_mode=mode)
        log_fn(f'''   Đã tạo file phụ đề SRT đồng bộ (theo độ dài clip thật): {path}''')
    except Exception as e:
        log_fn(f'''   [WARN] Lỗi tạo file phụ đề SRT: {e}''')


def _mix_bgm(video_in, bgm_path, video_out, bgm_volume, log_fn=print, audio_ducking=True):
    if audio_ducking:
        filter_str = f'''[1:a]volume={bgm_volume}[bgm];[bgm][0:a]sidechaincompress=threshold=-25dB:ratio=10:attack=100:release=400[bgm_ducked];[0:a][bgm_ducked]amix=inputs=2:normalize=0:duration=first:dropout_transition=0,alimiter=limit=0.97:level=disabled[a]'''
    else:
        filter_str = f'''[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:normalize=0:duration=first:dropout_transition=0,alimiter=limit=0.97:level=disabled[a]'''
    cmd = [FFMPEG_EXE, '-y', '-i', video_in, '-stream_loop', '-1', '-i', bgm_path, '-filter_complex', filter_str, '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-shortest', video_out]
    r = run_subprocess_heartbeat(cmd, log_fn=log_fn, label='Trộn nhạc nền (BGM)', text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        log_fn(f'''   [WARN] Trộn nhạc nền (BGM) lỗi: {r.stderr[slice(-300, None, None)]}''')
        return False
    return os.path.exists(video_out) and os.path.getsize(video_out) > 0
def _mix_multi_audio(video_in, clips, video_out, log_fn=print, mute_music=False, mute_sfx=False):
    def _clip_dur(c):
        try:
            return float(c.get('duration') or 0)
        except (TypeError, ValueError):
            return 0.0
    usable = [c for c in (clips or []) if c.get('source') and os.path.exists(c['source']) and _clip_dur(c) > 0 and not (c.get('track') == 'music' and mute_music) and not (c.get('track') == 'sfx' and mute_sfx)]
    if not usable:
        return False
    cmd = [FFMPEG_EXE, '-y', '-i', video_in]
    for c in usable:
        cmd += ['-i', c['source']]
    chains = []
    labels = []
    for (i, c) in enumerate(usable, start=1):
        dur = max(0.05, float(c.get('duration') or 0))
        vol_raw = c.get('volume')
        vol = max(0.0, float(vol_raw if vol_raw is not None else 1.0))
        start_ms = max(0, int(round(float(c.get('start', 0.0) or 0.0) * 1000)))
        chain = f'''[{i}:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={vol:.3f}'''
        fade_in = max(0.0, float(c.get('fadeIn', 0.0) or 0.0))
        fade_out = max(0.0, float(c.get('fadeOut', 0.0) or 0.0))
        if fade_in > 0:
            chain += f''',afade=t=in:st=0:d={min(fade_in, dur):.2f}'''
        if fade_out > 0:
            st = max(0.0, dur - fade_out)
            chain += f''',afade=t=out:st={st:.2f}:d={min(fade_out, dur):.2f}'''
        chain += f''',adelay={start_ms}|{start_ms}[a{i}]'''
        chains.append(chain)
        labels.append(f'''[a{i}]''')
    n_inputs = len(usable) + 1
    filter_str = ';'.join(chains) + f''';[0:a]{''.join(labels)}amix=inputs={n_inputs}:normalize=0:duration=first:dropout_transition=0,alimiter=limit=0.97:level=disabled[a]'''
    cmd += ['-filter_complex', filter_str, '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-shortest', video_out]
    r = run_subprocess_heartbeat(cmd, log_fn=log_fn, label=f'''Trộn {len(usable)} đoạn Nhạc/SFX''', text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        log_fn(f'''   [WARN] Trộn nhiều âm thanh lỗi: {r.stderr[slice(-300, None, None)]}''')
        return False
    return os.path.exists(video_out) and os.path.getsize(video_out) > 0
def _process_one_scene(source_video, scene, out_path, resolution, fps, original_volume, burn_subtitles, log_fn, i=0, font_path=None, video_total_duration=0.0, use_nvenc=False, remove_old_sub=False, sub_cover_height=18, mirror_video=False, watermark_path='', ai_sub_box=None, ai_logo_box=None, remove_old_logo=False, manual_logo_corner='Trên-Phải', manual_logo_size=15, watermark_corner='Trên-Phải', watermark_size_pct=14, watermark_margin_x_pct=2.0, watermark_margin_y_pct=2.0, watermark_opacity=0.92, blur_boxes=None, **kwargs):
    clip_start = scene['clip_start']
    clip_end = scene['clip_end']
    tts_duration = scene['tts_duration']
    _raw_tts_duration = tts_duration
    tts_path = scene['tts_path']
    subtitle = _resolve_subtitle_text(scene, kwargs.get('sub_source_mode', 'prefer_voiceover'))
    is_reup = scene.get('is_reup', False)
    if is_reup and 'reup_out' in scene:
        # đã tính sẵn ở build_review_video: đoạn hình gốc [clip_start, clip_end], tốc độ hình, tốc độ giọng, độ dài xuất
        clip_duration = max(0.05, clip_end - clip_start)
        pts_ratio = float(scene.get('reup_pts') or 1.0)
        _at = float(scene.get('reup_atempo') or 1.0)
        if _at > 1.001 and tts_duration > 0.05:
            stretched_wav = out_path + '_fast.wav'
            if _stretch_audio_to_duration(tts_path, tts_duration / _at, stretched_wav, max_ratio=_at + 0.001):
                tts_path = stretched_wav
        tts_duration = float(scene['reup_out'])
        sub_span_duration = min(_raw_tts_duration / _at, tts_duration) if _raw_tts_duration > 0.1 else tts_duration
    elif is_reup:
        clip_duration = max(0.05, clip_end - clip_start)
        if tts_duration <= 0.05:
            tts_duration = clip_duration
        if tts_duration > clip_duration:
            stretched_wav = out_path + '_stretched.wav'
            ok_stretch = _stretch_audio_to_duration(tts_path, clip_duration, stretched_wav)
            if ok_stretch:
                tts_path = stretched_wav
                ratio = tts_duration / clip_duration
                if ratio > 1.18:
                    tts_duration = tts_duration / 1.18
                else:
                    tts_duration = clip_duration
        pts_ratio = tts_duration / clip_duration
        pts_ratio = max(0.4, min(2.5, pts_ratio))
        tts_duration = clip_duration * pts_ratio
        sub_span_duration = min(_raw_tts_duration, tts_duration) if _raw_tts_duration > 0.1 else tts_duration
    else:
        if tts_duration <= 0.1:
            return False
        if video_total_duration > 0:
            max_available = max(0.5, video_total_duration - clip_start)
        else:
            max_available = tts_duration + 5
        TAIL = 0.12
        cap = scene.get('review_cap')
        if cap:                                  # không đọc hình lấn sang cảnh khác phía sau (tránh lặp hình)
            max_available = min(max_available, max(0.3, float(cap)))
        clip_duration = min(tts_duration + TAIL, max_available)
        if clip_duration < tts_duration:
            clip_duration = min(tts_duration, max_available)
        pts_ratio = 1.0
        if cap and tts_duration + TAIL > clip_duration + 0.05:
            # lời dài hơn đoạn hình của riêng cảnh này → chiếu chậm nhẹ (≤1.25×); vẫn thiếu thì tpad giữ khung cuối
            pts_ratio = round(min(1.25, (tts_duration + TAIL) / clip_duration), 4)
        sub_span_duration = clip_duration
        # đuôi TAIL thật sự có trong clip xuất (trước bị '-t tts_duration' cắt mất → hằng TAIL vô dụng, cảnh kết thúc
        # đúng lúc tắt tiếng, nghe cụt); hình thiếu thì bước tpad bên dưới giữ khung cuối
        tts_duration = max(tts_duration, clip_duration)
    (w, h) = resolution.split('x')
    vf = _crop_prefix(kwargs.get('crop_box'), kwargs.get('crop_fill', True), w, h) or \
        f'''scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black'''
    vf += f',fps={fps}'
    # vf = chỉ co hình vào khung xuất (+ viền đen) — đúng hệ toạ độ của khung xem trước nơi người dùng kéo vùng che.
    # vf_post = mọi biến đổi hình KHÁC (zoom theo cảnh, đổi tốc độ, lật gương, màu, phóng 3%) — chạy SAU bước làm mờ,
    # nếu chạy trước thì chữ gốc dời chỗ còn vùng che vẫn đứng yên → che lệch.
    vf_post = ''
    _v_scale = scene.get('_video_scale')
    _v_pos = str(scene.get('_video_position') or 'center').strip().lower()
    if _v_scale is not None:
        try:
            _v_scale = max(0.5, min(2.0, float(_v_scale)))
        except (TypeError, ValueError):
            _v_scale = 1.0
        if abs(_v_scale - 1.0) > 0.001:
            vf_post += f''',scale=iw*{_v_scale:.4f}:ih*{_v_scale:.4f}'''
            if _v_scale > 1.0:
                if _v_pos == 'top':
                    crop_y = '0'
                elif _v_pos == 'bottom':
                    crop_y = 'in_h-out_h'
                else:
                    crop_y = '(in_h-out_h)/2'
                vf_post += f''',crop={w}:{h}:(in_w-out_w)/2:{crop_y}'''
            else:
                if _v_pos == 'top':
                    pad_y = '0'
                elif _v_pos == 'bottom':
                    pad_y = 'oh-ih'
                else:
                    pad_y = '(oh-ih)/2'
                vf_post += f''',pad={w}:{h}:(ow-iw)/2:{pad_y}:color=black'''
    if pts_ratio != 1.0:
        vf_post += f''',setpts={pts_ratio:.4f}*PTS'''
    if mirror_video:
        vf_post += ',hflip'
    _extra_blur_boxes = []
    sub_cover_boxes = kwargs.get('sub_cover_boxes')
    if sub_cover_boxes is None:
        _legacy_box = kwargs.get('sub_cover_box')
        sub_cover_boxes = [_legacy_box] if _legacy_box else None
    if remove_old_sub and sub_cover_boxes:
        for box in sub_cover_boxes:
            if not box or len(box) != 4:
                continue
            try:
                (x_pct, y_pct, w_pct, h_pct) = [max(0, min(100, float(v))) / 100.0 for v in box]
            except (TypeError, ValueError):
                continue
            if w_pct > 0.01 and h_pct > 0.01:
                _extra_blur_boxes.append([x_pct, y_pct, x_pct + w_pct, y_pct + h_pct])
    elif remove_old_sub:
        pct = max(5, min(50, int(sub_cover_height))) / 100.0
        _extra_blur_boxes.append([0.0, 1.0 - pct, 1.0, 1.0])
    elif ai_sub_box:
        if len(ai_sub_box) == 2:
            (ymin, ymax) = ai_sub_box
            if ymax - ymin > 0.01:
                _extra_blur_boxes.append([0.0, ymin, 1.0, ymax])
    if remove_old_logo:
        size_pct = max(5, min(50, int(manual_logo_size))) / 100.0
        if manual_logo_corner == 'Trên-Trái':
            vf += f''',drawbox=x=0:y=0:w=iw*{size_pct:.4f}:h=ih*{size_pct:.4f}:color=black:t=fill'''
        elif manual_logo_corner == 'Trên-Phải':
            vf += f''',drawbox=x=iw-iw*{size_pct:.4f}:y=0:w=iw*{size_pct:.4f}:h=ih*{size_pct:.4f}:color=black:t=fill'''
        elif manual_logo_corner == 'Dưới-Trái':
            vf += f''',drawbox=x=0:y=ih-ih*{size_pct:.4f}:w=iw*{size_pct:.4f}:h=ih*{size_pct:.4f}:color=black:t=fill'''
        elif manual_logo_corner == 'Dưới-Phải':
            vf += f''',drawbox=x=iw-iw*{size_pct:.4f}:y=ih-ih*{size_pct:.4f}:w=iw*{size_pct:.4f}:h=ih*{size_pct:.4f}:color=black:t=fill'''
    elif ai_logo_box:
        if len(ai_logo_box) == 4:
            (ymin, xmin, ymax, xmax) = ai_logo_box
            w_pct = xmax - xmin
            h_pct = ymax - ymin
            if w_pct > 0.01:
                if h_pct > 0.01:
                    vf += f''',drawbox=x=iw*{xmin:.4f}:y=ih*{ymin:.4f}:w=iw*{w_pct:.4f}:h=ih*{h_pct:.4f}:color=black:t=fill'''
    vf_post += ',' + COLOR_PRESETS.get(str(kwargs.get('color_preset') or 'none'), COLOR_PRESETS['none'])
    vf_post += f''',crop=iw*0.97:ih*0.97,scale={w}:{h}'''
    _video_len = clip_duration * pts_ratio
    if (not is_reup or 'reup_out' in scene) and tts_duration - _video_len > 0.01:
        # lời dài hơn đoạn hình (đã chậm tối đa) → giữ khung cuối cho đủ lời
        vf_post += f''',tpad=stop_mode=clone:stop_duration={tts_duration - _video_len:.4f}'''
    vf_post = vf_post.lstrip(',')
    has_audio = _has_audio(source_video)
    orig_vol = scene.get('orig_volume', original_volume)
    # Giữ nhạc nền gốc (đã tách giọng): đoạn có lời Việt / câu gốc bị bỏ → dùng nhạc nền + tiếng động thay cho tiếng gốc
    # (không còn giọng Trung lẫn vào). Đoạn để tiếng gốc 100% (khoảng trống không lời Việt) vẫn dùng tiếng gốc thật.
    bg_audio = kwargs.get('bg_audio') or ''
    use_bg = bool(bg_audio) and os.path.isfile(bg_audio) and float(orig_vol) < 0.999 and has_audio
    if use_bg:
        orig_vol = max(0.0, min(2.0, float(kwargs.get('bg_volume', 0.9))))
    mute_orig = float(orig_vol) <= 0.001 or not has_audio
    atempo_filter = ''
    if is_reup and pts_ratio != 1.0 and not mute_orig:
        audio_speed = 1.0 / pts_ratio
        if audio_speed < 0.5:
            atempo_filter = f''',atempo=0.5,atempo={audio_speed / 0.5:.4f}'''
        elif audio_speed > 2.0:
            atempo_filter = f''',atempo=2.0,atempo={audio_speed / 2.0:.4f}'''
        else:
            atempo_filter = f''',atempo={audio_speed:.4f}'''
    subtitle_files = []
    sub_filters = []
    _sub_blur = []          # vùng làm mờ ngay sau từng dòng phụ đề: (x, y, w, h px, t bắt đầu, t kết thúc)
    if burn_subtitles and subtitle and not font_path:
        log_fn('   [WARN] Không tìm thấy font Unicode, bỏ qua burn phụ đề cảnh này')
        burn_subtitles = False
    if burn_subtitles and subtitle:
        if True:
            try:
                vid_h = int(h)
                vid_w = int(w)
            except Exception:
                (vid_h, vid_w) = (1080, 1920)
            sub_font_color = kwargs.get('sub_font_color', 'white')
            sub_font_size_factor = kwargs.get('sub_font_size_factor', 1.0)
            sub_border_width = kwargs.get('sub_border_width', 3)
            sub_border_color = kwargs.get('sub_border_color', 'black')
            sub_box_enabled = kwargs.get('sub_box_enabled', True)
            sub_box_color = kwargs.get('sub_box_color', 'black@0.5')
            sub_box_padding = kwargs.get('sub_box_padding', 12)
            sub_margin_v_pct = kwargs.get('sub_margin_v_pct', 0.06)
            sub_line_spacing = kwargs.get('sub_line_spacing', 6)
            sub_text_transform = kwargs.get('sub_text_transform', 'none')
            sub_position_mode = str(kwargs.get('sub_position_mode', 'bottom') or 'bottom').lower()
            sub_max_chars_per_chunk = kwargs.get('sub_max_chars_per_chunk', 56)
            sub_max_lines = kwargs.get('sub_max_lines', 2)
            sub_max_width_pct = max(0.3, min(0.95, float(kwargs.get('sub_max_width_pct', 0.82) or 0.82)))
            margin_v = max(20, int(vid_h * sub_margin_v_pct))
            sub_center_y = kwargs.get('sub_center_y_pct')        # có → tâm phụ đề đặt đúng tâm vùng che phụ đề cũ
            _sub_dur = sub_span_duration if sub_span_duration is not None else clip_duration
            _manual_chunks = scene.get('_manual_sub_chunks')
            chunks_timed = []
            if _manual_chunks:
                _dur_timeline = max(clip_end - clip_start, _raw_tts_duration, 0.5)
                _scale = _sub_dur / _dur_timeline if _dur_timeline > _sub_dur + 0.01 else 1.0
                for c in _manual_chunks:
                    ctext = str(c.get('text', '')).strip()
                    if not ctext:
                        continue
                    cs = max(0.0, min(_sub_dur, float(c.get('t_start', 0.0) or 0.0) * _scale))
                    ce = max(0.0, min(_sub_dur, float(c.get('t_end', 0.0) or 0.0) * _scale))
                    if ce > cs:
                        chunks_timed.append((ctext, cs, ce, c.get('style')))
            if not chunks_timed:
                chunks = _split_subtitle_chunks(subtitle, sub_max_chars_per_chunk, sub_max_lines)
                if chunks:
                    total_chars = sum((len(c) for c in chunks)) or 1
                    t_cur = 0.0
                    for (ci, chunk) in enumerate(chunks):
                        chunk_dur = _sub_dur * (len(chunk) / total_chars)
                        t_end = _sub_dur if ci == len(chunks) - 1 else min(_sub_dur, t_cur + chunk_dur)
                        chunks_timed.append((chunk, t_cur, t_end, None))
                        t_cur = t_end
            sub_filters = []
            for (ci, (chunk, t_cur, t_end, c_style)) in enumerate(chunks_timed):
                c_style = c_style or {}
                eff_font_color = c_style.get('color') or sub_font_color
                eff_size_factor = float(c_style.get('fontSize') or sub_font_size_factor or 1.0)
                eff_position_mode = str(c_style.get('position') or sub_position_mode or 'bottom').lower()
                eff_box_enabled = c_style['backgroundEnabled'] if c_style.get('backgroundEnabled') is not None else sub_box_enabled
                eff_box_color = c_style.get('background') or sub_box_color
                eff_font_name = c_style.get('fontName') or ''
                if eff_font_name:
                    eff_font_path = _find_system_font(eff_font_name) or font_path
                else:
                    eff_font_path = font_path
                if eff_font_path:
                    eff_font_esc = eff_font_path.replace('\\', '/').replace(':', '\\:')
                    eff_font_str = f'''fontfile=\'{eff_font_esc}\':'''
                else:
                    eff_font_str = ''
                eff_box_str = f'''box=1:boxcolor={eff_box_color}:boxborderw={sub_box_padding}:''' if eff_box_enabled else ''
                (wrapped, fontsize) = _fit_subtitle(chunk.upper() if str(sub_text_transform).lower() == 'uppercase' else chunk, vid_w, vid_h, font_size_factor=eff_size_factor, max_lines=sub_max_lines, line_spacing=sub_line_spacing, max_width_pct=sub_max_width_pct)
                subtitle_file = f'''{out_path}.subtxt{ci}'''
                subtitle_files.append(subtitle_file)
                with open(subtitle_file, 'w', encoding='utf-8') as _sf:
                    _sf.write(wrapped)
                subtxt_esc = subtitle_file.replace('\\', '/').replace(':', '\\:')
                center_y = sub_center_y if (sub_center_y is not None and not c_style.get('position')) else None
                if center_y is not None:
                    y_expr = f'h*{float(center_y):.4f}-text_h/2'
                elif eff_position_mode == 'top':
                    y_expr = f"{margin_v}"
                elif eff_position_mode == 'middle':
                    y_expr = '(h-text_h)/2'
                else:
                    y_expr = f'''h-text_h-{margin_v}'''
                clause = f'''drawtext={eff_font_str}textfile=\'{subtxt_esc}\':fontcolor={eff_font_color}:fontsize={fontsize}:borderw={sub_border_width}:bordercolor={sub_border_color}:line_spacing={sub_line_spacing}:x=(w-text_w)/2:y={y_expr}:{eff_box_str}enable=\'gte(t\\,{t_cur:.3f})*lt(t\\,{t_end:.3f})\''''
                sub_filters.append(clause)
                if c_style.get('bgBlur', kwargs.get('sub_bg_blur')):
                    reg = _text_region(wrapped, eff_font_path, fontsize, sub_line_spacing, sub_border_width, vid_w, vid_h, eff_position_mode, margin_v, center_y)
                    if reg:
                        _sub_blur.append((*reg, t_cur, t_end))
    _all_blur_boxes = list(blur_boxes or []) + _extra_blur_boxes
    (blur_chain, blur_last) = _build_blur_chain('vbase', _all_blur_boxes, clip_start=clip_start, clip_end=clip_end)
    has_wm = bool(watermark_path and os.path.exists(watermark_path))
    # Chữ Trung do AI quét (core/text_cover): làm mờ ngay trên hình GỐC, trước cắt/co/giãn → đúng chỗ, đúng lúc
    (src_chain, src_last) = _src_text_blur_chain(kwargs.get('text_regions'), clip_start, clip_duration, float(kwargs.get('text_blur_sigma') or 22),
                                                 style=kwargs.get('cover_style') or 'erase', src_size=src_dims(source_video))
    vin = f'[{src_last}]' if src_chain else '[0:v]'
    fc = (src_chain + ';' if src_chain else '') + f'''{vin}{vf}[vbase]'''
    last = 'vbase'
    if blur_chain:
        fc += ';' + blur_chain
        last = blur_last
    if vf_post:
        fc += f'; [{last}]{vf_post}[vgeo]'
        last = 'vgeo'
    # zoom chậm / tối viền: sau lớp che sub cũ (vùng che khớp chữ gốc), trước phụ đề mới (phụ đề không zoom theo)
    _fx = _scene_fx_filter(kwargs, i, w, h, fps, tts_duration)
    if _fx:
        fc += f'; [{last}]{_fx}[vfx]'
        last = 'vfx'
    # nền mờ sau phụ đề: làm mờ đúng khung chữ, chỉ lúc dòng đó hiện (sau hiệu ứng → khớp vị trí chữ trên khung cuối)
    for (bi, (bx, by, bw, bh, ta, tb)) in enumerate(_sub_blur):
        fc += (f'; [{last}]split[sba{bi}][sbc{bi}]; [sbc{bi}]crop={bw}:{bh}:{bx}:{by},gblur=sigma=18:steps=2[sbb{bi}]'
               f"; [sba{bi}][sbb{bi}]overlay={bx}:{by}:enable='gte(t\\,{ta:.3f})*lt(t\\,{tb:.3f})'[sbo{bi}]")
        last = f'sbo{bi}'
    for (si, sub_filter) in enumerate(sub_filters):
        out_lbl = f'''vsub{si}'''
        fc += f'''; [{last}]{sub_filter}[{out_lbl}]'''
        last = out_lbl
    wm_size_pct = max(5, min(40, int(watermark_size_pct or 14))) / 100.0
    wm_margin_x_pct = max(0.0, min(20.0, float(watermark_margin_x_pct or 0.0))) / 100.0
    wm_margin_y_pct = max(0.0, min(20.0, float(watermark_margin_y_pct or 0.0))) / 100.0
    wm_opacity = max(0.2, min(1.0, float(watermark_opacity or 1.0)))
    wm_width_px = max(48, int(int(w) * wm_size_pct))
    wm_margin_x_px = max(0, int(int(w) * wm_margin_x_pct))
    wm_margin_y_px = max(0, int(int(h) * wm_margin_y_pct))
    if watermark_corner == 'Trên-Trái':
        wm_x_expr = f"{wm_margin_x_px}"
        wm_y_expr = f"{wm_margin_y_px}"
    elif watermark_corner == 'Dưới-Trái':
        wm_x_expr = f"{wm_margin_x_px}"
        wm_y_expr = f'''H-h-{wm_margin_y_px}'''
    elif watermark_corner == 'Dưới-Phải':
        wm_x_expr = f'''W-w-{wm_margin_x_px}'''
        wm_y_expr = f'''H-h-{wm_margin_y_px}'''
    else:
        wm_x_expr = f'''W-w-{wm_margin_x_px}'''
        wm_y_expr = f"{wm_margin_y_px}"
    if has_wm:
        fc += f'''; [2:v]scale={wm_width_px}:-1,colorchannelmixer=aa={wm_opacity:.3f}[wm]; [{last}][wm]overlay={wm_x_expr}:{wm_y_expr}[v]'''
    else:
        fc += f'''; [{last}]copy[v]'''
    filter_complex_v = fc
    map_v = '[v]'
    enc = _video_encode_args(use_nvenc)
    if mute_orig:
        filter_complex = f'''{filter_complex_v};[1:a]apad[a]'''
        cmd = [FFMPEG_EXE, '-y', '-ss', str(clip_start), '-t', str(clip_duration), '-i', source_video, '-i', tts_path]
        if watermark_path:
            if os.path.exists(watermark_path):
                cmd.append('-i')
                cmd.append(watermark_path)
        cmd.extend(['-filter_complex', filter_complex, '-map', map_v, '-map', '[a]', '-t', str(tts_duration), *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), out_path])
    else:
        # nhạc nền đã tách là input sau watermark (watermark luôn là [2:v] nếu có)
        a_in = f'{3 if has_wm else 2}:a' if use_bg else '0:a'
        af_src = f'''[{a_in}]volume={orig_vol}{atempo_filter},atrim=duration={tts_duration},asetpts=N/SR/TB[ao]'''
        # tiếng gốc còn giọng → nén mạnh khi có lời Việt (không nghe 2 giọng chồng); nhạc nền đã tách → chỉ hạ nhẹ ~6dB
        # cho lời rõ mà nhạc vẫn liền mạch như phim lồng tiếng thật
        duck = 'threshold=-30dB:ratio=3:attack=40:release=500' if use_bg else 'threshold=-35dB:ratio=20:attack=50:release=400'
        filter_complex = f'''{filter_complex_v};{af_src};[1:a]asetpts=N/SR/TB[vo];[vo]asplit=2[vo_sc][vo_mix];[ao][vo_sc]sidechaincompress={duck}[ao_ducked];[ao_ducked][vo_mix]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.97:level=disabled,apad[a]'''
        cmd = [FFMPEG_EXE, '-y', '-ss', str(clip_start), '-t', str(clip_duration), '-i', source_video, '-i', tts_path]
        if watermark_path:
            if os.path.exists(watermark_path):
                cmd.append('-i')
                cmd.append(watermark_path)
        if use_bg:
            cmd += ['-ss', str(clip_start), '-t', str(clip_duration), '-i', bg_audio]
        cmd.extend(['-filter_complex', filter_complex, '-map', map_v, '-map', '[a]', '-t', str(tts_duration), *enc, '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), out_path])
    r = run_subprocess(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        fc_fb = (src_chain + ';' if src_chain else '') + f'''{vin}{vf}[vbase]'''
        last_fb = 'vbase'
        if blur_chain:
            fc_fb += ';' + blur_chain
            last_fb = blur_last
        if vf_post:
            fc_fb += f'; [{last_fb}]{vf_post}[vgeo_fb]'
            last_fb = 'vgeo_fb'
        if _fx:
            fc_fb += f'; [{last_fb}]{_fx}[vfx_fb]'
            last_fb = 'vfx_fb'
        for (si_fb, sf_fb) in enumerate(sub_filters):
            out_lbl_fb = f'''vsub_fb{si_fb}'''
            fc_fb += f'''; [{last_fb}]{sf_fb}[{out_lbl_fb}]'''
            last_fb = out_lbl_fb
        if has_wm:
            fc_fb += f'''; [2:v]scale={wm_width_px}:-1,colorchannelmixer=aa={wm_opacity:.3f}[wm]; [{last_fb}][wm]overlay={wm_x_expr}:{wm_y_expr}[v]'''
        else:
            fc_fb += f'''; [{last_fb}]copy[v]'''
        filter_complex_fb = fc_fb + '; [1:a]apad[a]'
        cmd_fb = [FFMPEG_EXE, '-y', '-ss', str(clip_start), '-t', str(clip_duration), '-i', source_video, '-i', tts_path]
        if watermark_path:
            if os.path.exists(watermark_path):
                cmd_fb.append('-i')
                cmd_fb.append(watermark_path)
        cmd_fb.extend(['-filter_complex', filter_complex_fb, '-map', map_v, '-map', '[a]', '-t', str(tts_duration), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), out_path])
        r2 = run_subprocess(cmd_fb, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if r2.returncode != 0:
            log_fn(f'''   [WARN] FFmpeg lỗi clip {i + 1}: {r2.stderr[slice(-300, None, None)]}''')
            _cleanup_files(subtitle_files)
            return False
    _cleanup_files(subtitle_files)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 0
def _cleanup_files(paths):
    for sf in paths:
        try:
            if os.path.exists(sf):
                os.remove(sf)
        except OSError:
            pass
# ── Hiệu ứng hình ──
COLOR_PRESETS = {
    'none': 'eq=brightness=0.02:saturation=1.06',
    'cinematic': 'eq=contrast=1.08:saturation=0.92:brightness=-0.01,colorbalance=rs=-0.04:bs=0.05:rh=0.06:bh=-0.05',
    'warm': 'colorbalance=rm=0.07:gm=0.02:bm=-0.07:rh=0.04:bh=-0.03,eq=saturation=1.08',
    'cool': 'colorbalance=rm=-0.05:bm=0.07:rh=-0.03:bh=0.05,eq=saturation=0.98',
    'vivid': 'eq=contrast=1.06:saturation=1.32:brightness=0.01',
    'vintage': 'curves=preset=vintage,eq=saturation=0.9',
    'bw': 'hue=s=0,eq=contrast=1.12',
}


def _scene_fx_filter(kwargs, idx, w, h, fps, duration):
    """Zoom chậm (Ken Burns — cảnh chẵn zoom vào, lẻ zoom ra) + tối viền. '' nếu không bật."""
    parts = []
    if kwargs.get('ken_burns'):
        amount = max(0.02, min(0.2, float(kwargs.get('ken_burns_zoom', 0.08) or 0.08)))
        frames = max(1, int(round(float(duration) * float(fps))))
        prog = f'min(on/{frames}\\,1)'
        z = f'1+{amount:.4f}*{prog}' if idx % 2 == 0 else f'{1 + amount:.4f}-{amount:.4f}*{prog}'
        # phóng 2 lần trước zoompan → toạ độ cắt mịn hơn, đỡ rung hình
        parts.append(f"scale={int(w) * 2}:{int(h) * 2}:flags=bicubic,zoompan=z='{z}':d=1"
                     f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}")
    if kwargs.get('vignette'):
        parts.append('vignette=angle=PI/5')
    return ','.join(parts)


TRANSITIONS = ('fade', 'dissolve', 'fadeblack', 'slideleft', 'wipeleft', 'zoomin', 'circleopen', 'smoothleft', 'radial', 'pixelize')
_RANDOM_POOL = ('fade', 'dissolve', 'slideleft', 'wipeleft', 'zoomin', 'circleopen', 'smoothleft', 'radial')


_XFADE_GROUP = 24          # số clip tối đa trong 1 lệnh ffmpeg (mỗi clip 1 luồng giải mã — 147 luồng 1080p cùng lúc dễ hỏng)


def _xfade_pass(inputs, lens, pads, kinds, d, fps, use_nvenc, output_path, temp_dir, tag, log_fn):
    """1 lệnh ffmpeg: nối `inputs` bằng xfade. `lens` = độ dài HÌNH từng input; tiếng mỗi input được cắt/độn cho bằng
    đúng độ dài hình (chênh vài ms do hình làm tròn theo khung) → không lệch cộng dồn qua hàng trăm clip.
    Input k kéo dài thêm pads[k] giây bằng khung hình cuối để có hình cho chuyển cảnh; chuyển cảnh k bắt đầu đúng lúc
    input k hết (mốc cộng dồn `lens`) → clip sau bắt đầu đúng thời điểm như ghép thường."""
    n = len(inputs)
    fc = []
    for k in range(n):
        pad = f',tpad=stop_mode=clone:stop_duration={pads[k]:.3f}' if pads[k] > 0 else ''
        fc.append(f'[{k}:v]fps={fps},format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS{pad}[v{k}]')
    (last, t) = ('v0', 0.0)
    for k in range(1, n):
        t += lens[k - 1]
        fc.append(f'[{last}][v{k}]xfade=transition={kinds[k - 1]}:duration={d:.3f}:offset={t:.3f}[x{k}]')
        last = f'x{k}'
    for k in range(n):
        fc.append(f'[{k}:a]aresample=44100,apad,atrim=duration={lens[k]:.6f},asetpts=N/SR/TB[a{k}]')
    fc.append(''.join(f'[a{k}]' for k in range(n)) + f'concat=n={n}:v=0:a=1[a]')
    script = os.path.join(temp_dir, f'xfade_{tag}.txt')
    with open(script, 'w', encoding='utf-8') as f:
        f.write(';\n'.join(fc))
    args = []
    for c in inputs:
        args += ['-i', c]

    def _run(enc):
        cmd = [FFMPEG_EXE, '-y', *args, '-/filter_complex', script, '-map', f'[{last}]', '-map', '[a]', *enc,
               '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', '-r', str(fps), output_path]
        return run_subprocess_heartbeat(cmd, log_fn=log_fn, label='Ghép clip + chuyển cảnh', text=True, encoding='utf-8', errors='replace')
    r = _run(_video_encode_args(use_nvenc))
    if r.returncode != 0 and use_nvenc:
        r = _run(_video_encode_args(False))
    if r.returncode != 0 or not os.path.exists(output_path):
        log_fn(f'   [WARN] xfade: {(r.stderr or "")[-300:]}')
        return False
    return True


def _concat_with_transitions(clips, output_path, temp_dir, log_fn, transition, duration, fps, use_nvenc):
    """Ghép có chuyển cảnh (xfade) mà KHÔNG làm ngắn video.

    xfade chồng 2 clip lên nhau d giây → video ngắn đi, lời đọc/phụ đề lệch dần. Nên mỗi clip (trừ clip cuối)
    được kéo dài d giây bằng khung hình cuối, chuyển cảnh bắt đầu đúng lúc clip cũ hết → clip sau vẫn bắt đầu
    đúng thời điểm như ghép thường; âm thanh ghép nối tiếp không đổi.
    Nhiều clip → ghép theo nhóm ≤ 24 clip rồi nối các nhóm (cũng có chuyển cảnh ở chỗ nối), mỗi lệnh ffmpeg mở ít luồng.
    """
    import random
    # mốc theo độ dài HÌNH (chính xác theo khung); tiếng từng clip được căn bằng đúng độ dài này trong _xfade_pass
    lens = [(_stream_duration(c, 'v:0') or _safe_duration(c)) for c in clips]
    if any(not L or L <= 0 for L in lens):
        return False
    d = max(0.2, min(1.5, float(duration or 0.5)))
    d = min(d, min(lens) * 0.45)            # có clip quá ngắn → rút ngắn chuyển cảnh
    if d < 0.1:
        return False
    n = len(clips)
    rnd = random.Random(n)                  # cố định theo số cảnh → dựng lại ra cùng kết quả
    kinds = [rnd.choice(_RANDOM_POOL) if transition == 'random' else (transition if transition in TRANSITIONS else 'fade') for _ in range(n - 1)]
    log_fn(f'   Ghép {n} clip có chuyển cảnh ({transition}, {d:.2f}s)...')
    if n <= _XFADE_GROUP:
        ok = _xfade_pass(clips, lens, [d] * (n - 1) + [0], kinds, d, fps, use_nvenc, output_path, temp_dir, 'all', log_fn)
    else:
        # Lượt 1: từng nhóm. Clip cuối mỗi nhóm (trừ nhóm cuối) cũng kéo dài d → còn hình cho chuyển cảnh nối nhóm.
        groups = [list(range(i, min(n, i + _XFADE_GROUP))) for i in range(0, n, _XFADE_GROUP)]
        (parts, plens) = ([], [])
        for (gi, g) in enumerate(groups):
            final = gi == len(groups) - 1
            part = os.path.join(temp_dir, f'xfade_part{gi:02d}.mp4')
            pads = [d] * len(g)
            if final:
                pads[-1] = 0
            log_fn(f'   Chuyển cảnh nhóm {gi + 1}/{len(groups)} ({len(g)} clip)...')
            if not _xfade_pass([clips[k] for k in g], [lens[k] for k in g], pads, [kinds[k] for k in g[:-1]], d, fps, use_nvenc,
                               part, temp_dir, f'g{gi:02d}', log_fn):
                return False
            parts.append(part)
            plens.append(sum(lens[k] for k in g))   # = độ dài tiếng của nhóm (hình dư thêm d ở cuối)
        # Lượt 2: nối các nhóm — hình mỗi nhóm đã dư d giây ở cuối nên không kéo thêm
        joins = [kinds[g[-1]] for g in groups[:-1]]
        ok = _xfade_pass(parts, plens, [0] * len(parts), joins, d, fps, use_nvenc, output_path, temp_dir, 'join', log_fn)
        for pth in parts:
            try:
                os.remove(pth)
            except OSError:
                pass
    if not ok:
        return False
    # Chốt chặn: ghép xong mà luồng hình ngắn hơn luồng tiếng (hình dừng giữa chừng) → báo hỏng để ghép thường
    (vd, ad) = (_stream_duration(output_path, 'v:0'), _stream_duration(output_path, 'a:0'))
    if vd > 0 and ad > 0 and ad - vd > 1.0:
        log_fn(f'   [WARN] Ghép chuyển cảnh lỗi: hình chỉ dài {vd:.1f}s / tiếng {ad:.1f}s — ghép lại kiểu thường')
        return False
    return True


def _stream_duration(path, stream):
    """Độ dài 1 luồng (v:0 / a:0) theo ffprobe; 0 nếu không đọc được."""
    try:
        r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-select_streams', stream, '-show_entries', 'stream=duration', '-of', 'csv=p=0', path],
                           capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return float((r.stdout or '').strip().splitlines()[0])
    except Exception:
        return 0.0


def _concat_clips(clips, output_path, temp_dir, log_fn):
    list_file = os.path.join(temp_dir, 'concat_list.txt')
    with open(list_file, 'w', encoding='utf-8') as f:
        for c in clips:
            safe = c.replace('\\', '/').replace("'", "\\'")
            f.write(f'''file \'{safe}\'\n''')
    cmd = [FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', output_path]
    r = run_subprocess_heartbeat(cmd, log_fn=log_fn, label='Ghép clip cuối', text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        log_fn('   Ghép nối (copy video/re-encode audio) thất bại, tiến hành re-encode toàn bộ...')
        cmd2 = [FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '1', output_path]
        r2 = run_subprocess_heartbeat(cmd2, log_fn=log_fn, label='Ghép clip cuối (re-encode toàn bộ)', text=True, encoding='utf-8', errors='replace')
        if r2.returncode != 0:
            log_fn(f'''   [LỖI] Concat: {r2.stderr[slice(None, 300, None)]}''')
            return False
    return os.path.exists(output_path)
def _build_blur_chain(in_label, boxes, clip_start=0.0, clip_end=None):
    if not boxes:
        return ('', in_label)
    parts = []
    cur = in_label
    idx = 0
    for b in boxes:
        (t_start, t_end) = (None, None)
        if isinstance(b, dict):
            box_xy = b.get('box')
            t_start = b.get('t_start')
            t_end = b.get('t_end')
        else:
            box_xy = b
        try:
            (x1, y1, x2, y2) = [float(v) for v in box_xy]
        except Exception:
            continue
        (x1, x2) = sorted((x1, x2))
        (y1, y2) = sorted((y1, y2))
        # nới 0.5% mỗi phía: viền / bóng chữ thường rộng hơn chỗ người dùng kéo, và zoom sau bước làm mờ hay lộ 1 hàng mép
        PAD = 0.005
        (x1, x2) = (max(0.0, min(1.0, x1 - PAD)), max(0.0, min(1.0, x2 + PAD)))
        (y1, y2) = (max(0.0, min(1.0, y1 - PAD)), max(0.0, min(1.0, y2 + PAD)))
        dw = x2 - x1
        dh = y2 - y1
        if dw < 0.01 or dh < 0.01:
            continue
        enable_clause = ''
        if t_start is not None or t_end is not None:
            t_start = float(t_start) if t_start is not None else 0.0
            t_end = float(t_end) if t_end is not None else 1000000000.0
            if clip_end is not None and (t_start >= clip_end or t_end <= clip_start):
                continue
            rel_start = max(0.0, t_start - clip_start)
            rel_end = t_end - clip_start if clip_end is None else min(clip_end - clip_start, t_end - clip_start)
            enable_clause = f''':enable=\'between(t\\,{rel_start:.3f}\\,{rel_end:.3f})\''''
        a = f'''ba{idx}'''
        c = f'''bc{idx}'''
        nxt = f'''bm{idx}'''
        # mép trái/trên làm tròn XUỐNG, mép phải/dưới làm tròn LÊN (số chẵn cho yuv420) và dán lại đúng toạ độ đã cắt
        # — trước: cắt ở toạ độ làm tròn nhưng dán ở W*x không làm tròn → khối mờ trượt 1px, lộ 1 hàng điểm ảnh chữ
        cx = f'''trunc(iw*{x1:.4f}/2)*2'''
        cy = f'''trunc(ih*{y1:.4f}/2)*2'''
        cw = f'''min(iw\\,ceil(iw*{x2:.4f}/2)*2)-{cx}'''
        ch = f'''min(ih\\,ceil(ih*{y2:.4f}/2)*2)-{cy}'''
        ox = f'''trunc(W*{x1:.4f}/2)*2'''
        oy = f'''trunc(H*{y1:.4f}/2)*2'''
        parts.append(f'''[{cur}]split[{a}][{c}]''')
        parts.append(f'''[{c}]crop={cw}:{ch}:{cx}:{cy},gblur=sigma=20:steps=3[{c}b]''')
        parts.append(f'''[{a}][{c}b]overlay={ox}:{oy}{enable_clause}[{nxt}]''')
        cur = nxt
        idx += 1
    if idx == 0:
        return ('', in_label)
    return (';'.join(parts), cur)
def _fit_subtitle(text, vid_w, vid_h, font_size_factor=1.0, max_lines=2, line_spacing=6, max_width_pct=0.82):
    """Chữ phụ đề → (chữ đã ngắt dòng, cỡ chữ) vừa khung: thu cỡ chữ tới min_font; vẫn quá số dòng thì nới độ dài dòng và
    thu tiếp cỡ chữ cho vừa bề ngang — KHÔNG bao giờ trả về quá max_lines dòng. Chữ IN HOA rộng ~0.7× cỡ chữ (thường 0.6×)."""
    text = ' '.join(((text or '')).split())
    if not text:
        return ('', max(24, int(vid_h // 24 * font_size_factor)))
    max_lines = max(1, int(max_lines or 2))
    max_block_h = vid_h * 0.28
    base_font = max(24, int(vid_h // 26 * font_size_factor))
    min_font = max(18, int(vid_h // 42 * font_size_factor))
    safe_w = vid_w * max(0.3, min(0.95, float(max_width_pct or 0.82)))
    letters = [c for c in text if c.isalpha()]
    upper = len(letters) > 0 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6
    cw = 0.7 if upper else 0.6                    # bề ngang 1 ký tự ≈ cw × cỡ chữ
    fontsize = base_font
    while True:
        chars_per_line = max(16, int(safe_w / (fontsize * cw)))
        wrapped = _wrap_text(text, max_len=chars_per_line)
        n_lines = wrapped.count('\n') + 1
        line_h = fontsize * 1.15 + max(0, int(line_spacing))
        if n_lines <= max_lines and n_lines * line_h <= max_block_h:
            return (wrapped, int(fontsize))
        if fontsize <= min_font:
            break
        fontsize -= 2
    # tới cỡ nhỏ nhất vẫn quá số dòng → ép về max_lines dòng, thu cỡ chữ cho dòng dài nhất vừa bề ngang
    wrapped = _wrap_lines(text, max(16, int(safe_w / (fontsize * cw))), max_lines)
    longest = max(len(x) for x in wrapped.split('\n'))
    fontsize = max(14, min(int(fontsize), int(safe_w / (max(1, longest) * cw))))
    return (wrapped, int(fontsize))


def _split_subtitle_chunks(text, max_chars_per_chunk=56, max_lines_per_chunk=2):
    text = text or ''
    if '||' in text:
        out = []
        for part in text.split('||'):
            part = part.strip()
            if part:
                out.extend(_auto_split_subtitle_chunks(part, max_chars_per_chunk, max_lines_per_chunk))
        return out
    return _auto_split_subtitle_chunks(text, max_chars_per_chunk, max_lines_per_chunk)
def _auto_split_subtitle_chunks(text, max_chars_per_chunk=56, max_lines_per_chunk=2):
    text = ' '.join(((text or '')).split())
    max_chars_per_chunk = max(18, int(max_chars_per_chunk or 56))
    max_lines_per_chunk = max(1, int(max_lines_per_chunk or 2))
    if not text:
        return []
    if len(text) <= max_chars_per_chunk:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars_per_chunk:
            chunks.append(remaining)
            break
        window = remaining[slice(None, max_chars_per_chunk + 1, None)]
        cut = -1
        for i in range(len(window) - 1, int(len(window) * 0.4), -1):
            if window[i] in '.!?,;':
                cut = i + 1
                break
        if cut == -1:
            sp = window.rfind(' ')
            cut = sp if sp > 0 else max_chars_per_chunk
        chunks.append(remaining[slice(None, cut, None)].strip())
        remaining = remaining[slice(cut, None, None)].strip()
    chunks = [c for c in chunks if c]
    _MIN_CHUNK_CHARS = 20
    merged = []
    for c in chunks:
        if merged and len(c) < _MIN_CHUNK_CHARS:
            combined = ((merged[-1] + ' ' + c)).strip()
            if len(combined) <= max_chars_per_chunk:
                merged[-1] = combined
                continue
        merged.append(c)
    return merged
def _wrap_lines(text, max_len, max_lines):
    """Ngắt dòng ~max_len ký tự nhưng KHÔNG quá max_lines dòng (nới độ dài dòng khi cần) — SRT 28 ký tự/dòng hay ra 3 dòng."""
    n = max(1, int(max_lines or 2))
    width = max(8, int(max_len))
    wrapped = _wrap_text(text, max_len=width)
    while wrapped.count('\n') + 1 > n and width < len(text):
        width += 2
        wrapped = _wrap_text(text, max_len=width)
    return wrapped


def _wrap_text(text, max_len=50):
    if len(text) <= max_len:
        return text
    words = text.split()
    lines = []
    cur = ''
    for w in words:
        if len(cur) + len(w) + 1 <= max_len:
            cur = ((cur + ' ' + w)).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return '\n'.join(lines)