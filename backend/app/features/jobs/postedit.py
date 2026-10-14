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
Bạn là biên tập viên hậu kỳ cho kênh YouTube {kind} tiếng Việt. Bạn nhận kịch bản ĐÃ LỒNG TIẾNG
và phải làm cho LỜI ĐỌC của từng cảnh khớp đúng ĐOẠN HÌNH của cảnh đó.

# DỮ LIỆU MỖI CẢNH
- "id": số thứ tự cảnh (giữ nguyên khi trả về)
- "hinh": thời lượng đoạn hình (giây)
- "tu_hien_tai": số từ lời đọc hiện tại
- "tu_muc_tieu": số từ NÊN CÓ để đọc vừa khít đoạn hình (đã tính sẵn ≈ {wps:.1f} từ/giây)
- "voiceover": lời đọc hiện tại
- "subtitle": phụ đề, chỉ có khi khác lời đọc

# QUY TẮC BẮT BUỘC
1. ĐỘ DÀI: lời đọc mỗi cảnh phải có số từ trong khoảng tu_muc_tieu ± {tol}%.
   Cảnh nằm ngoài khoảng đó PHẢI viết lại: dài thì rút gọn (giữ ý chính), ngắn thì thêm chi tiết của CHÍNH cảnh đó.
2. KHỚP CẢNH: lời đọc chỉ kể chuyện đang diễn ra trong cảnh đó; không kéo nội dung cảnh sau lên, không kể lại cảnh trước.
3. MẠCH: các cảnh nối tiếp tự nhiên như một bài thuyết minh liền mạch; có thể dùng từ nối ngắn ("rồi", "lúc này", "không ngờ").
   KHÔNG LẶP: mỗi cảnh một ý mới; không kể lại ý / cụm từ của cảnh khác; không mở đầu 2 cảnh liền nhau bằng cùng cụm từ;
   hạn chế nhắc lại tên nhân vật ở mọi câu — dùng đại từ. Cảnh nào đang lặp ý cảnh khác → PHẢI viết lại.
4. GIỌNG VĂN: tiếng Việt nói tự nhiên, câu ngắn vừa phải, dễ đọc thành tiếng. Không markdown, không emoji,
   không ký hiệu, không "[Cảnh N]", không chú thích trong ngoặc, không tiêu đề.
5. TRUNG THỰC: giữ nguyên tên riêng và tình tiết đã có; TUYỆT ĐỐI không bịa tình tiết mới.
6. BỎ CẢNH: chỉ đặt "exclude": true khi cảnh là rác, vô nghĩa, hoặc trùng nội dung cảnh khác.
7. PHỤ ĐỀ: nếu cảnh có "subtitle" riêng thì sửa cho cùng ý với lời đọc mới; không có thì bỏ qua trường này.
8. Cảnh đã đạt (đúng độ dài, câu ổn) → KHÔNG đưa vào kết quả.
{extra}
# ĐẦU RA
Chỉ trả về JSON, không giải thích gì thêm:
{{"edits": [{{"id": <số>, "voiceover": "<lời mới>", "subtitle": "<phụ đề mới, nếu cần>", "exclude": false, "reason": "<lý do ngắn, vd: dài gấp 3 hình → rút gọn>"}}]}}
Không có cảnh nào cần sửa → {{"edits": []}}

# KỊCH BẢN
{scenes}"""

RECHECK_PROMPT = """Các cảnh dưới đây VẪN SAI ĐỘ DÀI so với đoạn hình. Viết lại lời đọc của TỪNG cảnh để số từ
nằm trong khoảng tu_muc_tieu ± {tol}% — giữ ý chính, giọng văn tự nhiên, không bịa tình tiết, không ký hiệu.
Chỉ trả về JSON: {{"edits": [{{"id": <số>, "voiceover": "<lời mới>", "reason": "<ngắn>"}}]}}

{scenes}"""


def word_count(text):
    return len(re.findall(r'\w+', text or '', flags=re.UNICODE))


def target_words(seconds, wps=None):
    return max(3, round(max(0.0, seconds) * (wps or WORDS_PER_SEC) * FILL_RATIO))


def measure_wps(scenes):
    """Tốc độ đọc THẬT của giọng đang dùng (từ/giây, trung vị các cảnh ≥ 2s). Mỗi giọng một tốc độ —
    CapCut ~4.4, Edge ~3.8 — nên số từ mục tiêu phải tính theo giọng thật. None nếu chưa đủ dữ liệu."""
    rates = sorted(word_count(s.get('voiceover')) / float(s['tts_duration']) for s in scenes
                   if not s.get('excluded') and float(s.get('tts_duration') or 0) >= 2 and word_count(s.get('voiceover')) >= 5)
    if len(rates) < 2:
        return None
    return round(min(5.5, max(2.5, rates[len(rates) // 2])), 2)


def _scene_rows(scenes, wps=None):
    rows = []
    for (i, s) in enumerate(scenes[:MAX_SCENES]):
        if s.get('excluded'):
            continue
        hinh = max(0.0, float(s.get('clip_end') or 0) - float(s.get('clip_start') or 0))
        vo = (s.get('voiceover') or '').strip()
        row = {'id': i, 'hinh': round(hinh, 1), 'tu_hien_tai': word_count(vo), 'tu_muc_tieu': target_words(hinh, wps), 'voiceover': vo}
        sub = (s.get('subtitle') or '').strip()
        if sub and sub != vo:
            row['subtitle'] = sub
        rows.append(row)
    return rows


def _extract_json(text):
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', (text or '').strip())
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
    return None


def _off_target(text, target, tol):
    n = word_count(text)
    return target > 0 and abs(n - target) / target > tol


def suggest_edits(scenes, kind='review', instruction='', log_fn=print, wps=None):
    """→ [{'id', 'voiceover'?, 'subtitle'?, 'exclude', 'reason'}]. RuntimeError nếu chưa đăng nhập / AI lỗi."""
    from core import web_llm
    if not web_llm.available():
        raise RuntimeError('Chưa đăng nhập tài khoản ChatGPT hoặc Gemini (Cài đặt → Tài khoản AI).')
    wps = wps or measure_wps(scenes)
    rows = _scene_rows(scenes, wps)
    if not rows:
        return []
    off = sum(1 for r in rows if _off_target(r['voiceover'], r['tu_muc_tieu'], TOLERANCE))
    log_fn(f'   [AI hậu kỳ] {len(rows)} cảnh, {off} cảnh lệch độ dài so với hình (giọng đọc ~{wps or WORDS_PER_SEC:.1f} từ/giây) — gửi AI rà...')
    extra = f'\n# YÊU CẦU THÊM CỦA NGƯỜI DÙNG (ưu tiên)\n{instruction.strip()}\n' if instruction.strip() else ''
    prompt = SYSTEM_PROMPT.format(kind='review phim' if kind == 'review' else 'dịch & lồng tiếng phim', wps=wps or WORDS_PER_SEC,
                                  tol=int(TOLERANCE * 100), extra=extra, scenes=json.dumps(rows, ensure_ascii=False, indent=0))
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
        data2 = _extract_json(web_llm.chat(RECHECK_PROMPT.format(tol=int(TOLERANCE * 100),
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
(trường "loi" cho biết lỗi cụ thể). Viết lại lời đọc của TỪNG cảnh để số từ nằm trong khoảng tu_muc_tieu ± {tol}%.
- Lời dài hơn hình (hình bị lặp / đứng / kéo chậm) → rút gọn, giữ ý chính.
- Lời ngắn hơn hình → thêm chi tiết của CHÍNH cảnh đó.
- Lỗi lặp ý / lặp câu / mở đầu giống cảnh khác → viết lại bằng ý và cách diễn đạt KHÁC HẲN "trung_voi":
  không dùng lại cụm từ, hình ảnh, câu cảm thán của nó; đổi cách mở câu; giữ độ dài.
- KHÔNG mở đầu bằng cùng một cụm từ như "truoc"; hạn chế lặp tên nhân vật — dùng đại từ ("cậu", "cô bé", "chú ta").
- Giữ tên riêng, tình tiết; không bịa; tiếng Việt nói tự nhiên; không markdown, không ký hiệu.
- "truoc" / "sau" là lời của cảnh liền kề — chỉ để giữ mạch, KHÔNG sửa, KHÔNG lặp lại.
Chỉ trả về JSON: {{"edits": [{{"id": <số>, "voiceover": "<lời mới>"}}]}}

{scenes}"""


def rewrite_to_length(scenes, problems, log_fn=print, wps=None):
    """AI viết lại lời các cảnh lỗi. problems: {chỉ số cảnh: {'why', 'fit': số giây lời nên có, 'ref'?: chỉ số cảnh bị trùng}}.
    → {chỉ số: lời mới}."""
    from core import web_llm
    if not problems or not web_llm.available():
        return {}
    wps = wps or measure_wps(scenes)
    rows = []
    for (i, pb) in sorted(problems.items()):
        s = scenes[i]
        vo = (s.get('voiceover') or '').strip()
        row = {'id': i, 'loi': pb['why'], 'hinh': round(pb['fit'], 1), 'tu_hien_tai': word_count(vo), 'tu_muc_tieu': target_words(pb['fit'], wps),
               'voiceover': vo, 'truoc': (scenes[i - 1].get('voiceover') or '')[:160] if i > 0 else '',
               'sau': (scenes[i + 1].get('voiceover') or '')[:160] if i + 1 < len(scenes) else ''}
        if pb.get('ref') is not None:
            row['trung_voi'] = (scenes[pb['ref']].get('voiceover') or '')[:300]
        rows.append(row)
    data = _extract_json(web_llm.chat(FIX_PROMPT.format(tol=int(TOLERANCE * 100), scenes=json.dumps(rows, ensure_ascii=False, indent=0)), log_fn))
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
