"""Dịch lời thoại để LỒNG TIẾNG: biết ai nói từng câu (đã phân vai trên SRT gốc) → xưng hô đúng quan hệ nhân vật,
và mỗi câu có số từ tối đa theo thời gian câu gốc → giọng Việt đọc vừa khít, không trễ / không phải tua."""
import json
import re

from core import langs

WPS = 4.3            # tốc độ đọc giọng Việt (từ/giây) sau khi cắt khoảng lặng — đo trên Edge / VieNeu


def rate(target_lang='vi'):
    """Tốc độ đọc của ngôn ngữ lồng tiếng → (đơn vị / giây, 'words' | 'chars').
    Tiếng Việt: WPS từ/giây như cũ. Ngôn ngữ có dấu cách: langs.words_per_sec (ký tự/giây ÷ độ dài từ trung bình).
    Trung / Nhật / Thái (không dấu cách giữa từ): đếm KÝ TỰ, langs.chars_per_sec."""
    t = langs.norm(target_lang)
    if t == 'vi':
        return (WPS, 'words')
    if not langs.spaced(t):
        return (langs.chars_per_sec(t), 'chars')
    return (langs.words_per_sec(t), 'words')        # vd tiếng Anh ~2.6 từ/giây (từ dài hơn tiếng Việt)


def text_units(text, target_lang='vi'):
    """Độ dài câu theo đơn vị của rate(): số từ (ngôn ngữ có dấu cách) hoặc số ký tự chữ (Trung / Nhật / Thái —
    bỏ khoảng trắng & dấu câu)."""
    text = str(text or '')
    if rate(target_lang)[1] == 'chars':
        return len(re.sub(r'[\s\W_]+', '', text))
    return len(re.findall(r'\w+', text))


def unit_name(target_lang='vi'):
    """'từ' / 'ký tự' — chèn vào lời nhắc AI."""
    return 'ký tự' if rate(target_lang)[1] == 'chars' else 'từ'

PROMPT = """Bạn là biên dịch viên lồng tiếng phim Trung Quốc → tiếng Việt. Dịch từng câu thoại sang tiếng Việt để LỒNG TIẾNG.
Mỗi câu có: "i" (số thứ tự), "ai" (người nói), "goc" (lời gốc), "toi_da" (số từ tiếng Việt TỐI ĐA).

Quy tắc:
1. Cố gắng KHÔNG vượt "toi_da" từ — câu phải đọc vừa khít thời gian nhân vật nói trên hình. Thiếu chỗ thì nói gọn, bỏ chữ thừa.
   NHƯNG TUYỆT ĐỐI giữ ĐÚNG NGHĨA câu gốc: nếu không thể gọn hơn mà vẫn đúng nghĩa thì được vượt 1–2 từ, không bao giờ đổi / bịa nghĩa.
2. Xưng hô đúng vai và quan hệ giữa người nói với người nghe (ta/ngươi, tôi/cậu, anh/em, con/cha, tiểu thư/ta…), nhất quán cả phim.
3. Văn nói tự nhiên như phim lồng tiếng Việt, đúng giọng nhân vật (nam / nữ, già / trẻ, sang / bình dân). Tên riêng đọc Hán Việt.
4. Dòng "ai" là "(không phải thoại)" — tiếng động, lời bài hát — dịch thật ngắn.
5. Mỗi câu là ĐÚNG 1 dòng phụ đề trên hình (không có dấu câu), 1 câu nói hay bị ngắt sang 2–3 dòng liền nhau. Đọc cả các dòng
   liền nhau để hiểu đúng ý, nhưng mỗi "viet" chỉ dịch ĐÚNG phần của dòng đó (không dồn ý dòng sau lên, không lặp ý dòng trước)
   — đọc nối các dòng thành câu tiếng Việt tự nhiên; mỗi dòng được lồng tiếng & hiện phụ đề đúng lúc dòng gốc hiện.
{chars}{context}{glossary}{prev}
Làm 2 bước cho TỪNG câu (như biên dịch chuyên nghiệp): "sat" = dịch SÁT NGHĨA lời gốc (đủ ý, chưa cần gọn);
rồi tự soát lại "sat" (đúng nghĩa? đúng xưng hô? tự nhiên như người Việt nói?) và viết "viet" = câu lồng tiếng cuối cùng, gọn theo "toi_da".
Chỉ trả về JSON đúng dạng: {{"cau": [{{"i": <số>, "sat": "<dịch sát nghĩa>", "viet": "<câu lồng tiếng cuối>"}}]}}

{rows}"""


# Ngôn ngữ lồng tiếng KHÁC tiếng Việt: hướng dẫn vẫn tiếng Việt, câu trả lời (sat / viet) viết bằng {lang}.
PROMPT_OTHER = """Bạn là biên dịch viên lồng tiếng phim → {lang}. Dịch từng câu thoại sang {lang} để LỒNG TIẾNG (giọng đọc {lang}).
Mỗi câu có: "i" (số thứ tự), "ai" (người nói), "goc" (lời gốc), "toi_da" (số {unit} {lang} TỐI ĐA).

Quy tắc:
1. Cố gắng KHÔNG vượt "toi_da" {unit} — câu phải đọc vừa khít thời gian nhân vật nói trên hình. Thiếu chỗ thì nói gọn, bỏ chữ thừa.
   NHƯNG TUYỆT ĐỐI giữ ĐÚNG NGHĨA câu gốc: nếu không thể gọn hơn mà vẫn đúng nghĩa thì được vượt chút ít, không bao giờ đổi / bịa nghĩa.
2. Xưng hô / cách gọi đúng vai và quan hệ giữa người nói với người nghe, nhất quán cả phim (theo cách tự nhiên của {lang}).
3. Văn nói tự nhiên như phim lồng tiếng {lang} chuyên nghiệp, đúng giọng nhân vật (nam / nữ, già / trẻ, sang / bình dân).
   Tên riêng: dùng cách viết quen thuộc với khán giả {lang} (phiên âm / tên gốc romanized), KHÔNG phiên âm Hán Việt.
4. Dòng "ai" là "(không phải thoại)" — tiếng động, lời bài hát — dịch thật ngắn.
5. Mỗi câu là ĐÚNG 1 dòng phụ đề trên hình (không có dấu câu), 1 câu nói hay bị ngắt sang 2–3 dòng liền nhau. Đọc cả các dòng
   liền nhau để hiểu đúng ý, nhưng mỗi "viet" chỉ dịch ĐÚNG phần của dòng đó (không dồn ý dòng sau lên, không lặp ý dòng trước)
   — đọc nối các dòng thành câu {lang} tự nhiên; mỗi dòng được lồng tiếng & hiện phụ đề đúng lúc dòng gốc hiện.
{{chars}}{{context}}{{glossary}}{{prev}}
Làm 2 bước cho TỪNG câu (như biên dịch chuyên nghiệp): "sat" = dịch SÁT NGHĨA lời gốc sang {lang} (đủ ý, chưa cần gọn);
rồi tự soát lại "sat" (đúng nghĩa? đúng cách gọi? tự nhiên như người bản xứ nói?) và viết "viet" = câu lồng tiếng {lang} cuối cùng, gọn theo "toi_da".
Trường "viet" vẫn tên là "viet" nhưng nội dung PHẢI là {lang}. Số đếm viết bằng chữ số hay chữ đều được (giọng đọc {lang} tự đọc).
Chỉ trả về JSON đúng dạng: {{{{"cau": [{{{{"i": <số>, "sat": "<dịch sát nghĩa>", "viet": "<câu lồng tiếng cuối bằng {lang}>"}}}}]}}}}

{{rows}}"""


GLOSSARY_PROMPT_OTHER = """Bạn chuẩn bị lồng tiếng {lang} cho một bộ phim. Đọc toàn bộ kịch bản gốc dưới đây (mỗi dòng: người nói: lời).
Lập bảng để cả đội dịch dùng chung cho NHẤT QUÁN cả phim:
- "tom_tat": tóm tắt cốt truyện 2–3 câu (bối cảnh: cổ trang / hiện đại / tu tiên…).
- "ten": tên riêng, biệt danh, chức danh, thuật ngữ đặc biệt → cách viết bằng {lang} (tên người: cách viết quen thuộc với khán giả {lang}), vd {{{{"goc": "宿主", "viet": "<thuật ngữ bằng {lang}>"}}}}.
- "xung_ho": cách gọi nhau giữa các cặp nhân vật hay nói chuyện với nhau (bằng {lang}), vd {{{{"cap": "A → B", "cach": "..."}}}}.
Chỉ trả về JSON: {{{{"tom_tat": "...", "ten": [...], "xung_ho": [...]}}}}

{{script}}"""


def _prompts(target_lang):
    """(PROMPT, GLOSSARY_PROMPT) cho ngôn ngữ lồng tiếng — tiếng Việt giữ nguyên bản cũ."""
    t = langs.norm(target_lang)
    if t == 'vi':
        return (PROMPT, GLOSSARY_PROMPT)
    lang = f'{langs.name_en(t)} ({langs.name_vi(t).replace("Tiếng", "tiếng", 1)})'
    return (PROMPT_OTHER.format(lang=lang, unit=unit_name(t)), GLOSSARY_PROMPT_OTHER.format(lang=lang))


GLOSSARY_PROMPT = """Bạn chuẩn bị lồng tiếng Việt cho một phim Trung Quốc. Đọc toàn bộ kịch bản gốc dưới đây (mỗi dòng: người nói: lời).
Lập bảng để cả đội dịch dùng chung cho NHẤT QUÁN cả phim:
- "tom_tat": tóm tắt cốt truyện 2–3 câu (bối cảnh: cổ trang / hiện đại / tu tiên…).
- "ten": tên riêng, biệt danh, chức danh, thuật ngữ đặc biệt → cách dịch tiếng Việt (tên người đọc Hán Việt), vd {{"goc": "宿主", "viet": "ký chủ"}}.
- "xung_ho": cách xưng hô giữa các cặp nhân vật hay nói chuyện với nhau, vd {{"cap": "Diệp Phong → Anh cả", "cach": "xưng em, gọi anh cả"}}.
Chỉ trả về JSON: {{"tom_tat": "...", "ten": [...], "xung_ho": [...]}}

{script}"""


def glossary(segments, who, log=print, max_chars=9000, target_lang='vi'):
    """1 lượt AI đọc cả kịch bản gốc → tóm tắt + bảng tên riêng / thuật ngữ + xưng hô từng cặp nhân vật (dịch nhất quán cả phim).
    → đoạn chữ chèn vào lời nhắc dịch ('' nếu lỗi)."""
    from core import web_llm
    from app.features.jobs.postedit import _extract_json
    lines = [f"{who(i)}: {str(s['text']).strip()}" for (i, s) in enumerate(segments)]
    script = '\n'.join(lines)
    if len(script) > max_chars:                  # phim dài: lấy đều các đoạn cho đủ nhân vật & tình tiết
        step = max(1.0, len(lines) / (max_chars / 40))
        script = '\n'.join(lines[int(k * step)] for k in range(int(len(lines) / step)))[:max_chars]
    data = _extract_json(web_llm.chat(_prompts(target_lang)[1].format(script=script), log))
    if not isinstance(data, dict):
        log('   [WARN] AI lập bảng tên riêng / xưng hô không được — dịch không có bảng', 'warn')
        return ''
    ten = [t for t in (data.get('ten') or []) if isinstance(t, dict) and t.get('goc') and t.get('viet')][:60]
    xh = [x for x in (data.get('xung_ho') or []) if isinstance(x, dict) and x.get('cap') and x.get('cach')][:30]
    log(f"   Bảng dịch chung: {len(ten)} tên riêng / thuật ngữ, {len(xh)} cặp xưng hô", 'step')
    out = ''
    if data.get('tom_tat'):
        out += f"\nTóm tắt phim: {str(data['tom_tat'])[:500]}\n"
    if ten:
        out += 'Tên riêng & thuật ngữ (BẮT BUỘC dịch đúng như sau): ' + '; '.join(f"{t['goc']} = {t['viet']}" for t in ten) + '\n'
    if xh:
        out += 'Xưng hô giữa các nhân vật (giữ đúng cả phim): ' + '; '.join(f"{x['cap']}: {x['cach']}" for x in xh) + '\n'
    return out


def budgets(segments, wps=None, tolerance=1.5, target_lang='vi'):
    """Số từ (Trung / Nhật / Thái: số ký tự — xem rate()) tối đa mỗi câu = khung thời gian (thời lượng câu + mượn khoảng lặng sau tối đa 1.5s, như VideoLingo) × tốc độ đọc
    tự nhiên — đọc vừa ở tốc độ gốc; lệch chút thì bước lồng tiếng tua nhẹ (≤ 1.2×)."""
    if wps is None:
        wps = rate(target_lang)[0]
    out = []
    for (i, s) in enumerate(segments):
        nxt = segments[i + 1]['start'] if i + 1 < len(segments) else s['end'] + tolerance
        room = max(0.4, s['end'] - s['start'] + min(max(0.0, nxt - s['end']), tolerance))
        # đọc ở ~1.1× (giọng tua tối đa 1.2× nên còn dư chút) — ≥ 3 từ: ít hơn AI phải bóp câu đến sai nghĩa
        out.append(max(3, int(room * 1.1 * wps)))
    return out


def translate(segments, cast, log=print, film_context='', batch=30, target_lang='vi'):
    """segments = [{'start', 'end', 'text'}] lời gốc; cast = kết quả phân vai ({'labels', 'speakers'}) hoặc None.
    → list câu dịch (cùng độ dài segments; câu AI không trả → None) hoặc None nếu chưa đăng nhập AI."""
    from core import web_llm
    from app.features.jobs.postedit import _extract_json
    if not web_llm.available():
        return None
    n = len(segments)
    labels = cast['labels'] if cast else [None] * n
    spk = cast['speakers'] if cast else {}

    def who(i):
        k = labels[i]
        if k is None:
            return '?'
        if k not in spk:
            return '(không phải thoại)'
        return f"{spk[k].get('name') or f'NV{k + 1}'} ({'nữ' if spk[k].get('gender') == 'female' else 'nam'})"
    chars = ''
    if spk:
        chars = '\nNhân vật trong phim: ' + ', '.join(f"{v.get('name') or f'NV{k + 1}'} ({'nữ' if v.get('gender') == 'female' else 'nam'})"
                                                     for (k, v) in sorted(spk.items(), key=lambda kv: -int(kv[1].get('count') or 0))) + '\n'
    context = f'\nBối cảnh phim: {film_context.strip()[:600]}\n' if film_context.strip() else ''
    t = langs.norm(target_lang)
    prompt_tpl = _prompts(t)[0]
    limit = budgets(segments, target_lang=t)
    from core import user_glossary
    mine = user_glossary.prompt_block() if t == 'vi' else ''      # từ điển của bạn: gốc → tiếng Việt, chỉ dùng khi lồng tiếng Việt
    if mine:
        log(f"   Từ điển của bạn: {mine.count(' = ')} tên / thuật ngữ đã chốt cách dịch", 'step')
    gloss = mine + glossary(segments, who, log, target_lang=t)
    out = [None] * n
    for k in range(0, n, batch):
        idx = list(range(k, min(n, k + batch)))
        rows = [{'i': i, 'ai': who(i), 'goc': str(segments[i]['text']).strip()[:200], 'toi_da': limit[i]} for i in idx]
        done = [(i, out[i]) for i in range(max(0, k - 6), k) if out[i]]
        prev = ('\nCác câu ngay trước (đã dịch, để nối mạch & giữ xưng hô): '
                + json.dumps([{'ai': who(i), 'viet': t} for (i, t) in done], ensure_ascii=False) + '\n') if done else ''
        for attempt in range(2):
            raw = web_llm.chat(prompt_tpl.format(chars=chars, context=context, glossary=gloss, prev=prev, rows=json.dumps(rows, ensure_ascii=False, indent=0)), log)
            data = _extract_json(raw)
            items = data.get('cau') if isinstance(data, dict) else (data if isinstance(data, list) else None)
            got = 0
            for it in items or []:
                try:
                    i = int(it.get('i'))
                    t = str(it.get('viet') or '').strip()
                except (TypeError, ValueError, AttributeError):
                    continue
                if i in idx and t:
                    out[i] = t
                    got += 1
            if got >= len(idx) * 0.8:
                break
            log(f'   [WARN] AI dịch gói câu {k + 1}–{idx[-1] + 1} chỉ trả {got}/{len(idx)} câu' + (' — thử lại' if attempt == 0 else ''), 'warn')
        log(f'   Dịch theo vai: {min(n, k + batch)}/{n} câu', 'step')
    return out
