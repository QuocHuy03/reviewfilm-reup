
"""
Script writer: viet script review tieng Viet bang DeepSeek API.
Approach SCENE-FIRST: su dung Gemini plot_beats timestamps truc tiep lam clip_start/clip_end,
sau do viet thuyet minh KHOP voi tung canh -> giai quyet van de hinh/giong khong sync.
"""
import os
import time
import json
import re
import requests
try:
    import google.generativeai as genai
except Exception:
    genai = None
DEEPSEEK_URL = 'https://api.deepseek.com/v1/chat/completions'
OPENAI_URL = 'https://api.openai.com/v1/chat/completions'
TTS_WPM = 230
MAX_SCENES = 90
MIN_SCENE_SECONDS = 10.0
HARD_MAX_SCENES_V2 = 240
def _llm_text_deepseek(prompt, api_key, log_fn, max_tokens, temperature=0.7, model='deepseek-chat'):
    _cap = 65536 if model == 'deepseek-reasoner' else 8192
    payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': max(1, min(int(max_tokens), _cap))}
    if model != 'deepseek-reasoner':
        payload['temperature'] = temperature
    for attempt in range(3):
        try:
            r = requests.post(DEEPSEEK_URL, headers={'Authorization': f'''Bearer {api_key}''', 'Content-Type': 'application/json'}, json=payload, timeout=240)
            if r.status_code == 200:
                return r.json()['choices'][0]['message']['content'].strip()
            log_fn(f'''   [WARN] DeepSeek HTTP {r.status_code} (attempt {attempt + 1}/3): {r.text[slice(None, 200, None)]}''')
        except Exception as e:
            log_fn(f'''   [WARN] DeepSeek exception (attempt {attempt + 1}/3): {str(e)[slice(None, 150, None)]}''')
        time.sleep(3)
    return ''
def _llm_text_openai(prompt, api_key, log_fn, max_tokens, temperature=0.7):
    for attempt in range(2):
        try:
            r = requests.post(OPENAI_URL, headers={'Authorization': f'''Bearer {api_key}''', 'Content-Type': 'application/json'}, json={'model': 'gpt-4o-mini', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': temperature, 'max_tokens': min(max_tokens, 16000)}, timeout=240)
            if r.status_code == 200:
                return r.json()['choices'][0]['message']['content'].strip()
            log_fn(f'''   [WARN] OpenAI HTTP {r.status_code} (attempt {attempt + 1}/2): {r.text[slice(None, 200, None)]}''')
        except Exception as e:
            log_fn(f'''   [WARN] OpenAI exception (attempt {attempt + 1}/2): {str(e)[slice(None, 150, None)]}''')
        time.sleep(2)
    return ''
def _llm_text_gemini(prompt, api_key, log_fn, max_tokens, temperature=0.7):
    if not api_key or genai is None:
        return ''
    keys = [k.strip() for k in str(api_key).split(',') if k.strip()]
    for key in keys:
        key_short = f'''...{key[slice(-6, None, None)]}''' if len(key) > 6 else key
        try:
            genai.configure(api_key=key)
        except Exception as ex:
            log_fn(f'''   [WARN] Gemini configure loi ({key_short}): {str(ex)[slice(None, 60, None)]}''')
            continue
        for m_name in ('gemini-2.5-flash', 'gemini-1.5-flash'):
            try:
                model = genai.GenerativeModel(m_name)
                resp = model.generate_content(prompt, generation_config={'temperature': temperature, 'max_output_tokens': min(max_tokens, 65536)})
                txt = ((getattr(resp, 'text', '') or '')).strip()
                if txt:
                    return txt
            except Exception as ex:
                err_str = str(ex)
                if any((s in err_str for s in ('429', 'RESOURCE_EXHAUSTED', 'quota', 'exhausted'))):
                    log_fn(f'''   [WARN] Gemini {m_name} ({key_short}) het quota, thu model/key khac...''')
                    continue
                if any((s in err_str for s in ('API_KEY_INVALID', 'PERMISSION_DENIED', '401', '403'))):
                    log_fn(f'''   [WARN] Gemini key {key_short} loi auth, thu key tiep theo...''')
                    break
                log_fn(f'''   [WARN] Gemini {m_name} ({key_short}) loi: {err_str[slice(None, 80, None)]}''')
    return ''
def _llm_text_call(engine, key, prompt, log_fn, max_tokens, temperature=0.7, quality='standard'):
    if engine == 'web':
        from core import web_llm
        return web_llm.chat(prompt, log_fn)
    if engine == 'openai':
        return _llm_text_openai(prompt, key, log_fn, max_tokens, temperature)
    if engine == 'gemini':
        return _llm_text_gemini(prompt, key, log_fn, max_tokens, temperature)
    ds_model = 'deepseek-reasoner' if quality == 'deep' else 'deepseek-chat'
    return _llm_text_deepseek(prompt, key, log_fn, max_tokens, temperature, model=ds_model)
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
        log_fn('   [LOI] Chua co API key (DeepSeek/OpenAI/Gemini) hoac tai khoan AI web de viet kich ban')
        return
    if not analysis:
        log_fn('   [LOI] Khong co du lieu phan tich phim')
        return
    analysis = dict(analysis)
    user_context = ((user_context or '')).strip()
    analysis['_user_context'] = user_context
    try:
        from .translator import _find_known_titles as _fkt, _get_char_glossary_for_film as _gcgf, _fetch_characters_from_ai as _fcai
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
            else:
                _ai_chars = _fcai(vi_t, src_t, deepseek_key=api_key, openai_key=os.environ.get('OPENAI_API_KEY', ''), log_fn=log_fn)
                if _ai_chars:
                    analysis['_char_glossary'] = _ai_chars
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
            log_fn(f'''   → Nap {len(_persist)} ten/vai tro da chot tu tap truoc (review)''')
    except Exception:
        pass
    scenes_meta = _build_scenes_from_beats(analysis.get('plot_beats', []), video_duration, target_minutes)
    log_fn(f'''   Da xay dung {len(scenes_meta)} canh tu Gemini timestamps''')
    log_fn(f'''[TRACE-③] V1 _build_scenes_from_beats: {len(analysis.get('plot_beats', []) or [])} beats -> {len(scenes_meta)} canh (tran MAX_SCENES={MAX_SCENES})''')
    scenes_meta = _enrich_scenes_with_transcript(scenes_meta, transcript)
    log_fn('   Da gan thoai Whisper vao cac canh (tang do chinh xac hinh-giong)')
    words_per_scene = max(12, int(TTS_WPM * target_minutes / max(1, len(scenes_meta))))
    total_words = words_per_scene * len(scenes_meta)
    log_fn(f'''   Moi canh can ~{words_per_scene} tu -> tong ~{total_words} tu (~{target_minutes} phut)''')
    if words_per_scene < 15:
        log_fn(f'''   [WARN][BL-P1-05] Muc tu moi canh rat thap ({words_per_scene} < 15) - phim dai/nhieu canh so voi {target_minutes} phut da chon, loi doc co the cut lun. Can nhac tang so phut review.''')
    log_fn(f'''   Gui yeu cau viet kich ban lien mach toi {engines[0][0]}...''')
    narrations = _write_unified_marked_script(scenes_meta, analysis, words_per_scene, total_words, engines, log_fn, script_mode=script_mode, troll_tone=troll_tone, quality=quality)
    if not narrations:
        log_fn('   [WARN] Kich ban marked that bai, thu fallback plain text...')
        narrations = _fallback_plain_text(scenes_meta, analysis, words_per_scene, engines, log_fn, quality=quality)
    if not narrations:
        log_fn('   [WARN] Ca hai phuong phap deu that bai, dung mo ta canh lam kich ban tam thoi...')
        narrations = [s['description'] for s in scenes_meta]
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
            s['voiceover'] = _r2w(s['voiceover'])
            s['subtitle'] = s['voiceover']
    if digits_found:
        log_fn(f'''   [Safety] Da chuyen so thanh chu o {digits_found} canh (TTS safety pass)''')
    _enforce_total_word_budget(final_scenes, target_minutes, words_per_scene, log_fn)
    est_min = sum((len(s['voiceover'].split()) for s in final_scenes)) / TTS_WPM
    log_fn(f'''   Script hoan chinh: {len(final_scenes)} canh, ~{est_min:.1f} phut TTS''')
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
    try:
        return float(val)
    except (TypeError, ValueError):
        return default
def _build_scenes_from_beats(plot_beats, video_duration, target_minutes):
    video_duration = _safe_float(video_duration, 0.0)
    if video_duration <= 0:
        raise ValueError(f'''video_duration khong hop le ({video_duration}) — khong the tao scenes.''')
    min_scenes = int(min(MAX_SCENES, max(4, min(max(6, target_minutes * 5), int(video_duration / MIN_SCENE_SECONDS)))))
    if not plot_beats or len(plot_beats) < 4:
        n_fb = min_scenes
        step_fb = video_duration / n_fb
        plot_beats = [{'timestamp': i * step_fb, 'description': f'''Phan {i + 1} trong {n_fb}'''} for i in range(n_fb)]
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
            beats.append({'timestamp': ts, 'description': nearest_desc or f'''Tiep dien canh {ts:.0f}s'''})
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
        scenes.append({'clip_start': clip_start, 'clip_end': clip_end, 'description': beat.get('description', f'''Canh {i + 1}''')})
    return scenes
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
    log_fn(f'''   [BL-P1-05] Tong {total} tu vuot ngan sach {global_budget} ({target_minutes} phut x {TTS_WPM} wpm x 1.2) -> cat canh dai nhat truoc.''')
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
        log_fn(f'''   [WARN][BL-P1-05] Da cat cac canh dai nhat ve san {floor} tu/canh nhung tong van {total} tu (~{total / TTS_WPM:.1f} phut) > ngan sach {global_budget} — video se dai hon muc tieu {target_minutes} phut.''')
    else:
        log_fn(f'''   [BL-P1-05] Sau cat: {total} tu (~{total / TTS_WPM:.1f} phut) <= ngan sach {global_budget}.''')
def _write_unified_marked_script(scenes_meta, analysis, words_per_scene, total_words, engines, log_fn=print, script_mode='review_phim', troll_tone=True, quality='standard'):
    style_directive = SCRIPT_MODE_PRESETS.get(script_mode, SCRIPT_MODE_PRESETS['review_phim'])
    band_high = int(words_per_scene * 1.15)
    scenes_text_list = []
    for (idx, s) in enumerate(scenes_meta):
        dur = max(2.0, s['clip_end'] - s['clip_start'])
        s['_word_limit'] = min(band_high, max(words_per_scene, int(dur * 3.2)))
        dial = s.get('_transcript', '')
        if dial:
            scenes_text_list.append(f'''Cảnh {idx + 1}: {s['description']} [Thoại gốc: {dial}]''')
        else:
            scenes_text_list.append(f'''Cảnh {idx + 1}: {s['description']}''')
    scenes_text = '\n'.join(scenes_text_list)
    tone_str = '''Bổ sung: Giọng văn kể chuyện phải hơi troll, vui vẻ, hóm hỉnh và pha chút châm biếm hài hước để người xem thích thú bật cười.

''' if troll_tone else 'Bổ sung: Giọng văn kể chuyện nghiêm túc, kịch tính, lôi cuốn và bám sát vào cảm xúc thực tế, bối cảnh phim.\n\n'
    _uc = ((analysis.get('_user_context') or '')).strip()
    _uc_block = f'''*** BỐI CẢNH NGƯỜI DÙNG CUNG CẤP — ƯU TIÊN TUYỆT ĐỐI, TIN TƯỞNG HOÀN TOÀN ***\n{_uc}\n→ Dùng đúng tên phim, tên/vai trò nhân vật và xuất xứ như người dùng mô tả.\n\n''' if _uc else ''
    prompt = f'''Bạn là nhà biên kịch và bình luận phim chuyên nghiệp cho các kênh YouTube Movie Recap hàng đầu Việt Nam.\nMục tiêu là kể lại ĐÚNG những gì đang diễn ra trong cảnh, theo sát cốt truyện thực tế — dễ hiểu, mạch lạc, KHÔNG văn vẻ/thơ ca/triết lý vẽ vời, KHÔNG tự bịa thêm cảm xúc hay chi tiết không có trong cảnh.\n\n{_uc_block}PHONG CÁCH DIỄN ĐẠT CHỦ ĐẠO:\n{style_directive}\n{tone_str}QUY TẮC TÊN RIÊNG & BIỆT DANH (CỰC KỲ QUAN TRỌNG — TUYỆT ĐỐI KHÔNG DÙNG HÁN-VIỆT):\n1. TÊN PHIM: dịch nghĩa sang tiếng Việt tự nhiên hoặc giữ tên tiếng Anh/gốc. TUYỆT ĐỐI KHÔNG dùng tên phiên âm Hán-Việt (ví dụ KHÔNG \'Quỷ Xuy Đăng\', KHÔNG \'Khánh Dư Niên\' — hãy dùng \'Ma Thổi Đèn\', \'Niềm Vui Cuộc Sống\').\n2. TÊN NHÂN VẬT: {_origin_name_rule(analysis.get('origin', ''))} TUYỆT ĐỐI KHÔNG phiên âm Hán-Việt tên người (KHÔNG \'Tiểu Phi\', \'Trương Tam\'...).\n   ĐẶC BIỆT - PHIM LỒNG TIẾNG TRUNG: nếu nhân vật có tên dạng \'Xiao X\' (Xiao Min, Xiao Piao, Xiao Ba...) — đây là tên Trung của phim Hàn/Nhật/Thái lồng tiếng. Nếu BIẾT tên thật thì dùng tên romanized (Hàn/Nhật/Thái). Nếu KHÔNG biết tên thật: KHÔNG giữ pinyin \'Xiao X\' và KHÔNG Hán-Việt hóa, mà GÁN MỘT VAI TRÒ/BIỆT DANH THUẦN VIỆT cố định theo vai trò nhân vật (ví dụ \'cậu học trò quậy\', \'cô bé lớp trưởng\', \'gã đầu gấu\', \'ông trùm\') và DÙNG NHẤT QUÁN suốt cả phim.\n''' + (('   BẢNG TÊN/VAI TRÒ CHÍNH XÁC (BẮT BUỘC DÙNG ĐÚNG, NHẤT QUÁN):\n' + ''.join((f'''   - \'{e['src']}\' → \'{e['vi']}\'\n''' for e in analysis['_char_glossary'][slice(None, 8, None)]))) if analysis.get('_char_glossary') else '') + f'''3.Có thể tự tạo biệt danh hài hước, dí dỏm cho nhân vật phụ dựa vào ngoại hình hoặc hành động (ví dụ: \'anh mắt lác\', \'chị đại tóc đỏ\', \'gã đầu hói\'...) — nhưng phải dùng NHẤT QUÁN một biệt danh cho một nhân vật. Nếu không có đặc điểm nổi bật thì thôi.\n\nTHÔNG TIN CHUNG VỀ BỘ PHIM:\n- Tên phim (DÙNG CHÍNH XÁC TÊN NÀY): {analysis.get('_vi_title') or '?'}''' + (f''' (tên gốc: {analysis['_vi_title_src']})''' if analysis.get('_vi_title_src') else '') + f'''\n- Xuất xứ: {analysis.get('origin', 'chưa rõ')}\n- Thể loại: {analysis.get('genre', '?')}\n- Nhân vật chính: {', '.join((str(c) for c in analysis.get('main_characters', [])[slice(None, 4, None)]))}\n- Bối cảnh: {analysis.get('setting', '')}\n- Tóm tắt cốt truyện hoàn chỉnh: {analysis.get('summary', '')}\n\nDANH SÁCH {len(scenes_meta)} CẢNH PHIM THEO TRÌNH TỰ THỜI GIAN:\n{scenes_text}\n\nNHIỆM VỤ:\nHãy viết một kịch bản thuyết minh kể chuyện phim (Movie Recap) hoàn chỉnh, liền mạch, thống nhất từ đầu đến cuối dài khoảng {total_words} từ.\nBắt buộc chia kịch bản thành đúng {len(scenes_meta)} phần tương ứng với {len(scenes_meta)} cảnh ở trên.\nĐầu mỗi phần phải bắt đầu bằng nhãn [Cảnh N] (ví dụ: [Cảnh 1], [Cảnh 2]...).\n\nYÊU CẦU CHẤT LƯỢNG KỊCH BẢN (TIÊU CHUẨN 9-10/10 ĐIỂM):\n1. BÁM SÁT HÌNH ẢNH VÀ NỘI DUNG PHIM (QUAN TRỌNG NHẤT): Mỗi [Cảnh N] PHẢI kể đúng nội dung/hình ảnh của Cảnh N trong danh sách trên — vì lời đọc sẽ phát ĐÈ LÊN đúng đoạn video đó. Người xem nhìn thấy gì trên màn hình thì lời đọc phải nói về thứ đó. TUYỆT ĐỐI KHÔNG bịa ra sự kiện, cốt truyện sai lệch hoàn toàn với phim gốc, không phóng tác lung tung làm lệch nội dung chính của phim. Phải bám sát mô tả cảnh và phụ đề thoại gốc đi kèm.\n   ƯU TIÊN ĐỘ CHÍNH XÁC HƠN CHẤT VĂN: kể thẳng, đúng việc đang xảy ra. KHÔNG thêm câu cảm thán/suy ngẫm/đánh giá hoa mỹ không bắt nguồn từ chính cảnh đó (TRÁNH kiểu: \'một chiến thắng nhỏ nhưng vô cùng quan trọng\', \'công lý dường như quá xa xỉ\' — đây là bình luận tự bịa, không phải mô tả cảnh).\n2. VĂN PHONG TỰ NHIÊN, KHÔNG SÁO RỖNG: Viết như người Việt kể chuyện đời thường, rõ ràng dễ hiểu. TUYỆT ĐỐI TRÁNH văn vẻ rườm rà, ẩn dụ triết lý lê thê (TRÁNH kiểu: \'bóng tối không chỉ là sự vắng mặt của ánh sáng, mà còn là nơi ẩn náu của những bí mật chết người\'). Câu chữ gọn gàng, đi thẳng vào sự việc đang diễn ra.\n3. NHẤT QUÁN TÊN/CÁCH GỌI NHÂN VẬT: Một nhân vật chỉ gọi bằng MỘT tên/vai trò cố định xuyên suốt. KHÔNG được khi gọi \'người mẹ\' lúc lại gọi \'cô gái trẻ\' cho cùng một người. Nếu không rõ tên thì gọi theo vai trò cố định (người mẹ, đứa con, ông chủ...) và giữ nguyên đến hết.\n4. TUYỆT ĐỐI KHÔNG chép nguyên câu thoại nhân vật vào lời thuyết minh (TRÁNH: \'Anh nói: Mày là cái gì?\'). Thay vào đó, diễn giải sự kiện theo góc nhìn narrator (NÊN: \'Người đàn ông lạ mặt bất ngờ xuất hiện, khiến cả đám không kịp phản ứng\').\n5. HOOK Ở CẢNH 1: Cảnh đầu mở màn bằng một câu dẫn cuốn hút, tóm gọn mâu thuẫn chính của phim — nhưng vẫn phải đúng với hình ảnh đang chiếu ở cảnh đầu. NGOẠI LỆ: nếu mô tả cảnh đầu chỉ là logo hãng phim/màn hình thông tin sản xuất/màn đen (có ghi \'(logo/intro sản xuất)\') thì TUYỆT ĐỐI KHÔNG thuyết minh về màn hình đó — hãy viết thẳng câu hook giới thiệu mâu thuẫn chính của phim.\n6. LIÊN KẾT MƯỢT MÀ NHƯNG TIẾT CHẾ: Lời cảnh N và N+1 nối logic tự nhiên, ưu tiên nối bằng chính nội dung sự kiện (vd: nhắc lại hệ quả của cảnh trước). CHỈ dùng cụm mở kiểu \'Không ngờ rằng...\', \'Đúng lúc này...\', \'Hóa ra...\' khi thực sự hợp lý, KHÔNG dùng liên tục ở nhiều cảnh kế tiếp (tối đa 1/3 số cảnh) vì sẽ gây sáo rỗng, lặp khuôn.\n7. SỐ LƯỢNG TỪ MỖI CẢNH — BẮT BUỘC TUÂN THỦ CHẶT: Mỗi cảnh PHẢI viết trong khoảng {words_per_scene} đến {band_high} từ (không ít hơn {words_per_scene}, không nhiều hơn {band_high}). Đây là giới hạn CỨNG — viết quá số từ này sẽ làm TỔNG thời lượng video vượt xa thời lượng khách yêu cầu ({total_words} từ cho toàn bộ {len(scenes_meta)} cảnh). Ưu tiên câu ngắn gọn, đúng trọng tâm, đi thẳng vào sự việc thay vì mô tả chi tiết dài dòng để giữ đúng giới hạn này.\n8. ĐẢM BẢO kết thúc kịch bản (cảnh cuối) có lời chốt ấn tượng, giữ khoảnh lặng cảm xúc hoặc câu hỏi suy ngẫm, kèm 1 câu kêu gọi đăng ký kênh tự nhiên.\n9. TUYỆT ĐỐI KHÔNG DÙNG CHỮ SỐ (0-9): Kịch bản sẽ được đọc bằng phần mềm giọng nói (TTS) — nếu có chữ số, giọng đọc sẽ bị lỗi. Thay mọi chữ số bằng chữ tiếng Việt. Ví dụ: thay \'2026\' → \'hai nghìn không trăm hai mươi sáu\', \'3 người\' → \'ba người\', \'100 năm\' → \'một trăm năm\', \'tập 12\' → \'tập mười hai\', \'thế kỷ 19\' → \'thế kỷ mười chín\'. Đây là yêu cầu bắt buộc, không có ngoại lệ.\n10. GIỮ ĐÚNG TRÌNH TỰ NHÂN-QUẢ, KHÔNG ĐẢO/GỘP CẢNH XA NHAU: Cảnh N chỉ được nhắc lại/liên hệ với cảnh N-1 (cảnh LIỀN TRƯỚC nó) — TUYỆT ĐỐI KHÔNG suy đoán, gộp hay đảo trình tự sự kiện của các cảnh xa hơn (N-2, N-3...) vào cảnh N, kể cả khi cố tạo liên kết mượt mà. Nếu không chắc điều gì xảy ra trước/sau, chỉ kể đúng nội dung của cảnh N như mô tả, không suy diễn quan hệ nhân-quả với cảnh xa.\n\nChỉ trả về phần kịch bản thuyết minh bắt đầu từ [Cảnh 1], không thêm lời giới thiệu hay đính kèm nào khác.'''
    max_tokens = min(64000, len(scenes_meta) * 150 + 1000)
    content = ''
    for (idx, (eng, key)) in enumerate(engines):
        content = _llm_text_call(eng, key, prompt, log_fn, max_tokens, temperature=0.7, quality=quality)
        if content:
            break
        next_engines = [e for (e, _) in engines[slice(idx + 1, None, None)]]
        if next_engines:
            log_fn(f'''   [FALLBACK] \'{eng}\' loi/rong -> chuyen sang \'{next_engines[0]}\'...''')
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
    log_fn(f'''   Parser: Da phan tich {len(non_empty)}/{num_scenes} canh co loi thuyet minh''')
    if _dup_labels:
        log_fn(f'''   [WARN] AI ghi trung nhan [Cảnh N] cho {len(set(_dup_labels))} cảnh ({sorted(set(_dup_labels))[slice(None, 10, None)]}{'...' if len(set(_dup_labels)) > 10 else ''}) — đã giữ bản dài nhất (bỏ dòng tiêu đề/mục lục trùng nhãn).''')
    if len(non_empty) < num_scenes * 0.7:
        log_fn('   [WARN] So canh khop duoc qua it, tien hanh chia deu van ban tu dong...')
        clean_content = pattern.sub('', content)
        clean_content = '\n'.join((line.strip() for line in clean_content.split('\n') if line.strip()))
        return _split_text_to_n(clean_content, num_scenes)
    n_own_desc = 0
    n_dropped = 0
    for i in range(num_scenes):
        if final_narrations[i]:
            continue
        own_desc = ''
        if scenes_meta:
            if i < len(scenes_meta):
                own_desc = ((scenes_meta[i].get('description') or '')).strip()
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
    beats_text = '\n'.join((f'''- Canh {i + 1}: {s['description']}''' for (i, s) in enumerate(scenes_meta)))
    _vi_title = analysis.get('_vi_title') or '?'
    _src_title = analysis.get('_vi_title_src', '')
    title_line = f'''Tên phim (DÙNG ĐÚNG TÊN NÀY): {_vi_title}''' + (f''' ({_src_title})''' if _src_title else '')
    prompt = f'''Bạn là biên kịch viết kịch bản review phim (Movie Recap) cho kênh YouTube Việt Nam.\n{title_line}\nThể loại: {analysis.get('genre', '?')}. Tóm tắt cốt truyện: {analysis.get('summary', '')}\nCác mốc sự kiện chính:\n{beats_text}\n\nNHIỆM VỤ: Viết một bài thuyết minh kể chuyện phim bằng tiếng Việt dài khoảng {total_words} từ, liền mạch, dễ hiểu, giải thích rõ động cơ nhân vật và các tình tiết cốt truyện từ đầu đến cuối phim. Tránh miêu tả hình ảnh thô sơ.\nQUY TẮC TÊN PHIM: dùng tên tiếng Việt phổ biến (ví dụ \'Ma Thổi Đèn\', \'Chân Hoàn Truyện\').\nQUY TẮC TÊN NHÂN VẬT: {_origin_name_rule(analysis.get('origin', ''))}\nQUAN TRỌNG: TUYỆT ĐỐI KHÔNG dùng chữ số (0-9). Viết tất cả số bằng chữ tiếng Việt (ví dụ: \'ba người\', \'hai nghìn hai mươi sáu\', \'một trăm năm\').\nChỉ trả về văn bản thuần của bài thuyết minh, không chứa định dạng markdown, không chứa JSON.'''
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
    return _split_text_to_n(text, len(scenes_meta))
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
def _escape_inner_quotes(json_str):
    pattern = '((?:"text"|"voiceover"|"polished")\\s*:\\s*")([\\s\\S]*?)("\\s*(?:,\\s*"(?:id|scene_number)"\\s*:\\s*\\d+|\\s*\\}|\\,\\s*\\}))'
    def replace_fn(match):
        prefix = match.group(1)
        content = match.group(2)
        suffix = match.group(3)
        escaped_content = []
        escape = False
        for c in content:
            if c == '\\' and not escape:
                escaped_content.append(c)
                escape = True
                continue
            if c == '"' and not escape:
                escaped_content.append('\\"')
            else:
                escaped_content.append(c)
            escape = False
        return prefix + ''.join(escaped_content) + suffix
    return re.sub(pattern, replace_fn, json_str)
def _prepare_review_analysis(analysis, transcript, api_key, log_fn=print):
    try:
        from .translator import _find_known_titles as _fkt, _get_char_glossary_for_film as _gcgf, _fetch_characters_from_ai as _fcai
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
            else:
                _ai_chars = _fcai(vi_t, src_t, deepseek_key=api_key, openai_key=os.environ.get('OPENAI_API_KEY', ''), log_fn=log_fn)
                if _ai_chars:
                    analysis['_char_glossary'] = _ai_chars
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
            log_fn(f'''   → Nap {len(_persist)} ten/vai tro da chot tu tap truoc (review)''')
    except Exception:
        pass
def _finish_review_script(scenes_meta, analysis, transcript, target_minutes, engines, script_mode, troll_tone, quality, log_fn=print):
    scenes_meta = _enrich_scenes_with_transcript(scenes_meta, transcript)
    log_fn('   Da gan thoai Whisper vao cac canh (tang do chinh xac hinh-giong)')
    words_per_scene = max(12, int(TTS_WPM * target_minutes / max(1, len(scenes_meta))))
    total_words = words_per_scene * len(scenes_meta)
    log_fn(f'''   Moi canh can ~{words_per_scene} tu -> tong ~{total_words} tu (~{target_minutes} phut)''')
    if words_per_scene < 15:
        log_fn(f'''   [WARN][BL-P1-05] Muc tu moi canh rat thap ({words_per_scene} < 15) - phim dai/nhieu canh so voi {target_minutes} phut da chon, loi doc co the cut lun. Can nhac tang so phut review.''')
    log_fn(f'''   Gui yeu cau viet kich ban lien mach toi {engines[0][0]}...''')
    narrations = _write_unified_marked_script(scenes_meta, analysis, words_per_scene, total_words, engines, log_fn, script_mode=script_mode, troll_tone=troll_tone, quality=quality)
    if not narrations:
        log_fn('   [WARN] Kich ban marked that bai, thu fallback plain text...')
        narrations = _fallback_plain_text(scenes_meta, analysis, words_per_scene, engines, log_fn, quality=quality)
    if not narrations:
        log_fn('   [WARN] Ca hai phuong phap deu that bai, dung mo ta canh lam kich ban tam thoi...')
        narrations = [s['description'] for s in scenes_meta]
    final_scenes = []
    for (i, meta) in enumerate(scenes_meta):
        text = narrations[i].strip() if i < len(narrations) else ''
        if not text:
            continue
        limit = meta.get('_word_limit', 0)
        safety_limit = int(limit * 1.05) if limit > 0 else 150
        text = _trim_to_word_limit(text, safety_limit)
        final_scenes.append({'voiceover': text, 'clip_start': meta['clip_start'], 'clip_end': meta['clip_end'], 'subtitle': text})
    import re as _re
    from .tts_engine import replace_numbers_with_words as _r2w
    digits_found = 0
    for s in final_scenes:
        if _re.search('\\d', s['voiceover']):
            digits_found += 1
            s['voiceover'] = _r2w(s['voiceover'])
            s['subtitle'] = s['voiceover']
    if digits_found:
        log_fn(f'''   [Safety] Da chuyen so thanh chu o {digits_found} canh (TTS safety pass)''')
    _enforce_total_word_budget(final_scenes, target_minutes, words_per_scene, log_fn)
    est_min = sum((len(s['voiceover'].split()) for s in final_scenes)) / TTS_WPM
    log_fn(f'''   Script hoan chinh: {len(final_scenes)} canh, ~{est_min:.1f} phut TTS''')
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
        log_fn('   [LOI] Chua co API key (DeepSeek/OpenAI/Gemini) hoac tai khoan AI web de viet kich ban')
        return
    if not analysis:
        log_fn('   [LOI] Khong co du lieu phan tich phim')
        return
    analysis = dict(analysis)
    analysis['_user_context'] = ((user_context or '')).strip()
    _prepare_review_analysis(analysis, transcript, api_key, log_fn)
    from .scene_detector import detect_scene_cuts
    from .story_analyzer import build_scene_plan, analyze_scenes_with_vision
    real_cuts = detect_scene_cuts(video_path, log_fn=log_fn)
    scenes_meta = build_scene_plan(analysis.get('plot_beats', []), real_cuts, video_duration, target_minutes, log_fn=log_fn)
    if not scenes_meta:
        log_fn('   [LOI] Khong dung duoc chuong canh nao tu video')
        return {'scenes': [], 'num_cut_points': len(real_cuts or []), 'num_scene_chapters': 0}
    log_fn(f'''   Da xay dung {len(scenes_meta)} chuong canh (scene-accurate) tu video''')
    log_fn(f'''[TRACE-③] V2 build_scene_plan: {len(real_cuts or [])} diem cat that -> {len(scenes_meta)} chuong canh (tran HARD_MAX_SCENES_V2)''')
    scenes_meta = _enrich_scenes_with_transcript(scenes_meta, transcript)
    _map_tmp_dir = temp_dir or __import__('tempfile').gettempdir()
    outline = analyze_scenes_with_vision(scenes_meta, video_path, openai_key, _map_tmp_dir, log_fn=log_fn, quality=quality, film_context=analysis.get('_user_context', ''), char_glossary=analysis.get('_char_glossary'))
    if outline:
        analysis['_deep_outline'] = outline
        log_fn(f'''   [Map-Reduce] Da cap nhat mo ta chinh xac tung chuong (~{len(outline.split())} tu) — giu nguyen tom tat mach lac cua phan tich tong.''')
    else:
        log_fn('   [WARN] Map-Reduce Vision AI khong thanh cong o chuong nao -> giu summary cu.')
    result = _finish_review_script(scenes_meta, analysis, transcript, target_minutes, engines, script_mode, troll_tone, quality, log_fn)
    if isinstance(result, dict):
        result['num_cut_points'] = len(real_cuts or [])
        result['num_scene_chapters'] = len(scenes_meta)
    return result