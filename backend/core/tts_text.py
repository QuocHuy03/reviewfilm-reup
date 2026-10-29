"""Làm sạch câu trước khi gửi sang bộ đọc (chỉ chuỗi đọc — phụ đề / kịch bản giữ nguyên từng ký tự).

AI / người dán hay để lại rác ở mép câu (dấu phẩy cuối, gạch đầu dòng, dấu sao, ký tự vô hình) → giọng đọc ra tiếng lạ,
ngắt quãng hoặc lỗi. Chữ viết tắt (VN, TP, HLV…) được đọc thành chữ đầy đủ theo vi_abbreviations.txt.
"""
import os
import re

_INVISIBLE = re.compile(r'[​‌‍⁠﻿­\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_LEAD = re.compile(r'^[\s\-–—•*·▪►●>]+')
# dấu ngăn cách lạc ở cuối câu (dấu KẾT câu . ! ? … và ngoặc / nháy đóng thì giữ)
_TRAIL = re.compile(r'[\s,;:、，；：\-–—/\\|*#~·•]+$')
_OPEN_TAIL = re.compile(r'[\s(\[{“‘"\'「『（]+$')
_SPACES = re.compile(r'\s+')

_ABBR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vi_abbreviations.txt')
_abbr = None


def _load_abbr():
    """→ (regex khớp nguyên từ, dict). Từ dài khớp trước (TP.HCM trước TP)."""
    global _abbr
    if _abbr is None:
        table = {}
        try:
            with open(_ABBR_FILE, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or ':' not in line:
                        continue
                    (k, v) = line.split(':', 1)
                    if k.strip() and v.strip():
                        table[k.strip()] = v.strip()
        except OSError:
            pass
        if table:
            alt = '|'.join(re.escape(k) for k in sorted(table, key=len, reverse=True))
            # ranh giới: không dính chữ / số / dấu chấm-gạch nối liền (tránh cắt giữa "ABC.VN", "VN2")
            pat = re.compile(rf'(?<![\w.&/-])(?:{alt})(?![\w&/]|[.-]\w)')
        else:
            pat = None
        _abbr = (pat, table)
    return _abbr


def expand_abbreviations(text):
    (pat, table) = _load_abbr()
    if not pat or not text:
        return text or ''
    return pat.sub(lambda m: table[m.group(0)], text)


def clean_for_tts(text):
    """Câu sạch để đọc. Rỗng sau khi làm sạch → trả câu gốc (đã strip) để không mất câu."""
    raw = text or ''
    s = _INVISIBLE.sub('', raw).replace('||', ' ')
    s = _SPACES.sub(' ', s).strip()
    s = _LEAD.sub('', s)
    prev = None
    while prev != s:
        prev = s
        s = _TRAIL.sub('', s)
        s = _OPEN_TAIL.sub('', s)
    s = s.strip()
    return s if s else raw.strip()


def prepare_tts_text(text, lang='vi'):
    """Làm sạch + (tiếng Việt) đọc chữ viết tắt + đọc số bằng chữ → chuỗi gửi bộ đọc.
    Ngôn ngữ khác: chỉ làm sạch — bộ đọc nước ngoài tự đọc số / viết tắt theo tiếng của nó."""
    if lang != 'vi':
        return clean_for_tts(text)
    from .tts_engine import replace_numbers_with_words
    return replace_numbers_with_words(expand_abbreviations(clean_for_tts(text)))
