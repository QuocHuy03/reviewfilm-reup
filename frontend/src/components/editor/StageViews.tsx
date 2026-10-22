import {
  AlertTriangle, Captions, CheckCircle2, Info, CircleSlash, RefreshCw, ShieldCheck, Wand2, ExternalLink, Film, FolderOpen, Languages, Loader2, RotateCcw, StepForward, Trash2, XCircle,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Timeline } from "@/components/timeline/Timeline"
import { PublishSummary } from "./PublishPanel"
import { ReeditButton } from "./ReeditButton"
import { RedubButton } from "./RedubButton"
import { VoiceSelect } from "@/components/VoiceSelect"
import { SaveBadge } from "./SaveBadge"
import { StageHeader } from "./StageHeader"
import { draftFor, useDraftAutosave } from "@/hooks/useDraft"
import { layoutClips } from "@/components/timeline/useTimelinePlayer"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { api, bridge, mediaUrl } from "@/lib/api"
import { basename, fmtClock, fmtDuration } from "@/lib/format"
import type { JobDetail, LogLine, QaFix, QaReport, Scene } from "@/lib/types"
import { cn } from "@/lib/utils"
import { confirmAction } from "@/components/ConfirmHost"

const NO_MUTE = { video: false, voice: false, music: false }
const noop = () => {}
const boundVideos = new WeakSet<HTMLVideoElement>()

/* ═══════════════════════════════ Khung chung ═══════════════════════════════ */
/** Bố cục dùng cho MỌI bước: tiêu đề · (màn hình | bảng bên phải) · timeline. */
export function StageShell({ title, meta, dot, actions, monitor, side, timeline }: {
  title: string; meta?: ReactNode; dot?: string; actions?: ReactNode; monitor: ReactNode; side?: ReactNode; timeline: ReactNode
}) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card">
      <StageHeader title={title} meta={meta} dot={dot} actions={actions} />
      <div className={cn("grid min-h-0 flex-1", side ? "grid-cols-[minmax(0,1fr)_minmax(360px,430px)]" : "grid-cols-1")}>
        <div className="relative flex min-h-0 items-center justify-center overflow-hidden bg-black">{monitor}</div>
        {side && <div className="flex min-h-0 flex-col overflow-y-auto border-l border-border">{side}</div>}
      </div>
      {timeline}
    </div>
  )
}

/** Màn hình phát một file video (gốc hoặc đã xuất). */
function VideoMonitor({ path, videoRef, placeholder }: { path?: string; videoRef?: (el: HTMLVideoElement | null) => void; placeholder: ReactNode }) {
  if (!path) return <div className="flex flex-col items-center gap-2 text-xs text-white/45">{placeholder}</div>
  return <video ref={videoRef} src={mediaUrl(path)} controls preload="metadata" className="max-h-full max-w-full" />
}

/**
 * Timeline "tĩnh" cho các bước chưa có lời đọc / đã xuất xong: chọn cảnh, tua.
 * onPickClip(index) — bước Sửa kịch bản dùng để cuộn tới câu; video (nếu có) tua tới đoạn gốc của cảnh.
 */
/** Dịch phụ đề giữ nguyên thời gian video gốc → mỗi câu nằm đúng lúc nó nói (clip_start), không xếp nối nhau như Review. */
function realTimeClips(scenes: Scene[]) {
  const clips = scenes.flatMap((scene, index) => scene.excluded ? [] : [{
    index, scene, start: Math.max(0, scene.clip_start), dur: Math.max(0.2, (scene.clip_end || scene.clip_start + 1) - scene.clip_start) }])
  return { clips, total: clips.reduce((m, c) => Math.max(m, c.start + c.dur), 0) }
}

function useStaticTimeline(scenes: Scene[], realTime = false) {
  const { clips, total } = useMemo(() => (realTime ? realTimeClips(scenes) : layoutClips(scenes)), [scenes, realTime])
  const [time, setTime] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  /** Gắn thẻ <video> vào ref + theo dõi phát/dừng → nút Phát/Dừng trên timeline đổi icon đúng trạng thái. */
  const bindVideo = useCallback((ref: { current: HTMLVideoElement | null }) => (el: HTMLVideoElement | null) => {
    ref.current = el
    if (!el || boundVideos.has(el)) return
    boundVideos.add(el)
    setPlaying(!el.paused)
    el.addEventListener("play", () => setPlaying(true))
    el.addEventListener("pause", () => setPlaying(false))
    el.addEventListener("ended", () => setPlaying(false))
  }, [])
  return { clips, total, time, setTime, selected, setSelected, playing, bindVideo }
}

/* ═══════════════════════════════ Đang chạy ═══════════════════════════════ */
const STEPS: Record<string, [string, number][]> = {
  review: [["Tải video", 4], ["Whisper nhận dạng lời", 10], ["Vision AI phân tích phim", 30], ["Viết kịch bản", 45], ["Lồng tiếng", 55], ["Tự hậu kỳ", 70], ["Dựng video", 85]],
  reup: [["Tải video", 4], ["Whisper nhận dạng lời", 10], ["Dịch phụ đề", 30], ["Lồng tiếng", 55], ["Tự hậu kỳ", 70], ["Dựng video", 85]],
  srt: [["Whisper nhận dạng lời", 10], ["Dịch", 60], ["Xuất SRT", 95]],
  burn: [["Chuẩn bị", 0], ["Ghép phụ đề", 15]],
}

const isLocalVideo = (p: unknown): p is string => typeof p === "string" && /^[a-z]:[\\/]/i.test(p)

export function RunningStage({ job }: { job: JobDetail; logs?: LogLine[] }) {
  const tl = useStaticTimeline(job.scenes, job.kind === "vietsub")
  const video = useRef<HTMLVideoElement | null>(null)
  const steps = STEPS[job.kind] ?? []
  const cur = steps.reduce((acc, [, p], i) => (job.progress >= p ? i : acc), 0)
  const queued = job.status === "queued"
  // File trên máy thì xem được ngay — không phải chờ backend báo đường dẫn
  const source = job.result.video_path || (isLocalVideo(job.config.inp) ? job.config.inp : undefined)
  const nextAt = steps[cur + 1]?.[1] ?? 100
  const stepPct = Math.round(((job.progress - (steps[cur]?.[1] ?? 0)) / Math.max(1, nextAt - (steps[cur]?.[1] ?? 0))) * 100)
  const c = job.config as Record<string, unknown>
  const info: [string, string][] = ([
    ["Nguồn", isLocalVideo(c.inp) ? basename(c.inp) : String(c.inp ?? "")],
    ["Chế độ", KIND_TEXT[job.kind] ?? job.kind],
    ["Whisper", `${c.whisper_model ?? "base"} · ${String(c.device ?? "").startsWith("GPU") ? "GPU" : "CPU"}`],
    ["Giọng", c.voice ? String(c.voice).split(" — ").pop()! : ""],
    ["Khung hình", c.target_resolution === "1080x1920" ? "9:16 dọc" : c.target_resolution === "1280x720" ? "720p" : c.target_resolution ? "1080p" : ""],
    ["Hậu kỳ", [c.auto_post && "Tự hậu kỳ", c.script_edit === false && c.scene_preview === false && "Tự động hoàn toàn"].filter(Boolean).join(" · ")],
  ] as [string, string][]).filter(([, v]) => v)

  return (
    <StageShell title={queued ? `Đang xếp hàng${job.queue_pos ? ` #${job.queue_pos}` : ""}` : job.stage || "Đang xử lý…"} dot="bg-primary animate-pulse"
      meta={<span>{job.progress}% · {fmtDuration(job.elapsed)} · có thể chuyển trang, job vẫn chạy nền</span>}
      monitor={<VideoMonitor path={source} videoRef={tl.bindVideo(video)}
        placeholder={<><Loader2 className="size-6 animate-spin" /> Đang tải video…</>} />}
      actions={<>
        <ol className="flex items-center gap-1">
          {steps.map(([label], i) => {
            const done = !queued && i < cur
            const active = !queued && i === cur
            return (
              <li key={label} className="flex items-center gap-1">
                {i > 0 && <span className={cn("h-px w-3", done || active ? "bg-primary/50" : "bg-border")} />}
                {active ? (
                  <span className="flex items-center gap-1.5 rounded-full bg-primary px-2.5 py-1 text-[11.5px] font-medium text-primary-foreground">
                    <Loader2 className="size-3 animate-spin" /> {label}
                    <span className="tabular opacity-80">{Math.max(0, Math.min(99, stepPct))}%</span>
                  </span>
                ) : (
                  <span title={label} className={cn("flex size-6 items-center justify-center rounded-full border text-[10px] font-semibold",
                    done ? "border-success/50 bg-success/15 text-success" : "border-border text-muted-foreground")}>
                    {done ? <CheckCircle2 className="size-3.5" /> : i + 1}
                  </span>
                )}
              </li>
            )
          })}
        </ol>
        {info.length > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" title="Thông tin job"><Info /></Button>
            </TooltipTrigger>
            <TooltipContent side="bottom" align="end" className="p-3">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
                {info.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="opacity-60">{k}</dt>
                    <dd className="max-w-64 truncate text-right font-medium">{v}</dd>
                  </div>
                ))}
              </dl>
            </TooltipContent>
          </Tooltip>
        )}
      </>}
      timeline={<Timeline scenes={job.scenes} clips={tl.clips} total={tl.total} time={tl.time} playing={tl.playing} selected={tl.selected}
        muted={NO_MUTE} bgmName="" showMute={false}
        emptyHint={job.kind === "srt" || job.kind === "burn" ? "Job này không dựng cảnh — chỉ xuất phụ đề" : "Các cảnh sẽ hiện ở đây khi có kịch bản / bản dịch"}
        onSeek={tl.setTime} onSelect={(i) => { tl.setSelected(i); if (video.current) video.current.currentTime = job.scenes[i].clip_start }}
        onToggle={() => { const v = video.current; if (v) (v.paused ? v.play() : v.pause()) }} onToggleMute={noop} />}
    />
  )
}

const KIND_TEXT: Record<string, string> = { review: "Review phim", reup: "Dịch & Reup", vietsub: "Dịch phụ đề", srt: "Tách SRT", burn: "Ghép phụ đề" }

/* ═══════════════════════════════ Sửa kịch bản ═══════════════════════════════ */
// Giọng đọc tiếng Việt ~17 ký tự/giây (đo trên CapCut / Edge / VieNeu, đã cắt khoảng lặng)
const DUB_CPS = 17
// Căn thời gian như VideoLingo (khớp backend): mượn khoảng lặng sau tối đa 1.5s, dài hơn thì đọc nhanh nhẹ tối đa 1.2×
const DUB_TOLERANCE = 1.5
const DUB_MAX_SPEED = 1.2

/** Lồng tiếng giữ thời gian video: câu có kịp đọc trong khung (thời lượng câu + khoảng lặng mượn được) không. */
function readFit(scenes: Scene[], i: number) {
  const s = scenes[i]
  const next = scenes[i + 1]
  const gap = Math.max(0, (next ? next.clip_start : s.clip_end + DUB_TOLERANCE) - s.clip_end)
  const slot = Math.max(0.3, s.clip_end - s.clip_start + Math.min(gap, DUB_TOLERANCE))
  const need = s.speaker_id === -1 ? 0 : (s.voiceover || "").replace(/\s+/g, " ").trim().length / DUB_CPS
  return { slot, need, level: need > slot * DUB_MAX_SPEED ? "long" : need > slot ? "fast" : "ok" } as const
}

export function ScriptStage({ job }: { job: JobDetail }) {
  const [scenes, setScenes] = useState<Scene[]>(() => draftFor(job, "script")?.scenes ?? job.scenes)
  const saveState = useDraftAutosave(job.id, scenes)
  const [busy, setBusy] = useState(false)
  const tl = useStaticTimeline(scenes, job.kind === "vietsub")
  const video = useRef<HTMLVideoElement | null>(null)
  const items = useRef<Record<number, HTMLDivElement | null>>({})
  const words = useMemo(() => scenes.reduce((n, s) => n + (s.voiceover || "").split(/\s+/).filter(Boolean).length, 0), [scenes])
  // Dịch phụ đề + lồng tiếng: báo câu dài hơn thời gian câu thoại (vàng = đọc nhanh hơn, đỏ = AI sẽ rút gọn)
  const dub = job.kind === "vietsub" && !!job.config.dub_voice
  const fits = useMemo(() => (dub ? scenes.map((_, i) => readFit(scenes, i)) : []), [dub, scenes])
  // duyệt theo vai: danh sách nhân vật AI nhận ra (đổi được nhân vật từng câu trước khi tạo giọng)
  const cast = useMemo(() => Object.entries(job.result.dub_cast?.speakers ?? {})
    .map(([id, v]) => ({ id: Number(id), name: v.name || `NV${Number(id) + 1}`, female: v.gender === "female" }))
    .sort((a, b) => a.id - b.id), [job.result.dub_cast])
  const byRole = dub && cast.length > 0 && scenes.some((s) => s.speaker_id !== undefined)
  // giọng từng nhân vật: NGƯỜI DÙNG chọn (mặc định nam → giọng nam, nữ → giọng nữ đã chọn ở tab Lồng tiếng)
  // khớp backend: nam 1 giọng, nữ 1 giọng — "giọng nam" lỡ là giọng nữ thì dùng Nam Bắc, chưa chọn giọng nữ thì Nữ Bắc
  const rawMale = String(job.config.voice ?? "")
  const femaleVoice = String(job.config.voice_female || "Edge TTS — Nữ Bắc (miễn phí)")
  const maleVoice = !rawMale || rawMale.includes("Nữ") || rawMale === femaleVoice ? "Edge TTS — Nam Bắc (miễn phí)" : rawMale
  const [charVoices, setCharVoices] = useState<Record<string, string>>(() => ({ ...((job.config.char_voices as Record<string, string>) ?? {}) }))
  const voiceOf = (c: { id: number; female: boolean }) => charVoices[String(c.id)] || (c.female ? femaleVoice : maleVoice)
  const lineCount = useMemo(() => {
    const n: Record<number, number> = {}
    for (const s of scenes) if (s.speaker_id !== undefined) n[s.speaker_id] = (n[s.speaker_id] ?? 0) + 1
    return n
  }, [scenes])
  const longCount = fits.filter((f) => f.level === "long").length
  const fastCount = fits.filter((f) => f.level === "fast").length

  const pick = (i: number) => {
    tl.setSelected(i)
    const c = tl.clips.find((x) => x.index === i)
    if (c) tl.setTime(c.start)
    if (video.current) video.current.currentTime = scenes[i].clip_start
    items.current[i]?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }

  const submit = async (confirmed: boolean) => {
    setBusy(true)
    try {
      await api.confirm(job.id, confirmed
        ? { confirmed, scenes, ...(byRole ? { char_voices: Object.fromEntries(cast.map((c) => [String(c.id), voiceOf(c)])) } : {}) }
        : { confirmed })
      toast.success(confirmed ? (job.kind === "vietsub" && !dub ? "Đã xác nhận — bắt đầu ghép phụ đề" : "Đã xác nhận — bắt đầu lồng tiếng") : "Đã huỷ job")
    } catch (e) { toast.error((e as Error).message); setBusy(false) }   // thành công: giữ khoá nút tới khi chuyển bước
  }

  return (
    <StageShell title={job.kind === "review" ? "Sửa kịch bản thuyết minh" : byRole ? "Duyệt kịch bản theo vai" : "Sửa bản dịch"} dot="bg-warning animate-pulse"
      meta={<span className="flex items-center gap-2">{scenes.length} câu · {words.toLocaleString("vi-VN")} từ
        {dub && (longCount + fastCount > 0
          ? <span className="text-warning">· {longCount > 0 && <b className="text-destructive">{longCount} câu dài (AI sẽ rút gọn)</b>}{longCount > 0 && fastCount > 0 && " · "}{fastCount > 0 && `${fastCount} câu đọc nhanh nhẹ`}</span>
          : <span className="text-success">· mọi câu đọc vừa thời gian</span>)}
        {!dub && " · bấm cảnh trên timeline để tới câu đó"} <SaveBadge state={saveState} /></span>}
      actions={<>
        <Button variant="ghost" size="sm" disabled={busy} onClick={async () => {
            if (await confirmAction({ title: "Huỷ job?", danger: true, action: "Huỷ job", cancel: "Tiếp tục sửa",
              desc: "Job sẽ dừng và không xuất video. Các chỉnh sửa ở bước này sẽ không được dùng." })) submit(false)
          }}>Huỷ job</Button>
        <Button size="sm" onClick={() => submit(true)} disabled={busy || scenes.length === 0}>
          {busy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} {job.kind === "vietsub" && !dub ? "Xác nhận & ghép phụ đề" : "Xác nhận & lồng tiếng"}
        </Button>
      </>}
      monitor={<VideoMonitor path={job.result.video_path} videoRef={tl.bindVideo(video)} placeholder={<><Film className="size-6" /> Không có video gốc</>} />}
      side={<>
        {byRole && (
          <div className="flex flex-col gap-2 border-b border-border/60 bg-muted/30 px-3 py-3">
            <div>
              <p className="text-[13px] font-semibold">Giọng từng nhân vật</p>
              <p className="text-[11px] text-muted-foreground">Bạn tự chọn giọng cho từng nhân vật (bấm ▶ để nghe thử). Chưa đổi thì nam đọc giọng nam, nữ đọc giọng nữ ở tab Lồng tiếng.</p>
            </div>
            {cast.filter((c) => (lineCount[c.id] ?? 0) > 0).sort((a, b) => (lineCount[b.id] ?? 0) - (lineCount[a.id] ?? 0)).map((c) => (
              <div key={c.id} className="flex flex-col gap-1">
                <div className="flex items-center gap-2 text-[12px]">
                  <span className="font-medium">{c.name}</span>
                  <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", c.female ? "bg-pink-500/15 text-pink-600 dark:text-pink-300" : "bg-sky-500/15 text-sky-600 dark:text-sky-300")}>{c.female ? "Nữ" : "Nam"}</span>
                  <span className="text-[11px] text-muted-foreground">{lineCount[c.id] ?? 0} câu</span>
                </div>
                <VoiceSelect value={voiceOf(c)} onChange={(v) => setCharVoices((m) => ({ ...m, [String(c.id)]: v }))} />
              </div>
            ))}
          </div>
        )}
        {scenes.map((s, i) => (
        <div key={i} ref={(el) => { items.current[i] = el }} onClick={() => pick(i)}
          className={cn("group grid cursor-pointer grid-cols-[40px_1fr_28px] gap-2 border-b border-border/60 px-3 py-2.5", tl.selected === i && "bg-primary/5")}>
          <div className="pt-1 text-xs">
            <div className={cn("tabular font-semibold", tl.selected === i ? "text-primary" : "text-muted-foreground")}>#{i + 1}</div>
            <div className="tabular mt-0.5 text-[10px] text-muted-foreground/70">{fmtClock(s.clip_start)}</div>
          </div>
          <div className="flex flex-col gap-1">
            {byRole && (
              <select value={s.speaker_id ?? 0} onClick={(e) => e.stopPropagation()} onFocus={() => pick(i)}
                onChange={(e) => setScenes(scenes.map((x, j) => j === i ? { ...x, speaker_id: Number(e.target.value) } : x))}
                className={cn("h-7 w-fit max-w-full rounded-md border border-input bg-background px-2 text-[12px] font-medium",
                  s.speaker_id === -1 ? "text-muted-foreground" : cast.find((c) => c.id === s.speaker_id)?.female ? "text-pink-600 dark:text-pink-300" : "text-sky-600 dark:text-sky-300")}
                title="Nhân vật nói câu này — đổi nếu AI gán nhầm">
                {cast.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.female ? "nữ" : "nam"})</option>)}
                <option value={-1}>— Không lồng tiếng (nhạc, tiếng động…)</option>
              </select>
            )}
            {(s.orig_text || s.description) && <p className="line-clamp-2 text-[11px] text-muted-foreground">{s.orig_text || s.description}</p>}
            <Textarea value={s.voiceover} rows={2} className="min-h-0 resize-y text-[13px] leading-relaxed" onFocus={() => pick(i)}
              onChange={(e) => setScenes(scenes.map((x, j) => j === i ? { ...x, voiceover: e.target.value, subtitle: e.target.value } : x))} />
            {dub && fits[i] && (
              <p className={cn("tabular text-[10.5px]", fits[i].level === "long" ? "text-destructive" : fits[i].level === "fast" ? "text-warning" : "text-muted-foreground/70")}>
                {fits[i].slot.toFixed(1)}s · cần ~{fits[i].need.toFixed(1)}s đọc
                {fits[i].level === "long" ? " — dài quá, AI sẽ rút gọn (hoặc tự sửa ngắn lại)" : fits[i].level === "fast" ? " — hơi dài, sẽ đọc nhanh nhẹ (≤ 1.2×)" : ""}
              </p>
            )}
          </div>
          <Button variant="ghost" size="icon-xs" className="opacity-0 group-hover:opacity-100" title="Xoá câu"
            onClick={(e) => { e.stopPropagation(); setScenes(scenes.filter((_, j) => j !== i)) }}><Trash2 /></Button>
        </div>
      ))}
      </>}
      timeline={<Timeline scenes={scenes} clips={tl.clips} total={tl.total} time={tl.time} playing={tl.playing} selected={tl.selected}
        muted={NO_MUTE} bgmName="" showMute={false}
        onSeek={tl.setTime} onSelect={pick} onToggle={() => { const v = video.current; if (v) (v.paused ? v.play() : v.pause()) }} onToggleMute={noop}
        onReorder={(from, to) => setScenes((prev) => moveItem(prev, from, to))}
        onTrim={(i, patch) => setScenes((prev) => prev.map((x, j) => (j === i ? { ...x, ...patch } : x)))} />}
    />
  )
}

/** Đổi chỗ phần tử `from` tới vị trí `to` (chỉ số trong mảng gốc). */
export function moveItem<T>(arr: T[], from: number, to: number): T[] {
  if (from === to) return arr
  const next = arr.slice()
  const [it] = next.splice(from, 1)
  next.splice(to > from ? to - 1 : to, 0, it)
  return next
}

/* ═══════════════════════════════ Xong ═══════════════════════════════ */
/** Video đã xuất + timeline chạy theo video (bố cục cảnh trùng với video xuất ra). */
export function DoneStage({ job }: { job: JobDetail }) {
  const tl = useStaticTimeline(job.scenes, job.kind === "vietsub")
  const video = useRef<HTMLVideoElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const raf = useRef(0)

  const attach = useCallback((el: HTMLVideoElement | null) => {
    video.current = el
    if (!el) return
    const loop = () => { tl.setTime(el.currentTime); if (!el.paused) raf.current = requestAnimationFrame(loop) }
    el.onplay = () => { setPlaying(true); raf.current = requestAnimationFrame(loop) }
    el.onpause = () => { setPlaying(false); cancelAnimationFrame(raf.current); tl.setTime(el.currentTime) }
    el.onseeked = () => tl.setTime(el.currentTime)
  }, [tl.setTime]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => cancelAnimationFrame(raf.current), [])
  useEffect(() => { const c = tl.clips.find((x) => tl.time >= x.start && tl.time < x.start + x.dur); if (c) tl.setSelected(c.index) }, [tl.time, tl.clips]) // eslint-disable-line react-hooks/exhaustive-deps

  const seek = (t: number) => { tl.setTime(t); if (video.current) video.current.currentTime = t }
  const files = ([
    ["Video", job.result.output_path, Film, "bg-sky-500/15 text-sky-500"],
    ["Phụ đề tiếng Việt", job.result.srt_path || job.result.vi_srt, Captions, "bg-violet-500/15 text-violet-500"],
    ["Phụ đề gốc", job.result.original_srt, Languages, "bg-muted text-muted-foreground"],
  ].filter(([, p]) => p) as [string, string, typeof Film, string][])

  return (
    <StageShell title="Hoàn thành" dot="bg-success" meta={`${tl.clips.length} cảnh · ${fmtDuration(tl.total)} · xong sau ${fmtDuration(job.elapsed)}`}
      actions={<>
        {(job.kind === "review" || job.kind === "reup") && job.scenes.length > 0 && <ReeditButton job={job} />}
        {job.kind === "vietsub" && job.result.vi_srt && <RedubButton job={job} />}
        {job.result.output_path && <Button size="sm" variant="outline" onClick={() => bridge.open(job.result.output_path!)}><Film /> Mở video</Button>}
      </>}
      monitor={<VideoMonitor path={job.result.output_path} videoRef={attach} placeholder={<><CheckCircle2 className="size-6 text-success" /> Hoàn thành</>} />}
      side={
        <div className="flex flex-col gap-5 p-4">
          <section>
            <h4 className="mb-2 text-[10.5px] font-semibold tracking-wider text-muted-foreground uppercase">Tệp xuất</h4>
            <div className="flex flex-col gap-1.5">
              {files.map(([label, p, Icon, tone]) => (
                <div key={label} className="group flex items-center gap-3 rounded-lg border border-border bg-background/40 px-2.5 py-2 hover:border-primary/40">
                  <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-md [&_svg]:size-4", tone)}><Icon /></span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[12.5px] font-medium">{label}</p>
                    <p className="truncate font-mono text-[10.5px] text-muted-foreground" title={p}>{basename(p)}</p>
                  </div>
                  <Button variant="ghost" size="icon-sm" title="Mở" onClick={() => bridge.open(p)}><ExternalLink /></Button>
                  <Button variant="ghost" size="icon-sm" title="Hiện trong thư mục" onClick={() => bridge.reveal(p)}><FolderOpen /></Button>
                </div>
              ))}
            </div>
          </section>
          {(job.kind === "review" || job.kind === "reup") && job.result.output_path && <>
            <PublishSummary jobId={job.id} initial={job.result.publish} />
            <QaPanel jobId={job.id} initial={job.result.qa} fixes={job.result.qa_fixes} />
          </>}
          <section className="min-h-0">
            <h4 className="mb-2 text-[10.5px] font-semibold tracking-wider text-muted-foreground uppercase">Kịch bản · {tl.clips.length} câu</h4>
            <div className="flex flex-col gap-0.5">
              {tl.clips.map((c, k) => {
                const on = tl.selected === c.index
                return (
                  <button key={c.index} onClick={() => seek(c.start)}
                    className={cn("flex gap-2.5 rounded-md px-2 py-2 text-left transition", on ? "bg-primary/10" : "hover:bg-muted/60")}>
                    <span className={cn("tabular mt-px h-fit shrink-0 rounded px-1.5 py-0.5 font-mono text-[10.5px]", on ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
                      {fmtClock(c.start)}
                    </span>
                    <span className={cn("line-clamp-3 text-[12.5px] leading-relaxed", on ? "text-foreground" : "text-muted-foreground")}>
                      {job.scenes[c.index].voiceover || `Cảnh ${k + 1}`}
                    </span>
                  </button>
                )
              })}
            </div>
          </section>
        </div>
      }
      timeline={<Timeline scenes={job.scenes} clips={tl.clips} total={tl.total} time={tl.time} playing={playing} selected={tl.selected}
        muted={NO_MUTE} bgmName="" showMute={false}
        onSeek={seek} onSelect={(i) => { const c = tl.clips.find((x) => x.index === i); if (c) seek(c.start) }}
        onToggle={() => { const v = video.current; if (v) (v.paused ? v.play() : v.pause()) }} onToggleMute={noop} />}
    />
  )
}

const QA_TONE = {
  ok: { icon: CheckCircle2, cls: "text-success" },
  warn: { icon: AlertTriangle, cls: "text-warning" },
  fail: { icon: XCircle, cls: "text-destructive" },
} as const

/** Kiểm tra chất lượng video đã xuất: độ dài, khung hình, âm thanh, màn đen, hình đứng, khớp hình–lời, phụ đề. */
function QaPanel({ jobId, initial, fixes }: { jobId: string; initial?: QaReport; fixes?: QaFix[] }) {
  const [qa, setQa] = useState(initial)
  const [busy, setBusy] = useState(false)
  useEffect(() => setQa(initial), [initial])
  const recheck = async () => {
    setBusy(true)
    try { setQa(await api.recheckQa(jobId)) }
    catch (e) { toast.error("Không kiểm tra được", { description: (e as Error).message }) }
    finally { setBusy(false) }
  }
  const tone = !qa ? "" : qa.score >= 90 ? "bg-success/15 text-success" : qa.score >= 70 ? "bg-warning/15 text-warning" : "bg-destructive/15 text-destructive"
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <h4 className="text-[10.5px] font-semibold tracking-wider text-muted-foreground uppercase">Kiểm tra chất lượng</h4>
        {qa && <span className={cn("tabular rounded px-1.5 py-0.5 text-[10.5px] font-semibold", tone)}>{qa.score}/100</span>}
        <Button variant="ghost" size="xs" className="ml-auto" disabled={busy} onClick={recheck}>
          {busy ? <Loader2 className="animate-spin" /> : qa ? <RefreshCw /> : <ShieldCheck />} {qa ? "Kiểm tra lại" : "Kiểm tra"}
        </Button>
      </div>
      {!!fixes?.length && (
        <div className="mb-2 flex flex-col gap-1 rounded-lg border border-primary/25 bg-primary/5 px-2.5 py-2">
          {fixes.map((f) => (
            <p key={f.round} className="flex items-start gap-1.5 text-[11px] leading-snug">
              <Wand2 className="mt-px size-3 shrink-0 text-primary" />
              <span>
                <b className="font-medium">Tự sửa vòng {f.round}</b>{f.scenes.length > 0 && ` · cảnh ${f.scenes.map((n) => `#${n}`).join(", ")}`}: {f.actions.join(", ")}
                <span className="tabular text-muted-foreground"> · {f.before} → {f.after} điểm</span>
              </span>
            </p>
          ))}
        </div>
      )}
      {qa ? (
        <div className="flex flex-col divide-y divide-border/60 rounded-lg border border-border bg-background/40">
          {qa.checks.map((c) => {
            const { icon: Icon, cls } = QA_TONE[c.status]
            return (
              <div key={c.id} className="flex items-start gap-2.5 px-2.5 py-2">
                <Icon className={cn("mt-px size-3.5 shrink-0", cls)} />
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] font-medium">{c.label}</p>
                  <p className="text-[11px] leading-snug break-words text-muted-foreground">{c.detail}</p>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="rounded-lg border border-dashed border-border px-3 py-2.5 text-[11.5px] text-muted-foreground">
          Soi lại video đã xuất: độ dài, khung hình, âm thanh, màn đen, hình đứng, khớp hình–lời, phụ đề.
        </p>
      )}
    </section>
  )
}

/* ═══════════════════════════════ Lỗi / đã huỷ ═══════════════════════════════ */
export function FailedStage({ job, onResumed }: { job: JobDetail; onResumed: () => void }) {
  const { openJob } = useStore()
  const tl = useStaticTimeline(job.scenes, job.kind === "vietsub")
  const video = useRef<HTMLVideoElement | null>(null)
  const [busy, setBusy] = useState<"" | "resume" | "retry">("")
  const isError = job.status === "error"

  const resume = async () => {
    setBusy("resume")
    try { await api.resume(job.id); toast.success(`Tiếp tục từ: ${job.resume_from}`); onResumed() }
    catch (e) { toast.error("Không tiếp tục được", { description: (e as Error).message }) }
    finally { setBusy("") }
  }
  const retry = async () => {
    setBusy("retry")
    try { const n = await api.retry(job.id); toast.success("Đã tạo job chạy lại từ đầu"); openJob(n.id) }
    catch (e) { toast.error("Không chạy lại được", { description: (e as Error).message }) }
    finally { setBusy("") }
  }

  // Mất thư mục tạm nhưng đã có kịch bản → dùng lại kịch bản (job mới đọc lại giọng, dừng ở Hậu kỳ)
  const canReuse = !job.resumable && (job.kind === "review" || job.kind === "reup") && job.scenes.some((x) => (x.voiceover || "").trim())
  return (
    <StageShell title={isError ? `Job bị lỗi${job.stage ? ` ở bước: ${job.stage}` : ""}` : "Job đã huỷ"} dot={isError ? "bg-destructive" : "bg-muted-foreground"}
      meta="Chi tiết đầy đủ trong Nhật ký"
      actions={<>
        {job.resumable && (
          <Button size="sm" onClick={resume} disabled={!!busy}>
            {busy === "resume" ? <Loader2 className="animate-spin" /> : <StepForward />} Tiếp tục từ “{job.resume_from}”
          </Button>
        )}
        {canReuse && <ReeditButton job={job} label="Dùng lại kịch bản" />}
        <Button size="sm" variant={job.resumable || canReuse ? "outline" : "default"} onClick={retry} disabled={!!busy}>
          {busy === "retry" ? <Loader2 className="animate-spin" /> : <RotateCcw />} Chạy lại từ đầu
        </Button>
      </>}
      monitor={<VideoMonitor path={job.result.video_path} videoRef={tl.bindVideo(video)} placeholder={<><Film className="size-6" /> Không có video</>} />}
      side={
        <div className="flex flex-col gap-3 p-4">
          <div className="flex items-center gap-2">
            {isError ? <XCircle className="size-5 text-destructive" /> : <CircleSlash className="size-5 text-muted-foreground" />}
            <span className="text-sm font-semibold">{isError ? "Lỗi" : "Đã huỷ"}</span>
          </div>
          {job.error && <pre className="max-h-72 overflow-y-auto rounded-md bg-destructive/5 p-3 text-xs whitespace-pre-wrap text-destructive">{job.error}</pre>}
          {job.resumable ? (
            <p className="text-xs text-muted-foreground">Các bước đã xong được giữ lại — “Tiếp tục” chạy tiếp từ bước hỏng, không làm lại từ đầu.</p>
          ) : canReuse ? (
            <p className="text-xs text-muted-foreground">Không tiếp tục được (thư mục tạm đã bị dọn), nhưng kịch bản {job.scenes.length} cảnh vẫn còn — <b>Dùng lại kịch bản</b> để đọc lại giọng & dựng lại, bỏ qua Whisper và bước viết kịch bản.</p>
          ) : (job.kind === "review" || job.kind === "reup") && (
            <p className="text-xs text-muted-foreground">Job này không tiếp tục được (lỗi trước khi xong bước đầu, hoặc chạy từ bản cũ) — chạy lại từ đầu với cùng cấu hình.</p>
          )}
        </div>
      }
      timeline={<Timeline scenes={job.scenes} clips={tl.clips} total={tl.total} time={tl.time} playing={tl.playing} selected={tl.selected}
        muted={NO_MUTE} bgmName="" showMute={false} emptyHint="Job dừng trước khi có kịch bản"
        readOnlyHint={job.resumable ? `Bấm "Tiếp tục" để quay lại bước ${job.resume_from || "đang dở"} — ở đó kéo đổi thứ tự / cắt cảnh được.` : undefined}
        onSeek={tl.setTime} onSelect={(i) => { tl.setSelected(i); if (video.current) video.current.currentTime = job.scenes[i].clip_start }}
        onToggle={() => { const v = video.current; if (v) (v.paused ? v.play() : v.pause()) }} onToggleMute={noop} />}
    />
  )
}
