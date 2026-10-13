import { createContext, useContext, type ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Phần chung của thanh tiêu đề Studio do JobView cung cấp (tên job + nút Dừng/Thư mục/Toàn màn hình + tiến độ),
 * để mỗi bước chỉ cần 1 thanh tiêu đề thay vì thanh job + thanh bước chồng nhau.
 */
export type JobHeaderParts = { lead?: ReactNode; trail?: ReactNode; progress?: number }
export const JobHeaderContext = createContext<JobHeaderParts>({})

export function StageHeader({ title, meta, dot, actions }: { title: string; meta?: ReactNode; dot?: string; actions?: ReactNode }) {
  const { lead, trail, progress } = useContext(JobHeaderContext)
  return (
    <div className="relative flex items-center gap-3 border-b border-border px-4 py-2">
      {lead && <>{lead}<span className="h-6 w-px shrink-0 bg-border" /></>}
      <span className={cn("flex size-2 shrink-0 rounded-full", dot ?? "bg-primary")} />
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-[13px] font-semibold">{title}</h3>
        {meta && <div className="truncate text-[11px] text-muted-foreground">{meta}</div>}
      </div>
      {actions}
      {trail && <><span className="h-6 w-px shrink-0 bg-border" />{trail}</>}
      {progress !== undefined && progress < 100 && (
        <span className="absolute inset-x-0 bottom-0 h-0.5 bg-border/60">
          <span className="block h-full bg-primary transition-[width] duration-500" style={{ width: `${Math.max(1, progress)}%` }} />
        </span>
      )}
    </div>
  )
}
