import {
  AlertTriangle, Check, CheckCircle2, Circle, Clapperboard, Eye, EyeOff, Film, List as ListIcon, Loader2, Minus, Move, Music, Pause, Play, Plus,
  Redo2, RefreshCw, Scissors, Settings, Sparkles, SquareDashed, Trash2, Undo2, Wand2, X, XCircle,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { PathInput, Segmented, ToggleRow } from "@/components/common"
import { Monitor, subtitleChunk, type CoverBox } from "@/components/timeline/Monitor"
import { Timeline } from "@/components/timeline/Timeline"
import { sourceRate, useTimelinePlayer } from "@/components/timeline/useTimelinePlayer"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Slider } from "@/components/ui/slider"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { useAudio } from "@/hooks/useAudio"
import { api, bridge, mediaUrl } from "@/lib/api"
import { basename, fmtClock, fmtDuration } from "@/lib/format"
import type { AiEdit, JobDetail, Scene, TextRegion } from "@/lib/types"
import { cn } from "@/lib/utils"
import { checkScenes, fixDurations, issueLevels, type Issue } from "./checks"
import { SaveBadge } from "./SaveBadge"
import { StageHeader } from "./StageHeader"
import { draftFor, useDraftAutosave } from "@/hooks/useDraft"
import { confirmAction } from "@/components/ConfirmHost"
import { DEFAULT_FX, FxPicker, fxSummary, type Fx } from "@/components/FxPicker"
import { DEFAULT_TEXT_COVER, TextCoverOptions, type TextCover } from "@/components/TextCoverOptions"
import { subCoverCenter } from "@/components/CoverBoxEditor"
import { TextRegionsPanel, type SceneSpan } from "./TextRegionsPanel"

/** Khung & phụ đề: vùng che mờ (% khung xuất), khung cắt (% hình gốc), phụ đề mới (bật/tắt, cách đáy %). */
type Cover = {
  remove_old_sub: boolean; cover_boxes: CoverBox[]; sub_margin_pct: number
  crop_on: boolean; crop_box: CoverBox; crop_fill: boolean; burn_subtitles: boolean
  /** phụ đề mới căn giữa vùng che phụ đề cũ (vùng rộng nhất) */
  sub_in_cover?: boolean
  /** vùng che chữ đã quét + sửa ở Hậu kỳ; null = để app tự quét lúc dựng */
  text_regions?: TextRegion[] | null
} & TextCover
const FULL_CROP: CoverBox = [0, 0, 100, 100]
type Mixer = {
  original_volume: number; bgm_path: string; bgm_volume: number; audio_ducking: boolean; cover?: Cover; fx?: Fx
  /** giữ nhạc nền & tiếng động gốc (tách giọng) · mức nhạc nền % · hiệu ứng âm thanh tự động (Review) — chưa chỉnh = theo cấu hình job */
  keep_bg?: boolean; bg_volume?: number; auto_sfx?: boolean
}
/** Giá trị âm thanh nâng cao đang áp dụng: đã chỉnh ở Hậu kỳ > cấu hình lúc tạo job > mặc định (Reup giữ nhạc nền, Review thì không). */
function audioExtras(mixer: Mixer, jcfg: Record<string, unknown>, mode: "review" | "reup") {
  const keep = mixer.keep_bg ?? (jcfg.keep_bg == null ? mode === "reup" : Boolean(jcfg.keep_bg))
  const vol = mixer.bg_volume ?? (jcfg.bg_volume == null ? (mode === "reup" ? 90 : 35) : Math.round(Number(jcfg.bg_volume) * 100))
  return { keep_bg: keep, bg_volume: vol, auto_sfx: mixer.auto_sfx ?? Boolean(jcfg.auto_sfx) }
}
const DEFAULT_BOX: CoverBox = [10, 84, 80, 10]

/** Chạy fn cho từng phần tử, tối đa `limit` việc cùng lúc. Tạo giọng mỗi câu tốn ~1 phút chờ máy chủ → chạy song song thay vì lần lượt. */
async function runPool<T>(items: T[], limit: number, fn: (item: T) => Promise<void>) {
  let next = 0
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) await fn(items[next++])
  }))
}
const REGEN_PARALLEL = 8
type StepState = "pending" | "running" | "done" | "skip" | "error"
type AutoStep = { label: string; state: StepState; detail?: string }
type AutoRun = { steps: AutoStep[]; running: boolean; backup: Scene[]; summary?: string; needLogin?: boolean }

/**
 * Trình hậu kỳ ở bước "Xem trước": Monitor + bảng tab (Cảnh · Âm thanh · Kiểm tra · AI hậu kỳ) + Timeline.
 * Mọi chỉnh sửa giữ ở client; "Xuất video" gửi kịch bản + mixer về backend để dựng.
 */
export function PostEditor({ job }: { job: JobDetail }) {
  const { play, playing, stop } = useAudio()
  const draft = draftFor(job, "preview")
  const [scenes, setScenes] = useState<Scene[]>(draft?.scenes ?? job.scenes)
  const [regen, setRegen] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<"timeline" | "list">("timeline")
  const [tab, setTab] = useState("scene")
  const [subVisible, setSubVisible] = useState(true)
  const { options, go } = useStore()
  const subLayout = options?.sub_layouts[String((job.config as Record<string, unknown>).sub_layout ?? "")]
  // giống backend: mỗi đoạn phụ đề ≤ sub_max_chars_per_chunk ký tự (trước nhân thêm số dòng → đoạn dài gấp đôi video xuất)
  const subChars = subLayout ? subLayout.sub_max_chars_per_chunk : 56
  // nguồn chữ phụ đề y như lúc xuất (Cài đặt "Nguồn phụ đề"): theo lời đọc hay theo bản dịch gốc
  const subFromSubtitle = String((job.config as Record<string, unknown>).sub_source ?? "").startsWith("Theo subtitle")
  const subText = (s: Scene) => (subFromSubtitle ? s.subtitle || s.voiceover : s.voiceover || s.subtitle) || ""
  const [mixer, setMixer] = useState<Mixer>({ original_volume: 8, bgm_path: "", bgm_volume: 5, audio_ducking: true, ...(draft?.mixer as Partial<Mixer> | undefined) })
  // Che sub gốc: lấy từ cấu hình lúc tạo job, sửa ở tab "Che sub" (lưu cùng bản nháp mixer)
  const jcfg = job.config as Record<string, unknown>
  const cover: Cover = mixer.cover ?? {
    remove_old_sub: Boolean(jcfg.remove_old_sub),
    cover_boxes: Array.isArray(jcfg.cover_boxes) && jcfg.cover_boxes.length ? (jcfg.cover_boxes as CoverBox[]) : [[...DEFAULT_BOX]],
    sub_margin_pct: typeof jcfg.sub_margin_pct === "number" ? jcfg.sub_margin_pct : 6,
    crop_on: Array.isArray(jcfg.crop_box) && jcfg.crop_box.length === 4,
    crop_box: Array.isArray(jcfg.crop_box) && jcfg.crop_box.length === 4 ? (jcfg.crop_box as CoverBox) : [...FULL_CROP],
    crop_fill: jcfg.crop_fill !== false,
    burn_subtitles: jcfg.burn_subtitles !== false,
    sub_in_cover: jcfg.sub_in_cover === true,
    auto_cover_text: Boolean(jcfg.auto_cover_text),
    text_scan_interval: typeof jcfg.text_scan_interval === "number" ? jcfg.text_scan_interval : DEFAULT_TEXT_COVER.text_scan_interval,
    text_blur_strength: typeof jcfg.text_blur_strength === "number" ? jcfg.text_blur_strength : DEFAULT_TEXT_COVER.text_blur_strength,
    text_regions: Array.isArray(jcfg.text_regions_manual) ? (jcfg.text_regions_manual as TextRegion[]) : null,
  }
  const setCover = (patch: Partial<Cover>) => setMixer((m) => ({ ...m, cover: { ...cover, ...(m.cover ?? {}), ...patch } }))
  const [coverEdit, setCoverEdit] = useState(false)
  const [cropEdit, setCropEdit] = useState(false)
  const [textEdit, setTextEdit] = useState(false)
  // cover cũ trong bản nháp (trước khi có cắt khung) thiếu trường mới → bổ sung mặc định
  if (cover.crop_box === undefined) Object.assign(cover, { crop_on: false, crop_box: [...FULL_CROP], crop_fill: true, burn_subtitles: true })
  if (cover.auto_cover_text === undefined) Object.assign(cover, DEFAULT_TEXT_COVER)
  // Hiệu ứng: lấy từ cấu hình lúc tạo job, chỉnh ở tab "Hiệu ứng" (job cũ chưa có tuỳ chọn này vẫn bật được)
  const fx: Fx = mixer.fx ?? Object.fromEntries(Object.entries(DEFAULT_FX).map(([k, v]) => [k, jcfg[k] ?? v])) as Fx
  const setFx = (patch: Partial<Fx>) => setMixer((m) => ({ ...m, fx: { ...fx, ...(m.fx ?? {}), ...patch } }))
  const [rw, rh] = String(jcfg.target_resolution || "1920x1080").split("x").map(Number)
  const saveState = useDraftAutosave(job.id, scenes, mixer as unknown as Record<string, unknown>)
  useEffect(() => { if (draft) toast.info("Đã mở lại bản đang sửa dở") }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const mode = job.kind === "reup" ? "reup" : "review"
  const player = useTimelinePlayer({ scenes, bgmPath: mixer.bgm_path, bgmVolume: mixer.bgm_volume, originalVolume: mixer.original_volume, mode })
  const [selected, setSelected] = useState<number | null>(player.clips[0]?.index ?? null)
  const issues = useMemo(() => checkScenes(scenes, mode), [scenes, mode])
  const levels = useMemo(() => issueLevels(issues), [issues])
  const errors = issues.filter((i) => i.level === "error").length
  const [auto, setAuto] = useState<AutoRun | null>(null)
  const scenesRef = useRef(scenes)
  scenesRef.current = scenes

  // Đầu phát chạy qua cảnh nào thì chọn cảnh đó
  useEffect(() => { if (player.playing && player.currentClip) setSelected(player.currentClip.index) }, [player.playing, player.currentClip])

  // Phím tắt: Space phát/dừng, ← → chuyển cảnh (bỏ qua khi đang gõ chữ)
  useEffect(() => {
    if (view !== "timeline") return
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === "TEXTAREA" || tag === "INPUT") return
      if (e.code === "Space") { e.preventDefault(); stop(); player.toggle() }
      if ((e.ctrlKey || e.metaKey) && e.code === "KeyZ") { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return }
      if ((e.ctrlKey || e.metaKey) && e.code === "KeyY") { e.preventDefault(); redo(); return }
      if ((e.code === "Delete" || e.code === "Backspace") && selected !== null) { e.preventDefault(); toggleExcluded(selected); return }
      if (e.altKey && (e.code === "ArrowRight" || e.code === "ArrowLeft") && selected !== null) {
        e.preventDefault()
        const k = player.clips.findIndex((c) => c.index === selected)
        if (k < 0) return
        if (e.code === "ArrowLeft" && k > 0) reorder(selected, player.clips[k - 1].index)
        if (e.code === "ArrowRight" && k < player.clips.length - 1) reorder(selected, player.clips[k + 2]?.index ?? scenesRef.current.length)
        return
      }
      if (e.code === "ArrowRight" || e.code === "ArrowLeft") {
        e.preventDefault()
        const i = player.clips.findIndex((c) => c.index === selected)
        const c = player.clips[Math.max(0, Math.min(player.clips.length - 1, i + (e.code === "ArrowRight" ? 1 : -1)))]
        if (c) { setSelected(c.index); player.seek(c.start) }
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [view, player, selected, stop]) // eslint-disable-line react-hooks/exhaustive-deps

  const update = (i: number, patch: Partial<Scene>) => setScenes((prev) => prev.map((x, j) => (j === i ? { ...x, ...patch } : x)))

  const select = (i: number) => {
    setSelected(i)
    const c = player.clips.find((x) => x.index === i)
    if (c) player.seek(c.start)
  }

  /** Tạo lại giọng 1 cảnh từ lời hiện tại (backend lưu vào job). */
  const regenerate = async (i: number, text = scenesRef.current[i].voiceover, preview = true): Promise<Scene | null> => {
    player.pause()
    setRegen(i)
    // mã cố định của cảnh: trong lúc chờ giọng, người dùng vẫn kéo đổi thứ tự / hoàn tác / tự hậu kỳ chạy song song —
    // ghép kết quả theo VỊ TRÍ thì giọng mới gắn nhầm cảnh khác. Ghép theo mã; cảnh không còn thì bỏ kết quả.
    const uid = `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
    scenesRef.current = scenesRef.current.map((x, j) => (j === i ? { ...x, _regen_uid: uid } : x))
    setScenes((prev) => prev.map((x, j) => (j === i ? { ...x, _regen_uid: uid } : x)))
    try {
      const updated = await api.regenScene(job.id, i, text, scenesRef.current[i])
      const merged = (x: Scene) => ({ ...x, ...updated, voiceover: text, excluded: x.excluded, clip_start: x.clip_start, clip_end: x.clip_end, _regen_uid: undefined })
      const at = scenesRef.current.findIndex((x) => x._regen_uid === uid)
      if (at < 0) { toast.info(`Cảnh #${i + 1} đã bị xoá / hoàn tác trong lúc tạo giọng — bỏ giọng vừa tạo`); return null }
      scenesRef.current = scenesRef.current.map((x) => (x._regen_uid === uid ? merged(x) : x))
      setScenes((prev) => prev.map((x) => (x._regen_uid === uid ? merged(x) : x)))
      if (preview) play(mediaUrl(updated.tts_path!))
      return scenesRef.current[at]
    } catch (e) {
      toast.error(`Cảnh #${i + 1}: ${(e as Error).message}`)
      return null
    } finally { setRegen(null) }
  }

  /** Đặt kịch bản mới ngay (state + ref) — để các bước sau của chuỗi tự hậu kỳ đọc được. */
  const commit = (next: Scene[]) => { scenesRef.current = next; setScenes(next) }

  // ── Hoàn tác / làm lại cho chỉnh sửa trên timeline (cắt mép, đổi thứ tự, bỏ cảnh) ──
  const past = useRef<Scene[][]>([])
  const future = useRef<Scene[][]>([])
  const [, setHistoryTick] = useState(0)
  const snapshot = () => {
    past.current = [...past.current.slice(-49), scenesRef.current]
    future.current = []
    setHistoryTick((n) => n + 1)
  }
  const undo = () => {
    const prev = past.current.pop()
    if (!prev) return
    future.current.push(scenesRef.current)
    commit(prev)
    setHistoryTick((n) => n + 1)
  }
  const redo = () => {
    const next = future.current.pop()
    if (!next) return
    past.current.push(scenesRef.current)
    commit(next)
    setHistoryTick((n) => n + 1)
  }

  /** Đưa cảnh `from` tới trước cảnh `to` (to = số cảnh → cuối). Lời, giọng, phụ đề, đoạn hình đi cùng nhau. */
  const reorder = (from: number, to: number) => {
    snapshot()
    const next = [...scenesRef.current]
    const [moved] = next.splice(from, 1)
    const at = to > from ? to - 1 : to
    next.splice(at, 0, moved)
    commit(next)
    setSelected(at)
  }

  // Sửa từ các tab: lưu bản Hoàn tác trước mỗi thay đổi; gõ chữ liên tục trong 1 cảnh gộp thành 1 bước (nghỉ > 1.5s = bước mới)
  const lastText = useRef<{ i: number; t: number }>({ i: -1, t: 0 })
  const edit = (i: number, patch: Partial<Scene>) => {
    const typing = "voiceover" in patch || "subtitle" in patch
    const now = Date.now()
    if (!typing || lastText.current.i !== i || now - lastText.current.t > 1500) snapshot()
    lastText.current = typing ? { i, t: now } : { i: -1, t: 0 }
    update(i, patch)
  }

  const toggleExcluded = (i: number) => {
    snapshot()
    update(i, { excluded: !scenesRef.current[i].excluded })
  }

  /**
   * Tự hậu kỳ một chạm:
   *   1. căn đoạn hình theo lời đọc  2. AI (ChatGPT/Gemini) rà & sửa kịch bản  3. tạo lại giọng câu đã sửa
   *   4. căn lại theo giọng mới. Có "Hoàn tác" về bản trước khi chạy.
   */
  const autoPost = async () => {
    player.pause(); stop()
    const steps: AutoStep[] = [
      { label: "Căn đoạn hình khớp lời đọc", state: "pending" },
      { label: "AI rà & sửa kịch bản", state: "pending" },
      { label: "Tạo lại giọng các câu đã sửa", state: "pending" },
      { label: "Căn lại theo giọng mới", state: "pending" },
    ]
    const run: AutoRun = { steps, running: true, backup: scenesRef.current }
    const set = (i: number, patch: Partial<AutoStep>) => { steps[i] = { ...steps[i], ...patch }; setAuto({ ...run, steps: [...steps] }) }
    setAuto({ ...run })

    set(0, { state: "running" })
    const f1 = fixDurations(scenesRef.current, player.videoDuration, mode)
    commit(f1.scenes)
    set(0, { state: "done", detail: f1.changed.length ? `Đã chỉnh ${f1.changed.length} cảnh` : "Không cần chỉnh" })

    let voiceChanged: { i: number; text: string }[] = []
    let aiCount = 0
    set(1, { state: "running" })
    const sys = await api.system().catch(() => null)
    const connected = Boolean(sys?.web_ai?.chatgpt || sys?.web_ai?.gemini)
    if (!connected) {
      set(1, { state: "skip", detail: "Chưa kết nối ChatGPT / Gemini" })
      run.needLogin = true
    } else {
      try {
        const { edits } = await api.aiPolish(job.id, scenesRef.current)
        aiCount = edits.length
        const next = scenesRef.current.map((x) => ({ ...x }))
        for (const e of edits) {
          const sc = next[e.id]
          if (!sc) continue
          if (e.exclude) { sc.excluded = true; continue }
          if (e.subtitle) sc.subtitle = e.subtitle
          if (e.voiceover) {
            sc.voiceover = e.voiceover
            if (job.kind === "review") sc.subtitle = e.voiceover
            voiceChanged.push({ i: e.id, text: e.voiceover })
          }
        }
        commit(next)
        set(1, { state: "done", detail: edits.length ? `${edits.length} chỉnh sửa (${edits.filter((e) => e.exclude).length} cảnh bỏ)` : "Kịch bản đã ổn" })
      } catch (err) {
        set(1, { state: "error", detail: (err as Error).message })
        voiceChanged = []
      }
    }

    set(2, { state: voiceChanged.length ? "running" : "skip", detail: voiceChanged.length ? `0/${voiceChanged.length}` : "Không có câu cần tạo lại" })
    let ok = 0, n = 0
    await runPool(voiceChanged, REGEN_PARALLEL, async (v) => {
      if (await regenerate(v.i, v.text, false)) ok++
      set(2, { detail: `${++n}/${voiceChanged.length}` })
    })
    if (voiceChanged.length) set(2, { state: ok === voiceChanged.length ? "done" : "error", detail: `${ok}/${voiceChanged.length} câu` })

    set(3, { state: "running" })
    const f2 = fixDurations(scenesRef.current, player.videoDuration, mode)
    commit(f2.scenes)
    set(3, { state: "done", detail: f2.changed.length ? `Đã chỉnh ${f2.changed.length} cảnh` : "Đã khớp" })

    const left = checkScenes(scenesRef.current).length
    run.running = false
    run.summary = `Đã căn ${new Set([...f1.changed, ...f2.changed]).size} đoạn hình, AI sửa ${aiCount} mục, tạo lại ${ok} giọng. ${left ? `Còn ${left} vấn đề — xem tab Kiểm tra.` : "Không còn vấn đề."}`
    setAuto({ ...run, steps: [...steps] })
  }

  const submit = async (confirmed: boolean) => {
    stop(); player.pause(); setBusy(true)
    try {
      await api.confirm(job.id, confirmed ? {
        confirmed, scenes, mixer: { original_volume: mixer.original_volume / 100, bgm_path: mixer.bgm_path, bgm_volume: mixer.bgm_volume / 100, audio_ducking: mixer.audio_ducking,
          ...(({ keep_bg, bg_volume, auto_sfx }) => ({ keep_bg, bg_volume: bg_volume / 100, auto_sfx }))(audioExtras(mixer, job.config as Record<string, unknown>, mode)),
          cover: mixer.cover ? {
            remove_old_sub: cover.remove_old_sub, cover_boxes: cover.remove_old_sub ? cover.cover_boxes : [], sub_margin_pct: cover.sub_margin_pct,
            crop_box: cover.crop_on ? cover.crop_box : [], crop_fill: cover.crop_fill, burn_subtitles: cover.burn_subtitles, sub_in_cover: !!cover.sub_in_cover,
            auto_cover_text: cover.auto_cover_text, text_scan_interval: cover.text_scan_interval, text_blur_strength: cover.text_blur_strength,
            // tắt che chữ → danh sách rỗng (không che); bật mà chưa quét → null (app tự quét lúc dựng)
            text_regions: !cover.auto_cover_text ? [] : cover.text_regions ? cover.text_regions.filter((r) => !r.off) : null,
          } : undefined, fx: mixer.fx },
      } : { confirmed })
      toast.success(confirmed ? "Đang dựng video…" : "Đã huỷ job")
    } catch (e) { toast.error((e as Error).message); setBusy(false) }   // thành công: giữ khoá nút tới khi chuyển bước
  }

  const current = player.currentClip
  const currentScene = current ? scenes[current.index] : null
  // đoạn hình gốc của từng cảnh (Reup kéo giãn theo lời) — để vùng chữ hiện đúng lúc & nhảy tới đúng chỗ
  const spans: SceneSpan[] = useMemo(() => player.clips.map((c, k) => ({
    n: k + 1, srcStart: c.scene.clip_start, srcEnd: c.scene.clip_start + c.dur * sourceRate(c, mode),
  })), [player.clips, mode])
  const srcTime = current ? current.scene.clip_start + (player.time - current.start) * sourceRate(current, mode) : 0
  const currentSpan = current ? spans[player.clips.indexOf(current)] ?? null : null
  const jumpToSource = (t: number) => {
    const k = spans.findIndex((sp) => t >= sp.srcStart && t < sp.srcEnd)
    if (k < 0) return
    const c = player.clips[k]
    stop(); player.pause()
    player.seek(c.start + (t - spans[k].srcStart) / sourceRate(c, mode))
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card">
      <StageHeader title="Hậu kỳ & xác nhận" dot="bg-warning animate-pulse"
        meta={<span className="flex items-center gap-2">
          <span>{player.clips.length}/{scenes.length} cảnh · {fmtDuration(player.total)}</span>
          <SaveBadge state={saveState} />
          {issues.length > 0 ? (
            <button className={cn("flex items-center gap-1 font-medium", errors ? "text-destructive" : "text-warning")} onClick={() => setTab("checks")}>
              <AlertTriangle className="size-3" /> {issues.length} vấn đề
            </button>
          ) : <span className="flex items-center gap-1 text-success"><CheckCircle2 className="size-3" /> Không có lỗi</span>}
        </span>}
        actions={<>
          <div className="flex items-center">
            <Button variant="ghost" size="icon-sm" title="Hoàn tác (Ctrl+Z)" disabled={!past.current.length} onClick={undo}><Undo2 /></Button>
            <Button variant="ghost" size="icon-sm" title="Làm lại (Ctrl+Y)" disabled={!future.current.length} onClick={redo}><Redo2 /></Button>
          </div>
          <Segmented size="sm" value={view} onChange={setView} items={[{ value: "timeline", label: "Timeline", icon: <Clapperboard /> }, { value: "list", label: "Danh sách", icon: <ListIcon /> }]} />
          <Button variant="outline" size="sm" onClick={autoPost} disabled={busy || regen !== null || auto?.running}
            title="Căn hình theo lời + AI (ChatGPT/Gemini) sửa kịch bản + tạo lại giọng — tự động">
            {auto?.running ? <Loader2 className="animate-spin" /> : <Wand2 />} Tự hậu kỳ
          </Button>
          <Button variant="ghost" size="sm" disabled={busy} onClick={async () => {
            if (await confirmAction({ title: "Huỷ job?", danger: true, action: "Huỷ job", cancel: "Tiếp tục sửa",
              desc: "Job sẽ dừng và không xuất video. Các chỉnh sửa ở bước này sẽ không được dùng." })) submit(false)
          }}>Huỷ job</Button>
          <Button size="sm" onClick={() => submit(true)} disabled={busy || regen !== null || player.clips.length === 0}
            title={errors ? "Còn lỗi — vẫn có thể xuất, nhưng nên sửa trước" : undefined}>
            {busy ? <Loader2 className="animate-spin" /> : <Film />} Xuất video
          </Button>
        </>} />

      <AutoDialog auto={auto} onClose={() => setAuto(null)} onUndo={() => { if (auto) commit(auto.backup); setAuto(null); toast("Đã hoàn tác về bản trước khi tự hậu kỳ") }}
        onLogin={() => { setAuto(null); go("settings") }} />

      {view === "timeline" ? (
        <>
          <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(360px,430px)]">
            <Monitor videoPath={job.result.video_path} attachVideo={player.attachVideo} time={player.time} total={player.total}
              subtitle={subVisible && cover.burn_subtitles && currentScene && current
                ? subtitleChunk(subText(currentScene), player.time - current.start,
                    mode === "reup" ? Math.min(current.dur, (currentScene.tts_duration || current.dur) / (current.voiceRate ?? 1)) : current.dur, subChars)
                : ""}
              label={current ? `Cảnh ${player.clips.indexOf(current) + 1}/${player.clips.length}` : ""}
              aspect={rw && rh ? rw / rh : 16 / 9} subMarginPct={cover.sub_margin_pct}
              subCenterPct={cover.remove_old_sub && cover.sub_in_cover ? subCoverCenter(cover.cover_boxes) : null}
              cover={cover.remove_old_sub || coverEdit ? cover.cover_boxes : undefined} coverEdit={coverEdit && tab === "cover"}
              onCoverChange={(b) => setCover({ cover_boxes: b, remove_old_sub: true })}
              crop={cover.crop_on || cropEdit ? cover.crop_box : null} cropFill={cover.crop_fill} cropEdit={cropEdit && tab === "cover"}
              onCropChange={(b) => setCover({ crop_box: b, crop_on: true })}
              textRegions={cover.auto_cover_text && cover.text_regions ? cover.text_regions : undefined} srcTime={srcTime}
              textEdit={textEdit && tab === "cover"} textBlurPx={Math.round(cover.text_blur_strength * 0.55)}
              onTextRegionChange={(i, r) => setCover({ text_regions: (cover.text_regions ?? []).map((x, j) => (j === i ? r : x)) })} />

            <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-col gap-0 border-l border-border">
              <TabsList className="m-2 grid w-auto grid-cols-6 [&>button]:gap-1 [&>button]:px-0.5 [&>button]:text-[12px] [&>button>svg]:hidden">
                <TabsTrigger value="scene"><Scissors /> Cảnh</TabsTrigger>
                <TabsTrigger value="cover"><SquareDashed /> Khung &amp; sub</TabsTrigger>
                <TabsTrigger value="fx" className="gap-1"><Sparkles /> Hiệu ứng{fxSummary(fx) && <span className="size-1.5 rounded-full bg-primary" />}</TabsTrigger>
                <TabsTrigger value="audio"><Music /> Âm thanh</TabsTrigger>
                <TabsTrigger value="checks" className="gap-1">
                  <AlertTriangle /> Kiểm tra
                  {issues.length > 0 && <span className={cn("rounded-full px-1 text-[9px] text-white", errors ? "bg-destructive" : "bg-warning")}>{issues.length}</span>}
                </TabsTrigger>
                <TabsTrigger value="ai"><Sparkles /> AI</TabsTrigger>
              </TabsList>
              <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
                <TabsContent value="scene">
                  <SceneTab job={job} scenes={scenes} selected={selected} issues={issues} regen={regen}
                    update={edit} regenerate={regenerate} onPlay={(i) => { const c = player.clips.find((x) => x.index === i); stop(); if (c) player.play(c.start) }} />
                </TabsContent>
                <TabsContent value="cover">
                  <CoverTab cover={cover} setCover={setCover} editing={coverEdit} cropEditing={cropEdit} reup={mode === "reup"}
                    textPanel={<TextRegionsPanel jobId={job.id} scenes={scenes} spans={spans} regions={cover.text_regions}
                      interval={cover.text_scan_interval} onInterval={(v) => setCover({ text_scan_interval: v })}
                      onRegions={(r) => setCover({ text_regions: r })} currentSpan={currentSpan} onJump={jumpToSource}
                      editing={textEdit} setEditing={(v) => { setTextEdit(v); if (v) { setCoverEdit(false); setCropEdit(false); player.pause() } }} />}
                    scanMinutes={mode === "reup" ? undefined : scenes.reduce((a, s) => a + Math.max(0, s.clip_end - s.clip_start), 0) / 60}
                    setEditing={(v) => { setCoverEdit(v); if (v) { setCropEdit(false); player.pause() } }}
                    setCropEditing={(v) => { setCropEdit(v); if (v) { setCoverEdit(false); player.pause() } }} />
                </TabsContent>
                <TabsContent value="fx">
                  <div className="flex flex-col gap-4 pt-1">
                    <p className="text-[11px] text-muted-foreground">Áp dụng khi bấm <b>Xuất video</b>. Độ dài video giữ nguyên — lời đọc và phụ đề không bị lệch.</p>
                    <FxPicker fx={fx} onChange={setFx} compact />
                  </div>
                </TabsContent>
                <TabsContent value="audio"><AudioTab mixer={mixer} setMixer={setMixer} mode={mode} jcfg={job.config as Record<string, unknown>} /></TabsContent>
                <TabsContent value="checks"><ChecksTab issues={issues} onPick={(i) => { select(i); setTab("scene") }} /></TabsContent>
                <TabsContent value="ai">
                  <AiTab job={job} scenes={scenes} regen={regen} update={edit} regenerate={regenerate} onPick={select} />
                </TabsContent>
              </div>
            </Tabs>
          </div>
          <Timeline scenes={scenes} clips={player.clips} total={player.total} time={player.time} playing={player.playing}
            selected={selected} muted={player.muted} bgmName={mixer.bgm_path ? basename(mixer.bgm_path) : ""} issues={levels}
            mode={mode} videoDuration={Number.isFinite(player.videoDuration) ? player.videoDuration : undefined}
            onTrim={(i, patch) => update(i, patch)} onEditStart={snapshot} onPeek={player.peek} onReorder={reorder}
            subtitleVisible={subVisible} onToggleSubtitle={() => setSubVisible((v) => !v)}
            onUndo={undo} onRedo={redo} canUndo={past.current.length > 0} canRedo={future.current.length > 0} onToggleExcluded={toggleExcluded}
            onSeek={player.seek} onSelect={setSelected} onToggle={() => { stop(); player.toggle() }} onToggleMute={player.toggleMute} />
        </>
      ) : (
        <SceneList scenes={scenes} regen={regen} levels={levels} playing={playing}
          onPlay={(url) => { player.pause(); play(url) }} update={edit} regenerate={(i) => regenerate(i)} />
      )}
    </div>
  )
}

/* ─────────────────────────────── Hộp thoại tự hậu kỳ ─────────────────────────────── */
function AutoDialog({ auto, onClose, onUndo, onLogin }: { auto: AutoRun | null; onClose: () => void; onUndo: () => void; onLogin: () => void }) {
  const icon = (st: StepState) => st === "running" ? <Loader2 className="size-4 animate-spin text-primary" />
    : st === "done" ? <CheckCircle2 className="size-4 text-success" />
    : st === "error" ? <XCircle className="size-4 text-destructive" />
    : st === "skip" ? <Circle className="size-4 text-muted-foreground/50" />
    : <Circle className="size-4 text-muted-foreground" />
  return (
    <Dialog open={!!auto} onOpenChange={(o) => { if (!o && !auto?.running) onClose() }}>
      <DialogContent className="max-w-md" showCloseButton={!auto?.running}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Wand2 className="size-4 text-primary" /> Tự hậu kỳ</DialogTitle>
          <DialogDescription>{auto?.running ? "Đang xử lý — đừng đóng cửa sổ." : auto?.summary}</DialogDescription>
        </DialogHeader>
        <ol className="flex flex-col gap-3">
          {auto?.steps.map((st, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="mt-0.5">{icon(st.state)}</span>
              <div className="min-w-0">
                <p className={cn("text-[13px]", st.state === "pending" && "text-muted-foreground")}>{st.label}</p>
                {st.detail && <p className={cn("text-[11px]", st.state === "error" ? "text-destructive" : "text-muted-foreground")}>{st.detail}</p>}
              </div>
            </li>
          ))}
        </ol>
        {!auto?.running && (
          <DialogFooter className="gap-2 sm:justify-between">
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={onUndo}><Undo2 /> Hoàn tác</Button>
              {auto?.needLogin && <Button variant="outline" size="sm" onClick={onLogin}><Settings /> Kết nối ChatGPT / Gemini</Button>}
            </div>
            <Button size="sm" onClick={onClose}>Xong</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

/* ─────────────────────────────── Tab: Cảnh ─────────────────────────────── */
function SceneTab({ job, scenes, selected, issues, regen, update, regenerate, onPlay }: {
  job: JobDetail; scenes: Scene[]; selected: number | null; issues: Issue[]; regen: number | null
  update: (i: number, p: Partial<Scene>) => void; regenerate: (i: number) => Promise<Scene | null>; onPlay: (i: number) => void
}) {
  if (selected === null || !scenes[selected]) return <p className="py-10 text-center text-xs text-muted-foreground">Chọn một cảnh trên timeline</p>
  const s = scenes[selected]
  const mine = issues.filter((x) => x.index === selected)
  const src = Math.max(0, s.clip_end - s.clip_start)
  const showSub = job.kind === "reup" || (s.subtitle !== undefined && s.subtitle !== s.voiceover)
  const nudge = (field: "clip_start" | "clip_end", d: number) => {
    const v = Math.max(0, +(s[field] + d).toFixed(2))
    if (field === "clip_start" && v >= s.clip_end - 0.2) return
    if (field === "clip_end" && v <= s.clip_start + 0.2) return
    update(selected, { [field]: v })
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">Cảnh #{selected + 1}</span>
        {s._tts_engine_used && <span className="rounded bg-muted px-1.5 text-[10px] uppercase">{s._tts_engine_used}</span>}
        {s.excluded && <span className="rounded bg-destructive/10 px-1.5 text-[10px] text-destructive">đã bỏ</span>}
        <div className="ml-auto flex gap-1">
          <Button size="icon-sm" variant="outline" disabled={s.excluded} title="Nghe cảnh" onClick={() => onPlay(selected)}><Play /></Button>
          <Button size="icon-sm" variant="ghost" title={s.excluded ? "Dùng lại cảnh" : "Bỏ cảnh"} onClick={() => update(selected, { excluded: !s.excluded })}>
            {s.excluded ? <Eye /> : <EyeOff />}
          </Button>
        </div>
      </div>

      {mine.length > 0 && (
        <div className="flex flex-col gap-1 rounded-md border border-warning/30 bg-warning/5 p-2">
          {mine.map((m) => (
            <p key={m.code} className={cn("flex gap-1.5 text-[11px]", m.level === "error" ? "text-destructive" : "text-warning")}>
              <AlertTriangle className="mt-0.5 size-3 shrink-0" /> {m.message}
            </p>
          ))}
        </div>
      )}

      <Group label="Đoạn hình gốc" hint={`${src.toFixed(1)}s hình · ${(s.tts_duration ?? 0).toFixed(1)}s lời`}>
        <div className="grid grid-cols-2 gap-2">
          <TimeField label="Bắt đầu" value={s.clip_start} onNudge={(d) => nudge("clip_start", d)} onSet={(v) => v < s.clip_end - 0.2 && update(selected, { clip_start: v })} />
          <TimeField label="Kết thúc" value={s.clip_end} onNudge={(d) => nudge("clip_end", d)} onSet={(v) => v > s.clip_start + 0.2 && update(selected, { clip_end: v })} />
        </div>
      </Group>

      <Group label="Lời đọc" hint={`${(s.voiceover || "").trim().split(/\s+/).filter(Boolean).length} từ`}>
        <Textarea value={s.voiceover} rows={5} className="resize-y text-[13px]" onChange={(e) => update(selected, { voiceover: e.target.value })} />
        <Button size="sm" variant="outline" className="self-start" disabled={regen !== null} onClick={() => regenerate(selected)}>
          {regen === selected ? <Loader2 className="animate-spin" /> : <RefreshCw />} Tạo lại giọng
        </Button>
      </Group>

      {showSub && (
        <Group label="Phụ đề" hint="hiện trên video">
          <Textarea value={s.subtitle ?? ""} rows={3} className="resize-y text-[13px]" onChange={(e) => update(selected, { subtitle: e.target.value })} />
        </Group>
      )}
    </div>
  )
}

function Group({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium">{label}</span>
        {hint && <span className="tabular text-[10.5px] text-muted-foreground">{hint}</span>}
      </div>
      {children}
    </div>
  )
}

function TimeField({ label, value, onNudge, onSet }: { label: string; value: number; onNudge: (d: number) => void; onSet: (v: number) => void }) {
  const [text, setText] = useState(value.toFixed(1))
  useEffect(() => setText(value.toFixed(1)), [value])
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10.5px] text-muted-foreground">{label} · {fmtClock(value)}</span>
      <div className="flex items-center gap-1">
        <Button size="icon-xs" variant="outline" onClick={() => onNudge(-0.5)} title="-0.5s"><Minus /></Button>
        <Input value={text} onChange={(e) => setText(e.target.value)} className="tabular h-7 px-1.5 text-center font-mono text-xs"
          onBlur={() => { const v = parseFloat(text); if (Number.isFinite(v) && v >= 0) onSet(+v.toFixed(2)); else setText(value.toFixed(1)) }}
          onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur() }} />
        <Button size="icon-xs" variant="outline" onClick={() => onNudge(0.5)} title="+0.5s"><Plus /></Button>
      </div>
    </div>
  )
}

/* ─────────────────────────────── Tab: Âm thanh ─────────────────────────────── */
/* ─────────── Tab Khung & sub: phụ đề mới, cắt khung hình gốc, che mờ chữ cứng ─────────── */
function CoverTab({ cover, setCover, editing, setEditing, cropEditing, setCropEditing, reup, scanMinutes, textPanel }: {
  cover: Cover; setCover: (p: Partial<Cover>) => void; editing: boolean; setEditing: (v: boolean) => void
  cropEditing: boolean; setCropEditing: (v: boolean) => void; reup: boolean; scanMinutes?: number; textPanel?: React.ReactNode
}) {
  const boxes = cover.cover_boxes
  const setBox = (i: number, k: number, v: number) => setCover({ cover_boxes: boxes.map((b, j) => (j === i ? b.map((x, n) => (n === k ? v : x)) : b)) })
  useEffect(() => () => { setEditing(false); setCropEditing(false) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const [cx, cy, cw, ch] = cover.crop_box
  return (
    <div className="flex flex-col gap-5 pt-1">
      {/* Phụ đề mới */}
      <section className="flex flex-col gap-3">
        <h4 className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Phụ đề mới</h4>
        <ToggleRow label="Hiện phụ đề tiếng Việt trên video" checked={cover.burn_subtitles} onChange={(v) => setCover({ burn_subtitles: v })}
          desc="Tắt nếu chỉ cần lời đọc (vẫn xuất file .srt riêng để đăng kèm)." />
        {cover.burn_subtitles && cover.remove_old_sub && (
          <ToggleRow label="Nằm giữa vùng che phụ đề" checked={!!cover.sub_in_cover} onChange={(v) => setCover({ sub_in_cover: v })}
            desc="Chữ mới đè đúng chỗ phụ đề cũ — kéo vùng che tới đâu, phụ đề theo tới đó." />
        )}
        {cover.burn_subtitles && !(cover.remove_old_sub && cover.sub_in_cover) && (
          <Group label="Cách đáy" hint={`${cover.sub_margin_pct}%`}>
            <Slider value={[cover.sub_margin_pct]} min={1} max={60} step={0.5} onValueChange={([v]) => setCover({ sub_margin_pct: v })} />
          </Group>
        )}
      </section>

      {/* Cắt khung */}
      <section className="flex flex-col gap-3 border-t border-border pt-4">
        <h4 className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Cắt khung hình</h4>
        <ToggleRow label="Cắt bỏ phần mép video gốc" checked={cover.crop_on} onChange={(v) => { setCover({ crop_on: v }); if (!v) setCropEditing(false) }}
          desc="Cắt bỏ hẳn dải phụ đề cứng / logo / viền đen ở mép rồi phóng phần còn lại cho đầy khung — sạch hơn làm mờ." />
        <div className="grid grid-cols-2 gap-2">
          <Button variant={cropEditing ? "default" : "outline"} size="sm" onClick={() => { setCover({ crop_on: true }); setCropEditing(!cropEditing) }}>
            <Scissors /> {cropEditing ? "Xong" : "Chỉnh trên màn hình"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setCover({ crop_on: true, crop_box: [0, 0, 100, 84] })} title="Cắt bỏ 16% phía dưới — chỗ phụ đề cứng hay nằm">
            Bỏ dải phụ đề dưới
          </Button>
        </div>
        {cropEditing && <p className="-mt-1 text-[11px] text-muted-foreground">Kéo 4 góc / 4 cạnh để đổi khung, kéo giữa để dời. Phần tối bên ngoài sẽ bị cắt bỏ.</p>}
        {cover.crop_on && <>
          <Segmented size="sm" value={cover.crop_fill ? "fill" : "fit"} onChange={(v) => setCover({ crop_fill: v === "fill" })}
            items={[{ value: "fill", label: "Phủ kín khung" }, { value: "fit", label: "Giữ trọn (viền đen)" }]} />
          <p className="text-[11px] text-muted-foreground">
            Giữ lại {Math.round(cw)}% × {Math.round(ch)}% hình gốc (từ {Math.round(cx)}%, {Math.round(cy)}%).
            {cover.crop_fill ? " Phủ kín: phóng to cho đầy khung, có thể cắt thêm chút mép nếu khác tỉ lệ." : " Giữ trọn: thấy hết phần đã chọn, thêm viền đen."}
            {" "}<button className="text-primary hover:underline" onClick={() => setCover({ crop_box: [...FULL_CROP] })}>Đặt lại</button>
          </p>
        </>}
      </section>

      {/* Che mờ */}
      <section className="flex flex-col gap-3 border-t border-border pt-4">
        <h4 className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Che mờ chữ cứng / logo</h4>
        <TextCoverOptions value={cover} onChange={(p) => setCover(p)} reup={reup} minutes={scanMinutes} />
        {cover.auto_cover_text && textPanel}
        <ToggleRow label="Làm mờ vùng có chữ gốc" checked={cover.remove_old_sub} onChange={(v) => setCover({ remove_old_sub: v })}
          desc="Dùng khi không muốn cắt hình: làm mờ đúng vùng chữ cứng. Màn xem trước hiện mờ y như lúc xuất." />
        <Button variant={editing ? "default" : "outline"} size="sm" onClick={() => setEditing(!editing)}>
          <Move /> {editing ? "Xong — thoát sửa vùng che" : "Sửa vùng che trên màn hình"}
        </Button>
        {boxes.map((b, i) => (
          <div key={i} className={cn("flex flex-col gap-2 rounded-lg border border-border p-3", !cover.remove_old_sub && "opacity-50")}>
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium">Vùng {i + 1}</span>
              <div className="flex gap-1">
                {boxes.length > 1 && <Button size="icon-xs" variant="ghost" title="Xoá vùng" onClick={() => setCover({ cover_boxes: boxes.filter((_, j) => j !== i) })}><Trash2 /></Button>}
              </div>
            </div>
            {(["Ngang", "Dọc", "Rộng", "Cao"] as const).map((name, k) => (
              <div key={name} className="grid grid-cols-[44px_1fr_44px] items-center gap-2 text-[11px] text-muted-foreground">
                {name}
                <Slider value={[b[k]]} min={k >= 2 ? 2 : 0} max={100 - (k >= 2 ? b[k - 2] : b[k + 2])} step={0.5} onValueChange={([v]) => setBox(i, k, v)} />
                <span className="tabular text-right">{b[k].toFixed(1)}%</span>
              </div>
            ))}
          </div>
        ))}
        <Button variant="ghost" size="sm" className="self-start" onClick={() => setCover({ cover_boxes: [...boxes, [70, 4, 26, 10]], remove_old_sub: true })}>
          <Plus /> Thêm vùng (logo, chữ góc…)
        </Button>
      </section>
    </div>
  )
}

function AudioTab({ mixer, setMixer, mode, jcfg }: { mixer: Mixer; setMixer: (m: Mixer) => void; mode: "review" | "reup"; jcfg: Record<string, unknown> }) {
  const x = audioExtras(mixer, jcfg, mode)
  return (
    <div className="flex flex-col gap-5">
      <ToggleRow label="Giữ nhạc nền & tiếng động gốc" checked={x.keep_bg} onChange={(v) => setMixer({ ...mixer, keep_bg: v })}
        desc="Tách bỏ giọng gốc, giữ lại nhạc + tiếng động — nghe như phim lồng tiếng thật. Lần đầu mất thêm thời gian tách (có GPU nhanh hơn nhiều)." />
      {x.keep_bg && (
        <Group label="Âm lượng nhạc nền gốc" hint={`${x.bg_volume}%`}>
          <Slider value={[x.bg_volume]} max={150} step={5} onValueChange={([v]) => setMixer({ ...mixer, bg_volume: v })} />
        </Group>
      )}
      <Group label={x.keep_bg ? "Tiếng gốc (khi không tách được)" : "Tiếng gốc của phim"} hint={`${mixer.original_volume}%`}>
        <Slider value={[mixer.original_volume]} max={100} onValueChange={([v]) => setMixer({ ...mixer, original_volume: v })} />
      </Group>
      {mode === "review" && (
        <ToggleRow label="Hiệu ứng âm thanh tự động" checked={x.auto_sfx} onChange={(v) => setMixer({ ...mixer, auto_sfx: v })}
          desc={'Tiếng "vút" khi chuyển cảnh nhảy đoạn, "bùm" ở đoạn cao trào — video review có nhịp hơn.'} />
      )}
      <Group label="Nhạc nền">
        <PathInput value={mixer.bgm_path} onChange={(v) => setMixer({ ...mixer, bgm_path: v })} pick={bridge.pickAudio} placeholder="Chọn file nhạc (tuỳ chọn)" />
      </Group>
      <Group label="Âm lượng nhạc nền" hint={`${mixer.bgm_volume}%`}>
        <Slider value={[mixer.bgm_volume]} max={50} disabled={!mixer.bgm_path} onValueChange={([v]) => setMixer({ ...mixer, bgm_volume: v })} />
      </Group>
      <ToggleRow label="Tự nén nhạc khi có lời" desc="Nhạc nhỏ lại lúc đang đọc, to lên ở khoảng lặng." checked={mixer.audio_ducking}
        onChange={(v) => setMixer({ ...mixer, audio_ducking: v })} disabled={!mixer.bgm_path} />
      <p className="text-[11px] text-muted-foreground">Nút <b>M</b> trên timeline chỉ tắt tiếng khi nghe thử, không ảnh hưởng video xuất ra.</p>
    </div>
  )
}

/* ─────────────────────────────── Tab: Kiểm tra ─────────────────────────────── */
function ChecksTab({ issues, onPick }: { issues: Issue[]; onPick: (i: number) => void }) {
  if (!issues.length) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center">
        <CheckCircle2 className="size-7 text-success" />
        <p className="text-sm font-medium">Không phát hiện vấn đề</p>
        <p className="text-xs text-muted-foreground">Lời đọc, giọng và độ dài hình đều ổn.</p>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1.5">
      <p className="mb-1 text-[11px] text-muted-foreground">Bấm vào một mục để mở cảnh đó.</p>
      {issues.map((it, k) => (
        <button key={k} onClick={() => onPick(it.index)}
          className="flex items-start gap-2 rounded-md border border-border px-2.5 py-2 text-left hover:border-primary/40 hover:bg-muted/40">
          <span className={cn("tabular mt-0.5 shrink-0 rounded px-1 text-[10px] font-semibold text-white", it.level === "error" ? "bg-destructive" : "bg-warning")}>#{it.index + 1}</span>
          <span className="text-xs">{it.message}</span>
        </button>
      ))}
    </div>
  )
}

/* ─────────────────────────────── Tab: AI hậu kỳ ─────────────────────────────── */
function AiTab({ job, scenes, regen, update, regenerate, onPick }: {
  job: JobDetail; scenes: Scene[]; regen: number | null
  update: (i: number, p: Partial<Scene>) => void; regenerate: (i: number, text?: string, preview?: boolean) => Promise<Scene | null>; onPick: (i: number) => void
}) {
  const [instruction, setInstruction] = useState("")
  const [edits, setEdits] = useState<AiEdit[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [done, setDone] = useState<Set<number>>(new Set())

  const run = async () => {
    setLoading(true); setEdits(null); setDone(new Set())
    try {
      const r = await api.aiPolish(job.id, scenes, instruction)
      setEdits(r.edits)
      if (!r.edits.length) toast.success("AI không thấy cần sửa gì")
    } catch (e) { toast.error("AI hậu kỳ lỗi", { description: (e as Error).message }) } finally { setLoading(false) }
  }

  const apply = async (e: AiEdit) => {
    const patch: Partial<Scene> = {}
    if (e.subtitle) patch.subtitle = e.subtitle
    if (e.exclude) patch.excluded = true
    if (Object.keys(patch).length) update(e.id, patch)
    if (e.voiceover && !e.exclude) {
      update(e.id, { voiceover: e.voiceover, ...(job.kind === "review" ? { subtitle: e.voiceover } : {}) })
      if (!(await regenerate(e.id, e.voiceover, false))) return false
    }
    setDone((d) => new Set(d).add(e.id))
    return true
  }

  const applyAll = async () => {
    setApplying(true)
    let ok = 0
    await runPool((edits ?? []).filter((e) => !done.has(e.id)), REGEN_PARALLEL, async (e) => { if (await apply(e)) ok++ })
    setApplying(false)
    toast.success(`Đã áp dụng ${ok} đề xuất`)
  }

  const pending = (edits ?? []).filter((e) => !done.has(e.id))
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">AI (ChatGPT/Gemini đã đăng nhập) rà toàn bộ kịch bản: sửa lời cho tự nhiên, khớp độ dài hình, bỏ ký hiệu rác và cảnh trùng. Bạn duyệt từng đề xuất trước khi áp dụng.</p>
      <Textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} rows={2} className="text-[13px]"
        placeholder="Yêu cầu thêm (tuỳ chọn) — VD: giọng hài hước hơn, gọi nhân vật chính là “cậu bé”…" />
      <Button onClick={run} disabled={loading || applying}>
        {loading ? <Loader2 className="animate-spin" /> : <Wand2 />} {edits ? "Rà lại" : "AI hậu kỳ tự động"}
      </Button>

      {edits && edits.length > 0 && (
        <>
          <div className="flex items-center justify-between pt-1">
            <span className="text-xs font-medium">{edits.length} đề xuất · {pending.length} chưa áp dụng</span>
            <Button size="xs" variant="outline" disabled={!pending.length || applying || regen !== null} onClick={applyAll}>
              {applying ? <Loader2 className="animate-spin" /> : <Check />} Áp dụng tất cả
            </Button>
          </div>
          {edits.map((e) => {
            const s = scenes[e.id]
            const applied = done.has(e.id)
            return (
              <div key={e.id} className={cn("flex flex-col gap-1.5 rounded-md border border-border p-2.5", applied && "opacity-55")}>
                <div className="flex items-center gap-2">
                  <button className="text-xs font-semibold hover:text-primary" onClick={() => onPick(e.id)}>Cảnh #{e.id + 1}</button>
                  {e.exclude && <span className="rounded bg-destructive/10 px-1.5 text-[10px] text-destructive">đề xuất bỏ</span>}
                  <span className="ml-auto flex gap-1">
                    {applied ? <span className="flex items-center gap-1 text-[11px] text-success"><Check className="size-3" /> Đã áp dụng</span> : (
                      <>
                        <Button size="icon-xs" variant="ghost" title="Bỏ qua" onClick={() => setEdits(edits.filter((x) => x !== e))}><X /></Button>
                        <Button size="xs" disabled={applying || regen !== null} onClick={() => apply(e)}>
                          {regen === e.id ? <Loader2 className="animate-spin" /> : <Check />} Áp dụng
                        </Button>
                      </>
                    )}
                  </span>
                </div>
                {e.reason && <p className="text-[11px] text-muted-foreground">{e.reason}</p>}
                {e.voiceover && (
                  <div className="flex flex-col gap-1 text-[12px]">
                    <p className="text-muted-foreground line-through decoration-destructive/60">{s?.voiceover}</p>
                    <p className="text-foreground">{e.voiceover}</p>
                  </div>
                )}
                {e.subtitle && <p className="text-[11px]"><span className="text-muted-foreground">Phụ đề: </span>{e.subtitle}</p>}
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}

/* ─────────────────────────────── Danh sách ─────────────────────────────── */
function SceneList({ scenes, regen, levels, playing, onPlay, update, regenerate }: {
  scenes: Scene[]; regen: number | null; levels: Record<number, "error" | "warn">; playing: string | null
  onPlay: (url: string) => void; update: (i: number, p: Partial<Scene>) => void; regenerate: (i: number) => void
}) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {scenes.map((s, i) => {
        const url = s.tts_path ? mediaUrl(s.tts_path) : ""
        return (
          <div key={i} className={cn("grid grid-cols-[36px_1fr_auto] items-start gap-3 border-b border-border/60 px-4 py-2.5 last:border-0", s.excluded && "opacity-40")}>
            <Button variant={playing === url ? "default" : "outline"} size="icon-sm" disabled={!url} onClick={() => onPlay(url)} className="mt-1">
              {playing === url ? <Pause /> : <Play />}
            </Button>
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2 text-[10.5px] text-muted-foreground">
                {levels[i] && <AlertTriangle className={cn("size-3", levels[i] === "error" ? "text-destructive" : "text-warning")} />}
                <span className="tabular font-semibold">#{i + 1}</span>
                <span className="tabular">{fmtClock(s.clip_start)} → {fmtClock(s.clip_end)}</span>
                <span className="tabular">· {(s.tts_duration ?? 0).toFixed(1)}s</span>
                {s._tts_engine_used && <span className="rounded bg-muted px-1 uppercase">{s._tts_engine_used}</span>}
              </div>
              <Textarea value={s.voiceover} rows={1} className="min-h-9 resize-y py-2 text-[13px]" onChange={(e) => update(i, { voiceover: e.target.value })} />
            </div>
            <div className="mt-1 flex gap-1">
              <Button variant="ghost" size="icon-sm" title="Tạo lại giọng" disabled={regen !== null} onClick={() => regenerate(i)}>
                {regen === i ? <Loader2 className="animate-spin" /> : <RefreshCw />}
              </Button>
              <Button variant="ghost" size="icon-sm" title={s.excluded ? "Dùng lại" : "Bỏ câu"} onClick={() => update(i, { excluded: !s.excluded })}>
                {s.excluded ? <EyeOff /> : <Eye />}
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
