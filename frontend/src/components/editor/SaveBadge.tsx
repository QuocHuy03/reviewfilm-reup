import { Check, CloudOff, Loader2 } from "lucide-react"

/** Trạng thái tự lưu bản nháp — hiện cạnh tiêu đề bước đang sửa. */
export function SaveBadge({ state }: { state: "" | "saving" | "saved" | "error" }) {
  if (!state) return null
  if (state === "saving") return <span className="flex items-center gap-1 text-muted-foreground"><Loader2 className="size-3 animate-spin" /> Đang lưu…</span>
  if (state === "error") return <span className="flex items-center gap-1 text-warning" title="Không lưu được bản nháp — chỉnh sửa vẫn còn trên màn hình"><CloudOff className="size-3" /> Chưa lưu</span>
  return <span className="flex items-center gap-1 text-muted-foreground"><Check className="size-3" /> Đã lưu nháp</span>
}
