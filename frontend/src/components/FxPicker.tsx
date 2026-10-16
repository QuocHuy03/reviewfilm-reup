import { Field, ToggleRow } from "@/components/common"
import { Slider } from "@/components/ui/slider"
import { cn } from "@/lib/utils"

/** Hiệu ứng hình & chuyển cảnh — khớp backend video_editor (COLOR_PRESETS, TRANSITIONS). */
export type Fx = {
  transition: string; transition_duration: number; color_preset: string
  ken_burns: boolean; ken_burns_zoom: number; vignette: boolean
}
export const DEFAULT_FX: Fx = { transition: "none", transition_duration: 0.5, color_preset: "none", ken_burns: false, ken_burns_zoom: 0.08, vignette: false }

export const COLOR_PRESETS: { value: string; label: string; swatch: string }[] = [
  { value: "none", label: "Gốc", swatch: "linear-gradient(135deg,#6b7280,#d1d5db)" },
  { value: "cinematic", label: "Điện ảnh", swatch: "linear-gradient(135deg,#0f4c5c,#e09f3e)" },
  { value: "warm", label: "Ấm", swatch: "linear-gradient(135deg,#9a3412,#fbbf24)" },
  { value: "cool", label: "Lạnh", swatch: "linear-gradient(135deg,#1e3a8a,#7dd3fc)" },
  { value: "vivid", label: "Rực rỡ", swatch: "linear-gradient(135deg,#db2777,#22d3ee)" },
  { value: "vintage", label: "Cổ điển", swatch: "linear-gradient(135deg,#78350f,#d6c7a1)" },
  { value: "bw", label: "Đen trắng", swatch: "linear-gradient(135deg,#111,#eee)" },
]
export const TRANSITIONS: { value: string; label: string }[] = [
  { value: "none", label: "Không" }, { value: "random", label: "Ngẫu nhiên" }, { value: "fade", label: "Mờ dần" },
  { value: "dissolve", label: "Hoà tan" }, { value: "fadeblack", label: "Qua màn đen" }, { value: "slideleft", label: "Trượt" },
  { value: "smoothleft", label: "Lướt mượt" }, { value: "wipeleft", label: "Quét" }, { value: "zoomin", label: "Phóng to" },
  { value: "circleopen", label: "Mở tròn" }, { value: "radial", label: "Xoay kim" }, { value: "pixelize", label: "Vỡ điểm ảnh" },
]

/** Tóm tắt 1 dòng: "Chuyển cảnh: Mờ dần · Điện ảnh · Zoom chậm" ("" nếu không bật gì). */
export const fxSummary = (fx: Fx) => [
  fx.transition !== "none" && `Chuyển cảnh: ${TRANSITIONS.find((t) => t.value === fx.transition)?.label}`,
  fx.color_preset !== "none" && COLOR_PRESETS.find((c) => c.value === fx.color_preset)?.label,
  fx.ken_burns && "Zoom chậm", fx.vignette && "Tối viền",
].filter(Boolean).join(" · ")

/** Bộ chọn hiệu ứng. compact = cột hẹp (màn Hậu kỳ): ít cột hơn. */
export function FxPicker({ fx, onChange, compact }: { fx: Fx; onChange: (patch: Partial<Fx>) => void; compact?: boolean }) {
  return (
    <>
      <Field label="Chuyển cảnh" hint="Áp cho mọi chỗ nối giữa 2 cảnh. Ngẫu nhiên = mỗi chỗ nối một kiểu.">
        <div className={cn("grid gap-1.5", compact ? "grid-cols-3" : "grid-cols-4")}>
          {TRANSITIONS.map((t) => (
            <button key={t.value} type="button" onClick={() => onChange({ transition: t.value })}
              className={cn("rounded-md border px-2 py-1.5 text-[12px] transition",
                fx.transition === t.value ? "border-primary bg-primary/10 font-medium text-primary" : "border-border hover:bg-muted")}>
              {t.label}
            </button>
          ))}
        </div>
      </Field>
      {fx.transition !== "none" && (
        <Field label={`Thời gian chuyển: ${fx.transition_duration.toFixed(1)}s`}>
          <Slider value={[fx.transition_duration]} min={0.2} max={1.5} step={0.1} onValueChange={([v]) => onChange({ transition_duration: +v.toFixed(1) })} className="mt-2" />
        </Field>
      )}
      <Field label="Màu phim">
        <div className={cn("grid gap-1.5", compact ? "grid-cols-4" : "grid-cols-7")}>
          {COLOR_PRESETS.map((c) => (
            <button key={c.value} type="button" onClick={() => onChange({ color_preset: c.value })}
              className={cn("flex flex-col items-center gap-1 rounded-md border p-1.5 text-[11px] transition",
                fx.color_preset === c.value ? "border-primary bg-primary/10 font-medium text-primary" : "border-border hover:bg-muted")}>
              <span className="h-6 w-full rounded" style={{ background: c.swatch }} />
              {c.label}
            </button>
          ))}
        </div>
      </Field>
      <ToggleRow label="Zoom chậm (Ken Burns)" checked={fx.ken_burns} onChange={(v) => onChange({ ken_burns: v })}
        desc="Mỗi cảnh phóng to / thu nhỏ nhẹ xen kẽ — hình động hơn, giảm trùng với video gốc. Phụ đề không bị zoom theo." />
      {fx.ken_burns && (
        <Field label={`Mức zoom: ${Math.round(fx.ken_burns_zoom * 100)}%`}>
          <Slider value={[fx.ken_burns_zoom]} min={0.03} max={0.2} step={0.01} onValueChange={([v]) => onChange({ ken_burns_zoom: +v.toFixed(2) })} className="mt-2" />
        </Field>
      )}
      <ToggleRow label="Tối viền (vignette)" checked={fx.vignette} onChange={(v) => onChange({ vignette: v })}
        desc="Làm tối nhẹ 4 góc, dồn mắt người xem vào giữa khung hình." />
    </>
  )
}
