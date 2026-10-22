import { Film } from "lucide-react"
import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react"
import { mediaUrl } from "@/lib/api"
import type { TextRegion } from "@/lib/types"
import { fmtClock } from "@/lib/format"
import { cn } from "@/lib/utils"

/** [x, y, rộng, cao] theo %. Vùng che: % khung xuất · Khung cắt: % hình gốc. */
export type CoverBox = number[]

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const round1 = (v: number) => Math.round(v * 10) / 10
type Handle = "move" | "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw"
const HANDLES: { h: Handle; cls: string; cursor: string }[] = [
  { h: "nw", cls: "-top-1.5 -left-1.5", cursor: "cursor-nwse-resize" }, { h: "n", cls: "-top-1.5 left-1/2 -translate-x-1/2", cursor: "cursor-ns-resize" },
  { h: "ne", cls: "-top-1.5 -right-1.5", cursor: "cursor-nesw-resize" }, { h: "e", cls: "top-1/2 -right-1.5 -translate-y-1/2", cursor: "cursor-ew-resize" },
  { h: "se", cls: "-right-1.5 -bottom-1.5", cursor: "cursor-nwse-resize" }, { h: "s", cls: "-bottom-1.5 left-1/2 -translate-x-1/2", cursor: "cursor-ns-resize" },
  { h: "sw", cls: "-bottom-1.5 -left-1.5", cursor: "cursor-nesw-resize" }, { h: "w", cls: "top-1/2 -left-1.5 -translate-y-1/2", cursor: "cursor-ew-resize" },
]
const MIN = 3

/** Kéo khung theo kiểu CapCut: thân = dời, 4 góc + 4 cạnh = đổi cỡ. `parent` = phần tử mà % tính theo. */
function startBoxDrag(e: ReactPointerEvent, parent: HTMLElement, box: CoverBox, handle: Handle, onChange: (b: CoverBox) => void) {
  e.preventDefault(); e.stopPropagation()
  const r = parent.getBoundingClientRect()
  const [x0, y0] = [e.clientX, e.clientY]
  const [bx, by, bw, bh] = box
  const move = (ev: PointerEvent) => {
    const dx = ((ev.clientX - x0) / r.width) * 100
    const dy = ((ev.clientY - y0) / r.height) * 100
    if (handle === "move") { onChange([clamp(bx + dx, 0, 100 - bw), clamp(by + dy, 0, 100 - bh), bw, bh].map(round1)); return }
    let [l, t, rr, b] = [bx, by, bx + bw, by + bh]
    if (handle.includes("w")) l = clamp(l + dx, 0, rr - MIN)
    if (handle.includes("e")) rr = clamp(rr + dx, l + MIN, 100)
    if (handle.includes("n")) t = clamp(t + dy, 0, b - MIN)
    if (handle.includes("s")) b = clamp(b + dy, t + MIN, 100)
    onChange([l, t, rr - l, b - t].map(round1))
  }
  const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up) }
  window.addEventListener("pointermove", move)
  window.addEventListener("pointerup", up)
}

/** Khung có 8 tay cầm. dim = làm tối phần ngoài khung (dùng cho khung cắt). */
export function BoxFrame({ box, parent, onChange, label, active, dim, blur }: {
  box: CoverBox; parent: () => HTMLElement | null; onChange: (b: CoverBox) => void; label: string; active?: boolean; dim?: boolean; blur?: boolean
}) {
  const down = (e: ReactPointerEvent, h: Handle) => { const p = parent(); if (p) startBoxDrag(e, p, box, h, onChange) }
  return (
    <div onPointerDown={(e) => down(e, "move")}
      className={cn("absolute cursor-move border-2", active ? "border-white" : "border-white/60", blur && "backdrop-blur-[10px]")}
      style={{ left: `${box[0]}%`, top: `${box[1]}%`, width: `${box[2]}%`, height: `${box[3]}%`,
        boxShadow: dim ? "0 0 0 9999px rgba(0,0,0,.6)" : "0 0 0 1px rgba(0,0,0,.4)" }}>
      {/* lưới 1/3 giúp căn giữa */}
      {dim && <div className="pointer-events-none absolute inset-0 [background:linear-gradient(to_right,transparent_33.2%,rgba(255,255,255,.25)_33.3%,transparent_33.5%,transparent_66.5%,rgba(255,255,255,.25)_66.6%,transparent_66.8%),linear-gradient(to_bottom,transparent_33.2%,rgba(255,255,255,.25)_33.3%,transparent_33.5%,transparent_66.5%,rgba(255,255,255,.25)_66.6%,transparent_66.8%)]" />}
      <span className="pointer-events-none absolute -top-5 left-0 rounded bg-black/75 px-1.5 text-[10px] whitespace-nowrap text-white">{label}</span>
      {HANDLES.map(({ h, cls, cursor }) => (
        <span key={h} onPointerDown={(e) => down(e, h)}
          className={cn("absolute size-3 rounded-full border border-black/40 bg-white shadow", cls, cursor)} />
      ))}
    </div>
  )
}

/**
 * Màn hình xem trước: hình gốc chạy theo đầu phát (player điều khiển qua attachVideo) + phụ đề đè lên.
 * Khung có đúng tỉ lệ video xuất, hình gốc co vào giống lúc dựng → vùng che (% khung hình) khớp 1-1 với video thật.
 * crop = khung cắt (% hình gốc): xem trước hiện đúng kết quả sau cắt (phủ kín / viền đen); cropEdit = hiện cả hình gốc để chỉnh.
 */
export function Monitor({ videoPath, attachVideo, subtitle, time, total, label, aspect = 16 / 9, cover, coverEdit, onCoverChange, subMarginPct = 7,
  subCenterPct, crop, cropFill = true, cropEdit, onCropChange, textRegions, srcTime = 0, textEdit, onTextRegionChange, textBlurPx = 12 }: {
  videoPath?: string
  attachVideo: (el: HTMLVideoElement | null) => void
  subtitle: string
  time: number
  total: number
  label: string
  aspect?: number
  cover?: CoverBox[]
  coverEdit?: boolean
  onCoverChange?: (boxes: CoverBox[]) => void
  /** Phụ đề mới cách đáy bao nhiêu % chiều cao khung */
  subMarginPct?: number
  /** có → tâm phụ đề nằm ở % chiều cao này (giữa vùng che phụ đề cũ), bỏ qua subMarginPct */
  subCenterPct?: number | null
  crop?: CoverBox | null
  cropFill?: boolean
  cropEdit?: boolean
  onCropChange?: (box: CoverBox) => void
  /** Vùng chữ Trung cần che (theo hình gốc) — hiện mờ đúng lúc chữ xuất hiện (srcTime = giây trên video gốc) */
  textRegions?: TextRegion[]
  srcTime?: number
  textEdit?: boolean
  onTextRegionChange?: (index: number, r: TextRegion) => void
  textBlurPx?: number
}) {
  const wrap = useRef<HTMLDivElement>(null)
  const frame = useRef<HTMLDivElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [srcAspect, setSrcAspect] = useState(16 / 9)
  const [active, setActive] = useState(0)

  // Khung lớn nhất vừa màn hình mà vẫn đúng tỉ lệ video xuất
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const fit = () => {
      const [W, H] = [el.clientWidth, el.clientHeight]
      if (!W || !H) return
      setSize(W / H > aspect ? { w: H * aspect, h: H } : { w: W, h: W / aspect })
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [aspect])

  // ổn định giữa các lần vẽ lại — không thì player bị gắn lại video liên tục
  const bindVideo = useCallback((el: HTMLVideoElement | null) => {
    attachVideo(el)
    if (!el) return
    const read = () => { if (el.videoWidth && el.videoHeight) setSrcAspect(el.videoWidth / el.videoHeight) }
    read()
    el.addEventListener("loadedmetadata", read)
  }, [attachVideo])

  // Vị trí hình gốc trong khung (px): bình thường co vừa khung; có cắt → phóng phần đã cắt phủ kín / vừa khung như lúc dựng
  const [FW, FH] = [size.w, size.h]
  const cropOn = !!crop && !cropEdit && !(crop[2] > 99.5 && crop[3] > 99.5)
  let st = { left: 0, top: 0, width: FW, height: FH }
  if (FW && FH) {
    if (cropOn) {
      const [cx, cy, cw, ch] = crop!.map((v) => v / 100)
      const rw = cw * srcAspect, rh = ch                         // vùng cắt theo đơn vị "chiều cao hình gốc = 1"
      const s = cropFill ? Math.max(FW / rw, FH / rh) : Math.min(FW / rw, FH / rh)
      st = { width: srcAspect * s, height: s, left: FW / 2 - (cx + cw / 2) * srcAspect * s, top: FH / 2 - (cy + ch / 2) * s }
    } else {
      const s = Math.min(FW / srcAspect, FH)
      st = { width: srcAspect * s, height: s, left: (FW - srcAspect * s) / 2, top: (FH - s) / 2 }
    }
  }

  return (
    <div ref={wrap} className="relative flex min-h-0 items-center justify-center overflow-hidden bg-black">
      <div ref={frame} className="relative overflow-hidden" style={{ width: size.w, height: size.h, containerType: "size" }}>
        {videoPath ? (
          <div ref={stage} className="absolute" style={st}>
            <video ref={bindVideo} src={mediaUrl(videoPath)} preload="auto" playsInline className="absolute inset-0 size-full object-fill" />
            {!cropEdit && textRegions?.map((r, i) => {
              if (srcTime < r.t_start || srcTime > r.t_end || (r.off && !textEdit)) return null
              const b = [r.box[0] * 100, r.box[1] * 100, (r.box[2] - r.box[0]) * 100, (r.box[3] - r.box[1]) * 100]
              if (textEdit && onTextRegionChange && !r.off) {
                return <BoxFrame key={i} box={b} parent={() => stage.current} label={r.manual ? `Vùng tay ${i + 1}` : `Chữ ${i + 1}`} active blur
                  onChange={(nb) => onTextRegionChange(i, { ...r, box: [nb[0] / 100, nb[1] / 100, (nb[0] + nb[2]) / 100, (nb[1] + nb[3]) / 100] })} />
              }
              return <div key={i} className={cn("pointer-events-none absolute", r.off && "border border-dashed border-white/60")}
                style={{ left: `${b[0]}%`, top: `${b[1]}%`, width: `${b[2]}%`, height: `${b[3]}%`,
                  backdropFilter: r.off ? undefined : `blur(${textBlurPx}px)`, WebkitBackdropFilter: r.off ? undefined : `blur(${textBlurPx}px)` }} />
            })}
            {cropEdit && crop && onCropChange && (
              <BoxFrame box={crop} parent={() => stage.current} onChange={onCropChange} label="Khung cắt — phần tối sẽ bị bỏ" active dim />
            )}
          </div>
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-2 text-xs text-white/40"><Film className="size-6" /> Không có file video gốc để xem trước</div>
        )}
        {!cropEdit && cover?.map((b, i) => coverEdit && onCoverChange ? (
          <div key={i} onPointerDownCapture={() => setActive(i)}>
            <BoxFrame box={b} parent={() => frame.current} label={`Vùng che ${i + 1}`} active={active === i} blur
              onChange={(nb) => onCoverChange(cover.map((x, j) => (j === i ? nb : x)))} />
          </div>
        ) : (
          <div key={i} className="pointer-events-none absolute backdrop-blur-[10px]"
            style={{ left: `${b[0]}%`, top: `${b[1]}%`, width: `${b[2]}%`, height: `${b[3]}%` }} />
        ))}
        {subtitle && !cropEdit && (
          <div className={cn("pointer-events-none absolute inset-x-0 flex justify-center px-[9%]", subCenterPct != null && "-translate-y-1/2")}
            style={subCenterPct != null ? { top: `${subCenterPct}%` } : { bottom: `${subMarginPct}%` }}>
            {/* cỡ chữ = 1/26 chiều cao khung, rộng tối đa 82% — giống lúc dựng */}
            <span className="line-clamp-2 rounded bg-black/55 px-[0.6em] py-[0.15em] text-center leading-snug font-semibold break-words text-white [text-shadow:0_1px_2px_#000]"
              style={{ fontSize: "max(10px, 3.85cqh)" }}>{subtitle}</span>
          </div>
        )}
      </div>
      <span className="tabular absolute top-2 left-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10.5px] text-white/80">{fmtClock(time)} / {fmtClock(total)}</span>
      {label && <span className="absolute top-2 right-2 rounded bg-black/60 px-1.5 py-0.5 text-[10.5px] text-white/80">{label}</span>}
    </div>
  )
}

/**
 * Đoạn phụ đề đang hiện tại `offset` giây trong cảnh dài `dur` giây — chia lời thành các đoạn ≤ maxChars
 * (ưu tiên ngắt ở dấu câu) rồi rải đều theo thời gian, giống cách video_editor ghép phụ đề.
 */
export function subtitleChunk(text: string, offset: number, dur: number, maxChars = 80) {
  const words = (text || "").replace(/\s+/g, " ").trim().split(" ").filter(Boolean)
  if (!words.length) return ""
  const chunks: string[] = []
  let cur = ""
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w
    if (next.length > maxChars && cur) { chunks.push(cur); cur = w } else cur = next
    if (/[.!?…;]$/.test(w) && cur.length > maxChars * 0.45) { chunks.push(cur); cur = "" }
  }
  if (cur) chunks.push(cur)
  const i = Math.min(chunks.length - 1, Math.max(0, Math.floor((offset / Math.max(0.1, dur)) * chunks.length)))
  return chunks[i]
}
