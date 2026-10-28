

"""
Tạo giọng đọc từng cảnh: Edge TTS (miễn phí, song song), CapCut (gom gói, song song), FPT.AI (tuần tự, tránh giới hạn tần suất),
VieNeu / VieNeu3 (chạy cục bộ). Chọn giọng nào đọc đúng giọng đó — lỗi thì báo lỗi, KHÔNG tự đổi sang giọng / engine khác.
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
_VI_ONES = ['không', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín']


def _vi_lt1000(x, full=False):
    """0–999 → chữ. full=True: nhóm đứng sau nhóm lớn hơn (vd 1.005.000) → đọc đủ "không trăm lẻ năm"."""
    (h, r) = divmod(x, 100)
    (t, u) = divmod(r, 10)
    out = []
    if h or full:
        out.append(_VI_ONES[h] + ' trăm')
    if t == 0:
        if u:
            out.append(('lẻ ' if out else '') + _VI_ONES[u])
    elif t == 1:
        out.append('mười' + ('' if u == 0 else ' lăm' if u == 5 else ' ' + _VI_ONES[u]))
    else:
        tail = {0: '', 1: ' mốt', 4: ' tư', 5: ' lăm'}.get(u, ' ' + _VI_ONES[u])
        out.append(_VI_ONES[t] + ' mươi' + tail)
    return ' '.join(out)


def _vi_number_to_words(n):
    """Số nguyên → chữ đúng cách đọc: 2024 → hai nghìn không trăm hai mươi tư; 1005000 → một triệu không trăm lẻ năm nghìn."""
    n = int(n)
    if n == 0:
        return 'không'
    if n < 0:
        return 'âm ' + _vi_number_to_words(-n)
    if n >= 10 ** 12:
        return ' '.join(_VI_ONES[int(d)] for d in str(n))
    groups = []
    for (div, unit) in ((10 ** 9, 'tỷ'), (10 ** 6, 'triệu'), (1000, 'nghìn'), (1, '')):
        (q, n) = divmod(n, div)
        groups.append((q, unit))
    out = []
    for (q, unit) in groups:
        if q == 0:
            continue
        out.append((_vi_lt1000(q, full=bool(out)) + (' ' + unit if unit else '')).strip())
    return ' '.join(out)


def _vi_digits(s):
    return ' '.join(_VI_ONES[int(d)] for d in s if d.isdigit())


def _vi_decimal(int_part, frac):
    """2,5 → hai phẩy năm · 3,14 → ba phẩy mười bốn · 3,05 → ba phẩy không năm · 2,500 → hai phẩy năm."""
    frac = frac.rstrip('0')
    words = _vi_number_to_words(int(int_part or '0'))
    if not frac:
        return words
    if len(frac) <= 2 and not frac.startswith('0'):
        return words + ' phẩy ' + _vi_number_to_words(int(frac))
    return words + ' phẩy ' + _vi_digits(frac)


def replace_numbers_with_words(text):
    """Đổi số trong câu sang chữ để giọng đọc đúng (phụ đề giữ nguyên chữ số — chỉ dùng cho lời đọc).
    0912345678 → đọc từng số · 1,2,3 → một, hai, ba · 2,5 / 2,500 → hai phẩy năm (dấu phẩy thập phân kiểu Việt)
    1.005.000 → một triệu không trăm lẻ năm nghìn · 2024 → hai nghìn không trăm hai mươi tư
    50% → năm mươi phần trăm · 10:30 → mười giờ ba mươi."""
    if not text:
        return ''
    import re

    def time_(m):
        (h, mi) = (int(m.group(1)), int(m.group(2)))
        if h > 24 or mi > 59:
            return m.group(0)
        sec = m.group(3)
        out = _vi_number_to_words(h) + ' giờ' + ('' if mi == 0 and not sec else ' ' + _vi_number_to_words(mi) + (' phút' if sec else ''))
        if sec:
            out += ' ' + _vi_number_to_words(int(sec)) + ' giây'
        return out
    text = re.sub(r'(?<![\d.,:])(\d{1,2}):(\d{2})(?::(\d{2}))?(?![\d:])', time_, text)

    def num(raw):
        if re.fullmatch(r'0\d{2,}', raw) or re.fullmatch(r'\d{9,}', raw):        # số điện thoại / mã số → đọc từng số
            return _vi_digits(raw)
        if '.' in raw and ',' in raw:                                            # 1.234,5 (kiểu Việt)
            (a, b) = raw.rsplit(',', 1)
            return _vi_decimal(a.replace('.', ''), b) if all(len(p) == 3 for p in a.split('.')[1:]) else _vi_digits(raw)
        if ',' in raw:
            parts = raw.split(',')
            if len(parts) == 2:
                return _vi_decimal(parts[0], parts[1])                           # dấu phẩy = thập phân
            return ', '.join(_vi_number_to_words(int(p)) for p in parts)         # 1,2,3 → liệt kê
        if '.' in raw:
            parts = raw.split('.')
            if all(len(p) == 3 for p in parts[1:]):
                return _vi_number_to_words(int(raw.replace('.', '')))            # 1.005.000 → hàng nghìn
            if len(parts) == 2:
                return _vi_decimal(parts[0], parts[1])                           # 1.5 → một phẩy năm
            return ', '.join(_vi_number_to_words(int(p)) for p in parts)         # 1.2.3 (mục lục) → liệt kê
        return _vi_number_to_words(int(raw))

    def repl(m):
        try:
            words = num(m.group(1))
        except Exception:
            return m.group(0)
        return words + (' phần trăm' if m.group(2) else '')
    return re.sub(r'(\d+(?:[.,]\d+)*)(\s*%)?', repl, text)
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
POLISH_RATE = 48000
POLISH_TARGET_DB = -16.5          # độ to trung bình phần có tiếng (RMS) → ≈ -17…-18 LUFS cho giọng nói
POLISH_PEAK = 0.89                # đỉnh tối đa -1 dBFS


def polish_tts(scenes, log_fn=print):
    """Chuẩn hoá MỌI file giọng (Edge, CapCut, FPT, VieNeu, gTTS…) trước khi dùng:
    - cắt khoảng lặng đầu / cuối (chừa 30ms đầu, 100ms cuối): engine hay chèn 0.1–0.8s lặng → lời vào trễ so với miệng,
      độ dài giả kéo giãn hình / tua nhanh giọng không cần thiết, phụ đề chia sai;
    - cân độ to về cùng một mức (giới hạn đỉnh -1 dBFS): câu đọc lại bằng engine / giọng khác không to nhỏ lệch câu bên cạnh.
    Ghi <tên>_n.wav (48kHz mono), cập nhật tts_path / tts_duration. File lỗi → giữ nguyên. → scenes (sửa tại chỗ)."""
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
    import wave as _wave

    from core import cancel

    def one(sc):
        src = sc.get('tts_path')
        if not src or not os.path.isfile(src) or src.endswith('_n.wav') or cancel.requested():
            return False
        r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-i', src, '-ac', '1', '-ar', str(POLISH_RATE), '-f', 's16le', '-'],
                           capture_output=True, creationflags=_HIDE)
        x = np.frombuffer(r.stdout, '<i2').astype(np.float32) / 32768.0 if r.returncode == 0 else np.zeros(0, np.float32)
        hop = POLISH_RATE // 100                 # khung 10ms
        if len(x) < hop * 5:
            return False
        fr = x[:len(x) // hop * hop].reshape(-1, hop)
        db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
        act = np.where(db > max(-50.0, db.max() - 45.0))[0]
        if not len(act):
            return False
        a = max(0, act[0] * hop - int(0.03 * POLISH_RATE))
        b = min(len(x), (act[-1] + 1) * hop + int(0.10 * POLISH_RATE))
        y = x[a:b]
        rms = np.sqrt((fr[act] ** 2).mean()) + 1e-9
        gain = 10 ** ((POLISH_TARGET_DB - 20 * np.log10(rms)) / 20)
        gain = float(min(max(gain, 10 ** (-12 / 20)), 10 ** (15 / 20)))
        peak = float(np.abs(y).max()) + 1e-9
        gain = min(gain, POLISH_PEAK / peak)
        y = np.clip(y * gain, -1.0, 1.0)
        out = os.path.splitext(src)[0] + '_n.wav'
        with _wave.open(out, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(POLISH_RATE)
            w.writeframes((y * 32767).astype('<i2').tobytes())
        sc['tts_path'] = out
        sc['tts_duration'] = len(y) / POLISH_RATE
        return True
    todo = [sc for sc in scenes or [] if sc.get('tts_path')]
    if not todo:
        return scenes
    with ThreadPoolExecutor(min(6, len(todo))) as ex:
        ok = sum(1 for r in ex.map(lambda sc: _safe(one, sc), todo) if r)
    if ok:
        log_fn(f'   Chuẩn hoá giọng: cắt lặng đầu / cuối + cân âm lượng {ok}/{len(todo)} câu')
    return scenes


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return False


def generate_tts_per_scene(scenes, voice, temp_dir, rate='+5%', log_fn=print, fptai_key=None, ref_audio_path='', strict_voice=False, gpu_timeout=None, **kw):
    """Tạo giọng từng câu (mọi engine) rồi chuẩn hoá (cắt lặng + cân âm lượng) — xem polish_tts."""
    from core import cancel
    cancel.check()                           # đã bấm Dừng trước khi bắt đầu đọc
    out = _generate_tts_raw(scenes, voice, temp_dir, rate, log_fn, fptai_key, ref_audio_path, strict_voice, gpu_timeout, **kw)
    for o in out or []:
        o['tts_text'] = o.get('voiceover', '')    # đúng câu đã đọc — sửa lời sau đó mà chưa tạo lại giọng thì biết là lệch
    return polish_tts(out, log_fn) if out else out


def _generate_tts_raw(scenes, voice, temp_dir, rate='+5%', log_fn=print, fptai_key=None, ref_audio_path='', strict_voice=False, gpu_timeout=None, **_unused):
    os.makedirs(temp_dir, exist_ok=True)
    for (idx, s) in enumerate(scenes):
        # người gọi đã ghi chỉ số cảnh (vd tự hậu kỳ gửi lô cảnh [3, 7]) → giữ nguyên, ghi đè thì giọng gắn nhầm cảnh
        s.setdefault('_original_index', idx)
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
        out = _render_capcut_parallel(scenes, cc_voice, cookie, log_fn, temp_dir, rate=rate)
        if out and len(out) == len(nonempty):
            log_fn(f'''   Hoàn tất TTS (CapCut): {len(out)}/{len(nonempty)} cảnh''')
            return out
        log_fn(f'''   [LỖI] CapCut: {len(out or [])}/{len(nonempty)} cảnh có giọng — không đổi sang giọng khác'''
               + ('' if cookie else ' (lỗi lặp lại thì thử dán cookie CapCut ở Cài đặt)'))
        return out or []
    _voice_lower = voice.lower()
    if _voice_lower.startswith('vieneu-') or _voice_lower.startswith('vieneu3-'):
        if _voice_lower.startswith('vieneu3-'):
            vn_voice = _voice_lower
        else:
            vn_voice = voice[len('vieneu-'):].lower()
        log_fn(f'''   Công nghệ TTS: VieNeu | Giọng: {vn_voice}''')
        if not _acquire_gpu_lock(log_fn, gpu_timeout, '   [GPU] Đang chờ GPU giải phóng (tiến trình khác đang xử lý)...'):
            return []
        try:
            out = _render_vieneu_sequential(scenes, vn_voice, ref_audio_path, log_fn, temp_dir, allow_fallback=False)
        finally:
            _LOCAL_GPU_LOCK.release()
        out = out or []
        log_fn(f'''   Hoàn tất TTS (VieNeu): {len(out)}/{len(nonempty)} cảnh''')
        return out
    if voice in FPTAI_VOICES:
        if not fptai_key:
            log_fn('   [LỖI] Chưa có FPT_API_KEY cho giọng FPT.AI đã chọn (Cài đặt → Key giọng đọc) — không đổi sang giọng khác')
            return []
        log_fn(f'''   TTS Engine: FPT.AI | Giọng: {voice} ({FPTAI_VOICES.get(voice, '')})''')
        out = _render_fptai_sequential(scenes, voice, fptai_key, log_fn, temp_dir)
        if out and len(out) == len(nonempty):
            log_fn(f'''   Hoàn tất TTS (FPT.AI): {len(out)}/{len(nonempty)} cảnh''')
            return out
        log_fn(f'''   [LỖI] FPT.AI: {len(out or [])}/{len(nonempty)} cảnh có giọng (lỗi / hết quota) — không đổi sang giọng khác''')
        return out or []
    if voice not in EDGE_VOICES:
        log_fn(f'''   [LỖI] Giọng "{voice}" không có trong danh sách — chọn lại giọng đọc''')
        return []
    log_fn(f'''   TTS Engine: Edge TTS (song song) | Giọng: {voice}''')
    out = _render_edge_parallel(scenes, voice, rate, log_fn, temp_dir)
    log_fn(f'''   Hoàn tất TTS (Edge): {len(out)}/{len(nonempty)} cảnh''')
    return out
def _clear_outputs(paths):
    """Xoá file giọng cũ trùng tên trước khi tạo (vo_0000…): tên file cố định theo số thứ tự câu — chạy lại / "Tiếp tục"
    sau khi sửa, đổi thứ tự kịch bản mà câu nào tạo lỗi thì không được nhặt nhầm file giọng CŨ (lời cũ, có khi của câu khác)."""
    for p in paths:
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


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
            if dur <= 0 and result_map[i] in _PROBE_ERR:     # file hỏng / không đọc được → báo đúng lỗi, không ghi "quá ngắn"
                log_fn(f'   [WARN] Cảnh {i + 1}: {_short_reason(result_map[i], dur)} — bỏ qua')
            else:
                log_fn(short_msg.format(n=i + 1, dur=dur))
            continue
        scene2 = dict(scene)
        scene2['tts_path'] = result_map[i]
        scene2['tts_duration'] = dur
        scene2['_tts_engine_used'] = engine
        out_scenes.append(scene2)
    return out_scenes
_EDGE_CHUNK = 8          # gửi dồn 30 câu cùng lúc → Edge chặn tạm ("No audio was received") hàng loạt câu
_EDGE_RETRY = 4
_EDGE_CONNECT_TIMEOUT = 40


def _render_edge_parallel(scenes, voice, rate, log_fn, temp_dir):
    """Chỉ đọc bằng Edge (không đổi sang engine khác) — câu lỗi thử lại bằng chính Edge."""
    retries = _EDGE_RETRY
    try:
        import edge_tts
    except ImportError:
        log_fn('   [LỖI] Chưa cài edge-tts: pip install edge-tts')
        return []
    os.makedirs(temp_dir, exist_ok=True)
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    total = len(indexed)
    _clear_outputs([os.path.join(temp_dir, f'vo_{i:04d}.mp3') for (i, _) in indexed])
    log_fn(f'''   Đang tạo giọng {total} cảnh (chunk {_EDGE_CHUNK}/batch, thử lại {retries}x)...''')
    edge_errs = {}

    async def _one(i, text):
        out_path = os.path.join(temp_dir, f'''vo_{i:04d}.mp3''')
        last_err = None
        # Edge hay không trả âm thanh với câu cảm thán rất ngắn ("Hả?", "Ơ!") → lần thử sau đổi cách viết (bỏ dấu hỏi / thêm dấu chấm)
        base = text.rstrip('?!.…, ').strip() or text
        variants = [text, text, base + '.', base, base + '...']
        from core import cancel
        for attempt in range(retries + 1):
            if cancel.requested():
                break
            try:
                # mặc định chờ kết nối 10s — mạng chậm bắt tay với máy chủ Edge hay quá 10s → bị cắt (ServerTimeoutError /
                # "No audio was received"); nới 40s thì hết lỗi
                comm = edge_tts.Communicate(variants[min(attempt, len(variants) - 1)], voice, rate=rate,
                                            connect_timeout=_EDGE_CONNECT_TIMEOUT, receive_timeout=60)
                await comm.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    return (i, out_path, True)
            except Exception as _e:
                last_err = _e
            if attempt < retries:
                import random
                await asyncio.sleep(2.0 ** (attempt + 1) + random.uniform(0, 1.5))   # chờ tăng dần 2 → 4 → 8 → 16s cho Edge hồi
        if last_err:
            edge_errs[i] = str(last_err)[:160]  # lý do lỗi THẬT của từng cảnh (trước chỉ ghi của cảnh đầu)
        return (i, out_path, False)
    result_map = {}
    chunks = [indexed[k:k + _EDGE_CHUNK] for k in range(0, len(indexed), _EDGE_CHUNK)]
    async def _run_chunk(chunk):
        tasks = [_one(i, s.get('voiceover_for_tts', s['voiceover']).strip()) for (i, s) in chunk]
        return await asyncio.gather(*tasks, return_exceptions=True)
    done = 0
    from core import cancel
    for (ch_idx, chunk) in enumerate(chunks):
        cancel.check()                       # bấm Dừng → ngừng ngay giữa các lô câu
        results = _run_coro(lambda chunk=chunk: _run_chunk(chunk))
        result_map.update(_collect_results(results, check_file=False))
        done += len(chunk)
        log_fn(f'''   Edge TTS: {done}/{total} cảnh xong''')
    out_scenes = []
    for (i, scene) in indexed:
        if i not in result_map:
            log_fn(f'''   [WARN] Cảnh {i + 1}: Edge TTS thất bại — {edge_errs.get(i, 'không có âm thanh trả về')}''')
            continue
        dur = _audio_duration(result_map[i])
        if dur < 0.1:
            log_fn(f'''   [WARN] Cảnh {i + 1}: {_short_reason(result_map[i], dur)} — bỏ qua''')
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
    from core import cancel
    for (i, scene) in enumerate(scenes):
        cancel.check()
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
            log_fn(f'''   [WARN] Cảnh {idx + 1}: {_short_reason(mp3_path, dur)} — bỏ qua''')
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


def _rate_to_speed(rate):
    """'+10%' / '-5%' (kiểu Edge) → hệ số tốc độ 1.10 / 0.95. Mặc định '+5%' của Edge KHÔNG áp cho engine khác (giữ nguyên
    tốc độ quen thuộc của CapCut) — chỉ khi người gọi chỉ định tốc độ khác."""
    try:
        r = str(rate or '').strip()
        if not r or r == '+5%':
            return 1.0
        return max(0.5, min(2.0, 1.0 + float(r.rstrip('%')) / 100.0))
    except (TypeError, ValueError):
        return 1.0


def _render_capcut_parallel(scenes, voice, cookie, log_fn, temp_dir, rate=''):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from core.capcut_tts import CapcutBatchTooBig, CapcutError, synthesize_batch
    indexed = [(s.get('_original_index', i), s) for (i, s) in enumerate(scenes) if (s.get('voiceover') or '').strip()]
    items = [(i, s.get('voiceover_for_tts', s['voiceover']).strip(), os.path.join(temp_dir, f'vo_{i:04d}.mp3')) for (i, s) in indexed]
    _clear_outputs([p for (_, _, p) in items])
    batches = _capcut_batches(items)
    log_fn(f'   Đang tạo giọng CapCut {len(items)} cảnh ({len(batches)} gói, song song {_CAPCUT_MAX_CONCURRENCY} luồng)...')
    (ok, errors, lock, done) = (set(), [], threading.Lock(), [0])

    def _send(batch):
        """Gửi 1 gói; bị cắt vì quá dài thì chia đôi gửi lại. → chỉ số các cảnh thành công."""
        try:
            res = synthesize_batch([(t, p) for (_, t, p) in batch], voice, cookie, speed=_rate_to_speed(rate))
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

    from core import cancel

    def _job(batch):
        if cancel.requested():               # bấm Dừng → các gói còn chờ trong hàng bỏ luôn
            return
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
        cancel.check()
        failed = [it for it in items if it[0] not in ok]
        if not failed:
            break
        log_fn(f'   CapCut lỗi {len(failed)} cảnh — gửi lại (lượt {attempt + 1})...')
        if cancel.sleep(3):
            cancel.check()
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
        clean_text = re.sub('\\s+', ' ', (s['voiceover'] or '').replace('||', ' ')).strip()
        s['voiceover_for_tts'] = replace_numbers_with_words(clean_text)   # như generate_tts_per_scene (đọc số bằng chữ)
    n_voice = len({s['_vn_voice'] for s in scenes})
    if not _acquire_gpu_lock(log_fn, gpu_timeout, '   [GPU] Đang chờ GPU giải phóng (tiến trình khác đang xử lý)...'):
        return []
    try:
        return polish_tts(_render_vieneu_sequential(scenes, scenes[0]['_vn_voice'], '', log_fn, temp_dir, allow_fallback=False,
                                                    _display_override=f'{n_voice} giọng nhân vật') or [], log_fn)
    finally:
        _LOCAL_GPU_LOCK.release()


def _render_vieneu_sequential(scenes, vn_voice, ref_audio_path, log_fn, temp_dir, allow_fallback=False, _fallback_flag=None, _retry_done=False, _display_override=None):
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
    _clear_outputs([b['out'] for b in batch])
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
    try:                                          # ngân sách CPU chung: mặc định torch / onnx lấy hết lõi → máy đơ
        from core import perf
        for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'ORT_NUM_THREADS'):
            env[k] = str(perf.threads_for(1))
    except Exception:
        pass
    from . import vieneu_setup
    if base_cmd[0] == vieneu_setup.PY:
        env = vieneu_setup.hf_env(offline=True)   # model đã tải đủ lúc cài → không gọi mạng
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=_HIDE, env=env)
        register_process(proc)
        deadline = time.time() + timeout_secs
        # đọc output ở luồng riêng: worker treo IM LẶNG (không in dòng nào) thì vòng đọc cũ chờ mãi, giữ khoá GPU → mọi job
        # sau kẹt theo. Luồng chính canh cả hạn tổng lẫn "quá IDLE_SECS không có tiến triển" rồi kill.
        import queue as _q
        lines = _q.Queue()

        def _pump():
            try:
                for ln in proc.stdout:
                    lines.put(ln)
            finally:
                lines.put(None)
        threading.Thread(target=_pump, daemon=True).start()
        IDLE_SECS = 300                          # 1 câu (kể cả nạp model lần đầu) không bao giờ lâu tới vậy
        last = time.time()
        try:
            while True:
                from core import cancel
                if cancel.requested():
                    proc.kill()
                    log_fn('   [DỪNG] Dừng VieNeu TTS')
                    break
                try:
                    line = lines.get(timeout=1)
                except _q.Empty:
                    now = time.time()
                    if now > deadline or now - last > IDLE_SECS:
                        proc.kill()
                        log_fn('   [WARN] VieNeu TTS ' + ('quá thời gian' if now > deadline else f'không phản hồi {IDLE_SECS}s')
                               + ' — dừng tiến trình, giải phóng GPU')
                        break
                    continue
                if line is None:
                    break
                last = time.time()
                line = line.rstrip()
                if line and '[VIENEU_WORKER]' in line:
                    log_fn(f'''   {line.replace('[VIENEU_WORKER] ', '')}''')
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
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
    # nghỉ 0.12s giữa 2 lượt lời (đoạn giọng đã cắt lặng 2 đầu → ghép thẳng thì các vai nói dính liền nhau)
    filt = ''.join((f'''[{k}:a]aresample=48000,aformat=sample_fmts=s16:channel_layouts=mono{',apad=pad_dur=0.12' if k < n - 1 else ''}[a{k}];''' for k in range(n))) + ''.join((f'''[a{k}]''' for k in range(n))) + f'''concat=n={n}:v=0:a=1[out]'''
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
    redo = []                                    # câu thiếu đoạn / ghép lỗi → đọc lại CẢ câu bằng giọng người kể (đủ lời)
    for (i, s) in enumerate(scenes):
        segs = seg_lists[i]
        if not segs:
            continue
        paths = [path_map.get((i, gi)) for gi in range(len(segs))]
        if not all(paths):
            log_fn(f'''   [WARN] Cảnh {i + 1}: thiếu {sum(1 for p in paths if not p)}/{len(segs)} đoạn giọng — đọc lại cả câu bằng giọng người kể (không để mất lời).''')
            redo.append(i)
            continue
        if len(paths) == 1:
            final = paths[0]
        else:
            final = _concat_audio_files(paths, os.path.join(temp_dir, f'''mv_{i:04d}.wav'''), log_fn)
            if not final:
                log_fn(f'''   [WARN] Cảnh {i + 1}: ghép giọng các vai lỗi — đọc lại cả câu bằng giọng người kể (không để mất lời).''')
                redo.append(i)
                continue
        dur = _audio_duration(final)
        if dur < 0.1:
            redo.append(i)
            continue
        s2 = dict(s)
        s2['_original_index'] = s.get('_original_index', i)   # thiếu chỉ số → bước đọc bù tưởng mọi cảnh thiếu giọng, đọc lại & nhân đôi video
        s2['tts_path'] = final
        s2['tts_duration'] = dur
        s2['_tts_engine_used'] = 'vieneu'
        s2['_cast_voices'] = len({_voice_for(seg) for seg in segs})
        s2['tts_text'] = s.get('voiceover', '')
        out_scenes.append(s2)
    if redo:
        plist = [{**scenes[i], 'segments': None, '_mv_redo': i} for i in redo]
        for o in generate_tts_per_scene(plist, narrator_voice, os.path.join(temp_dir, 'mv_redo'), log_fn=log_fn, **kw) or []:
            i = o.get('_mv_redo')
            if i is None or not o.get('tts_path'):
                continue
            s2 = {k: v for (k, v) in o.items() if k != '_mv_redo'}
            s2['_original_index'] = scenes[i].get('_original_index', i)
            out_scenes.append(s2)
        out_scenes.sort(key=lambda x: x.get('_original_index', 0))
    log_fn(f'''   [PHÂN VAI] Hoàn tất: {len(out_scenes)}/{len(scenes)} câu, {len(by_voice)} giọng khác nhau.''')
    return out_scenes
_PROBE_ERR = {}          # đường dẫn → lý do không đo được độ dài (báo đúng lỗi thay vì "audio quá ngắn")


def _audio_duration(path):
    """Độ dài file âm thanh (giây). ffprobe lỗi → đo lại bằng cách giải mã; vẫn lỗi → 0.0 và ghi lý do vào _PROBE_ERR."""
    from .utils import run_subprocess
    err = ''
    if not path or not os.path.isfile(path):
        _PROBE_ERR[path] = 'không thấy file'
        return 0.0
    try:
        r = run_subprocess([FFPROBE_EXE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path], timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        return float(r.stdout.strip())
    except Exception as e:
        err = f'ffprobe: {e}'
    try:                                         # dự phòng: giải mã cả file, đếm mẫu
        r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-i', path, '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                           capture_output=True, timeout=60, creationflags=_HIDE)
        if r.returncode == 0 and r.stdout:
            return len(r.stdout) / 2 / 16000
        err += f' · giải mã: {(r.stderr or b"").decode("utf-8", "replace").strip()[-120:] or "không có âm thanh"}'
    except Exception as e:
        err += f' · giải mã: {e}'
    _PROBE_ERR[path] = err.strip(' ·') or 'không đọc được'
    return 0.0


def _short_reason(path, dur):
    """Lý do bỏ 1 câu: file hỏng / không đọc được (kèm lỗi) hay thật sự quá ngắn."""
    return f'không đọc được file ({_PROBE_ERR.get(path)})' if dur <= 0 and path in _PROBE_ERR else f'audio quá ngắn ({dur:.2f}s)'


# Đệm im lặng sau câu TRƯỚC khi co giãn: bộ co giãn nuốt mất phần cuối file → mất âm cuối chữ.
STRETCH_PAD = 0.4


def stretch_filter(tempo=1.0, pitch=1.0, sr=48000):
    """Chuỗi lọc ffmpeg: nhanh / chậm theo tempo (giữ cao độ) + đổi cao độ theo hệ số pitch (giữ tốc độ).
    Có đệm đuôi chống mất chữ (đuôi im lặng thừa — người gọi tự cắt). Không đổi gì → ''."""
    (tempo, pitch) = (float(tempo or 1.0), float(pitch or 1.0))
    if abs(tempo - 1.0) < 0.002 and abs(pitch - 1.0) < 0.002:
        return ''
    # KHÔNG dùng rubberband: bản trong ffmpeg (engine R2) làm nhoè hài âm giọng nói → nghe rè / pha (đã so phổ âm).
    # atempo (WSOLA) + asetrate giữ giọng sạch; đệm đuôi để không nuốt âm cuối.
    parts = [f'apad=pad_dur={STRETCH_PAD}']
    if abs(pitch - 1.0) >= 0.002:
        parts += [f'asetrate={int(sr * pitch)}', f'aresample={sr}']
    t = tempo / pitch                             # asetrate làm nhanh theo pitch → bù lại
    while t > 2.0:                                # atempo chỉ nhận 0.5–2.0 mỗi lần
        parts.append('atempo=2.0')
        t /= 2.0
    while t < 0.5:
        parts.append('atempo=0.5')
        t /= 0.5
    if abs(t - 1.0) >= 0.002:
        parts.append(f'atempo={t:.4f}')
    return ','.join(parts)


# cắt im lặng thừa ở đuôi (do đệm) — ngưỡng thấp, chừa 0.12s để không lẹm âm cuối nhỏ dần
TAIL_TRIM = 'areverse,silenceremove=start_periods=1:start_threshold=-60dB:start_silence=0.12,areverse'


def voice_fx_filter(rate=1.0, pitch=1.0, sr=48000):
    """Bộ lọc ffmpeg đổi tốc độ (giữ cao độ) + cao độ theo hệ số pitch (giữ tốc độ), cắt lại đuôi im lặng. Không đổi gì → ''."""
    (rate, pitch) = (float(rate or 1.0), float(pitch or 1.0))
    if abs(rate - 1.0) < 0.005 and abs(pitch - 1.0) < 0.0005:
        return ''
    return f'{stretch_filter(rate, pitch, sr)},{TAIL_TRIM}'


def median_f0(path, sr=16000):
    """Cao độ trung vị (Hz) của giọng trong file — tự tương quan từng khung 40ms, chỉ khung đủ to & có chu kỳ rõ.
    Nội suy đỉnh để đo mịn (±0.5Hz). Không đo được → 0."""
    import numpy as np
    r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-i', path, '-ac', '1', '-ar', str(sr), '-af', 'highpass=f=70,lowpass=f=1000',
                        '-f', 's16le', '-'], capture_output=True, creationflags=_HIDE)
    x = np.frombuffer(r.stdout, '<i2').astype(np.float32) if r.returncode == 0 else np.zeros(0, np.float32)
    (n, hop, lo, hi) = (int(0.04 * sr), int(0.02 * sr), int(sr / 500), int(sr / 70))
    if len(x) < n:
        return 0.0
    rms_all = np.sqrt(np.mean(x ** 2)) + 1e-9
    f0 = []
    for i in range(0, len(x) - n, hop):
        fr = x[i:i + n] - x[i:i + n].mean()
        if np.sqrt(np.mean(fr ** 2)) < 0.6 * rms_all:
            continue
        ac = np.correlate(fr, fr, 'full')[n - 1:]
        if ac[0] <= 0:
            continue
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] / ac[0] <= 0.45 or k <= lo or k >= hi - 1:
            continue
        (a, b, c) = (ac[k - 1], ac[k], ac[k + 1])
        d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) else 0.0
        f0.append(sr / (k + d))
    return float(np.median(f0)) if len(f0) >= 5 else 0.0


def _sample_rate(path):
    try:
        import wave
        with wave.open(path, 'rb') as w:
            return w.getframerate()
    except Exception:
        try:
            r = subprocess.run([FFPROBE_EXE, '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=sample_rate',
                                '-of', 'default=noprint_wrappers=1:nokey=1', path], capture_output=True, text=True, creationflags=_HIDE, timeout=15)
            return int(r.stdout.strip() or 0) or 48000
        except Exception:
            return 48000


def apply_voice_fx(scenes, rate=1.0, pitch_hz=0.0, log_fn=print, engines=('vieneu',)):
    """Đổi tốc độ (rate, hệ số) / cao độ (pitch_hz: dời cao độ giọng ± bao nhiêu Hz, như Edge TTS) các câu tạo bằng VieNeu
    (model không có sẵn 2 tuỳ chọn này) → ghi file mới cạnh file cũ, cập nhật tts_path / tts_duration.
    Đo cao độ thật từng câu rồi dời đúng số Hz. Câu lỗi giữ nguyên file gốc. → scenes (sửa tại chỗ)."""
    (rate, pitch_hz) = (float(rate or 1.0), float(pitch_hz or 0.0))
    if abs(rate - 1.0) < 0.005 and abs(pitch_hz) < 0.05:
        return scenes
    todo = [s for s in scenes or [] if s.get('tts_path') and os.path.isfile(s['tts_path'])
            and (s.get('_tts_engine_used') in engines)]
    done = 0
    for s in todo:
        from core import cancel
        cancel.check()
        src = s['tts_path']
        ratio = 1.0
        if abs(pitch_hz) >= 0.05:
            f0 = median_f0(src) or 180.0              # không đo được (câu quá ngắn) → lấy mức giọng nói trung bình
            ratio = max(0.5, min(2.0, (f0 + pitch_hz) / f0))
        af = voice_fx_filter(rate, ratio, _sample_rate(src))
        if not af:
            continue
        out = os.path.splitext(src)[0] + '_fx.wav'
        r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-y', '-i', src, '-af', af, '-c:a', 'pcm_s16le', out],
                           capture_output=True, creationflags=_HIDE)
        if r.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 1000:
            s['tts_path'] = out
            s['tts_duration'] = _audio_duration(out) or s.get('tts_duration', 0)
            done += 1
    if todo:
        log_fn(f'   Giọng VieNeu: rate {(rate - 1) * 100:+.0f}% · pitch {pitch_hz:+g}Hz — áp cho {done}/{len(todo)} câu')
    return scenes
