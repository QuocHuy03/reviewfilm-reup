export type JobKind = "review" | "reup" | "srt" | "burn" | "download"
export type JobStatus = "queued" | "running" | "waiting" | "done" | "error" | "cancelled"

export type Scene = {
  voiceover: string
  subtitle?: string
  clip_start: number
  clip_end: number
  orig_text?: string
  description?: string
  tts_path?: string
  tts_duration?: number
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
}

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

export type ProbeInfo = {
  url: string; platform: string; platform_label: string; title?: string; duration?: number; thumbnail?: string
  uploader?: string; width?: number; height?: number; source?: string; size?: number; error?: string
}
export type DownloadItem = { url: string; platform: string; path?: string; size?: number; error?: string }

export type Preset = { name: string; mode: string; cfg: Record<string, unknown> }

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
export type FontInfo = { family: string; vi: boolean; styles: string[]; source: "system" | "user" | "custom"; path: string }
