import { useEffect, useState } from "react"
import type { PythonStatus, UpdateState } from "@/types/electron"

/** Trạng thái tự cập nhật (Electron main đẩy qua sự kiện update:state). */
export function useUpdate() {
  const bridge = window.rf?.update
  const [state, setState] = useState<UpdateState | null>(null)
  useEffect(() => {
    if (!bridge) return
    bridge.state().then(setState).catch(() => {})
    return bridge.onState(setState)
  }, [bridge])
  return {
    state,
    available: Boolean(bridge),
    check: () => bridge?.check().then(setState),
    install: () => bridge?.install(),
  }
}

/** Tiến trình chuẩn bị Python (lần đầu cài thư viện, hoặc sau khi cập nhật đổi requirements). */
export function usePythonStatus() {
  const bridge = window.rf?.python
  const [status, setStatus] = useState<PythonStatus | null>(null)
  useEffect(() => {
    if (!bridge) return
    bridge.status().then(setStatus).catch(() => {})
    return bridge.onStatus(setStatus)
  }, [bridge])
  return status
}
