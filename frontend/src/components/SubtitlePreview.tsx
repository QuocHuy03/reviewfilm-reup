import { useEffect, useState } from "react"
import { ensureFont } from "@/lib/fonts"
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

export function SubtitlePreview({ style, text = "Đây là dòng phụ đề mẫu cho video của bạn", className, compact, poster, marginPct, centerPct, vertical }: {
  style?: SubStyle; text?: string; className?: string; compact?: boolean; poster?: string; marginPct?: number
  /** có → tâm phụ đề ở đúng % chiều cao này (phụ đề nằm giữa vùng che) thay vì cách đáy */
  centerPct?: number | null
  /** khung xuất dọc 9:16 (1080×1920) */
  vertical?: boolean
}) {
  const s = style
  // Mọi kích thước theo % bề ngang khung (cqw) — đúng tỉ lệ như video xuất 1920px: cỡ chữ = cao khung / 26 (core/video_editor
  // _fit_subtitle) → 1080/26/1920 ≈ 2.16cqw; viền / đệm quy từ px ở 1920px. Khung to nhỏ cỡ nào chữ cũng đúng tỉ lệ.
  const frameW = vertical ? 1080 : 1920, frameH = vertical ? 1920 : 1080
  const px = (v: number) => `${(v / frameW * 100).toFixed(3)}cqw`
  const border = s?.sub_border_width ?? 3
  const edge = cssColor(s?.sub_border_color || "black")
  const shadow = border > 0 && !s?.sub_box_enabled
    ? [-1, 0, 1].flatMap((x) => [-1, 0, 1].map((y) => `${px(x * border)} ${px(y * border)} 0 ${edge}`)).join(",")
    : "none"
  void compact
  const [, bump] = useState(0)
  useEffect(() => { ensureFont(s?.sub_font_name, () => bump((n) => n + 1)) }, [s?.sub_font_name])
  const blur = !!s?.sub_bg_blur && !s?.sub_box_enabled
  return (
    <div className={cn("relative w-full overflow-hidden rounded-lg bg-neutral-900 [container-type:inline-size]", vertical ? "mx-auto aspect-[9/16] max-w-[220px]" : "aspect-video", className)}>
      {poster
        ? <video src={poster} className="absolute inset-0 size-full object-contain" muted preload="metadata" />
        : <div className="absolute inset-0 bg-[linear-gradient(160deg,#3a3a40_0%,#202024_55%,#111113_100%)]" />}
      <div className={cn("absolute inset-x-0 flex justify-center px-[9%]", centerPct != null && "-translate-y-1/2")}
        style={centerPct != null ? { top: `${centerPct}%` } : { bottom: `${(marginPct ?? (s?.sub_margin_v_pct ?? 0.06) * 100)}%` }}>
        <span
          className="text-center leading-snug font-bold"
          style={{
            fontFamily: `"${s?.sub_font_name ?? "Segoe UI"}", var(--font-sans)`,
            fontSize: `${(frameH / 26 / frameW * 100 * (s?.sub_font_size_factor ?? 1)).toFixed(3)}cqw`,
            color: cssColor(s?.sub_font_color),
            background: s?.sub_box_enabled ? cssColor(s?.sub_box_color, 0.5) : "transparent",
            padding: s?.sub_box_enabled || blur ? `${px((s?.sub_box_padding ?? 12) * 0.5)} ${px(s?.sub_box_padding ?? 12)}` : 0,
            backdropFilter: blur ? "blur(8px)" : undefined,
            borderRadius: px(8),
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
