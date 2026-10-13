// Log ra file trong userData/logs (+ in ra console). Xoay vòng khi quá MAX_BYTES, giữ KEEP bản cũ.
//   main.log    — Electron main (khởi động, updater, lỗi)
//   backend.log — stdout/stderr của backend Python
import fs from "node:fs"
import path from "node:path"
import { userDataDir } from "./paths"

const MAX_BYTES = 5 * 1024 * 1024
const KEEP = 3

export const logsDir = () => userDataDir("logs")

function rotate(file: string) {
  try {
    if (fs.statSync(file).size < MAX_BYTES) return
  } catch {
    return
  }
  for (let i = KEEP - 1; i >= 1; i--) {
    const from = `${file}.${i}`
    if (fs.existsSync(from)) fs.renameSync(from, `${file}.${i + 1}`)
  }
  fs.renameSync(file, `${file}.1`)
}

function write(name: string, line: string) {
  try {
    const dir = logsDir()
    fs.mkdirSync(dir, { recursive: true })
    const file = path.join(dir, name)
    rotate(file)
    fs.appendFileSync(file, line.endsWith("\n") ? line : line + "\n")
  } catch {
    /* ghi log hỏng không được làm hỏng app */
  }
}

/** Giờ địa phương "YYYY-MM-DD HH:mm:ss" (đọc log cho khớp đồng hồ máy). */
const stamp = () => {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function fmt(level: string, scope: string, args: unknown[]) {
  const msg = args.map((a) => (a instanceof Error ? a.stack || a.message : typeof a === "string" ? a : JSON.stringify(a))).join(" ")
  return `${stamp()} ${level.padEnd(5)} [${scope}] ${msg}`
}

/** Logger theo phạm vi: `const log = logger("updater"); log.info(...)`. */
export function logger(scope: string) {
  return {
    info: (...a: unknown[]) => { const l = fmt("INFO", scope, a); console.log(l); write("main.log", l) },
    warn: (...a: unknown[]) => { const l = fmt("WARN", scope, a); console.warn(l); write("main.log", l) },
    error: (...a: unknown[]) => { const l = fmt("ERROR", scope, a); console.error(l); write("main.log", l) },
  }
}

/** Ghi nguyên văn output của backend Python (đã có định dạng riêng). */
export function backendLog(chunk: string) {
  process.stdout.write(`[backend] ${chunk}`)
  for (const line of chunk.split(/\r?\n/)) if (line.trim()) write("backend.log", `${stamp()} ${line}`)
}
