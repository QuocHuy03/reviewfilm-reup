import { lazy, Suspense, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { AuthGate } from "@/app/auth"
import { StoreProvider, useStore } from "@/app/store"
import { ThemeProvider } from "@/app/theme"
import { BackendBoot } from "@/components/BackendBoot"
import { WhatsNewDialog } from "@/components/ReleaseNotes"
import { AppHeader } from "@/components/layout/AppHeader"
import { AppSidebar } from "@/components/layout/AppSidebar"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { useUpdate } from "@/hooks/useUpdate"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import type { JobSummary } from "@/lib/types"
import { CreatePage } from "@/pages/CreatePage"
import { HomePage } from "@/pages/HomePage"
import { ConfirmHost } from "@/components/ConfirmHost"
import { AssistantWidget } from "@/components/AssistantPanel"
import { Loader2 } from "lucide-react"

// Trang nặng chỉ nạp khi mở tới → app khởi động nhanh hơn (Trang chủ + Tạo video nạp sẵn)
const StudioPage = lazy(() => import("@/pages/StudioPage").then((m) => ({ default: m.StudioPage })))
const DownloadPage = lazy(() => import("@/pages/DownloadPage").then((m) => ({ default: m.DownloadPage })))
const SubtitlesPage = lazy(() => import("@/pages/SubtitlesPage").then((m) => ({ default: m.SubtitlesPage })))
const VoicesPage = lazy(() => import("@/pages/VoicesPage").then((m) => ({ default: m.VoicesPage })))
const JobsPage = lazy(() => import("@/pages/JobsPage").then((m) => ({ default: m.JobsPage })))
const SettingsPage = lazy(() => import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })))
const PageLoading = () => <div className="flex h-full items-center justify-center text-muted-foreground"><Loader2 className="size-5 animate-spin" /></div>

function useActiveJob(enabled: boolean) {
  const [job, setJob] = useState<JobSummary | null>(null)
  useEffect(() => {
    if (!enabled) return
    const tick = () => api.jobs().then((js) => setJob(js.find((j) => j.status === "waiting") ?? js.find((j) => j.status === "running") ?? js.find((j) => j.status === "queued") ?? null)).catch(() => {})
    tick()
    const t = setInterval(tick, 2000)
    return () => clearInterval(t)
  }, [enabled])
  return job
}

/** Báo một lần khi bản cập nhật đã tải xong. */
function useUpdateToast() {
  const { state, install } = useUpdate()
  const shown = useRef("")
  useEffect(() => {
    if (state?.status !== "downloaded" || !state.version || shown.current === state.version) return
    shown.current = state.version
    toast.info(`Đã tải bản cập nhật v${state.version}`, {
      description: "Khởi động lại để cài. Cài đặt và lịch sử job được giữ nguyên.",
      duration: Infinity,
      action: { label: "Khởi động lại", onClick: () => install() },
    })
  }, [state, install])
}

const KIND_NAME: Record<string, string> = { review: "Review phim", reup: "Dịch & Reup", vietsub: "Dịch phụ đề", srt: "Tách SRT", burn: "Ghép phụ đề", download: "Tải video" }
const fmtTook = (s: number) => (s >= 3600 ? `${Math.floor(s / 3600)} giờ ${Math.round((s % 3600) / 60)} phút` : s >= 60 ? `${Math.round(s / 60)} phút` : `${Math.round(s)} giây`)

/**
 * Báo khi job XONG / LỖI / CHỜ DUYỆT: thông báo trong app + thông báo Windows (khi app không ở trước mặt — đang thu nhỏ,
 * làm việc khác). Bấm thông báo → mở đúng job. Tắt được trong Cài đặt (localStorage "rf.notify" = "0").
 */
function useJobNotifications(enabled: boolean) {
  const { openJob } = useStore()
  const prev = useRef<Map<string, string> | null>(null)
  useEffect(() => {
    if (!enabled) return
    let off = false
    const tick = async () => {
      let jobs: JobSummary[]
      try { jobs = await api.jobs() } catch { return }
      if (off) return
      const now = new Map(jobs.map((j) => [j.id, `${j.status}:${j.waiting ?? ""}`]))
      const before = prev.current
      prev.current = now
      if (!before) return                                   // lần đầu: chỉ ghi nhận, không báo job cũ
      let on = true
      try { on = localStorage.getItem("rf.notify") !== "0" } catch { /* bỏ qua */ }
      for (const j of jobs) {
        const was = before.get(j.id)
        const cur = now.get(j.id)!
        if (!was || was === cur) continue
        const name = j.title.split(" · ").slice(1).join(" · ") || j.title
        const kind = KIND_NAME[j.kind] ?? j.kind
        let title = "", body = "", tone: "success" | "error" | "info" = "info"
        if (j.status === "done") {
          const qa = j.result.qa?.score
          const n = j.kind === "download" ? (j.result.items ?? []).filter((x) => x.path).length : 0
          title = `Xong: ${name}`
          body = [kind, j.kind === "download" ? `${n} video` : "", `mất ${fmtTook(j.elapsed)}`, qa ? `chất lượng ${qa}/100` : ""].filter(Boolean).join(" · ")
          tone = "success"
        } else if (j.status === "error") {
          title = `Lỗi: ${name}`
          body = (j.error || "Job dừng vì lỗi").slice(0, 140)
          tone = "error"
        } else if (j.status === "waiting") {
          title = `Đang chờ bạn: ${name}`
          body = j.waiting === "script" ? "Xem & sửa bản dịch / kịch bản rồi bấm Xác nhận" : "Xem lại & xác nhận để dựng video"
        } else continue
        const open = () => { window.rf?.focusWindow?.(); openJob(j.id) }
        const t = tone === "success" ? toast.success : tone === "error" ? toast.error : toast.info
        t(title, { description: body, duration: tone === "error" ? 15000 : 8000, action: { label: "Mở", onClick: open } })
        if (on && !document.hasFocus() && typeof Notification !== "undefined") {
          try {
            const n = new Notification(title, { body, silent: false })
            n.onclick = () => { n.close(); open() }
          } catch { /* hệ thống chặn thông báo → đã có thông báo trong app */ }
        }
      }
    }
    tick()
    const t = setInterval(tick, 3000)
    return () => { off = true; clearInterval(t) }
  }, [enabled, openJob])
}

function Shell() {
  const { page, backendReady, fullscreen, setFullscreen } = useStore()
  const activeJob = useActiveJob(backendReady)
  useJobNotifications(backendReady)
  const immersive = fullscreen && page === "studio"
  useUpdateToast()

  // Rời Studio thì tự thoát toàn màn hình; Esc để thoát
  useEffect(() => { if (fullscreen && page !== "studio") setFullscreen(false) }, [page, fullscreen, setFullscreen])
  useEffect(() => {
    if (!fullscreen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFullscreen(false) }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [fullscreen, setFullscreen])

  return (
    <div className="flex h-full bg-background text-foreground">
      <WhatsNewDialog />
      {backendReady && <AssistantWidget />}
      {!immersive && <AppSidebar studioBadge={activeJob?.status === "waiting"} />}
      <div className="flex min-w-0 flex-1 flex-col">
        {!immersive && <AppHeader activeJob={activeJob} />}
        <main className={cn("min-h-0 flex-1 overflow-hidden", immersive ? "p-2" : "p-5")}>
          {!backendReady ? (
            <BackendBoot />
          ) : (
            <Suspense fallback={<PageLoading />}>
            <div key={page} className="h-full animate-in duration-200 fade-in">
              {page === "home" && <div className="h-full overflow-y-auto"><HomePage /></div>}
              {page === "create" && <CreatePage />}
              {page === "studio" && <StudioPage />}
              {page === "download" && <DownloadPage />}
              {page === "subtitles" && <SubtitlesPage />}
              {page === "voices" && <VoicesPage />}
              {page === "jobs" && <JobsPage />}
              {page === "settings" && <div className="h-full overflow-y-auto"><SettingsPage /></div>}
            </div>
            </Suspense>
          )}
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <TooltipProvider delayDuration={250}>
        <AuthGate>
          <StoreProvider>
            <Shell />
          </StoreProvider>
        </AuthGate>
        <Toaster position="bottom-right" richColors closeButton />
        <ConfirmHost />
      </TooltipProvider>
    </ThemeProvider>
  )
}
