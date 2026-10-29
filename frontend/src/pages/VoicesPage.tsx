import { AlertTriangle, Check, KeyRound, ListMusic, Loader2, Mars, Package, Pause, Play, Search, Sparkles, Square, Star, Venus, Wand2 } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Segmented, VnFlag } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { VieneuSetup } from "@/components/VieneuSetup"
import { useAudio } from "@/hooks/useAudio"
import { api, mediaUrl } from "@/lib/api"
import type { Voice } from "@/lib/types"
import { DEMO_TEXT, LANGS, voiceFits } from "@/lib/langs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/utils"

type Gender = "all" | "male" | "female"

export function VoicesPage() {
  const { voices: allVoices, settings, setSettings, go, refreshSystem } = useStore()
  // ngôn ngữ giọng đọc: mặc định tiếng Việt; đổi sang ngôn ngữ khác để nghe / chọn giọng lồng tiếng nước ngoài
  const [lang, setLang] = useState("vi")
  const voices = useMemo(() => allVoices.filter((v) => voiceFits(v, lang)), [allVoices, lang])
  const langCount = (c: string) => allVoices.filter((v) => voiceFits(v, c)).length
  const [onlyReady, setOnlyReady] = useState(true)
  const { play, playing, playList, queueKey, stop } = useAudio()
  const [group, setGroup] = useState("Tất cả")
  const [gender, setGender] = useState<Gender>("all")
  const [q, setQ] = useState("")
  const [text, setText] = useState(DEMO_TEXT.vi)
  // đổi ngôn ngữ → câu thử đổi theo (nếu chưa tự sửa câu)
  const changeLang = (c: string) => { if (Object.values(DEMO_TEXT).includes(text)) setText(DEMO_TEXT[c] ?? DEMO_TEXT.en); setLang(c); setGroup("Tất cả") }
  const [busy, setBusy] = useState<string | null>(null)
  const [generated, setGenerated] = useState<Record<string, string>>({})
  // Tạo thử hàng loạt: lần lượt từng giọng (máy chủ chỉ tạo 1 giọng thử một lúc), huỷ được giữa chừng
  const [batch, setBatch] = useState<{ done: number; total: number; failed: number } | null>(null)
  const cancelBatch = useRef(false)
  // đổi câu thử → bản đã tạo không còn đúng câu, tạo lại khi bấm
  useEffect(() => { setGenerated({}) }, [text])

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

  /** Tạo câu thử cho mọi giọng đang hiện (theo bộ lọc), bỏ qua giọng đã tạo với câu này. */
  const generateAll = async () => {
    const todo = list.filter((v) => v.available && !generated[v.label])
    if (!todo.length) { toast.info("Các giọng đang hiện đã có bản thử — bấm \"Nghe lần lượt\""); return }
    cancelBatch.current = false
    let failed = 0
    setBatch({ done: 0, total: todo.length, failed: 0 })
    for (const [k, v] of todo.entries()) {
      if (cancelBatch.current) break
      setBusy(v.label)
      try {
        const r = await api.testVoice(v.label, text)
        const url = mediaUrl(r.path)
        setGenerated((g) => ({ ...g, [v.label]: url }))
      } catch { failed++ }
      setBatch({ done: k + 1, total: todo.length, failed })
    }
    setBusy(null)
    setBatch(null)
    if (cancelBatch.current) toast("Đã dừng tạo thử")
    else toast.success(`Đã tạo thử ${todo.length - failed}/${todo.length} giọng`, {
      description: failed ? `${failed} giọng lỗi (thường do mạng / CapCut chặn) — bấm Tạo thử riêng từng giọng.` : "Bấm \"Nghe lần lượt\" để nghe nhanh từng giọng.",
    })
  }
  /** Phát lần lượt: bản đã tạo với câu ở trên, chưa có thì phát mẫu dựng sẵn. */
  const queueItems = list.map((v) => ({ key: v.label, url: generated[v.label] || (v.sample ? mediaUrl(v.sample) : "") })).filter((x) => x.url)
  const playAll = () => {
    if (queueKey) { stop(); return }
    if (!queueItems.length) { toast.info("Chưa có bản nghe — bấm \"Tạo thử tất cả\" trước"); return }
    playList(queueItems)
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
      <VieneuSetup onChange={refreshSystem} />
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]">
          <Select value={lang} onValueChange={changeLang}>
            <SelectTrigger className="h-8 w-auto gap-1.5 font-semibold">{lang === "vi" && <VnFlag />}<SelectValue /></SelectTrigger>
            <SelectContent className="max-h-80">
              {LANGS.map((l) => <SelectItem key={l.code} value={l.code}>{l.name} · {langCount(l.code)} giọng</SelectItem>)}
            </SelectContent>
          </Select>
          <span className="font-semibold">{voices.length} giọng</span>
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
          <div className="ml-auto flex items-center gap-1.5">
            {batch ? (
              <Button size="sm" variant="outline" onClick={() => { cancelBatch.current = true }} title="Dừng tạo thử">
                <Loader2 className="animate-spin" /> Đang tạo {batch.done}/{batch.total} <Square className="size-3" />
              </Button>
            ) : (
              <Button size="sm" variant="outline" disabled={busy !== null || !list.some((v) => v.available)} onClick={generateAll}
                title="Đọc câu ở trên bằng mọi giọng đang hiện">
                <Wand2 /> Tạo thử tất cả
              </Button>
            )}
            <Button size="sm" variant={queueKey ? "default" : "outline"} onClick={playAll} disabled={!queueKey && !queueItems.length}
              title="Nghe lần lượt từng giọng đang hiện">
              {queueKey ? <><Square className="size-3" /> Dừng nghe</> : <><ListMusic /> Nghe lần lượt</>}
            </Button>
          </div>
          <div className="relative w-60">
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
            <div key={v.label} ref={queueKey === v.label ? (el) => el?.scrollIntoView({ block: "nearest", behavior: "smooth" }) : undefined}
              className={cn("flex flex-col gap-3 rounded-xl border bg-card p-3.5 transition",
                queueKey === v.label ? "border-primary ring-2 ring-primary/40" : isDefault ? "border-primary/60 ring-1 ring-primary/30" : "border-border hover:border-foreground/20")}>
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
                {queueKey === v.label && <span className="flex items-center gap-1 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground"><Play className="size-2.5 fill-current" /> Đang nghe</span>}
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
  return <p className="flex items-center gap-1 truncate text-[10.5px] text-muted-foreground" title={v.need}><Package className="size-3 shrink-0" /> {v.group.startsWith("VieNeu") ? "Cần tải model (thẻ trên cùng)" : "Cần cài thêm trên máy"}</p>
}
