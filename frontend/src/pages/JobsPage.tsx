import { Film, FolderOpen, History, Loader2, RefreshCw, RotateCcw, Search, StepForward, Trash2 } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { EmptyState, jobFileName, KIND_LABEL, Segmented, StatusBadge } from "@/components/common"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, bridge, mediaUrl } from "@/lib/api"
import { fmtDuration, fmtRelative } from "@/lib/format"
import type { JobSummary } from "@/lib/types"
import { confirmAction } from "@/components/ConfirmHost"

type Filter = "all" | "active" | "done" | "failed"
const FILTERS: Record<Filter, Set<string>> = {
  all: new Set(["queued", "running", "waiting", "done", "error", "cancelled"]),
  active: new Set(["queued", "running", "waiting"]),
  done: new Set(["done"]),
  failed: new Set(["error", "cancelled"]),
}
const FILTER_LABEL: Record<Filter, string> = { all: "Tất cả", active: "Đang chạy", done: "Hoàn thành", failed: "Lỗi / huỷ" }

export function JobsPage() {
  const { openJob, go } = useStore()
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [loaded, setLoaded] = useState(false)
  const [q, setQ] = useState("")
  const [filter, setFilter] = useState<Filter>("all")
  const failing = useRef(false)
  // Làm mới mỗi 3s; backend khởi động lại thì chỉ báo lỗi 1 lần (không spam thông báo)
  const load = () => api.jobs()
    .then((j) => { setJobs(j); setLoaded(true); failing.current = false })
    .catch((e) => { if (!failing.current) toast.error("Không tải được lịch sử", { description: (e as Error).message }); failing.current = true })
  useEffect(() => {
    load()
    const t = setInterval(() => { if (!document.hidden) load() }, 3000)
    return () => clearInterval(t)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const count = (f: Filter) => jobs.filter((j) => FILTERS[f].has(j.status)).length
  const list = useMemo(() => jobs.filter((j) => FILTERS[filter].has(j.status) && j.title.toLowerCase().includes(q.trim().toLowerCase())), [jobs, filter, q])

  const retry = async (j: JobSummary) => {
    try {
      const n = await api.retry(j.id)
      toast.success(n.queue_pos ? `Đã xếp hàng chạy lại (#${n.queue_pos})` : "Đang chạy lại", { description: n.title })
      openJob(n.id)
    } catch (e) { toast.error("Không chạy lại được", { description: (e as Error).message }) }
  }

  const resume = async (j: JobSummary) => {
    try { await api.resume(j.id); toast.success(`Tiếp tục từ: ${j.resume_from}`, { description: j.title }); openJob(j.id) }
    catch (e) { toast.error("Không tiếp tục được", { description: (e as Error).message }) }
  }

  const remove = async (j: JobSummary) => {
    if (j.status === "running" || j.status === "queued" || j.status === "waiting") {
      toast.warning("Job đang chạy — mở job và bấm Dừng trước khi xoá"); return
    }
    if (!await confirmAction({ title: "Xoá job khỏi lịch sử?", danger: true, action: "Xoá job",
      desc: `"${j.title}" — thư mục tạm của job cũng bị dọn (không Tiếp tục được nữa). Video và file đã xuất vẫn giữ nguyên.` })) return
    try { await api.deleteJob(j.id); setJobs(jobs.filter((x) => x.id !== j.id)) } catch (e) { toast.error((e as Error).message) }
  }

  if (!loaded) return <div className="flex h-full items-center justify-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
  if (jobs.length === 0) return <EmptyState className="h-full" icon={<History />} title="Chưa có lịch sử" desc="Các job tạo video, tách SRT, ghép phụ đề sẽ xuất hiện ở đây." />

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        <Segmented size="sm" value={filter} onChange={setFilter} items={(Object.keys(FILTERS) as Filter[]).map((f) => ({ value: f, label: `${FILTER_LABEL[f]} · ${count(f)}` }))} />
        <div className="relative ml-auto w-64">
          <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm theo tên video…" className="h-8 pl-8 text-xs" />
        </div>
        <Button variant="ghost" size="sm" onClick={load}><RefreshCw /> Làm mới</Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Tên</TableHead>
              <TableHead className="w-28">Loại</TableHead>
              <TableHead className="w-32">Trạng thái</TableHead>
              <TableHead className="w-40">Tiến độ</TableHead>
              <TableHead className="w-28">Thời gian</TableHead>
              <TableHead className="w-32">Tạo lúc</TableHead>
              <TableHead className="w-36" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.length === 0 && (
              <TableRow><TableCell colSpan={7} className="py-10 text-center text-xs text-muted-foreground">Không có job nào khớp bộ lọc</TableCell></TableRow>
            )}
            {list.map((j) => {
              const out = j.result.output_path || j.result.vi_srt || j.result.original_srt
              const thumb = j.result.publish?.thumbnails?.[0]
              return (
                <TableRow key={j.id} className="cursor-pointer" onClick={() => (j.kind === "download" ? go("download") : openJob(j.id))}>
                  <TableCell className="max-w-0 pl-4">
                    <div className="flex items-center gap-2.5">
                      {thumb
                        ? <img src={`${mediaUrl(thumb.path)}&v=${thumb.v ?? 0}`} alt="" className="h-9 w-16 shrink-0 rounded object-cover" />
                        : <span className="flex h-9 w-16 shrink-0 items-center justify-center rounded bg-muted text-muted-foreground"><Film className="size-3.5" /></span>}
                      <div className="min-w-0">
                        <p className="truncate text-[13px]" title={j.title}>{jobFileName(j.title)}</p>
                        {j.error ? <p className="truncate text-[11px] text-destructive">{j.error}</p>
                          : j.result.qa ? <p className="text-[11px] text-muted-foreground">Chất lượng {j.result.qa.score}/100</p> : null}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{KIND_LABEL[j.kind]}</TableCell>
                  <TableCell><StatusBadge status={j.status} queuePos={j.queue_pos} /></TableCell>
                  <TableCell><div className="flex items-center gap-2"><Progress value={j.progress} className="h-1" /><span className="tabular w-8 text-[11px] text-muted-foreground">{j.progress}%</span></div></TableCell>
                  <TableCell className="tabular text-xs text-muted-foreground">{fmtDuration(j.elapsed)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{fmtRelative(j.created_at)}</TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-0.5 pr-2">
                      {out && <Button variant="ghost" size="icon-sm" title="Mở thư mục" onClick={() => bridge.reveal(out)}><FolderOpen /></Button>}
                      {j.resumable && <Button variant="ghost" size="icon-sm" title={`Tiếp tục từ: ${j.resume_from}`} onClick={() => resume(j)}><StepForward /></Button>}
                      <Button variant="ghost" size="icon-sm" title="Chạy lại từ đầu với cấu hình cũ" onClick={() => retry(j)}
                        disabled={!["done", "error", "cancelled"].includes(j.status)}><RotateCcw /></Button>
                      <Button variant="ghost" size="icon-sm" title="Xoá khỏi lịch sử" onClick={() => remove(j)}
                        disabled={["running", "waiting", "queued"].includes(j.status)}><Trash2 /></Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
