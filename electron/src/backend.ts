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
export let backendPort = 8765

export function pickPort(preferred = 8765): Promise<number> {
  return new Promise((resolve) => {
    const srv = net.createServer()
    srv.once("error", () => {
      const s2 = net.createServer()
      s2.listen(0, "127.0.0.1", () => { const p = (s2.address() as net.AddressInfo).port; s2.close(() => resolve(p)) })
    })
    srv.listen(preferred, "127.0.0.1", () => srv.close(() => resolve(preferred)))
  }).then((p) => (backendPort = p as number))
}

/** Khởi động backend một lần (gọi lặp lại an toàn). `extraEnv` do main.ts truyền thêm. */
export function startBackend(extraEnv: Record<string, string>, report: (s: PythonStatus) => void): Promise<void> {
  if (proc) return Promise.resolve()
  if (starting) return starting
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
    proc.on("exit", (code) => {
      log.info(`backend thoát, mã ${code}`)
      proc = null
    })
  })().finally(() => { starting = null })
  return starting
}

export function stopBackend() {
  if (!proc?.pid) return
  if (process.platform === "win32") spawn("taskkill", ["/pid", String(proc.pid), "/T", "/F"], { windowsHide: true })
  else proc.kill()
  proc = null
}
