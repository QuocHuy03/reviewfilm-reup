import { Bot, CheckCircle2, Eye, EyeOff, KeyRound, Laptop, Loader2, LogIn, Monitor, Moon, Palette, Save, SlidersHorizontal, Sun, XCircle, Cpu, RefreshCw, Wand2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { AiAccounts } from "@/components/AiAccounts"
import { AboutPanel } from "@/components/ReleaseNotes"
import { UpdatePanel } from "@/components/UpdatePanel"
import { Field, ToggleRow, PathInput, Section, Segmented } from "@/components/common"
import { ACCENTS, UI_SCALES, useAppearance, type AccentKey } from "@/app/appearance"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"
import { VoiceSelect } from "@/components/VoiceSelect"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Input } from "@/components/ui/input"
import { api, bridge } from "@/lib/api"
import type { ApiKey, HardwareProfile, Settings } from "@/lib/types"
import { SimpleSelect } from "./CreatePage"
import { ASR_HINT, ASR_LABELS, asrLabel } from "@/lib/asr"

const SETTING_TABS = [
  { value: "ai", label: "Tài khoản AI", desc: "ChatGPT / Gemini viết kịch bản, dịch", icon: <Bot /> },
  { value: "voice", label: "Giọng đọc", desc: "Key FPT, Viettel… · tài khoản CapCut", icon: <KeyRound /> },
  { value: "defaults", label: "Mặc định", desc: "Thư mục xuất, nhận dạng giọng, giọng mặc định", icon: <SlidersHorizontal /> },
  { value: "look", label: "Giao diện", desc: "Sáng/tối, màu nhấn, cỡ chữ", icon: <Palette /> },
  { value: "system", label: "Hệ thống & cập nhật", desc: "Phiên bản, cập nhật, nhật ký", icon: <Monitor /> },
]

export function SettingsPage() {
  const { options, settings, setSettings, system, refreshSystem } = useStore()
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [show, setShow] = useState<Record<string, boolean>>({})
  const [form, setForm] = useState<Settings | null>(settings)
  const [saving, setSaving] = useState(false)

  useEffect(() => { api.keys().then(setKeys).catch(() => {}) }, [])
  useEffect(() => { setForm(settings) }, [settings])

  const [capcutBusy, setCapcutBusy] = useState(false)
  const capcutLogin = async () => {
    setCapcutBusy(true)
    try {
      const cookie = await window.rf!.capcut.login()
      setKeys(await api.saveKeys({ CAPCUT_COOKIE: cookie })); refreshSystem()
      toast.success("Đã đăng nhập CapCut — cookie đã lưu tự động")
    } catch (e) { toast.error("Chưa lấy được cookie CapCut", { description: (e as Error).message }) }
    finally { setCapcutBusy(false) }
  }
  const capcutLogout = async () => {
    await window.rf?.capcut.logout()
    setKeys(await api.saveKeys({ CAPCUT_COOKIE: "" })); refreshSystem()
    toast("Đã đăng xuất CapCut — giọng CapCut vẫn dùng được (không cookie)")
  }

  if (!options || !form) return null

  const saveKeys = async () => {
    setSaving(true)
    try {
      const values = Object.fromEntries(Object.entries(draft).filter(([, v]) => v !== undefined))
      setKeys(await api.saveKeys(values)); setDraft({}); refreshSystem(); toast.success("Đã lưu API key vào backend/.env")
    } catch (e) { toast.error((e as Error).message) } finally { setSaving(false) }
  }
  const saveDefaults = async () => {
    try { const s = await api.saveSettings(form); setSettings(s); refreshSystem(); toast.success("Đã lưu cài đặt") } catch (e) { toast.error((e as Error).message) }
  }

  return (
    <Tabs defaultValue="ai" orientation="vertical" className="grid grid-cols-[230px_minmax(0,1fr)] items-start gap-6 pb-8">
      <TabsList className="sticky top-0 w-full items-stretch gap-0.5 bg-transparent p-0">
        {SETTING_TABS.map((t) => (
          <TabsTrigger key={t.value} value={t.value} className="h-auto items-start gap-2.5 rounded-lg px-3 py-2 text-left data-active:bg-muted">
            <span className="mt-0.5 [&_svg]:size-4">{t.icon}</span>
            <span className="flex flex-col">
              <span className="text-[13px] font-medium text-foreground">{t.label}</span>
              <span className="text-[11px] font-normal whitespace-normal text-muted-foreground">{t.desc}</span>
            </span>
          </TabsTrigger>
        ))}
      </TabsList>

      <TabsContent value="ai"><AiAccounts /></TabsContent>

      <TabsContent value="look"><AppearancePanel /></TabsContent>

      <TabsContent value="voice">
        <Section title="API key giọng đọc" icon={<KeyRound />} desc="Tuỳ chọn — chỉ cần khi dùng giọng FPT.AI / ElevenLabs / Viettel / CapCut. Lưu cục bộ trên máy"
          action={<Button size="sm" onClick={saveKeys} disabled={saving || Object.keys(draft).length === 0}>{saving ? <Loader2 className="animate-spin" /> : <Save />} Lưu key</Button>}>
          {keys.map((k) => (
            <Field key={k.name} label={k.label} hint={k.name === "CAPCUT_COOKIE"
              ? <><b>Không bắt buộc</b> — giọng CapCut chạy được cả khi chưa đăng nhập. Bấm <b>Đăng nhập CapCut</b>: đăng nhập xong app tự lấy cookie (dùng khi CapCut bắt đăng nhập).</>
              : <span className="font-mono">{k.name}</span>}>
              <div className="flex gap-2">
                <Input type={show[k.name] ? "text" : "password"} className="font-mono text-xs placeholder:font-sans"
                  placeholder={k.set ? `Đã lưu: ${k.masked} — nhập để thay, để trống + Xoá để gỡ` : "Chưa cấu hình"}
                  value={draft[k.name] ?? ""} onChange={(e) => setDraft({ ...draft, [k.name]: e.target.value })} />
                <Button variant="ghost" size="icon" onClick={() => setShow({ ...show, [k.name]: !show[k.name] })}>{show[k.name] ? <EyeOff /> : <Eye />}</Button>
                {k.name === "CAPCUT_COOKIE" && window.rf?.capcut && (
                  <Button variant="outline" disabled={capcutBusy} title="Mở capcut.com, đăng nhập xong app tự lấy và lưu cookie" onClick={capcutLogin}>
                    {capcutBusy ? <Loader2 className="animate-spin" /> : <LogIn />} {k.set ? "Đăng nhập lại" : "Đăng nhập CapCut"}
                  </Button>
                )}
                {k.set && <Button variant="ghost" onClick={() => (k.name === "CAPCUT_COOKIE" ? capcutLogout() : setDraft({ ...draft, [k.name]: "" }))}>
                  {k.name === "CAPCUT_COOKIE" ? "Đăng xuất" : "Xoá"}</Button>}
              </div>
            </Field>
          ))}
        </Section>
      </TabsContent>

      <TabsContent value="defaults" className="flex flex-col gap-4">
        <HardwareCard onApply={(r) => { setForm({ ...form, ...r }); toast.success("Đã điền cấu hình hợp với máy", { description: "Bấm Lưu để áp dụng." }) }} />
        <Section title="Mặc định" icon={<SlidersHorizontal />} desc="Giá trị điền sẵn khi tạo job mới"
          action={<Button size="sm" onClick={saveDefaults}><Save /> Lưu</Button>}>
          <Field label="Thư mục xuất"><PathInput value={form.output_dir} onChange={(v) => setForm({ ...form, output_dir: v })} pick={bridge.pickFolder} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Nhận dạng giọng nói" hint={ASR_HINT}><SimpleSelect labels={ASR_LABELS} value={form.whisper_model} onChange={(v) => setForm({ ...form, whisper_model: v })} items={options.whisper_models} /></Field>
            <Field label="Thiết bị" hint={system && !system.gpu ? "Máy không có GPU NVIDIA — nên chọn CPU" : undefined}>
              <SimpleSelect value={form.device} onChange={(v) => setForm({ ...form, device: v })} items={options.devices} />
            </Field>
            <Field label="Phong cách phụ đề"><SimpleSelect value={form.sub_style} onChange={(v) => setForm({ ...form, sub_style: v })} items={Object.keys(options.sub_styles)} /></Field>
            <Field label="Bố cục dòng"><SimpleSelect value={form.sub_layout} onChange={(v) => setForm({ ...form, sub_layout: v })} items={Object.keys(options.sub_layouts)} /></Field>
          </div>
          <Field label="Giọng đọc mặc định"><VoiceSelect value={form.voice} onChange={(v) => setForm({ ...form, voice: v })} /></Field>
          <ToggleRow label="Chế độ nhẹ máy" checked={!!form.light_mode} onChange={(v) => setForm({ ...form, light_mode: v })}
            desc={form.light_mode
              ? "Đang bật: tool chỉ dùng khoảng một nửa CPU, dựng 1 cảnh mỗi lượt — chậm hơn nhưng vừa chạy vừa làm việc khác thoải mái."
              : "Tắt (khuyên dùng): tool vẫn chạy ưu tiên thấp và chừa lõi cho máy — máy không đơ. Bật khi cần dùng máy nặng song song (chơi game, dựng video khác…)."} />
          <NotifyToggle />
          <GpuEncodeToggle checked={form.gpu_encode !== false} onChange={(v) => setForm({ ...form, gpu_encode: v })} />
        </Section>
      </TabsContent>

      <TabsContent value="system" className="grid grid-cols-2 items-start gap-4">
        <div className="flex flex-col gap-4">
          <UpdatePanel />
          <Section title="Hệ thống" icon={<Monitor />}>
            {system && (
              <dl className="flex flex-col gap-2.5 text-xs">
                <Row label="Python" value={system.python} />
                <Row label="GPU" value={system.gpu || "Không phát hiện"} />
                <Row label="Ổ đĩa xuất trống" value={`${system.free_gb} GB`} />
                <Row label="ffmpeg" ok={system.ffmpeg} />
                <Row label="ffprobe" ok={system.ffprobe} />
              </dl>
            )}
          </Section>
        </div>
        <AboutPanel />
      </TabsContent>
    </Tabs>
  )
}

/** Chủ đề app: sáng/tối/theo hệ thống, màu nhấn, cỡ giao diện. Lưu trên máy, áp dụng ngay. */
function AppearancePanel() {
  const { theme, setTheme } = useTheme()
  const { appearance, update } = useAppearance()
  return (
    <Section title="Giao diện" icon={<Palette />} desc="Áp dụng ngay, lưu trên máy này">
      <Field label="Chế độ">
        <Segmented value={(theme ?? "dark") as "light" | "dark" | "system"} onChange={setTheme}
          items={[{ value: "light", label: "Sáng", icon: <Sun /> }, { value: "dark", label: "Tối", icon: <Moon /> }, { value: "system", label: "Theo hệ thống", icon: <Laptop /> }]} />
      </Field>
      <Field label="Màu nhấn">
        <div className="flex flex-wrap gap-2">
          {(Object.keys(ACCENTS) as AccentKey[]).map((k) => (
            <button key={k} onClick={() => update({ accent: k })} title={ACCENTS[k].label}
              className={cn("flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition",
                appearance.accent === k ? "border-foreground/40 bg-muted" : "border-border hover:bg-muted/50")}>
              <span className="size-4 rounded-full" style={{ background: `oklch(0.65 0.18 ${ACCENTS[k].hue})` }} />
              {ACCENTS[k].label}
              {appearance.accent === k && <CheckCircle2 className="size-3.5" />}
            </button>
          ))}
        </div>
      </Field>
      <Field label="Cỡ giao diện" hint="Phóng to/thu nhỏ toàn bộ chữ và nút — tiện cho màn hình lớn hoặc nhỏ.">
        <Segmented value={String(appearance.scale)} onChange={(v) => update({ scale: Number(v) })}
          items={UI_SCALES.map((s) => ({ value: String(s), label: `${Math.round(s * 100)}%` }))} />
      </Field>
    </Section>
  )
}

function Row({ label, value, ok }: { label: string; value?: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate font-medium">
        {value ?? (ok ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-destructive" />)}
      </dd>
    </div>
  )
}

/** Thông báo Windows khi job xong / lỗi / chờ duyệt (lưu trên máy, áp dụng ngay). */
function NotifyToggle() {
  const [on, setOn] = useState(() => { try { return localStorage.getItem("rf.notify") !== "0" } catch { return true } })
  return (
    <ToggleRow label="Thông báo khi job xong" checked={on}
      onChange={(v) => { setOn(v); try { localStorage.setItem("rf.notify", v ? "1" : "0") } catch { /* bỏ qua */ } }}
      desc={on ? "Hiện thông báo Windows khi job xong, lỗi hoặc chờ bạn duyệt (lúc đang làm việc khác). Bấm thông báo để mở job." : "Chỉ báo trong app."} />
  )
}

/** Dựng video bằng GPU NVIDIA (NVENC): bật / tắt + trạng thái thật trên máy (card, driver, lý do không dùng được) + cách sửa. */
function GpuEncodeToggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  const [st, setSt] = useState<Awaited<ReturnType<typeof api.encoderStatus>> | null>(null)
  const [busy, setBusy] = useState(false)
  const check = (force = false) => { setBusy(true); api.encoderStatus(force).then(setSt).catch(() => setSt(null)).finally(() => setBusy(false)) }
  useEffect(() => { check() }, [])
  const ready = !!st && !!st.gpu && !st.reason
  const oldDriver = !!st?.reason && /Driver NVIDIA .* quá cũ/.test(st.reason)
  return (
    <div className="flex flex-col gap-2">
      <ToggleRow label="Dựng bằng GPU (NVENC)" checked={checked} onChange={onChange}
        desc={checked ? "Máy có card NVIDIA thì mã hoá video bằng GPU — nhanh hơn nhiều, máy đỡ nóng. Lỗi thì tự chuyển sang CPU." : "Luôn mã hoá bằng CPU."} />
      {checked && (
        <div className={cn("flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-xs",
          ready ? "border-success/30 bg-success/5" : st?.gpu ? "border-warning/40 bg-warning/5" : "border-border bg-muted/30")}>
          {busy ? <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-muted-foreground" />
            : ready ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : <XCircle className={cn("mt-0.5 size-4 shrink-0", st?.gpu ? "text-warning" : "text-muted-foreground")} />}
          <div className="min-w-0 flex-1 leading-relaxed">
            <p className="font-medium">{busy ? "Đang kiểm tra GPU…" : ready ? `Đang dùng GPU: ${st!.gpu}` : st?.gpu ? `${st.gpu} — đang dựng bằng CPU` : "Dựng bằng CPU"}</p>
            {!busy && st && (
              <p className="text-muted-foreground">
                {ready ? `Driver ${st.driver}.` : st.reason}
                {oldDriver && <>. Cập nhật driver NVIDIA (miễn phí): mở <b>NVIDIA App</b> / <b>GeForce Experience</b> → Drivers → tải bản mới nhất, hoặc tải từ trang NVIDIA. Cập nhật xong bấm "Kiểm tra lại".</>}
              </p>
            )}
            <div className="mt-1.5 flex gap-1.5">
              <button className="rounded-md border border-border px-2 py-0.5 text-[11px] hover:bg-muted disabled:opacity-50" disabled={busy} onClick={() => check(true)}>Kiểm tra lại</button>
              {oldDriver && (
                <button className="rounded-md border border-border px-2 py-0.5 text-[11px] hover:bg-muted" onClick={() => window.open("https://www.nvidia.com/Download/index.aspx")}>
                  Mở trang tải driver NVIDIA
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** Cấu hình máy (dò tự động) + nút áp dụng cài đặt đề xuất: Whisper GPU/CPU, model vừa VRAM, mã hoá GPU, chế độ nhẹ máy. */
function HardwareCard({ onApply }: { onApply: (r: HardwareProfile["recommend"]) => void }) {
  const [hw, setHw] = useState<HardwareProfile | null>(null)
  const [busy, setBusy] = useState(true)
  const load = (force = false) => { setBusy(true); api.hardware(force).then(setHw).catch(() => setHw(null)).finally(() => setBusy(false)) }
  useEffect(() => { load() }, [])
  const Chip = ({ ok, children }: { ok: boolean; children: React.ReactNode }) => (
    <span className={cn("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium", ok ? "bg-success/12 text-success" : "bg-muted text-muted-foreground")}>
      {ok ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}{children}
    </span>
  )
  return (
    <Section title="Cấu hình máy" icon={<Cpu />} desc="App tự dò phần cứng và đề xuất cài đặt chạy nhanh, ổn định nhất cho máy này"
      action={<div className="flex gap-1.5">
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => load(true)}>{busy ? <Loader2 className="animate-spin" /> : <RefreshCw />} Dò lại</Button>
        <Button size="sm" disabled={busy || !hw} onClick={() => hw && onApply(hw.recommend)}><Wand2 /> Áp dụng đề xuất</Button>
      </div>}>
      {busy && !hw ? <p className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> Đang dò cấu hình máy…</p> : hw && (
        <div className="flex flex-col gap-3">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[12.5px] sm:grid-cols-4">
            <div><dt className="text-[11px] text-muted-foreground">CPU</dt><dd className="font-medium">{hw.cpu_threads} luồng</dd></div>
            <div><dt className="text-[11px] text-muted-foreground">RAM</dt><dd className="font-medium">{hw.ram_gb ? `${hw.ram_gb} GB` : "—"}</dd></div>
            <div className="col-span-2"><dt className="text-[11px] text-muted-foreground">Card đồ hoạ</dt>
              <dd className="truncate font-medium">{hw.gpu ? `${hw.gpu.replace(/^NVIDIA /, "")} · ${hw.vram_gb} GB · driver ${hw.driver}` : "Không có card NVIDIA"}</dd></div>
          </dl>
          <div className="flex flex-wrap gap-1.5">
            <Chip ok={hw.whisper_cuda}>Nhận dạng giọng {hw.whisper_cuda ? `chạy GPU (${hw.whisper_compute})` : "chạy CPU"}</Chip>
            <Chip ok={hw.nvenc}>Mã hoá video {hw.nvenc ? "GPU NVENC" : "CPU"}</Chip>
          </div>
          <div className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs leading-relaxed">
            <p className="mb-1 font-medium">Đề xuất cho máy này: Thiết bị <b>{hw.recommend.device}</b> · Nhận dạng <b>{asrLabel(hw.recommend.whisper_model)}</b>
              {" · "}Dựng GPU <b>{hw.recommend.gpu_encode ? "bật" : "tắt"}</b> · Chế độ nhẹ máy <b>{hw.recommend.light_mode ? "bật" : "tắt"}</b></p>
            <ul className="list-disc pl-4 text-muted-foreground">{hw.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>
        </div>
      )}
    </Section>
  )
}
