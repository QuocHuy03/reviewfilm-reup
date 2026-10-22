import { RotateCcw } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Segmented } from "@/components/common"
import { BoxFrame, type CoverBox } from "@/components/timeline/Monitor"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { fmtClock } from "@/lib/format"

export const FULL_CROP: CoverBox = [0, 0, 100, 100]

/**
 * Cắt khung video gốc ngay khi tạo video (trước mọi bước khác): kéo 4 góc / 4 cạnh trên hình gốc,
 * tua để tìm khung có phụ đề cứng, xem trước kết quả trong khung xuất (phủ kín / viền đen).
 * box = [x, y, rộng, cao] theo % HÌNH GỐC — khớp backend (video_editor._crop_prefix).
 */
export function CropEditor({ src, resolution, box, fill, onChange, onFill }: {
  src?: string; resolution: string; box: CoverBox; fill: boolean; onChange: (b: CoverBox) => void; onFill: (v: boolean) => void
}) {
  const stage = useRef<HTMLDivElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const preview = useRef<HTMLVideoElement>(null)
  const [srcAspect, setSrcAspect] = useState(16 / 9)
  const [dur, setDur] = useState(0)
  const [t, setT] = useState(0)
  const [w, h] = resolution.split("x").map(Number)
  const outAspect = w && h ? w / h : 16 / 9

  useEffect(() => {
    for (const v of [video.current, preview.current]) if (v && dur) v.currentTime = t
  }, [t, dur])

  // Ảnh kết quả: phóng vùng đã cắt vào khung xuất y như lúc dựng (đơn vị % của khung kết quả)
  const [cx, cy, cw, ch] = box.map((v) => v / 100)
  const rw = cw * srcAspect, rh = ch
  const s = fill ? Math.max(outAspect / rw, 1 / rh) : Math.min(outAspect / rw, 1 / rh)   // khung kết quả cao = 1
  const vw = srcAspect * s, vh = s
  const pv = { width: `${(vw / outAspect) * 100}%`, height: `${vh * 100}%`,
    left: `${((outAspect / 2 - (cx + cw / 2) * srcAspect * s) / outAspect) * 100}%`, top: `${(0.5 - (cy + ch / 2) * s) * 100}%` }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/30 p-3">
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,34%)] items-start gap-3">
        <div>
          <p className="mb-1.5 text-[11px] text-muted-foreground">Hình gốc — kéo khung, phần tối sẽ bị cắt bỏ</p>
          <div className="relative w-full overflow-hidden rounded-md bg-black select-none" style={{ aspectRatio: srcAspect }}>
            <div ref={stage} className="absolute inset-0 m-4">
              {src
                ? <video ref={video} src={src} muted preload="auto" className="absolute inset-0 size-full object-fill"
                    onLoadedMetadata={(e) => { const v = e.currentTarget; setDur(v.duration || 0); if (v.videoWidth) setSrcAspect(v.videoWidth / v.videoHeight); v.currentTime = Math.min(5, (v.duration || 0) / 3); setT(v.currentTime) }} />
                : <div className="absolute inset-0 flex items-center justify-center text-[11px] text-white/40">Chọn file video để xem khung hình</div>}
              <BoxFrame box={box} parent={() => stage.current} onChange={onChange} label={`Giữ ${Math.round(box[2])}% × ${Math.round(box[3])}%`} active dim />
            </div>
          </div>
        </div>
        <div>
          <p className="mb-1.5 text-[11px] text-muted-foreground">Kết quả ({w}×{h})</p>
          <div className="relative w-full overflow-hidden rounded-md bg-black" style={{ aspectRatio: outAspect }}>
            {src && <video ref={preview} src={src} muted preload="auto" className="absolute max-w-none object-fill" style={pv} />}
          </div>
        </div>
      </div>
      {dur > 0 && (
        <div className="flex items-center gap-3">
          <span className="tabular w-12 text-[11px] text-muted-foreground">{fmtClock(t)}</span>
          <Slider value={[t]} min={0} max={dur} step={0.5} onValueChange={([v]) => setT(v)} className="flex-1" />
          <span className="tabular w-12 text-right text-[11px] text-muted-foreground">{fmtClock(dur)}</span>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Segmented size="sm" value={fill ? "fill" : "fit"} onChange={(v) => onFill(v === "fill")}
          items={[{ value: "fill", label: "Phủ kín khung" }, { value: "fit", label: "Giữ trọn (viền đen)" }]} />
        <Button size="sm" variant="outline" onClick={() => onChange([0, 0, 100, 84])} title="Cắt bỏ 16% phía dưới — chỗ phụ đề cứng hay nằm">Bỏ dải dưới</Button>
        <Button size="sm" variant="outline" onClick={() => onChange([0, 12, 100, 76])} title="Bỏ dải tiêu đề phía trên và phụ đề phía dưới">Bỏ trên + dưới</Button>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={() => onChange([...FULL_CROP])}><RotateCcw /> Đặt lại</Button>
      </div>
    </div>
  )
}
