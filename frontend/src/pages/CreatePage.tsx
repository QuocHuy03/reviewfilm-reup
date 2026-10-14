import {
  AlertTriangle, Captions, Clapperboard, FileVideo, FolderOpen, FolderOutput, Languages, Link2, ListPlus, Loader2, Mic2, Rocket, Settings2, Wand2,
} from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Field, PathInput, Section, Segmented, ToggleRow } from "@/components/common"
import { SubtitlePreview } from "@/components/SubtitlePreview"
import { SubtitleStyleEditor } from "@/components/SubtitleStyleEditor"
import type { SubStyle } from "@/lib/types"
import { VoiceSelect } from "@/components/VoiceSelect"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Textarea } from "@/components/ui/textarea"
import { api, bridge, mediaUrl } from "@/lib/api"
import { fmtClock } from "@/lib/format"
import { CoverBoxEditor, DEFAULT_SUB_BOX } from "@/components/CoverBoxEditor"
import { PresetBar } from "@/components/PresetBar"
import { cn } from "@/lib/utils"

type Mode = "review" | "reup"
type Source = "file" | "url" | "batch"

const PRESETS = [{ m: 8, label: "Ngắn ~8′" }, { m: 12, label: "Vừa ~12′" }, { m: 18, label: "Dài ~18′" }]

export function SimpleSelect({ value, onChange, items, placeholder }: { value: string; onChange: (v: string) => void; items: string[]; placeholder?: string }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full"><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>{items.map((i) => <SelectItem key={i} value={i}>{i}</SelectItem>)}</SelectContent>
    </Select>
  )
}

const DEFAULT_CFG = {
  source_lang: "Tự động", whisper_model: "base", device: "GPU (NVIDIA)", minutes: 12, film_context: "",
  scene_accurate: false, ai_translate: true, video_speed: "1.0x (mặc định)", mirror_video: false,
  voice: "Edge TTS — Nữ Bắc (miễn phí)", strict_voice: false, multi_voice: false,
  sub_style: "Mặc định (chữ trắng, viền đen)", sub_layout: "2 dòng gọn (khuyên dùng)",
  sub_source: "Theo lời đọc AI (khớp voiceover)", burn_subtitles: true, sub_margin_pct: 6,
  remove_old_sub: false, cover_boxes: [[...DEFAULT_SUB_BOX]] as number[][], sub_custom: {} as Partial<SubStyle>,
  script_edit: true, scene_preview: true, out_dir: "",
  auto_post: true, auto_fix: true, auto_publish: true, target_resolution: "1920x1080",
  watermark_path: "", watermark_corner: "Trên-Phải", watermark_size_pct: 14, watermark_opacity: 0.92, intro_path: "", outro_path: "",
}

/** Danh sách video hàng loạt: mỗi dòng 1 nguồn, bỏ dòng trống / trùng. */
const batchItems = (v: string) => Array.from(new Set(v.split(/\r?\n/).map((x) => x.trim().replace(/^"|"$/g, "")).filter(Boolean)))

type Tab = "script" | "voice" | "subs" | "post" | "output"
const TABS: { value: Tab; label: string; icon: ReactNode; desc: string }[] = [
  { value: "script", label: "Kịch bản", icon: <Clapperboard />, desc: "Độ dài, bối cảnh phim" },
  { value: "voice", label: "Giọng đọc", icon: <Mic2 />, desc: "Giọng, tốc độ, phân vai" },
  { value: "subs", label: "Phụ đề", icon: <Captions />, desc: "Kiểu chữ, che phụ đề gốc" },
  { value: "post", label: "Hậu kỳ", icon: <Wand2 />, desc: "Tự sửa lỗi, bài đăng, logo, intro/outro" },
  { value: "output", label: "Quy trình & xuất", icon: <FolderOutput />, desc: "Dừng xem lại ở đâu, nơi lưu video" },
]

const CREATE_DRAFT_KEY = "rf.create.draft.v1"
type CreateDraft = { mode: Mode; source: Source; inp: string; cfg: Partial<typeof DEFAULT_CFG> }
function loadCreateDraft(): CreateDraft | null {
  try { const raw = localStorage.getItem(CREATE_DRAFT_KEY); return raw ? (JSON.parse(raw) as CreateDraft) : null } catch { return null }
}

/** Điền sẵn video vào trang Tạo video (giữ nguyên cấu hình đang có) — dùng khi bấm "Tạo Review" ở trang Tải video. */
export function openInCreate(path: string, mode: Mode) {
  const cur = loadCreateDraft()
  try { localStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify({ ...(cur ?? { cfg: {} }), mode, source: "file", inp: path })) } catch { /* bị chặn */ }
}

/** Mở trang Tạo video ở chế độ cho trước (Review / Dịch & Reup), giữ nguyên các cấu hình khác. */
export function setCreateMode(mode: Mode) {
  const cur = loadCreateDraft()
  try { localStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify({ ...(cur ?? { source: "file", inp: "", cfg: {} }), mode })) } catch { /* bị chặn */ }
}

export function CreatePage() {
  const { options, settings, system, openJob, go } = useStore()
  const saved = useMemo(loadCreateDraft, [])
  const [mode, setMode] = useState<Mode>(saved?.mode ?? "review")
  const [source, setSource] = useState<Source>(saved?.source ?? "file")
  const [inp, setInp] = useState(saved?.inp ?? "")
  const [cfg, setCfg] = useState(() => ({ ...DEFAULT_CFG, ...(saved?.cfg ?? {}) }))
  // Tự lưu form — trang này bị dựng lại mỗi lần chuyển trang
  useEffect(() => {
    const t = setTimeout(() => { try { localStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify({ mode, source, inp, cfg })) } catch { /* bị chặn / đầy */ } }, 400)
    return () => clearTimeout(t)
  }, [mode, source, inp, cfg])
  const [starting, setStarting] = useState(false)
  const [tab, setTab] = useState<Tab>("script")
  // chấm cam trên tab = đang bật tuỳ chọn khác mặc định trong tab đó (để biết mà mở xem)
  const tabDot: Record<Tab, boolean> = {
    script: !!cfg.film_context.trim() || cfg.scene_accurate,
    voice: cfg.strict_voice || cfg.multi_voice || !cfg.video_speed.startsWith("1.0x"),
    subs: !cfg.burn_subtitles || cfg.remove_old_sub || Object.keys(cfg.sub_custom).length > 0,
    post: !!cfg.watermark_path || !!cfg.intro_path || !!cfg.outro_path || cfg.mirror_video || cfg.target_resolution !== "1920x1080",
    output: !cfg.script_edit || !cfg.scene_preview,
  }
  const set = <K extends keyof typeof cfg>(k: K, v: (typeof cfg)[K]) => setCfg((c) => ({ ...c, [k]: v }))

  useEffect(() => {
    // đã có bản nháp cấu hình của người dùng → không ghi đè bằng mặc định trong Cài đặt
    if (!settings || Object.keys(saved?.cfg ?? {}).length) return
    // Máy không có GPU NVIDIA → mặc định CPU (tránh Whisper thử GPU rồi mới fallback)
    const device = system && !system.gpu && settings.device.startsWith("GPU") ? "CPU" : settings.device
    setCfg((c) => ({ ...c, whisper_model: settings.whisper_model, device, voice: settings.voice,
      sub_style: settings.sub_style, sub_layout: settings.sub_layout, out_dir: settings.output_dir, sub_custom: settings.sub_custom ?? {} }))
  }, [settings, system])

  const preset = options?.sub_styles[cfg.sub_style]
  const style = preset ? { ...preset, ...cfg.sub_custom } : undefined
  const webAi = Boolean(system?.web_ai?.chatgpt || system?.web_ai?.gemini)
  const needsKey = mode === "review" && system && !system.web_ai?.gemini
  const isLocalFile = source === "file" && /\.(mp4|mkv|mov|webm|m4v)$/i.test(inp)

  // Độ dài video gốc (file trên máy) — để cảnh báo khi độ dài review chọn dài hơn video
  const [srcDur, setSrcDur] = useState(0)
  useEffect(() => {
    setSrcDur(0)
    if (!isLocalFile) return
    const v = document.createElement("video")
    v.preload = "metadata"
    v.onloadedmetadata = () => setSrcDur(Number.isFinite(v.duration) ? v.duration : 0)
    v.src = mediaUrl(inp)
    return () => { v.removeAttribute("src"); v.load() }
  }, [inp, isLocalFile])

  const issues = useMemo(() => {
    const out: string[] = []
    if (!inp.trim()) out.push("Chưa chọn video / URL")
    else if (source === "batch" && batchItems(inp).length < 2) out.push("Hàng loạt cần từ 2 video trở lên (1 video thì dùng File / URL)")
    if (needsKey) out.push("Chế độ Review cần đăng nhập Gemini (Cài đặt → Tài khoản AI)")
    if (system && !system.ffmpeg) out.push("Thiếu ffmpeg")
    return out
  }, [inp, needsKey, system, source])

  const startBatch = async () => {
    const list = batchItems(inp)
    setStarting(true)
    let ok = 0
    const failed: { item: string; msg: string }[] = []
    for (const item of list) {
      try {
        await api.createVideoJob({ ...cfg, mode, inp: item, script_edit: false, scene_preview: false,
          cover_boxes: cfg.remove_old_sub ? cfg.cover_boxes : [] })
        ok++
      } catch (e) { failed.push({ item, msg: (e as Error).message }) }
    }
    setStarting(false)
    const name = (x: string) => x.split(/[\\/]/).pop() ?? x
    if (failed.length) toast.error(`${failed.length} video không tạo được — đã giữ lại trong ô để sửa`,
      { description: failed.slice(0, 3).map((f) => `${name(f.item)}: ${f.msg}`).join("\n") })
    setInp(failed.map((f) => f.item).join("\n"))   // chỉ giữ lại dòng lỗi
    if (ok) { toast.success(`Đã xếp hàng ${ok} video — chạy lần lượt`, { description: "Theo dõi ở trang Lịch sử" }); go("jobs") }
  }

  const start = async () => {
    if (source === "batch") return startBatch()
    setStarting(true)
    try {
      const job = await api.createVideoJob({ ...cfg, mode, inp: inp.trim(),
        cover_boxes: cfg.remove_old_sub ? cfg.cover_boxes : [] })
      toast.success(job.queue_pos ? `Đã xếp hàng (#${job.queue_pos}) — chạy khi job trước xong` : "Đã bắt đầu xử lý", { description: job.title })
      setInp("")                       // giữ cấu hình cho video tiếp theo, chỉ xoá nguồn vừa chạy
      openJob(job.id)
    } catch (e) {
      toast.error("Không thể bắt đầu", { description: (e as Error).message })
    } finally {
      setStarting(false)
    }
  }

  if (!options) return null

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_360px] gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
      {/* ---------- Form ---------- */}
      <div className="min-h-0 overflow-y-auto pr-1 pb-6">
        <div className="flex flex-col gap-4">
          <PresetBar mode={mode} cfg={cfg} onApply={(m, c) => { setMode(m === "reup" ? "reup" : "review"); setCfg({ ...DEFAULT_CFG, ...c }) }} />
          <div className="flex items-center justify-between gap-4">
            <Segmented value={mode} onChange={setMode} items={[
              { value: "review", label: "Tạo Review (AI viết kịch bản)", icon: <Wand2 /> },
              { value: "reup", label: "Dịch & Reup", icon: <Languages /> },
            ]} />
            <span className="text-xs text-muted-foreground">
              {mode === "review" ? "Whisper → Vision AI → kịch bản → lồng tiếng → dựng video" : "Whisper → dịch → lồng tiếng → dựng video"}
            </span>
          </div>

          <Section title="Video nguồn" icon={<FileVideo />} desc="File trên máy hoặc link YouTube / TikTok"
            action={<Segmented size="sm" value={source} onChange={(v) => { setSource(v); setInp("") }} items={[
              { value: "file", label: "File", icon: <FileVideo /> }, { value: "url", label: "URL", icon: <Link2 /> },
              { value: "batch", label: "Nhiều video", icon: <ListPlus /> }]} />}>
            {source === "file" && <PathInput value={inp} onChange={setInp} pick={bridge.pickVideo} placeholder="Chọn file video (.mp4, .mkv, .mov…)" />}
            {source === "url" && <Input value={inp} onChange={(e) => setInp(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" className="font-mono text-xs placeholder:font-sans" />}
            {source === "batch" && (
              <div className="flex flex-col gap-2">
                <Textarea value={inp} onChange={(e) => setInp(e.target.value)} rows={5} className="font-mono text-xs placeholder:font-sans"
                  placeholder={"Mỗi dòng 1 video — đường dẫn file hoặc link YouTube / TikTok\nC:\\Phim\\tap1.mp4\nhttps://www.youtube.com/watch?v=…"} />
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <Button variant="outline" size="sm" disabled={!bridge.available()}
                    onClick={async () => { const fs = await bridge.pickVideos(); if (fs.length) setInp((v) => [...batchItems(v), ...fs].join("\n")) }}>
                    <FolderOpen /> Chọn nhiều file
                  </Button>
                  <span>{batchItems(inp).length} video · chạy lần lượt, tự động hoàn toàn (không dừng chờ sửa từng video)</span>
                </div>
              </div>
            )}
            <div className="grid grid-cols-3 gap-3">
              <Field label="Ngôn ngữ video gốc">
                <SimpleSelect value={cfg.source_lang} onChange={(v) => set("source_lang", v)} items={options.languages} />
              </Field>
              <Field label="Whisper model" hint="base nhanh · medium/large chính xác hơn">
                <SimpleSelect value={cfg.whisper_model} onChange={(v) => set("whisper_model", v)} items={options.whisper_models} />
              </Field>
              <Field label="Thiết bị xử lý">
                <SimpleSelect value={cfg.device} onChange={(v) => set("device", v)} items={options.devices} />
              </Field>
            </div>
          </Section>

          {/* Các phần cấu hình gom thành tab — đỡ phải cuộn trang dài */}
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Segmented value={tab} onChange={setTab} items={TABS.map((t) => ({ value: t.value, label: t.value === "script" && mode === "reup" ? "Bản dịch" : t.label, icon: <span className="relative">{t.icon}{tabDot[t.value] && <span className="absolute -top-0.5 -right-1 size-1.5 rounded-full bg-primary" />}</span> }))} />
              <span className="ml-auto text-[11px] text-muted-foreground">{tab === "script" && mode === "reup" ? "Dịch AI, bối cảnh phim" : TABS.find((t) => t.value === tab)?.desc}</span>
            </div>

            {tab === "script" && (
              <Section title={mode === "review" ? "Kịch bản review" : "Dịch phụ đề"} icon={<Clapperboard />}
                desc={mode === "review" ? "AI xem phim và viết lời thuyết minh" : "Dịch lời thoại sang tiếng Việt"}>
              {mode === "review" ? (
                <>
                  <Field label="Độ dài review">
                    <div className="flex items-center gap-2">
                      {PRESETS.map((p) => (
                        <Button key={p.m} size="sm" variant={cfg.minutes === p.m ? "default" : "outline"} onClick={() => set("minutes", p.m)}>{p.label}</Button>
                      ))}
                      <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                        Tuỳ chỉnh
                        <Input type="number" min={1} max={60} value={cfg.minutes} className="h-8 w-16 text-center"
                          onChange={(e) => set("minutes", Math.max(1, Math.min(60, Number(e.target.value) || 1)))} /> phút
                      </div>
                    </div>
                    {srcDur > 0 && cfg.minutes * 60 > srcDur && (
                      <p className="mt-1.5 flex items-start gap-1.5 rounded-md border border-warning/30 bg-warning/5 px-2.5 py-1.5 text-[11px] text-warning">
                        <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                        Video gốc chỉ dài {fmtClock(srcDur)} — kịch bản sẽ tự rút còn ~{Math.round(srcDur * 0.95)} giây để lời đọc khớp hình từng cảnh.
                      </p>
                    )}
                  </Field>
                  <ToggleRow label="Phân tích chuyên sâu" checked={cfg.scene_accurate} onChange={(v) => set("scene_accurate", v)}
                    desc="Cắt cảnh theo scene thật (PySceneDetect) + AI xem kỹ từng chương — lời đọc khớp hình hơn, chạy chậm hơn." />
                </>
              ) : (
                <ToggleRow label="Dịch bằng AI (ChatGPT / Gemini)" checked={cfg.ai_translate} onChange={(v) => set("ai_translate", v)}
                  desc={webAi ? "Dịch tự nhiên hơn bằng tài khoản đã đăng nhập." : "Chưa đăng nhập tài khoản AI — sẽ dùng Google dịch miễn phí."} />
              )}
              <Field label="Bối cảnh phim (tuỳ chọn)" hint="Tên phim, thể loại, tên nhân vật… giúp AI viết/dịch đúng hơn.">
                <Textarea value={cfg.film_context} onChange={(e) => set("film_context", e.target.value)} rows={2} placeholder="VD: Phim hành động Hàn Quốc, nhân vật chính là thám tử Kang…" />
              </Field>
              </Section>
            )}

            {tab === "voice" && (
              <Section title="Giọng đọc" icon={<Mic2 />} desc="CapCut & Edge TTS miễn phí · FPT.AI cao cấp · VieNeu offline">
              <VoiceSelect value={cfg.voice} onChange={(v) => set("voice", v)} />
                <div className="grid grid-cols-2 gap-3">
                <Field label="Tốc độ video & giọng">
                  <SimpleSelect value={cfg.video_speed} onChange={(v) => set("video_speed", v)} items={options.speeds} />
                </Field>
                </div>
              <ToggleRow label="Giữ đúng giọng đã chọn" checked={cfg.strict_voice} onChange={(v) => set("strict_voice", v)}
                desc="Bật: câu lỗi bị bỏ qua thay vì tự đổi sang giọng Edge dự phòng." />
              {mode === "review" && (
                <ToggleRow label="Phân vai nhiều giọng" checked={cfg.multi_voice} onChange={(v) => set("multi_voice", v)}
                  desc="AI nhận diện nhân vật, mỗi vai một giọng VieNeu (cần đăng nhập ChatGPT hoặc Gemini)." />
              )}
              </Section>
            )}

            {tab === "subs" && (
              <Section title="Phụ đề" icon={<Captions />} desc="Kiểu chữ, bố cục, vị trí phụ đề · che phụ đề gốc / logo">
              <ToggleRow label="Ghép phụ đề vào video" checked={cfg.burn_subtitles} onChange={(v) => set("burn_subtitles", v)} />
              <div className={cn("grid grid-cols-2 gap-3", !cfg.burn_subtitles && "pointer-events-none opacity-50")}>
                <Field label="Phong cách">
                  <SimpleSelect value={cfg.sub_style} onChange={(v) => set("sub_style", v)} items={Object.keys(options.sub_styles)} />
                </Field>
                <Field label="Bố cục dòng">
                  <SimpleSelect value={cfg.sub_layout} onChange={(v) => set("sub_layout", v)} items={Object.keys(options.sub_layouts)} />
                </Field>
                <Field label="Nguồn phụ đề">
                  <SimpleSelect value={cfg.sub_source} onChange={(v) => set("sub_source", v)} items={options.sub_sources} />
                </Field>
                <Field label={`Cách đáy: ${cfg.sub_margin_pct}%`}>
                  <Slider value={[cfg.sub_margin_pct]} min={2} max={40} step={1} onValueChange={([v]) => set("sub_margin_pct", v)} className="mt-2.5" />
                </Field>
              </div>
              {cfg.burn_subtitles && <SubtitleStyleEditor base={preset} custom={cfg.sub_custom} onChange={(c) => set("sub_custom", c)} />}
              <ToggleRow label="Che phụ đề gốc / logo" checked={cfg.remove_old_sub} onChange={(v) => set("remove_old_sub", v)}
                desc="Làm mờ dòng chữ cứng / logo có sẵn trong video gốc — kéo khung ngay trên khung hình để che vừa khít." />
              {cfg.remove_old_sub && (
                <CoverBoxEditor src={isLocalFile ? mediaUrl(inp) : undefined} resolution={cfg.target_resolution}
                  boxes={cfg.cover_boxes} onChange={(v) => set("cover_boxes", v)} />
              )}
              </Section>
            )}

            {tab === "post" && (
              <Section title="Hậu kỳ & thương hiệu" icon={<Wand2 />} desc="Tự hậu kỳ, kiểm tra lỗi, bài đăng AI · khung hình, logo, intro/outro">
              <ToggleRow label="Tự hậu kỳ sau khi lồng tiếng" checked={cfg.auto_post} onChange={(v) => set("auto_post", v)}
                desc="Tự căn đoạn hình khớp lời đọc + AI (ChatGPT/Gemini) sửa kịch bản, bỏ cảnh rác & tạo lại giọng câu đã sửa." />
              <ToggleRow label="Tự kiểm tra & sửa lỗi sau khi xuất" checked={cfg.auto_fix} onChange={(v) => set("auto_fix", v)}
                desc="Soi lại video vừa dựng (hình đứng, màn đen, lệch hình–lời, âm lượng, phụ đề) → AI sửa đúng cảnh lỗi rồi dựng lại." />
              <ToggleRow label="Tự viết bài đăng sau khi xuất" checked={cfg.auto_publish} onChange={(v) => set("auto_publish", v)}
                desc="AI viết tiêu đề, mô tả, hashtag cho YouTube · Shorts · TikTok · Facebook · Instagram + 3 thumbnail, lưu cạnh video." />
              <ToggleRow label="Lật ảnh xen kẽ" checked={cfg.mirror_video} onChange={(v) => set("mirror_video", v)}
                desc="Lật ngang các cảnh chẵn để giảm trùng nội dung với video gốc." />
              <Field label="Khung hình xuất">
                <Segmented value={cfg.target_resolution as "1920x1080" | "1280x720" | "1080x1920"} onChange={(v) => set("target_resolution", v)}
                  items={[{ value: "1920x1080", label: "16:9 · 1080p" }, { value: "1280x720", label: "16:9 · 720p" }, { value: "1080x1920", label: "9:16 · Shorts/TikTok" }]} />
              </Field>
              <Field label="Logo / watermark (tuỳ chọn)" hint="Ảnh PNG nền trong suốt cho đẹp nhất.">
                <PathInput value={cfg.watermark_path} onChange={(v) => set("watermark_path", v)} pick={bridge.pickImage} placeholder="Chọn ảnh logo" />
              </Field>
              {cfg.watermark_path && (
                <div className="grid grid-cols-[auto_1fr_1fr] items-end gap-4">
                  <Field label="Góc">
                    <Segmented value={cfg.watermark_corner as "Trên-Trái" | "Trên-Phải" | "Dưới-Trái" | "Dưới-Phải"} onChange={(v) => set("watermark_corner", v)}
                      items={[{ value: "Trên-Trái", label: "↖" }, { value: "Trên-Phải", label: "↗" }, { value: "Dưới-Trái", label: "↙" }, { value: "Dưới-Phải", label: "↘" }]} />
                  </Field>
                  <Field label={`Cỡ logo: ${cfg.watermark_size_pct}%`}>
                    <Slider value={[cfg.watermark_size_pct]} min={5} max={30} step={1} onValueChange={([v]) => set("watermark_size_pct", v)} className="mb-2" />
                  </Field>
                  <Field label={`Độ rõ: ${Math.round(cfg.watermark_opacity * 100)}%`}>
                    <Slider value={[cfg.watermark_opacity]} min={0.2} max={1} step={0.05} onValueChange={([v]) => set("watermark_opacity", +v.toFixed(2))} className="mb-2" />
                  </Field>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <Field label="Intro (tuỳ chọn)"><PathInput value={cfg.intro_path} onChange={(v) => set("intro_path", v)} pick={bridge.pickVideo} placeholder="Video mở đầu" /></Field>
                <Field label="Outro (tuỳ chọn)"><PathInput value={cfg.outro_path} onChange={(v) => set("outro_path", v)} pick={bridge.pickVideo} placeholder="Video kết thúc" /></Field>
              </div>
              </Section>
            )}

            {tab === "output" && (
              <Section title="Quy trình & xuất file" icon={<FolderOutput />} desc="Dừng ở bước nào để bạn xem lại · nơi lưu video">
              <ToggleRow label="Chạy hoàn toàn tự động" checked={!cfg.script_edit && !cfg.scene_preview}
                onChange={(v) => setCfg((c) => ({ ...c, script_edit: !v, scene_preview: !v, auto_post: v ? true : c.auto_post }))}
                desc="Không dừng chờ sửa kịch bản / nghe lại — từ video gốc ra thẳng video hoàn chỉnh." />
              <ToggleRow label="Xem & sửa kịch bản trước khi lồng tiếng" checked={cfg.script_edit} onChange={(v) => set("script_edit", v)}
                desc="Pipeline dừng lại để bạn sửa từng câu trong Studio." />
              <ToggleRow label="Nghe lại & xác nhận trước khi dựng video" checked={cfg.scene_preview} onChange={(v) => set("scene_preview", v)}
                desc="Nghe từng câu, sửa & tạo lại giọng, bỏ câu không ưng, thêm nhạc nền." />
              <Field label="Thư mục xuất">
                <PathInput value={cfg.out_dir} onChange={(v) => set("out_dir", v)} pick={bridge.pickFolder} />
              </Field>
              </Section>
            )}
          </div>
        </div>
      </div>

      {/* ---------- Summary ---------- */}
      <aside className="flex min-h-0 flex-col gap-4 overflow-y-auto pb-6">
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="mb-3 text-xs font-medium text-muted-foreground">Xem trước khung hình</p>
          <SubtitlePreview style={cfg.burn_subtitles ? style : undefined} marginPct={cfg.sub_margin_pct}
            text={cfg.burn_subtitles ? "Đây là dòng phụ đề mẫu cho video của bạn" : ""}
            poster={isLocalFile ? mediaUrl(inp) : undefined} />
          <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-xs">
            <dt className="text-muted-foreground">Chế độ</dt><dd className="text-right">{mode === "review" ? `Review ~${cfg.minutes} phút` : "Dịch & Reup"}</dd>
            <dt className="text-muted-foreground">Giọng</dt><dd className="truncate text-right">{cfg.voice}</dd>
            <dt className="text-muted-foreground">Whisper</dt><dd className="text-right">{cfg.whisper_model} · {cfg.device.startsWith("GPU") ? "GPU" : "CPU"}</dd>
            <dt className="text-muted-foreground">Phụ đề</dt><dd className="truncate text-right">{cfg.burn_subtitles ? cfg.sub_style : "Không ghép"}</dd>
            <dt className="text-muted-foreground">Khung hình</dt><dd className="text-right">{cfg.target_resolution === "1080x1920" ? "9:16 dọc" : cfg.target_resolution === "1280x720" ? "720p" : "1080p"}</dd>
            <dt className="text-muted-foreground">Hậu kỳ</dt><dd className="text-right">{[cfg.auto_post && "Tự hậu kỳ", cfg.auto_fix && "Tự sửa lỗi", cfg.auto_publish && "Bài đăng AI", !cfg.script_edit && !cfg.scene_preview && "Tự động hoàn toàn", cfg.watermark_path && "Logo", (cfg.intro_path || cfg.outro_path) && "Intro/Outro"].filter(Boolean).join(" · ") || "Thủ công"}</dd>
          </dl>
        </div>

        {issues.length > 0 && (
          <Alert className="border-warning/30 bg-warning/5">
            <AlertTriangle className="text-warning" />
            <AlertTitle>Cần kiểm tra</AlertTitle>
            <AlertDescription><ul className="list-disc pl-4">{issues.map((i) => <li key={i}>{i}</li>)}</ul></AlertDescription>
          </Alert>
        )}

        <Button size="lg" className="w-full text-sm font-semibold" disabled={starting || issues.length > 0} onClick={start}>
          {starting ? <Loader2 className="animate-spin" /> : <Rocket />}
          {mode === "review" ? "Bắt đầu tạo review" : "Bắt đầu dịch & reup"}
        </Button>
        <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><Settings2 className="size-3" />Mặc định có thể đổi trong Cài đặt.</p>
      </aside>
    </div>
  )
}
