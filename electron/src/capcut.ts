// Đăng nhập CapCut để tự lấy cookie cho giọng CapCut (không cần F12 chép tay).
// Cửa sổ dùng phiên riêng "persist:capcut" — đăng nhập một lần, lần sau lấy lại cookie ngay không cần mở cửa sổ.
import { BrowserWindow, session } from "electron"
import { logger } from "./logger"

const log = logger("capcut")
const PARTITION = "persist:capcut"
const LOGIN_URL = "https://www.capcut.com/login"
// Có một trong các cookie này = đã đăng nhập
const AUTH_COOKIES = ["sessionid", "sessionid_ss", "sid_tt", "sid_guard"]

let pending: Promise<string> | null = null

async function readCookie(): Promise<string> {
  const all = await session.fromPartition(PARTITION).cookies.get({})
  const mine = all.filter((c) => (c.domain ?? "").replace(/^\./, "").endsWith("capcut.com"))
  if (!mine.some((c) => AUTH_COOKIES.includes(c.name) && c.value)) return ""
  const seen = new Set<string>()
  return mine.filter((c) => !seen.has(c.name) && seen.add(c.name)).map((c) => `${c.name}=${c.value}`).join("; ")
}

/** → chuỗi cookie "a=b; c=d". Đã đăng nhập từ trước thì trả ngay; chưa thì mở cửa sổ capcut.com chờ đăng nhập xong. */
export function capcutLogin(parent: BrowserWindow | null): Promise<string> {
  if (pending) return pending
  pending = (async () => {
    const existing = await readCookie()
    if (existing) return existing
    return await new Promise<string>((resolve, reject) => {
      const w = new BrowserWindow({
        width: 1100, height: 780, parent: parent ?? undefined, title: "Đăng nhập CapCut — đăng nhập xong cửa sổ tự đóng",
        autoHideMenuBar: true, webPreferences: { partition: PARTITION },
      })
      let done = false
      const timer = setInterval(async () => {
        try {
          const c = await readCookie()
          if (c && !done) {
            done = true
            clearInterval(timer)
            log.info("đã lấy cookie CapCut")
            w.close()
            resolve(c)
          }
        } catch (e) { log.warn("đọc cookie lỗi:", e) }
      }, 1500)
      w.on("closed", () => {
        clearInterval(timer)
        if (!done) reject(new Error("Đã đóng cửa sổ trước khi đăng nhập xong."))
      })
      w.loadURL(LOGIN_URL).catch((e) => log.warn("không mở được trang CapCut:", e))
    })
  })().finally(() => { pending = null })
  return pending
}

/** Đăng xuất: xoá phiên CapCut đã lưu trong app. */
export async function capcutLogout() {
  await session.fromPartition(PARTITION).clearStorageData()
}
