"""Hằng số chuyển từ main_qt.py (AutoReview Studio)."""

SUBTITLE_STYLE_PRESETS = {
    "Mặc định (chữ trắng, viền đen)": {
        "sub_font_color": "white",
        "sub_box_enabled": True,
        "sub_box_color": "black@0.5",
        "sub_border_width": 3,
        "sub_font_size_factor": 1.0,
        "sub_font_name": "Segoe UI",
        "sub_box_padding": 12,
        "sub_margin_v_pct": 0.06,
        "sub_line_spacing": 6,
        "sub_text_transform": "none"
    },
    "CapCut trắng đậm": {
        "sub_font_color": "white",
        "sub_box_enabled": False,
        "sub_box_color": "black@0.5",
        "sub_border_width": 6,
        "sub_font_size_factor": 1.08,
        "sub_font_name": "Arial",
        "sub_box_padding": 12,
        "sub_margin_v_pct": 0.065,
        "sub_line_spacing": 8,
        "sub_text_transform": "none"
    },
    "CapCut vàng nổi": {
        "sub_font_color": "#ffd400",
        "sub_box_enabled": False,
        "sub_box_color": "black@0.5",
        "sub_border_width": 6,
        "sub_font_size_factor": 1.08,
        "sub_font_name": "Arial",
        "sub_box_padding": 12,
        "sub_margin_v_pct": 0.065,
        "sub_line_spacing": 8,
        "sub_text_transform": "none"
    },
    "CapCut khung đen": {
        "sub_font_color": "white",
        "sub_box_enabled": True,
        "sub_box_color": "black@0.78",
        "sub_border_width": 2,
        "sub_font_size_factor": 1.0,
        "sub_font_name": "Montserrat",
        "sub_box_padding": 18,
        "sub_margin_v_pct": 0.06,
        "sub_line_spacing": 7,
        "sub_text_transform": "none"
    },
    "Game vàng in hoa (nền mờ)": {
        "sub_font_color": "#ffe21f",
        "sub_box_enabled": False,
        "sub_box_color": "black@0.5",
        "sub_border_width": 5,
        "sub_border_color": "#3a2200",
        "sub_font_size_factor": 1.0,
        "sub_font_name": "Baloo 2 ExtraBold",
        "sub_box_padding": 12,
        "sub_margin_v_pct": 0.06,
        "sub_line_spacing": 6,
        "sub_text_transform": "uppercase",
        "sub_bg_blur": True
    },
    "CapCut chữ hoa hook": {
        "sub_font_color": "#ffe95a",
        "sub_box_enabled": False,
        "sub_box_color": "black@0.5",
        "sub_border_width": 5,
        "sub_font_size_factor": 1.02,
        "sub_font_name": "Impact",
        "sub_box_padding": 12,
        "sub_margin_v_pct": 0.07,
        "sub_line_spacing": 10,
        "sub_text_transform": "uppercase"
    },
    "Tối giản (không khung)": {
        "sub_font_color": "white",
        "sub_box_enabled": False,
        "sub_box_color": "black@0.5",
        "sub_border_width": 4,
        "sub_font_size_factor": 1.0,
        "sub_font_name": "Segoe UI",
        "sub_box_padding": 12,
        "sub_margin_v_pct": 0.06,
        "sub_line_spacing": 6,
        "sub_text_transform": "none"
    },
    "Dịch & Reup (Tahoma viền đậm)": {
        "sub_font_color": "white",
        "sub_box_enabled": False,
        "sub_box_color": "black@0.5",
        "sub_border_width": 5,
        "sub_font_size_factor": 1.05,
        "sub_font_name": "Tahoma",
        "sub_box_padding": 12,
        "sub_margin_v_pct": 0.07,
        "sub_line_spacing": 7,
        "sub_text_transform": "none"
    },
    "CapCut nền vàng chữ đen": {
        "sub_font_color": "black",
        "sub_box_enabled": True,
        "sub_box_color": "#ffd400@0.92",
        "sub_border_width": 0,
        "sub_font_size_factor": 1.05,
        "sub_font_name": "Arial",
        "sub_box_padding": 14,
        "sub_margin_v_pct": 0.065,
        "sub_line_spacing": 8,
        "sub_text_transform": "none"
    },
    "CapCut xanh neon": {
        "sub_font_color": "#3dfca7",
        "sub_box_enabled": False,
        "sub_box_color": "black@0.5",
        "sub_border_width": 5,
        "sub_font_size_factor": 1.08,
        "sub_font_name": "Arial",
        "sub_box_padding": 12,
        "sub_margin_v_pct": 0.065,
        "sub_line_spacing": 8,
        "sub_text_transform": "none"
    },
    "CapCut hồng bắt mắt": {
        "sub_font_color": "#ff5ec7",
        "sub_box_enabled": False,
        "sub_box_color": "black@0.5",
        "sub_border_width": 5,
        "sub_font_size_factor": 1.08,
        "sub_font_name": "Arial",
        "sub_box_padding": 12,
        "sub_margin_v_pct": 0.065,
        "sub_line_spacing": 8,
        "sub_text_transform": "none"
    },
    "Bản tin (trắng nền đỏ)": {
        "sub_font_color": "white",
        "sub_box_enabled": True,
        "sub_box_color": "#c1121f@0.9",
        "sub_border_width": 0,
        "sub_font_size_factor": 1.0,
        "sub_font_name": "Arial",
        "sub_box_padding": 14,
        "sub_margin_v_pct": 0.06,
        "sub_line_spacing": 7,
        "sub_text_transform": "none"
    },
    "Tùy chỉnh riêng...": None
}

SUBTITLE_LAYOUT_PRESETS = {
    "1 dòng rất ngắn": {
        "sub_max_chars_per_chunk": 34,
        "sub_max_lines": 1
    },
    "2 dòng gọn (khuyên dùng)": {
        "sub_max_chars_per_chunk": 56,
        "sub_max_lines": 2
    },
    "3 dòng cân bằng": {
        "sub_max_chars_per_chunk": 78,
        "sub_max_lines": 3
    }
}

SUBTITLE_SOURCE_OPTIONS = {
    "Theo lời đọc AI (khớp voiceover)": "voiceover",
    "Theo subtitle/dịch gốc": "subtitle"
}

VOICE_OPTIONS = {
    "Giọng cao cấp — Ban Mai, Nữ Bắc": "banmaiace",
    "Giọng cao cấp — Lan Nhi, Nữ Nam": "lannhi",
    "Giọng cao cấp — Lê Minh, Nam Bắc": "leminh",
    "Giọng cao cấp — Mỹ An, Nữ Trung": "myan",
    "Giọng cao cấp — Thu Minh, Nữ Bắc": "thuminhace",
    "Giọng cao cấp — Gia Huy, Nam Trung": "giahuy",
    "Giọng cao cấp — Linh San, Nữ Nam": "linhsanace",
    "Giọng cao cấp — Ngọc Lam, Nữ Trung": "ngoclamace",
    "Giọng cao cấp — Minh Quang, Nam Nam": "minhquangace",
    "VieNeu — Adam bựa (Nam · miền Bắc · tự nhiên)": "vieneu-adam-bua",
    "VieNeu — Trúc Ly (Nữ · miền Bắc · tự nhiên)": "vieneu-truc-ly",
    "VieNeu — Thiện Minh (Nam · miền Bắc · kể chuyện)": "vieneu-thien-minh",
    "VieNeu — Mai Anh (Nữ · miền Bắc · tin tức)": "vieneu-mai-anh",
    "VieNeu — Hải Đăng (Nam · miền Bắc · tự nhiên)": "vieneu-hai-dang",
    "VieNeu — Thùy Dung (Nữ · miền Nam · tin tức)": "vieneu-thuy-dung",
    "VieNeu — Thiền Tâm Đức (Nam · miền Bắc · kể chuyện)": "vieneu-thien-tam-duc",
    "VieNeu — Ngọc Huyền (Nữ · miền Bắc · tự nhiên)": "vieneu-ngoc-huyen",
    "VieNeu — Quang Sơn (Nam · miền Trung · tự nhiên)": "vieneu-quang-son",
    "VieNeu — Ngọc Trân (Nữ · miền Trung · tự nhiên)": "vieneu-ngoc-tran",
    "VieNeu — Minh Đức (Nam · miền Bắc · tin tức)": "vieneu-minh-duc",
    "VieNeu — Phạm Tuyên (Nam · miền Bắc · tự nhiên)": "vieneu-pham-tuyen",
    "VieNeu — Thái Sơn (Nam · miền Nam · kể chuyện)": "vieneu-thai-son",
    "VieNeu — Xuân Vĩnh (Nam · miền Bắc · tự nhiên)": "vieneu-xuan-vinh",
    "VieNeu — Thanh Bình (Nam · miền Bắc · kể chuyện)": "vieneu-thanh-binh",
    "VieNeu — Ngọc Linh (Nữ · miền Bắc · kể chuyện)": "vieneu-ngoc-linh",
    "VieNeu — Đoan Trang (Nữ · miền Bắc · tự nhiên)": "vieneu-doan-trang",
    "VieNeu — Thục Đoan (Nữ · miền Nam · kể chuyện)": "vieneu-thuc-doan",
    "VieNeu — Minh Triết (Nam · miền Nam · tin tức)": "vieneu-minh-triet",
    "VieNeu — Mỹ Duyên (Nữ · miền Nam · kể chuyện)": "vieneu-my-duyen",
    "VieNeu — Quỳnh Anh (Nữ · miền Bắc · kể chuyện)": "vieneu-quynh-anh",
    "VieNeu — Đức Trí (Nam · miền Nam · kể chuyện)": "vieneu-duc-tri",
    "VieNeu — Kim Thanh (Nữ · miền Nam · kể chuyện)": "vieneu-kim-thanh",
    "VieNeu — Adam (Nam · miền Nam · tự nhiên)": "vieneu-adam",
    "VieNeu — Quốc Tuấn (Nam · miền Bắc · tự nhiên)": "vieneu-quoc-tuan",
    "VieNeu3 — Chiến Thắng": "vieneu3-chien-thang",
    "VieNeu3 — Hùng Bá": "vieneu3-hung-ba",
    "VieNeu3 — Lâm Lê": "vieneu3-lam-le",
    "VieNeu3 — Lý Long Tiếng": "vieneu3-ly-long-tieng",
    "VieNeu3 — Pháp Phật": "vieneu3-phat-phap",
    "VieNeu3 — Review Toptop": "vieneu3-review-toptop",
    "VieNeu3 — Trịnh Lê": "vieneu3-trinh-le",
    "VieNeu3 — Trung Dũng": "vieneu3-trung-dung",
    "VieNeu3 — Yến Tin Tức": "vieneu3-yen-tin-tuc",
    "VieNeu3 — Ban Mai": "vieneu3-ban-mai",
    "VieNeu3 — Quảng Cáo Nội Lực": "vieneu3-quang-cao",
    "VieNeu3 — Hệ Thống": "vieneu3-he-thong",
    "VieNeu3 — Lena": "vieneu3-lena",
    "VieNeu3 — MC Truyền Hình": "vieneu3-mc-truyen-hinh",
    "VieNeu3 — Mia": "vieneu3-mia",
    "VieNeu3 — Minh Quang": "vieneu3-minh-quang",
    "VieNeu3 — Nam": "vieneu3-nam",
    "VieNeu3 — Nguyên": "vieneu3-nguyen",
    "VieNeu3 — Thu Minh": "vieneu3-thu-minh",
    "VieNeu3 — Nam Trầm Ấm": "vieneu3-nam-tram-am",
    "VieNeu3 — Nam Chậm Rãi": "vieneu3-nam-cham-rai",
    "VieNeu3 — Nam Nhanh Nhẹn": "vieneu3-nam-nhanh-nhen",
    "VieNeu3 — Nam Truyền Cảm": "vieneu3-nam-truyen-cam",
    "VieNeu3 — Nữ Điềm Đạm": "vieneu3-nu-diem-dam",
    "VieNeu3 — Nữ Chậm Rãi": "vieneu3-nu-cham-rai",
    "VieNeu3 — Nữ Lưu Loát": "vieneu3-nu-luu-loat",
    "VieNeu3 — Nữ Nhàn Nhã": "vieneu3-nu-nhan-nha",
    "VieNeu3 — Nữ Nhẹ Nhàng": "vieneu3-nu-nhe-nhang",
    "CapCut — Nhỏ Ngọt Ngào (Nữ)": "capcut-BV421_vivn_streaming",
    "CapCut — Giọng Nữ Phổ Thông": "capcut-vi_female_huong",
    "CapCut — Cô Gái Hoạt Ngôn (Nữ)": "capcut-BV074_streaming",
    "CapCut — Mai (Nữ)": "capcut-BV562_streaming",
    "CapCut — Hoài My (Nữ)": "capcut-vi-VN-HoaiMyNeural",
    "CapCut — Nam Minh (Nam)": "capcut-vi-VN-NamMinhNeural",
    "CapCut — Giọng Bé": "capcut-BV074_streaming_dsp",
    "CapCut — Việt Méo (Nam, hài)": "capcut-BV075_streaming_vibrato_dsp",
    "CapCut — Kenny Đại Đế (Nam, hài)": "capcut-BV075_streaming_demon_dsp",
    "CapCut — Chị Điềm Đạm (Nữ)": "capcut-ICL_uranus_vi_male_yuenan7",
    "CapCut — Cô Gái Dịu Dàng (Nữ)": "capcut-ICL_uranus_vi_female_wnns",
    "CapCut — Chị Dịu Dàng (Nữ)": "capcut-ICL_uranus_vi_female_yuenan1",
    "CapCut — Mẹ Kế Khó Tính (Nữ)": "capcut-ICL_uranus_vi_female_edujiyi",
    "CapCut — Nàng Tươi Tắn (Nữ)": "capcut-ICL_uranus_vi_female_qcns",
    "CapCut — Cô bạn quốc dân (Nữ)": "capcut-multi_female_ling_uranus_bigtts",
    "CapCut — Bạn Vui (Nữ)": "capcut-multi_female_ruan_uranus_bigtts",
    "CapCut — Quan tòa minh mẫn (Nữ)": "capcut-multi_female_hong_uranus_bigtts",
    "CapCut — Quản lý vững vàng (Nữ)": "capcut-multi_female_partner_uranus_bigtts",
    "CapCut — Nàng tinh ranh (Nữ)": "capcut-multi_female_linh_uranus_bigtts",
    "CapCut — Cô bạn khô cứng (Nữ)": "capcut-multi_female_wu_uranus_bigtts",
    "CapCut — Thủ Lĩnh Sáng Suốt (Nữ)": "capcut-ICL_uranus_vi_female_youxichuangzuozhe",
    "CapCut — Sài Nữ (Nữ)": "capcut-xPEfmymXC4WdBxGMznS7",
    "CapCut — Hà Nữ (Nữ)": "capcut-pGapy9MNHCukzJtjavF0",
    "CapCut — Cô Gái Năng Động (Nữ)": "capcut-ICL_uranus_vi_female_xfns",
    "CapCut — Nàng Cá Tính (Nữ)": "capcut-ICL_uranus_vi_female_cmns",
    "CapCut — Nhám Thơ (Nữ)": "capcut-ICL_uranus_vi_female_shayazhiyu",
    "CapCut — Thẳm Ẩn Nữ (Nữ)": "capcut-ICL_uranus_vi_female_gushinv",
    "CapCut — Nàng Điềm Tĩnh (Nữ)": "capcut-ICL_uranus_vi_female_yuenan4",
    "CapCut — Chị Trưởng Thành (Nữ)": "capcut-ICL_uranus_vi_female_yuenan2",
    "CapCut — Em Gái Ngọt Ngào (Nữ)": "capcut-ICL_uranus_vi_female_yuenan3",
    "CapCut — Mềm Họa Sĩ (Nữ)": "capcut-ICL_uranus_vi_female_xuemei",
    "CapCut — Người Kể Điềm Tĩnh (Nam)": "capcut-ICL_uranus_vi_male_xinluyin",
    "CapCut — Chàng Trai Trầm Lắng (Nam)": "capcut-ICL_uranus_vi_male_kbpb",
    "CapCut — Chàng Trai Sôi Nổi (Nam)": "capcut-ICL_uranus_vi_male_yuenan9",
    "CapCut — Người Kể Trầm Ấm (Nam)": "capcut-ICL_uranus_vi_male_lizhipangbai",
    "CapCut — Giọng nam tự tin (Nam)": "capcut-BV075_streaming",
    "CapCut — Anh hiền lành (Nam)": "capcut-multi_male_wumg_uranus_bigtts",
    "CapCut — Anh Dũng (Nam)": "capcut-BV560_streaming",
    "CapCut — Chàng Trai U Sầu (Nam)": "capcut-ICL_uranus_vi_male_byns",
    "CapCut — Chàng Trai Ấm Áp (Nam)": "capcut-ICL_uranus_vi_male_cfzc",
    "CapCut — Chàng Trai Điềm Đạm (Nam)": "capcut-ICL_uranus_vi_male_jtcf",
    "CapCut — Ly Nam (Nam)": "capcut-7hsfEc7irDn6E8br0qfw",
    "CapCut — Duy Bắc (Nam)": "capcut-1d5Bb0SMBPB10Gx6iQeu",
    "CapCut — Trung Caha (Nam)": "capcut-ueSxRO0nLF1bj93J2hVt",
    "CapCut — Nam Trầm (Nam)": "capcut-9EE00wK5qV6tPtpQIxvy",
    "CapCut — Dịu Nhân Tử (Nam)": "capcut-ICL_uranus_vi_male_zhiyunan",
    "CapCut — Robot VN (Nam, hài)": "capcut-BV075_streaming_robot_dsp",
    "CapCut — Thánh nhân nhân hậu (Nam)": "capcut-ICL_uranus_vi_male_shenchendiyu",
    "CapCut — Anh Điềm Đạm (Nam)": "capcut-ICL_uranus_vi_male_yuenan8",
    "CapCut — Dịu Trí Giả (Nam)": "capcut-ICL_uranus_vi_male_qingxiunanhai",
    "Edge TTS — Nam Bắc (miễn phí)": "vi-VN-NamMinhNeural",
    "Edge TTS — Nữ Bắc (miễn phí)": "vi-VN-HoaiMyNeural"
}

VIENEU_CAST_MALE = [
    "VieNeu — Hải Đăng (Nam · miền Bắc · tự nhiên)",
    "VieNeu — Thiện Minh (Nam · miền Bắc · kể chuyện)",
    "VieNeu — Xuân Vĩnh (Nam · miền Bắc · tự nhiên)",
    "VieNeu — Thái Sơn (Nam · miền Nam · kể chuyện)",
    "VieNeu — Đức Trí (Nam · miền Nam · kể chuyện)",
    "VieNeu — Quang Sơn (Nam · miền Trung · tự nhiên)",
    "VieNeu — Minh Triết (Nam · miền Nam · tin tức)",
    "VieNeu — Quốc Tuấn (Nam · miền Bắc · tự nhiên)",
    "VieNeu3 — Trung Dũng",
    "VieNeu3 — Lâm Lê",
    "VieNeu3 — Nam Trầm Ấm",
    "VieNeu3 — Nam Truyền Cảm"
]

VIENEU_CAST_FEMALE = [
    "VieNeu — Trúc Ly (Nữ · miền Bắc · tự nhiên)",
    "VieNeu — Ngọc Huyền (Nữ · miền Bắc · tự nhiên)",
    "VieNeu — Mỹ Duyên (Nữ · miền Nam · kể chuyện)",
    "VieNeu — Ngọc Linh (Nữ · miền Bắc · kể chuyện)",
    "VieNeu — Mai Anh (Nữ · miền Bắc · tin tức)",
    "VieNeu — Thục Đoan (Nữ · miền Nam · kể chuyện)",
    "VieNeu — Ngọc Trân (Nữ · miền Trung · tự nhiên)",
    "VieNeu — Quỳnh Anh (Nữ · miền Bắc · kể chuyện)",
    "VieNeu3 — Lena",
    "VieNeu3 — Mia",
    "VieNeu3 — Yến Tin Tức",
    "VieNeu3 — Nữ Nhẹ Nhàng"
]

# Giọng VieNeu cũ không còn trong model mới — ẩn khỏi danh sách nhưng cấu hình / job cũ vẫn chạy (worker đổi sang giọng gần nhất)

def _foreign_voice_options():
    """Giọng lồng tiếng ngôn ngữ khác: Edge TTS (miễn phí) + toàn bộ giọng CapCut theo ngôn ngữ → {nhãn: id}.
    Nhãn "CapCut EN — Tên" / "Edge TTS EN — Nữ": duy nhất, phần sau " — " là tên hiện trong ô chọn."""
    from core import langs
    from core.capcut_tts import CATALOG
    out = {}
    for (code, row) in langs.LANGS.items():
        if code == 'vi':
            continue
        out[f'Edge TTS {code.upper()} — Nữ (miễn phí)'] = row[2]
        out[f'Edge TTS {code.upper()} — Nam (miễn phí)'] = row[3]
    for v in CATALOG:
        if v['lang'] == 'vi':
            continue
        sex = {'female': ' (Nữ)', 'male': ' (Nam)'}.get(v.get('gender'), '')
        base = f"CapCut {('MULTI' if v['lang'] == 'multi' else v['lang'].upper())} — {v['name']}{sex}"
        (label, n) = (base, 2)
        while label in out or label in VOICE_OPTIONS:
            (label, n) = (f'{base} {n}', n + 1)
        out[label] = 'capcut-' + v['id']
    return out


VOICE_OPTIONS.update(_foreign_voice_options())

LEGACY_VOICE_OPTIONS = {
    "VieNeu — Bình An (Nam)": "vieneu-binh-an",
    "VieNeu — Gia Bảo (Nam)": "vieneu-gia-bao",
    "VieNeu — Ngọc Lan (Nữ)": "vieneu-ngoc-lan",
    "VieNeu — Trọng Hữu (Nam)": "vieneu-trong-huu",
    "VieNeu — Xuân Vĩnh (Nam)": "vieneu-xuan-vinh",
    "VieNeu — Mỹ Duyên (Nữ)": "vieneu-my-duyen",
    "VieNeu — Trúc Ly (Nữ)": "vieneu-truc-ly",
    "VieNeu — Ngọc Linh (Nữ)": "vieneu-ngoc-linh",
    "VieNeu — Thái Sơn (Nam)": "vieneu-thai-son",
    "VieNeu — Đức Trí (Nam)": "vieneu-duc-tri",
}

WHISPER_MODELS = [
    "capcut",      # nhận dạng online của CapCut (core/capcut_stt.py) — nhanh, không cần GPU
    "tiny",
    "base",
    "small",
    "medium",
    "large",
    "large-v2",
    "large-v3"
]

COMPUTE_DEVICES = [
    "GPU (NVIDIA)",
    "CPU"
]

LANGUAGE_MAP = {
    "Tự động": "auto",
    "Tiếng Trung (Hoa)": "zh",
    "Tiếng Anh": "en",
    "Tiếng Nhật": "ja",
    "Tiếng Hàn": "ko",
    "Tiếng Việt": "vi"
}
