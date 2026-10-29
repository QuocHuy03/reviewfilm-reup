import { AlertTriangle, ArrowLeft, SlidersHorizontal, Captions, Clapperboard, FileVideo, FolderOpen, FolderOutput, Languages, ListPlus, Loader2, Mic2, Rocket, Settings2, Sparkles, Wand2 } from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Field, PathInput, Section, Segmented, ToggleRow } from "@/components/common"
import { SubtitlePreview } from "@/components/SubtitlePreview"
import { SubtitleStyleEditor } from "@/components/SubtitleStyleEditor"
import type { JobDetail, SubStyle } from "@/lib/types"
import { VieneuFx, VoiceSelect, isVieneu } from "@/components/VoiceSelect"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Textarea } from "@/components/ui/textarea"
import { api, bridge, mediaUrl } from "@/lib/api"
import { fmtClock, fmtDuration } from "@/lib/format"
import { CoverBoxEditor, DEFAULT_SUB_BOX, subCoverCenter } from "@/components/CoverBoxEditor"
import { CropEditor } from "@/components/CropEditor"
import { DEFAULT_TEXT_COVER, TextCoverOptions } from "@/components/TextCoverOptions"
import { PresetBar } from "@/components/PresetBar"
import { FxPicker, fxSummary } from "@/components/FxPicker"
import { cn } from "@/lib/utils"
import { confirmAction } from "@/components/ConfirmHost"
import { ASR_LABELS, asrLabel } from "@/lib/asr"
import { LANGS, langName, voiceFits } from "@/lib/langs"

type Mode = "review" | "reup" | "vietsub"
type Source = "file" | "batch"

const PRESETS = [{ m: 8, label: "Ngắn ~8′" }, { m: 12, label: "Vừa ~12′" }, { m: 18, label: "Dài ~18′" }]
// Độ dài review tự động theo độ dài phim — cùng bảng với backend (pipelines.auto_review_minutes)
const AUTO_POINTS: [number, number][] = [[5, 0.75], [10, 0.6], [20, 0.4], [40, 0.25], [90, 0.15], [150, 0.12]]
export function autoReviewMinutes(videoSec: number) {
  const m = Math.max(0.1, videoSec / 60)
  let r = m <= AUTO_POINTS[0][0] ? AUTO_POINTS[0][1] : AUTO_POINTS[AUTO_POINTS.length - 1][1]
  for (let i = 0; i < AUTO_POINTS.length - 1; i++) {
    const [[x0, y0], [x1, y1]] = [AUTO_POINTS[i], AUTO_POINTS[i + 1]]
    if (m >= x0 && m <= x1) { r = y0 + ((y1 - y0) * (m - x0)) / (x1 - x0); break }
  }
  return Math.round(Math.max(0.5, Math.min(25, m * r)) * 10) / 10
}

export function SimpleSelect({ value, onChange, items, placeholder, labels }: {
  value: string; onChange: (v: string) => void; items: string[]; placeholder?: string
  /** tên hiển thị theo giá trị (vd mức nhận dạng giọng nói) — thiếu thì hiện chính giá trị */
  labels?: Record<string, string>
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full"><SelectValue placeholder={placeholder}>{labels?.[value] ?? value}</SelectValue></SelectTrigger>
      <SelectContent>{items.map((i) => <SelectItem key={i} value={i}>{labels?.[i] ?? i}</SelectItem>)}</SelectContent>
    </Select>
  )
}

const DEFAULT_CFG = {
  source_lang: "Tự động", whisper_model: "base", device: "GPU (NVIDIA)", minutes: 0, film_context: "",
  scene_accurate: false, ai_translate: true, video_speed: "1.0x (mặc định)", mirror_video: false,
  voice: "Edge TTS — Nữ Bắc (miễn phí)", target_lang: "vi", multi_voice: false, vieneu_rate: 0, vieneu_pitch: 0,
  sub_style: "Mặc định (chữ trắng, viền đen)", sub_layout: "2 dòng gọn (khuyên dùng)",
  sub_source: "Theo lời đọc AI (khớp voiceover)", burn_subtitles: true, sub_margin_pct: 6,
  remove_old_sub: false, sub_in_cover: true, cover_fit_text: false, auto_sub_box: true, cover_style: "blur" as "clean" | "erase" | "blur" | "reflect", cover_quality: "fast" as "fast" | "clean", dub_voice: true, hardsub_source: true, dub_only_subbed: true, dub_separate: true, dub_orig_volume: 20, dub_by_gender: false, voice_female: "", cover_boxes: [[...DEFAULT_SUB_BOX]] as number[][], sub_custom: {} as Partial<SubStyle>,
  script_edit: true, scene_preview: true, out_dir: "", bilingual: false, extra_aspect: "",
  auto_post: true, auto_fix: true, auto_publish: true, target_resolution: "1920x1080",
  watermark_path: "", watermark_corner: "Trên-Phải", watermark_size_pct: 14, watermark_opacity: 0.92, watermark_text: "", watermark_motion: "static" as "static" | "hop" | "drift" | "bounce", frame_bg: "blur" as "blur" | "black", intro_path: "", outro_path: "",
  crop_on: false, crop_box: [0, 0, 100, 84] as number[], crop_fill: true, ...DEFAULT_TEXT_COVER,
  color_preset: "none", ken_burns: false, ken_burns_zoom: 0.08, vignette: false, transition: "none", transition_duration: 0.5,
  // âm thanh: giữ nhạc nền gốc (null = theo chế độ: Reup bật, Review tắt) · hiệu ứng âm thanh (Review) · chuẩn âm lượng xuất
  keep_bg: null as boolean | null, auto_sfx: false, loudness: "youtube" as "youtube" | "off",
}


/** Whisper trên CPU tốn bao lâu so với độ dài phim (đo thật trên Xeon 2.4GHz, chế độ nhanh beam 1). */
const CPU_RATIO: Record<string, number> = { tiny: 0.04, base: 0.11, small: 0.3, medium: 0.8, large: 1.6, "large-v2": 1.6, "large-v3": 1.6 }
function whisperHint(model: string, device: string) {
  if (model === "capcut") return "CapCut online: ~10s / tập, không cần GPU · cần mạng"
  if (device.startsWith("GPU")) return "GPU: vài phút cho phim dài"
  const r = CPU_RATIO[model]
  if (!r) return "base nhanh · medium chính xác hơn"
  const min = Math.max(1, Math.round(r * 40))
  return `CPU ~${min}′ / phim 40′${r >= 0.5 ? " · small nhanh hơn" : ""}`
}

/** Danh sách video hàng loạt: mỗi dòng 1 nguồn, bỏ dòng trống / trùng. */
const batchItems = (v: string) => Array.from(new Set(v.split(/\r?\n/).map((x) => x.trim().replace(/^"|"$/g, "")).filter(Boolean)))

type Tab = "script" | "voice" | "subs" | "fx" | "post" | "output"
const TABS: { value: Tab; label: string; icon: ReactNode; desc: string }[] = [
  { value: "script", label: "Kịch bản", icon: <Clapperboard />, desc: "Độ dài, bối cảnh phim" },
  { value: "voice", label: "Giọng đọc", icon: <Mic2 />, desc: "Giọng, nhạc nền gốc, hiệu ứng âm thanh" },
  { value: "subs", label: "Phụ đề", icon: <Captions />, desc: "Kiểu chữ, che phụ đề gốc" },
  { value: "fx", label: "Hiệu ứng", icon: <Sparkles />, desc: "Chuyển cảnh, màu, zoom chậm" },
  { value: "post", label: "Hậu kỳ", icon: <Wand2 />, desc: "Tự sửa lỗi, bài đăng, logo, intro/outro" },
  { value: "output", label: "Quy trình", icon: <FolderOutput />, desc: "Dừng xem lại ở đâu, nơi lưu video" },
]

// Dịch phụ đề: không lồng tiếng / hiệu ứng / hậu kỳ dựng cảnh → chỉ các tab liên quan
const VIETSUB_TABS: Tab[] = ["script", "voice", "subs", "output"]

const CREATE_DRAFT_KEY = "rf.create.draft.v1"
type CreateDraft = { mode: Mode; source: Source; inp: string; cfg: Partial<typeof DEFAULT_CFG>; fromJob?: { id: string; title: string } }
function loadCreateDraft(): CreateDraft | null {
  try { const raw = localStorage.getItem(CREATE_DRAFT_KEY); return raw ? (JSON.parse(raw) as CreateDraft) : null } catch { return null }
}

/** Điền sẵn video vào trang Tạo video (giữ nguyên cấu hình đang có) — dùng khi bấm "Tạo Review" ở trang Tải video. */
export function openInCreate(path: string, mode: Mode) {
  const cur = loadCreateDraft()
  try { localStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify({ ...(cur ?? { cfg: {} }), mode, cfg: modeCfg(mode, cur?.cfg), source: "file", inp: path, fromJob: undefined })) } catch { /* bị chặn */ }
}

/** Chuyển sang Dịch phụ đề: phụ đề Việt phải đè lên phụ đề cũ → bật sẵn che phụ đề + phụ đề nằm giữa vùng che (như bấm tab trên trang). */
function modeCfg(mode: Mode, cfg?: Partial<typeof DEFAULT_CFG>): Partial<typeof DEFAULT_CFG> {
  return mode === "vietsub" ? { ...(cfg ?? {}), remove_old_sub: true, sub_in_cover: true, burn_subtitles: true } : (cfg ?? {})
}

/** Studio → "Chỉnh thông số": nạp lại video + toàn bộ thông số của job vào trang Tạo video để sửa rồi chạy lại. */
export function reopenJobInCreate(job: JobDetail) {
  const c = job.config ?? {}
  const cfg: Record<string, unknown> = {}
  for (const k of Object.keys(DEFAULT_CFG)) if (k in c && c[k] !== null && c[k] !== undefined) cfg[k] = c[k]
  const crop = Array.isArray(c.crop_box) ? (c.crop_box as number[]) : []
  cfg.crop_on = crop.length >= 4
  if (crop.length < 4) delete cfg.crop_box
  if (!Array.isArray(c.cover_boxes) || !(c.cover_boxes as unknown[]).length) delete cfg.cover_boxes
  // nguồn là link (bản cũ) → dùng file video đã tải về của job đó (đã bỏ ô URL — nhập link không dùng được)
  const raw = String(c.inp ?? "")
  const inp = /^https?:\/\//i.test(raw) ? String(job.result.video_path ?? "") : raw
  const mode: Mode = job.kind === "reup" || job.kind === "vietsub" ? job.kind : "review"
  const draft: CreateDraft = { mode, source: "file", inp, cfg: cfg as Partial<typeof DEFAULT_CFG>,
    fromJob: { id: job.id, title: job.title } }
  try { localStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify(draft)) } catch { /* bị chặn */ }
}

/** Trang Tải video → "Làm hàng loạt": đưa cả lô video vào chế độ Nhiều video (giữ chế độ & cấu hình đang có). */
export function openBatchInCreate(paths: string[]) {
  const cur = loadCreateDraft()
  const draft = { ...(cur ?? { mode: "review" as Mode, cfg: {} }), source: "batch" as Source, inp: paths.join("\n"), fromJob: undefined }
  draft.cfg = modeCfg(draft.mode, draft.cfg)
  try { localStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify(draft)) } catch { /* bị chặn */ }
}

/** Mở trang Tạo video ở chế độ cho trước (Review / Dịch & Reup), giữ nguyên các cấu hình khác. */
export function setCreateMode(mode: Mode) {
  const cur = loadCreateDraft()
  try { localStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify({ ...(cur ?? { source: "file", inp: "", cfg: {} }), mode, cfg: modeCfg(mode, cur?.cfg) })) } catch { /* bị chặn */ }
}

export function CreatePage() {
  const { options, settings, system, openJob, go, voices } = useStore()
  const saved = useMemo(loadCreateDraft, [])
  const [mode, setMode] = useState<Mode>(saved?.mode ?? "review")
  // bản nháp cũ đang ở ô URL (đã bỏ) → về ô File, bỏ link
  const oldUrl = (saved?.source as string | undefined) === "url"
  const [source, setSource] = useState<Source>(saved?.source === "batch" ? "batch" : "file")
  const [inp, setInp] = useState(oldUrl ? "" : saved?.inp ?? "")
  // đang chỉnh lại thông số của 1 job từ Studio → hiện thanh báo, chạy lại thì hỏi dừng job cũ
  const [fromJob, setFromJob] = useState(saved?.fromJob)
  const [cfg, setCfg] = useState(() => {
    const c = { ...DEFAULT_CFG, ...(saved?.cfg ?? {}) }
    // một lần khi lên bản có "Tự động theo video": bản nháp cũ (độ dài cố định) chuyển sang tự động
    try {
      if (!localStorage.getItem("rf_review_len_auto")) { c.minutes = 0; localStorage.setItem("rf_review_len_auto", "1") }
      // Dịch phụ đề: lồng tiếng mặc định BẬT (bản nháp cũ đang tắt → bật một lần)
      if (!localStorage.getItem("rf_vietsub_dub_on")) { c.dub_voice = true; localStorage.setItem("rf_vietsub_dub_on", "1") }
      // khung mờ mặc định: cả dải cố định như CapCut (bản nháp cũ đang "vừa theo chữ" → đổi một lần)
      if (!localStorage.getItem("rf_vietsub_band")) { c.cover_fit_text = false; c.auto_sub_box = true; localStorage.setItem("rf_vietsub_band", "1") }
      // kiểu che mặc định: xoá sạch nét chữ (đẹp nhất) — đổi một lần cho bản nháp cũ
      // kiểu che mặc định: làm mờ cả dải phụ đề y như Review phim — đổi một lần cho bản nháp cũ
      // lồng tiếng: nam 1 giọng, nữ 1 giọng — bật chia giọng theo giới tính một lần cho bản nháp cũ
      // không tự chọn giọng nam / nữ: bản nháp cũ đang để giọng nữ mặc định do app tự gán → về 1 giọng (một lần)
      if (!localStorage.getItem("rf_single_voice")) {
        if (c.voice_female === "Edge TTS — Nữ Bắc (miễn phí)") { c.dub_by_gender = false; c.voice_female = "" }
        localStorage.setItem("rf_single_voice", "1")
      }
      // pitch VieNeu đổi từ nửa cung sang Hz → số cũ (±6) không còn đúng nghĩa, về 0 (một lần)
      if (!localStorage.getItem("rf_pitch_hz")) { c.vieneu_pitch = 0; localStorage.setItem("rf_pitch_hz", "1") }
      if (!localStorage.getItem("rf_cover_review_blur")) { c.cover_style = "blur"; localStorage.setItem("rf_cover_review_blur", "1") }
    } catch { /* bị chặn */ }
    return c
  })
  // Tự lưu form — trang này bị dựng lại mỗi lần chuyển trang
  useEffect(() => {
    const t = setTimeout(() => { try { localStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify({ mode, source, inp, cfg, fromJob })) } catch { /* bị chặn / đầy */ } }, 400)
    return () => clearTimeout(t)
  }, [mode, source, inp, cfg, fromJob])
  const [starting, setStarting] = useState(false)
  const [tab, setTab] = useState<Tab>("script")
  // chấm cam trên tab = đang bật tuỳ chọn khác mặc định trong tab đó (để biết mà mở xem)
  const tabDot: Record<Tab, boolean> = {
    script: !!cfg.film_context.trim() || cfg.scene_accurate,
    voice: cfg.multi_voice || !cfg.video_speed.startsWith("1.0x"),
    fx: cfg.color_preset !== "none" || cfg.ken_burns || cfg.vignette || cfg.transition !== "none",
    subs: !cfg.burn_subtitles || cfg.remove_old_sub || Object.keys(cfg.sub_custom).length > 0,
    post: !!cfg.watermark_path || !!cfg.intro_path || !!cfg.outro_path || cfg.mirror_video || cfg.target_resolution !== "1920x1080",
    output: !cfg.script_edit || !cfg.scene_preview,
  }
  const set = <K extends keyof typeof cfg>(k: K, v: (typeof cfg)[K]) => setCfg((c) => ({ ...c, [k]: v }))
  const vfx = { vieneu_rate: cfg.vieneu_rate, vieneu_pitch: cfg.vieneu_pitch }
  const voiceId = (label: string) => voices.find((v) => v.label === label)?.id
  const usesVieneu = isVieneu(voiceId(cfg.voice)) || (mode === "vietsub" && cfg.dub_by_gender && isVieneu(voiceId(cfg.voice_female)))

  useEffect(() => {
    // đã có bản nháp cấu hình của người dùng → không ghi đè bằng mặc định trong Cài đặt
    if (!settings || Object.keys(saved?.cfg ?? {}).length) return
    // Máy không có GPU NVIDIA → mặc định CPU (tránh Whisper thử GPU rồi mới fallback)
    const device = system && !system.gpu && settings.device.startsWith("GPU") ? "CPU" : settings.device
    setCfg((c) => ({ ...c, whisper_model: settings.whisper_model, device, voice: settings.voice,
      sub_style: settings.sub_style, sub_layout: settings.sub_layout, out_dir: settings.output_dir, sub_custom: settings.sub_custom ?? {} }))
  }, [settings, system])

  const preset = options?.sub_styles[cfg.sub_style]
  const style = preset ? { ...preset, ...cfg.sub_custom } : undefined
  const webAi = Boolean(system?.web_ai?.chatgpt || system?.web_ai?.gemini)
  const needsKey = mode === "review" && system && !system.web_ai?.gemini
  const isLocalFile = source === "file" && /\.(mp4|mkv|mov|webm|m4v)$/i.test(inp)

  // Độ dài video gốc (file trên máy) — để cảnh báo khi độ dài review chọn dài hơn video
  const [srcDur, setSrcDur] = useState(0)
  // 0 = tự động theo video; chọn "Tuỳ chỉnh" thì giữ ô nhập kể cả khi số trùng một mức có sẵn
  const [customOpen, setCustomOpen] = useState(false)
  const lengthMode = !cfg.minutes ? "auto" : !customOpen && PRESETS.some((p) => p.m === cfg.minutes) ? String(cfg.minutes) : "custom"
  const reviewMins = cfg.minutes || (srcDur > 0 ? autoReviewMinutes(srcDur) : 0)
  // phụ đề mới nằm giữa vùng che phụ đề cũ (cùng quy tắc với lúc dựng) — null = đặt theo "Cách đáy"
  const subCenter = cfg.remove_old_sub && cfg.sub_in_cover ? subCoverCenter(cfg.cover_boxes) : null
  useEffect(() => {
    setSrcDur(0)
    if (!isLocalFile) return
    const v = document.createElement("video")
    v.preload = "metadata"
    v.onloadedmetadata = () => setSrcDur(Number.isFinite(v.duration) ? v.duration : 0)
    v.src = mediaUrl(inp)
    return () => { v.removeAttribute("src"); v.load() }
  }, [inp, isLocalFile])

  const issues = useMemo(() => {
    const out: string[] = []
    if (!inp.trim()) out.push("Chưa chọn video / URL")
    else if (source === "batch" && batchItems(inp).length < 2) out.push("Hàng loạt cần từ 2 video trở lên (1 video thì dùng File / URL)")
    if (needsKey) out.push("Chế độ Review cần đăng nhập Gemini (Cài đặt → Tài khoản AI)")
    if (system && !system.ffmpeg) out.push("Thiếu ffmpeg")
    if (mode === "vietsub" && cfg.dub_voice && cfg.dub_by_gender && !cfg.voice_female) out.push("Chọn giọng cho nhân vật nữ (tab Lồng tiếng)")
    return out
  }, [inp, needsKey, system, source, mode, cfg.dub_voice, cfg.dub_by_gender, cfg.voice_female])

  const startBatch = async () => {
    const list = batchItems(inp)
    setStarting(true)
    let ok = 0
    const failed: { item: string; msg: string }[] = []
    for (const item of list) {
      try {
        await api.createVideoJob({ ...cfg, mode, inp: item, script_edit: false, scene_preview: false,
          cover_boxes: cfg.remove_old_sub ? cfg.cover_boxes : [], crop_box: cfg.crop_on ? cfg.crop_box : [] })
        ok++
      } catch (e) { failed.push({ item, msg: (e as Error).message }) }
    }
    setStarting(false)
    const name = (x: string) => x.split(/[\\/]/).pop() ?? x
    if (failed.length) toast.error(`${failed.length} video không tạo được — đã giữ lại trong ô để sửa`,
      { description: failed.slice(0, 3).map((f) => `${name(f.item)}: ${f.msg}`).join("\n") })
    setInp(failed.map((f) => f.item).join("\n"))   // chỉ giữ lại dòng lỗi
    if (ok) { toast.success(`Đã xếp hàng ${ok} video — chạy lần lượt`, { description: "Theo dõi ở trang Lịch sử" }); go("jobs") }
  }

  const start = async () => {
    if (source === "batch") return startBatch()
    if (fromJob) {
      // job cũ còn đang chạy / chờ → hỏi dừng để không chạy 2 bản cùng lúc
      const old = await api.job(fromJob.id).catch(() => null)
      if (old && ["running", "queued", "waiting"].includes(old.status)) {
        const stop = await confirmAction({ title: "Dừng job cũ rồi chạy lại?", action: "Dừng job cũ & chạy lại", cancel: "Giữ cả 2",
          desc: `Job "${fromJob.title}" vẫn đang chạy. Dừng nó để chạy bản mới với thông số vừa chỉnh — hoặc giữ cả 2 (bản mới xếp hàng sau).` })
        if (stop) await api.cancel(fromJob.id).catch(() => {})
      }
    }
    setStarting(true)
    try {
      const job = await api.createVideoJob({ ...cfg, mode, inp: inp.trim(),
        cover_boxes: cfg.remove_old_sub ? cfg.cover_boxes : [], crop_box: cfg.crop_on ? cfg.crop_box : [] })
      toast.success(job.queue_pos ? `Đã xếp hàng (#${job.queue_pos}) — chạy khi job trước xong` : "Đã bắt đầu xử lý", { description: job.title })
      setInp("")                       // giữ cấu hình cho video tiếp theo, chỉ xoá nguồn vừa chạy
      setFromJob(undefined)
      openJob(job.id)
    } catch (e) {
      toast.error("Không thể bắt đầu", { description: (e as Error).message })
    } finally {
      setStarting(false)
    }
  }

  if (!options) return null

  // Ngôn ngữ lồng tiếng & phụ đề: đổi ngôn ngữ → giọng đang chọn không đọc được tiếng đó thì tự chọn giọng hợp (miễn phí, cùng giới)
  const pickVoice = (lang: string, cur: string, female: boolean) => {
    if (voices.some((v) => v.label === cur && voiceFits(v, lang))) return cur
    const ok = voices.filter((v) => v.available && v.tier === "free" && voiceFits(v, lang))
    return (ok.find((v) => v.gender === (female ? "female" : "male") && v.group === "CapCut") ?? ok.find((v) => v.gender === (female ? "female" : "male")) ?? ok[0])?.label ?? cur
  }
  const setLang = (lang: string) => setCfg((c) => ({ ...c, target_lang: lang, voice: pickVoice(lang, c.voice, !c.dub_by_gender),
    voice_female: c.voice_female ? pickVoice(lang, c.voice_female, true) : c.voice_female, multi_voice: lang === "vi" ? c.multi_voice : false }))
  const langField = (
    <Field label="Ngôn ngữ lồng tiếng & phụ đề" hint={cfg.target_lang === "vi" ? "Mặc định tiếng Việt." : `AI viết / dịch lời đọc và phụ đề sang ${langName(cfg.target_lang)}, đọc bằng giọng ${langName(cfg.target_lang)}.`}>
      <Select value={cfg.target_lang} onValueChange={setLang}>
        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent className="max-h-80">
          {LANGS.map((l) => <SelectItem key={l.code} value={l.code}>{l.name} · {voices.filter((v) => voiceFits(v, l.code)).length} giọng</SelectItem>)}
        </SelectContent>
      </Select>
    </Field>
  )

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_360px] gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
      {/* ---------- Form ---------- */}
      <div className="min-h-0 overflow-y-auto pr-1 pb-6">
        <div className="flex flex-col gap-4">
          {fromJob && (
            <div className="flex items-center gap-3 rounded-xl border border-primary/40 bg-primary/5 px-4 py-2.5">
              <SlidersHorizontal className="size-4 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium">Đang chỉnh lại thông số</p>
                <p className="truncate text-[11px] text-muted-foreground" title={fromJob.title}>Từ job: {fromJob.title} — sửa xong bấm <b>Bắt đầu</b> để chạy lại.</p>
              </div>
              <Button variant="outline" size="sm" onClick={() => openJob(fromJob.id)}><ArrowLeft /> Về Studio</Button>
              <Button variant="ghost" size="sm" onClick={() => setFromJob(undefined)} title="Giữ thông số, coi như tạo video mới">Bỏ liên kết</Button>
            </div>
          )}
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-1.5">
            <Segmented value={mode} onChange={(m) => {
              setMode(m)
              // Dịch phụ đề: phụ đề Việt phải đè lên phụ đề cũ → bật sẵn che phụ đề + phụ đề nằm giữa vùng che
              if (m === "vietsub") setCfg((c) => ({ ...c, remove_old_sub: true, sub_in_cover: true, burn_subtitles: true }))
              if (m === "vietsub" && !VIETSUB_TABS.includes(tab)) setTab("script")
            }} items={[
              { value: "review", label: "Tạo Review", icon: <Wand2 /> },
              { value: "reup", label: "Dịch & Reup", icon: <Languages /> },
              { value: "vietsub", label: "Dịch phụ đề", icon: <Captions /> },
            ]} />
            <div className="ml-auto pr-1">
              <PresetBar bare mode={mode} cfg={cfg} onApply={(m, c) => { setMode(m === "reup" || m === "vietsub" ? m : "review"); setCfg({ ...DEFAULT_CFG, ...c }) }} />
            </div>
          </div>

          <Section title="Video nguồn" icon={<FileVideo />}
            desc={mode === "review" ? "Nhận dạng giọng nói → AI xem phim & viết kịch bản → lồng tiếng → dựng video"
              : mode === "vietsub" ? "Nhận dạng giọng nói → dịch tiếng Việt → che phụ đề cũ & ghép phụ đề Việt — giữ nguyên tiếng gốc"
              : "Nhận dạng giọng nói → dịch → lồng tiếng → dựng video"}
            action={<Segmented size="sm" value={source} onChange={(v) => { setSource(v); setInp("") }} items={[
              { value: "file", label: "File", icon: <FileVideo /> },
              { value: "batch", label: "Nhiều video", icon: <ListPlus /> }]} />}>
            {source === "file" && <PathInput value={inp} onChange={setInp} pick={bridge.pickVideo} placeholder="Chọn file video (.mp4, .mkv, .mov…)" />}
            {source === "batch" && (
              <div className="flex flex-col gap-2">
                <Textarea value={inp} onChange={(e) => setInp(e.target.value)} rows={5} className="font-mono text-xs placeholder:font-sans"
                  placeholder={"Mỗi dòng 1 file video\nC:\\Phim\\tap1.mp4\nC:\\Phim\\tap2.mp4\n(video trên mạng: tải ở trang Tải video rồi bấm Làm hàng loạt)"} />
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <Button variant="outline" size="sm" disabled={!bridge.available()}
                    onClick={async () => { const fs = await bridge.pickVideos(); if (fs.length) setInp((v) => [...batchItems(v), ...fs].join("\n")) }}>
                    <FolderOpen /> Chọn nhiều file
                  </Button>
                  <span>{batchItems(inp).length} video · chạy lần lượt, tự động hoàn toàn (không dừng chờ sửa từng video)</span>
                </div>
                <p className="text-[11px] text-muted-foreground">Mẹo: chọn <b className="text-foreground">Mẫu kênh</b> ở góc trên để cả lô dùng chung giọng, phụ đề, logo, intro / outro của kênh.</p>
              </div>
            )}
            <div className="grid grid-cols-3 gap-3">
              <Field label="Ngôn ngữ video gốc">
                <SimpleSelect value={cfg.source_lang} onChange={(v) => set("source_lang", v)} items={options.languages} />
              </Field>
              <Field label="Nhận dạng giọng nói" hint={whisperHint(cfg.whisper_model, cfg.device)}>
                <SimpleSelect value={cfg.whisper_model} onChange={(v) => set("whisper_model", v)} items={options.whisper_models} labels={ASR_LABELS} />
              </Field>
              <Field label="Thiết bị xử lý">
                <SimpleSelect value={cfg.device} onChange={(v) => set("device", v)} items={options.devices} />
              </Field>
            </div>
            <ToggleRow label="Cắt khung hình" checked={cfg.crop_on} onChange={(v) => set("crop_on", v)}
              desc="Cắt bỏ hẳn dải phụ đề cứng / logo / viền ở mép video gốc rồi phóng phần còn lại cho đầy khung — sạch hơn làm mờ." />
            {cfg.crop_on && (
              <CropEditor src={isLocalFile ? mediaUrl(inp) : undefined} resolution={cfg.target_resolution} box={cfg.crop_box} fill={cfg.crop_fill}
                onChange={(b) => set("crop_box", b)} onFill={(v) => set("crop_fill", v)} />
            )}
            {mode === "vietsub" && <>
              <ToggleRow label="Video gốc có phụ đề Trung in sẵn" checked={cfg.hardsub_source && cfg.remove_old_sub}
                onChange={(v) => setCfg((c) => ({ ...c, hardsub_source: v, remove_old_sub: v, dub_only_subbed: v }))}
                desc={cfg.hardsub_source && cfg.remove_old_sub ? "Đọc phụ đề trên hình làm lời gốc, xoá phụ đề cũ." : "Nghe giọng nói để lấy lời gốc, không xoá phụ đề cũ."} />
              <ToggleRow label="Hiện phụ đề tiếng Việt trên video" checked={cfg.burn_subtitles} onChange={(v) => set("burn_subtitles", v)}
                desc={cfg.burn_subtitles ? "Ghép chữ Việt vào video (kèm file .srt)." : "Video không có chữ — vẫn xuất file .srt riêng."} />
              {cfg.burn_subtitles && (
                <ToggleRow label="Phụ đề song ngữ" checked={!!cfg.bilingual} onChange={(v) => set("bilingual", v)}
                  desc={cfg.bilingual ? "Dòng Việt + lời gốc nhỏ bên dưới (kiểu học tiếng)." : "Chỉ hiện dòng tiếng Việt."} />
              )}
              <ToggleRow label={cfg.target_resolution === "1080x1920" ? "Xuất thêm bản ngang 16:9" : "Xuất thêm bản dọc 9:16"} checked={!!cfg.extra_aspect}
                onChange={(v) => set("extra_aspect", v ? (cfg.target_resolution === "1080x1920" ? "16:9" : "9:16") : "")}
                desc={cfg.extra_aspect ? (cfg.target_resolution === "1080x1920" ? "Thêm bản cho YouTube — dựng cùng lượt." : "Thêm bản cho TikTok / Shorts: nền mờ, phụ đề to dưới video — dựng cùng lượt.")
                  : "Chỉ xuất 1 khung hình."} />
            </>}
            {mode === "vietsub" && (
              <ToggleRow label="Lồng tiếng Việt" checked={cfg.dub_voice} onChange={(v) => set("dub_voice", v)}
                desc={cfg.dub_voice ? "Giọng & tuỳ chọn ở tab Lồng tiếng bên dưới." : "Tắt: chỉ ghép phụ đề Việt, giữ nguyên tiếng gốc."} />
            )}
            <TextCoverOptions value={cfg} onChange={(p) => setCfg((c) => ({ ...c, ...p }))}
              minutes={mode === "review" ? reviewMins || undefined : undefined} reup={mode === "reup"} />
          </Section>

          {/* Các phần cấu hình gom thành tab — đỡ phải cuộn trang dài */}
          <div className="flex flex-col gap-3">
            <div role="tablist" className="flex gap-1 overflow-x-auto rounded-xl border border-border bg-card p-1 [scrollbar-width:none]">
              {TABS.filter((t) => mode !== "vietsub" || VIETSUB_TABS.includes(t.value)).map((t) => (
                <button key={t.value} role="tab" aria-selected={tab === t.value} onClick={() => setTab(t.value)} title={t.desc}
                  className={cn("relative flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg px-2 text-[13px] whitespace-nowrap transition xl:px-3 [&_svg]:hidden [&_svg]:size-4 xl:[&_svg]:inline",
                    tab === t.value ? "bg-muted font-medium text-foreground shadow-sm" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground")}>
                  {t.icon}
                  {t.value === "script" && mode !== "review" ? "Bản dịch" : t.value === "voice" && mode === "vietsub" ? "Lồng tiếng" : t.label}
                  {tabDot[t.value] && <span className="size-1.5 rounded-full bg-primary" title="Đang bật tuỳ chọn khác mặc định" />}
                </button>
              ))}
            </div>

            {tab === "script" && (
              <Section title={mode === "review" ? "Kịch bản review" : "Dịch phụ đề"} icon={<Clapperboard />}
                desc={mode === "review" ? "AI xem phim và viết lời thuyết minh" : "Dịch lời thoại sang tiếng Việt"}>
              {mode === "review" ? (
                <>
                  <Field label="Độ dài review">
                    <div className="flex flex-wrap items-center gap-2">
                      <Segmented size="sm" value={lengthMode} onChange={(v) => {
                        setCustomOpen(v === "custom")
                        set("minutes", v === "auto" ? 0 : v === "custom" ? (cfg.minutes || Math.max(1, Math.round(reviewMins)) || 12) : Number(v))
                      }} items={[
                        { value: "auto", label: "Tự động theo video", icon: <Wand2 /> },
                        ...PRESETS.map((p) => ({ value: String(p.m), label: p.label })),
                        { value: "custom", label: "Tuỳ chỉnh" },
                      ]} />
                      {lengthMode === "custom" && (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Input type="number" min={1} max={60} value={cfg.minutes || ""} className="h-8 w-16 text-center" autoFocus
                            onChange={(e) => set("minutes", Math.max(1, Math.min(60, Math.round(Number(e.target.value)) || 1)))} /> phút
                        </div>
                      )}
                    </div>
                    <p className="mt-1.5 text-[11px] text-muted-foreground">
                      {lengthMode === "auto"
                        ? srcDur > 0
                          ? <>Phim {fmtDuration(srcDur)} → review khoảng <b className="text-foreground">{reviewMins} phút</b> — kể đủ ý, lời khớp hình từng cảnh.</>
                          : <>Bám theo độ dài video: phim 20′ → ~8′ · phim 90′ → ~13′ · phim 2 giờ → ~16′. Phim ngắn kể gần hết, phim dài tóm gọn.</>
                        : "Độ dài cố định — dùng khi kênh cần video đúng thời lượng."}
                    </p>
                    {srcDur > 0 && cfg.minutes > 0 && cfg.minutes * 60 > srcDur && (
                      <p className="mt-1.5 flex items-start gap-1.5 rounded-md border border-warning/30 bg-warning/5 px-2.5 py-1.5 text-[11px] text-warning">
                        <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                        Video gốc chỉ dài {fmtClock(srcDur)} — kịch bản sẽ tự rút còn ~{Math.round(srcDur * 0.95)} giây để lời đọc khớp hình từng cảnh.
                      </p>
                    )}
                  </Field>
                  <ToggleRow label="Phân tích chuyên sâu" checked={cfg.scene_accurate} onChange={(v) => set("scene_accurate", v)}
                    desc="Cắt cảnh theo scene thật (PySceneDetect) + AI xem kỹ từng chương — lời đọc khớp hình hơn, chạy chậm hơn." />
                </>
              ) : (
                <ToggleRow label="Dịch bằng AI (ChatGPT / Gemini)" checked={cfg.ai_translate} onChange={(v) => set("ai_translate", v)}
                  desc={webAi ? "Dịch tự nhiên hơn bằng tài khoản đã đăng nhập." : "Chưa đăng nhập tài khoản AI — sẽ dùng Google dịch miễn phí."} />
              )}
              <Field label="Bối cảnh phim (tuỳ chọn)" hint="Tên phim, thể loại, tên nhân vật… giúp AI viết/dịch đúng hơn.">
                <Textarea value={cfg.film_context} onChange={(e) => set("film_context", e.target.value)} rows={2} placeholder="VD: Phim hành động Hàn Quốc, nhân vật chính là thám tử Kang…" />
              </Field>
              </Section>
            )}

            {tab === "voice" && mode === "vietsub" && (
              <Section title={cfg.target_lang === "vi" ? "Lồng tiếng Việt" : `Lồng tiếng — ${langName(cfg.target_lang)}`} icon={<Mic2 />} desc="Đọc đúng lúc từng câu thoại gốc — không kéo giãn hình, không chồng tiếng">
                {langField}
                {!cfg.dub_voice && (
                  <p className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                    Đang tắt lồng tiếng — chỉ ghép phụ đề, giữ tiếng gốc.
                    <Button size="sm" variant="outline" className="h-7" onClick={() => set("dub_voice", true)}>Bật lồng tiếng</Button>
                  </p>
                )}
                <div className={cn("flex flex-col gap-4", !cfg.dub_voice && "pointer-events-none opacity-50")}>
                  <ToggleRow label="Giọng riêng cho nhân vật nam / nữ" checked={cfg.dub_by_gender} onChange={(v) => set("dub_by_gender", v)}
                    desc={cfg.dub_by_gender ? "Nhân vật nam đọc giọng nam, nữ đọc giọng nữ bên dưới. Ở bước duyệt vẫn đổi được giọng từng nhân vật."
                      : "Tắt: 1 giọng cho mọi nhân vật — đúng giọng bạn chọn, không tự đổi. Ở bước duyệt vẫn đổi được giọng từng nhân vật."} />
                  <div className={cn("grid gap-4", cfg.dub_by_gender && "xl:grid-cols-2")}>
                    <div className="flex min-w-0 flex-col gap-1.5">
                      <span className="text-xs font-medium text-muted-foreground">{cfg.dub_by_gender ? "Giọng nhân vật nam" : "Giọng đọc"}</span>
                      <VoiceSelect value={cfg.voice} onChange={(v) => set("voice", v)} fx={vfx} lang={cfg.target_lang} />
                    </div>
                    {cfg.dub_by_gender && (
                      <div className="flex min-w-0 flex-col gap-1.5">
                        <span className="text-xs font-medium text-muted-foreground">Giọng nhân vật nữ</span>
                        <VoiceSelect value={cfg.voice_female} onChange={(v) => set("voice_female", v)} fx={vfx} lang={cfg.target_lang} />
                      </div>
                    )}
                  </div>
                  {usesVieneu && <VieneuFx value={vfx} onChange={(p) => setCfg((c) => ({ ...c, ...p }))} />}
                  <details className="group rounded-lg border border-border">
                    <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">
                      Tuỳ chọn nâng cao
                      <span className="text-[11px] font-normal">
                        {cfg.dub_separate ? "tách giọng gốc" : `tiếng gốc ${cfg.dub_orig_volume}%`}{cfg.dub_only_subbed ? " · chỉ câu có phụ đề" : ""}
                        <span className="ml-1.5 inline-block transition group-open:rotate-90">›</span>
                      </span>
                    </summary>
                    <div className="flex flex-col gap-3 border-t border-border px-3 py-3">
                      <ToggleRow label="Tách giọng gốc, giữ nhạc nền" checked={cfg.dub_separate} onChange={(v) => set("dub_separate", v)}
                        desc="Lúc giọng Việt đọc thì tắt hẳn giọng Trung, nhạc nền giữ nguyên (tải model ~64MB lần đầu)." />
                      {!cfg.dub_separate && (
                        <Field label={`Tiếng gốc khi có lời Việt: ${cfg.dub_orig_volume}%`}>
                          <Slider value={[cfg.dub_orig_volume]} min={0} max={60} step={5} onValueChange={([v]) => set("dub_orig_volume", v)} className="mt-2.5" />
                        </Field>
                      )}
                      <ToggleRow label="Chỉ lồng câu có phụ đề Trung trên hình" checked={cfg.dub_only_subbed} onChange={(v) => set("dub_only_subbed", v)}
                        desc="Tiếng đám đông / lời nền không có phụ đề thì giữ tiếng gốc." />
                    </div>
                  </details>
                </div>
              </Section>
            )}
            {tab === "voice" && mode !== "vietsub" && (
              <Section title="Giọng đọc" icon={<Mic2 />} desc="CapCut & Edge TTS miễn phí · FPT.AI cao cấp · VieNeu offline">
              {langField}
              <VoiceSelect value={cfg.voice} onChange={(v) => set("voice", v)} fx={vfx} lang={cfg.target_lang} />
              {(usesVieneu || cfg.multi_voice) && <VieneuFx value={vfx} onChange={(p) => setCfg((c) => ({ ...c, ...p }))} />}
                <div className="grid grid-cols-2 gap-3">
                <Field label="Tốc độ video & giọng">
                  <SimpleSelect value={cfg.video_speed} onChange={(v) => set("video_speed", v)} items={options.speeds} />
                </Field>
                </div>
              {mode === "review" && cfg.target_lang === "vi" && (
                <ToggleRow label="Phân vai nhiều giọng" checked={cfg.multi_voice} onChange={(v) => set("multi_voice", v)}
                  desc="AI nhận diện nhân vật, mỗi vai một giọng VieNeu (cần đăng nhập ChatGPT hoặc Gemini)." />
              )}
              <ToggleRow label="Giữ nhạc nền & tiếng động gốc" checked={cfg.keep_bg ?? mode === "reup"} onChange={(v) => set("keep_bg", v)}
                desc="Tách bỏ giọng gốc, giữ nhạc + tiếng động dưới lời Việt — nghe như phim lồng tiếng thật. Chạy ngầm trong lúc AI viết kịch bản." />
              {mode === "review" && (
                <ToggleRow label="Hiệu ứng âm thanh tự động" checked={cfg.auto_sfx} onChange={(v) => set("auto_sfx", v)}
                  desc={'Tiếng "vút" khi chuyển cảnh nhảy đoạn, "bùm" ở đoạn cao trào — video review có nhịp hơn.'} />
              )}
              </Section>
            )}

            {tab === "subs" && (
              <Section title="Phụ đề" icon={<Captions />} desc="Kiểu chữ, bố cục, vị trí phụ đề · che phụ đề gốc / logo">
              <ToggleRow label="Ghép phụ đề vào video" checked={cfg.burn_subtitles} onChange={(v) => set("burn_subtitles", v)} />
              <div className={cn("grid grid-cols-2 gap-3", !cfg.burn_subtitles && "pointer-events-none opacity-50")}>
                <Field label="Phong cách">
                  <SimpleSelect value={cfg.sub_style} onChange={(v) => set("sub_style", v)} items={Object.keys(options.sub_styles)} />
                </Field>
                <Field label="Bố cục dòng">
                  <SimpleSelect value={cfg.sub_layout} onChange={(v) => set("sub_layout", v)} items={Object.keys(options.sub_layouts)} />
                </Field>
                <Field label="Nguồn phụ đề">
                  <SimpleSelect value={cfg.sub_source} onChange={(v) => set("sub_source", v)} items={options.sub_sources} />
                </Field>
                <Field label={subCenter != null ? "Vị trí: giữa vùng che phụ đề" : `Cách đáy: ${cfg.sub_margin_pct}%`}>
                  <Slider value={[cfg.sub_margin_pct]} min={2} max={40} step={1} onValueChange={([v]) => set("sub_margin_pct", v)}
                    className={cn("mt-2.5", subCenter != null && "pointer-events-none opacity-40")} disabled={subCenter != null} />
                </Field>
              </div>
              {cfg.burn_subtitles && <SubtitleStyleEditor base={preset} custom={cfg.sub_custom} onChange={(c) => set("sub_custom", c)} />}
              {mode === "vietsub" ? (
                <Field label="Che phụ đề cũ">
                  <Segmented size="sm" value={cfg.cover_quality} onChange={(v) => set("cover_quality", v)}
                    items={[{ value: "fast", label: "Nhanh (khuyên dùng)" }, { value: "clean", label: "Xoá sạch nét chữ (chậm)" }]} />
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {cfg.cover_quality === "clean"
                      ? "AI xoá từng nét chữ Trung trên từng khung hình — đẹp nhất nhưng rất chậm (~1–1.5 phút xử lý / 1 phút video)."
                      : "Chỉ che đúng khung chữ Trung của từng câu, đúng lúc câu đó hiện — không che cả dải suốt video, không thêm lượt xử lý từng khung, nhanh hơn nhiều."}
                  </p>
                </Field>
              ) : (
              <Field label="Kiểu che chữ cũ / logo">
                <Segmented size="sm" value={cfg.cover_style} onChange={(v) => set("cover_style", v)}
                  items={[{ value: "blur", label: "Làm mờ (như Review)" }, { value: "erase", label: "Xoá nhẹ" }, { value: "reflect", label: "Phản chiếu" }, { value: "clean", label: "Xoá sạch nét chữ" }]} />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {cfg.cover_style === "clean"
                    ? "Xoá sạch nét chữ chỉ có ở chế độ Dịch phụ đề — chế độ này sẽ dùng Xoá nhẹ."
                    : cfg.cover_style === "erase"
                    ? "Lấp cả vùng chữ bằng hình xung quanh như xoá logo — nhanh, ít vết; chỉ che lúc có chữ."
                    : cfg.cover_style === "reflect"
                    ? "Lấy dải hình ngay trên vùng che, lật ngược rồi phủ lên — nền trơn (trời, tường, sàn) trông như không có chữ. Chữ Trung AI quét trong cảnh vẫn dùng Xoá nhẹ."
                    : "Như chế độ Review phim: làm mờ cố định cả dải phụ đề cũ (và vùng logo) suốt video, phụ đề Việt nằm trên dải mờ — đều, nhanh, chắc chắn không lộ chữ cũ."}
                </p>
              </Field>
              )}
              <ToggleRow label="Che phụ đề gốc / logo" checked={cfg.remove_old_sub} onChange={(v) => set("remove_old_sub", v)}
                desc="Làm mờ dòng chữ cứng / logo có sẵn trong video gốc — kéo khung ngay trên khung hình để che vừa khít." />
              {cfg.remove_old_sub && (
                <>
                  <CoverBoxEditor src={isLocalFile ? mediaUrl(inp) : undefined} resolution={cfg.target_resolution}
                    boxes={cfg.cover_boxes} onChange={(v) => set("cover_boxes", v)}
                    subText={cfg.burn_subtitles && cfg.sub_in_cover ? "Phụ đề mới nằm giữa vùng che" : undefined}
                    fitText={mode === "vietsub" && cfg.sub_in_cover && cfg.cover_fit_text}
                    onAutoDetect={isLocalFile ? async () => {
                      try {
                        const r = await api.detectSubBox({ inp: inp.trim(), target_resolution: cfg.target_resolution, crop_box: cfg.crop_on ? cfg.crop_box : [], crop_fill: cfg.crop_fill })
                        if (!r.box) { toast.info("Không thấy phụ đề cứng trong video", { description: `Đã xem 24 khung hình (${r.seconds}s)` }); return null }
                        toast.success("Đã căn vùng che theo phụ đề cũ", { description: `Dọc ${r.box[1]}% · cao ${r.box[3]}% · rộng ${r.box[2]}% (${r.seconds}s)` })
                        return r.box
                      } catch (e) { toast.error((e as Error).message); return null }
                    } : undefined} />
                  {cfg.burn_subtitles && (
                    <ToggleRow label="Phụ đề mới nằm giữa vùng che" checked={cfg.sub_in_cover} onChange={(v) => set("sub_in_cover", v)}
                      desc="Chữ tiếng Việt đè đúng chỗ phụ đề cũ — kéo vùng che tới đâu, phụ đề theo tới đó (1 hay 2 dòng đều căn giữa)." />
                  )}
                  {mode === "vietsub" && (
                    <ToggleRow label="AI tự căn vùng che khi dựng" checked={cfg.auto_sub_box} onChange={(v) => set("auto_sub_box", v)}
                      desc="Lúc dựng, AI quét cả phim tìm đúng chỗ phụ đề cũ rồi đặt lại vùng che cho trùm kín — không lòi chữ cũ trên / dưới." />
                  )}
                </>
              )}
              </Section>
            )}

            {tab === "fx" && (
              <Section title="Hiệu ứng & chuyển cảnh" icon={<Sparkles />} desc="Không làm lệch lời đọc / phụ đề — độ dài video giữ nguyên">
              <FxPicker fx={cfg} onChange={(p) => setCfg((c) => ({ ...c, ...p }))} />
              </Section>
            )}

            {tab === "post" && (
              <Section title="Hậu kỳ & thương hiệu" icon={<Wand2 />} desc="Tự hậu kỳ, kiểm tra lỗi, bài đăng AI · khung hình, logo, intro/outro">
              <ToggleRow label="Tự hậu kỳ sau khi lồng tiếng" checked={cfg.auto_post} onChange={(v) => set("auto_post", v)}
                desc="Tự căn đoạn hình khớp lời đọc + AI (ChatGPT/Gemini) sửa kịch bản, bỏ cảnh rác & tạo lại giọng câu đã sửa." />
              <ToggleRow label="Tự kiểm tra & sửa lỗi sau khi xuất" checked={cfg.auto_fix} onChange={(v) => set("auto_fix", v)}
                desc="Soi lại video vừa dựng (hình đứng, màn đen, lệch hình–lời, âm lượng, phụ đề) → AI sửa đúng cảnh lỗi rồi dựng lại." />
              <ToggleRow label="Tự viết bài đăng sau khi xuất" checked={cfg.auto_publish} onChange={(v) => set("auto_publish", v)}
                desc="AI viết tiêu đề, mô tả, hashtag cho YouTube · Shorts · TikTok · Facebook · Instagram + 3 thumbnail, lưu cạnh video." />
              <ToggleRow label="Lật ảnh xen kẽ" checked={cfg.mirror_video} onChange={(v) => set("mirror_video", v)}
                desc="Lật ngang các cảnh chẵn để giảm trùng nội dung với video gốc." />
              <Field label="Khung hình xuất">
                <Segmented value={cfg.target_resolution as "1920x1080" | "1280x720" | "1080x1920"} onChange={(v) => set("target_resolution", v)}
                  items={[{ value: "1920x1080", label: "16:9 · 1080p" }, { value: "1280x720", label: "16:9 · 720p" }, { value: "1080x1920", label: "9:16 · Shorts/TikTok" }]} />
              </Field>
              {cfg.target_resolution === "1080x1920" && (
                <ToggleRow label="Nền mờ thay viền đen" checked={cfg.frame_bg !== "black"} onChange={(v) => set("frame_bg", v ? "blur" : "black")}
                  desc="Video ngang trong khung dọc: phần trên / dưới là chính video phóng to làm mờ (kiểu CapCut, TikTok) thay vì viền đen." />
              )}
              <Field label="Logo / watermark (tuỳ chọn)" hint="Ảnh PNG nền trong suốt cho đẹp nhất.">
                <PathInput value={cfg.watermark_path} onChange={(v) => set("watermark_path", v)} pick={bridge.pickImage} placeholder="Chọn ảnh logo" />
              </Field>
              <Field label="Logo chữ (tuỳ chọn)" hint="Tên kênh hiện như logo — không cần ảnh. Có cả ảnh thì hiện cả hai.">
                <Input value={cfg.watermark_text} maxLength={60} onChange={(e) => set("watermark_text", e.target.value)} placeholder="Vd: @TenKenh" />
              </Field>
              {(cfg.watermark_path || cfg.watermark_text.trim()) && (
                <Field label="Logo chuyển động" hint="Logo đứng yên dễ bị cắt / che khi người khác reup — logo di chuyển khó xoá hơn.">
                  <Segmented size="sm" value={cfg.watermark_motion} onChange={(v) => set("watermark_motion", v)}
                    items={[{ value: "static", label: "Đứng yên" }, { value: "hop", label: "Nhảy góc" }, { value: "drift", label: "Trôi dọc mép" }, { value: "bounce", label: "Nảy khắp khung" }]} />
                </Field>
              )}
              {(cfg.watermark_path || cfg.watermark_text.trim()) && (
                <div className="grid grid-cols-[auto_1fr_1fr] items-end gap-4">
                  <Field label="Góc">
                    <Segmented value={cfg.watermark_corner as "Trên-Trái" | "Trên-Phải" | "Dưới-Trái" | "Dưới-Phải"} onChange={(v) => set("watermark_corner", v)}
                      items={[{ value: "Trên-Trái", label: "↖" }, { value: "Trên-Phải", label: "↗" }, { value: "Dưới-Trái", label: "↙" }, { value: "Dưới-Phải", label: "↘" }]} />
                  </Field>
                  <Field label={`Cỡ logo: ${cfg.watermark_size_pct}%`}>
                    <Slider value={[cfg.watermark_size_pct]} min={5} max={30} step={1} onValueChange={([v]) => set("watermark_size_pct", v)} className="mb-2" />
                  </Field>
                  <Field label={`Độ rõ: ${Math.round(cfg.watermark_opacity * 100)}%`}>
                    <Slider value={[cfg.watermark_opacity]} min={0.2} max={1} step={0.05} onValueChange={([v]) => set("watermark_opacity", +v.toFixed(2))} className="mb-2" />
                  </Field>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <Field label="Intro (tuỳ chọn)"><PathInput value={cfg.intro_path} onChange={(v) => set("intro_path", v)} pick={bridge.pickVideo} placeholder="Video mở đầu" /></Field>
                <Field label="Outro (tuỳ chọn)"><PathInput value={cfg.outro_path} onChange={(v) => set("outro_path", v)} pick={bridge.pickVideo} placeholder="Video kết thúc" /></Field>
              </div>
              </Section>
            )}

            {tab === "output" && (
              <Section title="Quy trình & xuất file" icon={<FolderOutput />} desc="Dừng ở bước nào để bạn xem lại · nơi lưu video">
              <ToggleRow label="Chạy hoàn toàn tự động" checked={!cfg.script_edit && !cfg.scene_preview}
                onChange={(v) => setCfg((c) => ({ ...c, script_edit: !v, scene_preview: !v, auto_post: v ? true : c.auto_post }))}
                desc="Không dừng chờ sửa kịch bản / nghe lại — từ video gốc ra thẳng video hoàn chỉnh." />
              <ToggleRow label="Xem & sửa kịch bản trước khi lồng tiếng" checked={cfg.script_edit} onChange={(v) => set("script_edit", v)}
                desc="Pipeline dừng lại để bạn sửa từng câu trong Studio." />
              <ToggleRow label="Nghe lại & xác nhận trước khi dựng video" checked={cfg.scene_preview} onChange={(v) => set("scene_preview", v)}
                desc="Nghe từng câu, sửa & tạo lại giọng, bỏ câu không ưng, thêm nhạc nền." />
              {mode === "vietsub" && (<>
                <Field label="Khung hình xuất" hint={cfg.frame_bg === "black" ? "9:16 dọc: video ngang nằm giữa, trên / dưới viền đen." : "9:16 dọc: video ngang nằm giữa, trên / dưới là nền mờ."}>
                  <Segmented value={cfg.target_resolution as "1920x1080" | "1280x720" | "1080x1920"} onChange={(v) => set("target_resolution", v)}
                    items={[{ value: "1920x1080", label: "16:9 · 1080p" }, { value: "1280x720", label: "16:9 · 720p" }, { value: "1080x1920", label: "9:16 · Shorts/TikTok" }]} />
                </Field>
                  {cfg.target_resolution === "1080x1920" && (
                    <ToggleRow label="Nền mờ thay viền đen" checked={cfg.frame_bg !== "black"} onChange={(v) => set("frame_bg", v ? "blur" : "black")}
                      desc="Phần trên / dưới là chính video phóng to làm mờ (kiểu CapCut, TikTok) thay vì viền đen." />
                  )}
              </>)}
              <ToggleRow label="Chuẩn âm lượng YouTube / TikTok" checked={cfg.loudness !== "off"} onChange={(v) => set("loudness", v ? "youtube" : "off")}
                desc="Đưa độ to video xuất về -14 LUFS như nền tảng khuyến nghị — không bị nhỏ / to bất thường so với video khác." />
              <Field label="Thư mục xuất">
                <PathInput value={cfg.out_dir} onChange={(v) => set("out_dir", v)} pick={bridge.pickFolder} />
              </Field>
              </Section>
            )}
          </div>
        </div>
      </div>

      {/* ---------- Summary ---------- */}
      <aside className="flex min-h-0 flex-col gap-4 overflow-y-auto pb-6">
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="mb-3 text-xs font-medium text-muted-foreground">Xem trước khung hình</p>
          <SubtitlePreview style={cfg.burn_subtitles ? style : undefined} marginPct={cfg.sub_margin_pct} centerPct={subCenter} vertical={cfg.target_resolution === "1080x1920"}
            text={cfg.burn_subtitles ? "Đây là dòng phụ đề mẫu cho video của bạn" : ""}
            poster={isLocalFile ? mediaUrl(inp) : undefined} />
          <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-xs">
            <dt className="text-muted-foreground">Chế độ</dt><dd className="text-right">{mode === "review" ? (reviewMins ? `Review ~${reviewMins} phút${cfg.minutes ? "" : " (tự động)"}` : "Review · tự động") : mode === "vietsub" ? (cfg.dub_voice ? "Dịch phụ đề · lồng tiếng" : "Dịch phụ đề · giữ tiếng gốc") : "Dịch & Reup"}</dd>
            {mode !== "vietsub" && <><dt className="text-muted-foreground">Giọng</dt><dd className="truncate text-right">{cfg.voice}</dd></>}
            <dt className="text-muted-foreground">Nhận dạng</dt><dd className="text-right">{asrLabel(cfg.whisper_model)} · {cfg.device.startsWith("GPU") ? "GPU" : "CPU"}</dd>
            <dt className="text-muted-foreground">Phụ đề</dt><dd className="truncate text-right">{cfg.burn_subtitles ? cfg.sub_style : "Không ghép"}</dd>
            <dt className="text-muted-foreground">Khung hình</dt><dd className="text-right">{cfg.target_resolution === "1080x1920" ? "9:16 dọc" : cfg.target_resolution === "1280x720" ? "720p" : "1080p"}{cfg.crop_on ? " · cắt khung" : ""}{cfg.auto_cover_text ? " · che chữ Trung" : ""}</dd>
            {mode !== "vietsub" && <><dt className="text-muted-foreground">Hiệu ứng</dt><dd className="truncate text-right">{fxSummary(cfg) || "Không"}</dd></>}
            <dt className="text-muted-foreground">Âm thanh</dt>
            <dd className="truncate text-right">{[
              mode === "vietsub" ? (cfg.dub_voice && cfg.dub_separate ? "Giữ nhạc nền" : "") : (cfg.keep_bg ?? mode === "reup") ? "Giữ nhạc nền" : "",
              mode === "review" && cfg.auto_sfx ? "Hiệu ứng âm thanh" : "",
              cfg.loudness !== "off" ? "-14 LUFS" : "",
            ].filter(Boolean).join(" · ") || "Mặc định"}</dd>
            {mode === "vietsub" && <><dt className="text-muted-foreground">Lồng tiếng</dt><dd className="truncate text-right">{cfg.dub_voice ? (cfg.dub_by_gender && cfg.voice_female ? "Nam / nữ theo nhân vật" : cfg.voice) : "Không (giữ tiếng gốc)"}</dd></>}
            {mode === "vietsub" && <><dt className="text-muted-foreground">Che phụ đề cũ</dt><dd className="text-right">{cfg.remove_old_sub ? (cfg.sub_in_cover ? "Có · phụ đề Việt nằm giữa" : "Có") : "Không"}</dd></>}
            {mode !== "vietsub" && <><dt className="text-muted-foreground">Hậu kỳ</dt><dd className="text-right">{[cfg.auto_post && "Tự hậu kỳ", cfg.auto_fix && "Tự sửa lỗi", cfg.auto_publish && "Bài đăng AI", !cfg.script_edit && !cfg.scene_preview && "Tự động hoàn toàn", (cfg.watermark_path || cfg.watermark_text.trim()) && "Logo", (cfg.intro_path || cfg.outro_path) && "Intro/Outro"].filter(Boolean).join(" · ") || "Thủ công"}</dd></>}
          </dl>
        </div>

        {issues.length > 0 && (
          <Alert className="border-warning/30 bg-warning/5">
            <AlertTriangle className="text-warning" />
            <AlertTitle>Cần kiểm tra</AlertTitle>
            <AlertDescription><ul className="list-disc pl-4">{issues.map((i) => <li key={i}>{i}</li>)}</ul></AlertDescription>
          </Alert>
        )}

        <Button size="lg" className="w-full text-sm font-semibold" disabled={starting || issues.length > 0} onClick={start}>
          {starting ? <Loader2 className="animate-spin" /> : <Rocket />}
          {mode === "review" ? "Bắt đầu tạo review" : mode === "vietsub" ? (cfg.dub_voice ? "Bắt đầu dịch & lồng tiếng" : "Bắt đầu dịch phụ đề") : "Bắt đầu dịch & reup"}
        </Button>
        <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><Settings2 className="size-3" />Mặc định có thể đổi trong Cài đặt.</p>
      </aside>
    </div>
  )
}
