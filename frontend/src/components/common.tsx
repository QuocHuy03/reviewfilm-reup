import { FolderOpen } from "lucide-react"
import type { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { bridge } from "@/lib/api"
import type { JobKind, JobStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

export function Section({ title, icon, desc, action, children, className }: {
  title: string; icon?: ReactNode; desc?: string; action?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={cn("rounded-xl border border-border bg-card", className)}>
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
        {icon && <span className="flex size-7 items-center justify-center rounded-md bg-muted text-primary [&_svg]:size-3.5">{icon}</span>}
        <div className="min-w-0 flex-1">
          <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
          {desc && <p className="truncate text-xs text-muted-foreground">{desc}</p>}
        </div>
        {action}
      </div>
      <div className="flex flex-col gap-4 p-4">{children}</div>
    </section>
  )
}

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label className="text-xs font-medium text-muted-foreground">{label}</Label>
      {children}
      {hint && <p className="text-[11px] leading-relaxed text-muted-foreground/80">{hint}</p>}
    </div>
  )
}

export function ToggleRow({ label, desc, checked, onChange, disabled }: {
  label: string; desc?: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean
}) {
  return (
    <label className={cn("flex cursor-pointer items-start justify-between gap-4 rounded-lg px-1 py-0.5", disabled && "cursor-not-allowed opacity-50")}>
      <span className="flex flex-col gap-0.5">
        <span className="text-[13px]">{label}</span>
        {desc && <span className="text-[11px] leading-relaxed text-muted-foreground">{desc}</span>}
      </span>
      <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} className="mt-0.5" />
    </label>
  )
}

export function PathInput({ value, onChange, placeholder, pick, disabled }: {
  value: string; onChange: (v: string) => void; placeholder?: string; pick: () => Promise<string | null>; disabled?: boolean
}) {
  return (
    <div className="flex gap-2">
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} disabled={disabled} className="font-mono text-xs placeholder:font-sans" />
      <Button variant="outline" size="icon" disabled={disabled || !bridge.available()} title="Chọn…"
        onClick={async () => { const p = await pick(); if (p) onChange(p) }}>
        <FolderOpen />
      </Button>
    </div>
  )
}

/**
 * Nhóm nút chuyển. Chiều cao khớp với control đứng cạnh:
 *   size="default" = 36px (h-9) — cạnh Input / Select / Button mặc định
 *   size="sm"      = 32px (h-8) — cạnh Button size="sm" (thanh tiêu đề, đầu Section)
 */
export function Segmented<T extends string>({ value, onChange, items, size = "default" }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: string; icon?: ReactNode }[]; size?: "default" | "sm"
}) {
  return (
    <div className="inline-flex shrink-0 rounded-lg border border-border bg-muted/50 p-0.5">
      {items.map((it) => (
        <button key={it.value} onClick={() => onChange(it.value)}
          className={cn("flex items-center gap-1.5 rounded-md text-xs font-medium whitespace-nowrap text-muted-foreground transition-colors [&_svg]:size-3.5",
            size === "sm" ? "h-[26px] px-2.5" : "h-[30px] px-3",
            value === it.value ? "bg-background text-foreground shadow-sm" : "hover:text-foreground")}>
          {it.icon}{it.label}
        </button>
      ))}
    </div>
  )
}

const STATUS: Record<JobStatus, { label: string; cls: string }> = {
  queued: { label: "Xếp hàng", cls: "bg-muted text-muted-foreground" },
  running: { label: "Đang chạy", cls: "bg-primary/15 text-primary" },
  waiting: { label: "Chờ xác nhận", cls: "bg-warning/15 text-warning" },
  done: { label: "Hoàn thành", cls: "bg-success/15 text-success" },
  error: { label: "Lỗi", cls: "bg-destructive/15 text-destructive" },
  cancelled: { label: "Đã huỷ", cls: "bg-muted text-muted-foreground" },
}

export function StatusBadge({ status, queuePos }: { status: JobStatus; queuePos?: number }) {
  const s = STATUS[status]
  const label = status === "queued" && queuePos ? `${s.label} #${queuePos}` : s.label
  return <Badge variant="outline" className={cn("border-transparent", s.cls)}>{label}</Badge>
}

/** Tiêu đề job là "<Loại> · <tên file>" — bỏ phần loại khi đã có cột/nhãn loại riêng. */
export const jobFileName = (title: string) => title.split(" · ").slice(1).join(" · ") || title

export const KIND_LABEL: Record<JobKind, string> = { review: "Review", reup: "Dịch & Reup", srt: "Tách SRT", burn: "Ghép phụ đề" }

export function EmptyState({ icon, title, desc, action, className }: { icon: ReactNode; title: string; desc: string; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-card/50 px-6 py-14 text-center", className)}>
      <span className="flex size-11 items-center justify-center rounded-xl bg-muted text-muted-foreground [&_svg]:size-5">{icon}</span>
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-1 max-w-sm text-xs text-muted-foreground">{desc}</p>
      </div>
      {action}
    </div>
  )
}
