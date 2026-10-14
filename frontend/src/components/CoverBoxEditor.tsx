import { Plus, RotateCcw, Trash2 } from "lucide-react"
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { fmtClock } from "@/lib/format"
import { cn } from "@/lib/utils"

/** [x, y, rộng, cao] theo % khung hình VIDEO XUẤT (sau khi co + thêm viền đen cho đúng tỉ lệ). */
export type CoverBox = number[]

export const DEFAULT_SUB_BOX: CoverBox = [10, 84, 80, 10]   // dải giữa phía dưới — chỗ phụ đề cứng hay nằm
const LOGO_BOX: CoverBox = [80, 3, 17, 10]
const MIN = 2

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const round1 = (v: number) => Math.round(v * 10) / 10

/**
 * Vẽ vùng che phụ đề gốc / logo trực tiếp lên khung hình video gốc.
 * Kéo thân = di chuyển · kéo góc phải-dưới = đổi kích thước · tua thanh trượt để tìm khung có chữ.
 * Khung xem trước có đúng tỉ lệ video xuất và co video giống lúc dựng → toạ độ % khớp 1-1 với video thật.
 */
export function CoverBoxEditor({ src, resolution, boxes, onChange }: {
  src?: string; resolution: string; boxes: CoverBox[]; onChange: (b: CoverBox[]) => void
}) {
  const frame = useRef<HTMLDivElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const [dur, setDur] = useState(0)
  const [t, setT] = useState(0)
  const [active, setActive] = useState(0)
  const [w, h] = resolution.split("x").map(Number)

  useEffect(() => { const v = video.current; if (v && dur) v.currentTime = t }, [t, dur])

  const drag = (e: ReactPointerEvent, i: number, mode: "move" | "resize") => {
    e.preventDefault(); e.stopPropagation()
    setActive(i)
    const r = frame.current!.getBoundingClientRect()
    const [x0, y0] = [e.clientX, e.clientY]
    const orig = [...boxes[i]]
    const move = (ev: PointerEvent) => {
      const dx = ((ev.clientX - x0) / r.width) * 100
      const dy = ((ev.clientY - y0) / r.height) * 100
      const [bx, by, bw, bh] = orig
      const next = mode === "move"
        ? [clamp(bx + dx, 0, 100 - bw), clamp(by + dy, 0, 100 - bh), bw, bh]
        : [bx, by, clamp(bw + dx, MIN, 100 - bx), clamp(bh + dy, MIN, 100 - by)]
      onChange(boxes.map((b, j) => (j === i ? next.map(round1) : b)))
    }
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up) }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }

  const b = boxes[active]
  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-border bg-muted/30 p-3">
      <div ref={frame} className="relative w-full overflow-hidden rounded-md bg-black select-none" style={{ aspectRatio: `${w} / ${h}` }}>
        {src
          ? <video ref={video} src={src} muted preload="auto" className="absolute inset-0 size-full object-contain"
              onLoadedMetadata={(e) => { const d = e.currentTarget.duration; if (Number.isFinite(d)) { setDur(d); setT(Math.min(d / 3, d)) } }} />
          : <div className="absolute inset-0 flex items-center justify-center text-[11px] text-white/40">Chọn file video để xem khung hình thật</div>}
        {boxes.map((bx, i) => (
          <div key={i} onPointerDown={(e) => drag(e, i, "move")}
            className={cn("absolute cursor-move border-2 backdrop-blur-md", i === active ? "border-primary bg-primary/15" : "border-white/70 bg-white/10")}
            style={{ left: `${bx[0]}%`, top: `${bx[1]}%`, width: `${bx[2]}%`, height: `${bx[3]}%` }}>
            <span className="absolute -top-5 left-0 rounded bg-black/70 px-1 text-[10px] whitespace-nowrap text-white">Vùng {i + 1}</span>
            <span onPointerDown={(e) => drag(e, i, "resize")} title="Kéo để đổi kích thước"
              className="absolute -right-1.5 -bottom-1.5 size-3 cursor-nwse-resize rounded-sm border border-black/40 bg-white" />
          </div>
        ))}
      </div>

      {dur > 0 && (
        <div className="flex items-center gap-2.5 text-[11px] text-muted-foreground">
          <span className="w-16 shrink-0">Khung hình</span>
          <Slider value={[t]} min={0} max={dur} step={0.1} onValueChange={([v]) => setT(v)} />
          <span className="tabular w-10 shrink-0 text-right font-mono">{fmtClock(t)}</span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        {b ? (
          <span className="tabular text-muted-foreground">
            Vùng {active + 1}: X {b[0]}% · Y {b[1]}% · Rộng {b[2]}% · Cao {b[3]}%
          </span>
        ) : <span className="text-muted-foreground">Chưa có vùng che nào</span>}
        <div className="ml-auto flex gap-1.5">
          <Button variant="outline" size="xs" onClick={() => { onChange([...boxes, [...DEFAULT_SUB_BOX]]); setActive(boxes.length) }}><Plus /> Vùng phụ đề</Button>
          <Button variant="outline" size="xs" onClick={() => { onChange([...boxes, [...LOGO_BOX]]); setActive(boxes.length) }}><Plus /> Vùng logo</Button>
          {b && <Button variant="ghost" size="xs" onClick={() => onChange(boxes.map((x, j) => (j === active ? [...DEFAULT_SUB_BOX] : x)))}><RotateCcw /> Mặc định</Button>}
          {b && <Button variant="ghost" size="xs" className="text-destructive hover:text-destructive" onClick={() => { onChange(boxes.filter((_, j) => j !== active)); setActive(0) }}><Trash2 /> Xoá</Button>}
        </div>
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground/80">Kéo khung để di chuyển, kéo ô vuông ở góc để đổi kích thước. Che vừa khít dòng chữ gốc là đủ — che rộng quá sẽ làm mờ cả hình.</p>
    </div>
  )
}
