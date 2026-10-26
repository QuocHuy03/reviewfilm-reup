import { Bot, CheckCircle2, Eye, EyeOff, KeyRound, Laptop, Loader2, LogIn, Monitor, Moon, Palette, Save, SlidersHorizontal, Sun, XCircle } from "lucide-react"
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
import type { ApiKey, Settings } from "@/lib/types"
import { SimpleSelect } from "./CreatePage"

const SETTING_TABS = [
  { value: "ai", label: "Tài khoản AI", desc: "ChatGPT / Gemini viết kịch bản, dịch", icon: <Bot /> },
  { value: "voice", label: "Giọng đọc", desc: "Key FPT, Viettel… · tài khoản CapCut", icon: <KeyRound /> },
  { value: "defaults", label: "Mặc định", desc: "Thư mục xuất, Whisper, giọng mặc định", icon: <SlidersHorizontal /> },
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

      <TabsContent value="defaults">
        <Section title="Mặc định" icon={<SlidersHorizontal />} desc="Giá trị điền sẵn khi tạo job mới"
          action={<Button size="sm" onClick={saveDefaults}><Save /> Lưu</Button>}>
          <Field label="Thư mục xuất"><PathInput value={form.output_dir} onChange={(v) => setForm({ ...form, output_dir: v })} pick={bridge.pickFolder} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Whisper model"><SimpleSelect value={form.whisper_model} onChange={(v) => setForm({ ...form, whisper_model: v })} items={options.whisper_models} /></Field>
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
