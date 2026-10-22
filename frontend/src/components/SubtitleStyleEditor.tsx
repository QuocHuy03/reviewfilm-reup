import { AlertTriangle, Check, ChevronDown, Plus, RotateCcw, Save, Search, Type } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Field, ToggleRow } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { api, bridge } from "@/lib/api"
import { ensureFont } from "@/lib/fonts"
import type { FontInfo, SubStyle } from "@/lib/types"
import { cn } from "@/lib/utils"

const COLOR_PRESETS = ["#ffffff", "#ffd400", "#ffea00", "#00e5ff", "#7cff6b", "#ff4d6d", "#000000"]

/** "white" | "#ffd400" | "black@0.5" → { hex, alpha } */
function parseColor(spec: string | undefined, fallbackAlpha = 1) {
  const named: Record<string, string> = { white: "#ffffff", black: "#000000", yellow: "#ffff00", red: "#ff0000" }
  const [c, a] = (spec ?? "white").split("@")
  const hex = (named[c.toLowerCase()] ?? c).toLowerCase()
  return { hex: /^#[0-9a-f]{6}$/.test(hex) ? hex : "#ffffff", alpha: a !== undefined ? Number(a) : fallbackAlpha }
}

let fontCache: FontInfo[] | null = null
function useFonts() {
  const [fonts, setFonts] = useState<FontInfo[]>(fontCache ?? [])
  const load = (refresh = false) => api.fonts(refresh).then((f) => { fontCache = f; setFonts(f) }).catch(() => {})
  useEffect(() => { if (!fontCache) load() }, [])
  return { fonts, reload: () => load(true) }
}

/** Chọn font: tìm kiếm, xem trước bằng chính font đó, lọc font có dấu tiếng Việt, thêm font riêng. */
function FontPicker({ value, onChange }: { value: string; onChange: (family: string) => void }) {
  const { fonts, reload } = useFonts()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const [viOnly, setViOnly] = useState(true)
  const box = useRef<HTMLDivElement>(null)
  const current = fonts.find((f) => f.family.toLowerCase() === value.toLowerCase())
  // font không có trong Windows (đóng gói / tự thêm): nạp cho trình duyệt để tên hiện đúng kiểu chữ
  useEffect(() => { ensureFont(value) }, [value])
  useEffect(() => { if (open) fonts.filter((f) => f.source === "bundled" || f.source === "custom").forEach((f) => ensureFont(f.family)) }, [open, fonts])

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    window.addEventListener("mousedown", close)
    return () => window.removeEventListener("mousedown", close)
  }, [open])

  const list = useMemo(() => fonts.filter((f) => (!viOnly || f.vi) && f.family.toLowerCase().includes(q.toLowerCase())), [fonts, q, viOnly])

  const addFont = async () => {
    const p = await bridge.pickFont()
    if (!p) return
    try {
      const r = await api.importFont(p)
      await reload()
      onChange(r.family)
      toast.success(`Đã thêm font ${r.family}`, { description: r.vi ? undefined : "Font này thiếu dấu tiếng Việt — chữ có dấu sẽ bị lỗi." })
    } catch (e) { toast.error((e as Error).message) }
  }

  return (
    <div ref={box} className="relative">
      <button type="button" onClick={() => setOpen(!open)}
        className="flex h-9 w-full items-center gap-2 rounded-md border border-input bg-transparent px-3 text-left text-sm shadow-xs hover:bg-muted/40">
        <Type className="size-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate" style={{ fontFamily: `"${value}", var(--font-sans)` }}>{value || "Chọn font"}</span>
        {current && !current.vi && <span title="Thiếu dấu tiếng Việt"><AlertTriangle className="size-3.5 text-warning" /></span>}
        <ChevronDown className="size-4 text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-border bg-popover shadow-lg">
          <div className="flex items-center gap-2 border-b border-border px-2.5 py-2">
            <Search className="size-3.5 text-muted-foreground" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Tìm trong ${fonts.length} font…`}
              className="min-w-0 flex-1 bg-transparent text-sm outline-none" />
          </div>
          <label className="flex cursor-pointer items-center gap-2 border-b border-border px-3 py-1.5 text-[11px] text-muted-foreground">
            <input type="checkbox" checked={viOnly} onChange={(e) => setViOnly(e.target.checked)} /> Chỉ font có đủ dấu tiếng Việt ({fonts.filter((f) => f.vi).length})
          </label>
          <div className="max-h-64 overflow-y-auto py-1">
            {/* font đóng gói lên đầu; nạp font không có sẵn trong Windows để tên hiện đúng kiểu chữ */}
            {[...list].sort((a, b) => Number(b.source === "bundled") - Number(a.source === "bundled")).map((f) => (
              <button key={f.family} type="button" onClick={() => { onChange(f.family); setOpen(false) }}
                className={cn("flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-muted", f.family === value && "bg-primary/10")}>
                <span className="min-w-0 flex-1 truncate text-[15px]" style={{ fontFamily: `"${f.family}"` }}>{f.family}</span>
                {f.source === "custom" && <span className="rounded bg-primary/15 px-1 text-[9px] text-primary">đã thêm</span>}
                {f.source === "bundled" && <span className="rounded bg-success/15 px-1 text-[9px] text-success">có sẵn</span>}
                {!f.vi && <span className="text-[10px] text-warning">thiếu dấu</span>}
                {f.family === value && <Check className="size-3.5 text-primary" />}
              </button>
            ))}
            {!list.length && <p className="px-3 py-4 text-center text-xs text-muted-foreground">Không có font phù hợp</p>}
          </div>
          {bridge.available() && (
            <button type="button" onClick={addFont} className="flex w-full items-center gap-2 border-t border-border px-3 py-2 text-xs text-primary hover:bg-muted">
              <Plus className="size-3.5" /> Thêm font từ máy (.ttf / .otf)
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function ColorField({ label, value, onChange, alpha, onAlpha }: {
  label: string; value: string; onChange: (hex: string) => void; alpha?: number; onAlpha?: (a: number) => void
}) {
  return (
    <Field label={label}>
      <div className="flex items-center gap-1.5">
        <label className="relative size-8 shrink-0 cursor-pointer overflow-hidden rounded-md border border-border" style={{ background: value }}>
          <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" />
        </label>
        {COLOR_PRESETS.map((c) => (
          <button key={c} type="button" onClick={() => onChange(c)} title={c}
            className={cn("size-5 rounded-full border", value === c ? "border-primary ring-2 ring-primary/40" : "border-border")} style={{ background: c }} />
        ))}
      </div>
      {onAlpha && alpha !== undefined && (
        <div className="mt-1 flex items-center gap-2">
          <span className="w-16 text-[10.5px] text-muted-foreground">Độ đậm {Math.round(alpha * 100)}%</span>
          <Slider value={[alpha]} min={0.1} max={1} step={0.05} onValueChange={([a]) => onAlpha(a)} />
        </div>
      )}
    </Field>
  )
}

/**
 * Tuỳ chỉnh chữ phụ đề, đè lên preset: font, cỡ, màu, viền, nền, viết hoa.
 * `custom` chỉ chứa các trường đã đổi → gửi backend dưới tên sub_custom.
 */
export function SubtitleStyleEditor({ base, custom, onChange }: {
  base?: SubStyle; custom: Partial<SubStyle>; onChange: (c: Partial<SubStyle>) => void
}) {
  const { setSettings } = useStore()
  const s = { ...base, ...custom } as SubStyle
  const set = (patch: Partial<SubStyle>) => onChange({ ...custom, ...patch })
  const text = parseColor(s.sub_font_color)
  const bg = parseColor(s.sub_box_color, 0.5)

  const saveDefault = async () => {
    try { setSettings(await api.saveSettings({ sub_custom: custom })); toast.success("Đã lưu kiểu chữ làm mặc định") }
    catch (e) { toast.error((e as Error).message) }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/20 p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">Tuỳ chỉnh chữ</span>
        <div className="flex gap-1">
          <Button size="xs" variant="ghost" disabled={!Object.keys(custom).length} onClick={() => onChange({})} title="Về đúng preset"><RotateCcw /> Đặt lại</Button>
          <Button size="xs" variant="ghost" onClick={saveDefault} title="Dùng kiểu chữ này cho các job sau"><Save /> Lưu mặc định</Button>
        </div>
      </div>
      <Field label="Font chữ"><FontPicker value={s.sub_font_name ?? "Segoe UI"} onChange={(f) => set({ sub_font_name: f })} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={`Cỡ chữ: ${Math.round((s.sub_font_size_factor ?? 1) * 100)}%`}>
          <Slider value={[s.sub_font_size_factor ?? 1]} min={0.6} max={2} step={0.05} onValueChange={([v]) => set({ sub_font_size_factor: +v.toFixed(2) })} className="mt-2" />
        </Field>
        <Field label={`Viền chữ: ${s.sub_border_width ?? 3}px`}>
          <Slider value={[s.sub_border_width ?? 3]} min={0} max={8} step={1} onValueChange={([v]) => set({ sub_border_width: v })} className="mt-2" />
        </Field>
      </div>
      <ColorField label="Màu chữ" value={text.hex} onChange={(hex) => set({ sub_font_color: hex })} />
      {(s.sub_border_width ?? 3) > 0 && (
        <ColorField label="Màu viền" value={parseColor(s.sub_border_color || "black").hex} onChange={(hex) => set({ sub_border_color: hex })} />
      )}
      <ToggleRow label="Nền mờ sau chữ" checked={!!s.sub_bg_blur} onChange={(v) => set({ sub_bg_blur: v })}
        desc="Làm mờ hình ngay phía sau dòng chữ (khung vừa khít chữ) — chữ nổi rõ mà không cần nền màu, che luôn chữ cũ nằm cùng chỗ." />
      <ToggleRow label="Nền sau chữ" checked={!!s.sub_box_enabled} onChange={(v) => set({ sub_box_enabled: v })} />
      {s.sub_box_enabled && (
        <ColorField label="Màu nền" value={bg.hex} alpha={bg.alpha}
          onChange={(hex) => set({ sub_box_color: `${hex}@${bg.alpha}` })} onAlpha={(a) => set({ sub_box_color: `${bg.hex}@${+a.toFixed(2)}` })} />
      )}
      <ToggleRow label="VIẾT HOA toàn bộ" checked={s.sub_text_transform === "uppercase"} onChange={(v) => set({ sub_text_transform: v ? "uppercase" : "none" })} />
    </div>
  )
}
