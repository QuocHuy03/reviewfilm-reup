// Chuẩn bị Python cho backend.
//
// Dev:  RF_PYTHON → backend/.venv → `python` (như trước).
// Bản cài đặt: venv riêng ở %APPDATA%/reviewfilm/python-env, tạo ở lần chạy đầu bằng Python của máy.
//   requirements.txt đổi (sau khi cập nhật app) → tự `pip install` lại. So bằng hash nên không cài thừa.
import { app } from "electron"
import { spawn, spawnSync } from "node:child_process"
import crypto from "node:crypto"
import fs from "node:fs"
import path from "node:path"
import { BACKEND_DIR, userDataDir } from "./paths"

export type PythonStatus = { phase: "checking" | "creating" | "installing" | "ready" | "error"; message: string; detail?: string }
type Report = (s: PythonStatus) => void

const MIN_VERSION: [number, number] = [3, 10]
const isWin = process.platform === "win32"

function venvPython(venv: string) {
  return isWin ? path.join(venv, "Scripts", "python.exe") : path.join(venv, "bin", "python")
}

/** Phiên bản của một lệnh python, hoặc null nếu không chạy được. */
function versionOf(cmd: string, args: string[] = []): [number, number] | null {
  const r = spawnSync(cmd, [...args, "-c", "import sys;print(sys.version_info[0], sys.version_info[1])"], {
    encoding: "utf8", windowsHide: true, timeout: 15000,
  })
  if (r.status !== 0) return null
  const [maj, min] = (r.stdout || "").trim().split(/\s+/).map(Number)
  return Number.isFinite(maj) && Number.isFinite(min) ? [maj, min] : null
}

const atLeast = (v: [number, number]) => v[0] > MIN_VERSION[0] || (v[0] === MIN_VERSION[0] && v[1] >= MIN_VERSION[1])

/** Python của máy để tạo venv: RF_PYTHON → py launcher (3.12/3.11/3.10/3) → python → python3. */
function findSystemPython(): { cmd: string; args: string[]; version: string } | null {
  const candidates: [string, string[]][] = []
  if (process.env.RF_PYTHON) candidates.push([process.env.RF_PYTHON, []])
  if (isWin) for (const v of ["-3.12", "-3.11", "-3.10", "-3"]) candidates.push(["py", [v]])
  candidates.push(["python", []], ["python3", []])
  for (const [cmd, args] of candidates) {
    const v = versionOf(cmd, args)
    if (v && atLeast(v)) return { cmd, args, version: v.join(".") }
  }
  return null
}

/** Chạy lệnh, đẩy từng dòng output ra `onLine`. Reject nếu exit code ≠ 0. */
function run(cmd: string, args: string[], onLine: (l: string) => void, cwd?: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { cwd, windowsHide: true, env: { ...process.env, PYTHONIOENCODING: "utf-8", PIP_DISABLE_PIP_VERSION_CHECK: "1" } })
    let tail = ""
    const feed = (d: Buffer) => {
      for (const line of d.toString("utf8").split(/\r?\n/)) {
        if (!line.trim()) continue
        tail = (tail + "\n" + line).slice(-2000)
        onLine(line.trim())
      }
    }
    p.stdout.on("data", feed)
    p.stderr.on("data", feed)
    p.on("error", reject)
    p.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`${path.basename(cmd)} thoát mã ${code}\n${tail.slice(-600)}`))))
  })
}

function requirementsHash(): string {
  const file = path.join(BACKEND_DIR, "requirements.txt")
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex")
}

/** Python để chạy backend. Bản cài đặt: tạo/cập nhật venv nếu cần (có thể mất vài phút ở lần đầu). */
export async function ensurePython(report: Report): Promise<string> {
  if (!app.isPackaged) {
    if (process.env.RF_PYTHON) return process.env.RF_PYTHON
    const devVenv = venvPython(path.join(BACKEND_DIR, ".venv"))
    return fs.existsSync(devVenv) ? devVenv : "python"
  }

  const venv = userDataDir("python-env")
  const py = venvPython(venv)
  const stamp = path.join(venv, ".rf-requirements")

  report({ phase: "checking", message: "Kiểm tra môi trường Python…" })
  if (!fs.existsSync(py)) {
    const sys = findSystemPython()
    if (!sys) {
      throw new Error(`Máy chưa có Python ${MIN_VERSION.join(".")}+ — cài từ python.org (tick "Add python.exe to PATH") rồi mở lại app.`)
    }
    report({ phase: "creating", message: `Tạo môi trường Python (Python ${sys.version})…` })
    await run(sys.cmd, [...sys.args, "-m", "venv", venv], () => {})
  }

  const want = requirementsHash()
  const have = fs.existsSync(stamp) ? fs.readFileSync(stamp, "utf8").trim() : ""
  if (want !== have) {
    report({ phase: "installing", message: have ? "Cập nhật thư viện Python cho bản mới…" : "Cài thư viện Python lần đầu (vài phút)…" })
    await run(py, ["-m", "pip", "install", "--upgrade", "pip"], () => {})
    await run(py, ["-m", "pip", "install", "-r", path.join(BACKEND_DIR, "requirements.txt")], (line) => {
      if (/^(Collecting|Downloading|Installing|Successfully)/.test(line)) {
        report({ phase: "installing", message: "Đang cài thư viện Python…", detail: line.slice(0, 160) })
      }
    })
    fs.writeFileSync(stamp, want)
  }
  report({ phase: "ready", message: "Python sẵn sàng" })
  return py
}
