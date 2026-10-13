// Thông tin phiên bản + "Có gì mới".
// Phiên bản: package.json → app.getVersion() là nguồn DUY NHẤT (backend nhận qua RF_APP_VERSION).
// Ghi nhớ phiên bản lần chạy trước ở userData/state.json; khác phiên bản hiện tại = vừa cập nhật.
import { app } from "electron"
import fs from "node:fs"
import path from "node:path"
import { logsDir } from "./logger"
import { ROOT, userData, userDataDir } from "./paths"

export type ReleaseNote = { version: string; date: string; body: string }
export type AppInfo = {
  version: string
  previousVersion: string | null
  justUpdated: boolean
  electron: string
  chrome: string
  node: string
  platform: string
  packaged: boolean
  dataDir: string
  logsDir: string
}

const STATE_FILE = () => userDataDir("state.json")
let previous: string | null = null

function readState(): Record<string, unknown> {
  try { return JSON.parse(fs.readFileSync(STATE_FILE(), "utf8")) } catch { return {} }
}

/** Gọi một lần khi app sẵn sàng: nhớ phiên bản trước, ghi phiên bản hiện tại. */
export function trackVersion() {
  const state = readState()
  previous = typeof state.lastVersion === "string" ? state.lastVersion : null
  if (previous !== app.getVersion()) {
    try {
      fs.mkdirSync(userData(), { recursive: true })
      fs.writeFileSync(STATE_FILE(), JSON.stringify({ ...state, lastVersion: app.getVersion() }, null, 2))
    } catch { /* không ghi được thì lần sau hiện lại "Có gì mới" — vô hại */ }
  }
}

export function appInfo(): AppInfo {
  return {
    version: app.getVersion(),
    previousVersion: previous,
    justUpdated: previous !== null && previous !== app.getVersion(),
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
    platform: `${process.platform} ${process.arch}`,
    packaged: app.isPackaged,
    dataDir: userData(),
    logsDir: logsDir(),
  }
}

/** Các mục `## [x.y.z] - YYYY-MM-DD` trong CHANGELOG.md (chuẩn Keep a Changelog), mới nhất trước. */
export function releaseNotes(limit = 10): ReleaseNote[] {
  let text = ""
  try { text = fs.readFileSync(path.join(ROOT, "CHANGELOG.md"), "utf8") } catch { return [] }
  const out: ReleaseNote[] = []
  const re = /^## \[(\d+\.\d+\.\d+[^\]]*)\](?: - (\d{4}-\d{2}-\d{2}))?\s*$/gm
  const heads = [...text.matchAll(re)]
  const linksAt = text.search(/^\[[^\]]+\]:\s*\S+/m)            // khối link so sánh cuối file
  heads.forEach((m, i) => {
    const start = (m.index ?? 0) + m[0].length
    const next = heads[i + 1]?.index
    const end = next ?? (linksAt > start ? linksAt : text.length)
    out.push({ version: m[1], date: m[2] || "", body: text.slice(start, end).trim() })
  })
  return out.slice(0, limit)
}
