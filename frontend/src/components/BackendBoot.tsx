import { Loader2, TriangleAlert } from "lucide-react"
import { usePythonStatus } from "@/hooks/useUpdate"

/** Màn chờ khi backend chưa lên — hiện tiến trình chuẩn bị Python (lần đầu có thể mất vài phút). */
export function BackendBoot() {
  const s = usePythonStatus()
  if (s?.phase === "error") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <TriangleAlert className="size-6 text-destructive" />
        <p className="text-sm font-medium">{s.message}</p>
        {s.detail && <pre className="max-w-xl whitespace-pre-wrap text-xs text-muted-foreground">{s.detail}</pre>}
      </div>
    )
  }
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-sm text-muted-foreground">
      <Loader2 className="size-5 animate-spin text-primary" />
      <span>{s && s.phase !== "ready" ? s.message : "Đang khởi động backend Python…"}</span>
      {s?.detail && <span className="max-w-xl truncate font-mono text-[11px]">{s.detail}</span>}
    </div>
  )
}
