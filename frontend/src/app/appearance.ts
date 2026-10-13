import { useCallback, useEffect, useState } from "react"

/** Màu nhấn: chỉ đổi sắc độ (hue) của --primary/--ring/--brand… trong index.css (biến --accent-h). */
export const ACCENTS = {
  orange: { label: "Cam", hue: 42 },
  rose: { label: "Hồng", hue: 10 },
  violet: { label: "Tím", hue: 295 },
  blue: { label: "Xanh dương", hue: 255 },
  teal: { label: "Xanh ngọc", hue: 185 },
  green: { label: "Xanh lá", hue: 145 },
} as const
export type AccentKey = keyof typeof ACCENTS
export const UI_SCALES = [0.9, 1, 1.1, 1.25] as const

export type Appearance = { accent: AccentKey; scale: number }
const KEY = "rf-appearance"
const DEFAULT: Appearance = { accent: "orange", scale: 1 }
const EVENT = "rf-appearance-change"

function read(): Appearance {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "{}")
    return { accent: raw.accent in ACCENTS ? raw.accent : DEFAULT.accent, scale: UI_SCALES.includes(raw.scale) ? raw.scale : DEFAULT.scale }
  } catch {
    return DEFAULT
  }
}

function apply(a: Appearance) {
  const root = document.documentElement
  root.style.setProperty("--accent-h", String(ACCENTS[a.accent].hue))
  root.style.setProperty("zoom", String(a.scale))
}

/** Gọi 1 lần lúc khởi động (main.tsx) — tránh nháy màu cam trước khi React chạy. */
export function initAppearance() {
  apply(read())
}

export function useAppearance() {
  const [appearance, setState] = useState<Appearance>(read)
  useEffect(() => {
    const sync = () => setState(read())
    window.addEventListener(EVENT, sync)
    return () => window.removeEventListener(EVENT, sync)
  }, [])
  const update = useCallback((patch: Partial<Appearance>) => {
    const next = { ...read(), ...patch }
    try { localStorage.setItem(KEY, JSON.stringify(next)) } catch { /* chế độ riêng tư — vẫn áp dụng cho phiên này */ }
    apply(next)
    setState(next)
    window.dispatchEvent(new Event(EVENT))
  }, [])
  return { appearance, update }
}
