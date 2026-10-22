import { Eye, EyeOff, Loader2, Move, Plus, RotateCw, ScanText, Trash2, X } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { Segmented } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { api } from "@/lib/api"
import { fmtClock } from "@/lib/format"
import type { Scene, TextRegion, TextScanState } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Đoạn hình gốc của 1 cảnh trên timeline (để gom vùng theo cảnh / nhảy tới đúng chỗ). */
export type SceneSpan = { n: number; srcStart: number; srcEnd: number }

/** Cắt mỗi vùng theo ranh giới cảnh → mỗi cảnh có vùng riêng (tắt / sửa cảnh này không ảnh hưởng cảnh khác). */
function splitByScenes(regs: TextRegion[], spans: SceneSpan[]): TextRegion[] {
  const out: TextRegion[] = []
  regs.forEach((r, g) => {
    for (const sp of spans) {
      const a = Math.max(r.t_start, sp.srcStart), b = Math.min(r.t_end, sp.srcEnd)
      if (b - a > 0.05) out.push({ ...r, t_start: +a.toFixed(2), t_end: +b.toFixed(2), n: sp.n, g })
    }
  })
  return out.sort((x, y) => (x.n ?? 0) - (y.n ?? 0) || x.t_start - y.t_start)
}

const where = (b: number[]) => {
  const cy = (b[1] + b[3]) / 2
  return cy > 0.66 ? "dưới" : cy < 0.33 ? "trên" : "giữa"
}

/**
 * Che chữ Trung theo từng đoạn: AI quét video gốc → danh sách vùng (đúng chỗ, đúng lúc chữ hiện) hiện mờ ngay trên màn xem trước.
 * Tắt / xoá vùng sai, sửa khung trên màn hình, thêm vùng tay cho cảnh đang xem → lúc dựng dùng đúng danh sách này.
 */
export function TextRegionsPanel({ jobId, scenes, spans, regions, interval, onRegions, onInterval, editing, setEditing, currentSpan, onJump }: {
  jobId: string
  scenes: Scene[]
  spans: SceneSpan[]
  regions: TextRegion[] | null | undefined
  interval: number
  onRegions: (r: TextRegion[] | null) => void
  onInterval: (v: number) => void
  editing: boolean
  setEditing: (v: boolean) => void
  currentSpan: SceneSpan | null
  onJump: (srcT: number) => void
}) {
  const [scan, setScan] = useState<TextScanState | null>(null)
  const onRegionsRef = useRef(onRegions)
  const spansRef = useRef(spans)
  useEffect(() => { onRegionsRef.current = onRegions; spansRef.current = spans })

  // quét đang chạy (kể cả khi vừa mở lại màn hình) → hỏi tiến độ tới khi xong
  useEffect(() => { api.textScanState(jobId).then((s) => { if (s.running) setScan(s) }).catch(() => {}) }, [jobId])
  useEffect(() => {
    if (!scan?.running) return
    const t = setInterval(async () => {
      const s = await api.textScanState(jobId).catch(() => null)
      if (!s) return
      setScan(s)
      if (!s.running) {
        if (s.error) toast.error("Quét chữ lỗi", { description: s.error })
        else if (s.regions) {
          onRegionsRef.current(splitByScenes(s.regions, spansRef.current))
          toast.success(`Tìm thấy ${s.regions.length} vùng chữ Trung`, { description: "Xem trên màn hình, tắt vùng sai rồi bấm Xuất video." })
        }
      }
    }, 1000)
    return () => clearInterval(t)
  }, [scan?.running, jobId])

  const start = () => api.textScan(jobId, interval, scenes).then(setScan).catch((e) => toast.error((e as Error).message))
  const list = regions ?? []
  // vùng thuộc cảnh n (vùng cũ chưa có n → theo điểm giữa thời gian)
  const groups = useMemo(() => spans.map((sp) => ({
    sp, items: list.map((r, i) => ({ r, i })).filter(({ r }) => r.n != null ? r.n === sp.n : (r.t_start + r.t_end) / 2 >= sp.srcStart && (r.t_start + r.t_end) / 2 < sp.srcEnd),
  })).filter((g) => g.items.length), [spans, list])
  const update = (i: number, patch: Partial<TextRegion>) => onRegions(list.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  /** Tắt / bật 1 vùng ở cảnh này; vùng đó còn ở cảnh khác (vd logo suốt phim) → gợi ý áp cho mọi cảnh */
  const toggle = (i: number) => {
    const r = list[i], off = !r.off
    update(i, { off })
    const same = r.g != null ? list.filter((x, j) => j !== i && x.g === r.g && !!x.off !== off).length : 0
    if (same) toast(`${off ? "Đã tắt" : "Đã bật"} vùng này ở cảnh ${r.n}`, {
      description: `Vùng này còn ở ${same} cảnh khác.`,
      action: { label: off ? "Tắt ở mọi cảnh" : "Bật ở mọi cảnh", onClick: () => onRegions(list.map((x, j) => (j === i || x.g === r.g ? { ...x, off } : x))) },
    })
  }
  const addManual = () => {
    if (!currentSpan) return
    onRegions([...list, { box: [0.1, 0.84, 0.9, 0.96], t_start: currentSpan.srcStart, t_end: currentSpan.srcEnd, manual: true, n: currentSpan.n }])
    setEditing(true)
    toast.info(`Đã thêm vùng che cho cảnh ${currentSpan.n}`, { description: "Kéo khung trên màn hình cho trùm chữ." })
  }
  const on = list.filter((r) => !r.off).length

  if (scan?.running) {
    const pct = scan.total ? Math.round((scan.done / scan.total) * 100) : 0
    return (
      <div className="flex flex-col gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
        <div className="flex items-center gap-2 text-[12.5px] font-medium">
          <Loader2 className="size-3.5 animate-spin text-primary" /> AI đang quét chữ Trung…
          <span className="ml-auto font-mono text-[11px] text-muted-foreground">{scan.done}/{scan.total || "?"} khung</span>
          <Button size="icon-xs" variant="ghost" title="Huỷ" onClick={() => api.textScanCancel(jobId).then(setScan).catch(() => {})}><X /></Button>
        </div>
        <Progress value={pct} />
        <p className="text-[11px] text-muted-foreground">Quét theo từng cảnh đang dùng. Lần sau mở lại dùng kết quả đã lưu, không phải quét lại.</p>
      </div>
    )
  }

  if (!regions) {
    return (
      <div className="flex flex-col gap-2.5 rounded-lg border border-border bg-muted/30 p-3">
        <p className="text-[12px] text-muted-foreground">
          Quét trước để <b className="text-foreground">xem & sửa từng vùng che</b> theo đoạn. Không quét thì app tự quét lúc xuất video.
        </p>
        <Segmented size="sm" value={String(interval)} onChange={(v) => onInterval(Number(v))}
          items={[{ value: "1", label: "Kỹ (mỗi 1 giây)" }, { value: "2", label: "Nhanh (mỗi 2 giây)" }]} />
        <Button size="sm" onClick={start}><ScanText /> Quét chữ Trung &amp; xem trước</Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-border p-3">
      <div className="flex items-center gap-2 text-[12.5px]">
        <ScanText className="size-3.5 text-primary" />
        <span><b>{on}</b> vùng che{list.length > on && <span className="text-muted-foreground"> · {list.length - on} đang tắt</span>}</span>
        <Button size="xs" variant="ghost" className="ml-auto" onClick={start} title="Quét lại (vùng tay vẫn giữ nếu thêm lại)"><RotateCw /> Quét lại</Button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Button size="sm" variant={editing ? "default" : "outline"} onClick={() => setEditing(!editing)}><Move /> {editing ? "Xong" : "Sửa khung"}</Button>
        <Button size="sm" variant="outline" disabled={!currentSpan} onClick={addManual} title="Thêm vùng che cho cảnh đang xem"><Plus /> Vùng cho cảnh này</Button>
      </div>
      {editing && <p className="-mt-1 text-[11px] text-muted-foreground">Phát / tua tới chỗ có chữ — khung hiện đúng lúc chữ xuất hiện, kéo để chỉnh.</p>}
      <div className="flex max-h-72 flex-col gap-2 overflow-y-auto pr-1">
        {groups.length === 0 && <p className="py-3 text-center text-[12px] text-muted-foreground">Không thấy chữ Trung trong các cảnh — thêm vùng tay nếu còn sót.</p>}
        {groups.map(({ sp, items }) => (
          <div key={sp.n} className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold tracking-wider text-muted-foreground uppercase">Cảnh {sp.n}</span>
            {items.map(({ r, i }) => (
              <div key={i} className={cn("group flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11.5px]", r.off && "opacity-50")}>
                <button className="flex min-w-0 flex-1 items-center gap-1.5 text-left hover:text-primary" onClick={() => onJump(Math.max(r.t_start, sp.srcStart) + Math.min(0.5, (r.t_end - r.t_start) / 2))} title="Xem đoạn này">
                  <span className="font-mono tabular">{fmtClock(r.t_start)}–{fmtClock(r.t_end)}</span>
                  <span className="truncate text-muted-foreground">· {r.manual ? "vùng tay" : "chữ"} {where(r.box)}</span>
                </button>
                <Button size="icon-xs" variant="ghost" title={r.off ? "Bật lại" : "Không che vùng này"} onClick={() => toggle(i)}>{r.off ? <EyeOff /> : <Eye />}</Button>
                <Button size="icon-xs" variant="ghost" title="Xoá" onClick={() => onRegions(list.filter((_, j) => j !== i))}><Trash2 /></Button>
              </div>
            ))}
          </div>
        ))}
      </div>
      <button className="self-start text-[11px] text-muted-foreground hover:text-foreground hover:underline" onClick={() => { onRegions(null); setEditing(false) }}>
        Bỏ danh sách — để app tự quét lúc xuất
      </button>
    </div>
  )
}
