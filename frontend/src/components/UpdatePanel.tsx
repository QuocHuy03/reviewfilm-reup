import { CheckCircle2, Download, Loader2, RefreshCw, RotateCw, TriangleAlert } from "lucide-react"
import { Section } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { useUpdate } from "@/hooks/useUpdate"
import type { UpdateState } from "@/types/electron"

const LABEL: Record<UpdateState["status"], string> = {
  dev: "Bản chạy từ mã nguồn — tự cập nhật chỉ có ở bản cài đặt",
  idle: "Chưa kiểm tra",
  checking: "Đang kiểm tra bản mới…",
  available: "Có bản mới — đang chuẩn bị tải",
  downloading: "Đang tải bản mới",
  downloaded: "Đã tải xong — khởi động lại để cập nhật",
  none: "Bạn đang dùng bản mới nhất",
  error: "Không kiểm tra được bản mới",
}

export function UpdatePanel() {
  const { state, available, check, install } = useUpdate()
  if (!available || !state) return null
  const busy = state.status === "checking" || state.status === "downloading" || state.status === "available"

  return (
    <Section title="Cập nhật" icon={<Download />} desc={`Phiên bản hiện tại ${state.current}`}
      action={state.status === "downloaded" ? (
        <Button size="sm" onClick={() => install()}><RotateCw /> Khởi động lại & cập nhật</Button>
      ) : (
        <Button size="sm" variant="outline" disabled={busy || state.status === "dev"} onClick={() => check()}>
          {busy ? <Loader2 className="animate-spin" /> : <RefreshCw />} Kiểm tra
        </Button>
      )}>
      <div className="flex items-center gap-2 text-[13px]">
        {state.status === "none" && <CheckCircle2 className="size-4 text-success" />}
        {state.status === "error" && <TriangleAlert className="size-4 text-destructive" />}
        <span>{LABEL[state.status]}{state.version && state.status !== "none" ? ` · v${state.version}` : ""}</span>
      </div>
      {state.status === "downloading" && <Progress value={state.percent ?? 0} />}
      {state.status === "error" && state.error && <p className="text-xs text-muted-foreground">{state.error.slice(0, 300)}</p>}
      {state.notes && (state.status === "downloaded" || state.status === "downloading") && (
        <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-md bg-muted/50 p-2.5 text-xs text-muted-foreground">{state.notes}</pre>
      )}
      <p className="text-[11px] text-muted-foreground">App tự kiểm tra khi mở và mỗi 4 giờ. Cài đặt, API key và lịch sử job được giữ nguyên khi cập nhật.</p>
    </Section>
  )
}
