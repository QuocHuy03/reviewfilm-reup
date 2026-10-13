import { Bot, CheckCircle2, Laptop, Moon, Palette, Sun, Eye, EyeOff, KeyRound, Loader2, Monitor, Save, SlidersHorizontal, XCircle } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { AiAccounts } from "@/components/AiAccounts"
import { AboutPanel } from "@/components/ReleaseNotes"
import { UpdatePanel } from "@/components/UpdatePanel"
import { Field, PathInput, Section, Segmented } from "@/components/common"
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

export function SettingsPage() {
  const { options, settings, setSettings, system, refreshSystem } = useStore()
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [show, setShow] = useState<Record<string, boolean>>({})
  const [form, setForm] = useState<Settings | null>(settings)
  const [saving, setSaving] = useState(false)

  useEffect(() => { api.keys().then(setKeys).catch(() => {}) }, [])
  useEffect(() => { setForm(settings) }, [settings])
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
    <Tabs defaultValue="ai" className="flex flex-col gap-4 pb-8">
      <TabsList className="w-fit">
        <TabsTrigger value="ai"><Bot /> Tài khoản AI</TabsTrigger>
        <TabsTrigger value="look"><Palette /> Giao diện</TabsTrigger>
        <TabsTrigger value="voice"><KeyRound /> Key giọng đọc</TabsTrigger>
        <TabsTrigger value="defaults"><SlidersHorizontal /> Mặc định</TabsTrigger>
        <TabsTrigger value="system"><Monitor /> Hệ thống & cập nhật</TabsTrigger>
      </TabsList>

      <TabsContent value="ai" className="max-w-3xl"><AiAccounts /></TabsContent>

      <TabsContent value="look" className="max-w-3xl"><AppearancePanel /></TabsContent>

      <TabsContent value="voice" className="max-w-3xl">
        <Section title="API key giọng đọc" icon={<KeyRound />} desc="Tuỳ chọn — chỉ cần khi dùng giọng FPT.AI / ElevenLabs / Viettel. Lưu cục bộ trên máy"
          action={<Button size="sm" onClick={saveKeys} disabled={saving || Object.keys(draft).length === 0}>{saving ? <Loader2 className="animate-spin" /> : <Save />} Lưu key</Button>}>
          {keys.map((k) => (
            <Field key={k.name} label={k.label} hint={<span className="font-mono">{k.name}</span>}>
              <div className="flex gap-2">
                <Input type={show[k.name] ? "text" : "password"} className="font-mono text-xs placeholder:font-sans"
                  placeholder={k.set ? `Đã lưu: ${k.masked} — nhập để thay, để trống + Xoá để gỡ` : "Chưa cấu hình"}
                  value={draft[k.name] ?? ""} onChange={(e) => setDraft({ ...draft, [k.name]: e.target.value })} />
                <Button variant="ghost" size="icon" onClick={() => setShow({ ...show, [k.name]: !show[k.name] })}>{show[k.name] ? <EyeOff /> : <Eye />}</Button>
                {k.set && <Button variant="ghost" onClick={() => setDraft({ ...draft, [k.name]: "" })}>Xoá</Button>}
              </div>
            </Field>
          ))}
        </Section>
      </TabsContent>

      <TabsContent value="defaults" className="max-w-3xl">
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
        </Section>
      </TabsContent>

      <TabsContent value="system" className="grid max-w-5xl grid-cols-2 items-start gap-4">
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
