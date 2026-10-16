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
    "VieNeu — Bình An (Nam)": "vieneu-binh-an",
    "VieNeu — Xuân Vĩnh (Nam)": "vieneu-xuan-vinh",
    "VieNeu — Gia Bảo (Nam)": "vieneu-gia-bao",
    "VieNeu — Ngọc Lan (Nữ)": "vieneu-ngoc-lan",
    "VieNeu — Mỹ Duyên (Nữ)": "vieneu-my-duyen",
    "VieNeu — Trúc Ly (Nữ)": "vieneu-truc-ly",
    "VieNeu — Ngọc Linh (Nữ)": "vieneu-ngoc-linh",
    "VieNeu — Thái Sơn (Nam)": "vieneu-thai-son",
    "VieNeu — Đức Trí (Nam)": "vieneu-duc-tri",
    "VieNeu — Trọng Hữu (Nam)": "vieneu-trong-huu",
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
    "Edge TTS — Nam Bắc (miễn phí)": "vi-VN-NamMinhNeural",
    "Edge TTS — Nữ Bắc (miễn phí)": "vi-VN-HoaiMyNeural"
}

VIENEU_CAST_MALE = [
    "VieNeu — Bình An (Nam)",
    "VieNeu — Xuân Vĩnh (Nam)",
    "VieNeu — Gia Bảo (Nam)",
    "VieNeu — Thái Sơn (Nam)",
    "VieNeu — Đức Trí (Nam)",
    "VieNeu — Trọng Hữu (Nam)",
    "VieNeu3 — Trung Dũng",
    "VieNeu3 — Lâm Lê",
    "VieNeu3 — Nam Trầm Ấm",
    "VieNeu3 — Nam Truyền Cảm"
]

VIENEU_CAST_FEMALE = [
    "VieNeu — Ngọc Lan (Nữ)",
    "VieNeu — Mỹ Duyên (Nữ)",
    "VieNeu — Trúc Ly (Nữ)",
    "VieNeu — Ngọc Linh (Nữ)",
    "VieNeu3 — Lena",
    "VieNeu3 — Mia",
    "VieNeu3 — Yến Tin Tức",
    "VieNeu3 — Nữ Nhẹ Nhàng",
    "VieNeu3 — Nữ Điềm Đạm"
]

WHISPER_MODELS = [
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
