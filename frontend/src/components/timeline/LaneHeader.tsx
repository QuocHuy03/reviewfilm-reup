import { Minus, Plus } from "lucide-react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

/** 1 nút nhỏ ở cột icon đầu làn (khoá · mắt · loa …). null = chừa trống để các cột luôn thẳng hàng. */
export type LaneSlot = { title: string; icon: ReactNode; onClick: () => void; on?: boolean; danger?: boolean; extra?: ReactNode } | null

/**
 * Đầu làn kiểu NLE (CapCut / Premiere): vạch màu · TÊN IN HOA (+ dòng đếm nhỏ) · các cột icon cố định bên phải.
 * Bấm tên = thu gọn / mở rộng làn (nếu có onToggle). Mọi làn cùng số cột → icon thẳng hàng từ trên xuống.
 */
export function LaneHeader({ label, stat, accent, height, collapsed, dim, onToggle, toggleTitle, slots }: {
  label: string; stat?: ReactNode; accent: string; height: number; collapsed?: boolean; dim?: boolean
  onToggle?: () => void; toggleTitle?: string; slots: LaneSlot[]
}) {
  const name = (
    <span className="flex min-w-0 flex-col leading-tight">
      <span className={cn("truncate font-semibold tracking-wider whitespace-nowrap uppercase", collapsed ? "text-[9.5px]" : "text-[11.5px]",
        dim ? "text-white/30 line-through" : "text-white/80")}>{label}</span>
      {!collapsed && stat && <span className="tabular truncate text-[10px] whitespace-nowrap text-white/40">{stat}</span>}
    </span>
  )
  return (
    <div className="relative flex items-center gap-2 overflow-hidden border-b border-white/10 pr-1.5 pl-3" style={{ height }}>
      <span className={cn("absolute left-0 w-[3px] rounded-r", collapsed ? "inset-y-1" : "inset-y-2", accent)} />
      {onToggle
        ? <button onClick={onToggle} title={toggleTitle} className="flex min-w-0 flex-1 items-center rounded py-0.5 text-left hover:bg-white/5">{name}</button>
        : <div className="flex min-w-0 flex-1 items-center">{name}</div>}
      <div className={cn("flex shrink-0 items-center", collapsed && "scale-90")}>
        {slots.map((s, i) => s ? (
          <span key={i} className="relative">
            <button title={s.title} aria-pressed={s.on} onClick={s.onClick}
              className={cn("flex size-6 items-center justify-center rounded-md [&_svg]:size-[15px]",
                s.on ? (s.danger ? "bg-red-500/20 text-red-300 hover:bg-red-500/30" : "bg-amber-400/20 text-amber-200 hover:bg-amber-400/30")
                  : "text-white/45 hover:bg-white/10 hover:text-white")}>
              {s.icon}
            </button>
            {s.extra}
          </span>
        ) : <span key={i} className="size-6" />)}
      </div>
    </div>
  )
}

/** Thu phóng gọn kiểu NLE: −  100%  +  Vừa khung (100% = mức mặc định). */
export function ZoomControl({ pps, setPps, min, max, base, onFit }: {
  pps: number; setPps: (f: (p: number) => number) => void; min: number; max: number; base: number; onFit: () => void
}) {
  const btn = "flex size-6 items-center justify-center rounded-md text-white/60 hover:bg-white/10 hover:text-white [&_svg]:size-3.5"
  return (
    <div className="flex items-center gap-0.5 text-[11.5px] text-white/70" title="Thu phóng timeline (Ctrl + lăn chuột)">
      <button className={btn} title="Thu nhỏ" onClick={() => setPps((p) => Math.max(min, p / 1.25))}><Minus /></button>
      <span className="tabular w-11 text-center font-mono">{((v) => (Math.abs(v - 100) <= 3 ? 100 : v))(Math.round((pps / base) * 100))}%</span>
      <button className={btn} title="Phóng to" onClick={() => setPps((p) => Math.min(max, p * 1.25))}><Plus /></button>
      <button className="ml-1 rounded-md px-1.5 py-0.5 font-medium text-white/70 hover:bg-white/10 hover:text-white" title="Vừa khung — thấy hết video" onClick={onFit}>
        Vừa khung
      </button>
    </div>
  )
}

/** Mốc thước thời gian dạng 00:01.00 */
export function fmtRuler(t: number) {
  const m = Math.floor(t / 60)
  const s = t - m * 60
  return `${String(m).padStart(2, "0")}:${s.toFixed(2).padStart(5, "0")}`
}
