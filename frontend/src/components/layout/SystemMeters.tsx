import { useEffect, useState } from "react"
import type { Usage } from "@/types/electron"
import { cn } from "@/lib/utils"

const GB = 1024 ** 3

function Meter({ label, value, detail, title }: { label: string; value: number; detail: string; title: string }) {
  const tone = value >= 90 ? "bg-destructive" : value >= 75 ? "bg-warning" : "bg-primary"
  return (
    <div className="flex h-8 shrink-0 items-center gap-2 rounded-md border border-border px-2.5 whitespace-nowrap" title={title}>
      <span className="text-[10px] font-semibold tracking-wide text-muted-foreground">{label}</span>
      <span className="relative hidden h-1.5 w-10 overflow-hidden rounded-full bg-muted 2xl:block">
        <span className={cn("absolute inset-y-0 left-0 rounded-full transition-[width] duration-700", tone)} style={{ width: `${Math.min(100, value)}%` }} />
      </span>
      <span className="tabular min-w-[2.4rem] text-right text-[11px] font-medium text-foreground">{detail}</span>
    </div>
  )
}

/** CPU / RAM / GPU thời gian thực (lấy từ Electron, cập nhật mỗi 2 giây). */
export function SystemMeters() {
  const [u, setU] = useState<Usage | null>(null)

  useEffect(() => {
    if (!window.rf?.usage) return
    let alive = true
    const tick = () => window.rf!.usage().then((x) => alive && setU(x)).catch(() => {})
    tick()
    const t = setInterval(tick, 2000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  if (!u) return null
  const ramPct = Math.round((u.ramUsed / u.ramTotal) * 100)
  return (
    <div className="no-drag hidden shrink-0 items-center gap-1.5 xl:flex">
      <Meter label="CPU" value={u.cpu} detail={`${u.cpu}%`} title={`CPU đang dùng ${u.cpu}%`} />
      <Meter label="RAM" value={ramPct} detail={`${(u.ramUsed / GB).toFixed(1)}G`}
        title={`RAM ${(u.ramUsed / GB).toFixed(1)} / ${(u.ramTotal / GB).toFixed(1)} GB (${ramPct}%)`} />
      {u.gpu && (
        <Meter label="GPU" value={u.gpu.util} detail={`${u.gpu.util}%`}
          title={`${u.gpu.name} — ${u.gpu.util}% · VRAM ${(u.gpu.memUsed / GB).toFixed(1)} / ${(u.gpu.memTotal / GB).toFixed(1)} GB`} />
      )}
    </div>
  )
}
