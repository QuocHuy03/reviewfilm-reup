import { Loader2, PencilLine } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import type { JobDetail } from "@/lib/types"

/** Dịch phụ đề đã xong → mở lại bước sửa bản dịch (giữ nguyên cấu hình) rồi dựng lại video theo bản đã sửa. */
export function ResubButton({ job }: { job: JobDetail }) {
  const { openJob } = useStore()
  const [busy, setBusy] = useState(false)
  const go = async () => {
    setBusy(true)
    try {
      const n = await api.resub(job.id)
      toast.success("Đã mở lại bản dịch — sửa xong bấm Xác nhận để dựng lại video")
      openJob(n.id)
    } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Button size="sm" variant="outline" disabled={busy} onClick={go}
      title="Sửa lại bản dịch / phụ đề (Tìm & thay, Từ điển…) rồi dựng lại video — không dịch lại từ đầu">
      {busy ? <Loader2 className="animate-spin" /> : <PencilLine />} Sửa phụ đề
    </Button>
  )
}
