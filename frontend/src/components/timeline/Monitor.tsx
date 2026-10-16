import { Film } from "lucide-react"
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react"
import { mediaUrl } from "@/lib/api"
import { fmtClock } from "@/lib/format"
import { cn } from "@/lib/utils"

/** [x, y, rộng, cao] theo % khung hình video xuất. */
export type CoverBox = number[]

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const round1 = (v: number) => Math.round(v * 10) / 10

/**
 * Màn hình xem trước: hình gốc chạy theo đầu phát (player điều khiển qua attachVideo) + phụ đề đè lên.
 * Khung có đúng tỉ lệ video xuất, hình gốc co vào giống lúc dựng → vùng che (% khung hình) khớp 1-1 với video thật.
 * Vùng che hiện mờ y như khi dựng; coverEdit = kéo thân để dời, kéo góc phải-dưới để đổi cỡ.
 */
export function Monitor({ videoPath, attachVideo, subtitle, time, total, label, aspect = 16 / 9, cover, coverEdit, onCoverChange, subMarginPct = 7 }: {
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
}) {
  const wrap = useRef<HTMLDivElement>(null)
  const frame = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
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

  const drag = (e: ReactPointerEvent, i: number, mode: "move" | "resize") => {
    if (!cover || !onCoverChange) return
    e.preventDefault(); e.stopPropagation()
    setActive(i)
    const r = frame.current!.getBoundingClientRect()
    const [x0, y0] = [e.clientX, e.clientY]
    const orig = [...cover[i]]
    const move = (ev: PointerEvent) => {
      const dx = ((ev.clientX - x0) / r.width) * 100
      const dy = ((ev.clientY - y0) / r.height) * 100
      const [bx, by, bw, bh] = orig
      const next = mode === "move"
        ? [clamp(bx + dx, 0, 100 - bw), clamp(by + dy, 0, 100 - bh), bw, bh]
        : [bx, by, clamp(bw + dx, 2, 100 - bx), clamp(bh + dy, 2, 100 - by)]
      onCoverChange(cover.map((b, j) => (j === i ? next.map(round1) : b)))
    }
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up) }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }

  return (
    <div ref={wrap} className="relative flex min-h-0 items-center justify-center overflow-hidden bg-black">
      <div ref={frame} className="relative overflow-hidden" style={{ width: size.w, height: size.h, containerType: "size" }}>
        {videoPath ? (
          <video ref={attachVideo} src={mediaUrl(videoPath)} preload="auto" playsInline className="absolute inset-0 size-full object-contain" />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-2 text-xs text-white/40"><Film className="size-6" /> Không có file video gốc để xem trước</div>
        )}
        {cover?.map((b, i) => (
          <div key={i} onPointerDown={coverEdit ? (e) => drag(e, i, "move") : undefined}
            className={cn("absolute backdrop-blur-[10px]", coverEdit
              ? cn("cursor-move border-2 border-dashed", active === i ? "border-amber-300 bg-amber-300/10" : "border-white/70 bg-white/5")
              : "pointer-events-none")}
            style={{ left: `${b[0]}%`, top: `${b[1]}%`, width: `${b[2]}%`, height: `${b[3]}%` }}>
            {coverEdit && <>
              <span className="absolute -top-5 left-0 rounded bg-black/70 px-1 text-[10px] whitespace-nowrap text-amber-200">Vùng {i + 1}</span>
              <span onPointerDown={(e) => drag(e, i, "resize")} title="Kéo để đổi kích thước"
                className="absolute -right-1.5 -bottom-1.5 size-3.5 cursor-nwse-resize rounded-sm border border-black/50 bg-amber-300" />
            </>}
          </div>
        ))}
        {subtitle && (
          <div className="pointer-events-none absolute inset-x-0 flex justify-center px-[9%]" style={{ bottom: `${subMarginPct}%` }}>
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
