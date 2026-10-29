"""AI hậu kỳ: rà kịch bản đã lồng tiếng, sửa lời / phụ đề / bỏ cảnh để từng cảnh KHỚP HÌNH.

Chạy bằng tài khoản ChatGPT/Gemini đăng nhập trong app (core.web_llm).
  · Bước Xem trước (tab AI): chỉ ĐỀ XUẤT, người dùng duyệt rồi áp dụng.
  · Tự hậu kỳ trong pipeline (_step_autopost): áp dụng luôn.

Cách làm cho từng cảnh khớp hình:
  1. Tính sẵn SỐ TỪ MỤC TIÊU mỗi cảnh = thời lượng hình × tốc độ đọc TTS — AI không phải tự ước lượng.
  2. Prompt hệ thống ép quy tắc độ dài (±25%), giọng văn, chống bịa, bỏ rác.
  3. Tự kiểm tra kết quả: cảnh nào vẫn lệch quá ±40% → gửi lại 1 lượt chỉ cho các cảnh đó.
"""
import json
import re

WORDS_PER_SEC = 230 / 60          # tốc độ đọc trung bình của TTS (core.script_writer.TTS_WPM)
FILL_RATIO = 0.92                 # chừa ~8% hình cho khoảng lặng giữa các câu
TOLERANCE = 0.25                  # lệch số từ cho phép trong prompt
RECHECK_TOLERANCE = 0.40          # lệch quá mức này sau lượt 1 → sửa lượt 2
MAX_SCENES = 120                  # giới hạn độ dài prompt

SYSTEM_PROMPT = """# VAI TRÒ
Bạn là biên tập viên hậu kỳ cho kênh YouTube {kind} {lang}. Bạn nhận kịch bản ĐÃ LỒNG TIẾNG
và phải làm cho LỜI ĐỌC của từng cảnh khớp đúng ĐOẠN HÌNH của cảnh đó.

# DỮ LIỆU MỖI CẢNH
- "id": số thứ tự cảnh (giữ nguyên khi trả về)
- "hinh": thời lượng đoạn hình (giây)
- "tu_hien_tai": số {unit} lời đọc hiện tại
- "tu_muc_tieu": số {unit} NÊN CÓ để đọc vừa khít đoạn hình (đã tính sẵn ≈ {wps:.1f} {unit}/giây)
- "voiceover": lời đọc hiện tại
- "subtitle": phụ đề, chỉ có khi khác lời đọc

# QUY TẮC BẮT BUỘC
1. ĐỘ DÀI: lời đọc mỗi cảnh phải có số {unit} trong khoảng tu_muc_tieu ± {tol}%.
   Cảnh nằm ngoài khoảng đó PHẢI viết lại: dài thì rút gọn (giữ ý chính), ngắn thì thêm chi tiết của CHÍNH cảnh đó.
2. KHỚP CẢNH: lời đọc chỉ kể chuyện đang diễn ra trong cảnh đó; không kéo nội dung cảnh sau lên, không kể lại cảnh trước.
3. MẠCH: các cảnh nối tiếp tự nhiên như một bài thuyết minh liền mạch; có thể dùng từ nối ngắn{connectors}.
   KHÔNG LẶP: mỗi cảnh một ý mới; không kể lại ý / cụm từ của cảnh khác; không mở đầu 2 cảnh liền nhau bằng cùng cụm từ;
   hạn chế nhắc lại tên nhân vật ở mọi câu — dùng đại từ. Cảnh nào đang lặp ý cảnh khác → PHẢI viết lại.
4. GIỌNG VĂN: {lang} nói tự nhiên, câu ngắn vừa phải, dễ đọc thành tiếng. Không markdown, không emoji,
   không ký hiệu, không "[Cảnh N]", không chú thích trong ngoặc, không tiêu đề.
5. TRUNG THỰC: giữ nguyên tên riêng và tình tiết đã có; TUYỆT ĐỐI không bịa tình tiết mới.
6. BỎ CẢNH: chỉ đặt "exclude": true khi cảnh là rác, vô nghĩa, hoặc trùng nội dung cảnh khác.
7. PHỤ ĐỀ: nếu cảnh có "subtitle" riêng thì sửa cho cùng ý với lời đọc mới; không có thì bỏ qua trường này.
8. Cảnh đã đạt (đúng độ dài, câu ổn) → KHÔNG đưa vào kết quả.
{lang_rule}{extra}
# ĐẦU RA
Chỉ trả về JSON, không giải thích gì thêm:
{{"edits": [{{"id": <số>, "voiceover": "<lời mới>", "subtitle": "<phụ đề mới, nếu cần>", "exclude": false, "reason": "<lý do ngắn, vd: dài gấp 3 hình → rút gọn>"}}]}}
Không có cảnh nào cần sửa → {{"edits": []}}

# KỊCH BẢN
{scenes}"""

RECHECK_PROMPT = """Các cảnh dưới đây VẪN SAI ĐỘ DÀI so với đoạn hình. Viết lại lời đọc của TỪNG cảnh để số {unit}
nằm trong khoảng tu_muc_tieu ± {tol}% — giữ ý chính, giọng văn tự nhiên, không bịa tình tiết, không ký hiệu.{lang_rule_inline}
Chỉ trả về JSON: {{"edits": [{{"id": <số>, "voiceover": "<lời mới>", "reason": "<ngắn>"}}]}}

{scenes}"""


# Chữ không có dấu cách giữa từ (Trung, Nhật, Thái): mỗi ký tự = 1 đơn vị độ dài; còn lại đếm theo từ (\w+).
# Tiếng Việt / Anh… không có ký tự nào thuộc các dải này → đếm y như cũ.
_CHAR_UNIT = '\u0e00-\u0e7f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
_UNIT_RE = re.compile(f'[{_CHAR_UNIT}][ัิ-ฺ็-๎]*|[^\\W{_CHAR_UNIT}]+', flags=re.UNICODE)   # dấu Thái dính ký tự trước
# độ dài trung bình 1 từ (kể cả dấu cách) — đổi tốc độ ký tự / giây (core.langs) ra từ / giây cho ngôn ngữ có dấu cách


def word_count(text, target_lang=None):
    """Độ dài lời đọc: số từ; chữ Trung / Nhật / Thái đếm theo ký tự (không có dấu cách). target_lang để dành, không bắt buộc."""
    return len(_UNIT_RE.findall(text or ''))


def _tl(target_lang):
    from core import langs
    return langs.norm(target_lang)


def units_per_sec(target_lang='vi', vi_rate=None):
    """Tốc độ đọc mặc định (đơn vị của word_count / giây) theo ngôn ngữ lời đọc. 'vi' → vi_rate (mặc định WORDS_PER_SEC)."""
    from core import langs
    tl = _tl(target_lang)
    if tl == 'vi':
        return vi_rate or WORDS_PER_SEC
    if not langs.spaced(tl):
        return langs.chars_per_sec(tl)
    return langs.words_per_sec(tl)


def unit_name(target_lang='vi'):
    """'từ' (tiếng có dấu cách) / 'ký tự' (Trung, Nhật, Thái) — đơn vị độ dài ghi trong prompt."""
    from core import langs
    return 'từ' if langs.spaced(_tl(target_lang)) else 'ký tự'


def lang_label(target_lang='vi'):
    """Tên ngôn ngữ lời đọc cho prompt: 'tiếng Việt' (y như cũ) · 'tiếng Anh (English)'…"""
    from core import langs
    tl = _tl(target_lang)
    name = langs.name_vi(tl)
    name = name[:1].lower() + name[1:]
    return name if tl == 'vi' else f'{name} ({langs.name_en(tl)})'


def lang_rule(target_lang, inline=False):
    """Câu ép ngôn ngữ đầu ra (chỉ khi KHÔNG phải tiếng Việt — prompt tiếng Việt giữ nguyên từng chữ)."""
    tl = _tl(target_lang)
    if tl == 'vi':
        return ''
    from core import langs
    rule = (f'Lời đọc / phụ đề trả về PHẢI viết bằng {lang_label(tl)} — không dùng tiếng Việt. '
            f'Write every voiceover/subtitle in {langs.name_en(tl)}.')
    return (' ' + rule) if inline else f'9. NGÔN NGỮ: {rule}\n'


def target_words(seconds, wps=None, target_lang='vi'):
    return max(3, round(max(0.0, seconds) * (wps or units_per_sec(target_lang)) * FILL_RATIO))


def measure_wps(scenes, target_lang='vi'):
    """Tốc độ đọc THẬT của giọng đang dùng (từ/giây, trung vị các cảnh ≥ 2s). Mỗi giọng một tốc độ —
    CapCut ~4.4, Edge ~3.8 — nên số từ mục tiêu phải tính theo giọng thật. None nếu chưa đủ dữ liệu.
    Ngôn ngữ khác: đơn vị theo word_count (Trung / Nhật / Thái: ký tự), kẹp quanh tốc độ mặc định của ngôn ngữ đó."""
    rates = sorted(word_count(s.get('voiceover')) / float(s['tts_duration']) for s in scenes
                   if not s.get('excluded') and float(s.get('tts_duration') or 0) >= 2 and word_count(s.get('voiceover')) >= 5)
    if len(rates) < 2:
        return None
    if _tl(target_lang) == 'vi':
        return round(min(5.5, max(2.5, rates[len(rates) // 2])), 2)
    base = units_per_sec(target_lang)
    return round(min(base * 1.6, max(base * 0.55, rates[len(rates) // 2])), 2)


_FAKE_DESC = re.compile(r'^\s*(?:ph[aầ]n\s+\d+\s+trong|ti[eế]p\s+di[eễ]n\s+c[aả]nh|c[aả]nh\s+\d+\s*$)', re.IGNORECASE)


def _scene_rows(scenes, wps=None, target_lang='vi'):
    rows = []
    for (i, s) in enumerate(scenes[:MAX_SCENES]):
        if s.get('excluded'):
            continue
        hinh = max(0.0, float(s.get('clip_end') or 0) - float(s.get('clip_start') or 0))
        vo = (s.get('voiceover') or '').strip()
        row = {'id': i, 'hinh': round(hinh, 1), 'tu_hien_tai': word_count(vo), 'tu_muc_tieu': target_words(hinh, wps, target_lang), 'voiceover': vo}
        sub = (s.get('subtitle') or '').strip()
        if sub and sub != vo:
            row['subtitle'] = sub
        desc = str(s.get('description') or '').strip()
        if desc and not _FAKE_DESC.match(desc):
            row['mo_ta_hinh'] = desc[:240]       # AI hậu kỳ thấy hình cảnh có gì → "thêm chi tiết" không phải bịa
        rows.append(row)
    return rows


def _extract_json(text):
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', (text or '').strip())
    try:
        return json.loads(text)
    except ValueError:
        pass
    # ChatGPT web đôi khi bọc <CodeBlock language="json" editable={false}>…</CodeBlock> → bỏ thẻ, rồi đọc khối JSON đầu tiên hợp lệ
    text = re.sub(r'</?CodeBlock[^>]*>', '', text).replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    dec = json.JSONDecoder()
    for m in re.finditer(r'[\[{]', text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if obj:
            return obj
    return None


def _off_target(text, target, tol):
    n = word_count(text)
    return target > 0 and abs(n - target) / target > tol


def suggest_edits(scenes, kind='review', instruction='', log_fn=print, wps=None, target_lang='vi'):
    """→ [{'id', 'voiceover'?, 'subtitle'?, 'exclude', 'reason'}]. RuntimeError nếu chưa đăng nhập / AI lỗi.
    target_lang: ngôn ngữ lời đọc (core.langs) — 'vi' như cũ."""
    from core import web_llm
    if not web_llm.available():
        raise RuntimeError('Chưa đăng nhập tài khoản ChatGPT hoặc Gemini (Cài đặt → Tài khoản AI).')
    wps = wps or measure_wps(scenes, target_lang)
    rows = _scene_rows(scenes, wps, target_lang)
    if not rows:
        return []
    off = sum(1 for r in rows if _off_target(r['voiceover'], r['tu_muc_tieu'], TOLERANCE))
    log_fn(f'   [AI hậu kỳ] {len(rows)} cảnh, {off} cảnh lệch độ dài so với hình (giọng đọc ~{wps or units_per_sec(target_lang):.1f} {unit_name(target_lang)}/giây) — gửi AI rà...')
    extra = f'\n# YÊU CẦU THÊM CỦA NGƯỜI DÙNG (ưu tiên)\n{instruction.strip()}\n' if instruction.strip() else ''
    vi = _tl(target_lang) == 'vi'
    prompt = SYSTEM_PROMPT.format(kind='review phim' if kind == 'review' else 'dịch & lồng tiếng phim', wps=wps or units_per_sec(target_lang),
                                  tol=int(TOLERANCE * 100), extra=extra, scenes=json.dumps(rows, ensure_ascii=False, indent=0),
                                  lang=lang_label(target_lang), unit=unit_name(target_lang), lang_rule=lang_rule(target_lang),
                                  connectors=' ("rồi", "lúc này", "không ngờ")' if vi else f' của {lang_label(target_lang)}')
    data = _extract_json(web_llm.chat(prompt, log_fn))
    if not isinstance(data, dict):
        raise RuntimeError('AI không trả về kết quả hợp lệ — thử lại.')

    by_id = {r['id']: r for r in rows}
    edits = {}
    for e in data.get('edits') or []:
        try:
            i = int(e.get('id'))
        except (TypeError, ValueError):
            continue
        if i not in by_id:
            continue
        cur = by_id[i]
        item = {'id': i, 'exclude': bool(e.get('exclude')), 'reason': str(e.get('reason') or '')[:300]}
        vo = (e.get('voiceover') or '').strip()
        if vo and vo != cur['voiceover']:
            item['voiceover'] = vo
        sub = (e.get('subtitle') or '').strip()
        if sub and sub != cur.get('subtitle', cur['voiceover']):
            item['subtitle'] = sub
        if item['exclude'] or 'voiceover' in item or 'subtitle' in item:
            edits[i] = item

    # Tự kiểm tra: cảnh (sau sửa) vẫn lệch quá nhiều → 1 lượt sửa riêng cho các cảnh đó
    retry = []
    for r in rows:
        e = edits.get(r['id'])
        if e and e['exclude']:
            continue
        text = e['voiceover'] if e and 'voiceover' in e else r['voiceover']
        if _off_target(text, r['tu_muc_tieu'], RECHECK_TOLERANCE):
            retry.append({'id': r['id'], 'hinh': r['hinh'], 'tu_hien_tai': word_count(text), 'tu_muc_tieu': r['tu_muc_tieu'], 'voiceover': text})
    if retry:
        log_fn(f'   [AI hậu kỳ] Kiểm tra lại: {len(retry)} cảnh vẫn lệch độ dài — sửa thêm 1 lượt...')
        data2 = _extract_json(web_llm.chat(RECHECK_PROMPT.format(tol=int(TOLERANCE * 100), unit=unit_name(target_lang),
                                                                  lang_rule_inline=lang_rule(target_lang, True),
                                                                  scenes=json.dumps(retry, ensure_ascii=False, indent=0)), log_fn))
        for e in (data2 or {}).get('edits') or []:
            try:
                i = int(e.get('id'))
            except (TypeError, ValueError):
                continue
            vo = (e.get('voiceover') or '').strip()
            if i in by_id and vo and vo != by_id[i]['voiceover']:
                item = edits.get(i) or {'id': i, 'exclude': False, 'reason': ''}
                item['voiceover'] = vo
                item['reason'] = (item.get('reason') or str(e.get('reason') or 'khớp độ dài hình'))[:300]
                edits[i] = item

    still = [r['id'] + 1 for r in rows
             if not (edits.get(r['id']) or {}).get('exclude')
             and _off_target((edits.get(r['id']) or {}).get('voiceover', r['voiceover']), r['tu_muc_tieu'], RECHECK_TOLERANCE)]
    if still:
        log_fn(f'   [AI hậu kỳ] Còn {len(still)} cảnh lệch độ dài sau 2 lượt: {still[:10]} — bước căn hình sẽ bù phần còn lại.', 'warn')
    return [edits[k] for k in sorted(edits)]


MAX_STRETCH = 2.5   # video_editor kẹp tỉ lệ kéo giãn hình trong 0.4 … 2.5×


FIX_PROMPT = """Bạn là biên tập viên hậu kỳ. Máy kiểm tra video vừa dựng phát hiện lỗi ở các cảnh dưới đây
(trường "loi" cho biết lỗi cụ thể). Viết lại lời đọc của TỪNG cảnh để số {unit} nằm trong khoảng tu_muc_tieu ± {tol}%.
- Lời dài hơn hình (hình bị lặp / đứng / kéo chậm) → rút gọn, giữ ý chính.
- Lời ngắn hơn hình → thêm chi tiết của CHÍNH cảnh đó.
- Lỗi lặp ý / lặp câu / mở đầu giống cảnh khác → viết lại bằng ý và cách diễn đạt KHÁC HẲN "trung_voi":
  không dùng lại cụm từ, hình ảnh, câu cảm thán của nó; đổi cách mở câu; giữ độ dài.
- KHÔNG mở đầu bằng cùng một cụm từ như "truoc"; hạn chế lặp tên nhân vật — dùng đại từ{pronouns}.
- Giữ tên riêng, tình tiết; không bịa; {lang} nói tự nhiên; không markdown, không ký hiệu.{lang_rule_inline}
- "truoc" / "sau" là lời của cảnh liền kề — chỉ để giữ mạch, KHÔNG sửa, KHÔNG lặp lại.
Chỉ trả về JSON: {{"edits": [{{"id": <số>, "voiceover": "<lời mới>"}}]}}

{scenes}"""


def rewrite_to_length(scenes, problems, log_fn=print, wps=None, target_lang='vi'):
    """AI viết lại lời các cảnh lỗi. problems: {chỉ số cảnh: {'why', 'fit': số giây lời nên có, 'ref'?: chỉ số cảnh bị trùng}}.
    → {chỉ số: lời mới}. target_lang: ngôn ngữ lời đọc — 'vi' như cũ."""
    from core import web_llm
    if not problems or not web_llm.available():
        return {}
    wps = wps or measure_wps(scenes, target_lang)
    rows = []
    for (i, pb) in sorted(problems.items()):
        s = scenes[i]
        vo = (s.get('voiceover') or '').strip()
        row = {'id': i, 'loi': pb['why'], 'hinh': round(pb['fit'], 1), 'tu_hien_tai': word_count(vo), 'tu_muc_tieu': target_words(pb['fit'], wps, target_lang),
               'voiceover': vo, 'truoc': (scenes[i - 1].get('voiceover') or '')[:160] if i > 0 else '',
               'sau': (scenes[i + 1].get('voiceover') or '')[:160] if i + 1 < len(scenes) else ''}
        if pb.get('ref') is not None:
            row['trung_voi'] = (scenes[pb['ref']].get('voiceover') or '')[:300]
        rows.append(row)
    vi = _tl(target_lang) == 'vi'
    data = _extract_json(web_llm.chat(FIX_PROMPT.format(
        tol=int(TOLERANCE * 100), scenes=json.dumps(rows, ensure_ascii=False, indent=0), unit=unit_name(target_lang),
        lang=lang_label(target_lang), lang_rule_inline=lang_rule(target_lang, True),
        pronouns=' ("cậu", "cô bé", "chú ta")' if vi else ''), log_fn))
    out = {}
    for e in (data or {}).get('edits') or []:
        try:
            i = int(e.get('id'))
        except (TypeError, ValueError):
            continue
        vo = (e.get('voiceover') or '').strip()
        if i in problems and vo and vo != (scenes[i].get('voiceover') or '').strip():
            out[i] = vo
    return out


def fix_durations(scenes, video_duration=None):
    """Căn đoạn hình gốc cho khớp lời đọc (sửa tại chỗ). → danh sách chỉ số cảnh đã chỉnh.

    Hình dài hơn lời quá nhiều → cắt đuôi, giữ phần đầu (≈1.2× lời).
    Lời dài hơn hình quá nhiều → nới đuôi (≈ lời/1.2), không vượt cuối video.
    """
    changed = []
    limit = video_duration if video_duration and video_duration > 0 else float('inf')
    starts = [float(s.get('clip_start') or 0) for s in scenes if not s.get('excluded')]
    for (i, s) in enumerate(scenes):
        tts = float(s.get('tts_duration') or 0)
        if s.get('excluded') or tts <= 0:
            continue
        start, end = float(s.get('clip_start') or 0), float(s.get('clip_end') or 0)
        src = end - start
        new_end = end
        if src > tts * MAX_STRETCH:
            new_end = start + tts * 1.2
        elif tts > src * MAX_STRETCH:
            # Không nới lấn sang hình của cảnh phía sau — phần thiếu để AI rút lời / QA báo
            later = [x for x in starts if x > start + 0.05]
            new_end = min([limit, start + tts / 1.2] + ([max(end, min(later))] if later else []))
        new_end = round(new_end, 2)
        if abs(new_end - end) >= 0.05 and new_end > start + 0.2:
            s['clip_end'] = new_end
            changed.append(i)
    return changed
