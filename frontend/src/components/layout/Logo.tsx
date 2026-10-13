import { cn } from "@/lib/utils"

/** Logo ReviewFilm: khung phim (lỗ phim 2 bên) + nút play — 1 tông theo màu primary của theme. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8", className)} aria-label="ReviewFilm">
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <g className="fill-primary-foreground" fillOpacity="0.4">
        {[6.5, 13.5, 20.5].map((y) => (
          <g key={y}>
            <rect x="4" y={y} width="3" height="5" rx="1" />
            <rect x="25" y={y} width="3" height="5" rx="1" />
          </g>
        ))}
      </g>
      <path className="fill-primary-foreground" d="M13 10.6c0-1 1.1-1.6 1.95-1.08l7.3 4.42c.82.5.82 1.68 0 2.17l-7.3 4.43c-.85.52-1.95-.1-1.95-1.09z" />
    </svg>
  )
}

export function LogoWordmark({ className }: { className?: string }) {
  return (
    <span className={cn("text-[13px] font-semibold tracking-tight", className)}>
      Review<span className="text-primary">Film</span>
    </span>
  )
}
