// Tiến trình backend Python (FastAPI): chọn cổng, chuẩn bị Python, spawn, dừng.
import { app } from "electron"
import { spawn, type ChildProcess } from "node:child_process"
import net from "node:net"
import { backendLog, logger } from "./logger"
import { BACKEND_DIR, userDataDir } from "./paths"
import { ensurePython, type PythonStatus } from "./python"

const log = logger("backend")
let proc: ChildProcess | null = null
let starting: Promise<void> | null = null
// Cổng ưu tiên: số ít app khác dùng (8765 hay bị tool khác chiếm — 2 app bật cùng lúc giành cổng → backend không lên được)
export const PREFERRED_PORT = 47651
export let backendPort = PREFERRED_PORT

/** Cổng trống bất kỳ do hệ điều hành cấp. */
function freePort(): Promise<number> {
  return new Promise((resolve) => {
    const s = net.createServer()
    s.listen(0, "127.0.0.1", () => { const p = (s.address() as net.AddressInfo).port; s.close(() => resolve(p)) })
  })
}

export function pickPort(preferred = PREFERRED_PORT): Promise<number> {
  return new Promise<number>((resolve) => {
    const srv = net.createServer()
    srv.once("error", () => { void freePort().then(resolve) })
    srv.listen(preferred, "127.0.0.1", () => srv.close(() => resolve(preferred)))
  }).then((p) => (backendPort = p))
}

// Backend thoát ngay lúc mới chạy (vd cổng vừa bị app khác giành giữa lúc chọn cổng và lúc mở) → chọn cổng khác, chạy lại
const EARLY_EXIT_MS = 30_000
const MAX_RESTARTS = 3
let restarts = 0
let stopping = false
let lastArgs: { extraEnv: Record<string, string>; report: (s: PythonStatus) => void } | null = null
let onRestart: ((port: number) => void) | null = null
/** main.ts: backend đổi cổng → tải lại giao diện để dùng cổng mới. */
export function onBackendRestart(cb: (port: number) => void) { onRestart = cb }

/** Khởi động backend một lần (gọi lặp lại an toàn). `extraEnv` do main.ts truyền thêm. */
export function startBackend(extraEnv: Record<string, string>, report: (s: PythonStatus) => void): Promise<void> {
  if (proc) return Promise.resolve()
  if (starting) return starting
  lastArgs = { extraEnv, report }
  stopping = false
  starting = (async () => {
    let python: string
    try {
      python = await ensurePython(report)
    } catch (e) {
      log.error("không chuẩn bị được Python:", e)
      report({ phase: "error", message: "Không chuẩn bị được Python", detail: (e as Error).message })
      throw e
    }
    const env: Record<string, string | undefined> = {
      ...process.env, ...extraEnv,
      PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1", PYTHONUNBUFFERED: "1",   // UTF-8 mode: đọc output ffmpeg có tên file tiếng Việt/Trung không lỗi
      RF_APP_VERSION: app.getVersion(),
      ...(app.isPackaged ? { RF_DATA_DIR: userDataDir("data") } : {}),
    }
    proc = spawn(python, ["main.py", "--port", String(backendPort), "--parent-pid", String(process.pid)], {
      cwd: BACKEND_DIR, env, windowsHide: true,
    })
    log.info(`khởi động: ${python} main.py --port ${backendPort} (v${app.getVersion()})`)
    proc.stdout?.on("data", (d) => backendLog(String(d)))
    proc.stderr?.on("data", (d) => backendLog(String(d)))
    proc.on("error", (e) => {                     // vd không chạy được file python → báo ra thay vì im lặng
      log.error("không chạy được backend:", e)
      report({ phase: "error", message: "Không khởi động được backend", detail: e.message })
      proc = null
    })
    const startedAt = Date.now()
    proc.on("exit", (code) => {
      log.info(`backend thoát, mã ${code}`)
      proc = null
      if (stopping || code === 0 || Date.now() - startedAt > EARLY_EXIT_MS || restarts >= MAX_RESTARTS || !lastArgs) return
      restarts++
      void freePort().then((p) => {
        backendPort = p
        log.warn(`backend không lên được (mã ${code}) — thử lại ở cổng ${p} (lần ${restarts}/${MAX_RESTARTS})`)
        const a = lastArgs!
        return startBackend(a.extraEnv, a.report).then(() => onRestart?.(p))
      }).catch((e) => log.error("khởi động lại backend lỗi:", e))
    })
  })().finally(() => { starting = null })
  return starting
}

export function stopBackend() {
  stopping = true
  if (!proc?.pid) return
  if (process.platform === "win32") spawn("taskkill", ["/pid", String(proc.pid), "/T", "/F"], { windowsHide: true })
  else proc.kill()
  proc = null
}
