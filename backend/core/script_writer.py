
"""
Script writer: viết kịch bản review tiếng Việt bằng tài khoản ChatGPT/Gemini trong app.
Approach SCENE-FIRST: su dung Gemini plot_beats timestamps truc tiep lam clip_start/clip_end,
sau do viet thuyet minh KHOP voi tung canh -> giai quyet van de hinh/giong khong sync.
"""
import re
TTS_WPM = 230
MAX_SCENES = 90
MIN_SCENE_SECONDS = 10.0
HARD_MAX_SCENES_V2 = 240
def _llm_text_call(engine, key, prompt, log_fn, max_tokens, temperature=0.7, quality='standard'):
    """AI viết kịch bản = tài khoản ChatGPT/Gemini đăng nhập trong app (engine 'web')."""
    from core import web_llm
    return web_llm.chat(prompt, log_fn)
SCRIPT_MODE_PRESETS = {'review_phim': "Phong cach review phim tom tat kinh dien (kieu kenh SAKURA REVIEW, PIKACHU REVIEW): Ke chuyen ro rang, mach lac, BAM SAT dung canh va dung cot truyen dang dien ra — khong them tinh tiet/cam xuc/binh luan hoa my khong co trong canh. Co the dung 1-2 cum tu chuyen canh nhe (vi du 'khong ngo rang', 'hoa ra') nhung CHI khi thuc su hop ly voi noi dung, KHONG lap lai may moc cac cum nay o nhieu canh lien tiep va KHONG bien thanh van ve, an du, triet ly dai dong.", 'ma_soi_trinh_tham': "Phong cach giai do Ma Soi / Trinh tham (kieu HERO FROM ZERO, ke chuyen song nuoc): Tap trung cao do vao SUY LUAN, manh moi, dau hieu giau danh tinh, lap luan logic va bieu cam nghi ngo. Cu vai canh dat 1 cau hoi treo: 'Lieu ai trong so ho la ke noi doi?', 'Hanh dong bat thuong nay co nghia la gi?', 'Mot chi tiet nho nhung da to cao hung thu...'. Giong narrator phai gay can, toc do cham rai, thi tham hung hon va suy tu.", 'kinh_di_bi_an': "Phong cach kinh di bi an: giong tram, u am,cham rai, nhan manh vao noi so hai va cac yeu to tam linh, quy di. Dung nhieu cau hoi treo ve cam giac: 'Co cam giac ai do dang doi theo ho?', 'Thuc su do la tieng gio hay tieng keu khoc?'.", 'hai_huoc_meme': 'Phong cach hai huoc/meme YouTube VN: giong nhanh, nhe nhang, them nhieu binh luan troll, so sanh hai huoc ve hanh dong ngo nghech cua nhan vat. Loi thoi tre trung, gan gui, thich hop xem giai tri.'}
def _origin_name_rule(origin):
    o = ((origin or '')).strip().lower()
    if o == 'trung':
        return 'Phim TRUNG QUOC/Hoa ngu → ten nhan vat phien am Han Viet (Truong Tam, Lam Kiet...). Ten phim dung ten tieng Viet pho bien neu co.'
    if o == 'han':
        return "Phim HAN QUOC → GIU ten romanized kieu Han (Kim Min Jae, Lee Soo Jin, Park Bo Gum...), TUYET DOI KHONG phien am Han Viet DU thoai goc la tieng Trung (phim long tieng). Ten Sino-Korean (goc Han) doc theo am Han Quoc: 이민준 = 'Lee Min Jun' (KHONG phai 'Ly Dan Tuan'), 나화진 = 'Na Hwa Jin', 김수현 = 'Kim Soo Hyun'. KHONG doc theo am Han Viet."
    if o == 'nhat':
        return 'Phim NHAT → GIU ten romanized Nhat (Tanaka, Sakura...), KHONG phien am Han Viet.'
    if o == 'thai':
        return 'Phim THAI LAN → GIU ten romanized Thai (Somchai, Ploy, Nong...), KHONG phien am Han Viet.'
    if o in ('au-my', 'au_my', 'aumy'):
        return 'Phim AU-MY → giu nguyen ten goc (John, Anna...), KHONG phien am Han Viet.'
    return 'CHUA RO xuat xu → GIU NGUYEN ten romanized goc, CHI phien am Han Viet khi CHAC CHAN la phim Trung Quoc. Ten tieng Anh/Han/Nhat/Thai luon giu nguyen — KHONG bien thanh am Han Viet.'
def write_review_script(analysis, transcript, video_duration, api_key='', target_minutes=12, script_mode='review_phim', log_fn=print, troll_tone=True, user_context='', gemini_key='', openai_key='', quality='standard', deepseek_key='', film_context=''):
    if deepseek_key:
        if not api_key:
            api_key = deepseek_key
    if film_context:
        if not user_context:
            user_context = film_context
    from core import web_llm
    engines = web_llm.with_web([(e, k) for (e, k) in (('deepseek', api_key), ('openai', openai_key), ('gemini', gemini_key)) if k])
    if not engines:
        log_fn('   [LỖI] Chưa có API key (DeepSeek/OpenAI/Gemini) hoặc tài khoản AI web để viết kịch bản')
        return
    if not analysis:
        log_fn('   [LỖI] Không có dữ liệu phân tích phim')
        return
    analysis = dict(analysis)
    user_context = ((user_context or '')).strip()
    analysis['_user_context'] = user_context
    try:
        from .translator import _find_known_titles as _fkt, _get_char_glossary_for_film as _gcgf
        _lookup_text = analysis.get('title_guess', '') + ' ' + analysis.get('summary', '') + ' ' + analysis.get('_user_context', '')
        segs = ((transcript or {})).get('segments', [])
        if segs:
            _lookup_text += ' ' + ' '.join((s.get('text', '') for s in segs[slice(None, 40, None)]))
        _known = _fkt(_lookup_text)
        if _known:
            analysis = dict(analysis)
            (vi_t, src_t) = _known[0]
            if not analysis.get('_vi_title'):
                analysis['_vi_title'] = vi_t
                analysis['_vi_title_src'] = src_t
            log_fn(f'''   → Từ điển cứng (review): {vi_t}''')
            _hard_chars = _gcgf(vi_t)
            if _hard_chars:
                analysis['_char_glossary'] = _hard_chars
                log_fn(f'''   → Glossary nhân vật cứng (review): {len(_hard_chars)} mục''')
    except Exception:
        pass
    try:
        from .translator import _film_key as _fk, _load_film_glossary as _lfg
        _rk = _fk(analysis.get('_vi_title') or '', user_context)
        analysis['_film_key'] = _rk
        _persist = _lfg(_rk)
        if _persist:
            existing = {e.get('src', '').lower(): e for e in analysis.get('_char_glossary', [])}
            merged = list(analysis.get('_char_glossary', []))
            for e in _persist:
                if e['src'].lower() not in existing:
                    merged.insert(0, e)
                else:
                    existing[e['src'].lower()]['vi'] = e['vi']
            analysis['_char_glossary'] = merged
            log_fn(f'''   → Nạp {len(_persist)} tên/vai trò đã chốt từ tập trước (review)''')
    except Exception:
        pass
    scenes_meta = _build_scenes_from_beats(analysis.get('plot_beats', []), video_duration, target_minutes)
    log_fn(f'''   Đã xây dựng {len(scenes_meta)} cảnh từ timestamp của Gemini''')
    scenes_meta = _enrich_scenes_with_transcript(scenes_meta, transcript)
    log_fn('   Đã gán thoại Whisper vào các cảnh (tăng độ khớp hình - giọng)')
    words_per_scene = max(12, int(TTS_WPM * target_minutes / max(1, len(scenes_meta))))
    total_words = words_per_scene * len(scenes_meta)
    log_fn(f'''   Mỗi cảnh cần ~{words_per_scene} từ -> tổng ~{total_words} từ (~{target_minutes} phút)''')
    if words_per_scene < 15:
        log_fn(f'''   [WARN][BL-P1-05] Số từ mỗi cảnh rất thấp ({words_per_scene} < 15) - phim dài/nhiều cảnh so với {target_minutes} phút đã chọn, lời đọc có thể bị cụt. Cân nhắc tăng số phút review.''')
    log_fn(f'''   Gửi yêu cầu viết kịch bản liền mạch tới {engines[0][0]}...''')
    narrations = _write_unified_marked_script(scenes_meta, analysis, words_per_scene, total_words, engines, log_fn, script_mode=script_mode, troll_tone=troll_tone, quality=quality)
    if not narrations:
        log_fn('   [WARN] Kịch bản dạng marked thất bại, thử dự phòng dạng văn bản thường...')
        narrations = _fallback_plain_text(scenes_meta, analysis, words_per_scene, engines, log_fn, quality=quality)
    if not narrations:
        narrations = [_real_desc(s) for s in scenes_meta]
        if sum(1 for t in narrations if t) < max(1, len(scenes_meta) // 2):
            raise RuntimeError('AI không viết được kịch bản có nhãn [Cảnh N] (đã thử 2 cách) — chạy lại hoặc đổi tài khoản AI. '
                               'Không dùng mô tả cảnh tự sinh làm lời đọc.')
        log_fn('   [WARN] Cả hai phương pháp đều thất bại — tạm dùng mô tả cảnh THẬT làm lời (cảnh không có mô tả bị bỏ)')
    final_scenes = []
    for (i, meta) in enumerate(scenes_meta):
        text = narrations[i].strip() if i < len(narrations) else ''
        if not text:
            continue
        limit = meta.get('_word_limit', 0)
        safety_limit = int(limit * 1.05) if limit > 0 else 150
        text = _trim_to_word_limit(text, safety_limit)
        sub = text
        final_scenes.append({'voiceover': text, 'clip_start': meta['clip_start'], 'clip_end': meta['clip_end'], 'subtitle': sub, 'description': meta.get('description', '')})
    import re as _re
    from .tts_engine import replace_numbers_with_words as _r2w
    digits_found = 0
    for s in final_scenes:
        if _re.search('\\d', s['voiceover']):
            digits_found += 1
            s['subtitle'] = s.get('subtitle') or s['voiceover']   # phụ đề giữ chữ số — chỉ lời đọc đổi số thành chữ
            pass  # số → chữ để bước tạo giọng làm (voiceover_for_tts); lời & phụ đề giữ chữ số
    if digits_found:
        log_fn(f'''   {digits_found} cảnh có chữ số — phụ đề giữ chữ số, giọng đọc tự đọc thành chữ''')
    _enforce_total_word_budget(final_scenes, target_minutes, words_per_scene, log_fn)
    est_min = sum((len(s['voiceover'].split()) for s in final_scenes)) / TTS_WPM
    log_fn(f'''   Kịch bản hoàn chỉnh: {len(final_scenes)} cảnh, ~{est_min:.1f} phút TTS''')
    try:
        from .translator import _save_film_glossary as _sfg
        _sfg(analysis.get('_film_key', ''), analysis.get('_char_glossary', []), analysis.get('_vi_title') or '')
    except Exception:
        pass
    return {'scenes': final_scenes, 'num_scene_chapters': len(scenes_meta)}
def _enrich_scenes_with_transcript(scenes_meta, transcript):
    if not transcript or not transcript.get('segments'):
        return scenes_meta
    segs = transcript['segments']
    for scene in scenes_meta:
        start = scene['clip_start']
        end = scene['clip_end']
        lines = [s.get('text', '').strip() for s in segs if s.get('start', 0) < end and s.get('end', s.get('start', 0) + 0.01) > start and s.get('text', '').strip()]
        if lines:
            joined = ' / '.join(lines[slice(None, 6, None)])
            if len(joined) > 300:
                joined = joined[slice(None, 300, None)] + '...'
            scene['_transcript'] = joined
    return scenes_meta
def _safe_float(val, default=0.0):
    """Số giây từ AI: 12 / "12" / "12s" / "12.5 giây" / "1:23" / "01:02:03" → float. Trước "12s" thành 0 → cảnh nhận
    khoảng thời gian rác (đầu phim)."""
    try:
        return float(val)
    except (TypeError, ValueError):
        pass
    t = str(val or '').strip().lower()
    m = re.fullmatch(r'(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)', t)
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.match(r'^(\d+(?:[.,]\d+)?)\s*(?:s|sec|giây|gi[aâ]y)?', t)
    return float(m.group(1).replace(',', '.')) if m else default
def _build_scenes_from_beats(plot_beats, video_duration, target_minutes):
    video_duration = _safe_float(video_duration, 0.0)
    if video_duration <= 0:
        raise ValueError(f'''video_duration khong hop le ({video_duration}) — khong the tao scenes.''')
    min_scenes = int(min(MAX_SCENES, max(4, min(max(6, target_minutes * 5), int(video_duration / MIN_SCENE_SECONDS)))))
    if not plot_beats or len(plot_beats) < 4:
        n_fb = min_scenes
        step_fb = video_duration / n_fb
        plot_beats = [{'timestamp': i * step_fb, 'description': f'''Phan {i + 1} trong {n_fb}''', '_placeholder': True} for i in range(n_fb)]
    beats = sorted((b for b in plot_beats if _safe_float(b.get('timestamp', 0)) < video_duration), key=lambda b: _safe_float(b.get('timestamp', 0)))
    if len(beats) < min_scenes:
        real_beats = list(beats)
        existing_ts = {_safe_float(b.get('timestamp', 0)) for b in beats}
        for i in range(0, min_scenes):
            ts = video_duration * i / min_scenes
            if any((abs(ts - e) < 5.0 for e in existing_ts)):
                continue
            nearest_desc = ''
            if real_beats:
                nearest = min(real_beats, key=lambda b: abs(_safe_float(b.get('timestamp', 0)) - ts))
                nearest_desc = nearest.get('description', '')
            beats.append({'timestamp': ts, 'description': nearest_desc or f'''Tiep dien canh {ts:.0f}s''', '_placeholder': not nearest_desc})
            existing_ts.add(ts)
        beats = sorted(beats, key=lambda b: _safe_float(b.get('timestamp', 0)))
    scene_cap = min(MAX_SCENES, max(min_scenes, int(video_duration / MIN_SCENE_SECONDS)))
    if len(beats) > scene_cap:
        gap = max(MIN_SCENE_SECONDS, video_duration / scene_cap)
        kept = [beats[0]]
        for b in beats[slice(1, None, None)]:
            if len(kept) >= scene_cap:
                break
            if _safe_float(b.get('timestamp', 0)) - _safe_float(kept[-1].get('timestamp', 0)) >= gap:
                kept.append(b)
        beats = kept
    scenes = []
    for (i, beat) in enumerate(beats):
        clip_start = round(_safe_float(beat.get('timestamp', 0)), 1)
        if i + 1 < len(beats):
            clip_end = round(_safe_float(beats[i + 1].get('timestamp', 0)), 1)
        else:
            clip_end = round(float(video_duration), 1)
        clip_end = min(clip_end, float(video_duration))
        if clip_end - clip_start < 2.0:
            continue
        desc = str(beat.get('description') or '').strip()
        scenes.append({'clip_start': clip_start, 'clip_end': clip_end, 'description': desc or f'''Canh {i + 1}''',
                       '_placeholder': bool(beat.get('_placeholder')) or not desc or _is_placeholder(desc)})
    return scenes
_PLACEHOLDER_RE = re.compile(r'^\s*(?:ph[aầ]n\s+\d+\s+trong\s+\d+|ti[eế]p\s+di[eễ]n\s+c[aả]nh\b.*|c[aả]nh\s+\d+)\s*$', re.IGNORECASE)


def _is_placeholder(desc):
    """Mô tả GIẢ do code tự sinh khi thiếu dữ liệu ("Phan 3 trong 60", "Tiep dien canh 120s", "Canh 5") — không phải
    nội dung hình → không bao giờ được đọc thành lời thuyết minh."""
    return bool(_PLACEHOLDER_RE.match(str(desc or '')))


def _real_desc(meta):
    """Mô tả cảnh dùng được làm lời dự phòng — '' nếu là mô tả giả."""
    d = str((meta or {}).get('description') or '').strip()
    return '' if not d or (meta or {}).get('_placeholder') or _is_placeholder(d) else d


_SENT_END_RE = re.compile('(?:\\.{3}|…|[.!?])["\\\'”’»]?(?=\\s|$)')
def _trim_to_word_limit(text, max_words):
    words = text.split()
    if len(words) <= max_words:
        return text
    if max_words <= 0:
        return text
    kept = ' '.join(words[slice(None, max_words, None)])
    min_keep = int(max_words * 0.65)
    last = None
    for last in _SENT_END_RE.finditer(kept):
        pass
    if last is not None:
        cand = kept[slice(None, last.end(), None)].strip()
        if cand:
            if len(cand.split()) >= min_keep:
                return cand
    c = max(kept.rfind(','), kept.rfind(';'), kept.rfind('，'), kept.rfind('；'))
    if c > 0:
        cand = kept[slice(None, c, None)].rstrip()
        if cand:
            if len(cand.split()) >= min_keep:
                return cand + '…'
    if kept.endswith(('.', '!', '?', '…')):
        return kept
    return kept + '…'
def _enforce_total_word_budget(final_scenes, target_minutes, words_per_scene, log_fn=print):
    if not final_scenes:
        return
    global_budget = int(target_minutes * TTS_WPM * 1.2)
    def _wc(s):
        return len(s.get('voiceover', '').split())
    total = sum((_wc(s) for s in final_scenes))
    if total <= global_budget:
        return
    log_fn(f'''   [BL-P1-05] Tổng {total} từ vượt ngân sách {global_budget} ({target_minutes} phút x {TTS_WPM} wpm x 1.2) -> cắt cảnh dài nhất trước.''')
    floor = max(1, int(words_per_scene))
    guard = 0
    while total > global_budget and guard < 10 * len(final_scenes):
        guard += 1
        s = max(final_scenes, key=_wc)
        wc = _wc(s)
        if wc <= floor:
            break
        new_limit = max(floor, wc - (total - global_budget))
        if new_limit >= wc:
            new_limit = wc - 1
        s['voiceover'] = _trim_to_word_limit(s['voiceover'], new_limit)
        if 'subtitle' in s:
            s['subtitle'] = s['voiceover']
        total = sum((_wc(x) for x in final_scenes))
    if total > global_budget:
        log_fn(f'''   [WARN][BL-P1-05] Đã cắt các cảnh dài nhất về mức sàn {floor} từ/cảnh nhưng tổng vẫn {total} từ (~{total / TTS_WPM:.1f} phút) > ngân sách {global_budget} — video sẽ dài hơn mục tiêu {target_minutes} phút.''')
    else:
        log_fn(f'''   [BL-P1-05] Sau khi cắt: {total} từ (~{total / TTS_WPM:.1f} phút) <= ngân sách {global_budget}.''')
# Lời đọc dài hơn hình thì không nới được (sẽ lấn sang cảnh sau) → bước tự hậu kỳ phải nhờ AI viết lại.
# Nên chia số từ THEO ĐỘ DÀI HÌNH từng cảnh ngay từ đầu (cùng công thức với hậu kỳ: giây × tốc độ đọc × 0.92).
_SCRIPT_WPS = 230 / 60          # tốc độ đọc chậm nhất (Edge) — giọng nhanh hơn (CapCut) thì lời càng vừa hình
_SCRIPT_FILL = 0.92


def _per_scene_word_targets(scenes_meta, total_words, floor=12):
    """Chia tổng số từ cho các cảnh: mỗi cảnh không quá sức chứa của hình (giây × tốc độ đọc), phần dư dồn sang cảnh
    hình dài (hình thừa sẽ được tự cắt cho khớp lời) — tổng vẫn ≈ ngân sách theo số phút người dùng chọn."""
    caps = [max(floor, int(max(2.0, s['clip_end'] - s['clip_start']) * _SCRIPT_WPS * _SCRIPT_FILL)) for s in scenes_meta]
    if sum(caps) <= total_words:
        return caps
    (lo, hi) = (floor, max(caps))
    while hi - lo > 1:                       # tìm mức trần chung x: sum(min(cap, x)) ≈ ngân sách
        mid = (lo + hi) // 2
        if sum(min(c, mid) for c in caps) > total_words:
            hi = mid
        else:
            lo = mid
    return [min(c, lo) for c in caps]


def _write_unified_marked_script(scenes_meta, analysis, words_per_scene, total_words, engines, log_fn=print, script_mode='review_phim', troll_tone=True, quality='standard'):
    style_directive = SCRIPT_MODE_PRESETS.get(script_mode, SCRIPT_MODE_PRESETS['review_phim'])
    targets = _per_scene_word_targets(scenes_meta, total_words)
    short = sum(1 for t in targets if t < words_per_scene * 0.85)
    if short:
        log_fn(f'   Số từ theo độ dài hình: {short} cảnh hình ngắn được viết gọn hơn (tránh lời dài hơn hình)')
    scenes_text_list = []
    for (idx, s) in enumerate(scenes_meta):
        s['_word_target'] = targets[idx]
        s['_word_limit'] = int(targets[idx] * 1.15) + 2
        dial = s.get('_transcript', '')
        head = f'''Cảnh {idx + 1} (viết ~{targets[idx]} từ)'''
        if dial:
            scenes_text_list.append(f'''{head}: {s['description']} [Thoại gốc: {dial}]''')
        else:
            scenes_text_list.append(f'''{head}: {s['description']}''')
    scenes_text = '\n'.join(scenes_text_list)
    tone_str = '''Bổ sung: Giọng văn kể chuyện phải hơi troll, vui vẻ, hóm hỉnh và pha chút châm biếm hài hước để người xem thích thú bật cười.

''' if troll_tone else 'Bổ sung: Giọng văn kể chuyện nghiêm túc, kịch tính, lôi cuốn và bám sát vào cảm xúc thực tế, bối cảnh phim.\n\n'
    _uc = ((analysis.get('_user_context') or '')).strip()
    _uc_block = f'''*** BỐI CẢNH NGƯỜI DÙNG CUNG CẤP — ƯU TIÊN TUYỆT ĐỐI, TIN TƯỞNG HOÀN TOÀN ***\n{_uc}\n→ Dùng đúng tên phim, tên/vai trò nhân vật và xuất xứ như người dùng mô tả.\n\n''' if _uc else ''
    prompt = f'''Bạn là nhà biên kịch và bình luận phim chuyên nghiệp cho các kênh YouTube Movie Recap hàng đầu Việt Nam.\nMục tiêu là kể lại ĐÚNG những gì đang diễn ra trong cảnh, theo sát cốt truyện thực tế — dễ hiểu, mạch lạc, KHÔNG văn vẻ/thơ ca/triết lý vẽ vời, KHÔNG tự bịa thêm cảm xúc hay chi tiết không có trong cảnh.\n\n{_uc_block}PHONG CÁCH DIỄN ĐẠT CHỦ ĐẠO:\n{style_directive}\n{tone_str}QUY TẮC TÊN RIÊNG & BIỆT DANH (CỰC KỲ QUAN TRỌNG — TUYỆT ĐỐI KHÔNG DÙNG HÁN-VIỆT):\n1. TÊN PHIM: dịch nghĩa sang tiếng Việt tự nhiên hoặc giữ tên tiếng Anh/gốc. TUYỆT ĐỐI KHÔNG dùng tên phiên âm Hán-Việt (ví dụ KHÔNG \'Quỷ Xuy Đăng\', KHÔNG \'Khánh Dư Niên\' — hãy dùng \'Ma Thổi Đèn\', \'Niềm Vui Cuộc Sống\').\n2. TÊN NHÂN VẬT: {_origin_name_rule(analysis.get('origin', ''))} TUYỆT ĐỐI KHÔNG phiên âm Hán-Việt tên người (KHÔNG \'Tiểu Phi\', \'Trương Tam\'...).\n   ĐẶC BIỆT - PHIM LỒNG TIẾNG TRUNG: nếu nhân vật có tên dạng \'Xiao X\' (Xiao Min, Xiao Piao, Xiao Ba...) — đây là tên Trung của phim Hàn/Nhật/Thái lồng tiếng. Nếu BIẾT tên thật thì dùng tên romanized (Hàn/Nhật/Thái). Nếu KHÔNG biết tên thật: KHÔNG giữ pinyin \'Xiao X\' và KHÔNG Hán-Việt hóa, mà GÁN MỘT VAI TRÒ/BIỆT DANH THUẦN VIỆT cố định theo vai trò nhân vật (ví dụ \'cậu học trò quậy\', \'cô bé lớp trưởng\', \'gã đầu gấu\', \'ông trùm\') và DÙNG NHẤT QUÁN suốt cả phim.\n''' + (('   BẢNG TÊN/VAI TRÒ CHÍNH XÁC (BẮT BUỘC DÙNG ĐÚNG, NHẤT QUÁN):\n' + ''.join((f'''   - \'{e['src']}\' → \'{e['vi']}\'\n''' for e in analysis['_char_glossary'][slice(None, 8, None)]))) if analysis.get('_char_glossary') else '') + f'''3.Có thể tự tạo biệt danh hài hước, dí dỏm cho nhân vật phụ dựa vào ngoại hình hoặc hành động (ví dụ: \'anh mắt lác\', \'chị đại tóc đỏ\', \'gã đầu hói\'...) — nhưng phải dùng NHẤT QUÁN một biệt danh cho một nhân vật. Nếu không có đặc điểm nổi bật thì thôi.\n\nTHÔNG TIN CHUNG VỀ BỘ PHIM:\n- Tên phim (DÙNG CHÍNH XÁC TÊN NÀY): {analysis.get('_vi_title') or '?'}''' + (f''' (tên gốc: {analysis['_vi_title_src']})''' if analysis.get('_vi_title_src') else '') + f'''\n- Xuất xứ: {analysis.get('origin', 'chưa rõ')}\n- Thể loại: {analysis.get('genre', '?')}\n- Nhân vật chính: {', '.join((str(c) for c in analysis.get('main_characters', [])[slice(None, 4, None)]))}\n- Bối cảnh: {analysis.get('setting', '')}\n- Tóm tắt cốt truyện hoàn chỉnh: {analysis.get('summary', '')}\n\nDANH SÁCH {len(scenes_meta)} CẢNH PHIM THEO TRÌNH TỰ THỜI GIAN:\n{scenes_text}\n\nNHIỆM VỤ:\nHãy viết một kịch bản thuyết minh kể chuyện phim (Movie Recap) hoàn chỉnh, liền mạch, thống nhất từ đầu đến cuối dài khoảng {total_words} từ.\nBắt buộc chia kịch bản thành đúng {len(scenes_meta)} phần tương ứng với {len(scenes_meta)} cảnh ở trên.\nĐầu mỗi phần phải bắt đầu bằng nhãn [Cảnh N] (ví dụ: [Cảnh 1], [Cảnh 2]...).\n\nYÊU CẦU CHẤT LƯỢNG KỊCH BẢN (TIÊU CHUẨN 9-10/10 ĐIỂM):\n1. BÁM SÁT HÌNH ẢNH VÀ NỘI DUNG PHIM (QUAN TRỌNG NHẤT): Mỗi [Cảnh N] PHẢI kể đúng nội dung/hình ảnh của Cảnh N trong danh sách trên — vì lời đọc sẽ phát ĐÈ LÊN đúng đoạn video đó. Người xem nhìn thấy gì trên màn hình thì lời đọc phải nói về thứ đó. TUYỆT ĐỐI KHÔNG bịa ra sự kiện, cốt truyện sai lệch hoàn toàn với phim gốc, không phóng tác lung tung làm lệch nội dung chính của phim. Phải bám sát mô tả cảnh và phụ đề thoại gốc đi kèm.\n   ƯU TIÊN ĐỘ CHÍNH XÁC HƠN CHẤT VĂN: kể thẳng, đúng việc đang xảy ra. KHÔNG thêm câu cảm thán/suy ngẫm/đánh giá hoa mỹ không bắt nguồn từ chính cảnh đó (TRÁNH kiểu: \'một chiến thắng nhỏ nhưng vô cùng quan trọng\', \'công lý dường như quá xa xỉ\' — đây là bình luận tự bịa, không phải mô tả cảnh).\n2. VĂN PHONG TỰ NHIÊN, KHÔNG SÁO RỖNG: Viết như người Việt kể chuyện đời thường, rõ ràng dễ hiểu. TUYỆT ĐỐI TRÁNH văn vẻ rườm rà, ẩn dụ triết lý lê thê (TRÁNH kiểu: \'bóng tối không chỉ là sự vắng mặt của ánh sáng, mà còn là nơi ẩn náu của những bí mật chết người\'). Câu chữ gọn gàng, đi thẳng vào sự việc đang diễn ra.\n3. NHẤT QUÁN TÊN/CÁCH GỌI NHÂN VẬT: Một nhân vật chỉ gọi bằng MỘT tên/vai trò cố định xuyên suốt. KHÔNG được khi gọi \'người mẹ\' lúc lại gọi \'cô gái trẻ\' cho cùng một người. Nếu không rõ tên thì gọi theo vai trò cố định (người mẹ, đứa con, ông chủ...) và giữ nguyên đến hết.\n4. TUYỆT ĐỐI KHÔNG chép nguyên câu thoại nhân vật vào lời thuyết minh (TRÁNH: \'Anh nói: Mày là cái gì?\'). Thay vào đó, diễn giải sự kiện theo góc nhìn narrator (NÊN: \'Người đàn ông lạ mặt bất ngờ xuất hiện, khiến cả đám không kịp phản ứng\').\n5. HOOK Ở CẢNH 1: Cảnh đầu mở màn bằng một câu dẫn cuốn hút, tóm gọn mâu thuẫn chính của phim — nhưng vẫn phải đúng với hình ảnh đang chiếu ở cảnh đầu. NGOẠI LỆ: nếu mô tả cảnh đầu chỉ là logo hãng phim/màn hình thông tin sản xuất/màn đen (có ghi \'(logo/intro sản xuất)\') thì TUYỆT ĐỐI KHÔNG thuyết minh về màn hình đó — hãy viết thẳng câu hook giới thiệu mâu thuẫn chính của phim.\n6. LIÊN KẾT MƯỢT MÀ NHƯNG TIẾT CHẾ: Lời cảnh N và N+1 nối logic tự nhiên, ưu tiên nối bằng chính nội dung sự kiện (vd: nhắc lại hệ quả của cảnh trước). CHỈ dùng cụm mở kiểu \'Không ngờ rằng...\', \'Đúng lúc này...\', \'Hóa ra...\' khi thực sự hợp lý, KHÔNG dùng liên tục ở nhiều cảnh kế tiếp (tối đa 1/3 số cảnh) vì sẽ gây sáo rỗng, lặp khuôn.\n7. SỐ LƯỢNG TỪ MỖI CẢNH — BẮT BUỘC TUÂN THỦ CHẶT: Mỗi cảnh có ghi số từ riêng ở danh sách trên ('viết ~N từ') — PHẢI viết đúng khoảng N từ (lệch tối đa ±10%), vì lời đọc phát đè đúng đoạn hình dài tương ứng: cảnh hình ngắn thì viết gọn, cảnh hình dài thì kể kỹ hơn. Đây là giới hạn CỨNG — viết quá số từ này sẽ làm TỔNG thời lượng video vượt xa thời lượng khách yêu cầu ({total_words} từ cho toàn bộ {len(scenes_meta)} cảnh). Ưu tiên câu ngắn gọn, đúng trọng tâm, đi thẳng vào sự việc thay vì mô tả chi tiết dài dòng để giữ đúng giới hạn này.\n8. ĐẢM BẢO kết thúc kịch bản (cảnh cuối) có lời chốt ấn tượng, giữ khoảnh lặng cảm xúc hoặc câu hỏi suy ngẫm, kèm 1 câu kêu gọi đăng ký kênh tự nhiên.\n9. TUYỆT ĐỐI KHÔNG DÙNG CHỮ SỐ (0-9): Kịch bản sẽ được đọc bằng phần mềm giọng nói (TTS) — nếu có chữ số, giọng đọc sẽ bị lỗi. Thay mọi chữ số bằng chữ tiếng Việt. Ví dụ: thay \'2026\' → \'hai nghìn không trăm hai mươi sáu\', \'3 người\' → \'ba người\', \'100 năm\' → \'một trăm năm\', \'tập 12\' → \'tập mười hai\', \'thế kỷ 19\' → \'thế kỷ mười chín\'. Đây là yêu cầu bắt buộc, không có ngoại lệ.\n10. GIỮ ĐÚNG TRÌNH TỰ NHÂN-QUẢ, KHÔNG ĐẢO/GỘP CẢNH XA NHAU: Cảnh N chỉ được nhắc lại/liên hệ với cảnh N-1 (cảnh LIỀN TRƯỚC nó) — TUYỆT ĐỐI KHÔNG suy đoán, gộp hay đảo trình tự sự kiện của các cảnh xa hơn (N-2, N-3...) vào cảnh N, kể cả khi cố tạo liên kết mượt mà. Nếu không chắc điều gì xảy ra trước/sau, chỉ kể đúng nội dung của cảnh N như mô tả, không suy diễn quan hệ nhân-quả với cảnh xa.\n\nChỉ trả về phần kịch bản thuyết minh bắt đầu từ [Cảnh 1], không thêm lời giới thiệu hay đính kèm nào khác.'''
    max_tokens = min(64000, len(scenes_meta) * 150 + 1000)
    content = ''
    for (idx, (eng, key)) in enumerate(engines):
        content = _llm_text_call(eng, key, prompt, log_fn, max_tokens, temperature=0.7, quality=quality)
        if content:
            break
        next_engines = [e for (e, _) in engines[slice(idx + 1, None, None)]]
        if next_engines:
            log_fn(f'''   [FALLBACK] \'{eng}\' lỗi/rỗng -> chuyển sang \'{next_engines[0]}\'...''')
    if not content:
        return None
    return _parse_marked_script(content, len(scenes_meta), log_fn, scenes_meta=scenes_meta)
# Dấu cảnh: "[Cảnh 3]", "[Cảnh 3 – Mở đầu]", "**Cảnh 3**", "Cảnh 3:" ở đầu dòng.
# Số cảnh có thể là chữ số hoặc viết bằng chữ ("[Cảnh ba]", "[Cảnh mười hai]") — AI web hay viết kiểu sau.
_VN_UNITS = {'không': 0, 'một': 1, 'mốt': 1, 'hai': 2, 'ba': 3, 'bốn': 4, 'tư': 4, 'năm': 5, 'lăm': 5,
             'sáu': 6, 'bảy': 7, 'bẩy': 7, 'tám': 8, 'chín': 9}
_NUM = r'(\d+|(?:(?:một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|bẩy|tám|chín|mười|mươi|không)\b\s*){1,3})'
_SCENE_MARKER = re.compile(rf'\[\s*Cảnh\s*{_NUM}[^\]\n]{{0,60}}\]|\*\*\s*Cảnh\s*{_NUM}[^*\n]{{0,60}}\*\*|^\s*Cảnh\s*{_NUM}\s*[:：]',
                           re.IGNORECASE | re.MULTILINE)
_MARKER_LEFTOVER = re.compile(r'^\s*\[\s*Cảnh[^\]\n]{0,60}\]\s*$', re.IGNORECASE | re.MULTILINE)
_LEADING_LABEL = re.compile(r'^\s*(?:\[\s*Cảnh[^\]\n]{0,60}\]|\*\*\s*Cảnh[^*\n]{0,60}\*\*)\s*[:：\-–]?\s*', re.IGNORECASE)


def _scene_number(token):
    """'12' / 'mười hai' / 'hai mươi mốt' → int; không đọc được → None."""
    token = (token or '').strip().lower()
    if m := re.match(r'\d+', token):
        return int(m.group())
    words = token.split()
    if not words:
        return None
    if words[0] == 'mười':
        return 10 + (_VN_UNITS.get(words[1], 0) if len(words) > 1 else 0)
    if len(words) >= 2 and words[1] == 'mươi' and words[0] in _VN_UNITS:
        return _VN_UNITS[words[0]] * 10 + (_VN_UNITS.get(words[2], 0) if len(words) > 2 else 0)
    return _VN_UNITS.get(words[0]) or None


def strip_scene_label(text):
    """Bỏ nhãn "[Cảnh N]" / "**Cảnh N**" còn sót ở đầu lời đọc — để lại thì TTS đọc to cả nhãn."""
    prev = None
    while prev != text:
        prev, text = text, _LEADING_LABEL.sub('', text or '')
    return text.strip()


def _parse_marked_script(content, num_scenes, log_fn=print, scenes_meta=None):
    from core.web_llm import clean_reply
    content = clean_reply(content)  # NFC, bỏ khối :::writing{...} của ChatGPT web, ký tự vô hình
    content = re.sub('^```(?:markdown|text)?\\s*', '', content.strip())
    content = re.sub('\\s*```$', '', content.strip()).strip()
    pattern = _SCENE_MARKER
    matches = list(pattern.finditer(content))
    scenes_text = {}
    _dup_labels = []
    if matches:
        for i in range(len(matches)):
            start_idx = matches[i].end()
            end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            groups = matches[i].groups()
            scene_num = next((n for n in (_scene_number(g) for g in groups if g) if n), i + 1)
            text_block = _MARKER_LEFTOVER.sub('', content[slice(start_idx, end_idx, None)]).strip()
            text_block = re.sub('^[\\s\\-:]+', '', text_block)
            if scene_num not in scenes_text:
                scenes_text[scene_num] = text_block
            else:
                _dup_labels.append(scene_num)
                # Trùng nhãn: giữ khối DÀI hơn — khối đầu thường chỉ là dòng tiêu đề/mục lục, không phải lời đọc.
                if len(text_block) > len(scenes_text[scene_num]):
                    scenes_text[scene_num] = text_block
    else:
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        for (idx, p) in enumerate(paragraphs):
            scenes_text[idx + 1] = p
    final_narrations = []
    for s_id in range(1, num_scenes + 1):
        txt = strip_scene_label(scenes_text.get(s_id, ''))
        final_narrations.append(txt)
    non_empty = [t for t in final_narrations if t]
    log_fn(f'''   Parser: Đã phân tích {len(non_empty)}/{num_scenes} cảnh có lời thuyết minh''')
    if _dup_labels:
        log_fn(f'''   [WARN] AI ghi trung nhan [Cảnh N] cho {len(set(_dup_labels))} cảnh ({sorted(set(_dup_labels))[slice(None, 10, None)]}{'...' if len(set(_dup_labels)) > 10 else ''}) — đã giữ bản dài nhất (bỏ dòng tiêu đề/mục lục trùng nhãn).''')
    if len(non_empty) < num_scenes * 0.7:
        # KHÔNG chia đều văn bản cho các cảnh: lời kể sẽ lệch hình (cảnh 5 đọc chuyện cảnh 8) — để bước gọi thử lại / báo lỗi
        log_fn(f'   [WARN] Chỉ khớp được nhãn [Cảnh N] cho {len(non_empty)}/{num_scenes} cảnh — không chia đều (sẽ lệch lời với hình)')
        return None
    n_own_desc = 0
    n_dropped = 0
    for i in range(num_scenes):
        if final_narrations[i]:
            continue
        own_desc = ''
        if scenes_meta:
            if i < len(scenes_meta):
                own_desc = _real_desc(scenes_meta[i])    # mô tả giả ("Phan 3 trong 60") → bỏ cảnh, không đọc thành lời
        if own_desc:
            final_narrations[i] = own_desc
            n_own_desc += 1
        else:
            final_narrations[i] = ''
            n_dropped += 1
    if n_own_desc:
        log_fn(f'''   [WARN] {n_own_desc} cảnh AI không đánh nhãn -> tạm dùng mô tả cảnh (đúng nội dung hình ảnh, có thể chưa mượt văn phong) thay vì mượn lời cảnh khác.''')
    if n_dropped:
        log_fn(f'''   [WARN] {n_dropped} cảnh không có lời thuyết minh lẫn mô tả dự phòng -> bị bỏ qua khỏi video (an toàn hơn là lấy nhầm nội dung cảnh khác).''')
    return final_narrations
def _fallback_plain_text(scenes_meta, analysis, words_per_scene, engines, log_fn=print, quality='standard'):
    total_words = words_per_scene * len(scenes_meta)
    beats_text = '\n'.join((f'''- [Cảnh {i + 1}]: {_real_desc(s) or '(chưa có mô tả — kể tiếp mạch truyện)'}''' for (i, s) in enumerate(scenes_meta)))
    _vi_title = analysis.get('_vi_title') or '?'
    _src_title = analysis.get('_vi_title_src', '')
    title_line = f'''Tên phim (DÙNG ĐÚNG TÊN NÀY): {_vi_title}''' + (f''' ({_src_title})''' if _src_title else '')
    prompt = f'''Bạn là biên kịch viết kịch bản review phim (Movie Recap) cho kênh YouTube Việt Nam.\n{title_line}\nThể loại: {analysis.get('genre', '?')}. Tóm tắt cốt truyện: {analysis.get('summary', '')}\nCác mốc sự kiện chính:\n{beats_text}\n\nNHIỆM VỤ: Viết một bài thuyết minh kể chuyện phim bằng tiếng Việt dài khoảng {total_words} từ, liền mạch, dễ hiểu, giải thích rõ động cơ nhân vật và các tình tiết cốt truyện từ đầu đến cuối phim. Tránh miêu tả hình ảnh thô sơ.\nQUY TẮC TÊN PHIM: dùng tên tiếng Việt phổ biến (ví dụ \'Ma Thổi Đèn\', \'Chân Hoàn Truyện\').\nQUY TẮC TÊN NHÂN VẬT: {_origin_name_rule(analysis.get('origin', ''))}\nQUAN TRỌNG: TUYỆT ĐỐI KHÔNG dùng chữ số (0-9). Viết tất cả số bằng chữ tiếng Việt (ví dụ: \'ba người\', \'hai nghìn hai mươi sáu\', \'một trăm năm\').\nĐỊNH DẠNG BẮT BUỘC: chia bài thành đúng {len(scenes_meta)} đoạn theo thứ tự các mốc trên, MỖI đoạn mở đầu bằng nhãn [Cảnh N] (N = 1…{len(scenes_meta)}) rồi tới lời thuyết minh của đúng mốc đó. Không bỏ nhãn, không gộp 2 mốc vào 1 đoạn.\nChỉ trả về văn bản thuần (các đoạn có nhãn), không markdown, không JSON.'''
    fallback_max_tokens = min(64000, len(scenes_meta) * 150 + 1000)
    text = ''
    for (eng, key) in engines:
        text = _llm_text_call(eng, key, prompt, log_fn, fallback_max_tokens, temperature=0.8, quality=quality)
        if text:
            break
    if not text:
        return None
    parsed = _parse_marked_script(text, len(scenes_meta), log_fn, scenes_meta=scenes_meta)
    if parsed:
        return parsed
    log_fn('   [WARN] Bản dự phòng cũng thiếu nhãn [Cảnh N] — không chia đều (sẽ lệch lời với hình)')
    return None
def _split_text_to_n(text, n):
    if n <= 0:
        if text.strip():
            return [text]
        return []
    words = text.split()
    size = max(1, len(words) // n)
    parts = []
    for i in range(n):
        start = i * size
        end = (i + 1) * size if i < n - 1 else len(words)
        parts.append(' '.join(words[slice(start, end, None)]))
    return parts
def _clean_json_newlines(s):
    result = []
    in_quotes = False
    escape = False
    for c in s:
        if escape:
            result.append(c)
            escape = False
            continue
        if c == '\\':
            result.append(c)
            escape = True
            continue
        if c == '"':
            in_quotes = not in_quotes
            result.append(c)
            continue
        if c == '\n' and in_quotes:
            result.append('\\n')
            continue
        result.append(c)
    return ''.join(result)
def _prepare_review_analysis(analysis, transcript, api_key, log_fn=print):
    try:
        from .translator import _find_known_titles as _fkt, _get_char_glossary_for_film as _gcgf
        _lookup_text = analysis.get('title_guess', '') + ' ' + analysis.get('summary', '') + ' ' + analysis.get('_user_context', '')
        segs = ((transcript or {})).get('segments', [])
        if segs:
            _lookup_text += ' ' + ' '.join((s.get('text', '') for s in segs[slice(None, 40, None)]))
        _known = _fkt(_lookup_text)
        if _known:
            (vi_t, src_t) = _known[0]
            if not analysis.get('_vi_title'):
                analysis['_vi_title'] = vi_t
                analysis['_vi_title_src'] = src_t
            log_fn(f'''   → Từ điển cứng (review): {vi_t}''')
            _hard_chars = _gcgf(vi_t)
            if _hard_chars:
                analysis['_char_glossary'] = _hard_chars
                log_fn(f'''   → Glossary nhân vật cứng (review): {len(_hard_chars)} mục''')
    except Exception:
        pass
    try:
        from .translator import _film_key as _fk, _load_film_glossary as _lfg
        _rk = _fk(analysis.get('_vi_title') or '', analysis.get('_user_context', ''))
        analysis['_film_key'] = _rk
        _persist = _lfg(_rk)
        if _persist:
            existing = {e.get('src', '').lower(): e for e in analysis.get('_char_glossary', [])}
            merged = list(analysis.get('_char_glossary', []))
            for e in _persist:
                if e['src'].lower() not in existing:
                    merged.insert(0, e)
                else:
                    existing[e['src'].lower()]['vi'] = e['vi']
            analysis['_char_glossary'] = merged
            log_fn(f'''   → Nạp {len(_persist)} tên/vai trò đã chốt từ tập trước (review)''')
    except Exception:
        pass
def _finish_review_script(scenes_meta, analysis, transcript, target_minutes, engines, script_mode, troll_tone, quality, log_fn=print):
    scenes_meta = _enrich_scenes_with_transcript(scenes_meta, transcript)
    log_fn('   Đã gán thoại Whisper vào các cảnh (tăng độ khớp hình - giọng)')
    words_per_scene = max(12, int(TTS_WPM * target_minutes / max(1, len(scenes_meta))))
    total_words = words_per_scene * len(scenes_meta)
    log_fn(f'''   Mỗi cảnh cần ~{words_per_scene} từ -> tổng ~{total_words} từ (~{target_minutes} phút)''')
    if words_per_scene < 15:
        log_fn(f'''   [WARN][BL-P1-05] Số từ mỗi cảnh rất thấp ({words_per_scene} < 15) - phim dài/nhiều cảnh so với {target_minutes} phút đã chọn, lời đọc có thể bị cụt. Cân nhắc tăng số phút review.''')
    log_fn(f'''   Gửi yêu cầu viết kịch bản liền mạch tới {engines[0][0]}...''')
    narrations = _write_unified_marked_script(scenes_meta, analysis, words_per_scene, total_words, engines, log_fn, script_mode=script_mode, troll_tone=troll_tone, quality=quality)
    if not narrations:
        log_fn('   [WARN] Kịch bản dạng marked thất bại, thử dự phòng dạng văn bản thường...')
        narrations = _fallback_plain_text(scenes_meta, analysis, words_per_scene, engines, log_fn, quality=quality)
    if not narrations:
        narrations = [_real_desc(s) for s in scenes_meta]
        if sum(1 for t in narrations if t) < max(1, len(scenes_meta) // 2):
            raise RuntimeError('AI không viết được kịch bản có nhãn [Cảnh N] (đã thử 2 cách) — chạy lại hoặc đổi tài khoản AI. '
                               'Không dùng mô tả cảnh tự sinh làm lời đọc.')
        log_fn('   [WARN] Cả hai phương pháp đều thất bại — tạm dùng mô tả cảnh THẬT làm lời (cảnh không có mô tả bị bỏ)')
    final_scenes = []
    for (i, meta) in enumerate(scenes_meta):
        text = narrations[i].strip() if i < len(narrations) else ''
        if not text:
            continue
        limit = meta.get('_word_limit', 0)
        safety_limit = int(limit * 1.05) if limit > 0 else 150
        text = _trim_to_word_limit(text, safety_limit)
        final_scenes.append({'voiceover': text, 'clip_start': meta['clip_start'], 'clip_end': meta['clip_end'], 'subtitle': text,
                             'description': _real_desc(meta)})   # giữ mô tả cảnh cho AI hậu kỳ (không có thì AI dễ bịa)
    import re as _re
    from .tts_engine import replace_numbers_with_words as _r2w
    digits_found = 0
    for s in final_scenes:
        if _re.search('\\d', s['voiceover']):
            digits_found += 1
            s['subtitle'] = s.get('subtitle') or s['voiceover']   # phụ đề giữ chữ số — chỉ lời đọc đổi số thành chữ
            pass  # số → chữ để bước tạo giọng làm (voiceover_for_tts); lời & phụ đề giữ chữ số
    if digits_found:
        log_fn(f'''   {digits_found} cảnh có chữ số — phụ đề giữ chữ số, giọng đọc tự đọc thành chữ''')
    _enforce_total_word_budget(final_scenes, target_minutes, words_per_scene, log_fn)
    est_min = sum((len(s['voiceover'].split()) for s in final_scenes)) / TTS_WPM
    log_fn(f'''   Kịch bản hoàn chỉnh: {len(final_scenes)} cảnh, ~{est_min:.1f} phút TTS''')
    try:
        from .translator import _save_film_glossary as _sfg
        _sfg(analysis.get('_film_key', ''), analysis.get('_char_glossary', []), analysis.get('_vi_title') or '')
    except Exception:
        pass
    return {'scenes': final_scenes, 'num_scene_chapters': len(scenes_meta)}
def write_review_script_v2(analysis, transcript, video_duration, video_path, api_key='', target_minutes=12, script_mode='review_phim', log_fn=print, troll_tone=True, user_context='', gemini_key='', openai_key='', quality='standard', deepseek_key='', film_context='', temp_dir=''):
    if deepseek_key:
        if not api_key:
            api_key = deepseek_key
    if film_context:
        if not user_context:
            user_context = film_context
    from core import web_llm
    engines = web_llm.with_web([(e, k) for (e, k) in (('deepseek', api_key), ('openai', openai_key), ('gemini', gemini_key)) if k])
    if not engines:
        log_fn('   [LỖI] Chưa có API key (DeepSeek/OpenAI/Gemini) hoặc tài khoản AI web để viết kịch bản')
        return
    if not analysis:
        log_fn('   [LỖI] Không có dữ liệu phân tích phim')
        return
    analysis = dict(analysis)
    analysis['_user_context'] = ((user_context or '')).strip()
    _prepare_review_analysis(analysis, transcript, api_key, log_fn)
    from .scene_detector import detect_scene_cuts
    from .story_analyzer import build_scene_plan, analyze_scenes_with_vision
    real_cuts = detect_scene_cuts(video_path, log_fn=log_fn)
    scenes_meta = build_scene_plan(analysis.get('plot_beats', []), real_cuts, video_duration, target_minutes, log_fn=log_fn)
    if not scenes_meta:
        log_fn('   [LỖI] Không dựng được chương cảnh nào từ video')
        return {'scenes': [], 'num_cut_points': len(real_cuts or []), 'num_scene_chapters': 0}
    log_fn(f'''   Đã xây dựng {len(scenes_meta)} chương cảnh (khớp cảnh) từ video''')
    scenes_meta = _enrich_scenes_with_transcript(scenes_meta, transcript)
    # B10: video chỉ chiếu từ đầu chương, dài đúng bằng lời đọc (~số từ / tốc độ đọc) — không phải cả chương. Cho Vision xem
    # đúng phần hình SẼ CHIẾU để lời kể nói đúng chuyện đang hiện trên hình (trước rải khắp chương → kể chuyện ở giây
    # 8–17 của chương nhưng hình đó không bao giờ được chiếu)
    try:
        for (s, w) in zip(scenes_meta, _per_scene_word_targets(scenes_meta, int(TTS_WPM * target_minutes))):
            s['_shown_span'] = round(min(s['clip_end'] - s['clip_start'], max(4.0, w / _SCRIPT_WPS * 1.15)), 2)
    except Exception as e:
        log_fn(f'   [WARN] Không ước được phần hình mỗi chương ({e}) — Vision xem cả chương')
    _map_tmp_dir = temp_dir or __import__('tempfile').gettempdir()
    outline = analyze_scenes_with_vision(scenes_meta, video_path, openai_key, _map_tmp_dir, log_fn=log_fn, quality=quality, film_context=analysis.get('_user_context', ''), char_glossary=analysis.get('_char_glossary'))
    if outline:
        analysis['_deep_outline'] = outline
        log_fn(f'''   [Map-Reduce] Đã cập nhật mô tả chính xác từng chương (~{len(outline.split())} từ) — giữ nguyên tóm tắt mạch lạc của phân tích tổng.''')
    else:
        log_fn('   [WARN] Map-Reduce Vision AI không thành công ở chương nào -> giữ tóm tắt cũ.')
    result = _finish_review_script(scenes_meta, analysis, transcript, target_minutes, engines, script_mode, troll_tone, quality, log_fn)
    if isinstance(result, dict):
        result['num_cut_points'] = len(real_cuts or [])
        result['num_scene_chapters'] = len(scenes_meta)
    return result