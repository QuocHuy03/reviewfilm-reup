import { KeyRound, Loader2, ShieldCheck } from "lucide-react"
import { createContext, useCallback, useContext, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react"
import { toast } from "sonner"
import { ThemeToggle } from "@/app/theme"
import { LogoMark, LogoWordmark } from "@/components/layout/Logo"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { AuthResult } from "@/types/electron"

const REVERIFY_MS = 30 * 60_000

export type License = { key?: string; expiry?: string | null; start?: string | null; remaining?: string | null; offline?: boolean }
type AuthCtx = { license: License; deviceId: string; logout: () => Promise<void> }

const Ctx = createContext<AuthCtx | null>(null)

export const useAuth = () => {
  const c = useContext(Ctx)
  if (!c) throw new Error("useAuth phải nằm trong AuthGate")
  return c
}

/** Thời gian còn lại của key, dạng dễ đọc. null = không giới hạn. */
export function licenseLeft(expiry?: string | null, now = Date.now()) {
  if (!expiry) return null
  const ms = new Date(expiry).getTime() - now
  if (ms <= 0) return { ms, text: "Đã hết hạn", level: "expired" as const }
  const d = Math.floor(ms / 86_400_000)
  const h = Math.floor((ms % 86_400_000) / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  const text = d >= 3 ? `Còn ${d} ngày` : d >= 1 ? `Còn ${d} ngày ${h} giờ` : h >= 1 ? `Còn ${h} giờ ${m} phút` : `Còn ${Math.max(1, m)} phút`
  return { ms, text, level: d < 1 ? ("critical" as const) : d <= 7 ? ("warn" as const) : ("ok" as const) }
}

export function useNow(intervalMs = 30_000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), intervalMs); return () => clearInterval(t) }, [intervalMs])
  return now
}

/** Chặn toàn bộ app cho tới khi key hợp lệ. Backend Python chỉ được Electron khởi động sau khi xác thực. */
export function AuthGate({ children }: { children: ReactNode }) {
  const bridge = window.rf?.auth
  const [state, setState] = useState<"checking" | "locked" | "ok">(bridge ? "checking" : "ok")
  const [license, setLicense] = useState<License>({})
  const [deviceId, setDeviceId] = useState("")
  const [notice, setNotice] = useState("")

  const apply = useCallback((r: AuthResult) => {
    setLicense({ key: r.key, expiry: r.expiry, start: r.start, remaining: r.remaining, offline: r.offline })
    if (r.offline) toast.warning("Đang dùng chế độ offline", { description: r.error })
  }, [])

  useEffect(() => {
    if (!bridge) return
    bridge.deviceId().then(setDeviceId).catch(() => {})
    bridge.verify().then((r) => {
      if (r.success) { apply(r); setState("ok") }
      else { setNotice(r.error ?? ""); setState("locked") }
    }).catch(() => setState("locked"))
  }, [bridge, apply])

  // Xác thực lại định kỳ: key bị thu hồi / hết hạn → khoá app
  const stateRef = useRef(state)
  stateRef.current = state
  useEffect(() => {
    if (!bridge) return
    const t = setInterval(async () => {
      if (stateRef.current !== "ok") return
      const r = await bridge.verify()
      if (r.success) apply(r)
      else {
        await bridge.logout()
        setNotice(r.error || "Phiên sử dụng đã hết hạn — vui lòng nhập lại key")
        setState("locked")
      }
    }, REVERIFY_MS)
    return () => clearInterval(t)
  }, [bridge, apply])

  const logout = useCallback(async () => {
    await bridge?.logout()
    setLicense({}); setNotice(""); setState("locked")
  }, [bridge])

  if (state === "checking") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-background">
        <LogoMark className="size-12" />
        <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Đang xác thực bản quyền…</p>
      </div>
    )
  }
  if (state === "locked") {
    return <LoginScreen notice={notice} onSuccess={(r) => { apply(r); setState("ok") }} />
  }
  return <Ctx.Provider value={{ license, deviceId, logout }}>{children}</Ctx.Provider>
}

function LoginScreen({ notice, onSuccess }: { notice: string; onSuccess: (r: AuthResult) => void }) {
  const [key, setKey] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(notice)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!key.trim() || busy) return
    setBusy(true); setError("")
    try {
      const r = await window.rf!.auth.login(key.trim())
      if (r.success) { toast.success("Kích hoạt thành công"); onSuccess(r) }
      else setError(r.error || "Key không hợp lệ")
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="drag flex h-11 shrink-0 items-center justify-end pr-[150px] pl-4">
        <ThemeToggle />
      </div>
      <div className="flex flex-1 items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-[400px] rounded-2xl border border-border bg-card p-8 shadow-sm">
          <div className="flex flex-col items-center text-center">
            <LogoMark className="size-12" />
            <LogoWordmark className="mt-4 text-xl" />
            <p className="mt-1.5 text-sm text-muted-foreground">Nhập key bản quyền để bắt đầu sử dụng</p>
          </div>

          <div className="mt-7 flex flex-col gap-2">
            <label htmlFor="license" className="text-xs font-medium text-muted-foreground">License key</label>
            <div className="relative">
              <KeyRound className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input id="license" autoFocus value={key} onChange={(e) => { setKey(e.target.value); setError("") }}
                placeholder="XXXX-XXXX-XXXX-XXXX" className="h-10 pl-9 font-mono text-sm" aria-invalid={!!error} disabled={busy} />
            </div>
            {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
          </div>

          <Button type="submit" size="lg" className="mt-5 w-full" disabled={busy || !key.trim()}>
            {busy ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Kích hoạt
          </Button>

        </form>
      </div>
    </div>
  )
}

