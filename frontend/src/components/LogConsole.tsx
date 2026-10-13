import { ArrowDownToLine, Copy } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import type { LogLine } from "@/lib/types"
import { cn } from "@/lib/utils"

const TAG_CLS: Record<LogLine["tag"], string> = {
  err: "text-destructive",
  warn: "text-warning",
  ok: "text-success",
  info: "text-primary",
  step: "text-muted-foreground",
}

export function LogConsole({ logs, className }: { logs: LogLine[]; className?: string }) {
  const box = useRef<HTMLDivElement>(null)
  const [follow, setFollow] = useState(true)

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [logs, follow])

  return (
    <div className={cn("flex min-h-0 flex-col rounded-xl border border-border bg-console", className)}>
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="text-xs font-medium">Nhật ký</span>
        <span className="tabular text-[11px] text-muted-foreground">{logs.length} dòng</span>
        <div className="flex-1" />
        <Button variant="ghost" size="icon-sm" title="Sao chép" onClick={() => {
          navigator.clipboard.writeText(logs.map((l) => l.msg).join("\n")); toast.success("Đã sao chép nhật ký")
        }}><Copy /></Button>
        <Button variant={follow ? "secondary" : "ghost"} size="icon-sm" title="Tự cuộn" onClick={() => setFollow(!follow)}>
          <ArrowDownToLine />
        </Button>
      </div>
      <div ref={box} onWheel={(e) => { if (e.deltaY < 0) setFollow(false) }}
        className="min-h-0 flex-1 overflow-auto px-3 py-2 font-mono text-[11.5px] leading-[1.65]">
        {logs.length === 0 && <p className="text-muted-foreground">Chưa có log.</p>}
        {logs.map((l, i) => (
          <div key={i} className={cn("break-words whitespace-pre-wrap", TAG_CLS[l.tag] ?? TAG_CLS.step)}>
            <span className="mr-2 text-muted-foreground/50 select-none">
              {new Date(l.t * 1000).toLocaleTimeString("vi-VN", { hour12: false })}
            </span>
            {l.msg}
          </div>
        ))}
      </div>
    </div>
  )
}
