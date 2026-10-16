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
    mode: Literal['review', 'reup'] = 'review'
    out_dir: str = ''
    source_lang: str = 'Tự động'
    whisper_model: str = 'base'
    device: str = 'GPU (NVIDIA)'
    minutes: int = Field(12, ge=1, le=60)
    film_context: str = ''
    scene_accurate: bool = False
    ai_translate: bool = True
    video_speed: str = '1.0x (mặc định)'
    mirror_video: bool = False
    voice: str = 'Edge TTS — Nữ Bắc (miễn phí)'
    strict_voice: bool = False
    multi_voice: bool = False
    sub_source: str = 'Theo lời đọc AI (khớp voiceover)'
    burn_subtitles: bool = True
    remove_old_sub: bool = False
    cover_boxes: list[list[float]] = Field(default_factory=list)  # [x, y, w, h] theo %
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


class RegenRequest(BaseModel):
    text: str
    scene: dict | None = None      # cảnh hiện tại ở client (có thể đã đổi thứ tự / cắt) — ưu tiên hơn job.scenes[idx]


class DownloadJobRequest(BaseModel):
    urls: list[str]
    quality: str = 'best'          # best | 1080 | 720 | audio
    out_dir: str = ''
    titles: dict[str, str] = {}    # tiêu đề cho link video trực tiếp (để đặt tên file)


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
