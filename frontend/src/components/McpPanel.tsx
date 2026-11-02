import { Check, Copy, Eye, EyeOff, Loader2, Plug, RefreshCw } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Section, Segmented } from "@/components/common"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { confirmAction } from "@/components/ConfirmHost"

type McpInfo = {
  enabled: boolean; port: number | string; url: string; token: string
  claude_desktop: unknown; cursor: unknown; claude_code: string
}
type Client = "claude_desktop" | "cursor" | "claude_code"

const CLIENTS: { value: Client; label: string; how: string }[] = [
  { value: "claude_desktop", label: "Claude Desktop", how: "Claude Desktop → Settings → Developer → Edit Config → dán vào claude_desktop_config.json (gộp vào mục mcpServers nếu đã có) → thoát hẳn Claude Desktop rồi mở lại." },
  { value: "cursor", label: "Cursor / VS Code", how: "Cursor: Settings → MCP → Add new MCP server (hoặc dán vào ~/.cursor/mcp.json). VS Code / Windsurf: dán vào file cấu hình MCP tương tự." },
  { value: "claude_code", label: "Claude Code", how: "Chạy lệnh này trong terminal (1 lần)." },
]

const TOOLS = [
  "Tải video từ link (Douyin, TikTok, Bilibili, YouTube…)", "Tạo job Review / Dịch & Reup / Dịch phụ đề — 17 ngôn ngữ",
  "Chọn & nghe thử giọng (>1.200 giọng)", "Theo dõi tiến độ, chờ job xong", "Đọc & sửa kịch bản / bản dịch, duyệt bước chờ",
  "Lấy file xuất, xuất phụ đề SRT / VTT / ASS", "Dừng, chạy tiếp, chạy lại job",
]

/** Cài đặt → Kết nối AI (MCP): cho Claude Desktop / Cursor / Claude Code điều khiển ReviewFilm. */
export function McpPanel() {
  const [info, setInfo] = useState<McpInfo | null>(null)
  const [err, setErr] = useState("")
  const [client, setClient] = useState<Client>("claude_desktop")
  const [showToken, setShowToken] = useState(false)
  const [copied, setCopied] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.mcpInfo().then(setInfo).catch((e) => setErr((e as Error).message)) }, [])

  const text = !info ? "" : client === "claude_code" ? info.claude_code : JSON.stringify(info[client], null, 2)
  const copy = async (what: string, value: string) => {
    try { await navigator.clipboard.writeText(value); setCopied(what); setTimeout(() => setCopied(""), 1500) } catch { toast.error("Không sao chép được") }
  }
  const rotate = async () => {
    if (!(await confirmAction({ title: "Đổi token MCP?", desc: "Các AI đã kết nối sẽ mất quyền — phải dán lại cấu hình mới.", action: "Đổi token" }))) return
    setBusy(true)
    try { setInfo(await api.mcpRotate()); toast.success("Đã đổi token — dán lại cấu hình cho các AI") } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }
  const mask = (t: string) => (showToken ? t : t.slice(0, 4) + "•".repeat(Math.max(0, t.length - 8)) + t.slice(-4))
  const shown = info && !showToken ? text.split(info.token).join(mask(info.token)) : text

  return (
    <div className="flex flex-col gap-4">
      <Section title="Kết nối AI (MCP)" icon={<Plug />}
        desc="Cho Claude Desktop, Cursor, Claude Code… điều khiển ReviewFilm bằng lời: tải video, tạo video review / dịch / lồng tiếng, sửa kịch bản, lấy file — như bạn tự bấm trong app.">
        {err && <p className="text-xs text-destructive">Chưa bật được MCP: {err}</p>}
        {!info && !err && <p className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> Đang đọc cấu hình…</p>}
        {info && (
          <>
            <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-2 text-xs">
              <span className="text-muted-foreground">Địa chỉ</span>
              <code className="truncate rounded bg-muted px-2 py-1 font-mono">{info.url}</code>
              <Button size="xs" variant="ghost" onClick={() => copy("url", info.url)}>{copied === "url" ? <Check /> : <Copy />}</Button>
              <span className="text-muted-foreground">Token</span>
              <code className="truncate rounded bg-muted px-2 py-1 font-mono">{mask(info.token)}</code>
              <span className="flex gap-0.5">
                <Button size="icon-xs" variant="ghost" title={showToken ? "Ẩn" : "Hiện"} onClick={() => setShowToken(!showToken)}>{showToken ? <EyeOff /> : <Eye />}</Button>
                <Button size="icon-xs" variant="ghost" title="Sao chép token" onClick={() => copy("token", info.token)}>{copied === "token" ? <Check /> : <Copy />}</Button>
                <Button size="icon-xs" variant="ghost" title="Đổi token (lỡ lộ)" disabled={busy} onClick={rotate}><RefreshCw /></Button>
              </span>
            </div>
            <div className="flex flex-col gap-2">
              <Segmented size="sm" value={client} onChange={setClient} items={CLIENTS.map((c) => ({ value: c.value, label: c.label }))} />
              <p className="text-[11.5px] text-muted-foreground">{CLIENTS.find((c) => c.value === client)?.how}</p>
              <div className="relative">
                <pre className="max-h-64 overflow-auto rounded-lg border border-border bg-muted/50 p-3 pr-24 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap">{shown}</pre>
                <Button size="sm" className="absolute top-2 right-2" onClick={() => copy("cfg", text)}>
                  {copied === "cfg" ? <><Check /> Đã chép</> : <><Copy /> Sao chép</>}
                </Button>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Chỉ máy này kết nối được (127.0.0.1) và cần đúng token. ReviewFilm phải đang mở khi AI dùng. Đổi token nếu lỡ gửi cấu hình cho người khác.
            </p>
          </>
        )}
      </Section>
      <Section title="AI làm được gì" icon={<Check />} desc="Ví dụ nói với Claude: “Tải link Douyin này, làm video review tiếng Anh 3 phút giọng nữ, xong gửi mình file.”">
        <ul className="grid list-disc grid-cols-2 gap-x-6 gap-y-1 pl-4 text-xs text-muted-foreground">
          {TOOLS.map((t) => <li key={t}>{t}</li>)}
        </ul>
      </Section>
    </div>
  )
}
