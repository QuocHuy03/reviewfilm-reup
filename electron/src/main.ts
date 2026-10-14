// Electron main: cửa sổ, IPC, vòng đời app. Logic riêng nằm ở các module:
//   paths.ts (dev vs bản cài) · backend.ts + python.ts (tiến trình Python) · updater.ts (tự cập nhật) · auth.ts (license)
import { app, BrowserWindow, dialog, ipcMain, shell } from "electron"
import path from "node:path"
import { pathToFileURL } from "node:url"
import { appInfo, releaseNotes, trackVersion } from "./appInfo"
import * as auth from "./auth"
import { capcutLogin, capcutLogout } from "./capcut"
import { backendPort, pickPort, startBackend, stopBackend } from "./backend"
import { logger, logsDir } from "./logger"
import { DEV, DEV_URL, FRONTEND_INDEX, ICON, ROOT, userData } from "./paths"
import type { PythonStatus } from "./python"
import { checkForUpdates, getUpdateState, initUpdater, installUpdate } from "./updater"
import { usage } from "./usage"

const log = logger("main")
let win: BrowserWindow | null = null

// Tài khoản AI web (ChatGPT/Gemini) — electron/ai là ESM nên nạp bằng dynamic import.
// Server loopback của nó phải chạy TRƯỚC backend để truyền URL + token qua env.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let ai: any = null
let aiServer: { url: string; token: string } | null = null
const aiReady = (async () => {
  try {
    ai = await import(pathToFileURL(path.join(ROOT, "electron", "ai", "index.js")).href)
    ai.initAccounts(app.getPath("userData"))
    aiServer = await ai.startLocalServer()
  } catch (e) {
    log.error("không khởi động được tài khoản AI web:", e)
  }
})()

// ---------- Backend ----------
let pyStatus: PythonStatus = { phase: "checking", message: "Đang khởi động…" }
const reportPython = (s: PythonStatus) => { pyStatus = s; win?.webContents.send("py:status", s) }

/** Không chờ: lần đầu cài thư viện có thể mất vài phút — UI theo dõi qua sự kiện py:status. */
function launchBackend() {
  void (async () => {
    await aiReady
    const aiEnv: Record<string, string> = aiServer ? { RF_WEB_LLM_URL: aiServer.url, RF_WEB_LLM_TOKEN: aiServer.token } : {}
    await startBackend(aiEnv, reportPython)
  })().catch((e) => log.error("không khởi động được backend:", e))
}

function shutdown() {
  stopBackend()
  ai?.closeAll().catch(() => {})
  ai?.stopLocalServer().catch(() => {})
}

// ---------- Đóng app khi còn job đang chạy ----------
let allowClose = false

/** Còn job đang chạy / xếp hàng / chờ xác nhận → hỏi trước khi đóng (đóng là dừng backend, video đang dựng bị bỏ dở). */
async function confirmClose(): Promise<boolean> {
  let active: { title: string; status: string }[] = []
  try {
    const r = await fetch(`http://127.0.0.1:${backendPort}/api/jobs`, { signal: AbortSignal.timeout(1500) })
    const jobs = (await r.json()) as { title: string; status: string }[]
    active = jobs.filter((j) => ["running", "queued", "waiting"].includes(j.status))
  } catch { return true }               // backend không phản hồi → không có gì để giữ
  if (!active.length || !win) return true
  const { response } = await dialog.showMessageBox(win, {
    type: "warning", buttons: ["Ở lại", "Vẫn thoát"], defaultId: 0, cancelId: 0, noLink: true,
    title: "Còn job đang chạy",
    message: `Còn ${active.length} job đang chạy / chờ xác nhận`,
    detail: active.slice(0, 5).map((j) => `• ${j.title}`).join("\n") +
      "\n\nThoát bây giờ sẽ dừng các job này. Lần sau mở app có thể bấm Tiếp tục để chạy tiếp từ bước đã xong.",
  })
  return response === 1
}

// ---------- Window ----------
const OVERLAY = {
  dark: { color: "#0f0f11", symbolColor: "#a1a1aa" },
  light: { color: "#ffffff", symbolColor: "#52525b" },
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1180,
    minHeight: 720,
    backgroundColor: OVERLAY.dark.color,
    title: "ReviewFilm Studio",
    icon: ICON,
    titleBarStyle: "hidden",
    titleBarOverlay: process.platform === "win32" ? { ...OVERLAY.dark, height: 43 } : undefined,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      sandbox: false,
      additionalArguments: [`--rf-backend=http://127.0.0.1:${backendPort}`],
    },
  })
  win.once("ready-to-show", () => win?.show())
  win.on("close", (e) => {
    if (allowClose) return
    e.preventDefault()
    confirmClose().then((ok) => { if (ok) { allowClose = true; win?.close() } })
  })
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: "deny" } })
  if (DEV) win.loadURL(DEV_URL)
  else win.loadFile(FRONTEND_INDEX)
}

// ---------- IPC: hệ thống ----------
ipcMain.handle("rf:pickFile", async (_e, filters?: Electron.FileFilter[]) => {
  const r = await dialog.showOpenDialog(win!, { properties: ["openFile"], filters })
  return r.canceled ? null : r.filePaths[0]
})
ipcMain.handle("rf:pickFiles", async (_e, filters?: Electron.FileFilter[]) => {
  const r = await dialog.showOpenDialog(win!, { properties: ["openFile", "multiSelections"], filters })
  return r.canceled ? [] : r.filePaths
})
ipcMain.handle("rf:pickFolder", async () => {
  const r = await dialog.showOpenDialog(win!, { properties: ["openDirectory", "createDirectory"] })
  return r.canceled ? null : r.filePaths[0]
})
ipcMain.handle("rf:openPath", (_e, p: string) => shell.openPath(p))
ipcMain.handle("rf:showInFolder", (_e, p: string) => shell.showItemInFolder(p))
ipcMain.handle("rf:setTheme", (_e, theme: "dark" | "light") => {
  if (process.platform === "win32" && win) win.setTitleBarOverlay({ ...OVERLAY[theme], height: 43 })
  win?.setBackgroundColor(OVERLAY[theme].color)
})
ipcMain.handle("sys:usage", () => usage())
ipcMain.handle("rf:setFullScreen", (_e, on: boolean) => { win?.setFullScreen(!!on); return win?.isFullScreen() ?? false })
ipcMain.handle("py:status", () => pyStatus)

// ---------- IPC: thông tin app / phiên bản ----------
ipcMain.handle("capcut:login", () => capcutLogin(win))
ipcMain.handle("capcut:logout", () => capcutLogout())
ipcMain.handle("app:info", () => appInfo())
ipcMain.handle("app:releaseNotes", () => releaseNotes())
ipcMain.handle("app:openLogs", () => shell.openPath(logsDir()))
ipcMain.handle("app:openData", () => shell.openPath(userData()))

// ---------- IPC: license — backend chỉ chạy sau khi key hợp lệ ----------
ipcMain.handle("auth:verify", async () => {
  const r = await auth.verify()
  if (r.success) launchBackend()
  return r
})
ipcMain.handle("auth:login", async (_e, key: string) => {
  const r = await auth.login(key)
  if (r.success) launchBackend()
  return r
})
ipcMain.handle("auth:logout", () => { auth.logout(); stopBackend(); return { success: true } })
ipcMain.handle("auth:get-device-id", () => auth.deviceId())

// ---------- IPC: cập nhật ----------
ipcMain.handle("update:state", () => getUpdateState())
ipcMain.handle("update:check", () => checkForUpdates())
ipcMain.handle("update:install", () => installUpdate(shutdown))

// ---------- Tài khoản AI web ----------
async function withAi<T>(fn: () => Promise<T> | T) {
  await aiReady
  if (!ai) return { ok: false, error: "Module tài khoản AI chưa nạp được — xem log." }
  try { return await fn() } catch (e) { return { ok: false, error: (e as Error)?.message || String(e) } }
}
ipcMain.handle("ai:state", () => withAi(() => ai.publicState()))
ipcMain.handle("ai:chatgptLogin", () => withAi(() => ai.chatgptLogin()))
ipcMain.handle("ai:chatgptLoginDone", () => withAi(() => ai.chatgptLoginDone()))
ipcMain.handle("ai:chatgptCheck", (_e, id: number) => withAi(() => ai.chatgptCheck(id)))
ipcMain.handle("ai:chatgptSetActive", (_e, id: number) => withAi(() => ai.chatgptSetActive(id)))
ipcMain.handle("ai:chatgptDelete", (_e, id: number) => withAi(() => ai.chatgptDelete(id)))
ipcMain.handle("ai:geminiLogin", () => withAi(() => ai.geminiLogin()))
ipcMain.handle("ai:geminiLogout", () => withAi(() => ai.geminiLogout()))
ipcMain.handle("ai:geminiCheck", () => withAi(() => ai.geminiCheck()))

// ---------- Vòng đời ----------
// Chỉ 1 cửa sổ app: mở lần 2 → đưa cửa sổ đang mở lên trước (2 backend cùng ghi dữ liệu job sẽ hỏng lịch sử)
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on("second-instance", () => {
    if (!win) return
    if (win.isMinimized()) win.restore()
    win.focus()
  })
}

app.whenReady().then(async () => {
  trackVersion()
  log.info(`ReviewFilm Studio v${app.getVersion()} (${app.isPackaged ? "bản cài đặt" : "dev"}) — Electron ${process.versions.electron}`)
  await pickPort(8765)
  createWindow()
  initUpdater(() => win)
})
app.on("window-all-closed", () => { shutdown(); app.quit() })
app.on("before-quit", shutdown)
