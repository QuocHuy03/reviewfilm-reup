import { AlertTriangle, Check, KeyRound, Loader2, Mars, Package, Pause, Play, Search, Sparkles, Star, Venus } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Segmented, VnFlag } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { useAudio } from "@/hooks/useAudio"
import { api, mediaUrl } from "@/lib/api"
import type { Voice } from "@/lib/types"
import { cn } from "@/lib/utils"

type Gender = "all" | "male" | "female"

export function VoicesPage() {
  const { voices, settings, setSettings, go } = useStore()
  const [onlyReady, setOnlyReady] = useState(true)
  const { play, playing } = useAudio()
  const [group, setGroup] = useState("Tất cả")
  const [gender, setGender] = useState<Gender>("all")
  const [q, setQ] = useState("")
  const [text, setText] = useState("Xin chào các bạn, hôm nay chúng ta sẽ cùng xem một bộ phim cực kỳ hấp dẫn.")
  const [busy, setBusy] = useState<string | null>(null)
  const [generated, setGenerated] = useState<Record<string, string>>({})

  // Tập giọng đang xét: mặc định chỉ giọng dùng được ngay; bật công tắc để xem cả giọng cần key / cần cài thêm
  const pool = useMemo(() => (onlyReady ? voices.filter((v) => v.available) : voices), [voices, onlyReady])
  const groups = ["Tất cả", ...Array.from(new Set(pool.map((v) => v.group)))]
  const activeGroup = groups.includes(group) ? group : "Tất cả"
  const list = useMemo(() => pool.filter((v) =>
    (activeGroup === "Tất cả" || v.group === activeGroup) && (gender === "all" || v.gender === gender) &&
    v.label.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => Number(b.available) - Number(a.available)), [pool, activeGroup, gender, q])
  // Số lượng trên bộ lọc: nhóm đếm theo giới tính đang chọn, giới tính đếm theo nhóm đang chọn
  const inGroup = (g: string) => pool.filter((v) => (g === "Tất cả" || v.group === g) && (gender === "all" || v.gender === gender)).length
  const inGender = (x: Gender) => pool.filter((v) => (activeGroup === "Tất cả" || v.group === activeGroup) && (x === "all" || v.gender === x)).length
  const ready = voices.filter((v) => v.available).length
  const defaultVoice = voices.find((v) => v.label === settings?.voice)

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
      {defaultVoice && !defaultVoice.available && (
        <div className="flex items-center gap-2.5 rounded-xl border border-warning/40 bg-warning/5 px-4 py-2.5 text-[12.5px]">
          <AlertTriangle className="size-4 shrink-0 text-warning" />
          <span className="min-w-0 flex-1">
            Giọng mặc định <b>{defaultVoice.label.split(" — ")[1] ?? defaultVoice.label}</b> chưa dùng được trên máy này ({defaultVoice.need}) —
            các video mới đang tự đọc bằng <b>Edge TTS</b>. Chọn một giọng dùng được làm mặc định, hoặc thêm key.
          </span>
          {defaultVoice.tier === "key" && <Button size="sm" variant="outline" onClick={() => go("settings")}><KeyRound /> Thêm key</Button>}
        </div>
      )}
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]">
          <span className="flex items-center gap-1.5 font-semibold"><VnFlag /> {voices.length} giọng tiếng Việt</span>
          <span className="text-success">{ready} dùng được ngay</span>
          {voices.length - ready > 0 && <span className="text-muted-foreground">{voices.length - ready} cần cài thêm / key</span>}
          <span className="text-muted-foreground">{new Set(voices.map((v) => v.group)).size} nhóm</span>
          <label className="ml-auto flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
            Chỉ giọng dùng được ngay <Switch checked={onlyReady} onCheckedChange={setOnlyReady} />
          </label>
          <span className="text-xs text-muted-foreground">· đang hiện {list.length}</span>
        </div>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className="text-[13px]" placeholder="Câu dùng để tạo thử giọng" />
        <div className="flex flex-wrap items-center gap-2">
          <Segmented value={activeGroup} onChange={setGroup} items={groups.map((g) => ({ value: g, label: `${g} · ${inGroup(g)}` }))} />
          <Segmented value={gender} onChange={setGender} items={[
            { value: "all", label: `Tất cả · ${inGender("all")}` },
            { value: "male", label: `Nam · ${inGender("male")}`, icon: <Mars /> },
            { value: "female", label: `Nữ · ${inGender("female")}`, icon: <Venus /> }]} />
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
                  <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    {v.group}
                    {v.gender !== "neutral" && <span>· {v.gender === "male" ? "Nam" : "Nữ"}</span>}
                  </p>
                  <TierBadge v={v} onFix={() => go("settings")} />
                </div>
                {isDefault && <Star className="size-3.5 fill-primary text-primary" />}
              </div>
              <div className="flex gap-1.5">
                <Button variant="outline" size="sm" className="flex-1" disabled={!sample} onClick={() => play(sample)} title={sample ? "" : "Chưa có mẫu dựng sẵn"}>
                  {playing === sample && sample ? <Pause /> : <Play />} Mẫu
                </Button>
                <Button variant="outline" size="sm" className="flex-1" disabled={busy !== null || !v.available}
                  onClick={() => (gen ? play(gen) : generate(v))} title={v.available ? "Đọc câu ở trên bằng giọng này" : v.need}>
                  {busy === v.label ? <Loader2 className="animate-spin" /> : playing === gen && gen ? <Pause /> : <Sparkles />} {gen ? "Nghe" : "Tạo thử"}
                </Button>
                <Button variant={isDefault ? "secondary" : "ghost"} size="icon-sm" title={isDefault ? "Đang là giọng mặc định" : "Đặt làm mặc định"}
                  disabled={!v.available && !isDefault} onClick={() => setDefault(v)}><Check /></Button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Trạng thái giọng: Miễn phí · Có key · Cần key (bấm → Cài đặt) · Cần cài thêm. */
function TierBadge({ v, onFix }: { v: Voice; onFix: () => void }) {
  if (v.available)
    return <p className="text-[10.5px] text-success">{v.tier === "key" ? "Đã có key · dùng được" : "Miễn phí · dùng được ngay"}</p>
  if (v.tier === "key")
    return (
      <button onClick={onFix} className="flex items-center gap-1 text-[10.5px] text-warning hover:underline" title={v.need}>
        <KeyRound className="size-3" /> Cần API key — mở Cài đặt
      </button>
    )
  return <p className="flex items-center gap-1 truncate text-[10.5px] text-muted-foreground" title={v.need}><Package className="size-3 shrink-0" /> Cần cài thêm trên máy</p>
}
