import { app } from "electron"
import fs from "node:fs"
import path from "node:path"
import { machineIdSync } from "node-machine-id"

const AUTH_URL = "https://serverkey.taothaoai.com/api/review_film/auth"
const TIMEOUT_MS = 15_000
const OFFLINE_GRACE_MS = 3 * 24 * 3600_000   // dùng offline tối đa 3 ngày từ lần xác thực online gần nhất

export type AuthResult = {
  success: boolean
  key?: string
  expiry?: string | null
  start?: string | null
  remaining?: string | null
  offline?: boolean
  error?: string
}

type Stored = { auth_key?: string; auth_expiry?: string; auth_start?: string; auth_remaining?: string; verified_at?: string }

const storeFile = () => path.join(app.getPath("userData"), "auth.json")

function readStore(): Stored {
  try { return JSON.parse(fs.readFileSync(storeFile(), "utf8")) } catch { return {} }
}

function writeStore(patch: Partial<Stored>) {
  const data = { ...readStore(), ...patch }
  for (const k of Object.keys(data) as (keyof Stored)[]) if (data[k] === undefined) delete data[k]
  fs.mkdirSync(path.dirname(storeFile()), { recursive: true })
  fs.writeFileSync(storeFile(), JSON.stringify(data, null, 2))
}

let cachedDeviceId: string | null = null
export function deviceId(): string {
  if (!cachedDeviceId) cachedDeviceId = machineIdSync()
  return cachedDeviceId
}

const parseDate = (raw: unknown, endOfDay = false): string | null => {
  if (!raw) return null
  const str = String(raw).trim()
  // "2026-11-22" (chỉ có ngày) → hết hạn cuối ngày đó theo giờ máy, không phải 00:00 UTC
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(str)
  const d = m ? new Date(+m[1], +m[2] - 1, +m[3], endOfDay ? 23 : 0, endOfDay ? 59 : 0, endOfDay ? 59 : 0) : new Date(str)
  return isNaN(d.getTime()) ? null : d.toISOString()
}

function extractLicenseInfo(data: any): { expiry: string | null; start: string | null; remaining: string | null } {
  const d = data?.data ?? data ?? {}
  return {
    expiry: parseDate(d.expires || d.expire_date || d.expires_at || d.expired_at || d.expiry_date || d.valid_until || d.end_date, true),
    start: parseDate(d.start_date || d.started_at || d.activation_date || d.created_at || d.begin_date),
    remaining: d.remaining != null ? String(d.remaining) : null,
  }
}

const isExpired = (expiry?: string | null) => !!expiry && new Date(expiry).getTime() < Date.now()

class NetworkError extends Error {}

/** Bỏ emoji trong message server (ký hiệu dấu X, dấu tích... ở đầu câu) */
const clean = (msg: string) =>
  msg.replace(/[\p{Extended_Pictographic}\u{FE0F}\u{200D}\u{20E3}]/gu, "").replace(/\s{2,}/g, " ").trim()

/** Gọi server. Trả về {ok,data,message}; ném NetworkError khi không kết nối được. */
async function callServer(key: string) {
  let res: Response
  try {
    res = await fetch(AUTH_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, device_id: deviceId() }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    })
  } catch (e) {
    throw new NetworkError(e instanceof Error && e.name === "TimeoutError" ? "Máy chủ xác thực không phản hồi" : "Không kết nối được máy chủ xác thực")
  }
  const data: any = await res.json().catch(() => ({}))
  // Server trả 403 {success:false,message} khi key sai; phòng trường hợp 200 nhưng success=false
  const ok = res.ok && data?.success !== false && data?.status !== false
  return { ok, data, message: clean(String(data?.message ?? "")) || `Máy chủ trả lỗi ${res.status}` }
}

function accept(key: string, data: any): AuthResult {
  const { expiry, start, remaining } = extractLicenseInfo(data)
  const stored = readStore()
  const exp = expiry ?? stored.auth_expiry ?? null
  if (isExpired(exp)) return { success: false, error: "Key đã hết hạn sử dụng", expiry: exp }
  const rem = remaining ?? stored.auth_remaining ?? null
  writeStore({ auth_key: key, auth_expiry: exp ?? undefined, auth_start: start ?? stored.auth_start, auth_remaining: rem ?? undefined, verified_at: new Date().toISOString() })
  return { success: true, key: maskKey(key), expiry: exp, start: start ?? stored.auth_start ?? null, remaining: rem }
}

export const maskKey = (k: string) => (k.length > 8 ? `${k.slice(0, 4)}••••${k.slice(-4)}` : "••••")

export async function login(rawKey: string): Promise<AuthResult> {
  const key = (rawKey || "").trim()
  if (!key) return { success: false, error: "Vui lòng nhập key" }
  try {
    const r = await callServer(key)
    return r.ok ? accept(key, r.data) : { success: false, error: r.message }
  } catch (e) {
    return { success: false, error: (e as Error).message }
  }
}

/** Xác thực lại key đã lưu. Mất mạng → cho dùng offline nếu key đã từng hợp lệ và chưa hết hạn. */
export async function verify(): Promise<AuthResult> {
  const stored = readStore()
  const key = stored.auth_key
  if (!key) return { success: false }
  try {
    const r = await callServer(key)
    if (r.ok) return accept(key, r.data)
    writeStore({ auth_key: undefined })   // server từ chối → bỏ key đã lưu
    return { success: false, error: r.message, expiry: stored.auth_expiry ?? null }
  } catch (e) {
    const expiry = stored.auth_expiry ?? null
    const fresh = stored.verified_at && Date.now() - new Date(stored.verified_at).getTime() < OFFLINE_GRACE_MS
    if (fresh && !isExpired(expiry)) {
      return { success: true, offline: true, key: maskKey(key), expiry, start: stored.auth_start ?? null, remaining: stored.auth_remaining ?? null, error: (e as Error).message }
    }
    return { success: false, error: (e as Error).message, expiry }
  }
}

export function logout() {
  writeStore({ auth_key: undefined, verified_at: undefined })
}
