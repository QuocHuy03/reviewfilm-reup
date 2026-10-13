import { CalendarClock, Copy, LogOut, ShieldCheck, WifiOff } from "lucide-react"
import { toast } from "sonner"
import { licenseLeft, useAuth, useNow } from "@/app/auth"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })

/** Chip thời hạn key trên header + menu chi tiết (ngày hết hạn, mã thiết bị, đăng xuất). */
export function LicenseMenu() {
  const { license, deviceId, logout } = useAuth()
  const now = useNow()
  const left = licenseLeft(license.expiry, now)

  const tone = !left ? "border-border text-foreground"
    : left.level === "ok" ? "border-success/40 bg-success/10 text-success"
    : left.level === "warn" ? "border-warning/50 bg-warning/10 text-warning"
    : "border-destructive/50 bg-destructive/10 text-destructive"

  // % thời hạn đã dùng (khi biết ngày bắt đầu)
  const usedPct = license.start && license.expiry
    ? Math.min(100, Math.max(0, ((now - +new Date(license.start)) / (+new Date(license.expiry) - +new Date(license.start))) * 100))
    : null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className={cn("no-drag flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-[11px] font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring", tone)}>
        {license.offline ? <WifiOff className="size-3.5" /> : <CalendarClock className="size-3.5" />}
        <span className="tabular">{left ? left.text : "Không giới hạn"}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72 p-0">
        <div className="flex flex-col gap-3 p-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-primary" />
            <span className="text-sm font-semibold">Bản quyền</span>
            {license.offline && <span className="ml-auto rounded bg-warning/15 px-1.5 py-0.5 text-[10px] text-warning">offline</span>}
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
            <dt className="text-muted-foreground">Key</dt><dd className="text-right font-mono">{license.key ?? "—"}</dd>
            <dt className="text-muted-foreground">Hết hạn</dt><dd className="text-right font-medium">{license.expiry ? fmtDate(license.expiry) : "Không giới hạn"}</dd>
            <dt className="text-muted-foreground">Còn lại</dt><dd className="text-right font-medium">{left?.text.replace("Còn ", "") ?? "∞"}</dd>
            {license.remaining && license.remaining !== "unlimited" && (
              <><dt className="text-muted-foreground">Lượt dùng</dt><dd className="text-right">{license.remaining}</dd></>
            )}
          </dl>
          {usedPct !== null && (
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${usedPct}%` }} />
            </div>
          )}
        </div>
        <DropdownMenuSeparator className="my-0" />
        <div className="p-1">
          <DropdownMenuItem onSelect={() => { navigator.clipboard.writeText(deviceId); toast.success("Đã sao chép mã thiết bị") }}>
            <Copy /> Sao chép mã thiết bị
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => logout()}><LogOut /> Đăng xuất key</DropdownMenuItem>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
