import {
  AlertTriangle, ArrowRight, Captions, Clock, ExternalLink, FileText, FolderOpen, Languages, Loader2, Merge, Pencil, Plus, Save, Search,
  Trash2, Wand2,
} from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { EmptyState, Field, PathInput, Section, StatusBadge, ToggleRow, jobFileName } from "@/components/common"
import { SubtitlePreview } from "@/components/SubtitlePreview"
import { SubtitleStyleEditor } from "@/components/SubtitleStyleEditor"
import type { JobSummary, SubStyle } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Slider } from "@/components/ui/slider"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { api, bridge, mediaUrl } from "@/lib/api"
import { basename, fmtClock, fmtRelative } from "@/lib/format"
import { SimpleSelect } from "./CreatePage"
import { confirmAction } from "@/components/ConfirmHost"
import { ASR_HINT, ASR_LABELS, asrLabel } from "@/lib/asr"

type Cue = { start: number; end: number; text: string }
type TabKey = "extract" | "burn" | "edit"
/** Chuyển file giữa các tab: "Sửa" một SRT vừa tách, "Ghép" SRT đang sửa vào video… */
type Handoff = { tab: TabKey; srt?: string; video?: string; n: number }

const SPLIT = "grid items-start grid-cols-[minmax(0,1fr)_360px] gap-5 xl:grid-cols-[minmax(0,1fr)_400px]"
const MAX_CPS = 20          // ký tự / giây — quá mức này người xem đọc không kịp

const srtTime = (t: number) => {
  const ms = Math.round(t * 1000)
  const h = Math.floor(ms / 3_600_000), m = Math.floor(ms / 60_000) % 60, s = Math.floor(ms / 1000) % 60
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(ms % 1000).padStart(3, "0")}`
}
/** "00:01:02,500" · "1:02.5" · "62.5" → giây. Sai định dạng → null. */
const parseSrtTime = (v: string): number | null => {
  const t = v.trim().replace(",", ".")
  if (!t) return null
  const parts = t.split(":").map(Number)
  if (parts.some((x) => Number.isNaN(x) || x < 0) || parts.length > 3) return null
  return parts.reduce((acc, x) => acc * 60 + x, 0)
}

/** Ô thời gian SRT: gõ tự do, chỉ áp dụng khi rời ô / Enter (không nhảy số khi đang gõ). Sai → trả về giá trị cũ. */
function SrtTime({ value, onChange, invalid }: { value: number; onChange: (v: number) => void; invalid?: boolean }) {
  const [text, setText] = useState(srtTime(value))
  useEffect(() => setText(srtTime(value)), [value])
  const commit = () => { const v = parseSrtTime(text); if (v === null) setText(srtTime(value)); else if (v !== value) onChange(v) }
  return (
    <Input value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") commit() }}
      className={cn("tabular h-8 px-1.5 font-mono text-[11px] md:text-[11px]", invalid && "border-destructive/60 text-destructive")} title="giờ:phút:giây,mili-giây — vd 00:01:02,500" />
  )
}

export function SubtitlesPage() {
  const [tab, setTab] = useState<TabKey>("extract")
  const [handoff, setHandoff] = useState<Handoff | null>(null)
  const send = (h: Omit<Handoff, "n">) => { setHandoff({ ...h, n: Date.now() }); setTab(h.tab) }
  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)} className="flex h-full min-h-0 flex-col gap-4">
      <TabsList>
        <TabsTrigger value="extract"><Wand2 /> Tách SRT</TabsTrigger>
        <TabsTrigger value="burn"><Merge /> Ghép phụ đề</TabsTrigger>
        <TabsTrigger value="edit"><FileText /> Sửa SRT</TabsTrigger>
      </TabsList>
      {/* forceMount + ẩn tab không chọn: chuyển tab không mất file / chỉnh sửa đang làm */}
      <TabsContent forceMount value="extract" className="min-h-0 overflow-y-auto pb-6 data-[state=inactive]:hidden"><ExtractTab send={send} /></TabsContent>
      <TabsContent forceMount value="burn" className="min-h-0 overflow-y-auto pb-6 data-[state=inactive]:hidden"><BurnTab send={send} handoff={handoff} /></TabsContent>
      <TabsContent forceMount value="edit" className="flex min-h-0 flex-col data-[state=inactive]:hidden"><EditTab send={send} handoff={handoff} /></TabsContent>
    </Tabs>
  )
}

/* ─────────────────────────── dùng chung ─────────────────────────── */

/** Job phụ đề gần đây (tách / ghép) — cập nhật mỗi 2s khi trang đang hiện. */
function useRecentJobs(kind: "srt" | "burn") {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  useEffect(() => {
    const load = () => api.jobs().then((j) => setJobs(j.filter((x) => x.kind === kind).slice(0, 6))).catch(() => {})
    load()
    const t = setInterval(() => { if (!document.hidden) load() }, 2000)
    return () => clearInterval(t)
  }, [kind])
  return jobs
}

/** Cột phải: tóm tắt cấu hình + nút chạy (luôn trong tầm mắt) + job gần đây. */
function ActionAside({ children, summary, action, recent }: { children?: ReactNode; summary: [string, ReactNode][]; action: ReactNode; recent: ReactNode }) {
  return (
    <aside className="sticky top-0 flex flex-col gap-4">
      <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4">
        {children}
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-xs">
          {summary.map(([k, v]) => (
            <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="truncate text-right">{v}</dd></div>
          ))}
        </dl>
        {action}
      </div>
      {recent}
    </aside>
  )
}

function RecentList({ title, jobs, render }: { title: string; jobs: JobSummary[]; render: (j: JobSummary) => ReactNode }) {
  const { openJob } = useStore()
  if (!jobs.length) return null
  return (
    <div className="rounded-xl border border-border bg-card">
      <p className="flex items-center gap-1.5 border-b border-border px-4 py-2.5 text-xs font-medium text-muted-foreground"><Clock className="size-3.5" /> {title}</p>
      <ul className="divide-y divide-border/60">
        {jobs.map((j) => {
          const running = ["running", "queued", "waiting"].includes(j.status)
          return (
            <li key={j.id} className="flex flex-col gap-1.5 px-4 py-2.5">
              <div className="flex items-center gap-2">
                <button className="min-w-0 flex-1 truncate text-left text-[12.5px] font-medium hover:underline" onClick={() => openJob(j.id)} title="Mở chi tiết job">
                  {jobFileName(j.title)}
                </button>
                {j.status !== "done" && <StatusBadge status={j.status} queuePos={j.queue_pos} />}
              </div>
              {running
                ? <div className="h-1 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-[width]" style={{ width: `${j.progress}%` }} /></div>
                : j.status === "done" ? <div className="flex flex-wrap items-center gap-1">{render(j)}</div>
                : <p className="truncate text-[11px] text-destructive" title={j.error}>{j.error || "Không hoàn thành"}</p>}
              <span className="text-[10.5px] text-muted-foreground">{running ? j.stage : fmtRelative(j.created_at)}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/* ─────────────────────────── Tách SRT ─────────────────────────── */

function ExtractTab({ send }: { send: (h: Omit<Handoff, "n">) => void }) {
  const { options, settings, system, openJob } = useStore()
  const [inp, setInp] = useState("")
  const [cfg, setCfg] = useState({ source_lang: "Tự động", whisper_model: "base", device: "GPU (NVIDIA)", sub_layout: "2 dòng gọn (khuyên dùng)", translate: true, ai_translate: false, film_context: "", out_dir: "" })
  const [busy, setBusy] = useState(false)
  const recent = useRecentJobs("srt")
  useEffect(() => {
    if (!settings) return
    const device = system && !system.gpu && settings.device.startsWith("GPU") ? "CPU" : settings.device
    setCfg((c) => ({ ...c, whisper_model: settings.whisper_model, device, out_dir: settings.output_dir }))
  }, [settings, system])
  if (!options) return null
  const set = <K extends keyof typeof cfg>(k: K, v: (typeof cfg)[K]) => setCfg((c) => ({ ...c, [k]: v }))
  const hasAi = Boolean(system?.web_ai?.chatgpt || system?.web_ai?.gemini)

  const start = async () => {
    setBusy(true)
    try { const j = await api.createSrtJob({ ...cfg, inp }); openJob(j.id) } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }
  const name = inp ? basename(inp).replace(/\.[^.]+$/, "") : "tên_video"
  return (
    <div className={SPLIT}>
      <div className="flex flex-col gap-4">
        <Section title="Video nguồn" icon={<Captions />} desc="File trên máy hoặc link YouTube / TikTok / Douyin…">
          <PathInput value={inp} onChange={setInp} pick={bridge.pickVideo} placeholder="Chọn video hoặc dán URL" />
        </Section>
        <Section title="Nhận dạng lời nói" icon={<Wand2 />} desc="Chạy ngay trên máy — không cần API key">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Ngôn ngữ gốc"><SimpleSelect value={cfg.source_lang} onChange={(v) => set("source_lang", v)} items={options.languages} /></Field>
            <Field label="Bố cục dòng"><SimpleSelect value={cfg.sub_layout} onChange={(v) => set("sub_layout", v)} items={Object.keys(options.sub_layouts)} /></Field>
            <Field label="Nhận dạng giọng nói" hint={ASR_HINT}><SimpleSelect labels={ASR_LABELS} value={cfg.whisper_model} onChange={(v) => set("whisper_model", v)} items={options.whisper_models} /></Field>
            <Field label="Thiết bị" hint={system && !system.gpu ? "Máy không có GPU NVIDIA — nên chọn CPU" : undefined}>
              <SimpleSelect value={cfg.device} onChange={(v) => set("device", v)} items={options.devices} />
            </Field>
          </div>
        </Section>
        <Section title="Dịch & lưu" icon={<Languages />} desc="Xuất thêm bản tiếng Việt cạnh bản gốc">
          <ToggleRow label="Dịch sang tiếng Việt" checked={cfg.translate} onChange={(v) => set("translate", v)} desc="Xuất thêm file _vi.srt (Google miễn phí, hoặc AI nếu bật bên dưới)." />
          <ToggleRow label="Dịch bằng AI (ChatGPT / Gemini)" checked={cfg.ai_translate} onChange={(v) => set("ai_translate", v)} disabled={!cfg.translate}
            desc={hasAi ? "Dịch tự nhiên hơn bằng tài khoản đã đăng nhập trong app." : "Chưa đăng nhập ChatGPT/Gemini (Cài đặt → Tài khoản AI) — sẽ dịch bằng Google."} />
          {cfg.translate && cfg.ai_translate && (
            <Field label="Bối cảnh phim (tuỳ chọn)" hint="Tên phim, nhân vật… giúp AI dịch đúng tên riêng và xưng hô.">
              <Textarea rows={2} value={cfg.film_context} onChange={(e) => set("film_context", e.target.value)} placeholder="VD: Phim tu tiên, nam chính Giang Phàm, nữ chính Từ Du Nhiên…" />
            </Field>
          )}
          <Field label="Thư mục xuất"><PathInput value={cfg.out_dir} onChange={(v) => set("out_dir", v)} pick={bridge.pickFolder} /></Field>
        </Section>
      </div>

      <ActionAside
        summary={[["Nhận dạng", `${asrLabel(cfg.whisper_model)} · ${cfg.device.startsWith("GPU") ? "GPU" : "CPU"}`], ["Ngôn ngữ", cfg.source_lang],
          ["Dịch", cfg.translate ? (cfg.ai_translate ? "AI (ChatGPT/Gemini)" : "Google") : "Không"]]}
        action={<Button size="lg" disabled={!inp || busy} onClick={start}>{busy ? <Loader2 className="animate-spin" /> : <Wand2 />} Tách SRT</Button>}
        recent={<RecentList title="Tách gần đây" jobs={recent} render={(j) => {
          const files = [j.result.vi_srt, j.result.original_srt].filter(Boolean) as string[]
          return <>
            {files.map((f) => (
              <Button key={f} size="xs" variant="outline" title={f} onClick={() => send({ tab: "edit", srt: f })}><Pencil /> {f.endsWith("_vi.srt") ? "Sửa bản Việt" : "Sửa bản gốc"}</Button>
            ))}
            {files[0] && <Button size="xs" variant="outline" onClick={() => send({ tab: "burn", srt: files[0], video: j.result.video_path })}><Merge /> Ghép</Button>}
            {files[0] && <Button size="icon-xs" variant="ghost" title="Mở thư mục" onClick={() => bridge.reveal(files[0])}><FolderOpen /></Button>}
          </>
        }} />}>
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Sẽ tạo ra</p>
          <ul className="flex flex-col gap-2 text-[12.5px]">
            <li className="flex gap-2"><FileText className="mt-0.5 size-3.5 shrink-0 text-primary" /><span className="min-w-0"><b className="block truncate">{name}_original.srt</b><span className="text-[11px] text-muted-foreground">Phụ đề gốc, đúng thời gian lời nói</span></span></li>
            <li className={cn("flex gap-2", !cfg.translate && "opacity-40")}><Languages className="mt-0.5 size-3.5 shrink-0 text-primary" /><span className="min-w-0"><b className="block truncate">{name}_vi.srt</b><span className="text-[11px] text-muted-foreground">Bản dịch tiếng Việt {cfg.ai_translate ? "(AI)" : "(Google)"}</span></span></li>
          </ul>
        </div>
      </ActionAside>
    </div>
  )
}

/* ─────────────────────────── Ghép phụ đề ─────────────────────────── */

function BurnTab({ send, handoff }: { send: (h: Omit<Handoff, "n">) => void; handoff: Handoff | null }) {
  const { options, settings, openJob } = useStore()
  const [inp, setInp] = useState("")
  const [srt, setSrt] = useState("")
  const [cfg, setCfg] = useState({ sub_style: "Mặc định (chữ trắng, viền đen)", sub_layout: "2 dòng gọn (khuyên dùng)", sub_margin_pct: 6, out_dir: "", sub_custom: {} as Partial<SubStyle> })
  const [busy, setBusy] = useState(false)
  const recent = useRecentJobs("burn")
  useEffect(() => { if (settings) setCfg((c) => ({ ...c, sub_style: settings.sub_style, sub_layout: settings.sub_layout, out_dir: settings.output_dir, sub_custom: settings.sub_custom ?? {} })) }, [settings])
  useEffect(() => {
    if (handoff?.tab !== "burn") return
    if (handoff.srt) setSrt(handoff.srt)
    if (handoff.video) setInp(handoff.video)
  }, [handoff?.n]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!options) return null
  const start = async () => {
    setBusy(true)
    try { const j = await api.createBurnJob({ ...cfg, inp, srt_path: srt }); openJob(j.id) } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }
  const missing = !inp ? "Chưa chọn video" : !srt ? "Chưa chọn file SRT" : ""
  return (
    <div className={SPLIT}>
      <div className="flex flex-col gap-4">
        <Section title="File" icon={<Merge />} desc="Video gốc + file phụ đề .srt có sẵn">
          <Field label="Video"><PathInput value={inp} onChange={setInp} pick={bridge.pickVideo} placeholder="Chọn video" /></Field>
          <Field label="File SRT">
            <div className="flex gap-2">
              <div className="min-w-0 flex-1"><PathInput value={srt} onChange={setSrt} pick={bridge.pickSrt} placeholder="Chọn file .srt" /></div>
              <Button variant="outline" disabled={!srt} title="Mở file này ở tab Sửa SRT" onClick={() => send({ tab: "edit", srt, video: inp })}><Pencil /> Sửa</Button>
            </div>
          </Field>
          <Field label="Thư mục xuất"><PathInput value={cfg.out_dir} onChange={(v) => setCfg({ ...cfg, out_dir: v })} pick={bridge.pickFolder} /></Field>
        </Section>
        <Section title="Kiểu chữ" icon={<Captions />} desc="Phong cách, bố cục dòng, vị trí và màu chữ">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Phong cách"><SimpleSelect value={cfg.sub_style} onChange={(v) => setCfg({ ...cfg, sub_style: v })} items={Object.keys(options.sub_styles)} /></Field>
            <Field label="Bố cục dòng"><SimpleSelect value={cfg.sub_layout} onChange={(v) => setCfg({ ...cfg, sub_layout: v })} items={Object.keys(options.sub_layouts)} /></Field>
          </div>
          <Field label={`Cách đáy: ${cfg.sub_margin_pct}%`}><Slider value={[cfg.sub_margin_pct]} min={2} max={40} onValueChange={([v]) => setCfg({ ...cfg, sub_margin_pct: v })} className="mt-1" /></Field>
          <SubtitleStyleEditor base={options.sub_styles[cfg.sub_style]} custom={cfg.sub_custom} onChange={(c) => setCfg({ ...cfg, sub_custom: c })} />
        </Section>
      </div>

      <ActionAside
        summary={[["Video", inp ? basename(inp) : "—"], ["Phụ đề", srt ? basename(srt) : "—"], ["Phong cách", cfg.sub_style]]}
        action={<>
          <Button size="lg" disabled={!!missing || busy} onClick={start}>{busy ? <Loader2 className="animate-spin" /> : <Merge />} Ghép phụ đề</Button>
          {missing && <p className="-mt-2 text-center text-[11px] text-muted-foreground">{missing}</p>}
        </>}
        recent={<RecentList title="Ghép gần đây" jobs={recent} render={(j) => j.result.output_path ? <>
          <Button size="xs" variant="outline" onClick={() => bridge.open(j.result.output_path!)}><ExternalLink /> Xem video</Button>
          <Button size="icon-xs" variant="ghost" title="Mở thư mục" onClick={() => bridge.reveal(j.result.output_path!)}><FolderOpen /></Button>
        </> : null} />}>
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Xem trước</p>
          <SubtitlePreview style={{ ...options.sub_styles[cfg.sub_style], ...cfg.sub_custom }} marginPct={cfg.sub_margin_pct} poster={/\.(mp4|mov|mkv|webm)$/i.test(inp) ? mediaUrl(inp) : undefined} />
        </div>
      </ActionAside>
    </div>
  )
}

/* ─────────────────────────── Sửa SRT ─────────────────────────── */

function EditTab({ send, handoff }: { send: (h: Omit<Handoff, "n">) => void; handoff: Handoff | null }) {
  const [path, setPath] = useState("")
  const [cues, setCues] = useState<Cue[]>([])
  const [loaded, setLoaded] = useState("")
  const [dirty, setDirty] = useState(false)
  const [video, setVideo] = useState("")
  const [query, setQuery] = useState("")
  const [shift, setShift] = useState("0.5")
  const recent = useRecentJobs("srt")

  const load = async (p = path) => {
    try { const r = await api.readSrt(p); setCues(r.cues); setLoaded(p); setPath(p); setDirty(false) } catch (e) { toast.error((e as Error).message) }
  }
  useEffect(() => {
    if (handoff?.tab !== "edit" || !handoff.srt) return
    setVideo(handoff.video ?? "")
    load(handoff.srt)
  }, [handoff?.n]) // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => {
    try { await api.saveSrt(loaded, cues); setDirty(false); toast.success("Đã lưu SRT") } catch (e) { toast.error((e as Error).message) }
  }
  const change = (next: Cue[]) => { setCues(next); setDirty(true) }
  const upd = (i: number, patch: Partial<Cue>) => change(cues.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  const shiftAll = (sign: 1 | -1) => {
    const d = Number(shift.replace(",", "."))
    if (!d) return
    change(cues.map((c) => ({ ...c, start: Math.max(0, c.start + sign * d), end: Math.max(0.1, c.end + sign * d) })))
    toast.success(`Đã dời ${cues.length} dòng ${sign > 0 ? "chậm" : "sớm"} ${d}s`)
  }

  // Cảnh báo từng dòng: thời gian sai / chồng dòng trước / chữ chạy quá nhanh
  const problems = useMemo(() => cues.map((c, i) => {
    const dur = c.end - c.start
    if (dur <= 0) return "Kết thúc trước khi bắt đầu"
    if (i > 0 && c.start < cues[i - 1].end - 0.01) return "Chồng lên dòng trước"
    const cps = c.text.replace(/\s+/g, "").length / dur
    if (cps > MAX_CPS) return `Chữ chạy nhanh (${cps.toFixed(0)} ký tự/giây) — người xem đọc không kịp`
    return ""
  }), [cues])
  const issueCount = problems.filter(Boolean).length
  const q = query.trim().toLowerCase()
  const shown = cues.map((c, i) => ({ c, i })).filter(({ c }) => !q || c.text.toLowerCase().includes(q))
  const recentFiles = recent.flatMap((j) => [j.result.vi_srt, j.result.original_srt]).filter(Boolean) as string[]

  if (!loaded) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pb-6">
        <EmptyState icon={<FileText />} title="Mở một file SRT để sửa" desc="Sửa chữ, chỉnh thời gian từng dòng, dời cả file sớm/muộn, phát hiện dòng chồng nhau hoặc chữ chạy quá nhanh."
          action={
            <div className="flex w-full max-w-xl gap-2">
              <div className="min-w-0 flex-1"><PathInput value={path} onChange={setPath} pick={async () => { const p = await bridge.pickSrt(); if (p) load(p); return p }} placeholder="Đường dẫn file .srt" /></div>
              <Button onClick={() => load()} disabled={!path}>Mở</Button>
            </div>
          } />
        {recentFiles.length > 0 && (
          <div className="rounded-xl border border-border bg-card">
            <p className="flex items-center gap-1.5 border-b border-border px-4 py-2.5 text-xs font-medium text-muted-foreground"><Clock className="size-3.5" /> SRT vừa tách</p>
            <ul className="divide-y divide-border/60">
              {recentFiles.slice(0, 8).map((f) => (
                <li key={f}>
                  <button className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-[12.5px] hover:bg-muted/50" onClick={() => load(f)}>
                    {f.endsWith("_vi.srt") ? <Languages className="size-3.5 shrink-0 text-primary" /> : <FileText className="size-3.5 shrink-0 text-muted-foreground" />}
                    <span className="min-w-0 flex-1 truncate">{basename(f)}</span>
                    <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card">
      {/* thanh file */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <FileText className="size-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium" title={loaded}>{basename(loaded)}{dirty && <span className="ml-1.5 text-[11px] font-normal text-warning">· chưa lưu</span>}</p>
          <p className="text-[11px] text-muted-foreground">{cues.length} dòng · dài {fmtClock(cues.at(-1)?.end ?? 0)}
            {issueCount > 0 && <span className="text-warning"> · {issueCount} dòng cần xem</span>}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={async () => {
          if (dirty && !(await confirmAction({ title: "Đóng file chưa lưu?", desc: "Các chỉnh sửa chưa lưu sẽ mất.", action: "Đóng, không lưu", danger: true }))) return
          setLoaded(""); setCues([])
        }}>Đóng</Button>
        <Button variant="outline" size="sm" onClick={() => bridge.reveal(loaded)}><FolderOpen /> Thư mục</Button>
        <Button variant="outline" size="sm" onClick={() => send({ tab: "burn", srt: loaded, video })}><Merge /> Ghép vào video</Button>
        <Button size="sm" onClick={save} disabled={!dirty}><Save /> Lưu</Button>
      </div>
      {/* công cụ */}
      <div className="flex items-center gap-2 border-b border-border bg-muted/20 px-3 py-2">
        <div className="relative w-72">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm trong phụ đề…" className="h-8 pl-8 text-[12.5px]" />
        </div>
        {q && <span className="text-[11px] text-muted-foreground">{shown.length} kết quả</span>}
        <div className="ml-auto flex items-center gap-1.5 text-[12px] text-muted-foreground">
          Dời cả file
          <Input value={shift} onChange={(e) => setShift(e.target.value)} className="tabular h-8 w-16 text-center text-[12px]" />
          giây
          <Button size="sm" variant="outline" onClick={() => shiftAll(-1)} title="Phụ đề hiện sớm hơn">Sớm hơn</Button>
          <Button size="sm" variant="outline" onClick={() => shiftAll(1)} title="Phụ đề hiện muộn hơn">Muộn hơn</Button>
        </div>
      </div>
      {/* danh sách dòng */}
      <div className="grid grid-cols-[44px_250px_1fr_56px_36px] gap-3 border-b border-border px-4 py-1.5 text-[10.5px] font-semibold tracking-wider text-muted-foreground uppercase">
        <span>#</span><span>Thời gian</span><span>Nội dung</span><span className="text-right">Dài</span><span />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {shown.map(({ c, i }) => (
          <div key={i} className={cn("group grid grid-cols-[44px_250px_1fr_56px_36px] items-start gap-3 border-b border-border/60 px-4 py-2", problems[i] && "bg-warning/[0.04]")}>
            <span className="tabular flex items-center gap-1 pt-2 text-xs text-muted-foreground">
              {i + 1}{problems[i] && <span title={problems[i]}><AlertTriangle className="size-3 text-warning" /></span>}
            </span>
            <div className="flex items-center gap-1">
              <SrtTime value={c.start} onChange={(v) => upd(i, { start: v })} invalid={problems[i] === "Chồng lên dòng trước"} />
              <span className="text-muted-foreground">→</span>
              <SrtTime value={c.end} onChange={(v) => upd(i, { end: v })} invalid={problems[i] === "Kết thúc trước khi bắt đầu"} />
            </div>
            <div>
              <Textarea value={c.text} rows={1} onChange={(e) => upd(i, { text: e.target.value })} className="field-sizing-content min-h-8 py-1.5 text-[13px]" />
              {problems[i] && <p className="mt-0.5 text-[10.5px] text-warning">{problems[i]}</p>}
            </div>
            <span className="tabular pt-2 text-right text-[11px] text-muted-foreground">{(c.end - c.start).toFixed(1)}s</span>
            <Button variant="ghost" size="icon-sm" title="Xoá dòng" className="opacity-0 group-hover:opacity-100" onClick={() => change(cues.filter((_, j) => j !== i))}><Trash2 /></Button>
          </div>
        ))}
        {!q && (
          <Button variant="ghost" size="sm" className="m-3" onClick={() => { const last = cues.at(-1); change([...cues, { start: last?.end ?? 0, end: (last?.end ?? 0) + 2, text: "" }]) }}>
            <Plus /> Thêm dòng
          </Button>
        )}
      </div>
    </div>
  )
}
