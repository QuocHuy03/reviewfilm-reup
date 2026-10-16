import { Loader2, PauseCircle, Unplug } from "lucide-react"
import { useStore, type Page } from "@/app/store"
import { ThemeToggle } from "@/app/theme"
import type { JobSummary } from "@/lib/types"
import { cn } from "@/lib/utils"
import { LicenseMenu } from "./LicenseMenu"
import { LogoWordmark } from "./Logo"
import { SystemMeters } from "./SystemMeters"

const TITLES: Record<Page, { title: string; sub: string }> = {
  home: { title: "Tổng quan", sub: "Bảng điều khiển ReviewFilm" },
  create: { title: "Tạo video", sub: "Review phim bằng AI hoặc Dịch & Reup" },
  studio: { title: "Studio", sub: "Tiến trình, kịch bản và xem trước" },
  subtitles: { title: "Phụ đề", sub: "Tách SRT · Ghép phụ đề vào video" },
  download: { title: "Tải video", sub: "Douyin · TikTok · Bilibili · Weibo · YouTube… — tải về rồi làm Review / Reup" },
  voices: { title: "Giọng đọc", sub: "Nghe mẫu và tạo thử giọng" },
  jobs: { title: "Lịch sử", sub: "Các job đã chạy và file xuất" },
  settings: { title: "Cài đặt", sub: "API key, mặc định, hệ thống" },
}

export function AppHeader({ activeJob }: { activeJob: JobSummary | null }) {
  const { page, openJob, backendReady } = useStore()
  const t = TITLES[page]
  const winControls = window.rf && window.rf.platform === "win32"

  return (
    <header className={cn("drag flex h-11 shrink-0 items-center gap-3 border-b border-border bg-background pl-5", winControls ? "pr-[150px]" : "pr-4")}>
      <div className="flex min-w-0 items-center gap-2.5">
        <LogoWordmark />
        <span className="text-muted-foreground/40">/</span>
        <h1 className="shrink-0 text-[13px] font-medium tracking-tight whitespace-nowrap">{t.title}</h1>
        <span className="hidden min-w-0 truncate text-xs text-muted-foreground xl:inline">{t.sub}</span>
      </div>

      <div className="flex-1" />

      {activeJob && (
        <button onClick={() => openJob(activeJob.id)} title="Mở job đang chạy"
          className="no-drag group flex h-8 max-w-[300px] items-center gap-2 rounded-md border border-primary/40 bg-primary/10 px-2.5 text-xs text-primary hover:bg-primary/15">
          {activeJob.status === "waiting" ? <PauseCircle className="size-3.5" /> : <Loader2 className="size-3.5 animate-spin" />}
          <span className="truncate">{activeJob.status === "waiting" ? "Chờ bạn xác nhận" : activeJob.stage || "Đang xử lý"}</span>
          <span className="tabular font-semibold">{activeJob.progress}%</span>
        </button>
      )}

      {/* Chỉ báo backend chỉ hiện khi có vấn đề */}
      {!backendReady && (
        <span className="no-drag flex h-8 items-center gap-1.5 rounded-md border border-warning/50 bg-warning/10 px-2.5 text-[11px] text-warning">
          <Unplug className="size-3.5" /> Đang kết nối backend…
        </span>
      )}

      <SystemMeters />
      {window.rf && <LicenseMenu />}
      <ThemeToggle />
    </header>
  )
}
