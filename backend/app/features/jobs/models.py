from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SubtitleOptions(BaseModel):
    sub_style: str = 'Mặc định (chữ trắng, viền đen)'
    sub_layout: str = '2 dòng gọn (khuyên dùng)'
    sub_margin_pct: Optional[float] = None
    sub_width_pct: Optional[float] = None
    sub_custom: dict[str, Any] = Field(default_factory=dict)


class VideoJobRequest(SubtitleOptions):
    inp: str
    mode: Literal['review', 'reup', 'vietsub'] = 'review'
    out_dir: str = ''
    source_lang: str = 'Tự động'
    whisper_model: str = 'base'
    device: str = 'GPU (NVIDIA)'
    minutes: int = Field(0, ge=0, le=60)                           # độ dài review (phút); 0 = tự động theo độ dài video
    film_context: str = ''
    scene_accurate: bool = False
    ai_translate: bool = True
    video_speed: str = '1.0x (mặc định)'
    mirror_video: bool = False
    voice: str = 'Edge TTS — Nữ Bắc (miễn phí)'
    strict_voice: bool = False
    vieneu_rate: int = Field(0, ge=-30, le=50)                     # giọng VieNeu: tốc độ đọc ±% (giữ cao độ)
    vieneu_pitch: float = Field(0, ge=-50, le=50)                  # giọng VieNeu: dời cao độ ± Hz (giữ tốc độ), như Edge TTS
    multi_voice: bool = False
    sub_source: str = 'Theo lời đọc AI (khớp voiceover)'
    burn_subtitles: bool = True
    remove_old_sub: bool = False
    cover_boxes: list[list[float]] = Field(default_factory=list)  # [x, y, w, h] theo %
    sub_in_cover: bool = False                                     # phụ đề mới căn giữa vùng che phụ đề cũ
    cover_fit_text: bool = False                                   # Dịch phụ đề: khung mờ ngang vừa theo độ dài chữ từng câu
    cover_style: Literal['clean', 'erase', 'blur'] = 'erase'                # che chữ: xoá nhẹ (delogo, tự nhiên) | làm mờ
    cover_quality: Literal['fast', 'clean'] = 'fast'               # Dịch phụ đề: 'fast' che đúng khung từng câu Trung lúc câu hiện
                                                                   # (1 lượt dựng) | 'clean' xoá sạch nét chữ từng khung (đẹp, rất chậm)
    auto_sub_box: bool = True                                      # AI tự căn vùng che phụ đề theo chỗ phụ đề cũ thật
    dub_voice: bool = False                                        # Dịch phụ đề: lồng tiếng Việt đúng thời gian câu thoại
    dub_orig_volume: int = Field(20, ge=0, le=100)                 # % âm lượng tiếng gốc khi có lời Việt
    bilingual: bool = False                                         # Dịch phụ đề: thêm lời gốc nhỏ dưới dòng Việt (song ngữ)
    extra_aspect: str = ''                                          # Dịch phụ đề: xuất thêm bản '9:16' (video ngang) / '16:9' (video dọc) cùng lượt dựng
    hardsub_source: bool = True                                    # Dịch phụ đề: video có phụ đề cứng → đọc phụ đề trên hình làm lời gốc (thay Whisper)
    dub_only_subbed: bool = True                                   # lồng tiếng: chỉ câu có phụ đề Trung trên hình (lời nhân vật)
    dub_separate: bool = True                                      # lồng tiếng: tách giọng gốc khỏi nhạc nền (bỏ hẳn giọng Trung, giữ nhạc)
    dub_by_gender: bool = False                                    # lồng tiếng: câu giọng nữ (theo cao độ giọng gốc) đọc bằng voice_female
    voice_female: str = ''
    crop_box: list[float] = Field(default_factory=list)           # cắt khung hình gốc [x, y, w, h] theo % — rỗng = không cắt
    crop_fill: bool = True                                         # phóng phần đã cắt phủ kín khung (False = viền đen)
    auto_cover_text: bool = False                                  # AI quét & làm mờ mọi chữ tiếng Trung trên hình gốc
    text_scan_interval: float = Field(2.0, ge=0.5, le=5)           # giây giữa 2 khung quét (1 = kỹ, 2 = nhanh)
    text_blur_strength: int = Field(22, ge=8, le=60)               # độ mờ vùng chữ (sigma gblur)
    script_edit: bool = True
    scene_preview: bool = True
    # Hậu kỳ tự động sau lồng tiếng: căn hình theo lời + AI sửa kịch bản + tạo lại giọng
    auto_post: bool = True
    auto_fix: bool = True
    auto_publish: bool = True      # xuất xong → AI viết bài đăng theo nền tảng + thumbnail
    # Thương hiệu & khung hình
    target_resolution: str = '1920x1080'
    watermark_path: str = ''
    watermark_corner: str = 'Trên-Phải'
    watermark_size_pct: float = Field(14, ge=3, le=40)
    watermark_opacity: float = Field(0.92, ge=0.1, le=1)
    intro_path: str = ''
    outro_path: str = ''
    # Hiệu ứng hình & chuyển cảnh
    color_preset: Literal['none', 'cinematic', 'warm', 'cool', 'vivid', 'vintage', 'bw'] = 'none'
    ken_burns: bool = False
    ken_burns_zoom: float = Field(0.08, ge=0.02, le=0.2)
    vignette: bool = False
    transition: str = 'none'       # none | random | fade | dissolve | fadeblack | slideleft | wipeleft | zoomin | circleopen | smoothleft | radial | pixelize
    transition_duration: float = Field(0.5, ge=0.2, le=1.5)


class SrtJobRequest(BaseModel):
    inp: str
    out_dir: str = ''
    source_lang: str = 'Tự động'
    whisper_model: str = 'base'
    device: str = 'GPU (NVIDIA)'
    sub_layout: str = '2 dòng gọn (khuyên dùng)'
    translate: bool = True
    ai_translate: bool = False
    film_context: str = ''


class BurnJobRequest(SubtitleOptions):
    inp: str
    srt_path: str
    out_dir: str = ''


class ConfirmRequest(BaseModel):
    confirmed: bool = True
    scenes: Optional[list[dict[str, Any]]] = None
    mixer: Optional[dict[str, Any]] = None
    char_voices: Optional[dict[str, str]] = None   # Dịch phụ đề + lồng tiếng: giọng từng nhân vật chọn ở bước duyệt theo vai
    vieneu_rate: Optional[int] = Field(None, ge=-30, le=50)        # rate / pitch chỉnh lại ở bước duyệt theo vai
    vieneu_pitch: Optional[float] = Field(None, ge=-50, le=50)
    sub_custom: Optional[dict[str, Any]] = None   # Dịch phụ đề: kiểu chữ chỉnh nhanh ở timeline (cỡ chữ, in hoa)
    bilingual: Optional[bool] = None              # Dịch phụ đề: song ngữ bật / tắt ở timeline
    burn_subtitles: Optional[bool] = None  # Dịch phụ đề: con mắt ở timeline — False = không ghép phụ đề Việt (vẫn che phụ đề cũ)


class RegenRequest(BaseModel):
    text: str
    scene: dict | None = None      # cảnh hiện tại ở client (có thể đã đổi thứ tự / cắt) — ưu tiên hơn job.scenes[idx]


class DownloadJobRequest(BaseModel):
    urls: list[str]
    quality: str = 'best'          # best | 1080 | 720 | audio
    out_dir: str = ''
    titles: dict[str, str] = {}    # tiêu đề cho link video trực tiếp (để đặt tên file)
    subs: str = ''                 # tải xong tạo phụ đề bằng CapCut: '' = tắt, 'zh'/'en'/'ja'/'ko' = ngôn ngữ gốc (+ bản dịch Việt)
    poster: bool = True            # lưu ảnh bìa: phim nhiều tập → <phim>/poster.jpg, video lẻ → <tên video>-poster.jpg


class ReeditRequest(BaseModel):
    voice: str | None = None       # đổi giọng khi mở lại (để trống = giữ giọng cũ)


class DraftRequest(BaseModel):
    scenes: list[dict]
    mixer: dict | None = None


class PublishRequest(BaseModel):
    platforms: list[str] = []
    tone: str = 'hap-dan'
    extra: str = ''


class ThumbnailRequest(BaseModel):
    index: int
    text: str


class AiPolishRequest(BaseModel):
    scenes: list[dict[str, Any]]
    instruction: str = ''
