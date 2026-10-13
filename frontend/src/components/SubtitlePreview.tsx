import type { SubStyle } from "@/lib/types"
import { cn } from "@/lib/utils"

/** 'white' | '#ffd400' | 'black@0.5' → CSS color */
export function cssColor(spec: string | undefined, fallbackAlpha = 1) {
  const named: Record<string, string> = { white: "#ffffff", black: "#000000", yellow: "#ffff00", red: "#ff0000" }
  let [c, a] = (spec ?? "white").split("@")
  c = named[c.toLowerCase()] ?? c
  const alpha = a !== undefined ? Number(a) : fallbackAlpha
  const hex = c.replace("#", "")
  if (hex.length !== 6) return c
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export function SubtitlePreview({ style, text = "Đây là dòng phụ đề mẫu cho video của bạn", className, compact, poster, marginPct }: {
  style?: SubStyle; text?: string; className?: string; compact?: boolean; poster?: string; marginPct?: number
}) {
  const s = style
  const scale = compact ? 0.55 : 1
  const border = (s?.sub_border_width ?? 3) * scale * 0.6
  const shadow = border > 0 && !s?.sub_box_enabled
    ? [-1, 0, 1].flatMap((x) => [-1, 0, 1].map((y) => `${x * border}px ${y * border}px 0 #000`)).join(",")
    : "none"
  return (
    <div className={cn("relative aspect-video w-full overflow-hidden rounded-lg bg-neutral-900", className)}>
      {poster
        ? <video src={poster} className="absolute inset-0 size-full object-contain" muted preload="metadata" />
        : <div className="absolute inset-0 bg-[linear-gradient(160deg,#3a3a40_0%,#202024_55%,#111113_100%)]" />}
      <div className="absolute inset-x-0 flex justify-center px-[9%]" style={{ bottom: `${(marginPct ?? (s?.sub_margin_v_pct ?? 0.06) * 100)}%` }}>
        <span
          className="text-center leading-snug font-bold"
          style={{
            fontFamily: `"${s?.sub_font_name ?? "Segoe UI"}", var(--font-sans)`,
            fontSize: `${(compact ? 11 : 17) * (s?.sub_font_size_factor ?? 1)}px`,
            color: cssColor(s?.sub_font_color),
            background: s?.sub_box_enabled ? cssColor(s?.sub_box_color, 0.5) : "transparent",
            padding: s?.sub_box_enabled ? `${(s.sub_box_padding ?? 12) * scale * 0.35}px ${(s.sub_box_padding ?? 12) * scale * 0.7}px` : 0,
            borderRadius: 4,
            textShadow: shadow,
            textTransform: s?.sub_text_transform === "uppercase" ? "uppercase" : "none",
          }}
        >
          {text}
        </span>
      </div>
    </div>
  )
}
