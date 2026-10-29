"""Ngôn ngữ đầu ra (lời đọc / phụ đề) — một nơi duy nhất: tên, giọng Edge dự phòng, tốc độ nói, có dấu cách giữa từ không.

target_lang mặc định 'vi' → mọi đường cũ giữ nguyên hành vi tiếng Việt.
"""

# code → (tên tiếng Việt, tên tiếng Anh cho prompt, Edge nữ, Edge nam, ký tự / giây khi đọc, có dấu cách giữa từ)
LANGS = {
    'vi': ('Tiếng Việt', 'Vietnamese', 'vi-VN-HoaiMyNeural', 'vi-VN-NamMinhNeural', 15.0, True),
    'en': ('Tiếng Anh', 'English', 'en-US-AriaNeural', 'en-US-GuyNeural', 15.0, True),
    'zh': ('Tiếng Trung', 'Simplified Chinese', 'zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural', 4.5, False),
    'ja': ('Tiếng Nhật', 'Japanese', 'ja-JP-NanamiNeural', 'ja-JP-KeitaNeural', 7.5, False),
    'ko': ('Tiếng Hàn', 'Korean', 'ko-KR-SunHiNeural', 'ko-KR-InJoonNeural', 7.0, True),
    'id': ('Tiếng Indonesia', 'Indonesian', 'id-ID-GadisNeural', 'id-ID-ArdiNeural', 15.0, True),
    'th': ('Tiếng Thái', 'Thai', 'th-TH-PremwadeeNeural', 'th-TH-NiwatNeural', 12.0, False),
    'es': ('Tiếng Tây Ban Nha', 'Spanish', 'es-ES-ElviraNeural', 'es-ES-AlvaroNeural', 15.0, True),
    'pt': ('Tiếng Bồ Đào Nha', 'Brazilian Portuguese', 'pt-BR-FranciscaNeural', 'pt-BR-AntonioNeural', 15.0, True),
    'fr': ('Tiếng Pháp', 'French', 'fr-FR-DeniseNeural', 'fr-FR-HenriNeural', 15.0, True),
    'de': ('Tiếng Đức', 'German', 'de-DE-KatjaNeural', 'de-DE-ConradNeural', 14.0, True),
    'it': ('Tiếng Ý', 'Italian', 'it-IT-ElsaNeural', 'it-IT-DiegoNeural', 15.0, True),
    'ru': ('Tiếng Nga', 'Russian', 'ru-RU-SvetlanaNeural', 'ru-RU-DmitryNeural', 14.0, True),
    'ar': ('Tiếng Ả Rập', 'Arabic', 'ar-SA-ZariyahNeural', 'ar-SA-HamedNeural', 13.0, True),
    'tr': ('Tiếng Thổ Nhĩ Kỳ', 'Turkish', 'tr-TR-EmelNeural', 'tr-TR-AhmetNeural', 14.0, True),
    'ms': ('Tiếng Mã Lai', 'Malay', 'ms-MY-YasminNeural', 'ms-MY-OsmanNeural', 15.0, True),
    'fil': ('Tiếng Philippines', 'Filipino', 'fil-PH-BlessicaNeural', 'fil-PH-AngeloNeural', 15.0, True),
}
DEFAULT = 'vi'


def norm(code):
    c = str(code or '').strip().lower().split('-')[0]
    return c if c in LANGS else DEFAULT


def name_vi(code):
    return LANGS[norm(code)][0]


def name_en(code):
    return LANGS[norm(code)][1]


def edge_voice(code, male=False):
    row = LANGS[norm(code)]
    return row[3] if male else row[2]


def chars_per_sec(code):
    return LANGS[norm(code)][4]


def spaced(code):
    """False: tiếng Trung / Nhật / Thái — không có dấu cách giữa từ (ngắt dòng / đếm độ dài theo ký tự)."""
    return LANGS[norm(code)][5]


def is_vi(code):
    return norm(code) == 'vi'


def google_code(code):
    c = norm(code)
    return {'zh': 'zh-CN', 'fil': 'tl'}.get(c, c)


DEMO = {
    'vi': 'Đây là thử nghiệm giọng đọc, xin chào các bạn, chúc một ngày tốt lành.',
    'en': 'Hello everyone, today we are watching an amazing movie together.',
    'zh': '大家好，今天我们一起来看一部非常精彩的电影。',
    'ja': '皆さん、こんにちは。今日は一緒にとても面白い映画を見ましょう。',
    'ko': '안녕하세요 여러분, 오늘은 함께 정말 재미있는 영화를 보겠습니다.',
    'id': 'Halo semuanya, hari ini kita akan menonton film yang sangat seru.',
    'th': 'สวัสดีทุกคน วันนี้เราจะมาดูหนังที่สนุกมากด้วยกัน',
    'es': 'Hola a todos, hoy vamos a ver juntos una película increíble.',
    'pt': 'Olá a todos, hoje vamos assistir juntos a um filme incrível.',
    'fr': "Bonjour à tous, aujourd'hui nous regardons ensemble un film incroyable.",
    'de': 'Hallo zusammen, heute schauen wir gemeinsam einen großartigen Film.',
    'it': 'Ciao a tutti, oggi guardiamo insieme un film incredibile.',
    'ru': 'Всем привет, сегодня мы вместе посмотрим потрясающий фильм.',
    'ar': 'مرحبا بالجميع، اليوم سنشاهد معا فيلما رائعا.',
    'tr': 'Herkese merhaba, bugün birlikte harika bir film izleyeceğiz.',
    'ms': 'Hai semua, hari ini kita akan menonton filem yang sangat menarik.',
    'fil': 'Kumusta kayong lahat, manonood tayo ngayon ng isang napakagandang pelikula.',
}


def voice_lang(voice_id):
    """Ngôn ngữ của 1 giọng (id kỹ thuật: 'capcut-…', 'en-US-AriaNeural', 'vieneu-…') → mã; giọng Việt / không rõ → 'vi'.
    CapCut 'multi' (đa ngôn ngữ) → 'multi'."""
    v = str(voice_id or '')
    if v.startswith('capcut-'):
        from core.capcut_tts import LANG_OF
        return LANG_OF.get(v[len('capcut-'):], 'vi')
    if v.endswith('Neural') and '-' in v:
        return norm(v.split('-')[0]) if v.split('-')[0].lower() in LANGS else 'vi'
    return 'vi'


# độ dài trung bình 1 từ (ký tự, kể cả dấu cách) — quy tốc độ ký tự ra từ / giây cho ngôn ngữ có dấu cách
_AVG_WORD_CHARS = {'en': 5.7, 'id': 6.5, 'ms': 6.5, 'fil': 6.0, 'es': 5.8, 'pt': 5.8, 'fr': 5.8, 'it': 5.9, 'de': 6.8,
                   'ru': 6.8, 'tr': 7.0, 'ar': 5.5, 'ko': 3.0}


def words_per_sec(code):
    """Từ / giây khi đọc (ngôn ngữ có dấu cách, trừ tiếng Việt — tiếng Việt dùng số đo riêng của từng module)."""
    c = norm(code)
    return round(chars_per_sec(c) / _AVG_WORD_CHARS.get(c, 6.0), 2)
