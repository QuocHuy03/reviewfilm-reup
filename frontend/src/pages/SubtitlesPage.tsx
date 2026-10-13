import { Captions, FileText, Loader2, Merge, Plus, Save, Trash2, Wand2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Field, PathInput, Section, ToggleRow } from "@/components/common"
import { SubtitlePreview } from "@/components/SubtitlePreview"
import { SubtitleStyleEditor } from "@/components/SubtitleStyleEditor"
import type { SubStyle } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Slider } from "@/components/ui/slider"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { api, bridge, mediaUrl } from "@/lib/api"
import { fmtClock } from "@/lib/format"
import { SimpleSelect } from "./CreatePage"

type Cue = { start: number; end: number; text: string }

export function SubtitlesPage() {
  return (
    <Tabs defaultValue="extract" className="flex h-full min-h-0 flex-col gap-4">
      <TabsList>
        <TabsTrigger value="extract"><Wand2 /> Tách SRT</TabsTrigger>
        <TabsTrigger value="burn"><Merge /> Ghép phụ đề</TabsTrigger>
        <TabsTrigger value="edit"><FileText /> Sửa SRT</TabsTrigger>
      </TabsList>
      <TabsContent value="extract" className="min-h-0 overflow-y-auto"><ExtractTab /></TabsContent>
      <TabsContent value="burn" className="min-h-0 overflow-y-auto"><BurnTab /></TabsContent>
      <TabsContent value="edit" className="flex min-h-0 flex-col"><EditTab /></TabsContent>
    </Tabs>
  )
}

function ExtractTab() {
  const { options, settings, system, openJob } = useStore()
  const [inp, setInp] = useState("")
  const [cfg, setCfg] = useState({ source_lang: "Tự động", whisper_model: "base", device: "GPU (NVIDIA)", sub_layout: "2 dòng gọn (khuyên dùng)", translate: true, ai_translate: false, film_context: "", out_dir: "" })
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!settings) return
    const device = system && !system.gpu && settings.device.startsWith("GPU") ? "CPU" : settings.device
    setCfg((c) => ({ ...c, whisper_model: settings.whisper_model, device, out_dir: settings.output_dir }))
  }, [settings, system])
  if (!options) return null
  const set = <K extends keyof typeof cfg>(k: K, v: (typeof cfg)[K]) => setCfg((c) => ({ ...c, [k]: v }))

  const start = async () => {
    setBusy(true)
    try { const j = await api.createSrtJob({ ...cfg, inp }); openJob(j.id) } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Section title="Tách phụ đề bằng Whisper" icon={<Captions />} desc="Tạo file SRT gốc, tuỳ chọn dịch sang tiếng Việt — không cần API key">
      <Field label="Video hoặc URL"><PathInput value={inp} onChange={setInp} pick={bridge.pickVideo} placeholder="Chọn video hoặc dán URL" /></Field>
      <div className="grid grid-cols-4 gap-3">
        <Field label="Ngôn ngữ gốc"><SimpleSelect value={cfg.source_lang} onChange={(v) => set("source_lang", v)} items={options.languages} /></Field>
        <Field label="Whisper"><SimpleSelect value={cfg.whisper_model} onChange={(v) => set("whisper_model", v)} items={options.whisper_models} /></Field>
        <Field label="Thiết bị"><SimpleSelect value={cfg.device} onChange={(v) => set("device", v)} items={options.devices} /></Field>
        <Field label="Bố cục dòng"><SimpleSelect value={cfg.sub_layout} onChange={(v) => set("sub_layout", v)} items={Object.keys(options.sub_layouts)} /></Field>
      </div>
      <ToggleRow label="Dịch sang tiếng Việt" checked={cfg.translate} onChange={(v) => set("translate", v)} desc="Xuất thêm file _vi.srt (Google miễn phí, hoặc AI nếu bật bên dưới)." />
      <ToggleRow label="Dịch bằng AI (DeepSeek / OpenAI)" checked={cfg.ai_translate} onChange={(v) => set("ai_translate", v)} disabled={!cfg.translate} />
      <Field label="Thư mục xuất"><PathInput value={cfg.out_dir} onChange={(v) => set("out_dir", v)} pick={bridge.pickFolder} /></Field>
      <Button className="self-end" disabled={!inp || busy} onClick={start}>{busy ? <Loader2 className="animate-spin" /> : <Wand2 />} Tách SRT</Button>
    </Section>
  )
}

function BurnTab() {
  const { options, settings, openJob } = useStore()
  const [inp, setInp] = useState("")
  const [srt, setSrt] = useState("")
  const [cfg, setCfg] = useState({ sub_style: "Mặc định (chữ trắng, viền đen)", sub_layout: "2 dòng gọn (khuyên dùng)", sub_margin_pct: 6, out_dir: "", sub_custom: {} as Partial<SubStyle> })
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (settings) setCfg((c) => ({ ...c, sub_style: settings.sub_style, sub_layout: settings.sub_layout, out_dir: settings.output_dir, sub_custom: settings.sub_custom ?? {} })) }, [settings])
  if (!options) return null
  const start = async () => {
    setBusy(true)
    try { const j = await api.createBurnJob({ ...cfg, inp, srt_path: srt }); openJob(j.id) } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="grid grid-cols-[1fr_340px] gap-4">
      <Section title="Ghép phụ đề vào video" icon={<Merge />} desc="Burn file SRT có sẵn vào video với kiểu chữ tuỳ chọn">
        <Field label="Video"><PathInput value={inp} onChange={setInp} pick={bridge.pickVideo} placeholder="Chọn video" /></Field>
        <Field label="File SRT"><PathInput value={srt} onChange={setSrt} pick={bridge.pickSrt} placeholder="Chọn file .srt" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Phong cách"><SimpleSelect value={cfg.sub_style} onChange={(v) => setCfg({ ...cfg, sub_style: v })} items={Object.keys(options.sub_styles)} /></Field>
          <Field label="Bố cục dòng"><SimpleSelect value={cfg.sub_layout} onChange={(v) => setCfg({ ...cfg, sub_layout: v })} items={Object.keys(options.sub_layouts)} /></Field>
        </div>
        <Field label={`Cách đáy: ${cfg.sub_margin_pct}%`}><Slider value={[cfg.sub_margin_pct]} min={2} max={40} onValueChange={([v]) => setCfg({ ...cfg, sub_margin_pct: v })} /></Field>
        <SubtitleStyleEditor base={options.sub_styles[cfg.sub_style]} custom={cfg.sub_custom} onChange={(c) => setCfg({ ...cfg, sub_custom: c })} />
        <Field label="Thư mục xuất"><PathInput value={cfg.out_dir} onChange={(v) => setCfg({ ...cfg, out_dir: v })} pick={bridge.pickFolder} /></Field>
        <Button className="self-end" disabled={!inp || !srt || busy} onClick={start}>{busy ? <Loader2 className="animate-spin" /> : <Merge />} Ghép phụ đề</Button>
      </Section>
      <div className="rounded-xl border border-border bg-card p-4">
        <p className="mb-3 text-xs font-medium text-muted-foreground">Xem trước</p>
        <SubtitlePreview style={{ ...options.sub_styles[cfg.sub_style], ...cfg.sub_custom }} marginPct={cfg.sub_margin_pct} poster={/\.(mp4|mov|mkv|webm)$/i.test(inp) ? mediaUrl(inp) : undefined} />
      </div>
    </div>
  )
}

function EditTab() {
  const [path, setPath] = useState("")
  const [cues, setCues] = useState<Cue[]>([])
  const [loaded, setLoaded] = useState("")
  const load = async (p = path) => {
    try { const r = await api.readSrt(p); setCues(r.cues); setLoaded(p) } catch (e) { toast.error((e as Error).message) }
  }
  const save = async () => {
    try { await api.saveSrt(loaded, cues); toast.success("Đã lưu SRT") } catch (e) { toast.error((e as Error).message) }
  }
  const upd = (i: number, patch: Partial<Cue>) => setCues(cues.map((c, j) => j === i ? { ...c, ...patch } : c))
  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border p-3">
        <div className="flex-1"><PathInput value={path} onChange={setPath} pick={async () => { const p = await bridge.pickSrt(); if (p) load(p); return p }} placeholder="Đường dẫn file .srt" /></div>
        <Button variant="outline" onClick={() => load()} disabled={!path}>Mở</Button>
        <Button onClick={save} disabled={!loaded}><Save /> Lưu</Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {!loaded && <p className="py-14 text-center text-xs text-muted-foreground">Mở một file SRT để sửa từng dòng.</p>}
        {cues.map((c, i) => (
          <div key={i} className="group grid grid-cols-[40px_170px_1fr_32px] items-start gap-3 border-b border-border/60 px-4 py-2 last:border-0">
            <span className="tabular pt-2 text-xs text-muted-foreground">{i + 1}</span>
            <div className="flex items-center gap-1">
              <Input type="number" step={0.1} value={c.start.toFixed(2)} onChange={(e) => upd(i, { start: Number(e.target.value) })} className="h-8 px-2 text-xs" title={fmtClock(c.start)} />
              <span className="text-muted-foreground">→</span>
              <Input type="number" step={0.1} value={c.end.toFixed(2)} onChange={(e) => upd(i, { end: Number(e.target.value) })} className="h-8 px-2 text-xs" title={fmtClock(c.end)} />
            </div>
            <Textarea value={c.text} rows={1} onChange={(e) => upd(i, { text: e.target.value })} className="min-h-8 py-1.5 text-[13px]" />
            <Button variant="ghost" size="icon-sm" className="opacity-0 group-hover:opacity-100" onClick={() => setCues(cues.filter((_, j) => j !== i))}><Trash2 /></Button>
          </div>
        ))}
        {loaded && (
          <Button variant="ghost" size="sm" className="m-3" onClick={() => { const last = cues.at(-1); setCues([...cues, { start: last?.end ?? 0, end: (last?.end ?? 0) + 2, text: "" }]) }}>
            <Plus /> Thêm dòng
          </Button>
        )}
      </div>
    </div>
  )
}
