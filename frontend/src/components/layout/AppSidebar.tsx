import { AudioLines, Captions, Clapperboard, Download, Film, History, LayoutDashboard, LifeBuoy, Settings } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useStore, type Page } from "@/app/store"
import { openSupport } from "@/lib/support"
import { cn } from "@/lib/utils"
import { LogoMark } from "./Logo"

/** short: nhãn dưới icon (ngắn cho vừa cột); label đầy đủ hiện trong tooltip */
type NavItem = { page: Page | "support"; label: string; short?: string; icon: LucideIcon; hint: string }

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
            "relative flex w-[64px] flex-col items-center gap-1 rounded-lg px-1 pt-2 pb-1.5 text-sidebar-foreground/75 transition-colors",
            "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none",
            active && "bg-sidebar-accent text-sidebar-primary hover:text-sidebar-primary",
          )}
        >
          {active && <span className="absolute top-1/2 -left-1.5 h-6 w-[3px] -translate-y-1/2 rounded-r-full bg-sidebar-primary" />}
          <span className="relative">
            <Icon className="size-[19px]" strokeWidth={active ? 2.2 : 1.8} />
            {badge && <span className="absolute -top-1 -right-1.5 size-2 rounded-full bg-primary ring-2 ring-sidebar" />}
          </span>
          <span className={cn("max-w-full truncate text-[10.5px] leading-tight", active ? "font-semibold" : "font-medium")}>{item.short ?? item.label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={8} className="flex flex-col gap-0.5">
        <span className="font-medium">{item.label}</span>
        <span className="text-[11px] opacity-70">{item.hint}</span>
      </TooltipContent>
    </Tooltip>
  )
}

export function AppSidebar({ studioBadge }: { studioBadge?: boolean }) {
  const { page, go } = useStore()
  return (
    <aside className="flex w-[76px] shrink-0 flex-col items-center border-r border-sidebar-border bg-sidebar pb-2.5">
      <div className="drag flex h-11 w-full items-center justify-center">
        <button onClick={() => go("home")} className="no-drag rounded-lg transition hover:opacity-85" title="ReviewFilm">
          <LogoMark />
        </button>
      </div>
      <nav className="mt-2 flex min-h-0 flex-1 flex-col items-center gap-1 overflow-y-auto [scrollbar-width:none]">
        {GROUPS.map((group, k) => (
          <div key={k} className="flex flex-col items-center gap-1">
            {k > 0 && <span className="my-1 h-px w-8 bg-sidebar-border" />}
            {group.map((item) => (
              <NavButton key={item.page} item={item} active={page === item.page} onClick={() => go(item.page as Page)}
                badge={item.page === "studio" && studioBadge} />
            ))}
          </div>
        ))}
      </nav>
      <span className="mb-1 h-px w-8 bg-sidebar-border" />
      <div className="mb-1">
        <NavButton item={{ page: "support", label: "Hỗ trợ & liên hệ", short: "Hỗ trợ", icon: LifeBuoy, hint: "taothaoai.com — hướng dẫn, báo lỗi, liên hệ" }}
          active={false} onClick={openSupport} />
      </div>
      <NavButton item={{ page: "settings", label: "Cài đặt", icon: Settings, hint: "API key, mặc định, hệ thống" }}
        active={page === "settings"} onClick={() => go("settings")} />
    </aside>
  )
}
