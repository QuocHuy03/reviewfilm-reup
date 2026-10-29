"""Kiểm tra chất lượng video đã xuất (QA) — soi file thật bằng ffprobe/ffmpeg, không cần AI.

Một lượt ffmpeg (video thu nhỏ cho nhanh) đo: màn hình đen, hình đứng, âm lượng.
Kết quả: {'score': 0-100, 'checks': [{id, label, status: ok|warn|fail, detail}], 'at': iso}
"""
import json
import os
import re
import subprocess
from datetime import datetime

BLACK_MIN_S = 1.5        # đoạn đen dài hơn → cảnh báo
FREEZE_MIN_S = 3.0       # hình đứng yên lâu hơn → cảnh báo
QUIET_MEAN_DB = -32.0    # âm lượng trung bình thấp hơn → quá nhỏ
CLIP_MAX_DB = -0.1       # đỉnh cao hơn → có thể rè
DUR_TOLERANCE = 0.10
OVERLAP_S = 1.0          # Review: lời lấn sang hình cảnh sau quá mức này → hình bị lặp
SHORT_RATIO = 0.5        # Review: lời ngắn hơn nửa đoạn hình (hình > 4s) → bỏ phí hình
LABEL_RE = re.compile(r'^\s*(?:\[\s*Cảnh|\*\*\s*Cảnh|Cảnh\s+\S+\s*[:：])', re.IGNORECASE)


def scene_fit(scenes, reup=False, target_lang='vi'):   # target_lang: chỉ đo theo giây → mọi ngôn ngữ như nhau
    """Cảnh nào lời đọc không vừa hình. → [{'scene', 'kind': long|short, 'why', 'fit': số giây lời nên có}]

    Review: video_editor đọc hình gốc từ clip_start dài đúng bằng lời (không kéo giãn) → lời dài thì
            lấn sang hình của cảnh sau (lặp hình), lời ngắn thì bỏ phí hình.
    Reup:   hình tốc độ thật; lời dài thì mượn khoảng lặng → giọng nhanh (≤1.35×) → hình chậm (≤1.25×) — giống video_editor.
            Báo 'long' khi phải tăng tốc giọng mạnh / chậm hình (nên rút gọn lời); 'short' khi lời quá ngắn so với câu gốc.
    """
    from core.video_editor import reup_fit
    out = []
    starts = [float(s.get('clip_start') or 0) for s in scenes]
    for (i, s) in enumerate(scenes):
        start, end = starts[i], float(s.get('clip_end') or 0)
        clip, tts = end - start, float(s.get('tts_duration') or 0)
        if tts <= 0.1 or clip <= 0.1:
            continue
        if reup:
            later = [x for x in starts if x > start + 0.05]
            room = (min(later) - start) if later else clip + tts
            (_, _, pts, at) = reup_fit(clip, room, tts)
            if pts > 1.0:
                out.append({'scene': i, 'kind': 'long', 'fit': round(max(clip, room), 1),
                            'why': f'lời {tts:.1f}s quá dài so với {max(clip, room):.1f}s tới câu sau → giọng nhanh {at:.2f}× và hình chậm {pts:.2f}×'})
            elif at > 1.2:
                out.append({'scene': i, 'kind': 'long', 'fit': round(max(clip, room), 1),
                            'why': f'lời {tts:.1f}s dài → giọng phải đọc nhanh {at:.2f}×'})
            elif clip > 3 and tts < clip * 0.35:
                out.append({'scene': i, 'kind': 'short', 'fit': round(clip, 1),
                            'why': f'lời {tts:.1f}s / câu gốc {clip:.1f}s → lặng {clip - tts:.1f}s'})
            continue
        later = [x for x in starts if x > start + 0.05]
        nxt = min(later) if later else None
        # Hình "của riêng" cảnh này: tới clip_end nhưng không quá điểm bắt đầu cảnh sau (clip_end có thể đã bị nới lấn sang)
        own = min(clip, nxt - start) if nxt is not None else clip
        if nxt is not None and start + tts - nxt > OVERLAP_S:
            out.append({'scene': i, 'kind': 'long', 'fit': round(nxt - start, 1),
                        'why': f'lời {tts:.0f}s dài hơn hình {nxt - start:.0f}s → lặp {start + tts - nxt:.0f}s hình cảnh sau'})
        elif own > 4 and tts < own * SHORT_RATIO:
            out.append({'scene': i, 'kind': 'short', 'fit': round(own, 1),
                        'why': f'lời {tts:.0f}s / hình {own:.0f}s → bỏ phí {own - tts:.0f}s hình'})
    return out


def used_span(s, reup=False):
    """Đoạn hình gốc cảnh thật sự chiếu trong video xuất (giây trên video gốc)."""
    start = float(s.get('clip_start') or 0)
    if reup:
        return start, float(s.get('clip_end') or 0)
    return start, start + float(s.get('tts_duration') or 0)


def footage_repeats(scenes, reup=False):
    """Cảnh chiếu lại đoạn hình gốc mà một cảnh ĐỨNG TRƯỚC nó (trong video xuất) đã chiếu — mọi cặp, không chỉ liền kề.

    Bỏ qua trường hợp cảnh trước lời dài lấn sang (đã báo ở scene_fit 'long' của cảnh trước).
    → [{'scene', 'kind': 'dup', 'with', 'why', 'fit'}]"""
    out = []
    spans = [used_span(s, reup) for s in scenes]
    for i in range(len(scenes)):
        a0, a1 = spans[i]
        for j in range(i):
            b0, b1 = spans[j]
            ov = min(a1, b1) - max(a0, b0)
            if ov <= OVERLAP_S:
                continue
            if not reup and b0 < a0 - 0.05:      # cảnh j bắt đầu trước, lời dài lấn sang hình cảnh i → lỗi của j
                continue
            out.append({'scene': i, 'kind': 'dup', 'with': j, 'fit': round(a1 - a0, 1),
                        'why': f'chiếu lại {ov:.0f}s hình đã dùng ở cảnh #{j + 1}'})
            break
    return out


_WORD = re.compile(r'\w+', re.UNICODE)
TEXT_OVERLAP = 0.2       # tỉ lệ cụm 3 từ trùng với một cảnh trước → lặp ý
TEXT_SHARED_MIN = 3      # hoặc trùng từ 3 cụm 3 từ "hiếm" trở lên


def _grams(text, n=3):
    from core.video_editor import _is_unspaced
    if _is_unspaced(text):                     # Trung / Nhật / Thái: không có dấu cách → mỗi 2 ký tự tính 1 "từ"
        t = ''.join(ch for ch in (text or '') if ch.isalnum())
        w = [t[k:k + 2] for k in range(0, len(t) - 1, 2)]
    else:
        w = [x.lower() for x in _WORD.findall(text or '')]
    return {tuple(w[k:k + n]) for k in range(len(w) - n + 1)}, w


def text_repeats(scenes):
    """Lời đọc lặp: trùng nhiều cụm 3 từ với một cảnh trước (kể lại cùng ý), hoặc mở đầu y hệt cảnh liền trước.
    → [{'scene', 'kind': 'text', 'with', 'why'}]"""
    out = []
    grams = [_grams(s.get('voiceover')) for s in scenes]
    # Cụm có ở hầu hết các cảnh (tên nhân vật, cách gọi chung) là bình thường — không tính là lặp
    df = {}
    for (g, _) in grams:
        for x in g:
            df[x] = df.get(x, 0) + 1
    common = {x for (x, n) in df.items() if len(scenes) >= 3 and n >= max(3, len(scenes) * 0.6)}
    for i in range(1, len(scenes)):
        gi, wi = grams[i]
        if len(wi) < 6:
            continue
        gi = gi - common
        hit = None
        for j in range(i):
            gj = grams[j][0] - common
            shared = gi & gj
            if gi and gj and (len(shared) >= TEXT_SHARED_MIN or len(shared) / min(len(gi), len(gj)) >= TEXT_OVERLAP):
                sample = ' '.join(sorted(shared)[0])
                hit = (j, f'lặp ý với cảnh #{j + 1} ({len(shared)} cụm trùng, vd "{sample}")')
                break
        if not hit and wi[:3] == grams[i - 1][1][:3]:
            hit = (i - 1, f'mở đầu giống hệt cảnh #{i} ("{" ".join(wi[:3])}…")')
        if hit:
            out.append({'scene': i, 'kind': 'text', 'with': hit[0], 'why': hit[1]})
    return out


def _run(cmd, timeout):
    from core.utils import _HIDE, _budgeted
    flags = _HIDE                                # ưu tiên thấp + luồng theo ngân sách CPU chung
    cmd = _budgeted(cmd)
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, creationflags=flags)


def _probe(path):
    from core.utils import FFPROBE_EXE
    r = _run([FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height,r_frame_rate,avg_frame_rate,duration',
              '-of', 'json', path], 60)
    data = json.loads(r.stdout or '{}')
    v = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), {})
    a = next((s for s in data.get('streams', []) if s.get('codec_type') == 'audio'), None)
    # avg_frame_rate = tốc độ thật (r_frame_rate là "tốc độ nền": ghép clip khác timebase ra 120 fps ảo)
    rate = v.get('avg_frame_rate') if v.get('avg_frame_rate') not in (None, '', '0/0') else v.get('r_frame_rate')
    num, _, den = (rate or '0/1').partition('/')
    fps = float(num) / float(den or 1) if float(den or 1) else 0
    return {'duration': float(data.get('format', {}).get('duration') or 0), 'width': v.get('width', 0), 'height': v.get('height', 0),
            'fps': round(fps, 2), 'has_audio': a is not None,
            'v_duration': float(v.get('duration') or 0), 'a_duration': float((a or {}).get('duration') or 0)}


def _scan(path, duration, has_audio):
    """Một lượt ffmpeg: blackdetect + freezedetect (video 320px) + volumedetect."""
    from core.utils import FFMPEG_EXE
    vchain = '[0:v]scale=320:-2,blackdetect=d=0.5:pix_th=0.10,freezedetect=n=0.003:d=1[v]'
    cmd = [FFMPEG_EXE, '-hide_banner', '-nostats', '-i', path, '-filter_complex',
           vchain + (';[0:a]volumedetect[a]' if has_audio else ''), '-map', '[v]'] + (['-map', '[a]'] if has_audio else []) + ['-f', 'null', '-']
    r = _run(cmd, max(120, int(duration * 3)))
    err = r.stderr or ''
    blacks = [(float(s), float(d)) for (s, d) in re.findall(r'black_start:([\d.]+) black_end:[\d.]+ black_duration:([\d.]+)', err)]
    starts = [float(x) for x in re.findall(r'freeze_start: ([\d.]+)', err)]
    durs = [float(x) for x in re.findall(r'freeze_duration: ([\d.]+)', err)]
    freezes = list(zip(starts, durs))
    mean = re.search(r'mean_volume: (-?[\d.]+) dB', err)
    peak = re.search(r'max_volume: (-?[\d.]+) dB', err)
    return blacks, freezes, (float(mean.group(1)) if mean else None), (float(peak.group(1)) if peak else None)


def video_speed(cfg):
    try:
        return max(0.5, min(2.0, float(str(cfg.get('video_speed', '1.0x')).split('x')[0] or 1.0)))
    except ValueError:
        return 1.0


def media_duration(path):
    try:
        return _probe(path)['duration'] if path and os.path.isfile(path) else 0.0
    except Exception:
        return 0.0


def _fmt(t):
    return f'{int(t // 60):02d}:{t % 60:04.1f}'


def check_video(output_path, scenes=None, cfg=None, srt_path=''):
    """Chạy toàn bộ kiểm tra cho 1 video đã xuất. Không ném lỗi — lỗi đo đạc thành một mục 'fail'."""
    cfg = cfg or {}
    scenes = [s for s in (scenes or []) if not s.get('excluded')]
    checks = []

    def add(cid, label, status, detail, **data):
        checks.append({'id': cid, 'label': label, 'status': status, 'detail': detail, **({'data': data} if data else {})})

    if not output_path or not os.path.isfile(output_path):
        add('file', 'File video', 'fail', 'Không tìm thấy file video đã xuất.')
        return _result(checks)
    try:
        info = _probe(output_path)
    except Exception as e:
        add('file', 'File video', 'fail', f'Không đọc được video: {str(e)[:120]}')
        return _result(checks)
    dur = info['duration']
    add('file', 'File video', 'ok' if dur > 0 else 'fail',
        f"{_fmt(dur)} · {info['width']}×{info['height']} · {info['fps']:.0f} fps · {os.path.getsize(output_path) / 1_048_576:.1f} MB")

    # Luồng hình phải dài bằng luồng tiếng — ghép lỗi có thể làm hình dừng sớm còn tiếng chạy tiếp (video "đứng" ở giữa)
    (vd, ad) = (info['v_duration'], info['a_duration'])
    if vd > 0 and ad > 0:
        gap = ad - vd
        add('av_length', 'Hình chạy hết video', 'ok' if gap <= 1.0 else 'fail',
            f'Hình {_fmt(vd)} · tiếng {_fmt(ad)}' + ('' if gap <= 1.0 else f' — mất hình từ {_fmt(vd)} tới hết video (chỉ còn tiếng)'),
            video=round(vd, 2), audio=round(ad, 2))

    # Khung hình đúng lựa chọn
    want = str(cfg.get('target_resolution') or '1920x1080')
    try:
        ww, wh = (int(x) for x in want.lower().split('x'))
        same = (info['width'], info['height']) == (ww, wh)
        add('resolution', 'Khung hình', 'ok' if same else 'warn',
            f"{info['width']}×{info['height']}" + ('' if same else f' — đã chọn {ww}×{wh}'))
    except ValueError:
        pass

    # Độ dài so với lời đọc (+ intro/outro). Reup giữ trọn phim gốc (đoạn không thoại để im lời) → không so được với lời đọc
    if scenes and cfg.get('mode', 'review') == 'review':
        expected = sum(float(s.get('tts_duration') or 0) for s in scenes)
        extra = media_duration(cfg.get('intro_path')) + media_duration(cfg.get('outro_path'))
        expected += extra
        expected /= video_speed(cfg)          # tốc độ video áp cho cả video (kể cả intro/outro)
        if expected > 0:
            diff = (dur - expected) / expected
            st = 'ok' if abs(diff) <= DUR_TOLERANCE else 'warn' if abs(diff) <= 0.3 else 'fail'
            add('duration', 'Độ dài khớp lời đọc', st,
                f'Video {_fmt(dur)} / lời đọc{" + intro/outro" if extra else ""} {_fmt(expected)} ({diff * 100:+.0f}%)', diff=round(diff, 3))

    # Khớp hình – lời từng cảnh (theo đúng cách video_editor dựng từng chế độ)
    if scenes:
        issues = scene_fit(scenes, reup=cfg.get('mode', 'review') != 'review')
        add('sync', 'Khớp hình – lời từng cảnh', 'ok' if not issues else 'warn',
            'Lời đọc vừa khít hình mọi cảnh' if not issues
            else f'{len(issues)}/{len(scenes)} cảnh: ' + '; '.join(f"#{x['scene'] + 1} {x['why']}" for x in issues[:4]) + ('…' if len(issues) > 4 else ''),
            **({'issues': issues} if issues else {}))

    # Lặp hình (mọi cặp cảnh) & lặp lời
    if len(scenes) > 1:
        reup = cfg.get('mode', 'review') != 'review'
        dups = footage_repeats(scenes, reup)
        add('footage', 'Không lặp hình', 'ok' if not dups else 'warn',
            'Mỗi đoạn hình gốc chỉ chiếu một lần' if not dups
            else f'{len(dups)} cảnh: ' + '; '.join(f"#{x['scene'] + 1} {x['why']}" for x in dups[:4]) + ('…' if len(dups) > 4 else ''),
            **({'issues': dups} if dups else {}))
        reps = text_repeats(scenes)
        add('repeat', 'Không lặp lời', 'ok' if not reps else 'warn',
            'Các cảnh kể ý khác nhau, mở đầu đa dạng' if not reps
            else f'{len(reps)} cảnh: ' + '; '.join(f"#{x['scene'] + 1} {x['why']}" for x in reps[:4]) + ('…' if len(reps) > 4 else ''),
            **({'issues': reps} if reps else {}))

    # Nhãn "[Cảnh N]" lọt vào lời đọc → TTS đọc to
    labelled = [i for (i, s) in enumerate(scenes) if LABEL_RE.match(s.get('voiceover') or '')]
    if scenes:
        add('labels', 'Lời đọc sạch', 'ok' if not labelled else 'fail',
            'Không có nhãn / ký hiệu lọt vào lời đọc' if not labelled
            else f'{len(labelled)} cảnh có nhãn "[Cảnh…]" bị đọc thành tiếng: ' + ', '.join(f'#{i + 1}' for i in labelled[:8]),
            **({'scenes': labelled} if labelled else {}))

    # Âm thanh, màn đen, hình đứng
    try:
        blacks, freezes, mean, peak = _scan(output_path, dur, info['has_audio'])
    except Exception as e:
        add('scan', 'Quét hình & tiếng', 'fail', f'Không quét được: {str(e)[:120]}')
        blacks, freezes, mean, peak = [], [], None, None
    if not info['has_audio']:
        add('audio', 'Âm thanh', 'fail', 'Video không có track âm thanh.')
    elif mean is not None:
        if mean < QUIET_MEAN_DB:
            add('audio', 'Âm thanh', 'warn', f'Quá nhỏ: trung bình {mean:.1f} dB (nên > {QUIET_MEAN_DB:.0f} dB)', issue='quiet')
        elif peak is not None and peak >= CLIP_MAX_DB:
            add('audio', 'Âm thanh', 'warn', f'Đỉnh {peak:.1f} dB — có thể bị rè (clipping)', issue='clip')
        else:
            add('audio', 'Âm thanh', 'ok', f'Trung bình {mean:.1f} dB · đỉnh {peak:.1f} dB')
    long_black = [(s, d) for (s, d) in blacks if d >= BLACK_MIN_S]
    add('black', 'Màn hình đen', 'ok' if not long_black else 'warn',
        'Không có đoạn đen kéo dài' if not long_black
        else ', '.join(f'{_fmt(s)} ({d:.1f}s)' for (s, d) in long_black[:5]),
        **({'ranges': long_black} if long_black else {}))
    long_freeze = [(s, d) for (s, d) in freezes if d >= FREEZE_MIN_S]
    add('freeze', 'Hình đứng yên', 'ok' if not long_freeze else 'warn',
        'Không có đoạn hình đứng lâu' if not long_freeze
        else ', '.join(f'{_fmt(s)} ({d:.1f}s)' for (s, d) in long_freeze[:5]) + ' — thường do lời dài hơn hình',
        **({'ranges': long_freeze} if long_freeze else {}))

    # Phụ đề
    if cfg.get('burn_subtitles', True) is not False and scenes:
        if srt_path and os.path.isfile(srt_path):
            with open(srt_path, encoding='utf-8-sig', errors='replace') as fh:
                n = len(re.findall(r'^\d+\s*$', fh.read(), flags=re.M))
            add('subtitle', 'Phụ đề', 'ok' if n else 'warn', f'{n} dòng phụ đề · {os.path.basename(srt_path)}')
        else:
            add('subtitle', 'Phụ đề', 'warn', 'Không thấy file phụ đề đi kèm.', missing=True)

    # Cảnh bị bỏ khỏi video: bước dựng ghi mốc thật (out_start / out_end) cho mọi cảnh dựng được — cảnh thiếu mốc
    # trong khi cảnh khác có = dựng lỗi, bị bỏ (mất lời, phụ đề các câu sau dễ lệch). Đếm dòng SRT không bắt được lỗi này.
    if scenes and any('out_start' in s for s in scenes):
        lost = [i + 1 for (i, s) in enumerate(scenes) if 'out_start' not in s]
        add('clips', 'Cảnh trong video', 'ok' if not lost else 'fail',
            f'Đủ {len(scenes)} cảnh' if not lost
            else f"{len(lost)} cảnh bị bỏ vì dựng lỗi: {', '.join(f'#{n}' for n in lost[:12])}" + (' …' if len(lost) > 12 else ''),
            **({'scenes': [n - 1 for n in lost]} if lost else {}))
    return _result(checks)


def _result(checks):
    weight = {'ok': 1.0, 'warn': 0.5, 'fail': 0.0}
    score = round(100 * sum(weight[c['status']] for c in checks) / max(1, len(checks)))
    return {'score': score, 'checks': checks, 'at': datetime.now().isoformat(timespec='seconds')}
