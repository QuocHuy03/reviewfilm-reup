import {
  AlertTriangle, ArrowLeftToLine, ArrowRightToLine, Captions, ChevronLeft, ChevronRight, CircleHelp, Crosshair, Eye, EyeOff, Film,
  Mic, Music2, Pause, Play, Redo2, SkipBack, SkipForward, Undo2, Volume2, VolumeX,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react"
import { toast } from "sonner"
import { LaneHeader, ZoomControl, fmtRuler, type LaneSlot } from "./LaneHeader"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fmtClock } from "@/lib/format"
import type { Scene } from "@/lib/types"
import { cn } from "@/lib/utils"
import type { Clip, EditMode, TrackKey } from "./useTimelinePlayer"

const HEADER_W = 150
const MIN_PPS = 4        // pixel / giây
const MAX_PPS = 240
const TICK_STEPS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]

/** Cấu hình track: chiều cao cố định để các hàng luôn thẳng nhau. */
const TRACKS = {
  video: { label: "Video", sub: "source", icon: Film, h: 46, accent: "bg-sky-400", text: "text-sky-300", clip: "bg-slate-600/90 border-slate-400/40" },
  voice: { label: "Voice", sub: "TTS", icon: Mic, h: 34, accent: "bg-orange-400", text: "text-orange-300", clip: "bg-orange-600/85 border-orange-300/40" },
  subtitle: { label: "Subtitle", sub: "on video", icon: Captions, h: 34, accent: "bg-violet-400", text: "text-violet-300", clip: "bg-violet-600/85 border-violet-300/40" },
  music: { label: "Music", sub: "", icon: Music2, h: 30, accent: "bg-emerald-400", text: "text-emerald-300", clip: "bg-emerald-600/80 border-emerald-300/40" },
} as const
const RULER_H = 22
const HIDDEN_H = 14          // làn đã tắt mắt: còn 1 dải mỏng

type Props = {
  scenes: Scene[]
  clips: Clip[]
  total: number
  time: number
  playing: boolean
  selected: number | null
  muted: Record<TrackKey, boolean>
  bgmName: string
  issues?: Record<number, "error" | "warn">
  /** false: ẩn nút loa (bước chưa có âm thanh để nghe thử) */
  showMute?: boolean
  /** Ẩn/hiện phụ đề trên màn xem trước (nút mắt ở track Phụ đề). Không truyền → không có nút. */
  subtitleVisible?: boolean
  onToggleSubtitle?: () => void
  /** Chữ hiện giữa timeline khi chưa có cảnh nào */
  emptyHint?: string
  /** Kéo mép clip Video: đổi điểm đầu/cuối đoạn hình gốc của cảnh `index`. */
  onTrim?: (index: number, patch: Partial<Pick<Scene, "clip_start" | "clip_end">>) => void
  /** Kéo thân clip Video: đưa cảnh `from` tới trước cảnh `to` (chỉ số trong mảng scenes; to = scenes.length → cuối). */
  onReorder?: (from: number, to: number) => void
  /** Ngay trước thay đổi đầu tiên của một lượt kéo mép — để lưu bản Hoàn tác. */
  onEditStart?: () => void
  /** Đang kéo mép: hiện khung hình gốc tại giây này. */
  onPeek?: (sourceT: number) => void
  /** Cách dựng: Review chiếu hình gốc dài bằng lời; Reup kéo giãn đoạn hình cho vừa lời. */
  mode?: EditMode
  /** Độ dài video gốc — giới hạn khi nới mép cuối. */
  videoDuration?: number
  /** Hoàn tác / làm lại — có thì hiện nút trên thanh công cụ. */
  onUndo?: () => void
  onRedo?: () => void
  canUndo?: boolean
  canRedo?: boolean
  /** Màn chỉ xem: kéo cảnh thì hiện thông báo này (vd "Kéo được ở bước Hậu kỳ & xác nhận"). */
  readOnlyHint?: string
  /** Bỏ cảnh đang chọn — có thì hiện nút. */
  onToggleExcluded?: (index: number) => void
  onSeek: (t: number) => void
  onSelect: (index: number) => void
  onToggle: () => void
  onToggleMute: (k: TrackKey) => void
}

/** Timeline nhiều track kiểu CapCut: Video · Lời đọc · Phụ đề · Nhạc nền, thước thời gian, đầu phát, zoom. */
export function Timeline({ scenes, clips, total, time, playing, selected, muted, bgmName, issues = {}, showMute = true, subtitleVisible, onToggleSubtitle, emptyHint = "Chưa có cảnh", onTrim: onTrimProp, onReorder: onReorderProp, onEditStart: onEditStartProp, onPeek: onPeekProp, mode = "review", videoDuration, onUndo, onRedo, canUndo, canRedo, onToggleExcluded, readOnlyHint = "Đổi thứ tự / cắt cảnh được ở bước Sửa kịch bản và Hậu kỳ & xác nhận (khi job dừng chờ bạn).", onSeek: onSeekProp, onSelect: onSelectProp, onToggle, onToggleMute }: Props) {
  // Trang cha truyền callback mới mỗi lần render (mỗi khung hình khi phát) → bọc thành hàm cố định đọc bản mới nhất,
  // để các làn clip (useMemo bên dưới) không phải dựng lại 60 lần/giây.
  const latest = useRef({ onSeekProp, onSelectProp, onTrimProp, onReorderProp, onEditStartProp, onPeekProp })
  latest.current = { onSeekProp, onSelectProp, onTrimProp, onReorderProp, onEditStartProp, onPeekProp }
  const onSeek = useCallback((t: number) => latest.current.onSeekProp(t), [])
  const onSelect = useCallback((i: number) => latest.current.onSelectProp(i), [])
  const trimS = useCallback((i: number, p: Partial<Pick<Scene, "clip_start" | "clip_end">>) => latest.current.onTrimProp?.(i, p), [])
  const reorderS = useCallback((from: number, to: number) => latest.current.onReorderProp?.(from, to), [])
  const onEditStart = useCallback(() => latest.current.onEditStartProp?.(), [])
  const onPeek = useCallback((t: number) => latest.current.onPeekProp?.(t), [])
  const onTrim = onTrimProp ? trimS : undefined
  const onReorder = onReorderProp ? reorderS : undefined

  const scroller = useRef<HTMLDivElement>(null)
  // con mắt từng làn (kiểu CapCut): tắt = làn thu thành dải mỏng, ẩn nội dung cho gọn — nhớ lựa chọn
  const [hidden, setHidden] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem("rf.tl.lanes") || "{}") } catch { return {} }
  })
  const toggleLane = (k: string) => setHidden((m) => {
    const n = { ...m, [k]: !m[k] }
    try { localStorage.setItem("rf.tl.lanes", JSON.stringify(n)) } catch { /* bỏ qua */ }
    return n
  })
  const laneH = (k: keyof typeof TRACKS) => (hidden[k] ? HIDDEN_H : TRACKS[k].h)
  const [pps, setPps] = useState(24)
  const [fitted, setFitted] = useState(false)
  const [follow, setFollow] = useState(true)
  const width = total > 0 ? total * pps + 48 : 0

  const fit = useCallback(() => {
    const w = (scroller.current?.clientWidth ?? 800) - 48
    if (total > 0) setPps(Math.min(MAX_PPS, Math.max(MIN_PPS, w / total)))
  }, [total])
  useEffect(() => { if (!fitted && total > 0) { fit(); setFitted(true) } }, [fit, fitted, total])

  // Đang phát: giữ đầu phát trong khung nhìn
  useEffect(() => {
    const el = scroller.current
    if (!el || !playing || !follow) return
    const x = time * pps
    if (x < el.scrollLeft + 40 || x > el.scrollLeft + el.clientWidth - 60) el.scrollLeft = x - el.clientWidth * 0.25
  }, [time, pps, playing, follow])

  // Ctrl + lăn chuột = zoom
  // Lăn chuột thường = cuộn ngang (nhiều cảnh vẫn đi hết được)
  const onWheel = (e: React.WheelEvent) => {
    const el = scroller.current
    if (!e.ctrlKey) {
      if (el && Math.abs(e.deltaY) > Math.abs(e.deltaX)) el.scrollLeft += e.deltaY
      return
    }
    setPps((p) => Math.min(MAX_PPS, Math.max(MIN_PPS, p * (e.deltaY < 0 ? 1.15 : 1 / 1.15))))
  }
  // Ctrl + lăn phải chặn zoom cả trang → listener không passive
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const block = (e: WheelEvent) => { if (e.ctrlKey) e.preventDefault() }
    el.addEventListener("wheel", block, { passive: false })
    return () => el.removeEventListener("wheel", block)
  }, [])

  // Khung nhìn hiện tại (cho thanh tổng quan)
  const [view, setView] = useState({ left: 0, w: 1 })
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const upd = () => setView({ left: el.scrollLeft, w: el.clientWidth })
    upd()
    el.addEventListener("scroll", upd)
    const ro = new ResizeObserver(upd)
    ro.observe(el)
    return () => { el.removeEventListener("scroll", upd); ro.disconnect() }
  }, [])

  // Kéo trên thước / vùng trống để tua
  const timeFromEvent = (e: ReactPointerEvent | PointerEvent) => {
    const el = scroller.current!
    const t = (e.clientX - el.getBoundingClientRect().left + el.scrollLeft) / pps
    return Math.max(0, Math.min(total, t))
  }
  const empty = clips.length === 0
  const startScrub = (e: ReactPointerEvent) => {
    if (empty) return
    onSeek(timeFromEvent(e))
    const move = (ev: PointerEvent) => onSeek(timeFromEvent(ev))
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up) }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }

  const step = TICK_STEPS.find((s) => s * pps >= 72) ?? 600
  const ticks: number[] = []
  for (let t = 0; t <= total + step; t += step) ticks.push(t)

  const cur = clips.findIndex((c) => time >= c.start && time < c.start + c.dur)
  const jump = (dir: -1 | 1) => {
    const i = cur < 0 ? (dir > 0 ? 0 : clips.length - 1) : cur + dir
    const c = clips[Math.max(0, Math.min(clips.length - 1, i))]
    if (c) { onSeek(c.start); onSelect(c.index) }
  }
  const pick = (c: Clip) => { onSelect(c.index); onSeek(c.start) }

  // ── Kéo thả trên track Video ──
  // move: cả cảnh (hình + lời + phụ đề) đi theo chuột, các cảnh khác dạt ra chừa chỗ, vạch vàng = vị trí thả.
  // trim: kéo mép đổi điểm đầu/cuối đoạn hình gốc, hít vào ranh giới cảnh kề để nối liền.
  const [drag, setDrag] = useState<{ index: number; dx: number; label: string; kind: "move" | "trim"; pos?: number } | null>(null)
  const MIN_SRC = 0.3
  const SNAP_PX = 8

  /** Vị trí chèn (0 … số cảnh còn lại) khi thả cảnh `c` lệch dx px: tâm cảnh đang kéo vượt qua tâm cảnh nào (theo vị trí gốc) thì xếp sau cảnh đó. */
  const insertPos = (c: Clip, dx: number) => {
    const center = c.start + c.dur / 2 + dx / pps
    return clips.filter((x) => x.index !== c.index && x.start + x.dur / 2 < center).length
  }

  /** Bố cục xem trước khi đang kéo: các cảnh khác xếp lại như sau khi thả. */
  const preview = new Map<number, number>()
  if (drag?.kind === "move" && drag.pos !== undefined) {
    const others = clips.filter((x) => x.index !== drag.index)
    const dragged = clips.find((x) => x.index === drag.index)!
    let t = 0
    others.forEach((x, k) => {
      if (k === drag.pos) { preview.set(-1, t); t += dragged.dur }
      preview.set(x.index, t)
      t += x.dur
    })
    if (!preview.has(-1)) preview.set(-1, t)
  }
  /** Toạ độ px của clip trên mọi làn (đang kéo: cảnh kéo theo chuột, cảnh khác theo bố cục xem trước). */
  const clipX = (c: Clip) =>
    drag?.kind === "move" ? (c.index === drag.index ? c.start * pps + drag.dx : (preview.get(c.index) ?? c.start) * pps) : c.start * pps

  const dragRole = (c: Clip) => (drag?.kind === "move" ? (drag.index === c.index ? "self" as const : "other" as const) : undefined)

  /** Kéo mép: dịch điểm đầu/cuối đoạn hình gốc theo số giây tương ứng trên timeline. */
  const startTrim = (e: ReactPointerEvent, c: Clip, field: "clip_start" | "clip_end") => {
    e.stopPropagation()
    e.preventDefault()
    onSelect(c.index)
    const k = clips.findIndex((x) => x.index === c.index)
    // Điểm hít: cuối cảnh trước (cho mép đầu) / đầu cảnh sau (cho mép cuối) trên video gốc → nối liền, không hở, không lặp hình
    const snapTo = field === "clip_start" ? clips[k - 1]?.scene.clip_end : clips[k + 1]?.scene.clip_start
    const snapName = field === "clip_start" ? "nối liền cảnh trước" : "nối liền cảnh sau"
    const x0 = e.clientX
    const orig = c.scene[field]
    let last = orig
    const move = (ev: PointerEvent) => {
      let v = +(orig + (ev.clientX - x0) / pps).toFixed(2)
      let snapped = false
      if (snapTo !== undefined && Math.abs(v - snapTo) * pps <= SNAP_PX) { v = snapTo; snapped = true }
      if (field === "clip_start") v = Math.max(0, Math.min(v, c.scene.clip_end - MIN_SRC))
      else v = Math.max(c.scene.clip_start + MIN_SRC, Math.min(v, videoDuration ?? Infinity))
      const len = (field === "clip_start" ? c.scene.clip_end - v : v - c.scene.clip_start).toFixed(1)
      setDrag({ index: c.index, dx: 0, kind: "trim", label: `${field === "clip_start" ? "Đầu" : "Cuối"} ${fmtClock(v)} · ${len}s${snapped ? ` · ${snapName}` : ""}` })
      if (v === last) return
      if (last === orig) onEditStart?.()          // lưu bản để Hoàn tác — 1 lần cho cả lượt kéo
      last = v
      onTrim?.(c.index, { [field]: v })
      onPeek?.(field === "clip_start" ? v : v - 0.05)
    }
    const up = () => {
      setDrag(null)
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", up)
      onSeek(c.start)
    }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }

  /** Kéo thân: bấm (không kéo) = chọn; kéo quá 4px = dời cả cảnh, thả để đổi thứ tự. Kéo sát mép khung → tự cuộn. */
  const startMove = (e: ReactPointerEvent, c: Clip) => {
    e.stopPropagation()
    if (!onReorder || clips.length < 2) {
      pick(c)
      // Màn chỉ xem (job đang chạy / đã xong / lỗi): kéo thì báo rõ khi nào mới kéo được, thay vì im lặng
      if (!onReorder && readOnlyHint) {
        const x0 = e.clientX
        const move = (ev: PointerEvent) => {
          if (Math.abs(ev.clientX - x0) < 8) return
          off()
          toast.info("Timeline này chỉ để xem", { id: "tl-readonly", description: readOnlyHint })
        }
        const off = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", off) }
        window.addEventListener("pointermove", move)
        window.addEventListener("pointerup", off)
      }
      return
    }
    const el = scroller.current!
    const x0 = e.clientX
    const scroll0 = el.scrollLeft
    let lastX = x0
    let moved = false
    const update = () => {
      const dx = lastX - x0 + (el.scrollLeft - scroll0)
      const pos = insertPos(c, dx)
      setDrag({ index: c.index, dx, kind: "move", pos, label: `→ vị trí ${pos + 1}/${clips.length}` })
    }
    const timer = window.setInterval(() => {            // tự cuộn khi giữ chuột sát mép
      if (!moved) return
      // càng sát / vượt mép càng cuộn nhanh → kéo cảnh đi xa trên timeline dài vẫn nhanh
      const r = el.getBoundingClientRect()
      const ZONE = 70
      const over = lastX < r.left + ZONE ? lastX - (r.left + ZONE) : lastX > r.right - ZONE ? lastX - (r.right - ZONE) : 0
      if (over) {
        const before = el.scrollLeft
        el.scrollLeft += Math.sign(over) * Math.min(80, 6 + Math.abs(over) * 0.6)
        if (el.scrollLeft !== before) update()
      }
    }, 30)
    const move = (ev: PointerEvent) => {
      lastX = ev.clientX
      if (!moved && Math.abs(lastX - x0) < 4) return
      if (!moved) { moved = true; onSelect(c.index) }
      update()
    }
    const up = () => {
      window.clearInterval(timer)
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", up)
      setDrag(null)
      if (!moved) { pick(c); return }
      const pos = insertPos(c, lastX - x0 + (el.scrollLeft - scroll0))
      const others = clips.filter((x) => x.index !== c.index)
      const before = clips.findIndex((x) => x.index === c.index)
      if (pos !== before) onReorder(c.index, others[pos] ? others[pos].index : scenes.length)
    }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }

  // Cảnh đang chọn: dời nhanh bằng nút (thay cho kéo xa trên timeline dài)
  const selPos = clips.findIndex((x) => x.index === selected)
  const selClip = selPos >= 0 ? clips[selPos] : undefined
  const moveSel = (pos: number) => {
    if (!selClip || !onReorder || pos === selPos) return
    const others = clips.filter((x) => x.index !== selClip.index)
    onReorder(selClip.index, others[pos] ? others[pos].index : scenes.length)
    const el = scroller.current
    const at = others.slice(0, pos).reduce((a, x) => a + x.dur, 0)
    if (el) requestAnimationFrame(() => { el.scrollLeft = Math.max(0, at * pps - el.clientWidth * 0.3) })
  }

  // Các làn clip không phụ thuộc đầu phát → chỉ dựng lại khi cảnh / zoom / chọn / kéo đổi, không phải mỗi khung hình
  const lanes = useMemo(() => (<>
            <Lane h={laneH("video")} onScrub={startScrub}>
              {!hidden.video && clips.map((c, k) => {
                const span = c.scene.clip_end - c.scene.clip_start
                const over = mode === "review" ? c.dur - span : 0           // Review: lời dài hơn đoạn hình → chiếu lấn sang hình phía sau
                const rate = mode === "reup" ? 1 / (c.pts ?? 1) : 1             // Reup: hình chỉ chậm lại khi lời quá dài (≤ 1.25×)
                return (
                  <ClipBox key={c.index} c={c} pps={pps} x={clipX(c)} selected={selected === c.index} onPick={() => pick(c)}
                    onBodyDown={(e) => startMove(e, c)} dragging={dragRole(c)}
                    className={cn(TRACKS.video.clip, (onReorder || onTrim) && "cursor-grab active:cursor-grabbing")}>
                    {over > 0.3 && (
                      <span title={`Lời dài hơn đoạn hình ${over.toFixed(1)}s — video sẽ chiếu sang phần hình phía sau (có thể lặp hình cảnh kế)`}
                        className="absolute inset-y-0 right-0 bg-[repeating-linear-gradient(135deg,rgba(251,191,36,.35)_0_4px,transparent_4px_8px)]"
                        style={{ width: Math.min(c.dur, over) * pps }} />
                    )}
                    {onTrim && <>
                      <span onPointerDown={(e) => startTrim(e, c, "clip_start")} title="Kéo để đổi điểm đầu đoạn hình gốc"
                        className="absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize after:absolute after:inset-y-2 after:left-0.5 after:w-[3px] after:rounded-full after:bg-white/0 hover:after:bg-white/80" />
                      <span onPointerDown={(e) => startTrim(e, c, "clip_end")} title="Kéo để đổi điểm cuối đoạn hình gốc"
                        className="absolute inset-y-0 right-0 z-10 w-2 cursor-ew-resize after:absolute after:inset-y-2 after:right-0.5 after:w-[3px] after:rounded-full after:bg-white/0 hover:after:bg-white/80" />
                    </>}
                    {drag?.index === c.index && (
                      <span className="tabular absolute top-0.5 right-1.5 z-20 rounded bg-black/75 px-1 font-mono text-[9.5px] whitespace-nowrap text-white">{drag.label}</span>
                    )}
                    {c.dur * pps >= 46 && <div className="relative flex h-full flex-col justify-between px-2 py-1">
                      <span className="flex items-center gap-1 truncate text-[11px] font-semibold">
                        Cảnh {k + 1}
                        {issues[c.index] && <AlertTriangle className={cn("size-3 shrink-0", issues[c.index] === "error" ? "text-red-300" : "text-amber-300")} />}
                        {rate < 0.99 && <span className="rounded bg-amber-400/25 px-1 font-mono text-[9px] text-amber-200" title="Lời quá dài so với khoảng trống tới câu sau — hình phải chậm lại. Nên rút gọn lời câu này.">×{rate.toFixed(2)}</span>}
                      </span>
                      <span className="tabular truncate font-mono text-[9.5px] text-white/55" title="Mốc trong video gốc · độ dài">▶ {fmtClock(c.scene.clip_start)} · {c.dur.toFixed(1)}s</span>
                    </div>}
                  </ClipBox>
                )
              })}
            </Lane>

            <Lane h={laneH("voice")} onScrub={startScrub}>
              {!hidden.voice && clips.map((c) => (
                <ClipBox key={c.index} c={c} pps={pps} x={clipX(c)} selected={selected === c.index} onPick={() => pick(c)}
                  onBodyDown={onReorder ? (e) => startMove(e, c) : undefined} dragging={dragRole(c)}
                  className={cn(TRACKS.voice.clip, muted.voice && "opacity-40", !c.scene.tts_path && "border-dashed bg-orange-950/70")}>
                  <div className="h-full w-full opacity-55 [background:repeating-linear-gradient(90deg,transparent_0_2px,rgba(255,237,213,.6)_2px_3px)] [mask:linear-gradient(transparent_22%,#000_38%,#000_62%,transparent_78%)]" />
                </ClipBox>
              ))}
            </Lane>

            <Lane h={laneH("subtitle")} onScrub={startScrub}>
              {!hidden.subtitle && clips.map((c) => {
                const s = scenes[c.index]
                return (
                  <ClipBox key={c.index} c={c} pps={pps} x={clipX(c)} selected={selected === c.index} onPick={() => pick(c)}
                    onBodyDown={onReorder ? (e) => startMove(e, c) : undefined} dragging={dragRole(c)}
                    className={TRACKS.subtitle.clip}>
                    {c.dur * pps >= 40 && <span className="block truncate px-2 pt-[9px] text-[10.5px] leading-none">{s?.subtitle || s?.voiceover}</span>}
                  </ClipBox>
                )
              })}
            </Lane>

            <Lane h={laneH("music")} onScrub={startScrub}>
              {!hidden.music && bgmName && total > 0 && (
                <div className={cn("absolute inset-y-1 left-0 overflow-hidden rounded-md border", TRACKS.music.clip, muted.music && "opacity-40")} style={{ width: total * pps }}>
                  <span className="block truncate px-2 pt-[6px] text-[10px] text-white/85">{bgmName}</span>
                </div>
              )}
            </Lane>
  </>), [clips, scenes, pps, selected, drag, issues, muted.voice, muted.music, bgmName, total, mode, videoDuration, readOnlyHint, !!onTrim, !!onReorder, hidden]) // eslint-disable-line react-hooks/exhaustive-deps

  // Thanh tổng quan: cả video thu nhỏ, khung trắng = phần đang nhìn; bấm / kéo để nhảy tới
  const overview = useRef<HTMLDivElement>(null)
  const startOverview = (e: ReactPointerEvent) => {
    const el = scroller.current, bar = overview.current
    if (!el || !bar || !width) return
    const go = (x: number) => {
      const r = bar.getBoundingClientRect()
      el.scrollLeft = ((x - r.left) / r.width) * width - el.clientWidth / 2
    }
    go(e.clientX)
    const move = (ev: PointerEvent) => go(ev.clientX)
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up) }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }
  const showOverview = !empty && width > view.w + 8
  const pct = (px: number) => `${(px / width) * 100}%`

  return (
    <div className="flex shrink-0 flex-col border-t border-white/10 bg-[#161618] text-white/90 select-none">
      {/* Thanh công cụ: công cụ | điều khiển phát ở GIỮA | zoom */}
      <div className="grid h-11 grid-cols-[1fr_auto_1fr] items-center border-b border-white/10 px-3">
        <div className="flex items-center gap-1">
          <IconBtn title={follow ? "Đang bám theo đầu phát — bấm để tắt" : "Bám theo đầu phát khi phát"} active={follow} onClick={() => setFollow(!follow)}><Crosshair /></IconBtn>
          {(onUndo || onRedo) && <>
            <span className="mx-1 h-4 w-px bg-white/10" />
            <IconBtn title="Hoàn tác (Ctrl+Z)" disabled={!canUndo} onClick={() => onUndo?.()}><Undo2 /></IconBtn>
            <IconBtn title="Làm lại (Ctrl+Y)" disabled={!canRedo} onClick={() => onRedo?.()}><Redo2 /></IconBtn>
          </>}
          {selClip && (onReorder || onToggleExcluded) && <>
            <span className="mx-1 h-4 w-px bg-white/10" />
            <span className="mr-0.5 text-[11px] whitespace-nowrap text-white/55">Cảnh {selPos + 1}</span>
            {onReorder && <>
              <IconBtn title="Đưa lên đầu" disabled={selPos <= 0} onClick={() => moveSel(0)}><ArrowLeftToLine /></IconBtn>
              <IconBtn title="Dời sang trái (Alt+←)" disabled={selPos <= 0} onClick={() => moveSel(selPos - 1)}><ChevronLeft /></IconBtn>
              <IconBtn title="Dời sang phải (Alt+→)" disabled={selPos >= clips.length - 1} onClick={() => moveSel(selPos + 1)}><ChevronRight /></IconBtn>
              <IconBtn title="Đưa xuống cuối" disabled={selPos >= clips.length - 1} onClick={() => moveSel(clips.length - 1)}><ArrowRightToLine /></IconBtn>
            </>}
            {onToggleExcluded && (
              <IconBtn title="Bỏ cảnh này khỏi video (Delete)" onClick={() => onToggleExcluded(selClip.index)}><EyeOff /></IconBtn>
            )}
          </>}
          <span className="mx-1 h-4 w-px bg-white/10" />
          <span className="text-[11px] whitespace-nowrap text-white/40">{clips.length} cảnh</span>
        </div>
        <div className={cn("flex items-center gap-3", empty && "pointer-events-none opacity-40")}>
          <span className="tabular w-[62px] text-right font-mono text-[12.5px] text-white">{fmtClock(empty ? 0 : time)}</span>
          <div className="flex items-center gap-1">
            <IconBtn title="Cảnh trước (←)" onClick={() => jump(-1)}><SkipBack /></IconBtn>
            <button title="Phát / dừng (Space)" onClick={onToggle}
              className="flex size-8 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md shadow-primary/30 transition hover:scale-105 [&_svg]:size-4">
              {playing ? <Pause /> : <Play className="translate-x-px" />}
            </button>
            <IconBtn title="Cảnh sau (→)" onClick={() => jump(1)}><SkipForward /></IconBtn>
          </div>
          <span className="tabular w-[62px] font-mono text-[12.5px] text-white/40">{fmtClock(total)}</span>
        </div>
        <div className="flex items-center justify-end gap-1.5">
          <ZoomControl pps={pps} setPps={setPps} min={MIN_PPS} max={MAX_PPS} base={Math.max(MIN_PPS, (view.w - 48) / Math.max(1, total))} onFit={fit} />
          <Tooltip>
            <TooltipTrigger asChild><span className="ml-1 cursor-help text-white/40 hover:text-white/80 [&_svg]:size-4"><CircleHelp /></span></TooltipTrigger>
            <TooltipContent side="top" className="text-xs">
              Space: phát/dừng · ← →: chuyển cảnh · Kéo thước: tua · Kéo cảnh: đổi thứ tự (Alt + ← →) · Kéo mép: cắt hình, tự hít nối liền cảnh kề ·
              Delete: bỏ/dùng lại cảnh · Ctrl+Z / Ctrl+Y: hoàn tác / làm lại · Lăn chuột: cuộn ngang · Ctrl + lăn chuột: zoom · Thanh tổng quan: bấm để nhảy nhanh
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      {showOverview && (
        <div className="flex h-4 items-center border-b border-white/10 bg-black/20" style={{ paddingLeft: HEADER_W }}>
          <div ref={overview} onPointerDown={startOverview} title="Bấm / kéo để nhảy tới đoạn đó"
            className="relative mx-1 h-2.5 flex-1 cursor-pointer overflow-hidden rounded-sm bg-white/[0.04]">
            {clips.map((c) => (
              <span key={c.index} className={cn("absolute inset-y-0 border-r border-black/40",
                selected === c.index ? "bg-white/70" : issues[c.index] === "error" ? "bg-red-400/60" : issues[c.index] ? "bg-amber-400/50" : "bg-sky-400/35")}
                style={{ left: pct(c.start * pps), width: pct(c.dur * pps) }} />
            ))}
            <span className="pointer-events-none absolute inset-y-0 w-px bg-red-500" style={{ left: pct(time * pps) }} />
            <span className="pointer-events-none absolute inset-y-0 rounded-sm border border-white/80 bg-white/10"
              style={{ left: pct(view.left), width: pct(Math.min(width, view.w)) }} />
          </div>
        </div>
      )}

      <div className="flex">
        {/* Cột track kiểu CapCut: icon + nút điều khiển, tên hiện khi rê chuột */}
        <div className="shrink-0 border-r border-white/10 bg-[#1b1b1e]" style={{ width: HEADER_W }}>
          <div className="border-b border-white/10" style={{ height: RULER_H }} />
          {(Object.keys(TRACKS) as (keyof typeof TRACKS)[]).map((k) => {
            const t = TRACKS[k]
            const muteKey = (k === "subtitle" ? undefined : k) as TrackKey | undefined
            const off = muteKey ? muted[muteKey] : false
            // cột icon thẳng hàng mọi làn: [mắt] [loa]
            const eye: LaneSlot = {
              title: hidden[k] ? `Hiện làn ${t.label}` : k === "subtitle" && onToggleSubtitle ? "Ẩn làn Phụ đề (và phụ đề trên màn xem trước)" : `Ẩn làn ${t.label}`,
              on: !!hidden[k], danger: true, icon: hidden[k] ? <EyeOff /> : <Eye />,
              onClick: () => {
                const willHide = !hidden[k]
                toggleLane(k)
                if (k === "subtitle" && onToggleSubtitle && subtitleVisible === willHide) onToggleSubtitle()
              },
            }
            const sound: LaneSlot = muteKey && showMute
              ? { title: off ? "Bật tiếng (khi nghe thử)" : "Tắt tiếng (khi nghe thử)", on: off, danger: true, icon: off ? <VolumeX /> : <Volume2 />,
                  onClick: () => onToggleMute(muteKey) }
              : null
            return (
              <LaneHeader key={k} label={t.label} accent={t.accent} height={laneH(k)} collapsed={!!hidden[k]}
                stat={k === "music" ? (bgmName || "none") : t.sub} onToggle={() => toggleLane(k)}
                toggleTitle={`${t.label} — bấm để ${hidden[k] ? "mở rộng" : "thu gọn"} làn`}
                slots={hidden[k] ? [eye, null] : [eye, sound]} />
            )
          })}
        </div>

        {/* Các làn */}
        <div ref={scroller} className="relative min-w-0 flex-1 overflow-x-auto overflow-y-hidden" onWheel={onWheel}>
          <div className="relative" style={{ width: width || "100%" }}>
            <div className="relative cursor-ew-resize border-b border-white/10 bg-white/[0.03]" style={{ height: RULER_H }} onPointerDown={startScrub}>
              {ticks.map((t) => (
                <div key={t} className="absolute inset-y-0 border-l border-white/15" style={{ left: t * pps }}>
                  <span className="tabular absolute top-[4px] left-1 font-mono text-[10px] text-white/50">{fmtRuler(t)}</span>
                </div>
              ))}
            </div>

            {lanes}

            {empty && (
              <div className="pointer-events-none absolute inset-x-0 bottom-0" style={{ top: RULER_H }}>
                {/* khung chờ: các khối mờ nhấp nháy trên từng làn */}
                {(Object.keys(TRACKS) as (keyof typeof TRACKS)[]).map((k, row) => (
                  <div key={k} className="relative flex items-center gap-1 border-b border-transparent px-1" style={{ height: laneH(k) }}>
                    {[22, 14, 30, 18, 26].map((w, i) => (
                      <span key={i} className="h-[calc(100%-8px)] animate-pulse rounded-md bg-white/[0.045]"
                        style={{ width: `${w - row * 2}%`, animationDelay: `${(i + row) * 120}ms` }} />
                    ))}
                  </div>
                ))}
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="rounded-full border border-white/10 bg-[#161618]/90 px-3 py-1 text-[11px] text-white/55">{emptyHint}</span>
                </div>
              </div>
            )}

            {/* Vạch vị trí thả khi kéo đổi thứ tự */}
            {drag?.kind === "move" && preview.has(-1) && (
              <div className="pointer-events-none absolute bottom-0 z-40 w-0.5 -translate-x-1/2 rounded-full bg-amber-300 shadow-[0_0_8px_rgba(252,211,77,.8)]"
                style={{ left: preview.get(-1)! * pps, top: RULER_H }} />
            )}

            {/* Đầu phát */}
            {!empty && (
              <div className="pointer-events-none absolute top-0 bottom-0 z-20" style={{ left: time * pps }}>
                <div className="absolute top-0 -left-[5px] h-3 w-[11px] rounded-b-sm bg-red-500" />
                <div className="absolute top-0 bottom-0 w-px bg-red-500" />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function IconBtn({ title, onClick, children, active, danger, disabled }: { title: string; onClick: () => void; children: ReactNode; active?: boolean; danger?: boolean; disabled?: boolean }) {
  return (
    <button title={title} onClick={onClick} disabled={disabled} aria-pressed={active}
      className={cn("flex size-7 shrink-0 items-center justify-center rounded-md disabled:pointer-events-none disabled:opacity-30 [&_svg]:size-3.5",
        active ? (danger ? "bg-red-500/20 text-red-300 hover:bg-red-500/30" : "bg-white/15 text-white") : "text-white/60 hover:bg-white/10 hover:text-white")}>
      {children}
    </button>
  )
}

function Lane({ h, children, onScrub }: { h: number; children: ReactNode; onScrub: (e: ReactPointerEvent) => void }) {
  return (
    <div className="relative border-b border-white/10" style={{ height: h }} onPointerDown={(e) => { if (e.target === e.currentTarget) onScrub(e) }}>
      {children}
    </div>
  )
}

function ClipBox({ c, pps, x, selected, onPick, onBodyDown, dragging, className, children }: {
  c: Clip; pps: number; x: number; selected: boolean; onPick: () => void; onBodyDown?: (e: ReactPointerEvent) => void
  /** self: cảnh đang được kéo (theo chuột) · other: cảnh khác đang dạt chỗ (trượt mượt) */
  dragging?: "self" | "other"; className: string; children: ReactNode
}) {
  return (
    <div onPointerDown={(e) => { if (onBodyDown) onBodyDown(e); else { e.stopPropagation(); onPick() } }}
      className={cn("absolute inset-y-1 cursor-pointer overflow-hidden rounded-md border hover:brightness-110",
        className, selected && "z-10 border-white ring-1 ring-white",
        dragging === "self" && "z-30 opacity-90 shadow-lg ring-2 shadow-black/60 ring-amber-300",
        dragging === "other" && "transition-[left] duration-150 ease-out")}
      style={{ left: x + 1, width: Math.max(3, c.dur * pps - 2) }}
      title={`${fmtClock(c.start)} · ${c.dur.toFixed(1)}s`}>
      {children}
    </div>
  )
}
