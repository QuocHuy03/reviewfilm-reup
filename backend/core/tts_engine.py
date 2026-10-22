

"""
Tạo giọng đọc từng cảnh: Edge TTS (miễn phí, song song), CapCut (gom gói, song song), FPT.AI (tuần tự, tránh giới hạn tần suất),
VieNeu / VieNeu3 (chạy cục bộ). Lỗi thì tự đọc lại bằng Edge, cuối cùng là Google TTS.
"""
import os
os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
import asyncio
import subprocess
import threading
import time
import re
import requests
from .utils import FFPROBE_EXE, FFMPEG_EXE, _HIDE, register_process, unregister_process
_LOCAL_GPU_LOCK = threading.Lock()
FPTAI_VOICES = {'banmai': 'Nu, mien Bac', 'lannhi': 'Nu, mien Nam', 'leminh': 'Nam, mien Bac', 'myan': 'Nu, mien Trung', 'thuminh': 'Nu, mien Bac', 'giahuy': 'Nam, mien Trung', 'linhsan': 'Nu, mien Nam', 'ngoclam': 'Nu, mien Trung', 'minhquang': 'Nam, mien Nam', 'banmaiace': 'Nu, mien Bac (Ace)', 'thuminhace': 'Nu, mien Bac (Ace)', 'ngoclamace': 'Nu, mien Trung (Ace)', 'linhsanace': 'Nu, mien Nam (Ace)', 'minhquangace': 'Nam, mien Nam (Ace)'}
FPTAI_ENHANCE_VOICES = {'lannhi'}
_FPTAI_ENHANCE_AF = 'highpass=f=75,equalizer=f=300:t=q:w=1.2:g=-1.5,equalizer=f=2500:t=q:w=1.0:g=2,treble=g=5:f=4000,acompressor=threshold=-18dB:ratio=2.5:attack=8:release=120:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=9,atempo=1.08'
EDGE_VOICES = {'vi-VN-HoaiMyNeural': 'Nu - Edge TTS mien phi', 'vi-VN-NamMinhNeural': 'Nam - Edge TTS mien phi'}
_FEMALE_VOICE_HINTS = ('lena', 'banmai', 'mia', 'rachel', 'nova', 'shimmer', 'ngoc-lan', 'ngoclan', 'my-duyen', 'myduyen', 'truc-ly', 'trucly', 'ngoc-linh', 'ngoclinh', 'hoaimy', '21m00tcm4tlvdq8ikwam', 'mai-anh', 'thuy-dung', 'ngoc-huyen', 'ngoc-tran', 'doan-trang', 'thuc-doan', 'quynh-anh', 'kim-thanh')
def _get_fallback_edge_voice(voice):
    voice = ((voice or '')).lower()
    if any((h in voice for h in _FEMALE_VOICE_HINTS)):
        return 'vi-VN-HoaiMyNeural'
    return 'vi-VN-NamMinhNeural'
VIENEU_VOICES = {'binh-an': 'Nam - Bình An (VieNeu điềm đạm)', 'xuan-vinh': 'Xuân Vĩnh (Nam · miền Bắc · tự nhiên)', 'ngoc-lan': 'Nữ - Ngọc Lan (VieNeu dịu dàng)', 'my-duyen': 'Mỹ Duyên (Nữ · miền Nam · kể chuyện)', 'truc-ly': 'Trúc Ly (Nữ · miền Bắc · tự nhiên)', 'ngoc-linh': 'Ngọc Linh (Nữ · miền Bắc · kể chuyện)', 'gia-bao': 'Nam - Gia Bảo (VieNeu mượt mà)', 'thai-son': 'Thái Sơn (Nam · miền Nam · kể chuyện)', 'duc-tri': 'Đức Trí (Nam · miền Nam · kể chuyện)', 'trong-huu': 'Nam - Trọng Hữu (VieNeu uyên bác)', 'clone': 'Nhân bản giọng riêng (VieNeu - cần 3-5s audio mẫu)', 'vieneu3-chien-thang': 'VieNeu3 - Chiến Thắng', 'vieneu3-hung-ba': 'VieNeu3 - Hùng Bá', 'vieneu3-lam-le': 'VieNeu3 - Lâm Lê', 'vieneu3-ly-long-tieng': 'VieNeu3 - Lý Long Tiếng', 'vieneu3-phat-phap': 'VieNeu3 - Pháp Phật', 'vieneu3-review-toptop': 'VieNeu3 - Review Toptop', 'vieneu3-trinh-le': 'VieNeu3 - Trịnh Lê', 'vieneu3-trung-dung': 'VieNeu3 - Trung Dũng', 'vieneu3-yen-tin-tuc': 'VieNeu3 - Yến Tin Tức', 'vieneu3-ban-mai': 'VieNeu3 - Ban Mai', 'vieneu3-bac-quynh-anh': 'VieNeu3 - Quỳnh Anh (Giọng Bắc)', 'vieneu3-bac-thao-chi': 'VieNeu3 - Thảo Chi (Giọng Bắc)', 'vieneu3-bac-thanh-tung': 'VieNeu3 - Thanh Tùng (Giọng Bắc)', 'vieneu3-bac-nam-khanh': 'VieNeu3 - Nam Khánh (Giọng Bắc)', 'vieneu3-quang-cao': 'VieNeu3 - Quảng Cáo Nội Lực', 'vieneu3-he-thong': 'VieNeu3 - Hệ Thống', 'vieneu3-lena': 'VieNeu3 - Lena', 'vieneu3-mc-truyen-hinh': 'VieNeu3 - MC Truyền Hình', 'vieneu3-mia': 'VieNeu3 - Mia', 'vieneu3-minh-quang': 'VieNeu3 - Minh Quang', 'vieneu3-nam': 'VieNeu3 - Nam', 'vieneu3-nguyen': 'VieNeu3 - Nguyên', 'vieneu3-thu-minh': 'VieNeu3 - Thu Minh', 'vieneu3-nam-tram-am': 'VieNeu3 - Nam Trầm Ấm', 'vieneu3-nam-cham-rai': 'VieNeu3 - Nam Chậm Rãi', 'vieneu3-nam-nhanh-nhen': 'VieNeu3 - Nam Nhanh Nhẹn', 'vieneu3-nam-truyen-cam': 'VieNeu3 - Nam Truyền Cảm', 'vieneu3-nu-diem-dam': 'VieNeu3 - Nữ Điềm Đạm', 'vieneu3-nu-cham-rai': 'VieNeu3 - Nữ Chậm Rãi', 'vieneu3-nu-luu-loat': 'VieNeu3 - Nữ Lưu Loát', 'vieneu3-nu-nhan-nha': 'VieNeu3 - Nữ Nhàn Nhã', 'vieneu3-nu-nhe-nhang': 'VieNeu3 - Nữ Nhẹ Nhàng', 'adam-bua': 'Adam bựa (Nam · miền Bắc · tự nhiên)', 'thien-minh': 'Thiện Minh (Nam · miền Bắc · kể chuyện)', 'mai-anh': 'Mai Anh (Nữ · miền Bắc · tin tức)', 'hai-dang': 'Hải Đăng (Nam · miền Bắc · tự nhiên)', 'thuy-dung': 'Thùy Dung (Nữ · miền Nam · tin tức)', 'thien-tam-duc': 'Thiền Tâm Đức (Nam · miền Bắc · kể chuyện)', 'ngoc-huyen': 'Ngọc Huyền (Nữ · miền Bắc · tự nhiên)', 'quang-son': 'Quang Sơn (Nam · miền Trung · tự nhiên)', 'ngoc-tran': 'Ngọc Trân (Nữ · miền Trung · tự nhiên)', 'minh-duc': 'Minh Đức (Nam · miền Bắc · tin tức)', 'pham-tuyen': 'Phạm Tuyên (Nam · miền Bắc · tự nhiên)', 'thanh-binh': 'Thanh Bình (Nam · miền Bắc · kể chuyện)', 'doan-trang': 'Đoan Trang (Nữ · miền Bắc · tự nhiên)', 'thuc-doan': 'Thục Đoan (Nữ · miền Nam · kể chuyện)', 'minh-triet': 'Minh Triết (Nam · miền Nam · tin tức)', 'quynh-anh': 'Quỳnh Anh (Nữ · miền Bắc · kể chuyện)', 'kim-thanh': 'Kim Thanh (Nữ · miền Nam · kể chuyện)', 'adam': 'Adam (Nam · miền Nam · tự nhiên)', 'quoc-tuan': 'Quốc Tuấn (Nam · miền Bắc · tự nhiên)'}
_VIENEU3_BUILTIN_REF = {'vieneu3-chien-thang': 'chien-thang.wav', 'vieneu3-hung-ba': 'hung-ba.wav', 'vieneu3-lam-le': 'lam-le.wav', 'vieneu3-ly-long-tieng': 'ly-long-tieng.wav', 'vieneu3-phat-phap': 'phat-phap.wav', 'vieneu3-review-toptop': 'review-toptop.wav', 'vieneu3-trinh-le': 'trinh-le.wav', 'vieneu3-trung-dung': 'trung-dung.wav', 'vieneu3-yen-tin-tuc': 'yen-tin-tuc.wav', 'vieneu3-ban-mai': 'ban-mai.wav', 'vieneu3-bac-quynh-anh': 'bac-quynh-anh.wav', 'vieneu3-bac-thao-chi': 'bac-thao-chi.wav', 'vieneu3-bac-thanh-tung': 'bac-thanh-tung.wav', 'vieneu3-bac-nam-khanh': 'bac-nam-khanh.wav', 'vieneu3-quang-cao': 'quang-cao.wav', 'vieneu3-he-thong': 'he-thong.wav', 'vieneu3-lena': 'lena.wav', 'vieneu3-mc-truyen-hinh': 'mc-truyen-hinh.wav', 'vieneu3-mia': 'mia.wav', 'vieneu3-minh-quang': 'minh-quang.wav', 'vieneu3-nam': 'nam.wav', 'vieneu3-nguyen': 'nguyen.wav', 'vieneu3-thu-minh': 'thu-minh.wav', 'vieneu3-nam-tram-am': 'nam-tram-am.wav', 'vieneu3-nam-cham-rai': 'nam-cham-rai.wav', 'vieneu3-nam-nhanh-nhen': 'nam-nhanh-nhen.wav', 'vieneu3-nam-truyen-cam': 'nam-truyen-cam.wav', 'vieneu3-nu-diem-dam': 'nu-diem-dam.wav', 'vieneu3-nu-cham-rai': 'nu-cham-rai.wav', 'vieneu3-nu-luu-loat': 'nu-luu-loat.wav', 'vieneu3-nu-nhan-nha': 'nu-nhan-nha.wav', 'vieneu3-nu-nhe-nhang': 'nu-nhe-nhang.wav'}
def _vi_number_to_words(n):
    if n == 0:
        return 'không'
    if n < 0:
        return 'âm ' + _vi_number_to_words(-n)
    _ones = ['', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín']
    _tens = ['', '', 'hai mươi', 'ba mươi', 'bốn mươi', 'năm mươi', 'sáu mươi', 'bảy mươi', 'tám mươi', 'chín mươi']
    def _lt100(x):
        if x == 0:
            return ''
        if x < 10:
            return _ones[x]
        if x == 10:
            return 'mười'
        if x < 20:
            return 'mười ' + ('lăm' if x == 15 else _ones[x % 10])
        (t, u) = divmod(x, 10)
        if u == 0:
            return _tens[t]
        if u == 1:
            return _tens[t] + ' mốt'
        if u == 5:
            return _tens[t] + ' lăm'
        return _tens[t] + ' ' + _ones[u]
    def _lt1000(x):
        if x == 0:
            return ''
        (h, r) = divmod(x, 100)
        if h == 0:
            return _lt100(r)
        base = _ones[h] + ' trăm'
        if r == 0:
            return base
        if r < 10:
            return base + ' lẻ ' + _ones[r]
        return base + ' ' + _lt100(r)
    result = []
    for (div, unit) in ((1000000000, 'tỷ'), (1000000, 'triệu'), (1000, 'nghìn')):
        (q, n) = divmod(n, div)
        if q:
            result.append(_lt1000(q) + ' ' + unit)
    if n:
        s = _lt1000(n)
        if result and n < 100:
            s = ('lẻ ' if n < 10 else '') + s
        result.append(s)
    return ' '.join(result)
def replace_numbers_with_words(text):
    if not text:
        return ''
    import re
    def _replacer(m):
        raw = m.group(0)
        has_dot = '.' in raw
        has_comma = ',' in raw
        int_str = raw
        frac_str = ''
        if has_dot and has_comma:
            int_str = raw.split(',')[0].replace('.', '')
            frac_str = raw.split(',')[1]
        elif has_dot:
            parts = raw.split('.')
            if len(parts) >= 2 and all((len(p) == 3 for p in parts[1:])):
                int_str = raw.replace('.', '')
            elif len(parts) == 2:
                int_str = parts[0]
                frac_str = parts[1]
            else:
                int_str = raw.replace('.', '')
        elif has_comma:
            parts = raw.split(',')
            if len(parts) >= 2 and all((len(p) == 3 for p in parts[1:])):
                int_str = raw.replace(',', '')
            elif len(parts) == 2:
                int_str = parts[0]
                frac_str = parts[1]
            else:
                int_str = raw.replace(',', '')
        try:
            words = _vi_number_to_words(int(int_str))
            if frac_str:
                frac_words = ' '.join((_vi_number_to_words(int(d)) for d in frac_str))
                return words + ' phẩy ' + frac_words
            return words
        except Exception:
            return raw
    return re.sub('\\d+(?:[.,]\\d+)*', _replacer, text)
def _acquire_gpu_lock(log_fn, gpu_timeout, wait_msg):
    """Lay _LOCAL_GPU_LOCK. Tra ve False neu het gpu_timeout ma GPU van ban."""
    if _LOCAL_GPU_LOCK.acquire(blocking=False):
        return True
    log_fn(wait_msg)
    if gpu_timeout is not None:
        if not _LOCAL_GPU_LOCK.acquire(timeout=gpu_timeout):
            log_fn(f'''   [GPU] Quá {gpu_timeout:.0f}s chờ — GPU bận, huỷ test giọng.''')
            return False
        return True
    _LOCAL_GPU_LOCK.acquire()
    return True
def generate_tts_per_scene(scenes, voice, temp_dir, rate='+5%', log_fn=print, fptai_key=None, ref_audio_path='', strict_voice=False, gpu_timeout=None, **_unused):
    os.makedirs(temp_dir, exist_ok=True)
    for (idx, s) in enumerate(scenes):
        s['_original_index'] = idx
        if 'voiceover' in s:
            clean_text = (s['voiceover'] or '').replace('||', ' ')
            clean_text = re.sub('\\s+', ' ', clean_text).strip()
            s['voiceover_for_tts'] = replace_numbers_with_words(clean_text)
    if not fptai_key:
        fptai_key = os.getenv('FPT_API_KEY', '').strip()
    nonempty = [s for s in scenes if (s.get('voiceover') or '').strip()]
    voice = voice or ''
    if voice.lower().startswith('capcut-'):
        cc_voice = voice[len('capcut-'):]
        cookie = os.getenv('CAPCUT_COOKIE', '').strip()      # tuỳ chọn — không có vẫn chạy
        from core.capcut_tts import VOICES as CC_VOICES
        log_fn(f'''   TTS Engine: CapCut | Giọng: {CC_VOICES.get(cc_voice, (cc_voice,))[0]}{'' if cookie else ' (không cookie)'}''')
        out = _render_capcut_parallel(scenes, cc_voice, cookie, log_fn, temp_dir)
        if out and len(out) == len(nonempty):
            log_fn(f'''   Hoàn tất TTS (CapCut): {len(out)}/{len(nonempty)} cảnh''')
            return out
        if strict_voice:
            log_fn('   [LỖI] CapCut lỗi ở một số cảnh. Đang bật giữ đúng giọng nên KHÔNG tự đổi sang Edge TTS.')
            return out or []
        log_fn('   [WARN] CapCut lỗi — đọc lại TOÀN BỘ bằng Edge TTS cho đồng đều giọng'
               + ('' if cookie else ' (thử dán cookie CapCut ở Cài đặt nếu lỗi lặp lại)') + '...')
        from core.capcut_tts import edge_fallback
        out = _render_edge_parallel(scenes, edge_fallback(cc_voice), rate, log_fn, temp_dir)
        log_fn(f'''   Hoàn tất TTS (Edge - thay CapCut): {len(out)}/{len(nonempty)} cảnh''')
        return out
    _voice_lower = voice.lower()
    if _voice_lower.startswith('vieneu-') or _voice_lower.startswith('vieneu3-'):
        if _voice_lower.startswith('vieneu3-'):
            vn_voice = _voice_lower
        else:
            vn_voice = voice[len('vieneu-'):].lower()
        log_fn(f'''   Công nghệ TTS: VieNeu | Giọng: {vn_voice}''')
        if not _acquire_gpu_lock(log_fn, gpu_timeout, '   [GPU] Đang chờ GPU giải phóng (tiến trình khác đang xử lý)...'):
            return []
        _vn_fallback = []
        try:
            out = _render_vieneu_sequential(scenes, vn_voice, ref_audio_path, log_fn, temp_dir, allow_fallback=not strict_voice, _fallback_flag=_vn_fallback)
        finally:
            _LOCAL_GPU_LOCK.release()
        out = out or []
        if _vn_fallback:
            log_fn(f'''   Hoàn tất TTS (Edge TTS - fallback từ VieNeu): {len(out)}/{len(nonempty)} cảnh''')
        else:
            log_fn(f'''   Hoàn tất TTS (VieNeu): {len(out)}/{len(nonempty)} cảnh''')
        return out
    use_fptai = bool(fptai_key) and voice in FPTAI_VOICES
    edge_fallback = voice if voice in EDGE_VOICES else _get_fallback_edge_voice(voice)
    if use_fptai:
        log_fn(f'''   TTS Engine: FPT.AI | Giọng: {voice} ({FPTAI_VOICES.get(voice, '')})''')
        out = _render_fptai_sequential(scenes, voice, fptai_key, log_fn, temp_dir)
        if out and len(out) == len(nonempty):
            log_fn(f'''   Hoàn tất TTS (FPT.AI): {len(out)}/{len(nonempty)} cảnh''')
            return out
        if strict_voice:
            log_fn('   [LỖI] FPT.AI lỗi hoặc hết quota. Đang bật giữ đúng giọng nên KHÔNG tự đổi sang Edge TTS.')
            return []
        log_fn('   [WARN] FPT.AI hết quota / lỗi. Đọc lại TOÀN BỘ bằng Edge TTS...')
    else:
        if voice in FPTAI_VOICES and not fptai_key:
            if strict_voice:
                log_fn('   [LỖI] Chưa có FPT_AI_KEY cho giọng FPT.AI đã chọn. Đang bật giữ đúng giọng nên KHÔNG tự đổi sang Edge TTS.')
                return []
            log_fn('   [WARN] Chưa đặt FPT_AI_KEY, dùng Edge TTS')
        log_fn(f'''   TTS Engine: Edge TTS (song song) | Giọng: {edge_fallback}''')
    out = _render_edge_parallel(scenes, edge_fallback, rate, log_fn, temp_dir)
    log_fn(f'''   Hoàn tất TTS (Edge): {len(out)}/{len(nonempty)} cảnh''')
    if not out:
        log_fn('   [FALLBACK] Edge TTS thất bại hoàn toàn. Thử Google TTS (dự phòng cuối)...')
        out = _render_gtts_fallback(scenes, log_fn, temp_dir)
    return out
def _run_coro(make_coro):
    """Chay coroutine (tao boi make_coro) ke ca khi da co event loop dang chay."""
    try:
        return asyncio.run(make_coro())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(make_coro())
        finally:
            loop.close()
def _collect_results(results, check_file=True):
    result_map = {}
    for item in results or []:
        if isinstance(item, BaseException):
            continue
        (i, out_path, ok) = item
        if ok and (not check_file or (os.path.exists(out_path) and os.path.getsize(out_path) > 0)):
            result_map[i] = out_path
    return result_map
def _build_out_scenes(indexed, result_map, engine, log_fn, fail_msg, short_msg):
    out_scenes = []
    for (i, scene) in indexed:
        if i not in result_map:
            log_fn(fail_msg.format(n=i + 1))
            continue
        dur = _audio_duration(result_map[i])
        if dur < 0.1:
            log_fn(short_msg.format(n=i + 1, dur=dur))
            continue
        scene2 = dict(scene)
        scene2['tts_path'] = result_map[i]
        scene2['tts_duration'] = dur
        scene2['_tts_engine_used'] = engine
        out_scenes.append(scene2)
    return out_scenes
_EDGE_CHUNK = 30
_EDGE_RETRY = 2
def _render_edge_parallel(scenes, voice, rate, log_fn, temp_dir):
    try:
        import edge_tts
    except ImportError:
        log_fn('   [LỖI] Chưa cài edge-tts: pip install edge-tts')
        return []
    os.makedirs(temp_dir, exist_ok=True)
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    log_fn(f'''   Đang tạo giọng {total} cảnh (chunk {_EDGE_CHUNK}/batch, thử lại {_EDGE_RETRY}x)...''')
    async def _one(i, text):
        out_path = os.path.join(temp_dir, f'''vo_{i:04d}.mp3''')
        last_err = None
        for attempt in range(_EDGE_RETRY + 1):
            try:
                comm = edge_tts.Communicate(text, voice, rate=rate)
                await comm.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    return (i, out_path, True)
            except Exception as _e:
                last_err = _e
            if attempt < _EDGE_RETRY:
                await asyncio.sleep(1.0 * (attempt + 1))
        if last_err and i == 0:
            log_fn(f'''   [WARN] Edge TTS lỗi (cảnh đầu): {last_err}''')
        return (i, out_path, False)
    result_map = {}
    chunks = [indexed[k:k + _EDGE_CHUNK] for k in range(0, len(indexed), _EDGE_CHUNK)]
    async def _run_chunk(chunk):
        tasks = [_one(i, s.get('voiceover_for_tts', s['voiceover']).strip()) for (i, s) in chunk]
        return await asyncio.gather(*tasks, return_exceptions=True)
    done = 0
    for (ch_idx, chunk) in enumerate(chunks):
        results = _run_coro(lambda chunk=chunk: _run_chunk(chunk))
        result_map.update(_collect_results(results, check_file=False))
        done += len(chunk)
        log_fn(f'''   Edge TTS: {done}/{total} cảnh xong''')
    out_scenes = []
    for (i, scene) in indexed:
        if i not in result_map:
            log_fn(f'''   [WARN] Cảnh {i + 1}: Edge TTS thất bại, bỏ qua''')
            continue
        dur = _audio_duration(result_map[i])
        if dur < 0.1:
            log_fn(f'''   [WARN] Cảnh {i + 1}: audio quá ngắn ({dur:.2f}s), bỏ qua''')
            continue
        scene2 = dict(scene)
        scene2['tts_path'] = result_map[i]
        scene2['tts_duration'] = dur
        scene2['_tts_engine_used'] = 'edge'
        out_scenes.append(scene2)
    return out_scenes
def _render_fptai_sequential(scenes, voice, fptai_key, log_fn, temp_dir):
    out_scenes = []
    total = len([s for s in scenes if (s.get('voiceover') or '').strip()])
    for (i, scene) in enumerate(scenes):
        text = scene.get('voiceover_for_tts', scene.get('voiceover', '')).strip()
        if not text:
            continue
        idx = scene.get('_original_index', i)
        mp3_path = os.path.join(temp_dir, f'''vo_{idx:04d}.mp3''')
        ok = False
        for attempt in range(3):
            ok = _tts_fptai(text, voice, fptai_key, mp3_path, log_fn)
            if ok:
                break
            if attempt < 2:
                log_fn(f'''   [RETRY] FPT.AI cảnh {idx + 1}/{total} — thử lại lần {attempt + 2}/3...''')
                time.sleep(2 + attempt * 3)
        if not ok:
            log_fn(f'''   [WARN] FPT.AI dừng ở cảnh {idx + 1}/{total} (đã thử 3 lần)''')
            return out_scenes
        if voice in FPTAI_ENHANCE_VOICES:
            _enhance_fptai_audio(mp3_path, log_fn)
        dur = _audio_duration(mp3_path)
        if dur < 0.1:
            log_fn(f'''   [WARN] Cảnh {idx + 1}: audio quá ngắn, bỏ qua''')
            continue
        scene2 = dict(scene)
        scene2['tts_path'] = mp3_path
        scene2['tts_duration'] = dur
        scene2['_tts_engine_used'] = 'fptai'
        out_scenes.append(scene2)
        if (i + 1) % 5 == 0:
            log_fn(f'''   TTS FPT.AI: {i + 1}/{len(scenes)}''')
    return out_scenes
def _enhance_fptai_audio(mp3_path, log_fn=print):
    tmp_out = mp3_path + '.enh.mp3'
    try:
        r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-y', '-i', mp3_path, '-af', _FPTAI_ENHANCE_AF, '-ar', '44100', '-b:a', '128k', tmp_out], capture_output=True, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if r.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 1000:
            os.replace(tmp_out, mp3_path)
            return True
    except Exception as e:
        log_fn(f'''   [WARN] Hậu kỳ âm thanh lỗi (giữ bản gốc): {e}''')
    try:
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
    except Exception:
        pass
    return False
def _tts_fptai(text, voice, api_key, out_path, log_fn=print):
    url = 'https://api.fpt.ai/hmi/tts/v5'
    headers = {'api_key': api_key, 'voice': voice, 'format': 'mp3', 'speed': '0'}
    try:
        r = requests.post(url, data=text.encode('utf-8'), headers=headers, timeout=30)
        if r.status_code != 200:
            log_fn(f'''   [WARN] FPT.AI HTTP {r.status_code}: {r.text[:100]}''')
            return False
        data = r.json()
        if data.get('error', 0) != 0:
            log_fn(f'''   [WARN] FPT.AI lỗi: {data}''')
            return False
        audio_url = data.get('async', '')
        if not audio_url:
            return False
        for _ in range(40):
            time.sleep(3)
            ar = requests.get(audio_url, timeout=30)
            if ar.status_code == 200 and len(ar.content) > 1000:
                with open(out_path, 'wb') as f:
                    f.write(ar.content)
                return True
        log_fn('   [WARN] FPT.AI timeout')
        return False
    except Exception as e:
        log_fn(f'''   [WARN] FPT.AI ngoại lệ: {e}''')
        return False
# CapCut: ~60s cố định mỗi request + thêm theo số chữ, quá ~140s bị cắt → gom vài cảnh / request, nhiều request song song.
# Đo thật: 6 request x 3 cảnh (~70 từ) song song xong trong ~72s; quá ~6-8 request cùng lúc CapCut từ chối ngay.
_CAPCUT_MAX_CONCURRENCY = 6
_CAPCUT_BATCH_SCENES = 3
_CAPCUT_BATCH_WORDS = 220


def _capcut_batches(items):
    """[(i, text, out_path)] → các gói ≤ 3 cảnh và ≤ ~220 từ (cảnh dài hơn thì đi 1 mình)."""
    (batches, cur, words) = ([], [], 0)
    for it in items:
        n = len(it[1].split())
        if cur and (len(cur) >= _CAPCUT_BATCH_SCENES or words + n > _CAPCUT_BATCH_WORDS):
            batches.append(cur)
            (cur, words) = ([], 0)
        cur.append(it)
        words += n
    if cur:
        batches.append(cur)
    return batches


def _render_capcut_parallel(scenes, voice, cookie, log_fn, temp_dir):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from core.capcut_tts import CapcutBatchTooBig, CapcutError, synthesize_batch
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    items = [(i, s.get('voiceover_for_tts', s['voiceover']).strip(), os.path.join(temp_dir, f'vo_{i:04d}.mp3')) for (i, s) in indexed]
    batches = _capcut_batches(items)
    log_fn(f'   Đang tạo giọng CapCut {len(items)} cảnh ({len(batches)} gói, song song {_CAPCUT_MAX_CONCURRENCY} luồng)...')
    (ok, errors, lock, done) = (set(), [], threading.Lock(), [0])

    def _send(batch):
        """Gửi 1 gói; bị cắt vì quá dài thì chia đôi gửi lại. → chỉ số các cảnh thành công."""
        try:
            res = synthesize_batch([(t, p) for (_, t, p) in batch], voice, cookie)
        except CapcutBatchTooBig as e:
            if len(batch) == 1:
                errors.append(str(e))
                return set()
            mid = len(batch) // 2
            return _send(batch[:mid]) | _send(batch[mid:])
        except CapcutError as e:
            errors.append(str(e))
            return set()
        good = set()
        for (k, (i, _, _)) in enumerate(batch):
            if res.get(k):
                errors.append(res[k])
            else:
                good.add(i)
        return good

    def _job(batch):
        good = _send(batch)
        with lock:
            ok.update(good)
            done[0] += 1
            if done[0] % 5 == 0 or done[0] == len(batches):
                log_fn(f'   CapCut: {len(ok)}/{len(items)} cảnh xong')

    with ThreadPoolExecutor(_CAPCUT_MAX_CONCURRENCY) as ex:
        list(ex.map(_job, batches))
    # Cảnh lỗi (CapCut thỉnh thoảng trả "failed" / từ chối khi dồn dập) → nghỉ chút rồi gửi lại theo gói, tối đa 2 lượt
    for attempt in range(2):
        failed = [it for it in items if it[0] not in ok]
        if not failed:
            break
        log_fn(f'   CapCut lỗi {len(failed)} cảnh — gửi lại (lượt {attempt + 1})...')
        time.sleep(3)
        (batches, done[0]) = (_capcut_batches(failed), 0)
        with ThreadPoolExecutor(_CAPCUT_MAX_CONCURRENCY) as ex:
            list(ex.map(_job, batches))
    if errors and len(ok) < len(items):
        log_fn(f'   [WARN] CapCut: {errors[-1]}')
    result_map = {i: p for (i, _, p) in items if i in ok and os.path.exists(p) and os.path.getsize(p) > 0}
    return _build_out_scenes(indexed, result_map, 'capcut', log_fn, '   [WARN] Cảnh {n}: CapCut thất bại', '   [WARN] Cảnh {n}: audio quá ngắn, bỏ qua')
import sys as _sys_tts
def _read_model_pack_root():
    if not getattr(_sys_tts, 'frozen', False):
        return ''
    exe_dir = os.path.dirname(_sys_tts.executable)
    candidates = []
    env_path = os.environ.get('AUTOREVIEW_MODEL_PACK_DIR', '').strip()
    if env_path:
        candidates.append(env_path)
    for txt_name in ('model_pack_dir.txt', 'model_pack_path.txt'):
        txt_path = os.path.join(exe_dir, txt_name)
        if os.path.exists(txt_path):
            try:
                with open(txt_path, 'r', encoding='utf-8-sig') as fh:
                    raw = fh.read().strip().strip('"')
                if raw:
                    candidates.append(raw)
            except Exception:
                pass
    candidates.append(os.path.join(exe_dir, 'models'))
    for drive in [f'''{chr(c)}:{os.sep}''' for c in range(ord('C'), ord('Z') + 1) if os.path.exists(f'''{chr(c)}:{os.sep}''')]:
        for folder in ('AutoReviewModelPack', 'ModelPack_AutoReview', 'ModelPack', 'AutoReviewTool_Models'):
            candidates.append(os.path.join(drive, folder))
            candidates.append(os.path.join(drive, folder, 'models'))
    seen = set()
    for base in candidates:
        base = os.path.abspath(base) if base else ''
        if not base or base in seen or not os.path.isdir(base):
            continue
        seen.add(base)
        if os.path.exists(os.path.join(base, 'vixtts', 'model.pth')) or os.path.exists(os.path.join(base, 'vieneu', 'vieneu_worker.exe')):
            return base
        if os.path.exists(os.path.join(base, 'models', 'vixtts', 'model.pth')) or os.path.exists(os.path.join(base, 'models', 'vieneu', 'vieneu_worker.exe')):
            return os.path.join(base, 'models')
    return ''
_VIENEU_PYTHON = 'C:\\Users\\Admin\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe'
_VIENEU_DEV_HUB = 'D:\\AutoReview_Studio\\models\\vieneu\\hub'
_VIENEU_VOICE_MAP = {'adam-bua': 'Adam bựa', 'truc-ly': 'Trúc Ly', 'thien-minh': 'Thiện Minh', 'mai-anh': 'Mai Anh', 'hai-dang': 'Hải Đăng', 'thuy-dung': 'Thùy Dung', 'thien-tam-duc': 'Thiền Tâm Đức', 'ngoc-huyen': 'Ngọc Huyền', 'quang-son': 'Quang Sơn', 'ngoc-tran': 'Ngọc Trân', 'minh-duc': 'Minh Đức', 'pham-tuyen': 'Phạm Tuyên', 'thai-son': 'Thái Sơn', 'xuan-vinh': 'Xuân Vĩnh', 'thanh-binh': 'Thanh Bình', 'ngoc-linh': 'Ngọc Linh', 'doan-trang': 'Đoan Trang', 'thuc-doan': 'Thục Đoan', 'minh-triet': 'Minh Triết', 'my-duyen': 'Mỹ Duyên', 'quynh-anh': 'Quỳnh Anh', 'duc-tri': 'Đức Trí', 'kim-thanh': 'Kim Thanh', 'adam': 'Adam', 'quoc-tuan': 'Quốc Tuấn', 'binh-an': 'Bình An', 'ngoc-lan': 'Ngọc Lan', 'gia-bao': 'Gia Bảo', 'trong-huu': 'Trọng Hữu', 'clone': 'clone'}
def _get_vieneu_worker_script():
    if getattr(_sys_tts, 'frozen', False):
        return os.path.join(_sys_tts._MEIPASS, 'vieneu_worker.py')
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'workers', 'vieneu_worker.py')
def _get_vieneu_exe_dir():
    if getattr(_sys_tts, 'frozen', False):
        model_root = _read_model_pack_root()
        if model_root:
            ext_dir = os.path.join(model_root, 'vieneu')
            if os.path.isdir(ext_dir):
                return ext_dir
        return os.path.join(os.path.dirname(_sys_tts.executable), 'models', 'vieneu')
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _get_vieneu_cmd():
    import sys
    try:                                     # cài bằng nút "Tải model" trong app (môi trường riêng trong thư mục dữ liệu)
        from . import vieneu_setup
        managed = vieneu_setup.worker_cmd()
        if managed:
            return (managed[0], managed[1], True)
    except Exception:
        pass
    exe_dir = _get_vieneu_exe_dir()
    worker_exe = os.path.join(exe_dir, 'vieneu_worker.exe')
    if os.path.exists(worker_exe):
        hf_home = os.path.join(exe_dir, 'hub')
        return ([worker_exe], hf_home if os.path.isdir(hf_home) else '', True)
    if not getattr(sys, 'frozen', False):
        worker_py = _get_vieneu_worker_script()
        if os.path.exists(_VIENEU_PYTHON) and os.path.exists(worker_py):
            hf_home = _VIENEU_DEV_HUB if os.path.isdir(_VIENEU_DEV_HUB) else ''
            return ([_VIENEU_PYTHON, '-W', 'ignore', worker_py], hf_home, True)
    if getattr(sys, 'frozen', False):
        try:
            import importlib.util
            if importlib.util.find_spec('vieneu') is not None:
                hf_home = os.path.join(exe_dir, 'hub')
                return ([sys.executable, '--vieneu-worker'], hf_home if os.path.isdir(hf_home) else '', True)
        except Exception:
            pass
    return (None, '', False)
def _trim_ref_audio(path, temp_dir, log_fn, max_dur=18.0):
    try:
        from .utils import run_subprocess
        r = run_subprocess([FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path], timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        dur = float(r.stdout.strip())
    except Exception:
        return path
    if dur <= max_dur + 0.5:
        return path
    log_fn(f'''   [WARN] File mẫu giọng dài {dur:.1f}s (quá dài) — tự cắt xuống {max_dur:.0f}s đầu để tránh treo/lỗi clone.''')
    trimmed = os.path.join(temp_dir, '_vieneu_ref_trimmed.wav')
    try:
        from .utils import run_subprocess
        r2 = run_subprocess([FFMPEG_EXE, '-y', '-i', path, '-t', str(max_dur), '-ac', '1', trimmed], timeout=30, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r2.returncode == 0 and os.path.exists(trimmed) and os.path.getsize(trimmed) > 0:
            return trimmed
    except Exception:
        pass
    return path
# File mẫu trong voice_samples/ mang tên khác tên giọng (bản ghi từ bộ cũ) — thiếu bảng này thì giọng lặng lẽ đọc thành "Bình An"
_VIENEU3_REF_ALIASES = {
    'vieneu3-ban-mai': 'fpt_banmai.wav', 'vieneu3-mia': 'fpt_mia.wav', 'vieneu3-minh-quang': 'fpt_minhquang.wav',
    'vieneu3-nam': 'fpt_nam.wav', 'vieneu3-nguyen': 'fpt_nguyen.wav', 'vieneu3-thu-minh': 'fpt_thuminh.wav',
    'vieneu3-lena': 'lena_xtts_ref.wav', 'vieneu3-mc-truyen-hinh': 'mc_truyen_hinh_clone.wav',
    'vieneu3-he-thong': 'giong_doc_he_thong.wav', 'vieneu3-quang-cao': 'giong_bac_noi_luc.wav',
    'vieneu3-nam-tram-am': 'vixtts_nam-calm.wav', 'vieneu3-nam-cham-rai': 'vixtts_nam-cham.wav',
    'vieneu3-nam-nhanh-nhen': 'vixtts_nam-nhanh.wav', 'vieneu3-nam-truyen-cam': 'vixtts_nam-truyen-cam.wav',
    'vieneu3-nu-diem-dam': 'vixtts_nu-calm.wav', 'vieneu3-nu-cham-rai': 'vixtts_nu-cham.wav',
    'vieneu3-nu-luu-loat': 'vixtts_nu-luu-loat.wav', 'vieneu3-nu-nhan-nha': 'vixtts_nu-nhan-nha.wav',
    'vieneu3-nu-nhe-nhang': 'vixtts_nu-nhe-nhang.wav',
}


def _get_vieneu3_builtin_ref(vn_voice):
    fname = _VIENEU3_BUILTIN_REF.get(vn_voice)
    if not fname:
        return ''
    from .utils import voice_samples_dir
    for path in (os.path.join(voice_samples_dir('vieneu3_ref'), fname),
                 os.path.join(voice_samples_dir(), fname.replace('-', '_')),
                 os.path.join(voice_samples_dir(), _VIENEU3_REF_ALIASES.get(vn_voice, '\0'))):
        if os.path.exists(path):
            return path
    return ''
def _vn_item(scene):
    """Lô nhiều nhân vật: câu mang '_vn_voice' riêng → giọng có sẵn ('voice') hoặc file mẫu clone có sẵn ('ref')."""
    v = scene.get('_vn_voice')
    if not v:
        return {}
    ref = _get_vieneu3_builtin_ref(v)
    return {'ref': ref} if ref else {'voice': v}


def vieneu_voice_key(voice):
    """id trong VOICE_OPTIONS ('vieneu-hai-dang' / 'vieneu3-lena') → id worker ('hai-dang' / 'vieneu3-lena'); không phải VieNeu → ''."""
    v = (voice or '').lower()
    return v if v.startswith('vieneu3-') else (v[len('vieneu-'):] if v.startswith('vieneu-') else '')


def generate_vieneu_cast(scenes, temp_dir, log_fn=print, gpu_timeout=600):
    """Đọc câu của NHIỀU nhân vật VieNeu trong 1 lần nạp model (mỗi câu có '_vn_voice'), khỏi nạp lại model cho từng giọng."""
    scenes = [s for s in scenes if (s.get('voiceover') or '').strip() and s.get('_vn_voice')]
    if not scenes:
        return []
    for (i, s) in enumerate(scenes):
        s.setdefault('_original_index', i)
    n_voice = len({s['_vn_voice'] for s in scenes})
    if not _acquire_gpu_lock(log_fn, gpu_timeout, '   [GPU] Đang chờ GPU giải phóng (tiến trình khác đang xử lý)...'):
        return []
    try:
        return _render_vieneu_sequential(scenes, scenes[0]['_vn_voice'], '', log_fn, temp_dir, allow_fallback=False,
                                         _display_override=f'{n_voice} giọng nhân vật') or []
    finally:
        _LOCAL_GPU_LOCK.release()


def _render_vieneu_sequential(scenes, vn_voice, ref_audio_path, log_fn, temp_dir, allow_fallback=True, _fallback_flag=None, _retry_done=False, _display_override=None):
    _orig_voice = vn_voice
    _edge_voice = _get_fallback_edge_voice(_orig_voice)
    def _full_edge_fallback():
        if _fallback_flag is not None:
            _fallback_flag.append(True)
        return _render_edge_parallel(scenes, _edge_voice, '+5%', log_fn, temp_dir)
    _builtin_ref = _get_vieneu3_builtin_ref(vn_voice)
    if _builtin_ref:
        if _display_override is None:
            _display_override = VIENEU_VOICES.get(vn_voice, vn_voice)
        ref_audio_path = _builtin_ref
        vn_voice = 'clone'
    is_clone = vn_voice == 'clone'
    if is_clone and (not ref_audio_path or not os.path.exists(ref_audio_path)):
        log_fn('   [LỖI] VieNeu Clone cần file audio mẫu (3-5 giây). Chưa có file mẫu.')
        if not allow_fallback:
            return []
        log_fn('   => Tự chuyển sang Edge TTS...')
        if _fallback_flag is not None:
            _fallback_flag.append(True)
        return _render_edge_parallel(scenes, 'vi-VN-HoaiMyNeural', '+5%', log_fn, temp_dir)
    if is_clone and ref_audio_path:
        ref_audio_path = _trim_ref_audio(ref_audio_path, temp_dir, log_fn)
    if vn_voice not in _VIENEU_VOICE_MAP:
        log_fn(f'''   [WARN] Giọng VieNeu không hợp lệ: {vn_voice} — dùng Hải Đăng''')
        vn_voice = 'hai-dang'
    (base_cmd, hf_home, cmd_ok) = _get_vieneu_cmd()
    if not cmd_ok:
        if getattr(_sys_tts, 'frozen', False):
            log_fn('   [LỖI] Chưa cài Model Pack VieNeu.')
            log_fn('   Giải nén ModelPack vào thư mục AutoReviewTool/ để dùng giọng VieNeu.')
            log_fn('   => Ổ chứa AutoReviewTool hết dung lượng? Có thể giải nén ModelPack sang Ổ ĐĨA KHÁC (vd D:\\ModelPack hoặc E:\\ModelPack) — tool tự tìm thấy, không cần cùng ổ với exe.')
        else:
            log_fn('   [LỖI] Chưa cài VieNeu — vào trang Giọng đọc, bấm "Tải model VieNeu".')
        if not allow_fallback:
            return []
        log_fn('   => Tự chuyển sang Edge TTS...')
        return _full_edge_fallback()
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    if not indexed:
        return []
    os.makedirs(temp_dir, exist_ok=True)
    batch = [{'text': s.get('voiceover_for_tts', s['voiceover']).strip(), 'out': os.path.join(temp_dir, f'''vo_{i:04d}.wav'''), **_vn_item(s)}
             for (i, s) in indexed]
    batch_file = os.path.join(temp_dir, '_vieneu_batch.json')
    import json as _json_vn
    with open(batch_file, 'w', encoding='utf-8') as bf:
        _json_vn.dump(batch, bf, ensure_ascii=False)
    display_voice = _display_override or VIENEU_VOICES.get(vn_voice, vn_voice)
    log_fn(f'''   VieNeu TTS: {display_voice} | {total} cảnh...''')
    ref_arg = (ref_audio_path or '') if is_clone else ''
    cmd = base_cmd + [batch_file, vn_voice, ref_arg, hf_home]
    timeout_secs = max(360, 90 + total * 30)
    env = os.environ.copy()
    env['PYTHONWARNINGS'] = 'ignore'
    from . import vieneu_setup
    if base_cmd[0] == vieneu_setup.PY:
        env = vieneu_setup.hf_env(offline=True)   # model đã tải đủ lúc cài → không gọi mạng
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE, env=env)
        register_process(proc)
        deadline = time.time() + timeout_secs
        try:
            for line in proc.stdout:
                if time.time() > deadline:
                    proc.kill()
                    log_fn('   [WARN] VieNeu TTS quá thời gian — giải phóng tiến trình')
                    break
                line = line.rstrip()
                if line and '[VIENEU_WORKER]' in line:
                    log_fn(f'''   {line.replace('[VIENEU_WORKER] ', '')}''')
            proc.wait()
        finally:
            unregister_process(proc)
    except Exception as e:
        log_fn(f'''   [WARN] Lỗi VieNeu worker: {e}''')
    out_scenes = []
    failed_scenes = []
    n_suspect = 0
    for (i, scene) in indexed:
        out_path = os.path.join(temp_dir, f'''vo_{i:04d}.wav''')
        if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
            failed_scenes.append(scene)
            continue
        dur = _audio_duration(out_path)
        if dur < 0.1:
            failed_scenes.append(scene)
            continue
        text = scene.get('voiceover_for_tts', scene.get('voiceover', '')).strip()
        if not _is_plausible_tts_duration(text, dur):
            failed_scenes.append(scene)
            n_suspect += 1
            continue
        scene2 = dict(scene)
        scene2['tts_path'] = out_path
        scene2['tts_duration'] = dur
        scene2['_tts_engine_used'] = 'vieneu'
        out_scenes.append(scene2)
    if n_suspect:
        log_fn(f'''   [WARN] {n_suspect} cảnh VieNeu có audio bất thường (nghi bị cắt ngang/lỗi) — bỏ qua''')
    log_fn(f'''   VieNeu TTS hoàn tất: {len(out_scenes)}/{total} cảnh thành công''')
    if failed_scenes:
        if not _retry_done and out_scenes:
            log_fn(f'''   [RETRY] {len(failed_scenes)} cảnh lỗi — thử lại 1 lần bằng chính giọng VieNeu để giữ nhất quán...''')
            retry_res = _render_vieneu_sequential(failed_scenes, vn_voice, ref_audio_path, log_fn, temp_dir, allow_fallback=False, _retry_done=True, _display_override=_display_override)
            got_idx = {s.get('_original_index') for s in retry_res}
            out_scenes.extend(retry_res)
            failed_scenes = [s for s in failed_scenes if s.get('_original_index') not in got_idx]
        if failed_scenes and out_scenes:
            if allow_fallback:
                log_fn(f'''   [FALLBACK] {len(failed_scenes)} cảnh vẫn lỗi sau khi thử lại → đổi sang Edge TTS (giọng khác) bổ sung...''')
                edge_res = _render_edge_parallel(failed_scenes, _edge_voice, '+5%', log_fn, temp_dir)
                out_scenes.extend(edge_res)
            else:
                log_fn(f'''   [WARN] {len(failed_scenes)} cảnh vẫn lỗi sau khi thử lại — bỏ qua (không đổi giọng).''')
        out_scenes.sort(key=lambda s: s.get('_original_index', 0))
    if (not out_scenes or len(out_scenes) < total * 0.5) and allow_fallback:
        log_fn('   [WARN] VieNeu tỷ lệ thất bại cao — chuyển toàn bộ sang Edge TTS...')
        return _full_edge_fallback()
    return out_scenes
def _render_gtts_fallback(scenes, log_fn, temp_dir):
    try:
        from gtts import gTTS
    except ImportError:
        log_fn('   [WARN] Chưa cài gTTS (pip install gTTS) — bỏ qua phương án dự phòng này')
        return []
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    if not indexed:
        return []
    log_fn(f'''   Google TTS: xử lý {total} cảnh...''')
    out_scenes = []
    fail = 0
    for (i, scene) in indexed:
        text = scene.get('voiceover_for_tts', scene['voiceover']).strip()
        if not text:
            continue
        out_path = os.path.join(temp_dir, f'''vo_{i:04d}_gtts.mp3''')
        try:
            tts = gTTS(text=text, lang='vi', slow=False)
            tts.save(out_path)
            dur = _audio_duration(out_path)
            if dur < 0.1:
                fail += 1
                continue
            scene2 = dict(scene)
            scene2['tts_path'] = out_path
            scene2['tts_duration'] = dur
            scene2['_tts_engine_used'] = 'gtts'
            out_scenes.append(scene2)
        except Exception as e:
            fail += 1
            if fail <= 3:
                log_fn(f'''   [WARN] Google TTS cảnh {i + 1}: {e}''')
    log_fn(f'''   Google TTS: {len(out_scenes)}/{total} cảnh thành công''')
    return out_scenes
def _is_plausible_tts_duration(text, dur):
    n_chars = len(text)
    if n_chars == 0:
        return dur < 0.5
    min_dur = n_chars / 26.0         # giọng đọc nhanh (VieNeu ~23 ký tự/giây) vẫn hợp lệ; audio bị cắt cụt ngắn hơn nhiều
    max_dur = n_chars / 4.0 + 2.0
    return min_dur <= dur <= max_dur
def _concat_audio_files(paths, out_path, log_fn=print):
    from .utils import FFMPEG_EXE, run_subprocess
    if not paths:
        return ''
    if len(paths) == 1:
        return paths[0]
    cmd = [FFMPEG_EXE, '-y']
    for p in paths:
        cmd += ['-i', p]
    n = len(paths)
    filt = ''.join((f'''[{k}:a]aresample=48000,aformat=sample_fmts=s16:channel_layouts=mono[a{k}];''' for k in range(n))) + ''.join((f'''[a{k}]''' for k in range(n))) + f'''concat=n={n}:v=0:a=1[out]'''
    cmd += ['-filter_complex', filt, '-map', '[out]', out_path]
    try:
        r = run_subprocess(cmd, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            return out_path
        log_fn(f'''   [WARN] Ghép audio phân vai lỗi: {(r.stderr or '')[-200:]}''')
    except Exception as e:
        log_fn(f'''   [WARN] Ghép audio phân vai lỗi: {e}''')
    return ''
def generate_tts_multi_voice(scenes, voice_map, narrator_voice, temp_dir, log_fn=print, **kw):
    os.makedirs(temp_dir, exist_ok=True)
    voice_map = voice_map or {}
    def _voice_for(seg):
        vai = (seg.get('vai') or 'ke').strip()
        return narrator_voice if vai == 'ke' else voice_map.get(vai, narrator_voice)
    by_voice = {}
    seg_lists = []
    for (i, s) in enumerate(scenes):
        segs = [seg for seg in (s.get('segments') or [{'text': s.get('voiceover', ''), 'vai': 'ke'}]) if (seg.get('text') or '').strip()]
        seg_lists.append(segs)
        for (gi, seg) in enumerate(segs):
            v = _voice_for(seg)
            by_voice.setdefault(v, []).append({'voiceover': seg['text'].strip(), 'subtitle': seg['text'].strip(), '_mv_key': [i, gi]})
    path_map = {}
    for (bi, (v, plist)) in enumerate(by_voice.items()):
        log_fn(f'''   [PHÂN VAI] Giọng \'{v}\': {len(plist)} đoạn...''')
        vdir = os.path.join(temp_dir, f'''mv_voice_{bi:02d}''')
        out = generate_tts_per_scene(plist, v, vdir, log_fn=log_fn, **kw)
        for o in out or []:
            k = o.get('_mv_key')
            p = o.get('tts_path', '')
            if k and p and os.path.exists(p):
                path_map[tuple(k)] = p
    out_scenes = []
    for (i, s) in enumerate(scenes):
        segs = seg_lists[i]
        if not segs:
            continue
        paths = [path_map.get((i, gi)) for gi in range(len(segs))]
        paths = [p for p in paths if p]
        if not paths:
            log_fn(f'''   [WARN] Cảnh {i + 1}: không tạo được giọng đoạn nào — bỏ cảnh.''')
            continue
        if len(paths) < len(segs):
            log_fn(f'''   [WARN] Cảnh {i + 1}: thiếu {len(segs) - len(paths)} đoạn giọng — ghép phần có được.''')
        if len(paths) == 1:
            final = paths[0]
        else:
            final = _concat_audio_files(paths, os.path.join(temp_dir, f'''mv_{i:04d}.wav'''), log_fn)
            if not final:
                final = paths[0]
        dur = _audio_duration(final)
        if dur < 0.1:
            continue
        s2 = dict(s)
        s2['tts_path'] = final
        s2['tts_duration'] = dur
        s2['_tts_engine_used'] = 'vieneu'
        s2['_cast_voices'] = len({_voice_for(seg) for seg in segs})
        out_scenes.append(s2)
    log_fn(f'''   [PHÂN VAI] Hoàn tất: {len(out_scenes)}/{len(scenes)} câu, {len(by_voice)} giọng khác nhau.''')
    return out_scenes
def _audio_duration(path):
    try:
        from .utils import run_subprocess
        r = run_subprocess([FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path], timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        return float(r.stdout.strip())
    except Exception:
        return 0.0
