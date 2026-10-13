import { FolderOpen, History, RefreshCw, RotateCcw, StepForward, Trash2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { EmptyState, jobFileName, KIND_LABEL, StatusBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, bridge } from "@/lib/api"
import { fmtDuration, fmtRelative } from "@/lib/format"
import type { JobSummary } from "@/lib/types"

export function JobsPage() {
  const { openJob } = useStore()
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const load = () => api.jobs().then(setJobs).catch((e) => toast.error(e.message))
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t) }, [])

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
    try { await api.deleteJob(j.id); setJobs(jobs.filter((x) => x.id !== j.id)) } catch (e) { toast.error((e as Error).message) }
  }

  if (jobs.length === 0) return <EmptyState className="h-full" icon={<History />} title="Chưa có lịch sử" desc="Các job tạo video, tách SRT, ghép phụ đề sẽ xuất hiện ở đây." />

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <p className="text-[13px] font-semibold">{jobs.length} job</p>
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
            {jobs.map((j) => {
              const out = j.result.output_path || j.result.vi_srt || j.result.original_srt
              return (
                <TableRow key={j.id} className="cursor-pointer" onClick={() => openJob(j.id)}>
                  <TableCell className="max-w-0 pl-4"><p className="truncate text-[13px]" title={j.title}>{jobFileName(j.title)}</p>{j.error && <p className="truncate text-[11px] text-destructive">{j.error}</p>}</TableCell>
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
