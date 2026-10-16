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

function Shell() {
  const { page, backendReady, fullscreen, setFullscreen } = useStore()
  const activeJob = useActiveJob(backendReady)
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
