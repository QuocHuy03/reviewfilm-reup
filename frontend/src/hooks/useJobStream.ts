import { useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import type { JobDetail, JobSummary, LogLine, Scene } from "@/lib/types"

type StreamPayload = { state: JobSummary; logs: LogLine[]; cursor: number; scenes?: Scene[] }

/** Theo dõi 1 job qua SSE: trạng thái, log, scenes (khi chờ xác nhận / xong). */
export function useJobStream(jobId: string | null) {
  const [job, setJob] = useState<JobDetail | null>(null)
  const [logs, setLogs] = useState<LogLine[]>([])
  const cursor = useRef(0)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    if (!jobId) return
    let es: EventSource | null = null
    let closed = false
    setLogs([]); setJob(null); cursor.current = 0

    api.job(jobId).then((d) => {
      if (closed) return
      setJob(d)
      if (d.logs) { setLogs(d.logs); cursor.current = d.log_cursor ?? d.logs.length }
      if (["done", "error", "cancelled"].includes(d.status)) return
      es = new EventSource(api.streamUrl(jobId, cursor.current))
      es.onmessage = (ev) => {
        const p = JSON.parse(ev.data) as StreamPayload
        // EventSource reconnect gửi lại từ `since` cũ → chỉ lấy log chưa nhận
        const fresh = p.logs.slice(Math.max(0, cursor.current - (p.cursor - p.logs.length)))
        cursor.current = Math.max(cursor.current, p.cursor)
        if (fresh.length) setLogs((prev) => [...prev, ...fresh].slice(-3000))
        setJob((prev) => prev ? { ...prev, ...p.state, ...(p.scenes ? { scenes: p.scenes } : {}) } : prev)
        if (["done", "error", "cancelled"].includes(p.state.status)) es?.close()
      }
      es.onerror = () => { /* EventSource tự reconnect */ }
    }).catch(() => {})

    return () => { closed = true; es?.close() }
  }, [jobId, nonce])

  /** Tải lại + mở lại stream (sau khi tiếp tục / chạy lại job đã kết thúc). */
  const reload = () => setNonce((n) => n + 1)
  return { job, setJob, logs, reload }
}
