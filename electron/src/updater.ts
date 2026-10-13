// Tự cập nhật qua GitHub Releases (electron-updater) — cùng cách ToolYoutube.
// Cấu hình repo ở package.json → build.publish. Chỉ hoạt động ở bản cài đặt (app.isPackaged).
//
// Luồng: mở app (+ mỗi 4 giờ) kiểm tra → có bản mới thì tải nền → tải xong báo UI →
// người dùng bấm "Khởi động lại" → dừng backend → cài đặt → mở lại.
import { app, type BrowserWindow } from "electron"
import { autoUpdater } from "electron-updater"
import { logger } from "./logger"

const log = logger("updater")

export type UpdateState = {
  status: "dev" | "idle" | "checking" | "available" | "downloading" | "downloaded" | "none" | "error"
  current: string
  version?: string
  notes?: string
  percent?: number
  error?: string
}

const CHECK_EVERY_MS = 4 * 60 * 60 * 1000
let state: UpdateState = { status: app.isPackaged ? "idle" : "dev", current: app.getVersion() }
let getWin: () => BrowserWindow | null = () => null

function set(patch: Partial<UpdateState>) {
  state = { ...state, ...patch }
  getWin()?.webContents.send("update:state", state)
}

const notesOf = (n: unknown) =>
  typeof n === "string" ? n : Array.isArray(n) ? n.map((x) => x?.note || "").join("\n") : ""

export function getUpdateState() {
  return state
}

export function initUpdater(windowGetter: () => BrowserWindow | null) {
  getWin = windowGetter
  if (!app.isPackaged) return
  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.on("checking-for-update", () => set({ status: "checking", error: undefined }))
  autoUpdater.on("update-available", (i) => {
    log.info(`có bản mới ${i.version}`)
    set({ status: "available", version: i.version, notes: notesOf(i.releaseNotes) })
  })
  autoUpdater.on("update-not-available", () => set({ status: "none" }))
  autoUpdater.on("download-progress", (p) => set({ status: "downloading", percent: Math.round(p.percent) }))
  autoUpdater.on("update-downloaded", (i) => {
    log.info(`đã tải xong ${i.version}`)
    set({ status: "downloaded", version: i.version, notes: notesOf(i.releaseNotes), percent: 100 })
  })
  autoUpdater.on("error", (e) => {
    log.error(e)
    set({ status: "error", error: e?.message || String(e) })
  })
  void checkForUpdates()
  setInterval(() => void checkForUpdates(), CHECK_EVERY_MS)
}

export async function checkForUpdates() {
  if (!app.isPackaged) return state
  if (state.status === "downloading" || state.status === "downloaded") return state
  try { await autoUpdater.checkForUpdates() } catch (e) { set({ status: "error", error: (e as Error).message }) }
  return state
}

/** Gọi `beforeQuit` (dừng backend) rồi cài bản đã tải và mở lại app. */
export function installUpdate(beforeQuit: () => void) {
  if (state.status !== "downloaded") return false
  beforeQuit()
  setImmediate(() => autoUpdater.quitAndInstall(false, true))
  return true
}
