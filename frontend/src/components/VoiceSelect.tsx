import { AlertTriangle, Loader2, Pause, Play, Sparkles } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { VnFlag } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useStore } from "@/app/store"
import { useAudio } from "@/hooks/useAudio"
import { api, mediaUrl } from "@/lib/api"

export function VoiceSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { voices } = useStore()
  const { play, playing } = useAudio()
  const [testing, setTesting] = useState(false)
  // Giọng dùng được ngay: theo nhóm (nhóm miễn phí trước). Giọng chưa dùng được: dồn xuống 1 mục cuối, làm mờ.
  const ready = voices.filter((v) => v.available)
  const notReady = voices.filter((v) => !v.available)
  const groups = Array.from(new Set(ready.map((v) => v.group)))
    .sort((a, b) => Number(ready.some((v) => v.group === b && v.tier === "free")) - Number(ready.some((v) => v.group === a && v.tier === "free")))
  const current = voices.find((v) => v.label === value)

  const test = async () => {
    setTesting(true)
    try {
      const r = await api.testVoice(value)
      play(mediaUrl(r.path))
      if (r.engine && current && !current.id.startsWith(r.engine === "edge" ? "vi-VN" : r.engine))
        toast.info(`Đã phát bằng ${r.engine.toUpperCase()} (giọng gốc chưa sẵn sàng trên máy này)`)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-full"><SelectValue placeholder="Chọn giọng đọc" /></SelectTrigger>
        <SelectContent className="max-h-80">
          <div className="flex items-center gap-1.5 px-2 pt-1.5 pb-1 text-[11px] text-muted-foreground">
            <VnFlag /> {voices.length} giọng tiếng Việt · {ready.length} dùng được ngay
          </div>
          {groups.map((g) => {
            const items = ready.filter((v) => v.group === g)
            return (
              <SelectGroup key={g}>
                <SelectLabel className="flex items-center justify-between">
                  <span>{g}{items[0]?.tier === "free" && <span className="ml-1.5 text-success">miễn phí</span>}</span>
                  <span className="tabular font-normal">{items.length} giọng</span>
                </SelectLabel>
                {items.map((v) => <SelectItem key={v.label} value={v.label}>{v.label.split(" — ")[1] ?? v.label}</SelectItem>)}
              </SelectGroup>
            )
          })}
          {notReady.length > 0 && (
            <SelectGroup>
              <SelectLabel className="flex items-center justify-between">
                <span>Chưa dùng được trên máy này</span>
                <span className="tabular font-normal">{notReady.length} giọng</span>
              </SelectLabel>
              {notReady.map((v) => (
                <SelectItem key={v.label} value={v.label} className="opacity-60">
                  {v.label}<span className="ml-1.5 text-[10px] text-warning">· {v.tier === "key" ? "cần key" : "cần cài thêm"}</span>
                </SelectItem>
              ))}
            </SelectGroup>
          )}
        </SelectContent>
      </Select>
      {current && !current.available && (
        <p className="flex items-start gap-1.5 rounded-md border border-warning/30 bg-warning/5 px-2.5 py-1.5 text-[11px] text-warning">
          <AlertTriangle className="mt-0.5 size-3 shrink-0" />
          <span>{current.need} — nếu chưa có, khi tạo giọng app sẽ tự dùng <b>Edge TTS</b> thay thế.</span>
        </p>
      )}
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={!current?.sample} onClick={() => current && play(mediaUrl(current.sample))}
          title={current?.sample ? "Nghe mẫu có sẵn" : "Giọng này chưa có mẫu dựng sẵn"}>
          {playing && current?.sample && playing === mediaUrl(current.sample) ? <Pause /> : <Play />} Mẫu nhanh
        </Button>
        <Button variant="outline" size="sm" onClick={test} disabled={testing || !value}>
          {testing ? <Loader2 className="animate-spin" /> : <Sparkles />} Tạo thử
        </Button>
      </div>
    </div>
  )
}
