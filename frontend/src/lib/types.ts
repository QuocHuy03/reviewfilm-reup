export type JobKind = "review" | "reup" | "vietsub" | "srt" | "burn" | "download"
export type JobStatus = "queued" | "running" | "waiting" | "done" | "error" | "cancelled"

/** Dòng phụ đề của 1 câu Dịch phụ đề: [bắt đầu (s), kết thúc (s), lời gốc, bản dịch dòng đó?] */
export type ScenePart = [number, number, string, string?]

export type Scene = {
  voiceover: string
  subtitle?: string
  clip_start: number
  clip_end: number
  orig_text?: string
  speaker_id?: number          // lồng tiếng: nhân vật nói câu này (-1 = không phải lời thoại, không lồng tiếng)
  description?: string
  tts_path?: string
  tts_duration?: number
  tts_text?: string             // đúng câu đã đọc lúc tạo giọng — khác lời hiện tại = sửa lời mà chưa tạo lại giọng
  parts?: ScenePart[] | null    // Dịch phụ đề: các dòng phụ đề của câu [bắt đầu, kết thúc, lời gốc, bản dịch dòng đó?]
  voice_start?: number          // Dịch phụ đề + lồng tiếng: khung đọc chỉnh tay trên timeline (mặc định = giờ câu)
  voice_end?: number
  _tts_engine_used?: string
  excluded?: boolean
  [key: string]: unknown
}

export type JobResult = {
  video_path?: string
  output_path?: string
  srt_path?: string
  original_srt?: string
  vi_srt?: string
  qa?: QaReport
  qa_fixes?: QaFix[]
  publish?: PublishPack
  items?: DownloadItem[]      // job tải video
  out_dir?: string
  cast?: CastMember[]         // lồng tiếng: nhân vật AI nhận ra + giọng đang đọc
  /** Dịch phụ đề + lồng tiếng: câu đã lồng (giờ phụ đề, dòng gốc, khung đọc chỉnh tay) — để mở lại sửa trên timeline */
  dub_units?: { start: number; end: number; text: string; orig?: string; parts?: [number, number, string, string?][] | null; voice_start?: number; voice_end?: number }[]
  /** Dịch phụ đề: bản khung khác dựng cùng lượt (dọc 9:16 / ngang 16:9) */
  output_variants?: string[]
  /** phụ đề đã xuất thêm theo định dạng: srt | vtt | ass | bilingual → đường dẫn */
  sub_exports?: Record<string, string>
  dub_cast?: { labels: number[]; speakers: Record<string, { name?: string; gender?: string; count?: number }> }
}

export type CastMember = { id: number; name: string; gender: "male" | "female"; count: number; voice: string; samples: string[] }

/** Bài đăng AI theo nền tảng (backend jobs/publish.py). */
export type PublishPost = {
  title?: string
  body: string
  text: string            // văn bản dán thẳng lên nền tảng (mô tả + chương + hashtag)
  hashtags: string[]
  chapters?: { t: string; title: string }[]
  tags?: string[]
}
export type PublishPack = {
  platforms: Partial<Record<"youtube" | "shorts" | "tiktok" | "facebook" | "instagram", PublishPost>>
  thumbnail_texts: string[]
  thumbnails: { path: string; time: number; text: string; v?: number }[]
  dir: string
  tone: string
  at: string
}

/** Kết quả kiểm tra chất lượng video đã xuất (backend jobs/qa.py). */
export type QaCheck = { id: string; label: string; status: "ok" | "warn" | "fail"; detail: string }
export type QaReport = { score: number; checks: QaCheck[]; at: string }
export type QaFix = { round: number; actions: string[]; before: number; after: number; scenes: number[] }

export type JobSummary = {
  id: string
  kind: JobKind
  title: string
  status: JobStatus
  waiting: "script" | "preview" | null
  stage: string
  progress: number
  error: string
  result: JobResult
  created_at: string
  updated_at: string
  elapsed: number
  scene_count: number
  queue_pos: number
  resumable: boolean
  resume_from: string
}

/** Cookie trình duyệt người dùng tự nạp cho 1 nền tảng (vd Douyin) — không chứa giá trị cookie. */
export type SiteCookie = { site: string; label: string; has: boolean; count: number; updated: number | null; expires_in_days: number | null
  /** lần tải gần nhất nền tảng không nhận cookie này → cần xuất lại */
  rejected: boolean; last_used: number | null }

export type ProbeInfo = {
  url: string; platform: string; platform_label: string; title?: string; duration?: number; thumbnail?: string
  uploader?: string; width?: number; height?: number; source?: string; size?: number; error?: string
  /** lỗi tạm thời lúc xem trước (vd nguồn Douyin bận) — vẫn bấm Tải được, lúc tải app tự chờ */
  soft?: boolean
  /** Phim ngắn (DramaBox, ShortMax…): danh sách tập; `ep` = các tập đã chọn sẵn trong link (#ep=1-10) */
  episodes?: { num: number; title: string; locked: boolean }[]; ep?: string
}
export type DownloadItem = {
  url: string; platform: string; path?: string; size?: number; error?: string; subs?: string[]
  /** phim nhiều tập: link phim, tên phim, số tập */
  drama?: string; series?: string; ep?: number
  /** thư mục chứa file · ảnh poster đã lưu */
  folder?: string; poster?: string
  /** thời lượng video (giây) — hiện trên ảnh bìa */
  duration?: number
}

export type Preset = { name: string; mode: string; cfg: Record<string, unknown> }

/** Từ điển dịch: goc (chữ gốc) → AI dịch đúng `viet`; sai (cách dịch sai) → tự thay thành `viet`. */
export type GlossaryEntry = { goc: string; sai: string; viet: string }
export type JobDraft = { waiting: "script" | "preview"; scenes: Scene[]; mixer?: Record<string, unknown> | null; at: number }

export type JobDetail = JobSummary & {
  config: Record<string, unknown>
  scenes: Scene[]
  /** Bản nháp đang sửa ở bước chờ — chỉ dùng khi draft.waiting trùng bước hiện tại */
  draft?: JobDraft | Record<string, never>
  logs?: LogLine[]
  log_cursor?: number
}

export type LogLine = { t: number; msg: string; tag: "err" | "warn" | "ok" | "info" | "step" }

export type Voice = {
  label: string
  id: string
  group: string
  gender: "male" | "female" | "neutral"
  sample: string
  /** free: dùng ngay · key: cần API key · install: cần cài thêm trên máy */
  tier: "free" | "key" | "install"
  free: boolean
  /** false: máy chưa đủ điều kiện (thiếu key / Model Pack) — khi tạo giọng sẽ tự đổi sang Edge TTS */
  available: boolean
  need: string
}

export type SubStyle = {
  sub_font_color: string
  sub_box_enabled: boolean
  sub_box_color: string
  sub_border_width: number
  sub_font_size_factor: number
  sub_font_name: string
  sub_box_padding: number
  sub_margin_v_pct: number
  sub_line_spacing: number
  sub_text_transform: string
  sub_border_color?: string
  /** làm mờ hình ngay sau dòng chữ (khung vừa khít chữ) */
  sub_bg_blur?: boolean
}

export type Options = {
  languages: string[]
  whisper_models: string[]
  devices: string[]
  speeds: string[]
  sub_styles: Record<string, SubStyle>
  sub_layouts: Record<string, { sub_max_chars_per_chunk: number; sub_max_lines: number }>
  sub_sources: string[]
}

export type Settings = {
  output_dir: string
  whisper_model: string
  device: string
  voice: string
  sub_style: string
  sub_layout: string
  sub_custom: Partial<SubStyle>
  light_mode?: boolean
  gpu_encode?: boolean
}

/** Cấu hình máy + cài đặt đề xuất (GET /api/system/hardware). */
export type HardwareProfile = {
  cpu_threads: number; ram_gb: number; gpu: string; vram_gb: number; driver: string
  whisper_cuda: boolean; whisper_compute: string; nvenc: boolean; nvenc_reason: string
  recommend: { device: string; whisper_model: string; gpu_encode: boolean; light_mode: boolean }
  notes: string[]
}

export type ApiKey = { name: string; label: string; set: boolean; masked: string }

export type SystemInfo = {
  version: string
  python: string
  ffmpeg: boolean
  ffprobe: boolean
  gpu: string
  free_gb: number
  keys: Record<string, boolean>
  web_ai: { chatgpt: boolean; gemini: boolean }
}

/** Một đề xuất của AI hậu kỳ (POST /api/jobs/{id}/ai-polish). */
export type AiEdit = { id: number; voiceover?: string; subtitle?: string; exclude: boolean; reason: string }

/** Font cho phụ đề (GET /api/fonts). vi=false → thiếu dấu tiếng Việt, chữ sẽ lỗi. */
export type FontInfo = { family: string; vi: boolean; styles: string[]; source: "system" | "user" | "custom" | "bundled"; path: string }

/** Cài VieNeu ngay trong app: môi trường riêng + model (~1.2 GB). */
export type VieneuStatus = {
  installed: boolean
  available: boolean
  running: boolean
  step: "" | "env" | "pip" | "model" | "test" | "done"
  progress: number
  message: string
  error: string
  log: string[]
  steps: { id: string; label: string }[]
  size_mb: number
  info?: { version?: string; at?: string; size_mb?: number; test_seconds?: number }
}

/** Vùng chữ cần che (AI quét hoặc thêm tay): box = [x1, y1, x2, y2] theo tỉ lệ 0-1 của hình GỐC, thời gian = giây trên video gốc. */
/** n = cảnh (1-based) chứa vùng; g = vùng gốc AI tìm (các mảnh cắt theo cảnh của cùng 1 vùng có chung g) */
export type TextRegion = { box: number[]; t_start: number; t_end: number; off?: boolean; manual?: boolean; n?: number; g?: number }
export type TextScanState = { running: boolean; done: number; total: number; regions: TextRegion[] | null; error: string }
