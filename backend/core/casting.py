

"""Phan vai nhieu giong theo nhan vat (GD5 06/07/2026).

AI (DeepSeek) doc kich ban thuyet minh, nhan dien nhan vat co LOI THOAI TRUC TIEP
(thuong nam trong ngoac kep) va tach tung cau thanh cac doan [nguoi ke / loi thoai
nhan vat X] de moi vai doc bang 1 giong VieNeu rieng (mien phi — chinh sach chot
06/07/2026: phan vai chi dung bo giong VieNeu, khong dinh den Token giong cao cap).

Nguyen tac an toan: AI chi duoc CHEP NGUYEN VAN — sau khi tach, ghep cac doan lai
phai ra dung cau goc (so sanh sau khi chuan hoa khoang trang); cau nao ghep lech
thi tu roi ve 1 doan "nguoi ke" duy nhat, KHONG bao gio lam sai kich ban.
"""
import json
import re
_QUOTE_RE = re.compile('["“”‘’«»]')
_BATCH = 25
def _norm(t):
    t = _QUOTE_RE.sub('', t or '')
    return re.sub('\\s+', ' ', t).strip().lower()
def _parse_json_block(out):
    cleaned = re.sub('^```(?:json)?\\s*|\\s*```$', '', ((out or '')).strip())
    return json.loads(cleaned)
def analyze_characters(scenes, deepseek_key, log_fn=print):
    if not deepseek_key:
        log_fn('   [WARN] Chưa có key AI (cần đăng nhập) — bỏ phân vai.')
        return
    from .script_writer import _llm_text_call
    _eng = 'web' if deepseek_key == 'web' else 'deepseek'
    quoted = []
    for (i, s) in enumerate(scenes):
        text = ((s.get('voiceover') or '')).strip()
        s['segments'] = [{'text': text, 'vai': 'ke'}] if text else []
        if text and _QUOTE_RE.search(text):
            quoted.append((i, text))
    if not quoted:
        return
    gender_map = {}
    n_cast_scenes = 0
    for b0 in range(0, len(quoted), _BATCH):
        batch = quoted[slice(b0, b0 + _BATCH, None)]
        known = ''
        if gender_map:
            known = 'Nhân vật đã biết từ phần trước (dùng ĐÚNG tên này nếu gặp lại): ' + json.dumps([{'ten': t, 'gioi_tinh': g} for (t, g) in gender_map.items()], ensure_ascii=False) + '\n'
        prompt = '''Bạn là biên tập viên lồng tiếng video review phim. Dưới đây là các câu thuyết minh, một số câu chứa LỜI THOẠI TRỰC TIẾP của nhân vật (thường trong ngoặc kép).
''' + known + '''Với TỪNG câu, tách thành danh sách đoạn theo đúng thứ tự: đoạn của người kể chuyện mang vai "ke"; đoạn là lời thoại trực tiếp mang vai = tên nhân vật nói câu đó (suy ra từ ngữ cảnh; không rõ tên thì đặt "Nhân vật nam 1"/"Nhân vật nữ 1"...).
LUẬT SẮT: mỗi đoạn phải CHÉP NGUYÊN VĂN từ câu gốc, không thêm/bớt/sửa một chữ nào; ghép các đoạn theo thứ tự phải ra lại đúng câu gốc. Câu không có lời thoại trực tiếp thì trả về 1 đoạn duy nhất vai "ke".

''' + json.dumps([{'i': i, 'cau': t} for (i, t) in batch], ensure_ascii=False) + '''

Trả về JSON thuần túy, không thêm chữ nào khác:
{"nhan_vat": [{"ten": "...", "gioi_tinh": "nam" | "nu"}],
 "cau": [{"i": <số>, "doan": [{"text": "...", "vai": "ke" | "<tên nhân vật>"}]}]}
Chỉ liệt kê nhân vật thực sự có lời thoại.'''
        try:
            out = _llm_text_call(_eng, deepseek_key, prompt, log_fn, max_tokens=8000, temperature=0.2)
            data = _parse_json_block(out)
        except Exception as e:
            log_fn(f'''   [WARN] Phân vai đợt {b0 // _BATCH + 1} lỗi ({e}) — các câu đợt này đọc giọng kể.''')
            continue
        if not isinstance(data, dict):
            continue
        for c in data.get('nhan_vat') or []:
            if not isinstance(c, dict):
                continue
            name = str(c.get('ten') or '').strip()
            gender = 'nu' if str(c.get('gioi_tinh', '')).strip().lower() in ('nu', 'nữ', 'female') else 'nam'
            if name and name.lower() != 'ke':
                gender_map.setdefault(name, gender)
        by_i = {}
        for c in data.get('cau') or []:
            if isinstance(c, dict):
                try:
                    by_i[int(c.get('i'))] = c.get('doan') or []
                except (TypeError, ValueError):
                    pass
        for (i, original) in batch:
            segs = by_i.get(i)
            if not segs:
                continue
            segs = [{'text': str(d.get('text') or ''), 'vai': str(d.get('vai') or 'ke').strip() or 'ke'} for d in segs if isinstance(d, dict) and str(d.get('text') or '').strip()]
            if segs and _norm(''.join((x['text'] for x in segs))) == _norm(original):
                if any((x['vai'] != 'ke' for x in segs)):
                    scenes[i]['segments'] = segs
                    n_cast_scenes += 1
            else:
                log_fn(f'''   [WARN] Câu {i + 1}: AI tách không khớp nguyên văn — giữ giọng kể cho an toàn.''')
    used = set()
    for s in scenes:
        for seg in s.get('segments') or []:
            if seg['vai'] != 'ke':
                used.add(seg['vai'])
    characters = [{'ten': t, 'gioi_tinh': gender_map.get(t, 'nam')} for t in sorted(used)]
    if not characters:
        return
    log_fn(f'''   Phân vai: tìm thấy {len(characters)} nhân vật có thoại trong {n_cast_scenes} câu — {', '.join((c['ten'] for c in characters[slice(None, 8, None)]))}''' + ('...' if len(characters) > 8 else ''))
    return characters