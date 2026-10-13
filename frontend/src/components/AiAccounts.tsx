import { Bot, CheckCircle2, Loader2, LogIn, LogOut, Plus, Sparkles, Star, Trash2, Zap } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Section } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { AiResult, AiState } from "@/types/electron"

// Tài khoản ChatGPT / Gemini web: đăng nhập 1 lần trong Chrome thật, app giữ phiên và dùng thay API key.
export function AiAccounts() {
  const { refreshSystem } = useStore()
  const [state, setState] = useState<AiState | null>(null)
  const [busy, setBusy] = useState<string>("")
  const [loggingIn, setLoggingIn] = useState(false)
  const bridge = window.rf?.ai

  const reload = useCallback(() => { bridge?.state().then(setState).catch(() => {}) }, [bridge])
  useEffect(reload, [reload])

  if (!bridge) {
    return (
      <Section title="Tài khoản AI" icon={<Bot />} desc="Chỉ dùng được trong app desktop">
        <p className="text-xs text-muted-foreground">Mở ReviewFilm bằng Electron để đăng nhập ChatGPT / Gemini.</p>
      </Section>
    )
  }

  const run = async (key: string, fn: () => Promise<AiResult>, okMsg?: (r: AiResult) => string) => {
    setBusy(key)
    try {
      const r = await fn()
      if (r.state) setState(r.state)
      else reload()
      if (r.ok) { if (okMsg) toast.success(okMsg(r)) } else toast.error(r.error || "Thất bại")
      if (r.warn) toast.warning(r.warn)
      refreshSystem()
    } finally { setBusy("") }
  }

  const loginChatgpt = async () => {
    setLoggingIn(true)
    await run("gpt-login", bridge.chatgptLogin, (r) => `Đã lưu tài khoản ChatGPT ${r.state?.chatgpt.find((a) => a.isActive)?.email ?? ""}`)
    setLoggingIn(false)
  }

  const gem = state?.gemini
  return (
    <Section title="Tài khoản AI" icon={<Bot />} desc="Đăng nhập ChatGPT / Gemini một lần — AI viết kịch bản, dịch, xem phim đều chạy bằng tài khoản này">
      {/* ChatGPT */}
      <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          <span className="flex-1 text-[13px] font-medium">ChatGPT <span className="text-xs font-normal text-muted-foreground">— viết kịch bản, dịch, phân vai</span></span>
          {loggingIn ? (
            <Button size="sm" onClick={() => bridge.chatgptLoginDone()}><CheckCircle2 /> Đã đăng nhập xong</Button>
          ) : (
            <Button size="sm" variant="outline" disabled={!!busy} onClick={loginChatgpt}><Plus /> Thêm tài khoản</Button>
          )}
        </div>
        {loggingIn && <p className="text-[11px] text-muted-foreground">Đăng nhập chatgpt.com trong cửa sổ Chrome vừa mở, rồi bấm "Đã đăng nhập xong" (hoặc đóng cửa sổ).</p>}
        {state?.chatgpt.length === 0 && !loggingIn && <p className="text-xs text-muted-foreground">Chưa có tài khoản.</p>}
        {state?.chatgpt.map((a) => (
          <div key={a.id} className="flex items-center gap-2 rounded-md bg-muted/40 px-2.5 py-1.5 text-xs">
            <button title="Dùng tài khoản này" onClick={() => run(`act-${a.id}`, () => bridge.chatgptSetActive(a.id))}>
              <Star className={a.isActive ? "size-3.5 fill-primary text-primary" : "size-3.5 text-muted-foreground"} />
            </button>
            <span className="min-w-0 flex-1 truncate font-medium">{a.email || a.label}</span>
            {a.plan && <Badge variant="secondary">{a.plan}</Badge>}
            <StatusBadge status={a.status} error={a.errorMsg} />
            <Button size="xs" variant="ghost" disabled={!!busy} title="Gửi thử 1 câu"
              onClick={() => run(`chk-${a.id}`, () => bridge.chatgptCheck(a.id), (r) => `OK (${r.route === "http" ? "HTTP nhanh" : "qua trình duyệt"}): ${r.reply}`)}>
              {busy === `chk-${a.id}` ? <Loader2 className="animate-spin" /> : <Zap />} Kiểm tra
            </Button>
            <Button size="icon-xs" variant="ghost" disabled={!!busy} title="Xoá tài khoản + profile"
              onClick={() => { if (confirm(`Xoá tài khoản ${a.email}?`)) run(`del-${a.id}`, () => bridge.chatgptDelete(a.id), () => "Đã xoá") }}>
              <Trash2 />
            </Button>
          </div>
        ))}
      </div>

      {/* Gemini */}
      <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          <span className="flex-1 text-[13px] font-medium">Gemini <span className="text-xs font-normal text-muted-foreground">— Vision xem phim (bắt buộc cho Review nếu không có OpenAI key)</span></span>
          {gem?.loggedIn ? (
            <>
              <StatusBadge status={gem.status || "ok"} error={gem.errorMsg} />
              <Button size="xs" variant="ghost" disabled={!!busy} onClick={() => run("gem-chk", bridge.geminiCheck, (r) => `Gemini OK: ${r.reply}`)}>
                {busy === "gem-chk" ? <Loader2 className="animate-spin" /> : <Zap />} Kiểm tra
              </Button>
              <Button size="xs" variant="ghost" disabled={!!busy} onClick={() => run("gem-out", bridge.geminiLogout, () => "Đã đăng xuất Gemini")}><LogOut /> Đăng xuất</Button>
            </>
          ) : (
            <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run("gem-in", bridge.geminiLogin, () => "Đã đăng nhập Gemini")}>
              {busy === "gem-in" ? <Loader2 className="animate-spin" /> : <LogIn />} Đăng nhập Google
            </Button>
          )}
        </div>
        {busy === "gem-in" && <p className="text-[11px] text-muted-foreground">Đăng nhập Google trong cửa sổ Chrome vừa mở — app tự nhận khi xong (tối đa 5 phút).</p>}
      </div>
    </Section>
  )
}

function StatusBadge({ status, error }: { status: string; error?: string }) {
  if (status === "ok") return <Badge variant="outline" className="text-success">Hoạt động</Badge>
  if (status === "error") return <Badge variant="destructive" title={error}>Lỗi</Badge>
  return null
}
