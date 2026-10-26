import {
  ArrowLeftToLine, ArrowRightToLine, AudioWaveform, Captions, CircleHelp, Combine, Crosshair, Link2, Link2Off, Magnet, Maximize2, Mic, Pause, Play,
  Redo2, RotateCcw, Scissors, SkipBack, SkipForward, Undo2, Wand2, ZoomIn, ZoomOut,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as RPE, type ReactNode } from "react"
import { toast } from "sonner"
import { Slider } from "@/components/ui/slider"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { confirmAction } from "@/components/ConfirmHost"
import { api } from "@/lib/api"
import { fmtClock } from "@/lib/format"
import { cutWord, isRetimed, origOf, partsWithText, readSpeed, resetTiming, sceneCues, voiceSlot } from "@/lib/subcues"
import type { Scene, ScenePart } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Sóng âm video gốc: đỉnh 0-255 mỗi 1/rate giây. */
export type Peaks = { rate: number; data: Uint8Array }

/** Tải sóng âm + điểm chuyển cảnh của video gốc (backend tính 1 lần rồi cache). Sóng âm có trong ~2s, điểm cảnh lần đầu lâu hơn. */
export function useTimelineMedia(jobId: string, enabled: boolean) {
  const [peaks, setPeaks] = useState<Peaks | null>(null)
  const [shots, setShots] = useState<number[]>([])
  useEffect(() => {
    if (!enabled) return
    let off = false
    api.waveform(jobId).then((w) => {
      if (off || !w.n) return
      const bin = atob(w.peaks)
      const data = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) data[i] = bin.charCodeAt(i)
      setPeaks({ rate: w.rate, data })
    }).catch(() => {})
    api.shots(jobId).then((s) => { if (!off) setShots(s.cuts || []) }).catch(() => {})
    return () => { off = true }
  }, [jobId, enabled])
  return { peaks, shots }
}

/*
 * Timeline chỉnh tay cho Dịch phụ đề (kiểu Aegisub / Subtitle Edit / CapCut):
 *  · làn Gốc: dòng phụ đề gốc (chỉ xem, để so & hít vào)
 *  · làn Lồng tiếng: khung đọc của từng câu — kéo để giọng bắt đầu sớm / muộn, kéo mép để nới / thu khung đọc
 *  · làn Phụ đề: từng dòng chữ Việt — kéo để dời, kéo mép để đổi lúc hiện / tắt
 * Hít (nam châm) vào đầu phát, mép các khối khác, mép dòng gốc. Liên kết: dời phụ đề thì giọng của câu đi theo (và ngược lại).
 * Mọi thay đổi chỉ ghi lúc thả chuột → 1 lần Hoàn tác cho 1 lượt kéo, timeline không vẽ lại mỗi pixel ở trang cha.
 */

const HEADER_W = 84
const RULER_H = 22
const MIN_PPS = 4
const MAX_PPS = 400
const MIN_DUR = 0.3
const SNAP_PX = 8
const DUB_CPS = 17      // giọng Việt ~17 ký tự / giây (khớp bước Sửa bản dịch)
const HELP: [string, string][] = [
  ["Kéo khối", "dời phụ đề / giọng"],
  ["Kéo mép", "đổi lúc bắt đầu / kết thúc"],
  ["Ctrl+B · M", "tách · gộp dòng"],
  ["← →", "dời 0.1s (Shift: 1s)"],
  ["[ ]", "đầu / cuối = đầu phát"],
  ["S · L", "hít · liên kết phụ đề & giọng"],
  ["R", "về giờ gốc"],
  ["↑ ↓ · Space", "dòng trước / sau · phát"],
  ["Ctrl+Z / Y", "hoàn tác / làm lại"],
  ["Ctrl + lăn", "zoom"],
]
const TICK_STEPS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]
const LANES = {
  orig: { label: "Gốc", sub: "sóng âm + phụ đề gốc", icon: AudioWaveform, h: 48, accent: "bg-sky-400", text: "text-sky-300" },
  voice: { label: "Giọng", sub: "khung đọc lồng tiếng từng câu", icon: Mic, h: 40, accent: "bg-orange-400", text: "text-orange-300" },
  sub: { label: "Phụ đề", sub: "dòng chữ hiện trên video", icon: Captions, h: 40, accent: "bg-violet-400", text: "text-violet-300" },
} as const

type LaneKey = "voice" | "sub"
type Item = { key: string; lane: LaneKey; scene: number; part: number; start: number; end: number; text: string; manual?: boolean }
type Span = { start: number; end: number }
type DragState = { keys: Set<string>; spans: Map<string, Span>; label: string; snapAt?: number }
type Snap = Pick<Scene, "clip_start" | "clip_end" | "parts" | "voice_start" | "voice_end">

const r2 = (x: number) => Math.round(x * 100) / 100
const snapOf = (s: Scene): Snap => ({ clip_start: s.clip_start, clip_end: s.clip_end, parts: s.parts, voice_start: s.voice_start, voice_end: s.voice_end })

type Props = {
  scenes: Scene[]
  onChange: (next: Scene[]) => void
  /** có lồng tiếng → hiện làn Lồng tiếng */
  dub: boolean
  time: number
  playing: boolean
  selected: number | null
  /** độ dài video gốc (giới hạn khi kéo) */
  duration?: number
  onSeek: (t: number) => void
  onSelect: (sceneIndex: number) => void
  onToggle: () => void
  /** sóng âm video gốc (useTimelineMedia) */
  peaks?: Peaks | null
  /** điểm chuyển cảnh (giây) — vạch trên timeline + hít vào */
  shots?: number[]
}

export function SubtitleTimeline({ scenes, onChange, dub, time, playing, selected, duration, onSeek, onSelect, onToggle, peaks, shots = [] }: Props) {
  const latest = useRef({ scenes, onChange, onSeek, onSelect, time })
  latest.current = { scenes, onChange, onSeek, onSelect, time }

  // ── Khối trên các làn ──
  const { lanes, items, origs, total } = useMemo(() => {
    const sub: Item[] = []
    const voice: Item[] = []
    const origs: { scene: number; start: number; end: number; text: string }[] = []
    scenes.forEach((s, i) => {
      if (s.excluded) return
      const o = origOf(s)
      for (const p of o.parts ?? [[o.cs, o.ce, s.orig_text || ""] as ScenePart]) origs.push({ scene: i, start: Number(p[0]), end: Number(p[1]), text: String(p[2] ?? "") })
      for (const c of sceneCues(s, i)) sub.push({ key: `s${i}.${c.part}`, lane: "sub", scene: i, part: c.part, start: c.start, end: c.end, text: c.text })
      const text = (s.voiceover || "").trim()
      if (dub && s.speaker_id !== -1 && text) {
        const v = voiceSlot(s)
        voice.push({ key: `v${i}`, lane: "voice", scene: i, part: -1, start: v.start, end: v.end, text, manual: v.manual })
      }
    })
    sub.sort((a, b) => a.start - b.start)
    voice.sort((a, b) => a.start - b.start)
    const all = [...sub, ...voice]
    const end = Math.max(0, ...all.map((x) => x.end), ...origs.map((x) => x.end))
    return { lanes: { sub, voice } as Record<LaneKey, Item[]>, items: all, origs, total: Math.max(duration ?? 0, end) }
  }, [scenes, dub, duration])
  const limit = duration && duration > 0 ? duration : Infinity

  // ── Chọn ──
  const byKey = useMemo(() => new Map(items.map((x) => [x.key, x])), [items])
  const [selKey, setSelKey] = useState<string | null>(null)
  const selItem = selKey ? byKey.get(selKey) : undefined
  useEffect(() => { if (selItem && selItem.scene !== selected) setSelKey(null) }, [selected]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Tuỳ chọn ──
  const [snapOn, setSnapOn] = useState(true)
  const [link, setLink] = useState(true)
  const [follow, setFollow] = useState(true)

  // ── Hoàn tác: kéo / cắt mép chỉ lưu GIỜ mọi câu (không xoá mất lời vừa gõ ở bảng bên); tách / gộp lưu cả bản ──
  type Hist = { full: false; s: Snap[] } | { full: true; s: Scene[] }
  const past = useRef<Hist[]>([])
  const future = useRef<Hist[]>([])
  const [, bump] = useState(0)
  const expectLen = useRef(scenes.length)
  useEffect(() => {
    // số câu đổi từ bên ngoài (xoá câu ở bảng bên) → lịch sử cũ không còn khớp
    if (scenes.length !== expectLen.current) { past.current = []; future.current = []; bump((n) => n + 1) }
    expectLen.current = scenes.length
  }, [scenes.length])
  const take = (cur: Scene[], full: boolean): Hist => (full ? { full: true, s: cur } : { full: false, s: cur.map(snapOf) })
  const restore = (cur: Scene[], snap: Snap[]) => cur.map((s, i) => {
    const t = snap[i]
    if (!t || JSON.stringify(snapOf(s)) === JSON.stringify(t)) return s
    const n: Scene = { ...s, clip_start: t.clip_start, clip_end: t.clip_end, parts: t.parts }
    if (typeof t.voice_start === "number") { n.voice_start = t.voice_start; n.voice_end = t.voice_end } else { delete n.voice_start; delete n.voice_end }
    return n
  })
  const commit = useCallback((next: Scene[], full = false) => {
    past.current.push(take(latest.current.scenes, full))
    if (past.current.length > 100) past.current.shift()
    future.current = []
    bump((n) => n + 1)
    expectLen.current = next.length
    latest.current.onChange(next)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const walk = (from: { current: Hist[] }, to: { current: Hist[] }) => {
    const cur = latest.current.scenes
    const h = from.current.pop()
    if (!h) return
    to.current.push(take(cur, h.full))
    const next = h.full ? h.s : restore(cur, h.s)
    bump((n) => n + 1)
    expectLen.current = next.length
    latest.current.onChange(next)
  }
  const undo = () => walk(past, future)
  const redo = () => walk(future, past)

  /** Ghi giờ mới của các khối vào câu. Dời phụ đề câu chưa có thông tin dòng (không link) → giữ giọng đứng yên. */
  const apply = useCallback((spans: Map<string, Span>) => {
    const cur = latest.current.scenes
    const touched = new Map<number, Scene>()
    const get = (i: number) => { if (!touched.has(i)) touched.set(i, { ...cur[i] }); return touched.get(i)! }
    const voiceMoved = new Set([...spans.keys()].filter((k) => k.startsWith("v")).map((k) => byKey.get(k)!.scene))
    for (const [key, sp] of spans) {
      const it = byKey.get(key)
      if (!it) continue
      const s = get(it.scene)
      const [a, b] = [r2(sp.start), r2(sp.end)]
      if (it.lane === "voice") { s.voice_start = a; s.voice_end = b }
      else if (it.part >= 0 && s.parts) s.parts = s.parts.map((p, k) => (k === it.part ? [a, b, ...p.slice(2)] as ScenePart : p))
      else {
        if (dub && typeof s.voice_start !== "number" && !voiceMoved.has(it.scene)) { s.voice_start = s.clip_start; s.voice_end = s.clip_end }
        s.clip_start = a
        s.clip_end = b
      }
    }
    return cur.map((s, i) => touched.get(i) ?? s)
  }, [byKey, dub])

  // ── Tính dời / cắt có giới hạn (không đè khối kề cùng làn, không ra ngoài video) ──
  const neighbors = (m: Item, keys: Set<string>) => {
    const L = lanes[m.lane]
    const j = L.indexOf(m)
    let prev: Item | undefined, next: Item | undefined
    for (let k = j - 1; k >= 0; k--) if (!keys.has(L[k].key)) { prev = L[k]; break }
    for (let k = j + 1; k < L.length; k++) if (!keys.has(L[k].key)) { next = L[k]; break }
    return { prev, next }
  }
  const groupOf = (it: Item, withLink: boolean) => (withLink ? items.filter((x) => x.scene === it.scene) : [it])
  const snapPoints = (keys: Set<string>) => {
    const pts = [latest.current.time]
    for (const x of items) if (!keys.has(x.key)) pts.push(x.start, x.end)
    for (const o of origs) pts.push(o.start, o.end)
    pts.push(...shots)                    // chuyển cảnh: phụ đề không vắt qua 2 cảnh
    return pts
  }
  const nearest = (vals: number[], pts: number[], tol: number) => {
    let best: { d: number; at: number } | undefined
    for (const v of vals) for (const p of pts) { const d = p - v; if (Math.abs(d) <= tol && (!best || Math.abs(d) < Math.abs(best.d))) best = { d, at: p } }
    return best
  }
  const planMove = (members: Item[], dt: number, pts: number[] | null, tol: number) => {
    const keys = new Set(members.map((m) => m.key))
    let lo = -Infinity, hi = Infinity
    for (const m of members) {
      const { prev, next } = neighbors(m, keys)
      lo = Math.max(lo, prev ? prev.end - m.start : -m.start)
      hi = Math.min(hi, next ? next.start - m.end : limit - m.end)
    }
    lo = Math.min(lo, 0); hi = Math.max(hi, 0)
    let snapAt: number | undefined
    if (pts) {
      const b = nearest(members.flatMap((m) => [m.start + dt, m.end + dt]), pts, tol)
      if (b) { dt += b.d; snapAt = b.at }
    }
    const c = Math.max(lo, Math.min(hi, dt))
    if (c !== dt) snapAt = undefined
    return { dt: c, snapAt, spans: new Map(members.map((m) => [m.key, { start: m.start + c, end: m.end + c }])) }
  }
  const planTrim = (m: Item, edge: "l" | "r", v: number, pts: number[] | null, tol: number) => {
    const { prev, next } = neighbors(m, new Set([m.key]))
    let snapAt: number | undefined
    if (pts) { const b = nearest([v], pts, tol); if (b) { v = b.at; snapAt = b.at } }
    const c = edge === "l"
      ? Math.max(prev ? Math.min(prev.end, m.start) : 0, Math.min(v, m.end - MIN_DUR))
      : Math.min(next ? Math.max(next.start, m.end) : limit, Math.max(v, m.start + MIN_DUR))
    if (c !== v) snapAt = undefined
    return { v: c, snapAt, spans: new Map([[m.key, edge === "l" ? { start: c, end: m.end } : { start: m.start, end: c }]]) }
  }

  // ── Zoom / cuộn ──
  const scroller = useRef<HTMLDivElement>(null)
  const [pps, setPps] = useState(24)
  const [fitted, setFitted] = useState(false)
  const width = total > 0 ? total * pps + 48 : 0
  const fit = useCallback(() => {
    const w = (scroller.current?.clientWidth ?? 800) - 48
    if (total > 0) setPps(Math.min(MAX_PPS, Math.max(MIN_PPS, w / total)))
  }, [total])
  useEffect(() => { if (!fitted && total > 0) { fit(); setFitted(true) } }, [fit, fitted, total])
  useEffect(() => {
    const el = scroller.current
    if (!el || !playing || !follow) return
    const x = time * pps
    if (x < el.scrollLeft + 40 || x > el.scrollLeft + el.clientWidth - 60) el.scrollLeft = x - el.clientWidth * 0.25
  }, [time, pps, playing, follow])
  // chọn câu ở bảng bên → cuộn timeline tới câu đó
  useEffect(() => {
    const el = scroller.current
    const it = selected === null ? undefined : items.find((x) => x.scene === selected)
    if (!el || !it || playing) return
    const x = it.start * pps
    if (x < el.scrollLeft || x > el.scrollLeft + el.clientWidth - 80) el.scrollTo({ left: x - el.clientWidth * 0.3, behavior: "smooth" })
  }, [selected]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const block = (e: WheelEvent) => { if (e.ctrlKey) e.preventDefault() }
    el.addEventListener("wheel", block, { passive: false })
    return () => el.removeEventListener("wheel", block)
  }, [])
  const onWheel = (e: React.WheelEvent) => {
    const el = scroller.current
    if (!el) return
    if (!e.ctrlKey) { if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) el.scrollLeft += e.deltaY; return }
    // zoom quanh vị trí chuột (giữ nguyên giây dưới con trỏ)
    const x = e.clientX - el.getBoundingClientRect().left
    const t = (x + el.scrollLeft) / pps
    const np = Math.min(MAX_PPS, Math.max(MIN_PPS, pps * (e.deltaY < 0 ? 1.2 : 1 / 1.2)))
    setPps(np)
    requestAnimationFrame(() => { el.scrollLeft = t * np - x })
  }
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

  const timeAt = (clientX: number) => {
    const el = scroller.current!
    return Math.max(0, Math.min(total, (clientX - el.getBoundingClientRect().left + el.scrollLeft) / pps))
  }
  const startScrub = (e: RPE) => {
    if (!items.length) return
    setSelKey(null)
    latest.current.onSeek(timeAt(e.clientX))
    const move = (ev: PointerEvent) => latest.current.onSeek(timeAt(ev.clientX))
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up) }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }

  // ── Kéo khối ──
  // Khối đang kéo: các khối gốc chỉ mờ đi (dragKeys đặt 1 lần / lượt kéo), bản kéo vẽ ở lớp riêng (ghost) → rê chuột
  // chỉ vẽ lại 1–vài khối, không vẽ lại cả làn. Mọi tính toán gom theo khung hình (requestAnimationFrame).
  const [dragKeys, setDragKeys] = useState<Set<string> | null>(null)
  const [ghost, setGhost] = useState<DragState | null>(null)
  const startDrag = (e: RPE, it: Item, mode: "move" | "l" | "r") => {
    e.stopPropagation()
    if (e.button !== 0) return
    e.preventDefault()
    const el = scroller.current!
    const x0 = e.clientX
    const scroll0 = el.scrollLeft
    // Alt khi bắt đầu kéo = tạm đảo Liên kết; Shift = tạm tắt hít
    const members = mode === "move" ? groupOf(it, link !== e.altKey) : [it]
    const keys = new Set(members.map((m) => m.key))
    const pts = snapOn ? snapPoints(keys) : null
    let moved = false
    let last: DragState | null = null
    let lastX = x0
    let shift = e.shiftKey
    let raf = 0
    let edgeRaf = 0
    const compute = () => {
      raf = 0
      const dt = (lastX - x0 + el.scrollLeft - scroll0) / pps
      const p = shift ? null : pts
      if (mode === "move") {
        const m = planMove(members, dt, p, SNAP_PX / pps)
        const sp = m.spans.get(it.key)!
        last = { keys, spans: m.spans, snapAt: m.snapAt,
          label: `${fmtClock(sp.start)} → ${fmtClock(sp.end)} · ${m.dt >= 0 ? "+" : ""}${m.dt.toFixed(2)}s${members.length > 1 ? ` · ${members.length} khối` : ""}` }
      } else {
        const t = planTrim(it, mode, (mode === "l" ? it.start : it.end) + dt, p, SNAP_PX / pps)
        const sp = t.spans.get(it.key)!
        last = { keys, spans: t.spans, snapAt: t.snapAt, label: `${mode === "l" ? "Đầu" : "Cuối"} ${fmtClock(t.v)} · ${(sp.end - sp.start).toFixed(2)}s` }
        latest.current.onSeek(mode === "l" ? t.v : Math.max(0, t.v - 0.05))   // xem khung hình ngay mép đang kéo
      }
      setGhost(last)
    }
    const schedule = () => { if (!raf) raf = requestAnimationFrame(compute) }
    // giữ chuột sát mép khung → cuộn liên tục (càng sát càng nhanh) như Premiere / CapCut
    const edgeLoop = () => {
      const r = el.getBoundingClientRect()
      const v = lastX < r.left + 40 ? -Math.ceil((r.left + 40 - lastX) / 3) : lastX > r.right - 40 ? Math.ceil((lastX - r.right + 40) / 3) : 0
      if (v && moved) { const before = el.scrollLeft; el.scrollLeft += v; if (el.scrollLeft !== before) schedule() }
      edgeRaf = requestAnimationFrame(edgeLoop)
    }
    const move = (ev: PointerEvent) => {
      lastX = ev.clientX
      shift = ev.shiftKey
      if (!moved && Math.abs(lastX - x0) < 3) return
      if (!moved) { moved = true; setDragKeys(keys); edgeRaf = requestAnimationFrame(edgeLoop) }
      schedule()
    }
    const end = (ok: boolean) => {
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", up)
      window.removeEventListener("pointercancel", cancel)
      window.removeEventListener("blur", cancel)
      window.removeEventListener("keydown", esc, true)
      cancelAnimationFrame(edgeRaf)
      if (raf) { cancelAnimationFrame(raf); if (ok) compute() }
      setDragKeys(null)
      setGhost(null)
      setSelKey(it.key)
      latest.current.onSelect(it.scene)
      if (!ok) return
      if (!moved) { latest.current.onSeek(it.start); return }
      const l = last as DragState | null
      if (l && [...l.spans].some(([k, s]) => { const o = byKey.get(k)!; return Math.abs(o.start - s.start) > 0.004 || Math.abs(o.end - s.end) > 0.004 })) {
        commit(apply(l.spans))
        if (mode === "move") latest.current.onSeek(l.spans.get(it.key)!.start)
      }
    }
    const up = () => end(true)
    const cancel = () => end(false)                   // mất chuột / chuyển cửa sổ giữa chừng → huỷ, không ghi nửa vời
    const esc = (ev: KeyboardEvent) => { if (ev.key === "Escape") { ev.stopPropagation(); end(false) } }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
    window.addEventListener("pointercancel", cancel)
    window.addEventListener("blur", cancel)
    window.addEventListener("keydown", esc, true)
  }

  // ── Thao tác trên khối đang chọn (nút + phím tắt) ──
  const nudge = (dt: number) => {
    if (!selItem) return
    const m = planMove(groupOf(selItem, link), dt, null, 0)
    if (m.dt !== 0) commit(apply(m.spans))
  }
  const edgeToPlayhead = (edge: "l" | "r") => {
    if (!selItem) return
    const t = planTrim(selItem, edge, latest.current.time, null, 0)
    commit(apply(t.spans))
  }
  const resetScene = (i: number) => {
    const cur = latest.current.scenes
    if (!cur[i] || !isRetimed(cur[i])) return
    commit(cur.map((s, j) => (j === i ? resetTiming(s) : s)))
  }
  const retimedSet = useMemo(() => new Set(scenes.flatMap((s, i) => (!s.excluded && isRetimed(s) ? [i] : []))), [scenes])
  const retimed = retimedSet.size
  const resetAll = async () => {
    if (!(await confirmAction({ title: `Khôi phục giờ gốc ${retimed} câu?`, action: "Khôi phục", cancel: "Thôi",
      desc: "Giờ phụ đề & giọng về như ban đầu. Lời đã sửa giữ nguyên. Ctrl+Z để hoàn tác." }))) return
    commit(latest.current.scenes.map((s) => (isRetimed(s) ? resetTiming(s) : s)))
  }
  // ── Tách / gộp dòng phụ đề ──
  // Có lồng tiếng: câu (1 lần đọc) giữ nguyên, chỉ chia / nối các DÒNG chữ trong câu (parts). Không lồng tiếng: mỗi dòng là 1 câu.
  const subAt = (t: number) => lanes.sub.find((x) => t > x.start && t < x.end)
  const splitLine = () => {
    const t = latest.current.time
    const it = selItem?.lane === "sub" && t > selItem.start && t < selItem.end ? selItem : subAt(t)
    if (!it) return void toast.info("Đặt đầu phát vào giữa dòng cần tách", { id: "tl-edit" })
    if (t - it.start < MIN_DUR || it.end - t < MIN_DUR) return void toast.info("Điểm tách cần cách mép dòng ≥ 0.3s", { id: "tl-edit" })
    const words = it.text.split(/\s+/).filter(Boolean)
    if (words.length < 2) return void toast.info("Dòng chỉ có 1 từ, không tách được", { id: "tl-edit" })
    const k = cutWord(words, (t - it.start) / (it.end - it.start))
    const [A, B] = [words.slice(0, k).join(" "), words.slice(k).join(" ")]
    const cur = latest.current.scenes
    const s = cur[it.scene]
    const tt = r2(t)
    if (dub) {
      const parts = partsWithText(s)
      const j = Math.max(0, it.part)
      const p = parts[j]
      const orig = Array.from(String(p[2] ?? ""))
      const oc = Math.round((orig.length * (tt - p[0])) / Math.max(0.01, p[1] - p[0]))
      parts.splice(j, 1, [p[0], tt, orig.slice(0, oc).join(""), A], [tt, p[1], orig.slice(oc).join(""), B])
      commit(cur.map((x, i) => (i === it.scene ? { ...x, parts } : x)), true)
      setSelKey(`s${it.scene}.${j + 1}`)
    } else {
      const base = { ...s, parts: null }
      const a: Scene = { ...base, clip_start: it.start, clip_end: tt, voiceover: A, subtitle: A, _o: { cs: it.start, ce: tt, parts: null } }
      const b: Scene = { ...base, clip_start: tt, clip_end: it.end, voiceover: B, subtitle: B, orig_text: "", _o: { cs: tt, ce: it.end, parts: null } }
      commit([...cur.slice(0, it.scene), a, b, ...cur.slice(it.scene + 1)], true)
      setSelKey(`s${it.scene + 1}.-1`)
    }
  }
  const mergeLine = () => {
    const t = latest.current.time
    const it = selItem?.lane === "sub" ? selItem : lanes.sub.find((x) => t >= x.start && t < x.end)
    if (!it) return void toast.info("Chọn dòng cần gộp với dòng sau", { id: "tl-edit" })
    const nx = lanes.sub[lanes.sub.indexOf(it) + 1]
    if (!nx) return void toast.info("Đây là dòng cuối", { id: "tl-edit" })
    const join = (a: string, b: string) => [a, b].map((x) => x.trim()).filter(Boolean).join(" ")
    const cur = latest.current.scenes
    if (nx.scene === it.scene) {
      const parts = partsWithText(cur[it.scene])
      const [a, b] = [parts[it.part], parts[nx.part]]
      const mid = parts.slice(it.part, nx.part + 1)
      parts.splice(it.part, nx.part - it.part + 1, [a[0], b[1], mid.map((p) => p[2]).join(""), join(mid.map((p) => p[3] ?? "").join(" "), "")])
      commit(cur.map((x, i) => (i === it.scene ? { ...x, parts } : x)), true)
      setSelKey(`s${it.scene}.${it.part}`)
      return
    }
    if (nx.scene !== it.scene + 1) return void toast.info("Chỉ gộp được 2 dòng liền nhau", { id: "tl-edit" })
    const [A, B] = [cur[it.scene], cur[nx.scene]]
    const text = join(A.voiceover || A.subtitle || "", B.voiceover || B.subtitle || "")
    const [oA, oB] = [origOf(A), origOf(B)]
    const m: Scene = { ...A, clip_start: Math.min(A.clip_start, B.clip_start), clip_end: Math.max(A.clip_end, B.clip_end), voiceover: text, subtitle: text,
      orig_text: join(A.orig_text || "", B.orig_text || "") }
    for (const k of ["tts_path", "tts_duration", "tts_text"]) delete m[k]       // lời đổi → giọng cũ hết đúng
    if (dub) {
      // gộp 2 câu đọc thành 1; dòng cuối câu trước + dòng đầu câu sau thành 1 dòng chữ
      const pa = partsWithText(A), pb = partsWithText(B)
      const [la, fb] = [pa[pa.length - 1], pb[0]]
      m.parts = [...pa.slice(0, -1), [la[0], fb[1], `${la[2]}${fb[2]}`, join(la[3] ?? "", fb[3] ?? "")] as ScenePart, ...pb.slice(1)]
      m._o = { cs: Math.min(oA.cs, oB.cs), ce: Math.max(oA.ce, oB.ce),
        parts: [...(oA.parts ?? [[oA.cs, oA.ce, A.orig_text || ""] as ScenePart]), ...(oB.parts ?? [[oB.cs, oB.ce, B.orig_text || ""] as ScenePart])] }
      const [va, vb] = [voiceSlot(A), voiceSlot(B)]
      if (va.manual || vb.manual) { m.voice_start = Math.min(va.start, vb.start); m.voice_end = Math.max(va.end, vb.end) }
      else { delete m.voice_start; delete m.voice_end }
    } else {
      m.parts = null
      m._o = { cs: Math.min(oA.cs, oB.cs), ce: Math.max(oA.ce, oB.ce), parts: null }
    }
    commit([...cur.slice(0, it.scene), m, ...cur.slice(nx.scene + 1)], true)
    setSelKey(null)
  }

  // ── Tốc độ đọc phụ đề ──
  const speeds = useMemo(() => new Map(lanes.sub.map((x) => [x.key, readSpeed(x.text, x.end - x.start)])), [lanes.sub])
  const hurried = useMemo(() => lanes.sub.filter((x) => speeds.get(x.key)!.level !== "ok"), [lanes.sub, speeds])
  /** Tự nới các dòng đọc gấp: kéo dài mép cuối vào khoảng trống phía sau, thiếu nữa thì lùi mép đầu — không đè dòng kề, không vượt chuyển cảnh gần. */
  const fixSpeed = () => {
    const L = lanes.sub
    const cur = L.map((x) => ({ start: x.start, end: x.end }))
    const spans = new Map<string, Span>()
    const GAP = 0.04
    let left = 0
    L.forEach((x, i) => {
      const sp = speeds.get(x.key)!
      if (sp.level === "ok") return
      let { start, end } = cur[i]
      let d = sp.need - (end - start)
      if (d <= 0.01) return
      const cutAfter = shots.find((c) => c > end + 0.01)
      const maxEnd = Math.min(i + 1 < L.length ? Math.max(end, cur[i + 1].start - GAP) : limit, cutAfter !== undefined && cutAfter - end < d + 0.5 ? Math.max(end, cutAfter) : Infinity)
      const e2 = Math.min(maxEnd, end + d)
      d -= e2 - end
      end = e2
      if (d > 0.01) start = Math.max(i > 0 ? Math.min(start, cur[i - 1].end + GAP) : 0, start - d)
      if (readSpeed(x.text, end - start).level !== "ok") left++
      if (start !== cur[i].start || end !== cur[i].end) { cur[i] = { start, end }; spans.set(x.key, { start: r2(start), end: r2(end) }) }
    })
    if (!spans.size) return void toast.info("Không còn khoảng trống để nới", { id: "tl-edit", description: "Rút gọn lời các dòng còn vàng / đỏ." })
    commit(apply(spans))
    toast.success(`Đã nới ${spans.size} dòng`, { id: "tl-edit", description: left ? `Còn ${left} dòng gấp — nên rút gọn lời.` : "Mọi dòng đã đọc kịp." })
  }

  const jump = (dir: -1 | 1) => {
    const L = lanes.sub.length ? lanes.sub : lanes.voice
    const t = latest.current.time
    const it = dir > 0 ? L.find((x) => x.start > t + 0.01) : [...L].reverse().find((x) => x.start < t - 0.05)
    if (it) { latest.current.onSeek(it.start); latest.current.onSelect(it.scene); setSelKey(it.key) }
  }

  // phím tắt — chỉ khi chuột / thao tác đang ở timeline, không khi đang gõ chữ
  const root = useRef<HTMLDivElement>(null)
  const hot = useRef(false)
  const keyRef = useRef<(e: KeyboardEvent) => void>(() => {})
  keyRef.current = (e: KeyboardEvent) => {
    const tag = (e.target as HTMLElement)?.tagName
    if (!hot.current || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (e.target as HTMLElement)?.isContentEditable) return
    const k = e.key.toLowerCase()
    const ctrl = e.ctrlKey || e.metaKey
    if (ctrl && k === "z" && !e.shiftKey) { e.preventDefault(); undo() }
    else if (ctrl && (k === "y" || (k === "z" && e.shiftKey))) { e.preventDefault(); redo() }
    else if (ctrl && k === "b") { e.preventDefault(); splitLine() }
    else if (ctrl || e.altKey) return
    else if (k === "m") { e.preventDefault(); mergeLine() }
    else if (k === " ") { e.preventDefault(); onToggle() }
    else if (k === "arrowleft" || k === "arrowright") { e.preventDefault(); const d = k === "arrowleft" ? -1 : 1; if (selItem) nudge(d * (e.shiftKey ? 1 : 0.1)); else jump(d as -1 | 1) }
    else if (k === "arrowup" || k === "arrowdown") { e.preventDefault(); jump(k === "arrowup" ? -1 : 1) }
    else if (e.key === "[") { e.preventDefault(); edgeToPlayhead("l") }
    else if (e.key === "]") { e.preventDefault(); edgeToPlayhead("r") }
    else if (k === "r" && selItem) { e.preventDefault(); resetScene(selItem.scene) }
    else if (k === "s") { e.preventDefault(); setSnapOn((v) => !v) }
    else if (k === "l") { e.preventDefault(); setLink((v) => !v) }
    else if (k === "escape") setSelKey(null)
  }
  useEffect(() => {
    const on = (e: KeyboardEvent) => keyRef.current(e)
    const down = (e: PointerEvent) => { hot.current = !!root.current?.contains(e.target as Node) }
    window.addEventListener("keydown", on)
    window.addEventListener("pointerdown", down, true)
    return () => { window.removeEventListener("keydown", on); window.removeEventListener("pointerdown", down, true) }
  }, [])

  // ── Vẽ ──
  const step = TICK_STEPS.find((s) => s * pps >= 72) ?? 600
  const ticks: number[] = []
  for (let t = 0; t <= total + step; t += step) ticks.push(t)

  // Chỉ dựng khối trong vùng đang nhìn ± 1 khung (phim dài hàng nghìn dòng vẫn mượt). Vùng tính theo "trang" →
  // cuộn trong cùng trang không dựng lại làn.
  const pageSec = Math.max(5, view.w / pps)
  const winFrom = (Math.floor(view.left / pps / pageSec) - 1) * pageSec
  const winTo = winFrom + 3 * pageSec
  const inWin = (x: { start: number; end: number }) => x.end >= winFrom && x.start <= winTo

  /** Thân 1 khối (dùng cho làn và cho bản đang kéo). */
  const voiceInfo = (x: Item, sp: Span) => {
    const slot = Math.max(0.1, sp.end - sp.start)
    const need = x.text.replace(/\s+/g, " ").length / DUB_CPS
    const ratio = need / slot
    return { slot, need, ratio, level: ratio > 1.35 ? "long" : ratio > 1 ? "fast" : "ok" }
  }
  const itemCls = (x: Item) => x.lane === "voice"
    ? cn("bg-orange-600/80 border-orange-300/40", x.manual && "bg-orange-500/90 border-orange-200/70")
    : cn("bg-violet-600/80 border-violet-300/40", { ok: "", warn: "border-amber-300", bad: "border-red-400 bg-violet-700/80" }[speeds.get(x.key)?.level ?? "ok"])
  const itemBody = (x: Item, sp: Span) => {
    const px = (sp.end - sp.start) * pps
    const showText = px >= 44            // khối hẹp: chỉ màu, không chữ vụn (rê chuột xem đủ)
    if (x.lane === "sub") {
      const rs = readSpeed(x.text, sp.end - sp.start)
      if (!showText) return null
      return (
        <div className="pointer-events-none flex h-full flex-col justify-center px-2">
          <span className="truncate text-[10.5px] leading-tight text-white/95">{x.text}</span>
          {px >= 72 && (
            <span className={cn("tabular truncate font-mono text-[9px]", rs.level === "bad" ? "font-semibold text-red-300" : rs.level === "warn" ? "text-amber-200" : "text-white/50")}>
              {(sp.end - sp.start).toFixed(1)}s · {Math.round(rs.cps)} kt/s
            </span>
          )}
        </div>
      )
    }
    const v = voiceInfo(x, sp)
    return (
      <div className={cn("pointer-events-none relative flex h-full flex-col px-1.5 py-[4px]", showText ? "justify-between" : "justify-end")}>
        {showText && (
          <span className="flex items-center gap-1 truncate text-[10.5px] leading-tight font-medium text-white/95">
            {x.manual && <span className="size-1.5 shrink-0 rounded-full bg-amber-200" />}
            {x.text}
          </span>
        )}
        <span className="relative h-[4px] w-full overflow-hidden rounded-full bg-black/30">
          <span className={cn("absolute inset-y-0 left-0 rounded-full", v.level === "long" ? "bg-red-400" : v.level === "fast" ? "bg-amber-300" : "bg-emerald-300/90")}
            style={{ width: `${Math.min(100, v.ratio * 100)}%` }} />
        </span>
      </div>
    )
  }
  const itemTitle = (x: Item) => {
    if (x.lane === "sub") {
      const rs = speeds.get(x.key) ?? readSpeed(x.text, x.end - x.start)
      return `Câu ${x.scene + 1}${x.part >= 0 ? ` · dòng ${x.part + 1}` : ""} · ${fmtClock(x.start)} → ${fmtClock(x.end)} · ${Math.round(rs.cps)} ký tự/giây` +
        (rs.level === "bad" ? ` · quá gấp, nên ~${rs.need.toFixed(1)}s` : rs.level === "warn" ? ` · hơi gấp, nên ~${rs.need.toFixed(1)}s` : "") + `\n${x.text}`
    }
    const v = voiceInfo(x, x)
    return `Câu ${x.scene + 1} · khung đọc ${fmtClock(x.start)} → ${fmtClock(x.end)} (${v.slot.toFixed(1)}s) · cần ~${v.need.toFixed(1)}s` +
      (v.level === "long" ? " · dài quá, AI sẽ rút gọn (hoặc nới khung)" : v.level === "fast" ? " · đọc hơi nhanh" : "") + (x.manual ? " · đã chỉnh tay" : "")
  }

  const laneEls = useMemo(() => {
    const box = (x: Item) => {
      const isSel = selKey === x.key
      const lifted = dragKeys?.has(x.key)
      return (
        <div key={x.key} onPointerDown={(e) => startDrag(e, x, "move")} title={itemTitle(x)}
          className={cn("group absolute inset-y-1 cursor-grab overflow-hidden rounded-md border active:cursor-grabbing hover:brightness-110", itemCls(x),
            selected === x.scene && !isSel && "ring-1 ring-white/35", isSel && "z-10 border-white ring-2 ring-white",
            lifted && "border-dashed opacity-30 ring-0")}
          style={{ left: x.start * pps, width: Math.max(4, (x.end - x.start) * pps) }}>
          {itemBody(x, x)}
          <span onPointerDown={(e) => startDrag(e, x, "l")}
            className="absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize after:absolute after:inset-y-1.5 after:left-0.5 after:w-[3px] after:rounded-full after:bg-white/0 group-hover:after:bg-white/60 hover:after:bg-white" />
          <span onPointerDown={(e) => startDrag(e, x, "r")}
            className="absolute inset-y-0 right-0 z-10 w-2 cursor-ew-resize after:absolute after:inset-y-1.5 after:right-0.5 after:w-[3px] after:rounded-full after:bg-white/0 group-hover:after:bg-white/60 hover:after:bg-white" />
        </div>
      )
    }
    return (<>
      <Lane h={LANES.orig.h} onScrub={startScrub}>
        {peaks && <Wave peaks={peaks} pps={pps} from={Math.max(0, winFrom)} to={Math.min(total, winTo)} h={LANES.orig.h} />}
        {origs.map((o, k) => inWin(o) && (
          <div key={k} title={`Gốc ${fmtClock(o.start)} → ${fmtClock(o.end)}\n${o.text}`}
            onPointerDown={(e) => { e.stopPropagation(); latest.current.onSeek(o.start); latest.current.onSelect(o.scene) }}
            className={cn("absolute top-[3px] h-[15px] cursor-pointer overflow-hidden rounded-[3px] border border-dashed border-slate-300/40 bg-slate-600/45 hover:bg-slate-500/60",
              selected === o.scene && "border-slate-100/80 bg-slate-500/70")}
            style={{ left: o.start * pps, width: Math.max(2, (o.end - o.start) * pps) }}>
            {(o.end - o.start) * pps >= 30 && <span className="block truncate px-1.5 text-[9.5px] leading-[13px] text-slate-200/85">{o.text}</span>}
          </div>
        ))}
      </Lane>
      {dub && <Lane h={LANES.voice.h} onScrub={startScrub}>{lanes.voice.filter(inWin).map(box)}</Lane>}
      <Lane h={LANES.sub.h} onScrub={startScrub}>{lanes.sub.filter(inWin).map(box)}</Lane>
    </>)
  }, [lanes, origs, pps, dragKeys, selKey, selected, dub, link, snapOn, byKey, winFrom, winTo, peaks, speeds, shots, total]) // eslint-disable-line react-hooks/exhaustive-deps

  // vạch chuyển cảnh (chỉ trong vùng đang nhìn)
  // thu nhỏ quá (vạch cách nhau < 14px) → ẩn cho đỡ rối, vẫn hít vào được
  const shotEls = useMemo(() => (shots.length && (total / shots.length) * pps < 14 ? [] : shots).filter((c) => c >= winFrom && c <= winTo).map((c) => (
    <div key={c} className="pointer-events-none absolute bottom-0 z-[5] w-px bg-cyan-300/40" style={{ left: c * pps, top: RULER_H - 6 }}>
      <span className="absolute -top-px -left-[3px] size-[7px] rotate-45 bg-cyan-300/80" />
    </div>
  )), [shots, pps, winFrom, winTo, total])

  // bản đang kéo: lớp nổi trên các làn
  const laneTop = (lane: LaneKey) => RULER_H + LANES.orig.h + (lane === "sub" && dub ? LANES.voice.h : 0)
  const ghostEls = ghost && [...ghost.spans].map(([k, sp]) => {
    const x = byKey.get(k)
    if (!x) return null
    return (
      <div key={k} className={cn("pointer-events-none absolute z-30 overflow-hidden rounded-md border shadow-lg ring-2 shadow-black/60 ring-amber-300", itemCls(x))}
        style={{ left: sp.start * pps, width: Math.max(4, (sp.end - sp.start) * pps), top: laneTop(x.lane) + 4, height: LANES[x.lane].h - 8 }}>
        {itemBody(x, sp)}
      </div>
    )
  })

  // thanh tổng quan: chỉ dựng lại khi câu / chọn / zoom đổi (không theo từng khung hình khi phát)
  const overviewSegs = useMemo(() => {
    const W = Math.max(1, width)
    return lanes.sub.map((x) => (
      <span key={x.key} className={cn("absolute inset-y-0", selected === x.scene ? "bg-white/70" : retimedSet.has(x.scene) ? "bg-amber-300/60" : "bg-violet-400/40")}
        style={{ left: `${((x.start * pps) / W) * 100}%`, width: `${(Math.max(1, (x.end - x.start) * pps) / W) * 100}%` }} />
    ))
  }, [lanes.sub, selected, retimedSet, pps, width])

  const overview = useRef<HTMLDivElement>(null)
  const startOverview = (e: RPE) => {
    const el = scroller.current, bar = overview.current
    if (!el || !bar || !width) return
    const go = (x: number) => { const r = bar.getBoundingClientRect(); el.scrollLeft = ((x - r.left) / r.width) * width - el.clientWidth / 2 }
    go(e.clientX)
    const move = (ev: PointerEvent) => go(ev.clientX)
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up) }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }
  const pct = (px: number) => `${(px / Math.max(1, width)) * 100}%`
  const empty = items.length === 0
  const selSpan = selItem ? ghost?.spans.get(selItem.key) ?? selItem : undefined
  const laneKeys = (dub ? ["orig", "voice", "sub"] : ["orig", "sub"]) as (keyof typeof LANES)[]

  return (
    <div ref={root} onPointerEnter={() => { hot.current = true }}
      className="flex shrink-0 flex-col border-t border-white/10 bg-[#161618] text-white/90 select-none">
      {/* Thanh công cụ: công cụ sửa | phát ở giữa | zoom */}
      <div className="grid h-11 grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-white/10 px-3">
        <div className="flex min-w-0 items-center gap-1">
          <IconBtn title="Hoàn tác (Ctrl+Z)" disabled={!past.current.length} onClick={undo}><Undo2 /></IconBtn>
          <IconBtn title="Làm lại (Ctrl+Y)" disabled={!future.current.length} onClick={redo}><Redo2 /></IconBtn>
          <Sep />
          <IconBtn title={snapOn ? "Hít: bật (S) — dính vào đầu phát, mép khối, chuyển cảnh" : "Hít: tắt (S)"} active={snapOn} onClick={() => setSnapOn(!snapOn)}><Magnet /></IconBtn>
          {dub && (
            <IconBtn title={link ? "Liên kết: bật (L) — phụ đề & giọng cùng câu dời chung" : "Liên kết: tắt (L) — dời riêng"} active={link} onClick={() => setLink(!link)}>
              {link ? <Link2 /> : <Link2Off />}
            </IconBtn>
          )}
          <IconBtn title="Tách dòng tại đầu phát (Ctrl+B)" onClick={splitLine}><Scissors /></IconBtn>
          <IconBtn title="Gộp với dòng sau (M)" onClick={mergeLine}><Combine /></IconBtn>
          {hurried.length > 0 && (
            <button onClick={fixSpeed} title="Dòng hiện quá nhanh so với số chữ — bấm để tự nới vào khoảng trống"
              className="ml-1 flex h-6 shrink-0 items-center gap-1 rounded-md bg-amber-400/15 px-2 text-[11px] font-medium whitespace-nowrap text-amber-200 ring-1 ring-amber-300/30 hover:bg-amber-400/25 [&_svg]:size-3.5">
              <Wand2 /> Nới {hurried.length} dòng gấp
            </button>
          )}
          <Sep />
          {selItem && selSpan ? <>
            <span className="tabular mr-0.5 shrink-0 text-[11px] whitespace-nowrap text-white/60" title={`${fmtClock(selSpan.start)} → ${fmtClock(selSpan.end)}`}>
              <b className={cn("font-semibold", selItem.lane === "voice" ? "text-orange-300" : "text-violet-300")}>
                {selItem.lane === "voice" ? "Giọng" : "Phụ đề"} #{selItem.scene + 1}{selItem.part >= 0 && (lanes.sub.filter((x) => x.scene === selItem.scene).length > 1) ? `.${selItem.part + 1}` : ""}
              </b> · {(selSpan.end - selSpan.start).toFixed(1)}s
            </span>
            <IconBtn title="Đầu dòng = đầu phát ([)" onClick={() => edgeToPlayhead("l")}><ArrowLeftToLine /></IconBtn>
            <IconBtn title="Cuối dòng = đầu phát (])" onClick={() => edgeToPlayhead("r")}><ArrowRightToLine /></IconBtn>
            <IconBtn title="Về giờ gốc (R)" disabled={!isRetimed(scenes[selItem.scene])} onClick={() => resetScene(selItem.scene)}><RotateCcw /></IconBtn>
          </> : (
            <span className="truncate text-[11px] whitespace-nowrap text-white/40">
              {retimed > 0 ? <>{retimed} câu đã chỉnh · <button className="text-white/70 underline-offset-2 hover:text-white hover:underline" onClick={resetAll}>khôi phục</button></>
                : "Kéo khối để dời · kéo mép để cắt"}
            </span>
          )}
        </div>
        <div className={cn("flex items-center gap-3", empty && "pointer-events-none opacity-40")}>
          <span className="tabular w-[62px] text-right font-mono text-[12.5px] text-white">{fmtClock(time)}</span>
          <div className="flex items-center gap-1">
            <IconBtn title="Dòng trước (↑)" onClick={() => jump(-1)}><SkipBack /></IconBtn>
            <button title="Phát / dừng (Space)" onClick={onToggle}
              className="flex size-8 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md shadow-primary/30 transition hover:scale-105 [&_svg]:size-4">
              {playing ? <Pause /> : <Play className="translate-x-px" />}
            </button>
            <IconBtn title="Dòng sau (↓)" onClick={() => jump(1)}><SkipForward /></IconBtn>
          </div>
          <span className="tabular w-[62px] font-mono text-[12.5px] text-white/40">{fmtClock(total)}</span>
        </div>
        <div className="flex items-center justify-end gap-1.5">
          <IconBtn title={follow ? "Bám theo đầu phát: bật" : "Bám theo đầu phát: tắt"} active={follow} onClick={() => setFollow(!follow)}><Crosshair /></IconBtn>
          <IconBtn title="Vừa khung" onClick={fit}><Maximize2 /></IconBtn>
          <IconBtn title="Thu nhỏ" onClick={() => setPps((p) => Math.max(MIN_PPS, p / 1.4))}><ZoomOut /></IconBtn>
          <Slider className="w-24" value={[Math.log(pps)]} min={Math.log(MIN_PPS)} max={Math.log(MAX_PPS)} step={0.01} onValueChange={([v]) => setPps(Math.exp(v))} />
          <IconBtn title="Phóng to" onClick={() => setPps((p) => Math.min(MAX_PPS, p * 1.4))}><ZoomIn /></IconBtn>
          <Tooltip>
            <TooltipTrigger asChild><span className="ml-1 cursor-help text-white/40 hover:text-white/80 [&_svg]:size-4"><CircleHelp /></span></TooltipTrigger>
            <TooltipContent side="top" className="w-72 p-3 text-xs">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                {HELP.map(([k, v]) => <div key={k} className="contents"><dt className="font-mono font-semibold whitespace-nowrap">{k}</dt><dd className="opacity-80">{v}</dd></div>)}
              </dl>
              <p className="mt-2 border-t border-white/10 pt-2 leading-relaxed opacity-70">
                Viền vàng / đỏ = dòng hiện quá nhanh (nên ≤ 17 ký tự/giây). Thanh trong khối giọng: xanh vừa · vàng hơi nhanh · đỏ dài quá. Vạch xanh ngọc = chuyển cảnh.
              </p>
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      {!empty && width > view.w * 1.3 && (
        <div className="flex h-4 items-center border-b border-white/10 bg-black/20" style={{ paddingLeft: HEADER_W }}>
          <div ref={overview} onPointerDown={startOverview} title="Bấm để nhảy tới"
            className="relative mx-1 h-2.5 flex-1 cursor-pointer overflow-hidden rounded-sm bg-white/[0.04]">
            {overviewSegs}
            <span className="pointer-events-none absolute inset-y-0 w-px bg-red-500" style={{ left: pct(time * pps) }} />
            <span className="pointer-events-none absolute inset-y-0 rounded-sm border border-white/80 bg-white/10" style={{ left: pct(view.left), width: pct(Math.min(width, view.w)) }} />
          </div>
        </div>
      )}

      <div className="flex">
        <div className="shrink-0 border-r border-white/10 bg-[#1b1b1e]" style={{ width: HEADER_W }}>
          <div className="border-b border-white/10" style={{ height: RULER_H }} />
          {laneKeys.map((k) => {
            const t = LANES[k]
            const Icon = t.icon
            return (
              <div key={k} className="relative flex items-center gap-1.5 border-b border-white/10 pr-1.5 pl-3" style={{ height: t.h }} title={`${t.label} — ${t.sub}`}>
                <span className={cn("absolute inset-y-1.5 left-0 w-[3px] rounded-r", t.accent)} />
                <span className={cn("flex size-5 shrink-0 items-center justify-center rounded bg-white/5 [&_svg]:size-3.5", t.text)}><Icon /></span>
                <span className="text-[11px] whitespace-nowrap text-white/60">{t.label}</span>
              </div>
            )
          })}
        </div>

        <div ref={scroller} className="relative min-w-0 flex-1 overflow-x-auto overflow-y-hidden" onWheel={onWheel}>
          <div className="relative" style={{ width: width || "100%" }}>
            <div className="relative cursor-ew-resize border-b border-white/10 bg-white/[0.03]" style={{ height: RULER_H }} onPointerDown={startScrub}>
              {ticks.map((t) => (
                <div key={t} className="absolute inset-y-0 border-l border-white/15" style={{ left: t * pps }}>
                  <span className="tabular absolute top-[3px] left-1 font-mono text-[9.5px] text-white/45">{fmtTick(t)}</span>
                </div>
              ))}
            </div>
            {laneEls}
            {shotEls}
            {empty && (
              <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-center" style={{ top: RULER_H }}>
                <span className="rounded-full border border-white/10 bg-[#161618]/90 px-3 py-1 text-[11px] text-white/55">Chưa có dòng phụ đề</span>
              </div>
            )}
            {/* vạch hít + nhãn thời gian khi đang kéo */}
            {ghostEls}
            {ghost?.snapAt !== undefined && (
              <div className="pointer-events-none absolute bottom-0 z-40 w-px bg-amber-300 shadow-[0_0_6px_rgba(252,211,77,.9)]" style={{ left: ghost.snapAt * pps, top: RULER_H }} />
            )}
            {ghost && (() => {
              const first = [...ghost.spans.values()][0]
              return (
                <div className="tabular pointer-events-none absolute top-[2px] z-50 -translate-x-1/2 rounded bg-amber-300 px-1.5 py-px font-mono text-[10px] whitespace-nowrap text-black shadow"
                  style={{ left: Math.max(60, first.start * pps) }}>{ghost.label}</div>
              )
            })()}
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

/** Sóng âm vẽ bằng canvas — chỉ phần đang nhìn, mỗi cột pixel lấy đỉnh lớn nhất trong khoảng thời gian của cột. */
function Wave({ peaks, pps, from, to, h }: { peaks: Peaks; pps: number; from: number; to: number; h: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const w = Math.max(1, Math.round((to - from) * pps))
  useEffect(() => {
    const c = ref.current
    if (!c) return
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    c.width = Math.min(30000, Math.round(w * dpr))
    c.height = Math.round(h * dpr)
    const g = c.getContext("2d")
    if (!g) return
    g.setTransform(c.width / w, 0, 0, dpr, 0, 0)
    g.clearRect(0, 0, w, h)
    g.fillStyle = "rgba(56,189,248,0.5)"
    const { rate, data } = peaks
    const mid = h / 2 + 7, amp = h / 2 - 9
    for (let x = 0; x < w; x++) {
      const t0 = from + x / pps
      const i0 = Math.floor(t0 * rate), i1 = Math.max(i0 + 1, Math.ceil((t0 + 1 / pps) * rate))
      let m = 0
      for (let i = i0; i < i1 && i < data.length; i++) if (data[i] > m) m = data[i]
      const bh = Math.max(0.5, (m / 255) * amp)
      g.fillRect(x, mid - bh, 1, bh * 2)
    }
  }, [peaks, pps, from, w, h])
  return <canvas ref={ref} className="pointer-events-none absolute top-0" style={{ left: from * pps, width: w, height: h }} />
}

function fmtTick(t: number) {
  const m = Math.floor(t / 60)
  const s = t % 60
  return `${String(m).padStart(2, "0")}:${(Number.isInteger(s) ? String(s) : s.toFixed(1)).padStart(2, "0")}`
}

const Sep = () => <span className="mx-1 h-4 w-px shrink-0 bg-white/10" />

function IconBtn({ title, onClick, children, active, disabled }: { title: string; onClick: () => void; children: ReactNode; active?: boolean; disabled?: boolean }) {
  return (
    <button title={title} onClick={onClick} disabled={disabled} aria-pressed={active}
      className={cn("flex size-7 shrink-0 items-center justify-center rounded-md disabled:pointer-events-none disabled:opacity-30 [&_svg]:size-3.5",
        active ? "bg-primary/25 text-white ring-1 ring-primary/50" : "text-white/60 hover:bg-white/10 hover:text-white")}>
      {children}
    </button>
  )
}

function Lane({ h, children, onScrub }: { h: number; children: ReactNode; onScrub: (e: RPE) => void }) {
  return (
    <div className="relative border-b border-white/10" style={{ height: h }} onPointerDown={(e) => { if (e.target === e.currentTarget) onScrub(e) }}>
      {children}
    </div>
  )
}
