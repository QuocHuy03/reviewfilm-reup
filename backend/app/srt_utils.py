"""SRT helpers — viết lại sạch từ main_qt.py (_segments_to_srt, _rechunk_srt, _parse_srt...)."""
import re

_TS_RE = re.compile(r'(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})')


def fmt_ts(sec):
    """Giây → hh:mm:ss,mmm. Làm tròn ms TRƯỚC khi tách giờ/phút/giây (59.9996s → 00:01:00,000, không ra 00:00:60,000)."""
    ms_total = int(round(max(0.0, float(sec)) * 1000))
    (h, rem) = divmod(ms_total, 3600000)
    (m, rem) = divmod(rem, 60000)
    (s, ms) = divmod(rem, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def cues_to_srt(cues):
    blocks = []
    for i, c in enumerate(cues, 1):
        blocks.append(f"{i}\n{fmt_ts(c['start'])} --> {fmt_ts(c['end'])}\n{c['text'].strip()}\n")
    return '\n'.join(blocks)


def parse_srt(content):
    out = []
    for block in re.split(r'\n\s*\n', content.replace('\r\n', '\n').strip()):
        lines = [l for l in block.split('\n') if l.strip()]
        if len(lines) < 2:
            continue
        ts_line = 0 if _TS_RE.search(lines[0]) else 1
        m = _TS_RE.search(lines[ts_line])
        if not m:
            continue
        g = m.groups()
        to_sec = lambda h, mi, s, ms: int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000.0
        text = ' '.join(lines[ts_line + 1:]).strip()
        if text:
            out.append({'start': to_sec(*g[:4]), 'end': to_sec(*g[4:]), 'text': text})
    return out


def split_chunks(text, max_chars=56, max_lines=2):
    """Chia câu dài thành các đoạn hiển thị ≤ max_chars ký tự (mỗi đoạn tối đa max_lines dòng)."""
    try:
        from core.video_editor import _split_subtitle_chunks
        chunks = _split_subtitle_chunks(text, max_chars, max_lines)
        if chunks:
            return [c for c in chunks if c.strip()]
    except Exception:
        pass
    words, chunks, cur = text.split(), [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            chunks.append(cur)
            cur = w
        else:
            cur = f'{cur} {w}'.strip()
    if cur:
        chunks.append(cur)
    return chunks


def rechunk_cues(cues, max_chars=56, max_lines=2):
    out = []
    for c in cues:
        text = (c.get('text') or '').strip()
        if not text:
            continue
        chunks = split_chunks(text, max_chars, max_lines) or [text]
        total_chars = sum(len(x) for x in chunks) or 1
        total_dur = max(0.01, c['end'] - c['start'])
        t = c['start']
        for ch in chunks:
            end = min(c['end'], t + total_dur * len(ch) / total_chars)
            out.append({'start': t, 'end': end, 'text': ch})
            t = end
    return out


def segments_to_cues(segments):
    return [{'start': float(s.get('start') or 0), 'end': float(s.get('end') or 0), 'text': (s.get('text') or '').strip()}
            for s in segments if (s.get('text') or '').strip()]


def scenes_to_cues(scenes, source='voiceover'):
    out = []
    for s in scenes:
        text = (s.get('subtitle') if source == 'subtitle' else s.get('voiceover')) or s.get('voiceover') or ''
        text = text.replace('||', ' ').strip()
        if not text:
            continue
        start = float(s.get('out_start', s.get('clip_start', 0)) or 0)
        end = float(s.get('out_end', s.get('clip_end', start + 3)) or start + 3)
        if end <= start:
            end = start + 3.0
        out.append({'start': start, 'end': end, 'text': text})
    return out
