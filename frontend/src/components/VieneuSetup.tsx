import { Check, Download, Loader2, RotateCw, Trash2, X } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { confirmAction } from "@/components/ConfirmHost"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { api } from "@/lib/api"
import type { VieneuStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Thẻ cài VieNeu (giọng offline) ở trang Giọng đọc: tải model một lần, theo dõi tiến trình, gỡ khi cần. */
export function VieneuSetup({ onChange }: { onChange: () => void }) {
  const [s, setS] = useState<VieneuStatus | null>(null)
  const load = useCallback(() => api.vieneu().then(setS).catch(() => {}), [])
  useEffect(() => { load() }, [load])
  // đang cài → hỏi trạng thái liên tục; xong thì làm mới danh sách giọng (giọng VieNeu chuyển sang "dùng được")
  useEffect(() => {
    if (!s?.running) return
    const t = setInterval(async () => {
      const n = await api.vieneu().catch(() => null)
      if (!n) return
      setS(n)
      if (!n.running) {
        onChange()
        if (n.installed) toast.success("VieNeu đã sẵn sàng", { description: "Giọng VieNeu dùng được ngay, chạy offline trên máy." })
        else if (n.error) toast.error("Cài VieNeu lỗi", { description: n.error.slice(0, 200) })
      }
    }, 1500)
    return () => clearInterval(t)
  }, [s?.running, onChange])

  if (!s) return null
  const act = (p: Promise<VieneuStatus>) => p.then(setS).catch((e) => toast.error((e as Error).message))
  const uninstall = async () => {
    if (await confirmAction({ title: "Gỡ VieNeu?", desc: "Xoá model và thư viện VieNeu (~1.2 GB). Giọng VieNeu sẽ tự đổi sang Edge TTS cho tới khi tải lại.", action: "Gỡ", danger: true }))
      act(api.vieneuUninstall()).then(onChange)
  }

  // Đã dùng được (cài qua app hoặc Model Pack cũ) → 1 dòng gọn
  if (!s.running && (s.installed || s.available) && !s.error) {
    return (
      <div className="flex items-center gap-2.5 rounded-xl border border-border bg-card px-4 py-2.5 text-[12.5px]">
        <Check className="size-4 shrink-0 text-success" />
        <span className="min-w-0 flex-1">
          <b>VieNeu</b> đã cài — giọng offline chạy trên CPU, không cần mạng.
          {s.info?.version && <span className="text-muted-foreground"> · bản {s.info.version}{s.info.size_mb ? ` · ${(s.info.size_mb / 1024).toFixed(1)} GB` : ""}</span>}
        </span>
        {s.installed && <Button size="sm" variant="ghost" onClick={uninstall}><Trash2 /> Gỡ</Button>}
      </div>
    )
  }

  const idx = s.steps.findIndex((x) => x.id === s.step)
  return (
    <div className={cn("flex flex-col gap-3 rounded-xl border bg-card p-4", s.error ? "border-destructive/40" : "border-primary/30")}>
      <div className="flex flex-wrap items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Download className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-semibold">Giọng VieNeu (offline, miễn phí)</p>
          <p className="text-[12px] text-muted-foreground">
            25 giọng có sẵn + 28 giọng VieNeu3 nhân bản từ giọng mẫu · chạy trên máy, không cần card màn hình, không giới hạn lượt.
            Tải một lần khoảng {(s.size_mb / 1024).toFixed(1)} GB (cần mạng, ~5–10 phút).
          </p>
        </div>
        {s.running
          ? <Button size="sm" variant="outline" onClick={() => act(api.vieneuCancel())}><X /> Huỷ</Button>
          : <Button size="sm" onClick={() => act(api.vieneuInstall())}>{s.error ? <><RotateCw /> Thử lại</> : <><Download /> Tải model VieNeu</>}</Button>}
      </div>
      {(s.running || s.error) && (
        <>
          <div className="flex items-center gap-1.5 text-[11.5px]">
            {s.steps.map((st, i) => (
              <span key={st.id} className={cn("flex items-center gap-1 rounded-md px-2 py-0.5",
                i < idx || s.step === "done" ? "text-success" : i === idx ? (s.error ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary") : "text-muted-foreground")}>
                {i < idx ? <Check className="size-3" /> : i === idx && s.running ? <Loader2 className="size-3 animate-spin" /> : <span className="text-[10px]">{i + 1}</span>}
                {st.label}
              </span>
            ))}
            {s.running && <span className="ml-auto font-mono text-muted-foreground">{s.progress}%</span>}
          </div>
          {s.running && <Progress value={s.progress} />}
          <p className={cn("truncate font-mono text-[11px]", s.error ? "text-destructive" : "text-muted-foreground")} title={s.message}>{s.message}</p>
          {s.error && <pre className="max-h-32 overflow-auto rounded-md bg-muted/50 p-2 text-[11px] whitespace-pre-wrap text-muted-foreground">{s.error}</pre>}
        </>
      )}
    </div>
  )
}
