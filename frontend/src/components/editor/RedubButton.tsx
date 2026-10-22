import { Loader2, Mic2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { ToggleRow } from "@/components/common"
import { VoiceSelect } from "@/components/VoiceSelect"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Slider } from "@/components/ui/slider"
import { api } from "@/lib/api"
import type { JobDetail } from "@/lib/types"

/** Dịch phụ đề đã xong → lồng tiếng Việt từ bản dịch có sẵn (không chạy lại Whisper / dịch). */
export function RedubButton({ job }: { job: JobDetail }) {
  const { openJob } = useStore()
  const [open, setOpen] = useState(false)
  const [voice, setVoice] = useState(String(job.config.voice ?? ""))
  const [byGender, setByGender] = useState(!!job.config.dub_by_gender)
  const [female, setFemale] = useState(String(job.config.voice_female ?? ""))
  const [level, setLevel] = useState(Number(job.config.dub_orig_volume ?? 20))
  const [busy, setBusy] = useState(false)
  const dubbed = !!job.config.dub_voice
  const cast = job.result.cast ?? []
  // giọng từng nhân vật (lần lồng tiếng trước) — đổi được từng người
  const [cv, setCv] = useState<Record<string, string>>(() => Object.fromEntries(cast.map((c) => [String(c.id), c.voice])))
  // đổi giọng chính nam / nữ → nhân vật đang dùng giọng chính cũ đổi theo
  const changeBase = (old: string, next: string, set: (v: string) => void) => {
    set(next)
    setCv((m) => Object.fromEntries(Object.entries(m).map(([k, v]) => [k, v === old ? next : v])))
  }

  const go = async () => {
    setBusy(true)
    try {
      const n = await api.redub(job.id, { voice, voice_female: byGender ? female : "", dub_by_gender: byGender && !!female, dub_orig_volume: level,
        char_voices: byGender ? cv : {} })
      toast.success("Đang lồng tiếng — dùng lại bản dịch, dừng cho bạn xem câu dài trước khi đọc", { description: n.title })
      setOpen(false)
      openJob(n.id)
    } catch (e) { toast.error("Không lồng tiếng được", { description: (e as Error).message }) }
    finally { setBusy(false) }
  }

  return (
    <>
      <Button size="sm" variant={dubbed ? "outline" : "default"} onClick={() => setOpen(true)}
        title="Lồng tiếng Việt cho video này từ bản dịch đã có — không chạy lại Whisper / dịch">
        <Mic2 /> {dubbed ? "Lồng tiếng lại" : "Lồng tiếng"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{dubbed ? "Lồng tiếng lại" : "Lồng tiếng Việt"}</DialogTitle>
            <DialogDescription>
              Dùng lại bản dịch {job.scenes.length} dòng của video này, đọc từng câu đúng lúc câu thoại gốc (giữ nguyên thời gian video).
              Không chạy lại Whisper / dịch. Video cũ giữ nguyên.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            {byGender && <p className="-mb-1 text-xs font-medium text-muted-foreground">Giọng cho nhân vật nam</p>}
            <VoiceSelect value={voice} onChange={(v) => changeBase(voice, v, setVoice)} />
            <ToggleRow label="Giọng theo nhân vật nam / nữ" checked={byGender} onChange={setByGender}
              desc="Tự nhận câu giọng nữ trong video gốc và đọc bằng giọng nữ bạn chọn." />
            {byGender && <>
              <p className="-mb-1 text-xs font-medium text-muted-foreground">Giọng cho nhân vật nữ</p>
              <VoiceSelect value={female} onChange={(v) => changeBase(female, v, setFemale)} />
            </>}
            {byGender && cast.length > 0 && (
              <div className="flex flex-col gap-2 rounded-lg border p-3">
                <div>
                  <p className="text-sm font-medium">Giọng từng nhân vật</p>
                  <p className="text-xs text-muted-foreground">AI đã nhận ra {cast.length} nhân vật ở lần lồng tiếng trước — chọn giọng riêng cho từng người. Giữ nguyên phân vai, không phân tích lại.</p>
                </div>
                {cast.map((c) => (
                  <div key={c.id} className="flex flex-col gap-1.5 border-t pt-2 first:border-t-0 first:pt-0">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-medium">{c.name}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${c.gender === "female" ? "bg-pink-500/15 text-pink-600 dark:text-pink-300" : "bg-sky-500/15 text-sky-600 dark:text-sky-300"}`}>
                        {c.gender === "female" ? "Nữ" : "Nam"}
                      </span>
                      <span className="text-xs text-muted-foreground">{c.count} câu</span>
                    </div>
                    {c.samples[0] && <p className="truncate text-xs italic text-muted-foreground" title={c.samples.join("\n")}>“{c.samples[0]}”</p>}
                    <VoiceSelect value={cv[String(c.id)] ?? c.voice} onChange={(v) => setCv((m) => ({ ...m, [String(c.id)]: v }))} />
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-col gap-2">
              <span className="text-xs text-muted-foreground">Tiếng gốc khi có lời Việt: <b className="text-foreground">{level}%</b></span>
              <Slider value={[level]} min={0} max={60} step={5} onValueChange={([v]) => setLevel(v)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Thôi</Button>
            <Button onClick={go} disabled={busy || !voice || (byGender && !female)}>{busy ? <Loader2 className="animate-spin" /> : <Mic2 />} Lồng tiếng</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
