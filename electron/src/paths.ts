// Đường dẫn dùng chung — một nơi duy nhất phân biệt chạy dev (mã nguồn) và bản cài đặt (đã đóng gói).
import { app } from "electron"
import path from "node:path"

/** Gốc app: thư mục reviewfilm/ khi dev, resources/app.asar khi đã đóng gói. */
export const ROOT = path.resolve(__dirname, "..", "..")

export const DEV = process.env.RF_DEV === "1"
export const DEV_URL = "http://127.0.0.1:5173"

/** Backend Python: nằm NGOÀI asar (extraResources) vì Python cần đọc file thật. */
export const BACKEND_DIR = app.isPackaged ? path.join(process.resourcesPath, "backend") : path.join(ROOT, "backend")

export const FRONTEND_INDEX = path.join(ROOT, "frontend", "dist", "index.html")
export const ICON = path.join(ROOT, "build", "icon.png")

/** Dữ liệu người dùng (cài đặt, API key, lịch sử job, venv) — sống sót qua các lần cập nhật. */
export const userData = () => app.getPath("userData")
export const userDataDir = (...parts: string[]) => path.join(userData(), ...parts)
