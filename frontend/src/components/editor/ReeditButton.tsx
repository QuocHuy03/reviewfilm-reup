import { Loader2, Wand2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Segmented } from "@/components/common"
import { VoiceSelect } from "@/components/VoiceSelect"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { api } from "@/lib/api"
import type { JobDetail } from "@/lib/types"

/**
 * "Mở lại hậu kỳ": job mới dùng lại kịch bản đã duyệt → đọc lại giọng (có thể đổi giọng) → dừng ở Xem trước.
 * Bỏ qua Whisper + Vision AI + viết kịch bản.
 */
export function ReeditButton({ job, label = "Mở lại hậu kỳ" }: { job: JobDetail; label?: string }) {
  const { openJob } = useStore()
  const oldVoice = String(job.config.voice ?? "")
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<"keep" | "change">("keep")
  const [voice, setVoice] = useState(oldVoice)
  const [busy, setBusy] = useState(false)

  const go = async () => {
    setBusy(true)
    try {
      const n = await api.reedit(job.id, mode === "change" && voice !== oldVoice ? voice : undefined)
      toast.success("Đang mở lại hậu kỳ — đọc lại giọng rồi dừng ở bước Xem trước", { description: n.title })
      setOpen(false)
      openJob(n.id)
    } catch (e) { toast.error("Không mở lại được", { description: (e as Error).message }) }
    finally { setBusy(false) }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)} title="Sửa tiếp & xuất lại — dùng lại kịch bản, không chạy lại Whisper / AI">
        <Wand2 /> {label}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Mở lại hậu kỳ</DialogTitle>
            <DialogDescription>
              Dùng lại kịch bản {job.scenes.filter((s) => !s.excluded).length} cảnh của video này, đọc lại giọng rồi dừng ở bước
              <b> Xem trước</b> để bạn sửa lời, đổi thứ tự, chỉnh nhạc và xuất lại. Không chạy lại Whisper / AI viết kịch bản.
              Video cũ giữ nguyên.
            </DialogDescription>
          </DialogHeader>
          <Segmented value={mode} onChange={setMode} items={[{ value: "keep", label: "Giữ giọng cũ" }, { value: "change", label: "Đổi giọng" }]} />
          {mode === "change" && <VoiceSelect value={voice} onChange={setVoice}
            fx={{ vieneu_rate: Number(job.config.vieneu_rate ?? 0) || 0, vieneu_pitch: Number(job.config.vieneu_pitch ?? 0) || 0 }} />}
          {mode === "keep" && <p className="text-xs text-muted-foreground">Giọng: <b>{oldVoice.split(" — ")[1] ?? oldVoice}</b></p>}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Thôi</Button>
            <Button onClick={go} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Wand2 />} Mở lại</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
