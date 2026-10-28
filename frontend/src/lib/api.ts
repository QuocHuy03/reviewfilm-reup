import type {
  AiEdit, ApiKey, HardwareProfile, FontInfo, GlossaryEntry, JobDetail, JobSummary, Options, Preset, ProbeInfo, PublishPack, SiteCookie, QaReport, Scene, Settings, SystemInfo, TextScanState, VieneuStatus, Voice,
} from "./types"

export const BASE_URL = window.rf?.backendUrl ?? "http://127.0.0.1:8765"

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE_URL + path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (typeof data.detail === "string") msg = data.detail
      else if (Array.isArray(data.detail)) msg = data.detail.map((d: { msg: string }) => d.msg).join("; ")
    } catch {
      /* body không phải JSON */
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export const mediaUrl = (path: string) => `${BASE_URL}/api/media?path=${encodeURIComponent(path)}`

export const api = {
  health: () => request<{ ok: boolean }>("GET", "/api/health"),
  options: () => request<Options>("GET", "/api/options"),
  system: () => request<SystemInfo>("GET", "/api/system"),
  settings: () => request<Settings>("GET", "/api/settings"),
  saveSettings: (patch: Partial<Settings>) => request<Settings>("PUT", "/api/settings", patch),
  keys: () => request<ApiKey[]>("GET", "/api/keys"),
  fonts: (refresh = false) => request<FontInfo[]>("GET", `/api/fonts${refresh ? "?refresh=true" : ""}`),
  importFont: (path: string) => request<{ family: string; vi: boolean; path: string }>("POST", "/api/fonts/import", { path }),
  saveKeys: (values: Record<string, string>) => request<ApiKey[]>("PUT", "/api/keys", { values }),
  voices: () => request<Voice[]>("GET", "/api/voices"),
  glossary: () => request<{ entries: GlossaryEntry[] }>("GET", "/api/glossary"),
  saveGlossary: (entries: GlossaryEntry[]) => request<{ entries: GlossaryEntry[] }>("PUT", "/api/glossary", { entries }),
  addGlossary: (entries: GlossaryEntry[]) => request<{ entries: GlossaryEntry[] }>("POST", "/api/glossary", { entries }),
  detectSubBox: (body: { inp: string; target_resolution: string; crop_box: number[]; crop_fill: boolean }) =>
    request<{ box: number[] | null; found: boolean; seconds: number }>("POST", "/api/jobs/detect-sub-box", body),
  redub: (id: string, body: { voice: string; voice_female: string; dub_by_gender: boolean; dub_orig_volume: number; char_voices?: Record<string, string>; vieneu_rate?: number; vieneu_pitch?: number }) =>
    request<JobSummary>("POST", `/api/jobs/${id}/redub`, body),
  resub: (id: string, body?: { scenes: Scene[]; burn_subtitles?: boolean; sub_custom?: Record<string, unknown>; bilingual?: boolean; char_voices?: Record<string, string>; vieneu_rate?: number; vieneu_pitch?: number }) =>
    request<JobSummary>("POST", `/api/jobs/${id}/resub`, body ? { confirmed: true, ...body } : undefined),
  waveform: (id: string) => request<{ rate: number; n: number; peaks: string }>("GET", `/api/jobs/${id}/waveform`),
  shots: (id: string) => request<{ cuts: number[] }>("GET", `/api/jobs/${id}/shots`),
  textScan: (id: string, interval: number, scenes: Scene[]) =>
    request<TextScanState>("POST", `/api/jobs/${id}/text-scan`, { interval, scenes: scenes.map((s) => ({ clip_start: s.clip_start, clip_end: s.clip_end, excluded: s.excluded, tts_duration: s.tts_duration })) }),
  textScanState: (id: string) => request<TextScanState>("GET", `/api/jobs/${id}/text-scan`),
  textScanCancel: (id: string) => request<TextScanState>("POST", `/api/jobs/${id}/text-scan/cancel`),
  vieneu: () => request<VieneuStatus>("GET", "/api/voices/vieneu"),
  vieneuInstall: () => request<VieneuStatus>("POST", "/api/voices/vieneu/install"),
  vieneuCancel: () => request<VieneuStatus>("POST", "/api/voices/vieneu/cancel"),
  vieneuUninstall: () => request<VieneuStatus>("DELETE", "/api/voices/vieneu"),
  testVoice: (voice: string, text?: string, fx?: { vieneu_rate: number; vieneu_pitch: number }) =>
    request<{ path: string; duration: number; engine: string; cached: boolean }>("POST", "/api/voices/test", { voice, text, ...fx }),

  jobs: () => request<JobSummary[]>("GET", "/api/jobs"),
  job: (id: string) => request<JobDetail>("GET", `/api/jobs/${id}`),
  createVideoJob: (cfg: Record<string, unknown>) => request<JobSummary>("POST", "/api/jobs/video", cfg),
  createSrtJob: (cfg: Record<string, unknown>) => request<JobSummary>("POST", "/api/jobs/srt", cfg),
  createBurnJob: (cfg: Record<string, unknown>) => request<JobSummary>("POST", "/api/jobs/burn", cfg),
  confirm: (id: string, body: { confirmed: boolean; scenes?: Scene[]; mixer?: Record<string, unknown>; char_voices?: Record<string, string>; vieneu_rate?: number; vieneu_pitch?: number }) =>
    request<{ ok: boolean }>("POST", `/api/jobs/${id}/confirm`, body),
  /** Tạo lại giọng 1 cảnh. Gửi kèm cảnh hiện tại ở client (đã có thể bị đổi thứ tự / cắt) → server không phụ thuộc số thứ tự cũ. */
  regenScene: (id: string, idx: number, text: string, scene?: Scene) =>
    request<Scene>("POST", `/api/jobs/${id}/scenes/${idx}/tts`, { text, scene }),
  aiPolish: (id: string, scenes: Scene[], instruction = "") =>
    request<{ edits: AiEdit[] }>("POST", `/api/jobs/${id}/ai-polish`, { scenes, instruction }),
  resume: (id: string) => request<JobSummary>("POST", `/api/jobs/${id}/resume`),
  publish: (id: string, body: { platforms?: string[]; tone?: string; extra?: string }) =>
    request<PublishPack>("POST", `/api/jobs/${id}/publish`, body),
  publishThumbnail: (id: string, index: number, text: string) =>
    request<PublishPack>("POST", `/api/jobs/${id}/publish/thumbnail`, { index, text }),
  saveDraft: (id: string, scenes: Scene[], mixer?: Record<string, unknown>) =>
    request<{ ok: boolean }>("PUT", `/api/jobs/${id}/draft`, { scenes, mixer }),
  presets: () => request<Preset[]>("GET", "/api/presets"),
  savePreset: (name: string, mode: string, cfg: Record<string, unknown>) => request<Preset[]>("PUT", "/api/presets", { name, mode, cfg }),
  deletePreset: (name: string) => request<Preset[]>("DELETE", `/api/presets/${encodeURIComponent(name)}`),
  createDownload: (urls: string[], quality: string, out_dir = "", titles: Record<string, string> = {}, subs = "", poster = true) =>
    request<JobSummary>("POST", "/api/jobs/download", { urls, quality, out_dir, titles, subs, poster }),
  savePoster: (image: string, title: string, out_dir = "") => request<{ path: string }>("POST", "/api/download/poster", { image, title, out_dir }),
  exportSubs: (id: string, fmt: "srt" | "vtt" | "ass" | "bilingual") => request<{ path: string }>("POST", `/api/jobs/${id}/export-subs`, { fmt }),
  retryDownload: (id: string) => request<JobSummary>("POST", `/api/jobs/${id}/download-retry`),
  siteCookies: () => request<SiteCookie[]>("GET", "/api/download/cookies"),
  saveSiteCookie: (site: string, text: string) => request<SiteCookie>("POST", `/api/download/cookies/${site}`, { text }),
  deleteSiteCookie: (site: string) => request<SiteCookie>("DELETE", `/api/download/cookies/${site}`),
  downloadProbe: (urls: string[]) => request<ProbeInfo[]>("POST", "/api/download/probe", { urls }),
  thumbUrl: (url: string, full = false) => `${BASE_URL}/api/download/thumb?url=${encodeURIComponent(url)}${full ? "&full=1" : ""}`,
  recheckQa: (id: string) => request<QaReport>("POST", `/api/jobs/${id}/qa`),
  reedit: (id: string, voice?: string) => request<JobSummary>("POST", `/api/jobs/${id}/reedit`, { voice }),
  retry: (id: string) => request<JobSummary>("POST", `/api/jobs/${id}/retry`),
  cancel: (id: string) => request<JobSummary>("POST", `/api/jobs/${id}/cancel`),
  deleteJob: (id: string) => request<{ ok: boolean }>("DELETE", `/api/jobs/${id}`),
  clearJobs: (ids: string[]) => request<{ deleted: number; skipped: number }>("POST", "/api/jobs/clear", { ids }),
  streamUrl: (id: string, since = 0) => `${BASE_URL}/api/jobs/${id}/stream?since=${since}`,

  readSrt: (path: string) => request<{ path: string; cues: { start: number; end: number; text: string }[] }>("GET", `/api/srt?path=${encodeURIComponent(path)}`),
  saveSrt: (path: string, cues: { start: number; end: number; text: string }[]) => request<{ ok: boolean }>("PUT", "/api/srt", { path, cues }),

  /** Trợ lý AI (dùng tài khoản ChatGPT / Gemini web đã đăng nhập) */
  hardware: (force = false) => request<HardwareProfile>("GET", `/api/system/hardware${force ? "?force=true" : ""}`),
  encoderStatus: (force = false) => request<{ available: boolean; gpu: string; driver: string; reason: string; enabled: boolean; min_driver: number }>(
    "GET", `/api/system/encoder${force ? "?force=true" : ""}`),
  assistantStatus: () => request<{ ready: boolean; chatgpt: boolean; gemini: boolean }>("GET", "/api/assistant/status"),
  assistantAsk: (messages: { role: "user" | "assistant"; content: string }[], job_id?: string | null, page?: string, images: string[] = []) =>
    request<{ answer: string }>("POST", "/api/assistant/ask", { messages, job_id: job_id || undefined, page, images }),
  assistantUpload: (name: string, data: string) => request<{ path: string }>("POST", "/api/assistant/upload", { name, data }),
}

export const bridge = {
  pickVideo: () => window.rf?.pickFile([{ name: "Video", extensions: ["mp4", "mkv", "avi", "mov", "webm", "flv", "m4v", "ts", "wmv"] }]) ?? Promise.resolve(null),
  pickVideos: () => window.rf?.pickFiles([{ name: "Video", extensions: ["mp4", "mkv", "avi", "mov", "webm", "flv", "m4v", "ts", "wmv"] }]) ?? Promise.resolve([] as string[]),
  pickAudio: () => window.rf?.pickFile([{ name: "Audio", extensions: ["wav", "mp3", "m4a", "flac", "ogg"] }]) ?? Promise.resolve(null),
  pickImage: () => window.rf?.pickFile([{ name: "Ảnh", extensions: ["png", "jpg", "jpeg", "webp"] }]) ?? Promise.resolve(null),
  pickFont: () => window.rf?.pickFile([{ name: "Font", extensions: ["ttf", "otf", "ttc"] }]) ?? Promise.resolve(null),
  pickSrt: () => window.rf?.pickFile([{ name: "Phụ đề", extensions: ["srt"] }]) ?? Promise.resolve(null),
  pickFolder: () => window.rf?.pickFolder() ?? Promise.resolve(null),
  open: (p: string) => window.rf?.openPath(p),
  reveal: (p: string) => window.rf?.showInFolder(p),
  available: () => Boolean(window.rf),
}
