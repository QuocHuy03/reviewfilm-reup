

"""
TTS Engine: doc tung canh script bang Edge-TTS, FPT.AI, OpenAI hoac ElevenLabs.
Edge TTS, OpenAI, ElevenLabs chay SONG SONG tat ca canh (asyncio.gather) → nhanh hon 10-20x.
FPT.AI chay tuan tu de tranh rate limit.
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
def _has_model_pack_entitlement():
    return True
FPTAI_VOICES = {'banmai': 'Nu, mien Bac', 'lannhi': 'Nu, mien Nam', 'leminh': 'Nam, mien Bac', 'myan': 'Nu, mien Trung', 'thuminh': 'Nu, mien Bac', 'giahuy': 'Nam, mien Trung', 'linhsan': 'Nu, mien Nam', 'ngoclam': 'Nu, mien Trung', 'minhquang': 'Nam, mien Nam', 'banmaiace': 'Nu, mien Bac (Ace)', 'thuminhace': 'Nu, mien Bac (Ace)', 'ngoclamace': 'Nu, mien Trung (Ace)', 'linhsanace': 'Nu, mien Nam (Ace)', 'minhquangace': 'Nam, mien Nam (Ace)'}
FPTAI_ENHANCE_VOICES = {'lannhi'}
_FPTAI_ENHANCE_AF = 'highpass=f=75,equalizer=f=300:t=q:w=1.2:g=-1.5,equalizer=f=2500:t=q:w=1.0:g=2,treble=g=5:f=4000,acompressor=threshold=-18dB:ratio=2.5:attack=8:release=120:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=9,atempo=1.08'
EDGE_VOICES = {'vi-VN-HoaiMyNeural': 'Nu - Edge TTS mien phi', 'vi-VN-NamMinhNeural': 'Nam - Edge TTS mien phi'}
_FEMALE_VOICE_HINTS = ('lena', 'banmai', 'mia', 'rachel', 'nova', 'shimmer', 'ngoc-lan', 'ngoclan', 'my-duyen', 'myduyen', 'truc-ly', 'trucly', 'ngoc-linh', 'ngoclinh', 'hoaimy', '21m00tcm4tlvdq8ikwam')
def _get_fallback_edge_voice(voice):
    voice = ((voice or '')).lower()
    if any((h in voice for h in _FEMALE_VOICE_HINTS)):
        return 'vi-VN-HoaiMyNeural'
    return 'vi-VN-NamMinhNeural'
VIETTEL_VOICES = {'hn-quynhanh': 'Nu, mien Bac - Quynh Anh', 'hcm-diemmy': 'Nu, mien Nam - Diem My', 'hue-maingoc': 'Nu, mien Trung - Mai Ngoc', 'hn-phuongtrang': 'Nu, mien Bac - Phuong Trang (mac dinh)', 'hn-thaochi': 'Nu, mien Bac - Thao Chi', 'hn-thanhha': 'Nu, mien Bac - Thanh Ha', 'hcm-phuongly': 'Nu, mien Nam - Phuong Ly', 'hcm-thuydung': 'Nu, mien Nam - Thuy Dung', 'hn-thanhtung': 'Nam, mien Bac - Thanh Tung', 'hue-baoquoc': 'Nam, mien Trung - Bao Quoc', 'hcm-minhquan': 'Nam, mien Nam - Minh Quan', 'hn-thanhphuong': 'Nu, mien Bac - Thanh Phuong', 'hn-namkhanh': 'Nam, mien Bac - Nam Khanh', 'hn-leyen': 'Nu, mien Nam - Le Yen', 'hn-tienquan': 'Nam, mien Bac - Tien Quan', 'hcm-thuyduyen': 'Nu, mien Nam - Thuy Duyen'}
VIENEU_VOICES = {'binh-an': 'Nam - Bình An (VieNeu điềm đạm)', 'xuan-vinh': 'Nam - Xuân Vĩnh (VieNeu vui tươi)', 'ngoc-lan': 'Nữ - Ngọc Lan (VieNeu dịu dàng)', 'my-duyen': 'Nữ - Mỹ Duyên (VieNeu mượt mà)', 'truc-ly': 'Nữ - Trúc Ly (VieNeu trẻ trung)', 'ngoc-linh': 'Nữ - Ngọc Linh (VieNeu tươi sáng)', 'gia-bao': 'Nam - Gia Bảo (VieNeu mượt mà)', 'thai-son': 'Nam - Thái Sơn (VieNeu chắc khỏe)', 'duc-tri': 'Nam - Đức Trí (VieNeu rõ ràng)', 'trong-huu': 'Nam - Trọng Hữu (VieNeu uyên bác)', 'clone': 'Nhân bản giọng riêng (VieNeu - cần 3-5s audio mẫu)', 'vieneu3-chien-thang': 'VieNeu3 - Chiến Thắng', 'vieneu3-hung-ba': 'VieNeu3 - Hùng Bá', 'vieneu3-lam-le': 'VieNeu3 - Lâm Lê', 'vieneu3-ly-long-tieng': 'VieNeu3 - Lý Long Tiếng', 'vieneu3-phat-phap': 'VieNeu3 - Pháp Phật', 'vieneu3-review-toptop': 'VieNeu3 - Review Toptop', 'vieneu3-trinh-le': 'VieNeu3 - Trịnh Lê', 'vieneu3-trung-dung': 'VieNeu3 - Trung Dũng', 'vieneu3-yen-tin-tuc': 'VieNeu3 - Yến Tin Tức', 'vieneu3-ban-mai': 'VieNeu3 - Ban Mai', 'vieneu3-bac-quynh-anh': 'VieNeu3 - Quỳnh Anh (Giọng Bắc)', 'vieneu3-bac-thao-chi': 'VieNeu3 - Thảo Chi (Giọng Bắc)', 'vieneu3-bac-thanh-tung': 'VieNeu3 - Thanh Tùng (Giọng Bắc)', 'vieneu3-bac-nam-khanh': 'VieNeu3 - Nam Khánh (Giọng Bắc)', 'vieneu3-quang-cao': 'VieNeu3 - Quảng Cáo Nội Lực', 'vieneu3-he-thong': 'VieNeu3 - Hệ Thống', 'vieneu3-lena': 'VieNeu3 - Lena', 'vieneu3-mc-truyen-hinh': 'VieNeu3 - MC Truyền Hình', 'vieneu3-mia': 'VieNeu3 - Mia', 'vieneu3-minh-quang': 'VieNeu3 - Minh Quang', 'vieneu3-nam': 'VieNeu3 - Nam', 'vieneu3-nguyen': 'VieNeu3 - Nguyên', 'vieneu3-thu-minh': 'VieNeu3 - Thu Minh', 'vieneu3-nam-tram-am': 'VieNeu3 - Nam Trầm Ấm', 'vieneu3-nam-cham-rai': 'VieNeu3 - Nam Chậm Rãi', 'vieneu3-nam-nhanh-nhen': 'VieNeu3 - Nam Nhanh Nhẹn', 'vieneu3-nam-truyen-cam': 'VieNeu3 - Nam Truyền Cảm', 'vieneu3-nu-diem-dam': 'VieNeu3 - Nữ Điềm Đạm', 'vieneu3-nu-cham-rai': 'VieNeu3 - Nữ Chậm Rãi', 'vieneu3-nu-luu-loat': 'VieNeu3 - Nữ Lưu Loát', 'vieneu3-nu-nhan-nha': 'VieNeu3 - Nữ Nhàn Nhã', 'vieneu3-nu-nhe-nhang': 'VieNeu3 - Nữ Nhẹ Nhàng'}
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
def generate_tts_per_scene(scenes, voice, temp_dir, rate='+5%', log_fn=print, fptai_key=None, openai_key=None, elevenlabs_key=None, viettel_key=None, ref_audio_path='', prompt_text='', local_api_url='http://127.0.0.1:9880', strict_voice=False, gpu_timeout=None):
    os.makedirs(temp_dir, exist_ok=True)
    for (idx, s) in enumerate(scenes):
        s['_original_index'] = idx
        if 'voiceover' in s:
            clean_text = (s['voiceover'] or '').replace('||', ' ')
            clean_text = re.sub('\\s+', ' ', clean_text).strip()
            s['voiceover_for_tts'] = replace_numbers_with_words(clean_text)
    if not fptai_key:
        fptai_key = os.getenv('FPT_AI_KEY', '').strip()
    if not openai_key:
        openai_key = os.getenv('OPENAI_API_KEY', '').strip()
    if not elevenlabs_key:
        elevenlabs_key = os.getenv('ELEVENLABS_API_KEY', '').strip()
    if not viettel_key:
        viettel_key = os.getenv('VIETTEL_AI_TOKEN', '').strip()
    nonempty = [s for s in scenes if (s.get('voiceover') or '').strip()]
    voice = voice or ''
    if voice.lower() == 'local-xtts':
        if not _has_model_pack_entitlement():
            log_fn('   [KHOÁ] Clone Giọng Offline cần addon Model Pack (+119.000đ) — nâng cấp tại vatoolskit.com. Tự chuyển sang Edge TTS...')
            return _render_edge_parallel(scenes, _get_fallback_edge_voice(os.path.basename(ref_audio_path or '')), '+5%', log_fn, temp_dir)
        log_fn(f'''   Công nghệ lồng tiếng: Nhân bản Offline v2 | Bản ghi mẫu: {os.path.basename(ref_audio_path or 'N/A')}''')
        if not _acquire_gpu_lock(log_fn, gpu_timeout, '   [GPU] Đang chờ GPU giải phóng (video khác đang xử lý)...'):
            return []
        try:
            out = _render_xtts_sequential(scenes, ref_audio_path, log_fn, temp_dir, allow_fallback=not strict_voice)
        finally:
            _LOCAL_GPU_LOCK.release()
        return out
    if voice.lower().startswith('local-'):
        log_fn('   Công nghệ lồng tiếng: Nhân bản Offline v1')
        if not _acquire_gpu_lock(log_fn, gpu_timeout, '   [GPU] Đang chờ GPU giải phóng (video khác đang xử lý)...'):
            return []
        try:
            out = _render_local_gptsovits_parallel(scenes, local_api_url, ref_audio_path, prompt_text, log_fn, temp_dir)
        finally:
            _LOCAL_GPU_LOCK.release()
        if out and len(out) < len(nonempty) * 0.5:
            log_fn('   [WARN] Ty le that bai cao. Ket qua co the bi thieu canh.')
        return out
    if voice.lower().startswith('openai-'):
        if not openai_key:
            if strict_voice:
                log_fn('   [LOI] Chua co OPENAI_API_KEY. Dang bat giu dung giong nen KHONG tu doi sang Edge TTS.')
                return []
            voice = _get_fallback_edge_voice(voice)
            log_fn(f'''   [WARN] Khong co OPENAI_API_KEY -> Tu dong chuyen sang Edge TTS mien phi ({voice})''')
        else:
            openai_voice = voice.split('-')[1].strip()
            log_fn(f'''   TTS Engine: OpenAI TTS | Giong: {openai_voice}''')
            out = _render_openai_parallel(scenes, openai_voice, openai_key, log_fn, temp_dir)
            log_fn(f'''   Hoan tat TTS (OpenAI): {len(out)}/{len(nonempty)} canh''')
            return out
    if voice.lower().startswith('eleven-'):
        if not elevenlabs_key:
            if strict_voice:
                log_fn('   [LOI] Chua co ELEVENLABS_API_KEY. Dang bat giu dung giong nen KHONG tu doi sang Edge TTS.')
                return []
            voice = _get_fallback_edge_voice(voice)
            log_fn(f'''   [WARN] Khong co ELEVENLABS_API_KEY -> Tu dong chuyen sang Edge TTS mien phi ({voice})''')
        else:
            m = re.search('\\(([^)]+)\\)', voice)
            eleven_voice = m.group(1).strip() if m else voice.split('-')[1].strip()
            log_fn(f'''   TTS Engine: ElevenLabs TTS | Giong ID: {eleven_voice}''')
            out = _render_elevenlabs_parallel(scenes, eleven_voice, elevenlabs_key, log_fn, temp_dir)
            log_fn(f'''   Hoan tat TTS (ElevenLabs): {len(out)}/{len(nonempty)} canh''')
            return out
    if voice.lower().startswith('viettel-'):
        vt_voice_code = voice[len('viettel-'):].strip()
        if vt_voice_code in ('', 'default'):
            vt_voice_code = 'hn-phuongtrang'
        if not viettel_key:
            if strict_voice:
                log_fn('   [LOI] Chua co VIETTEL_AI_TOKEN. Dang bat giu dung giong nen KHONG tu doi sang Edge TTS.')
                return []
            log_fn('   [WARN] Chua cau hinh VIETTEL_AI_TOKEN -> Tu dong chuyen sang Edge TTS mien phi')
            out = _render_edge_parallel(scenes, _get_fallback_edge_voice(vt_voice_code), rate, log_fn, temp_dir)
            log_fn(f'''   Hoan tat TTS (Edge - fallback tu VT): {len(out)}/{len(nonempty)} canh''')
            return out
        log_fn(f'''   TTS Engine: (VT) | Giong: {vt_voice_code} ({VIETTEL_VOICES.get(vt_voice_code, '')})''')
        out = _render_viettel_parallel(scenes, vt_voice_code, viettel_key, log_fn, temp_dir)
        if out and len(out) == len(nonempty):
            log_fn(f'''   Hoan tat TTS (VT): {len(out)}/{len(nonempty)} canh''')
            return out
        if strict_voice:
            log_fn('   [LOI] (VT) loi hoac het quota. Dang bat giu dung giong nen KHONG tu doi sang Edge TTS.')
            return []
        log_fn('   [WARN] (VT) loi/het quota. Doc lai TOAN BO bang Edge TTS...')
        out = _render_edge_parallel(scenes, _get_fallback_edge_voice(vt_voice_code), rate, log_fn, temp_dir)
        log_fn(f'''   Hoan tat TTS (Edge - fallback tu VT): {len(out)}/{len(nonempty)} canh''')
        return out
    _voice_lower = voice.lower()
    if _voice_lower.startswith('vieneu-') or _voice_lower.startswith('vieneu3-'):
        if not _has_model_pack_entitlement():
            log_fn('   [KHOÁ] Giọng VieNeu cần addon Model Pack (+119.000đ) — nâng cấp tại vatoolskit.com. Tự chuyển sang Edge TTS...')
            return _render_edge_parallel(scenes, _get_fallback_edge_voice(voice), '+5%', log_fn, temp_dir)
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
        log_fn(f'''   TTS Engine: FPT.AI | Giong: {voice} ({FPTAI_VOICES.get(voice, '')})''')
        out = _render_fptai_sequential(scenes, voice, fptai_key, log_fn, temp_dir)
        if out and len(out) == len(nonempty):
            log_fn(f'''   Hoan tat TTS (FPT.AI): {len(out)}/{len(nonempty)} canh''')
            return out
        if strict_voice:
            log_fn('   [LOI] FPT.AI loi hoac het quota. Dang bat giu dung giong nen KHONG tu doi sang Edge TTS.')
            return []
        log_fn('   [WARN] FPT.AI het quota / loi. Doc lai TOAN BO bang Edge TTS...')
    else:
        if voice in FPTAI_VOICES and not fptai_key:
            if strict_voice:
                log_fn('   [LOI] Chua co FPT_AI_KEY cho giong FPT.AI da chon. Dang bat giu dung giong nen KHONG tu doi sang Edge TTS.')
                return []
            log_fn('   [WARN] FPT_AI_KEY chua set, dung Edge TTS')
        log_fn(f'''   TTS Engine: Edge TTS (song song) | Giong: {edge_fallback}''')
    out = _render_edge_parallel(scenes, edge_fallback, rate, log_fn, temp_dir)
    log_fn(f'''   Hoan tat TTS (Edge): {len(out)}/{len(nonempty)} canh''')
    if not out:
        log_fn('   [FALLBACK] Edge TTS that bai hoan toan. Thu Google TTS (du phong cuoi)...')
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
def _tts_openai(text, voice, api_key, out_path, log_fn=print):
    url = 'https://api.openai.com/v1/audio/speech'
    headers = {'Authorization': f'''Bearer {api_key}''', 'Content-Type': 'application/json'}
    json_data = {'model': 'tts-1', 'input': text, 'voice': voice}
    try:
        r = requests.post(url, headers=headers, json=json_data, timeout=60)
        if r.status_code == 200:
            with open(out_path, 'wb') as f:
                f.write(r.content)
            return True
        log_fn(f'''   [WARN] OpenAI TTS HTTP {r.status_code}: {r.text[:150]}''')
        return False
    except Exception as e:
        log_fn(f'''   [WARN] OpenAI TTS exception: {e}''')
        return False
def _render_openai_parallel(scenes, voice, api_key, log_fn, temp_dir):
    if not api_key:
        log_fn('   [LOI] Chua co OPENAI_API_KEY')
        return []
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    log_fn(f'''   Dang tao giong OpenAI {total} canh song song...''')
    async def _one(i, text):
        out_path = os.path.join(temp_dir, f'''vo_{i:04d}.mp3''')
        ok = await asyncio.to_thread(_tts_openai, text, voice, api_key, out_path, log_fn)
        return (i, out_path, ok)
    async def _run_all():
        tasks = [_one(i, s.get('voiceover_for_tts', s['voiceover']).strip()) for (i, s) in indexed]
        return await asyncio.gather(*tasks, return_exceptions=True)
    results = _run_coro(_run_all)
    result_map = _collect_results(results)
    return _build_out_scenes(indexed, result_map, 'openai', log_fn, '   [WARN] Canh {n}: OpenAI TTS that bai, bo qua', '   [WARN] Canh {n}: audio qua ngan, bo qua')
def _tts_elevenlabs(text, voice, api_key, out_path, log_fn=print):
    url = f'''https://api.elevenlabs.io/v1/text-to-speech/{voice}'''
    headers = {'xi-api-key': api_key, 'Content-Type': 'application/json', 'accept': 'audio/mpeg'}
    json_data = {'text': text, 'model_id': 'eleven_multilingual_v2', 'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}}
    try:
        r = requests.post(url, headers=headers, json=json_data, timeout=60)
        if r.status_code == 200:
            with open(out_path, 'wb') as f:
                f.write(r.content)
            return True
        log_fn(f'''   [WARN] ElevenLabs TTS HTTP {r.status_code}: {r.text[:150]}''')
        return False
    except Exception as e:
        log_fn(f'''   [WARN] ElevenLabs TTS exception: {e}''')
        return False
def _render_elevenlabs_parallel(scenes, voice, api_key, log_fn, temp_dir):
    if not api_key:
        log_fn('   [LOI] Chua co ELEVENLABS_API_KEY')
        return []
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    log_fn(f'''   Dang tao giong ElevenLabs {total} canh song song...''')
    async def _one(i, text):
        out_path = os.path.join(temp_dir, f'''vo_{i:04d}.mp3''')
        ok = await asyncio.to_thread(_tts_elevenlabs, text, voice, api_key, out_path, log_fn)
        return (i, out_path, ok)
    async def _run_all():
        tasks = [_one(i, s.get('voiceover_for_tts', s['voiceover']).strip()) for (i, s) in indexed]
        return await asyncio.gather(*tasks, return_exceptions=True)
    results = _run_coro(_run_all)
    result_map = _collect_results(results)
    return _build_out_scenes(indexed, result_map, 'elevenlabs', log_fn, '   [WARN] Canh {n}: ElevenLabs TTS that bai, bo qua', '   [WARN] Canh {n}: audio qua ngan, bo qua')
_EDGE_CHUNK = 30
_EDGE_RETRY = 2
def _render_edge_parallel(scenes, voice, rate, log_fn, temp_dir):
    try:
        import edge_tts
    except ImportError:
        log_fn('   [LOI] edge-tts chua cai: pip install edge-tts')
        return []
    os.makedirs(temp_dir, exist_ok=True)
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    log_fn(f'''   Dang tao giong {total} canh (chunk {_EDGE_CHUNK}/batch, retry {_EDGE_RETRY}x)...''')
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
            log_fn(f'''   [WARN] Edge TTS loi (canh dau): {last_err}''')
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
        log_fn(f'''   Edge TTS: {done}/{total} canh xong''')
    out_scenes = []
    for (i, scene) in indexed:
        if i not in result_map:
            log_fn(f'''   [WARN] Canh {i + 1}: Edge TTS that bai, bo qua''')
            continue
        dur = _audio_duration(result_map[i])
        if dur < 0.1:
            log_fn(f'''   [WARN] Canh {i + 1}: audio qua ngan ({dur:.2f}s), bo qua''')
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
                log_fn(f'''   [RETRY] FPT.AI canh {idx + 1}/{total} — thu lai lan {attempt + 2}/3...''')
                time.sleep(2 + attempt * 3)
        if not ok:
            log_fn(f'''   [WARN] FPT.AI dung o canh {idx + 1}/{total} (da thu 3 lan)''')
            return out_scenes
        if voice in FPTAI_ENHANCE_VOICES:
            _enhance_fptai_audio(mp3_path, log_fn)
        dur = _audio_duration(mp3_path)
        if dur < 0.1:
            log_fn(f'''   [WARN] Canh {idx + 1}: audio qua ngan, bo qua''')
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
        log_fn(f'''   [WARN] Hau ky am thanh loi (giu ban goc): {e}''')
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
            log_fn(f'''   [WARN] FPT.AI error: {data}''')
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
        log_fn(f'''   [WARN] FPT.AI exception: {e}''')
        return False
_VIETTEL_MAX_CONCURRENCY = 15
def _tts_viettel(text, voice, token, out_path, log_fn=print):
    url = 'https://viettelai.vn/tts/speech_synthesis'
    headers = {'accept': '*/*', 'Content-Type': 'application/json'}
    json_data = {'text': text, 'voice': voice, 'token': token, 'without_filter': False, 'speed': 1.0, 'tts_return_option': 3}
    try:
        r = requests.post(url, headers=headers, json=json_data, timeout=30)
        if r.status_code != 200:
            log_fn(f'''   [WARN] (VT) HTTP {r.status_code}: {r.text[:150]}''')
            return False
        content_type = r.headers.get('Content-Type', '')
        if 'audio' in content_type:
            with open(out_path, 'wb') as f:
                f.write(r.content)
            return True
        data = r.json()
        if data.get('code', 0) not in (0, 200, None):
            log_fn(f'''   [WARN] (VT) error: {data}''')
            return False
        audio_url = data.get('data') or ''
        if not audio_url:
            log_fn(f'''   [WARN] (VT): khong tim thay link audio trong response: {data}''')
            return False
        ar = requests.get(audio_url, timeout=30)
        if ar.status_code == 200 and len(ar.content) > 1000:
            with open(out_path, 'wb') as f:
                f.write(ar.content)
            return True
        log_fn(f'''   [WARN] (VT): tai file audio that bai (HTTP {ar.status_code})''')
        return False
    except Exception as e:
        log_fn(f'''   [WARN] (VT) exception: {e}''')
        return False
def _render_viettel_parallel(scenes, voice, token, log_fn, temp_dir):
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    log_fn(f'''   Đang tạo giọng (VT) {total} cảnh (song song, tối đa {_VIETTEL_MAX_CONCURRENCY} luồng)...''')
    async def _one(sem, i, text):
        async with sem:
            out_path = os.path.join(temp_dir, f'''vo_{i:04d}.mp3''')
            ok = await asyncio.to_thread(_tts_viettel, text, voice, token, out_path, log_fn)
            return (i, out_path, ok)
    async def _run_all():
        sem = asyncio.Semaphore(_VIETTEL_MAX_CONCURRENCY)
        tasks = [_one(sem, i, s.get('voiceover_for_tts', s['voiceover']).strip()) for (i, s) in indexed]
        return await asyncio.gather(*tasks, return_exceptions=True)
    results = _run_coro(_run_all)
    result_map = _collect_results(results)
    return _build_out_scenes(indexed, result_map, 'viettel', log_fn, '   [WARN] Cảnh {n}: (VT) thất bại, bỏ qua', '   [WARN] Cảnh {n}: audio quá ngắn, bỏ qua')
VI_PHONETIC_REPLACEMENTS = {'quay': 'kwai', 'tro': 'cher', 'phim': 'feem', 'thuyet': 'tweet', 'truyen': 'chuen', 'tich': 'tick', 'gi': 'zee', 'da': 'dah', 'cung': 'kung', 'tinh': 'ting', 'minh': 'ming', 'kenh': 'keng', 'hop': 'hop', 'chao': 'chow', 'mung': 'mung', 'ban': 'bahn', 'voi': 'veil', 'co': 'co', 'giau': 'zhou', 'nuoc': 'nook', 'mat': 'mat', 'lan': 'luhn', 'cuoi': 'coy', 'bien': 'bee-an', 'tap': 'tub', 'thoi': 'toy', 'su': 'suh', 'hinh': 'hing', 'mot': 'mote', 'vo': 'vo', 'hom': 'hohm', 'nay': 'nay', 'chung': 'choong', 'ta': 'ta', 'se': 'se', 'phan': 'fun', 'tac': 'tack', 'pham': 'fam', 'hap': 'hub', 'dan': 'zen', 'nam': 'nam', 'bac': 'bark', 'nu': 'new', 'nhe': 'nay', 'nhang': 'nyang', 'cam': 'kam', 'trong': 'chong', 'ro': 'roh', 'rang': 'rang', 'pho': 'foe', 'am': 'am', 'the': 'tay', 'hien': 'hee-an', 'tot': 'tot', 'khoe': 'kway', 'khoang': 'kwang', 'manh': 'mang', 'me': 'may', 'nghiem': 'neem', 'tuc': 'took', 'phu': 'foo', 'hanh': 'hang', 'dong': 'dong', 'kinh': 'king', 'di': 'zee', 'huyen': 'huyen', 'bi': 'bee', 'tre': 'chay', 'nang': 'nang', 'tuoi': 'tuoi', 'dien': 'zee-an', 'va': 'veil', 'giong': 'zong', 'doc': 'doc', 'he': 'hay', 'thong': 'tong', 'cau': 'cow', 'den': 'den', 'day': 'they', 'ngam': 'ngam', 'canh': 'kang', 'chu': 'choo', 'that': 'tat', 'von': 'von', 'nen': 'nen', 'som': 'sohm', 'nhan': 'yan', 'dieu': 'zeo', 'thi': 'tee', 'ca': 'kah', 'hai': 'high', 'ong': 'ong', 'cu': 'koo', 'ba': 'bah', 'thu': 'too', 'khang': 'kang', 'coo': 'coo', 'hoi': 'hoy', 'lay': 'lay', 'chan': 'chahn', 'viec': 'vee-ek', 'vat': 'vaht', 'ho': 'hoh', 'so': 'soh', 'de': 'deh', 'lam': 'lahm', 'ky': 'kee', 'luat': 'loo-at', 'tren': 'chen', 'het': 'heht', 'cong': 'cong', 'chi': 'chee', 'dua': 'zuah', 'may': 'may', 'man': 'mahn', 'giup': 'zup', 'tien': 'tee-an', 'xa': 'sah', 'gap': 'gahp', 'sep': 'sehp', 'chuc': 'chook', 'sinh': 'sing', 'nhat': 'nyaht', 'beo': 'beo', 'thich': 'tik', 'cach': 'kack', 'cai': 'kai', 'tao': 'tow', 'noi': 'noy', 'tai': 'tai', 'dung': 'zoong', 'hong': 'hong', 'gia': 'zah', 'tri': 'chee', 'san': 'sahn', 'lich': 'lik', 'phung': 'foong', 'phi': 'fee', 'ngan': 'ngahn', 'sach': 'sack', 'quoc': 'kwok', 'phong': 'fong', 'dap': 'dahp', 'ung': 'oong', 'vuot': 'vuot', 'qua': 'kwah', 'tieu': 'tew', 'chuan': 'chwan', 'danh': 'zang', 'moi': 'moy', 'quan': 'kwan', 'bao': 'bow', 'chac': 'chack', 'ly': 'lee', 'do': 'doh', 'dac': 'dahk', 'nhiem': 'nyee-am', 'sas': 'sas', 'gioi': 'zoy', 'ngo': 'ngoh', 'huan': 'hwan', 'luyen': 'luyen', 'loi': 'loy', 'khoi': 'koy', 'chay': 'chay'}
def remove_vietnamese_diacritics(text):
    import unicodedata
    if not text:
        return ''
    nkfd_form = unicodedata.normalize('NFKD', text)
    only_ascii = ''.join([c for c in nkfd_form if not unicodedata.combining(c)])
    return only_ascii.replace('đ', 'd').replace('Đ', 'D')
def convert_vietnamese_to_english_phonetic(text):
    import re
    if not text:
        return ''
    clean_text = remove_vietnamese_diacritics(text)
    words = clean_text.split()
    processed_words = []
    for w in words:
        m = re.match('^([^a-zA-Z0-9]*)(.*?)([^a-zA-Z0-9]*)$', w)
        if not m:
            processed_words.append(w)
            continue
        (pref, core, suff) = m.groups()
        if not core:
            processed_words.append(w)
            continue
        core_lower = core.lower()
        if core_lower in VI_PHONETIC_REPLACEMENTS:
            p = VI_PHONETIC_REPLACEMENTS[core_lower]
        else:
            p = core_lower
            p = p.replace('tr', 'ch')
            p = p.replace('kh', 'k')
            p = p.replace('ph', 'f')
            p = p.replace('th', 't')
            p = p.replace('gi', 'z')
            if p.startswith('d') and not p.startswith('đ'):
                p = 'z' + p[1:]
            p = p.replace('đ', 'd')
            p = p.replace('x', 's')
            p = p.replace('qu', 'kw')
            p = p.replace('nh', 'ny')
        if core[0].isupper():
            p = p.capitalize()
        processed_words.append(pref + p + suff)
    return ' '.join(processed_words)
def _tts_local_gptsovits(text, api_url, ref_audio_path, prompt_text, out_path, log_fn=print):
    url = api_url.strip().rstrip('/')
    import urllib.parse
    clean_text = convert_vietnamese_to_english_phonetic(text)
    clean_prompt = convert_vietnamese_to_english_phonetic(prompt_text)
    params = {'refer_wav_path': ref_audio_path, 'ref_audio_path': ref_audio_path, 'prompt_text': clean_prompt, 'prompt_language': 'en', 'prompt_lang': 'en', 'text': clean_text, 'text_language': 'en', 'text_lang': 'en'}
    try:
        post_url = url + '/'
        r = requests.post(post_url, json=params, timeout=120)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(out_path, 'wb') as f:
                f.write(r.content)
            return True
        get_url = url + '/?' + urllib.parse.urlencode(params)
        r_get = requests.get(get_url, timeout=120)
        if r_get.status_code == 200 and len(r_get.content) > 1000:
            with open(out_path, 'wb') as f:
                f.write(r_get.content)
            return True
        log_fn(f'''   [WARN] Phản hồi máy chủ lồng tiếng offline HTTP {r.status_code} (POST)''')
        return False
    except requests.exceptions.ConnectionError:
        log_fn('   [LỖI] Không kết nối được dịch vụ lồng tiếng offline — vui lòng bật máy chủ âm thanh trước.')
        return False
    except Exception as e:
        log_fn(f'''   [LỖI] Dịch vụ lồng tiếng offline lỗi: {e}''')
        return False
def _render_local_gptsovits_parallel(scenes, api_url, ref_audio_path, prompt_text, log_fn, temp_dir):
    fallback_voice = _get_fallback_edge_voice(os.path.basename(ref_audio_path or ''))
    if not ref_audio_path or not os.path.exists(ref_audio_path):
        log_fn('   [LOI] Thieu file ghi am mau (.wav) hoac file khong ton tai')
        log_fn(f'''   => Tu dong chuyen sang Edge TTS ({fallback_voice})...''')
        return _render_edge_parallel(scenes, fallback_voice, '+5%', log_fn, temp_dir)
    if not prompt_text:
        log_fn('   [WARN] Thieu van ban mau, chat luong clone co the thap hon')
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    log_fn(f'''   Nhân bản offline v1: xử lý tuần tự {total} cảnh...''')
    out_scenes = []
    consecutive_fail = 0
    FAIL_LIMIT = 3
    done_idx = set()
    for (i, (idx, scene)) in enumerate(indexed):
        text = scene.get('voiceover_for_tts', scene['voiceover']).strip()
        out_path = os.path.join(temp_dir, f'''vo_{idx:04d}.wav''')
        log_fn(f'''   [{idx + 1}/{total}] Dang tao giong canh {i + 1}...''')
        ok = _tts_local_gptsovits(text, api_url, ref_audio_path, prompt_text, out_path, log_fn)
        if not ok or not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
            log_fn(f'''   [WARN] Cảnh {i + 1}: Lỗi nhân bản offline v1 → Tự động chuyển sang giọng dự phòng...''')
            edge_res = _render_edge_parallel([scene], fallback_voice, '+5%', log_fn, temp_dir)
            if edge_res:
                out_scenes.extend(edge_res)
                done_idx.add(idx)
            consecutive_fail += 1
            if consecutive_fail >= FAIL_LIMIT:
                log_fn(f'''   [!] Dịch vụ lồng tiếng offline lỗi {FAIL_LIMIT} lần liên tiếp. Dịch vụ có thể đã dừng.''')
                log_fn(f'''   => Tu dong chuyen toan bo canh con lai sang Edge TTS ({fallback_voice})...''')
                remaining = [sc for (j, sc) in indexed if j not in done_idx]
                edge_out = _render_edge_parallel(remaining, fallback_voice, '+5%', log_fn, temp_dir)
                log_fn(f'''   Edge TTS fallback: {len(edge_out)} canh thanh cong''')
                out_scenes.extend(edge_out)
                break
            continue
        consecutive_fail = 0
        dur = _audio_duration(out_path)
        if dur < 0.1:
            log_fn(f'''   [WARN] Canh {i + 1}: audio qua ngan ({dur:.2f}s), bo qua''')
            continue
        scene2 = dict(scene)
        scene2['tts_path'] = out_path
        scene2['tts_duration'] = dur
        scene2['_tts_engine_used'] = 'gptsovits'
        out_scenes.append(scene2)
        done_idx.add(idx)
    out_scenes.sort(key=lambda s: s.get('_original_index', 0))
    return out_scenes
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
if getattr(_sys_tts, 'frozen', False):
    _XTTS_RUNTIME_PYTHON = _sys_tts.executable
    _XTTS_USE_WORKER_ARG = True
else:
    _GPT_SOVITS_PYTHON = 'D:\\AutoReview_Studio\\GPT-SoVITS\\runtime\\python.exe'
    _XTTS_RUNTIME_PYTHON = _GPT_SOVITS_PYTHON if os.path.exists(_GPT_SOVITS_PYTHON) else _sys_tts.executable
    _XTTS_USE_WORKER_ARG = False
def _get_xtts_worker_script():
    if getattr(_sys_tts, 'frozen', False):
        return os.path.join(_sys_tts._MEIPASS, 'xtts_worker.py')
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'workers', 'xtts_worker.py')
_XTTS_WORKER_SCRIPT = _get_xtts_worker_script()
_OWN_XTTS_MODEL_DEV = 'D:\\AutoReview_Studio\\models\\vixtts'
def _get_xtts_model_dir():
    if getattr(_sys_tts, 'frozen', False):
        model_root = _read_model_pack_root()
        if model_root:
            portable = os.path.join(model_root, 'vixtts')
            if os.path.exists(os.path.join(portable, 'model.pth')):
                return portable
        portable = os.path.join(os.path.dirname(_sys_tts.executable), 'models', 'vixtts')
        if os.path.exists(os.path.join(portable, 'model.pth')):
            return portable
        return None
    if os.path.exists(os.path.join(_OWN_XTTS_MODEL_DEV, 'model.pth')):
        return _OWN_XTTS_MODEL_DEV
    edric = 'D:\\edric\\EdricAiTextToSpeech\\Data\\_internal\\data'
    if os.path.exists(os.path.join(edric, 'model.pth')):
        return edric
    return None
def _render_xtts_sequential(scenes, ref_audio_path, log_fn, temp_dir, allow_fallback=True, cpu_retry_done=False, _retry_done=False):
    import json as _json
    _fallback_edge_voice = _get_fallback_edge_voice(os.path.basename(ref_audio_path or ''))
    def _edge_gtts_fallback(scenes_to_retry):
        if not allow_fallback:
            log_fn('   [LOI] Dang bat giu dung giong nen KHONG tu doi sang Edge/Google TTS.')
            return []
        log_fn('   [FALLBACK] Chuyển toàn bộ sang Edge TTS online...')
        out = _render_edge_parallel(scenes_to_retry, _fallback_edge_voice, '+5%', log_fn, temp_dir)
        if out:
            return out
        log_fn('   [FALLBACK] Edge TTS cũng thất bại → thử Google TTS...')
        return _render_gtts_fallback(scenes_to_retry, log_fn, temp_dir)
    if not ref_audio_path or not os.path.exists(ref_audio_path):
        log_fn('   [LOI] Thieu file ghi am mau (.wav) — chuyen sang Edge TTS...')
        return _edge_gtts_fallback(scenes)
    ref_audio_path = _trim_ref_audio(ref_audio_path, temp_dir, log_fn)
    model_dir = _get_xtts_model_dir()
    if not model_dir:
        if getattr(_sys_tts, 'frozen', False):
            log_fn('   [LỖI] Chưa cài Model Pack Offline v2 — giải nén ModelPack_v1.0.zip vào thư mục AutoReviewTool/')
            log_fn('   => Ổ chứa AutoReviewTool hết dung lượng? Có thể giải nén ModelPack sang Ổ ĐĨA KHÁC (vd D:\\ModelPack hoặc E:\\ModelPack) — tool tự tìm thấy, không cần cùng ổ với exe.')
        else:
            log_fn('   [LỖI] Không tìm thấy model nhân bản offline v2 — tự chuyển sang giọng online...')
        return _edge_gtts_fallback(scenes)
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    if not indexed:
        return []
    log_fn(f'''   Khởi tạo bộ nhân bản offline v2 cho {total} cảnh...''')
    batch = [{'text': s.get('voiceover_for_tts', s['voiceover']).strip(), 'out': os.path.join(temp_dir, f'''vo_{i:04d}.wav''')} for (i, s) in indexed]
    batch_file = os.path.join(temp_dir, '_xtts_batch.json')
    with open(batch_file, 'w', encoding='utf-8') as bf:
        _json.dump(batch, bf, ensure_ascii=False)
    timeout_secs = max(300, 90 + total * 30)
    if getattr(_sys_tts, 'frozen', False):
        cmd = [_XTTS_RUNTIME_PYTHON, '--xtts-worker', batch_file, ref_audio_path, model_dir]
    else:
        cmd = [_XTTS_RUNTIME_PYTHON, '-W', 'ignore', _XTTS_WORKER_SCRIPT, batch_file, ref_audio_path, model_dir]
    env = os.environ.copy()
    env['PYTHONWARNINGS'] = 'ignore'
    env['TRANSFORMERS_VERBOSITY'] = 'error'
    timed_out = False
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE, env=env)
        register_process(proc)
        deadline = time.time() + timeout_secs
        try:
            for line in proc.stdout:
                if time.time() > deadline:
                    timed_out = True
                    proc.kill()
                    log_fn('   [WARN] Quá thời gian xử lý nhân bản offline v2 — đã giải phóng tiến trình')
                    break
                line = line.rstrip()
                if not line:
                    continue
                low = line.lower()
                if any((w in low for w in ('futurewarning:', 'userwarning:', 'deprecationwarning:', 'runtimewarning:'))):
                    continue
                if 'warnings.warn(' in line:
                    continue
                if any((p in low for p in ('site-packages\\transformers', 'site-packages\\torch', 'site-packages\\tts'))):
                    continue
                log_fn(f'''   {line}''')
            proc.wait()
        finally:
            unregister_process(proc)
    except Exception as e:
        log_fn(f'''   [WARN] Lỗi nhân bản offline v2: {e}''')
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
        scene2['_tts_engine_used'] = 'xtts'
        out_scenes.append(scene2)
    if n_suspect:
        log_fn(f'''   [WARN] {n_suspect} cảnh có audio bất thường (nghi bị cắt ngang/lỗi) — bỏ qua''')
    if not timed_out and not out_scenes and not cpu_retry_done:
        log_fn('   [XTTS] GPU chưa ra audio ổn định, thử lại 1 lần bằng CPU để giữ đúng giọng...')
        old_cuda = os.environ.get('CUDA_VISIBLE_DEVICES')
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        try:
            return _render_xtts_sequential(scenes, ref_audio_path, log_fn, temp_dir, allow_fallback=allow_fallback, cpu_retry_done=True, _retry_done=_retry_done)
        finally:
            if old_cuda is None:
                os.environ.pop('CUDA_VISIBLE_DEVICES', None)
            else:
                os.environ['CUDA_VISIBLE_DEVICES'] = old_cuda
    log_fn(f'''   Hoàn tất nhân bản offline v2: {len(out_scenes)}/{total} cảnh thành công''')
    if failed_scenes and not _retry_done:
        log_fn(f'''   [RETRY] {len(failed_scenes)} cảnh lỗi — thử lại 1 lần bằng chính giọng đã clone để giữ nhất quán...''')
        retry_res = _render_xtts_sequential(failed_scenes, ref_audio_path, log_fn, temp_dir, allow_fallback=False, cpu_retry_done=True, _retry_done=True)
        got_idx = {s.get('_original_index') for s in retry_res}
        out_scenes.extend(retry_res)
        failed_scenes = [s for s in failed_scenes if s.get('_original_index') not in got_idx]
    if failed_scenes:
        if allow_fallback:
            log_fn(f'''   [FALLBACK] {len(failed_scenes)} cảnh vẫn lỗi sau khi thử lại → đổi sang Edge TTS (giọng khác) bổ sung...''')
            edge_res = _render_edge_parallel(failed_scenes, _fallback_edge_voice, '+5%', log_fn, temp_dir)
            if not edge_res:
                edge_res = _render_gtts_fallback(failed_scenes, log_fn, temp_dir)
            out_scenes.extend(edge_res or [])
        else:
            log_fn(f'''   [LOI] {len(failed_scenes)} cảnh XTTS thất bại và đang bật giữ đúng giọng nên không dùng fallback.''')
    out_scenes.sort(key=lambda s: s.get('_original_index', 0))
    if out_scenes and len(out_scenes) >= total * 0.5:
        return out_scenes
    if allow_fallback:
        log_fn('   [WARN] Tỉ lệ thất bại cao — chuyển toàn bộ sang giọng online...')
        return _edge_gtts_fallback(scenes)
    if not _retry_done:
        log_fn('   [LOI] XTTS tỉ lệ thành công quá thấp và đang bật giữ đúng giọng nên dừng tại đây.')
    return out_scenes
_VIENEU_PYTHON = 'C:\\Users\\Admin\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe'
_VIENEU_DEV_HUB = 'D:\\AutoReview_Studio\\models\\vieneu\\hub'
_VIENEU_VOICE_MAP = {'binh-an': 'Bình An', 'xuan-vinh': 'Xuân Vĩnh', 'ngoc-lan': 'Ngọc Lan', 'my-duyen': 'Mỹ Duyên', 'truc-ly': 'Trúc Ly', 'ngoc-linh': 'Ngọc Linh', 'gia-bao': 'Gia Bảo', 'thai-son': 'Thái Sơn', 'duc-tri': 'Đức Trí', 'trong-huu': 'Trọng Hữu', 'clone': 'clone'}
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
        r = run_subprocess([FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path], timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
def _get_vieneu3_builtin_ref(vn_voice):
    fname = _VIENEU3_BUILTIN_REF.get(vn_voice)
    if not fname:
        return ''
    from .utils import voice_samples_dir
    path = os.path.join(voice_samples_dir('vieneu3_ref'), fname)
    if os.path.exists(path):
        return path
    fallback_name = fname.replace('-', '_')
    fallback_path = os.path.join(voice_samples_dir(), fallback_name)
    if os.path.exists(fallback_path):
        return fallback_path
    return ''
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
        log_fn(f'''   [WARN] Giọng VieNeu không hợp lệ: {vn_voice} — dùng Bình An''')
        vn_voice = 'binh-an'
    (base_cmd, hf_home, cmd_ok) = _get_vieneu_cmd()
    if not cmd_ok:
        if getattr(_sys_tts, 'frozen', False):
            log_fn('   [LỖI] Chưa cài Model Pack VieNeu.')
            log_fn('   Giải nén ModelPack vào thư mục AutoReviewTool/ để dùng giọng VieNeu.')
            log_fn('   => Ổ chứa AutoReviewTool hết dung lượng? Có thể giải nén ModelPack sang Ổ ĐĨA KHÁC (vd D:\\ModelPack hoặc E:\\ModelPack) — tool tự tìm thấy, không cần cùng ổ với exe.')
        else:
            log_fn('   [LỖI] Không tìm thấy vieneu_worker.exe hoặc Python 3.14.')
        if not allow_fallback:
            return []
        log_fn('   => Tự chuyển sang Edge TTS...')
        return _full_edge_fallback()
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    if not indexed:
        return []
    os.makedirs(temp_dir, exist_ok=True)
    batch = [{'text': s.get('voiceover_for_tts', s['voiceover']).strip(), 'out': os.path.join(temp_dir, f'''vo_{i:04d}.wav''')} for (i, s) in indexed]
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
        log_fn('   [WARN] gTTS chua cai (pip install gTTS) — bo qua fallback nay')
        return []
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    if not indexed:
        return []
    log_fn(f'''   Google TTS: xu ly {total} canh...''')
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
                log_fn(f'''   [WARN] Google TTS canh {i + 1}: {e}''')
    log_fn(f'''   Google TTS: {len(out_scenes)}/{total} canh thanh cong''')
    return out_scenes
def _is_plausible_tts_duration(text, dur):
    n_chars = len(text)
    if n_chars == 0:
        return dur < 0.5
    min_dur = n_chars / 22.0
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
        r = run_subprocess(cmd, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
        r = run_subprocess([FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path], timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(r.stdout.strip())
    except Exception:
        return 0.0
