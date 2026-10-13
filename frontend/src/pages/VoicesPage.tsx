import { Check, Loader2, Mars, Pause, Play, Search, Sparkles, Star, Venus } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Segmented } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useAudio } from "@/hooks/useAudio"
import { api, mediaUrl } from "@/lib/api"
import type { Voice } from "@/lib/types"
import { cn } from "@/lib/utils"

type Gender = "all" | "male" | "female"

export function VoicesPage() {
  const { voices, settings, setSettings } = useStore()
  const { play, playing } = useAudio()
  const [group, setGroup] = useState("Tất cả")
  const [gender, setGender] = useState<Gender>("all")
  const [q, setQ] = useState("")
  const [text, setText] = useState("Xin chào các bạn, hôm nay chúng ta sẽ cùng xem một bộ phim cực kỳ hấp dẫn.")
  const [busy, setBusy] = useState<string | null>(null)
  const [generated, setGenerated] = useState<Record<string, string>>({})

  const groups = ["Tất cả", ...Array.from(new Set(voices.map((v) => v.group)))]
  const list = useMemo(() => voices.filter((v) =>
    (group === "Tất cả" || v.group === group) && (gender === "all" || v.gender === gender) &&
    v.label.toLowerCase().includes(q.toLowerCase())), [voices, group, gender, q])

  const generate = async (v: Voice) => {
    setBusy(v.label)
    try {
      const r = await api.testVoice(v.label, text)
      const url = mediaUrl(r.path)
      setGenerated((g) => ({ ...g, [v.label]: url }))
      play(url)
    } catch (e) { toast.error((e as Error).message) } finally { setBusy(null) }
  }

  const setDefault = async (v: Voice) => {
    const s = await api.saveSettings({ voice: v.label }); setSettings(s); toast.success(`Giọng mặc định: ${v.label}`)
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className="text-[13px]" placeholder="Câu dùng để tạo thử giọng" />
        <div className="flex flex-wrap items-center gap-2">
          <Segmented value={group} onChange={setGroup} items={groups.map((g) => ({ value: g, label: g }))} />
          <Segmented value={gender} onChange={setGender} items={[
            { value: "all", label: "Tất cả" }, { value: "male", label: "Nam", icon: <Mars /> }, { value: "female", label: "Nữ", icon: <Venus /> }]} />
          <div className="relative ml-auto w-60">
            <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm giọng…" className="pl-8" />
          </div>
        </div>
      </div>

      <div className="grid min-h-0 grid-cols-3 content-start gap-3 overflow-y-auto pb-6 xl:grid-cols-4 2xl:grid-cols-5">
        {list.map((v) => {
          const isDefault = settings?.voice === v.label
          const sample = v.sample ? mediaUrl(v.sample) : ""
          const gen = generated[v.label]
          const name = v.label.split(" — ")[1] ?? v.label
          return (
            <div key={v.label} className={cn("flex flex-col gap-3 rounded-xl border bg-card p-3.5 transition", isDefault ? "border-primary/60 ring-1 ring-primary/30" : "border-border hover:border-foreground/20")}>
              <div className="flex items-start gap-2.5">
                <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                  v.gender === "neutral" ? "bg-muted text-muted-foreground" : "bg-primary/10 text-primary")}>
                  {name.replace(/[^\p{L}]/gu, "").slice(0, 1).toUpperCase() || "?"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium" title={v.label}>{name}</p>
                  <p className="text-[11px] text-muted-foreground">{v.group}</p>
                  {v.available
                    ? <p className="text-[10.5px] text-success">Dùng được</p>
                    : <p className="truncate text-[10.5px] text-warning" title={v.need}>{v.need}</p>}
                </div>
                {isDefault && <Star className="size-3.5 fill-primary text-primary" />}
              </div>
              <div className="flex gap-1.5">
                <Button variant="outline" size="sm" className="flex-1" disabled={!sample} onClick={() => play(sample)} title={sample ? "" : "Chưa có mẫu dựng sẵn"}>
                  {playing === sample && sample ? <Pause /> : <Play />} Mẫu
                </Button>
                <Button variant="outline" size="sm" className="flex-1" disabled={busy !== null || v.clone}
                  onClick={() => (gen ? play(gen) : generate(v))} title={v.clone ? "Giọng clone cần file mẫu — dùng ở trang Tạo video" : ""}>
                  {busy === v.label ? <Loader2 className="animate-spin" /> : playing === gen && gen ? <Pause /> : <Sparkles />} {gen ? "Nghe" : "Tạo thử"}
                </Button>
                <Button variant={isDefault ? "secondary" : "ghost"} size="icon-sm" title="Đặt làm mặc định" onClick={() => setDefault(v)}><Check /></Button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
