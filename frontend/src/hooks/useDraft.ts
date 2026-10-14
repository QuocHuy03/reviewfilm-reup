import { useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import type { JobDetail, Scene } from "@/lib/types"

/** Bản nháp đã lưu cho bước đang chờ (null nếu không có / của bước khác). */
export function draftFor(job: JobDetail, stage: "script" | "preview") {
  const d = job.draft
  return d && "waiting" in d && d.waiting === stage && Array.isArray(d.scenes) && d.scenes.length ? d : null
}

/**
 * Tự lưu chỉnh sửa lên backend 1 giây sau thay đổi cuối (và ngay khi rời màn hình) —
 * chuyển trang, đóng app rồi mở lại vẫn còn nguyên. → "saving" | "saved" | "error" | "".
 */
export function useDraftAutosave(jobId: string, scenes: Scene[], mixer?: Record<string, unknown>) {
  const [state, setState] = useState<"" | "saving" | "saved" | "error">("")
  const first = useRef(true)
  const pending = useRef<{ scenes: Scene[]; mixer?: Record<string, unknown> } | null>(null)
  const flush = useRef(() => {})
  flush.current = () => {
    const p = pending.current
    if (!p) return
    pending.current = null
    setState("saving")
    api.saveDraft(jobId, p.scenes, p.mixer).then(() => setState("saved")).catch(() => setState("error"))
  }
  useEffect(() => {
    if (first.current) { first.current = false; return }   // lần đầu = dữ liệu vừa tải, chưa có gì để lưu
    pending.current = { scenes, mixer }
    const t = setTimeout(() => flush.current(), 1000)
    return () => clearTimeout(t)
  }, [scenes, mixer])
  useEffect(() => () => flush.current(), [])                 // rời màn hình: lưu nốt phần chưa lưu
  return state
}
