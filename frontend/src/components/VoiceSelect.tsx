import { AlertTriangle, Loader2, Play, Sparkles, Square, X } from "lucide-react"
import { Input } from "@/components/ui/input"
import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import { VnFlag } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useStore } from "@/app/store"
import { stopAllAudio, useAudio } from "@/hooks/useAudio"
import { api, mediaUrl } from "@/lib/api"

type VoiceFx = { vieneu_rate: number; vieneu_pitch: number }

const DEMO_KEY = "rf.voice.demoText"

export const isVieneu =(id?: string) => !!id && id.startsWith("vieneu")

/** Ô số đi kèm thanh trượt: gõ tự do, Enter / rời ô thì làm tròn theo bước & kẹp trong [min, max]; ↑ ↓ tăng giảm 1 bước. */
function NumBox({ value, min, max, step, unit, onChange }: { value: number; min: number; max: number; step: number; unit: string; onChange: (v: number) => void }) {
  const [text, setText] = useState(String(value))
  const [focus, setFocus] = useState(false)
  const clamp = (n: number) => Math.round(Math.round(Math.min(max, Math.max(min, n)) / step) * step * 100) / 100
  const commit = (raw: string) => {
    const n = Number(String(raw).trim().replace(",", ".").replace(/^[+]/, ""))
    const r = Number.isFinite(n) && String(raw).trim() !== "" ? clamp(n) : value
    setText(String(r))
    if (r !== value) onChange(r)
  }
  return (
    <div className="flex h-7 shrink-0 items-center rounded-md border border-input bg-background pr-2 focus-within:ring-2 focus-within:ring-ring/40">
      <input inputMode="decimal" value={focus ? text : `${value > 0 ? "+" : ""}${value}`} aria-label={unit}
        onFocus={(e) => { setFocus(true); setText(String(value)); const t = e.target; requestAnimationFrame(() => t.select()) }}
        onBlur={(e) => { setFocus(false); commit(e.target.value) }}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          const t = e.target as HTMLInputElement
          if (e.key === "Enter") { e.preventDefault(); t.blur() }
          else if (e.key === "Escape") { setText(String(value)); setFocus(false); t.blur() }
          else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
            e.preventDefault()
            const v = clamp((Number(text.replace(",", ".")) || value) + (e.key === "ArrowUp" ? step : -step))
            setText(String(v)); onChange(v)
          }
        }}
        className="tabular w-12 bg-transparent px-2 text-right text-xs outline-none" />
      <span className="text-[11px] text-muted-foreground">{unit}</span>
    </div>
  )
}

/** Tốc độ & cao độ giọng VieNeu (model không có sẵn — app chỉnh sau khi tạo giọng). Dùng chung cho mọi giọng VieNeu. */
export function VieneuFx({ value, onChange }: { value: VoiceFx; onChange: (p: Partial<VoiceFx>) => void }) {
  const rate = value.vieneu_rate || 0
  const pitch = value.vieneu_pitch || 0
  const row = (label: string, hint: string, v: number, min: number, max: number, step: number, unit: string, set: (n: number) => void) => (
    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-muted-foreground" title={hint}>{label}</span>
        <NumBox value={v} min={min} max={max} step={step} unit={unit} onChange={set} />
      </div>
      <Slider value={[v]} min={min} max={max} step={step} onValueChange={([n]) => set(n)} />
      <div className="tabular flex justify-between text-[10px] text-muted-foreground/70"><span>{min}</span><span>+{max}</span></div>
    </div>
  )
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">Chỉnh giọng VieNeu</span>
        <Button variant="ghost" size="sm" className={cn("h-6 px-2 text-[11px]", rate === 0 && pitch === 0 && "invisible")}
          onClick={() => onChange({ vieneu_rate: 0, vieneu_pitch: 0 })}>Mặc định</Button>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row sm:gap-5">
        {row("Tốc độ (rate)", "Nhanh / chậm, giữ nguyên cao độ. Từ -30% đến +50%.", rate, -30, 50, 1, "%", (n) => onChange({ vieneu_rate: n }))}
        {row("Cao độ (pitch)", "Dời cao độ giọng ± Hz (như Edge TTS), giữ nguyên tốc độ. Từ -50 đến +50 Hz.", pitch, -50, 50, 1, "Hz", (n) => onChange({ vieneu_pitch: n }))}
      </div>
    </div>
  )
}

export function VoiceSelect({ value, onChange, fx }: { value: string; onChange: (v: string) => void; fx?: VoiceFx }) {
  const { voices } = useStore()
  const { play, playing } = useAudio()
  const [testing, setTesting] = useState(false)
  const [testUrl, setTestUrl] = useState("")           // file "Tạo thử" gần nhất của ô này
  // Giọng dùng được ngay: theo nhóm (nhóm miễn phí trước). Giọng chưa dùng được: dồn xuống 1 mục cuối, làm mờ.
  const ready = voices.filter((v) => v.available)
  const notReady = voices.filter((v) => !v.available)
  const groups = Array.from(new Set(ready.map((v) => v.group)))
    .sort((a, b) => Number(ready.some((v) => v.group === b && v.tier === "free")) - Number(ready.some((v) => v.group === a && v.tier === "free")))
  const current = voices.find((v) => v.label === value)
  // câu thoại tự nhập để nghe thử — nhớ giữa các lần mở (dùng chung mọi ô chọn giọng)
  const [demo, setDemo] = useState(() => { try { return localStorage.getItem(DEMO_KEY) ?? "" } catch { return "" } })
  const saveDemo = (t: string) => { setDemo(t); try { localStorage.setItem(DEMO_KEY, t) } catch { /* bị chặn */ } }
  const sampleUrl = current?.sample ? mediaUrl(current.sample) : ""
  const sampleOn = !!sampleUrl && playing === sampleUrl
  const testOn = !!testUrl && playing === testUrl
  // rời màn hình / đổi trang → tắt tiếng của ô này (không để giọng thử phát vọng ở trang khác)
  const mine = useRef<string[]>([])
  mine.current = [sampleUrl, testUrl].filter(Boolean)
  const playingRef = useRef(playing)
  playingRef.current = playing
  useEffect(() => () => { if (playingRef.current && mine.current.includes(playingRef.current)) stopAllAudio() }, [])

  const test = async () => {
    if (testOn) { stopAllAudio(); return }             // đang phát câu thử → bấm lần nữa là dừng
    if (testing || !value) return
    stopAllAudio()                                     // đang nghe giọng khác → tắt ngay khi bắt đầu tạo
    setTesting(true)
    try {
      const r = await api.testVoice(value, demo.trim() || undefined, isVieneu(current?.id) ? fx : undefined)
      const url = mediaUrl(r.path)
      setTestUrl(url)
      play(url)
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
        <Button variant={sampleOn ? "secondary" : "outline"} size="sm" disabled={!sampleUrl} onClick={() => play(sampleUrl)}
          title={sampleUrl ? (sampleOn ? "Dừng" : "Nghe mẫu có sẵn") : "Giọng này chưa có mẫu dựng sẵn"} className="w-[104px] shrink-0">
          {sampleOn ? <><Square className="fill-current" /> Dừng</> : <><Play /> Mẫu nhanh</>}
        </Button>
        <div className="relative min-w-0 flex-1">
          <Input value={demo} maxLength={500} onChange={(e) => saveDemo(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); test() } }}
            placeholder="Nhập câu thoại để nghe thử (Enter) — để trống dùng câu mẫu"
            className="h-8 pr-7 text-xs placeholder:text-muted-foreground/70" />
          {demo && (
            <button type="button" onClick={() => saveDemo("")} title="Xoá câu thử"
              className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground [&_svg]:size-3.5">
              <X />
            </button>
          )}
        </div>
        <Button variant={testOn ? "secondary" : "outline"} size="sm" onClick={test} disabled={(testing && !testOn) || !value}
          title={testOn ? "Dừng" : demo.trim() ? "Đọc câu bạn nhập" : "Đọc câu mẫu"} className="w-[96px] shrink-0">
          {testing ? <><Loader2 className="animate-spin" /> Đang tạo</> : testOn ? <><Square className="fill-current" /> Dừng</> : <><Sparkles /> Tạo thử</>}
        </Button>
      </div>
    </div>
  )
}
