import { AudioLines, Captions, Clapperboard, Download, Film, History, LayoutDashboard, Settings } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useStore, type Page } from "@/app/store"
import { cn } from "@/lib/utils"
import { LogoMark } from "./Logo"

type NavItem = { page: Page; label: string; icon: LucideIcon; hint: string }

// Chia nhóm: tổng quan · làm video (theo thứ tự công việc) · công cụ lẻ
const GROUPS: NavItem[][] = [
  [{ page: "home", label: "Tổng quan", icon: LayoutDashboard, hint: "Trạng thái & job gần đây" }],
  [
    { page: "download", label: "Tải video", icon: Download, hint: "Douyin · TikTok · Bilibili · YouTube…" },
    { page: "create", label: "Tạo video", icon: Clapperboard, hint: "Review phim / Dịch & Reup" },
    { page: "studio", label: "Studio", icon: Film, hint: "Theo dõi, sửa kịch bản, hậu kỳ" },
    { page: "jobs", label: "Lịch sử", icon: History, hint: "Tất cả job đã chạy" },
  ],
  [
    { page: "subtitles", label: "Phụ đề", icon: Captions, hint: "Tách SRT · Ghép · Sửa phụ đề" },
    { page: "voices", label: "Giọng đọc", icon: AudioLines, hint: "Nghe thử & chọn giọng" },
  ],
]

function NavButton({ item, active, onClick, badge }: { item: NavItem; active: boolean; onClick: () => void; badge?: boolean }) {
  const Icon = item.icon
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={onClick}
          aria-label={item.label}
          aria-current={active ? "page" : undefined}
          className={cn(
            "relative flex size-10 items-center justify-center rounded-lg text-sidebar-foreground transition-colors",
            "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none",
            active && "bg-sidebar-accent text-sidebar-primary",
          )}
        >
          {active && <span className="absolute -left-2 h-5 w-[3px] rounded-r-full bg-sidebar-primary" />}
          <Icon className="size-[18px]" strokeWidth={active ? 2.2 : 1.8} />
          {badge && <span className="absolute top-1.5 right-1.5 size-2 rounded-full bg-primary ring-2 ring-sidebar" />}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={10} className="flex flex-col gap-0.5">
        <span className="font-medium">{item.label}</span>
        <span className="text-[11px] opacity-70">{item.hint}</span>
      </TooltipContent>
    </Tooltip>
  )
}

export function AppSidebar({ studioBadge }: { studioBadge?: boolean }) {
  const { page, go } = useStore()
  return (
    <aside className="flex w-14 shrink-0 flex-col items-center border-r border-sidebar-border bg-sidebar pb-3">
      <div className="drag flex h-11 w-full items-center justify-center">
        <button onClick={() => go("home")} className="no-drag rounded-lg transition hover:opacity-85" title="ReviewFilm">
          <LogoMark />
        </button>
      </div>
      <nav className="mt-3 flex flex-1 flex-col items-center gap-1.5">
        {GROUPS.map((group, k) => (
          <div key={k} className="flex flex-col items-center gap-1.5">
            {k > 0 && <span className="my-1 h-px w-6 bg-sidebar-border" />}
            {group.map((item) => (
              <NavButton key={item.page} item={item} active={page === item.page} onClick={() => go(item.page)}
                badge={item.page === "studio" && studioBadge} />
            ))}
          </div>
        ))}
      </nav>
      <NavButton item={{ page: "settings", label: "Cài đặt", icon: Settings, hint: "API key, mặc định, hệ thống" }}
        active={page === "settings"} onClick={() => go("settings")} />
    </aside>
  )
}
