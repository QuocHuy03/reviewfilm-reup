import { Clapperboard, Film, FolderOpen, Loader2, Maximize2, Minimize2, ScrollText, Square, X } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { EmptyState, jobFileName, KIND_LABEL, StatusBadge } from "@/components/common"
import { PostEditor } from "@/components/editor/PostEditor"
import { DoneStage, FailedStage, RunningStage, ScriptStage } from "@/components/editor/StageViews"
import { JobHeaderContext } from "@/components/editor/StageHeader"
import { LogConsole } from "@/components/LogConsole"
import { Button } from "@/components/ui/button"
import { useJobStream } from "@/hooks/useJobStream"
import { api, bridge } from "@/lib/api"
import { fmtRelative } from "@/lib/format"
import type { JobSummary } from "@/lib/types"
import { cn } from "@/lib/utils"
import { confirmAction } from "@/components/ConfirmHost"

export function StudioPage() {
  const { activeJobId, openJob, go } = useStore()
  const [recent, setRecent] = useState<JobSummary[]>([])
  useEffect(() => { if (!activeJobId) api.jobs().then(setRecent).catch(() => {}) }, [activeJobId])

  if (!activeJobId) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-4">
        <EmptyState className="flex-1" icon={<Film />} title="Chưa mở job nào"
          desc="Bắt đầu một video mới, hoặc mở lại job gần đây để xem tiến trình, sửa kịch bản và xuất kết quả."
          action={<Button onClick={() => go("create")}><Clapperboard /> Tạo video mới</Button>} />
        {recent.length > 0 && (
          <div className="shrink-0">
            <p className="mb-2 text-xs font-medium text-muted-foreground">Job gần đây</p>
            <div className="grid grid-cols-2 gap-2 xl:grid-cols-3">
              {recent.slice(0, 6).map((j) => (
                <button key={j.id} onClick={() => openJob(j.id)} className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 text-left hover:border-primary/40">
                  <span className="min-w-0 flex-1 truncate text-sm">{j.title}</span>
                  <span className="text-xs text-muted-foreground">{fmtRelative(j.created_at)}</span>
                  <StatusBadge status={j.status} queuePos={j.queue_pos} />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }
  return <JobView key={activeJobId} jobId={activeJobId} />
}

function JobView({ jobId }: { jobId: string }) {
  const { job, logs, reload, error } = useJobStream(jobId)
  const { go } = useStore()
  const [logOpen, setLogOpen] = useState(false)
  const { fullscreen, setFullscreen } = useStore()

  // Phím F: bật/tắt toàn màn hình (bỏ qua khi đang gõ chữ)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === "TEXTAREA" || tag === "INPUT" || e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key === "f" || e.key === "F") { e.preventDefault(); setFullscreen(!fullscreen) }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [fullscreen, setFullscreen])
  if (!job && error) return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <p className="text-sm font-medium">Không mở được job này</p>
      <p className="max-w-sm text-xs text-muted-foreground">{/không tồn tại|404/i.test(error) ? "Job đã bị xoá khỏi lịch sử." : error}</p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={reload}>Thử lại</Button>
        <Button size="sm" onClick={() => go("jobs")}>Về Lịch sử</Button>
      </div>
    </div>
  )
  if (!job) return <div className="flex h-full items-center justify-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
  if (job.kind === "download") return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <p className="text-sm font-medium">{job.title}</p>
      <p className="text-xs text-muted-foreground">Job tải video — xem tiến độ và file đã tải ở trang Tải video.</p>
      <Button size="sm" onClick={() => go("download")}>Mở trang Tải video</Button>
    </div>
  )

  const running = job.status === "running" || job.status === "queued"
  const outPath = job.result.output_path || job.result.vi_srt || job.result.original_srt
  const editing = job.status === "waiting" && job.waiting === "preview"

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <JobHeaderContext.Provider value={{
        progress: running ? job.progress : undefined,
        lead: (
          <div className="flex min-w-0 max-w-[280px] shrink items-center gap-2">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">{KIND_LABEL[job.kind]}</span>
            <span className="truncate text-[12.5px] font-medium" title={job.title}>{jobFileName(job.title)}</span>
          </div>
        ),
        trail: (
          <div className="flex items-center gap-0.5">
            {(running || job.status === "waiting") && (
              <Button variant="ghost" size="icon-sm" className="text-destructive hover:bg-destructive/10 hover:text-destructive" title="Dừng job"
                onClick={async () => {
                  if (!await confirmAction({ title: "Dừng job này?", danger: true, action: "Dừng job",
                    desc: "Bước đang chạy sẽ dừng lại. Sau đó có thể bấm Tiếp tục để chạy tiếp từ bước đã xong gần nhất." })) return
                  api.cancel(job.id).then(() => toast("Đang dừng job…")).catch((e) => toast.error("Không dừng được", { description: (e as Error).message }))
                }}><Square /></Button>
            )}
            {outPath && <Button variant="ghost" size="icon-sm" title="Mở thư mục kết quả" onClick={() => bridge.reveal(outPath)}><FolderOpen /></Button>}
            <Button variant="ghost" size="icon-sm" title={fullscreen ? "Thoát toàn màn hình (Esc)" : "Toàn màn hình (F)"} onClick={() => setFullscreen(!fullscreen)}>
              {fullscreen ? <Minimize2 /> : <Maximize2 />}
            </Button>
          </div>
        ),
      }}>
      <div className="min-h-0 flex-1">
        <div className="h-full min-h-0">
          {job.status === "waiting" && job.waiting === "script" && <ScriptStage key="script" job={job} />}
          {editing && <PostEditor job={job} />}
          {running && <RunningStage job={job} logs={logs} />}
          {job.status === "done" && <DoneStage job={job} />}
          {(job.status === "error" || job.status === "cancelled") && <FailedStage job={job} onResumed={reload} />}
        </div>
      </div>
      </JobHeaderContext.Provider>

      {/* Nhật ký: nút tròn góc dưới phải → bảng nổi */}
      {logOpen && (
        <div className="fixed right-6 bottom-20 z-40 flex h-[min(60vh,560px)] w-[min(560px,calc(100vw-48px))] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl animate-in fade-in slide-in-from-bottom-2">
          <LogConsole logs={logs} className="min-h-0 flex-1 rounded-none border-0" />
        </div>
      )}
      <button onClick={() => setLogOpen(!logOpen)} title={logOpen ? "Đóng nhật ký" : "Mở nhật ký"}
        className={cn("fixed right-6 bottom-6 z-40 flex size-12 items-center justify-center rounded-full shadow-lg transition hover:scale-105 [&_svg]:size-5",
          logOpen ? "bg-foreground text-background" : "bg-primary text-primary-foreground")}>
        {logOpen ? <X /> : <ScrollText />}
        {!logOpen && logs.length > 0 && (
          <span className={cn("tabular absolute -top-1 -right-1 min-w-5 rounded-full px-1 text-[10px] leading-5 font-semibold text-white",
            job.status === "error" ? "bg-destructive animate-pulse" : "bg-foreground/80")}>
            {logs.length > 999 ? "999+" : logs.length}
          </span>
        )}
      </button>
    </div>
  )
}
