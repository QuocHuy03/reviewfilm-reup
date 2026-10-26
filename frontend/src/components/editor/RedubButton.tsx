import { Loader2, Mic2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { ToggleRow } from "@/components/common"
import { VieneuFx, VoiceSelect, isVieneu } from "@/components/VoiceSelect"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Slider } from "@/components/ui/slider"
import { api } from "@/lib/api"
import type { JobDetail } from "@/lib/types"

/** Dịch phụ đề đã xong → lồng tiếng Việt từ bản dịch có sẵn (không chạy lại Whisper / dịch). */
export function RedubButton({ job }: { job: JobDetail }) {
  const { openJob, voices } = useStore()
  const [open, setOpen] = useState(false)
  const [voice, setVoice] = useState(String(job.config.voice ?? ""))
  const [byGender, setByGender] = useState(!!job.config.dub_by_gender)
  const [female, setFemale] = useState(String(job.config.voice_female ?? ""))
  const [level, setLevel] = useState(Number(job.config.dub_orig_volume ?? 20))
  const [busy, setBusy] = useState(false)
  const dubbed = !!job.config.dub_voice
  const cast = job.result.cast ?? []
  // giọng riêng từng nhân vật: CHỈ những nhân vật người dùng đã tự chọn (không lấy giọng app từng tự gán ở lần trước)
  const [cv, setCv] = useState<Record<string, string>>(() => ({ ...((job.config.char_voices as Record<string, string>) ?? {}) }))
  const twoVoices = byGender && !!female && female !== voice
  const voiceOf = (c: { id: number; gender: string }) => cv[String(c.id)] || (twoVoices && c.gender === "female" ? female : voice)
  const changeBase = (_old: string, next: string, set: (v: string) => void) => set(next)
  // rate / pitch giọng VieNeu — lấy đúng như lúc setup job
  const [fx, setFx] = useState({ vieneu_rate: Number(job.config.vieneu_rate ?? 0) || 0, vieneu_pitch: Number(job.config.vieneu_pitch ?? 0) || 0 })
  const vn = (label: string) => isVieneu(voices.find((v) => v.label === label)?.id)
  const anyVieneu = vn(voice) || (twoVoices && vn(female)) || cast.some((c) => vn(voiceOf(c)))

  const go = async () => {
    setBusy(true)
    try {
      const n = await api.redub(job.id, { voice, voice_female: byGender ? female : "", dub_by_gender: byGender && !!female, dub_orig_volume: level,
        char_voices: cv, ...fx })
      toast.success("Đang phân tích nhân vật — app sẽ dừng ở bước Duyệt kịch bản theo vai để bạn kiểm tra vai & giọng trước khi lồng tiếng", { description: n.title })
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
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{dubbed ? "Lồng tiếng lại" : "Lồng tiếng Việt"}</DialogTitle>
            <DialogDescription>
              Dùng lại bản dịch {job.scenes.length} dòng của video này (không chạy lại Whisper / dịch, video cũ giữ nguyên).
              Các bước: phân tích nhân vật → dừng ở <b>Duyệt kịch bản theo vai</b> để bạn kiểm tra ai nói câu nào & chọn giọng từng nhân vật → rồi mới lồng tiếng.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <ToggleRow label="Giọng riêng cho nhân vật nam / nữ" checked={byGender} onChange={setByGender}
              desc={byGender ? "Nhân vật nam đọc giọng nam, nữ đọc giọng nữ — đổi riêng từng nhân vật bên dưới." : "Tắt: 1 giọng cho mọi nhân vật, đúng giọng bạn chọn — đổi riêng từng nhân vật bên dưới."} />
            <div className={byGender ? "grid gap-4 sm:grid-cols-2" : "flex flex-col gap-2"}>
              <div className="flex flex-col gap-1.5">
                <p className="text-xs font-medium text-muted-foreground">{byGender ? "Giọng cho nhân vật nam" : "Giọng đọc"}</p>
                <VoiceSelect value={voice} onChange={(v) => changeBase(voice, v, setVoice)} fx={fx} />
              </div>
              {byGender && (
                <div className="flex flex-col gap-1.5">
                  <p className="text-xs font-medium text-muted-foreground">Giọng cho nhân vật nữ</p>
                  <VoiceSelect value={female} onChange={(v) => changeBase(female, v, setFemale)} fx={fx} />
                </div>
              )}
            </div>
            {anyVieneu && <VieneuFx value={fx} onChange={(p) => setFx((f) => ({ ...f, ...p }))} />}
            {cast.length > 0 && (
              <div className="flex flex-col gap-2 rounded-lg border p-3">
                <div>
                  <p className="text-sm font-medium">Giọng từng nhân vật</p>
                  <p className="text-xs text-muted-foreground">AI đã nhận ra {cast.length} nhân vật ở lần lồng tiếng trước — chọn giọng riêng cho từng người (xem lại được ở bước duyệt).</p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                {cast.map((c) => (
                  <div key={c.id} className="flex min-w-0 flex-col gap-1.5 rounded-md border p-2.5">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-medium">{c.name}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${c.gender === "female" ? "bg-pink-500/15 text-pink-600 dark:text-pink-300" : "bg-sky-500/15 text-sky-600 dark:text-sky-300"}`}>
                        {c.gender === "female" ? "Nữ" : "Nam"}
                      </span>
                      <span className="text-xs text-muted-foreground">{c.count} câu</span>
                    </div>
                    {c.samples[0] && <p className="truncate text-xs italic text-muted-foreground" title={c.samples.join("\n")}>“{c.samples[0]}”</p>}
                    <VoiceSelect value={voiceOf(c)} onChange={(v) => setCv((m) => ({ ...m, [String(c.id)]: v }))} fx={fx} />
                  </div>
                ))}
                </div>
              </div>
            )}
            <div className="flex flex-col gap-2">
              <span className="text-xs text-muted-foreground">Tiếng gốc khi có lời Việt: <b className="text-foreground">{level}%</b></span>
              <Slider value={[level]} min={0} max={60} step={5} onValueChange={([v]) => setLevel(v)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Thôi</Button>
            <Button onClick={go} disabled={busy || !voice}>{busy ? <Loader2 className="animate-spin" /> : <Mic2 />} Phân tích & duyệt vai</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
