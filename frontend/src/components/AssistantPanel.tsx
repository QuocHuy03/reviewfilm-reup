import {
  AlertTriangle, Check, Copy, FileText, ImageIcon, Loader2, MessageSquarePlus, Minus, Paperclip, RefreshCw, SendHorizontal, Settings, Sparkles, X,
} from "lucide-react"
import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Button } from "@/components/ui/button"
import { api, mediaUrl } from "@/lib/api"
import { cn } from "@/lib/utils"

/*
 * Trợ lý AI — khung chat nổi góc dưới bên phải (kiểu chat hỗ trợ): hỏi cách dùng app, nhờ giải thích lỗi job,
 * gửi kèm ảnh chụp màn hình (Gemini đọc ảnh) hoặc file chữ (.srt, .log, .txt…). Dùng tài khoản ChatGPT / Gemini đã đăng nhập.
 * Mở / đóng: nút tròn góc dưới phải, nút "Trợ lý AI" trên thanh tiêu đề (sự kiện "rf:assistant"), Esc để thu nhỏ.
 */

type Msg = { role: "user" | "assistant"; content: string; error?: boolean; images?: string[]; files?: string[] }
type Status = { ready: boolean; chatgpt: boolean; gemini: boolean }
type Attach =
  | { id: string; kind: "image"; name: string; preview: string; path?: string; uploading: boolean }
  | { id: string; kind: "text"; name: string; text: string }

const STORE_KEY = "rf.assistant.chat.v2"
const MAX_SAVED = 60
const TEXT_EXTS = /\.(srt|vtt|ass|txt|log|json|md|csv)$/i
const IMAGE_EXTS = /\.(png|jpe?g|webp|gif)$/i
const MAX_TEXT_CHARS = 12000

const STARTERS = [
  "Làm sao lồng tiếng Việt cho phim có phụ đề Trung?",
  "Job đang mở bị lỗi — nguyên nhân và cách sửa?",
  "Nên chọn giọng đọc nào cho video review?",
  "Timeline phụ đề có những phím tắt gì?",
  "Tải cả bộ phim ngắn rồi làm hàng loạt thế nào?",
]

const NOT_READY_FALLBACK = 'Cần đăng nhập ChatGPT hoặc Gemini: Cài đặt → tab "Tài khoản AI".'

/** Mở / đóng trợ lý từ nơi khác (nút trên thanh tiêu đề). */
export const toggleAssistant = () => window.dispatchEvent(new Event("rf:assistant"))

function loadChat(): Msg[] {
  try {
    const v = JSON.parse(localStorage.getItem(STORE_KEY) || "[]") as Msg[]
    return Array.isArray(v) ? v.filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string") : []
  } catch { return [] }
}
function saveChat(msgs: Msg[]) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(msgs.slice(-MAX_SAVED))) } catch { /* bị chặn / đầy */ }
}
const readDataUrl = (f: File) => new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result)); r.onerror = rej; r.readAsDataURL(f) })

/* ---------- markdown tối giản, an toàn (chỉ tạo phần tử React) ---------- */
function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`)/g
  let last = 0, k = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    if (m[2] !== undefined) out.push(<strong key={`${keyBase}-b${k++}`} className="font-semibold text-foreground">{m[2]}</strong>)
    else out.push(<code key={`${keyBase}-c${k++}`} className="rounded bg-muted px-1 py-px font-mono text-[11.5px]">{m[3]}</code>)
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}
type Block = { kind: "p"; lines: string[] } | { kind: "ol" | "ul"; items: string[]; start: number } | { kind: "code"; text: string }
function parseBlocks(src: string): Block[] {
  const blocks: Block[] = []
  const lines = src.replace(/\r\n/g, "\n").split("\n")
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (/^\s*```/.test(line)) {
      const buf: string[] = []
      i++
      while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++])
      i++
      blocks.push({ kind: "code", text: buf.join("\n") })
      continue
    }
    const ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/)
    const ul = line.match(/^\s*[-*•]\s+(.*)$/)
    if (ol || ul) {
      const kind = ol ? "ol" : "ul"
      const items: string[] = []
      while (i < lines.length) {
        const a = kind === "ol" ? lines[i].match(/^\s*\d+[.)]\s+(.*)$/) : lines[i].match(/^\s*[-*•]\s+(.*)$/)
        if (a) { items.push(a[1]); i++; continue }
        if (items.length && /^\s{2,}\S/.test(lines[i])) { items[items.length - 1] += " " + lines[i].trim(); i++; continue }
        break
      }
      blocks.push({ kind, items, start: ol ? Number(ol[1]) : 1 })
      continue
    }
    if (!line.trim()) { i++; continue }
    const buf: string[] = []
    while (i < lines.length && lines[i].trim() && !/^\s*(\d+[.)]|[-*•])\s+/.test(lines[i]) && !/^\s*```/.test(lines[i])) buf.push(lines[i++].replace(/^#{1,6}\s+/, ""))
    blocks.push({ kind: "p", lines: buf })
  }
  return blocks
}
function Markdown({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-2">
      {parseBlocks(text).map((b, bi) => {
        if (b.kind === "code") return <pre key={bi} className="overflow-x-auto rounded-md bg-muted px-2.5 py-2 font-mono text-[11.5px] whitespace-pre-wrap">{b.text}</pre>
        if (b.kind === "p") return <p key={bi}>{b.lines.map((l, li) => <Fragment key={li}>{li > 0 && <br />}{inline(l, `${bi}-${li}`)}</Fragment>)}</p>
        const List = b.kind === "ol" ? "ol" : "ul"
        return (
          <List key={bi} start={b.kind === "ol" ? b.start : undefined}
            className={cn("flex flex-col gap-1 pl-5", b.kind === "ol" ? "list-decimal marker:font-semibold marker:text-primary" : "list-disc marker:text-muted-foreground")}>
            {b.items.map((it, ii) => <li key={ii} className="pl-0.5">{inline(it, `${bi}-${ii}`)}</li>)}
          </List>
        )
      })}
    </div>
  )
}

/* ---------- khung chat nổi ---------- */
export function AssistantWidget() {
  const { page, activeJobId, go } = useStore()
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>(loadChat)
  const [input, setInput] = useState("")
  const [atts, setAtts] = useState<Attach[]>([])
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<Status | null>(null)
  const [notReadyMsg, setNotReadyMsg] = useState("")
  const [copied, setCopied] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const openRef = useRef(open)
  openRef.current = open

  useEffect(() => { saveChat(msgs) }, [msgs])
  useEffect(() => {
    const t = () => setOpen((v) => !v)
    window.addEventListener("rf:assistant", t)
    return () => window.removeEventListener("rf:assistant", t)
  }, [])

  const checkStatus = useCallback(() => {
    api.assistantStatus().then((s) => { setStatus(s); if (s.ready) setNotReadyMsg("") }).catch(() => setStatus(null))
  }, [])
  useEffect(() => {
    if (!open) return
    setUnread(false)
    checkStatus()
    const t = setTimeout(() => inputRef.current?.focus(), 60)
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false) } }
    window.addEventListener("keydown", onKey, true)
    return () => { clearTimeout(t); window.removeEventListener("keydown", onKey, true) }
  }, [open, checkStatus])
  useEffect(() => { const el = listRef.current; if (el) el.scrollTop = el.scrollHeight }, [msgs, busy, open])

  // ── đính kèm: ảnh tải lên ngay (để gửi nhanh), file chữ đọc nội dung ──
  const addFiles = async (files: File[]) => {
    for (const f of files.slice(0, 6)) {
      const id = Math.random().toString(36).slice(2)
      if (f.type.startsWith("image/") || IMAGE_EXTS.test(f.name)) {
        if (f.size > 8 << 20) { toast.error(`${f.name}: ảnh quá lớn (tối đa 8 MB)`); continue }
        const name = IMAGE_EXTS.test(f.name) ? f.name : `anh-chup.${(f.type.split("/")[1] || "png").replace("jpeg", "jpg")}`
        const preview = URL.createObjectURL(f)
        setAtts((a) => [...a, { id, kind: "image", name, preview, uploading: true }])
        try {
          const r = await api.assistantUpload(name, await readDataUrl(f))
          setAtts((a) => a.map((x) => (x.id === id ? { ...x, path: r.path, uploading: false } as Attach : x)))
        } catch (e) {
          setAtts((a) => a.filter((x) => x.id !== id))
          toast.error("Không gửi kèm được ảnh", { description: (e as Error).message })
        }
      } else if (TEXT_EXTS.test(f.name) || f.type.startsWith("text/")) {
        if (f.size > 2 << 20) { toast.error(`${f.name}: file quá lớn (tối đa 2 MB)`); continue }
        const text = (await f.text()).slice(0, MAX_TEXT_CHARS)
        setAtts((a) => [...a, { id, kind: "text", name: f.name, text }])
      } else toast.error(`${f.name}: chỉ gửi kèm được ảnh hoặc file chữ (.srt, .txt, .log…)`)
    }
  }
  const removeAtt = (id: string) => setAtts((a) => a.filter((x) => x.id !== id))

  const send = async (text?: string) => {
    const q = (text ?? input).trim()
    if ((!q && !atts.length) || busy || atts.some((a) => a.kind === "image" && a.uploading)) return
    const images = atts.flatMap((a) => (a.kind === "image" && a.path ? [a.path] : []))
    const texts = atts.filter((a): a is Extract<Attach, { kind: "text" }> => a.kind === "text")
    const question = q || (images.length ? "Xem ảnh giúp mình — có vấn đề gì và sửa thế nào?" : "Xem file giúp mình.")
    const full = question + texts.map((t) => `\n\n[Tệp đính kèm: ${t.name}]\n\`\`\`\n${t.text}\n\`\`\``).join("")
    const shown: Msg = { role: "user", content: question, images: images.length ? images : undefined, files: texts.length ? texts.map((t) => t.name) : undefined }
    const history = [...msgs.filter((m) => !m.error).map(({ role, content }) => ({ role, content })), { role: "user" as const, content: full }]
    setMsgs((m) => [...m, shown])
    setInput("")
    setAtts([])
    setBusy(true)
    try {
      const r = await api.assistantAsk(history, activeJobId, page, images)
      setMsgs((m) => [...m, { role: "assistant", content: r.answer }])
      if (!openRef.current) setUnread(true)
    } catch (e) {
      const msg = (e as Error).message || "Có lỗi khi hỏi trợ lý."
      if (/^409\b/.test(msg) || /cần tài khoản ChatGPT hoặc Gemini/i.test(msg)) {
        setNotReadyMsg(/^409\b/.test(msg) ? NOT_READY_FALLBACK : msg)
        setStatus((s) => (s ? { ...s, ready: false } : { ready: false, chatgpt: false, gemini: false }))
      }
      setMsgs((m) => [...m, { role: "assistant", content: /Failed to fetch|NetworkError/i.test(msg) ? "Chưa kết nối được backend — đợi app khởi động xong rồi thử lại." : msg, error: true }])
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  const copy = async (i: number, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(i); setTimeout(() => setCopied(null), 1500) } catch { /* bị chặn */ }
  }
  const notReady = status ? !status.ready : !!notReadyMsg
  const online = status?.ready
  const uploading = atts.some((a) => a.kind === "image" && a.uploading)

  return (
    <>
      {/* nút tròn mở nhanh — ẩn ở Studio (để không che timeline; ở đó mở bằng nút trên thanh tiêu đề) */}
      {!open && page !== "studio" && (
        <button onClick={() => setOpen(true)} title="Trợ lý AI" aria-label="Mở Trợ lý AI"
          className="no-drag fixed right-5 bottom-5 z-50 flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg shadow-primary/30 ring-4 ring-primary/10 transition hover:scale-105 animate-in fade-in zoom-in-90">
          <Sparkles className="size-5" />
          {unread && <span className="absolute top-0.5 right-0.5 size-3 rounded-full border-2 border-background bg-destructive" />}
        </button>
      )}

      {open && (
        <section role="dialog" aria-label="Trợ lý AI"
          onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragOver(true) } }}
          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(false) }}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); addFiles(Array.from(e.dataTransfer.files)) }}
          className="no-drag fixed right-5 bottom-5 z-50 flex h-[min(620px,calc(100vh-96px))] w-[min(390px,calc(100vw-40px))] flex-col overflow-hidden rounded-2xl border border-border bg-background shadow-2xl shadow-black/40 animate-in fade-in slide-in-from-bottom-4 duration-200">
          {/* tiêu đề */}
          <header className="flex shrink-0 items-center gap-2.5 border-b border-border bg-gradient-to-r from-primary/12 via-primary/5 to-transparent px-3.5 py-2.5">
            <span className="relative flex size-8 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <Sparkles className="size-4" />
              <span className={cn("absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full border-2 border-background", online ? "bg-success" : "bg-muted-foreground/60")} />
            </span>
            <div className="min-w-0 flex-1 leading-tight">
              <p className="text-[13.5px] font-semibold">Trợ lý AI</p>
              <p className="truncate text-[10.5px] text-muted-foreground">
                {online ? `Đã kết nối · ${[status?.chatgpt && "ChatGPT", status?.gemini && "Gemini"].filter(Boolean).join(" + ")}` : "Chưa kết nối tài khoản AI"}
              </p>
            </div>
            <Button size="icon-sm" variant="ghost" title="Cuộc trò chuyện mới" onClick={() => { setMsgs([]); setAtts([]); setInput("") }} disabled={busy || msgs.length === 0}><MessageSquarePlus /></Button>
            <Button size="icon-sm" variant="ghost" title="Thu nhỏ (Esc)" onClick={() => setOpen(false)}><Minus /></Button>
          </header>

          {notReady && (
            <div className="mx-3 mt-3 flex shrink-0 flex-col gap-2 rounded-xl border border-warning/40 bg-warning/8 p-3 text-xs">
              <p className="flex items-center gap-1.5 font-medium text-warning"><AlertTriangle className="size-3.5" /> Chưa kết nối tài khoản AI</p>
              <p className="leading-relaxed text-muted-foreground">{notReadyMsg || NOT_READY_FALLBACK}</p>
              <div className="flex gap-1.5">
                <Button size="xs" onClick={() => { go("settings"); setOpen(false) }}><Settings /> Mở Cài đặt</Button>
                <Button size="xs" variant="ghost" onClick={checkStatus}><RefreshCw /> Kiểm tra lại</Button>
              </div>
            </div>
          )}

          {/* tin nhắn */}
          <div ref={listRef} className="relative min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
            {msgs.length === 0 ? (
              <div className="flex flex-col gap-3 pt-2">
                <div className="rounded-xl border border-border bg-card px-3 py-2.5 text-[12.5px] leading-relaxed text-foreground/90">
                  Chào bạn! Mình là trợ lý của ReviewFilm Studio. Hỏi mình cách làm video, chọn giọng, sửa phụ đề, hay gửi ảnh chụp lỗi —
                  mình hướng dẫn từng bước, đúng tên nút trong app.
                </div>
                <p className="px-0.5 text-[10.5px] font-semibold tracking-wider text-muted-foreground uppercase">Câu hỏi gợi ý</p>
                <div className="flex flex-col gap-1.5">
                  {STARTERS.map((s) => (
                    <button key={s} onClick={() => send(s)} disabled={busy}
                      className="rounded-lg border border-border px-3 py-2 text-left text-[12.5px] text-foreground/85 transition hover:border-primary/50 hover:bg-primary/5 disabled:opacity-50">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {msgs.map((m, i) => m.role === "user" ? (
                  <div key={i} className="flex flex-col items-end gap-1">
                    {!!m.images?.length && (
                      <div className="flex max-w-[85%] flex-wrap justify-end gap-1">
                        {m.images.map((p) => <img key={p} src={mediaUrl(p)} alt="" className="h-20 max-w-[160px] rounded-lg border border-border object-cover" />)}
                      </div>
                    )}
                    {!!m.files?.length && (
                      <div className="flex max-w-[85%] flex-wrap justify-end gap-1">
                        {m.files.map((f) => <span key={f} className="flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-[11px]"><FileText className="size-3" />{f}</span>)}
                      </div>
                    )}
                    <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3 py-2 text-[13px] leading-relaxed whitespace-pre-wrap text-primary-foreground">{m.content}</div>
                  </div>
                ) : (
                  <div key={i} className="group flex gap-2">
                    <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-lg",
                      m.error ? "bg-destructive/10 text-destructive" : "bg-primary/12 text-primary")}>
                      {m.error ? <AlertTriangle className="size-3.5" /> : <Sparkles className="size-3.5" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className={cn("rounded-2xl rounded-tl-md border px-3 py-2 text-[13px] leading-relaxed",
                        m.error ? "border-destructive/30 bg-destructive/5 text-destructive" : "border-border bg-card text-foreground/90")}>
                        {m.error ? m.content : <Markdown text={m.content} />}
                      </div>
                      {!m.error && (
                        <button onClick={() => copy(i, m.content)} title="Chép câu trả lời"
                          className="mt-1 flex items-center gap-1 rounded px-1 text-[10.5px] text-muted-foreground opacity-0 transition group-hover:opacity-100 hover:text-foreground focus-visible:opacity-100">
                          {copied === i ? <><Check className="size-3" /> Đã chép</> : <><Copy className="size-3" /> Chép</>}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {busy && (
                  <div className="flex items-center gap-2 pl-8 text-xs text-muted-foreground">
                    <span className="flex gap-1">{[0, 1, 2].map((d) => <span key={d} className="size-1.5 animate-bounce rounded-full bg-primary/70" style={{ animationDelay: `${d * 120}ms` }} />)}</span>
                    Đang trả lời…
                  </div>
                )}
              </div>
            )}
            {dragOver && (
              <div className="pointer-events-none absolute inset-2 flex flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-primary bg-background/90 text-[12.5px] font-medium text-primary">
                <Paperclip className="size-5" /> Thả ảnh / file vào đây
              </div>
            )}
          </div>

          {/* ô nhập + đính kèm */}
          <div className="shrink-0 border-t border-border p-2.5">
            {atts.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {atts.map((a) => (
                  <div key={a.id} className="group relative flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 py-1 pr-6 pl-1 text-[11px]">
                    {a.kind === "image"
                      ? <span className="relative size-8 overflow-hidden rounded-md bg-muted">
                          <img src={a.preview} alt="" className="size-full object-cover" />
                          {a.uploading && <span className="absolute inset-0 flex items-center justify-center bg-black/50"><Loader2 className="size-3.5 animate-spin text-white" /></span>}
                        </span>
                      : <span className="flex size-8 items-center justify-center rounded-md bg-background text-muted-foreground"><FileText className="size-4" /></span>}
                    <span className="max-w-[120px] truncate">{a.name}</span>
                    <button onClick={() => removeAtt(a.id)} title="Bỏ" className="absolute top-1/2 right-1 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"><X className="size-3" /></button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-end gap-1.5 rounded-xl border border-input bg-card px-1.5 py-1.5 focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-primary/15">
              <input ref={fileRef} type="file" multiple hidden accept="image/*,.srt,.vtt,.ass,.txt,.log,.json,.md,.csv"
                onChange={(e) => { addFiles(Array.from(e.target.files ?? [])); e.target.value = "" }} />
              <Button size="icon-sm" variant="ghost" className="shrink-0 text-muted-foreground" title="Gửi kèm ảnh / file (hoặc kéo thả, Ctrl+V ảnh)" onClick={() => fileRef.current?.click()}>
                <Paperclip />
              </Button>
              <textarea ref={inputRef} value={input} rows={1} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }}
                onPaste={(e) => {
                  const files = Array.from(e.clipboardData.files)
                  if (files.length) { e.preventDefault(); addFiles(files) }
                }}
                onInput={(e) => { const t = e.currentTarget; t.style.height = "auto"; t.style.height = `${Math.min(140, t.scrollHeight)}px` }}
                placeholder="Hỏi gì cũng được… (Enter gửi)"
                className="max-h-[140px] min-h-[32px] flex-1 resize-none bg-transparent px-1 py-1.5 text-[13px] leading-snug outline-none placeholder:text-muted-foreground" />
              <Button size="icon-sm" className="shrink-0 rounded-lg" title="Gửi (Enter)" disabled={busy || uploading || (!input.trim() && !atts.length)} onClick={() => send()}>
                {busy ? <Loader2 className="animate-spin" /> : <SendHorizontal />}
              </Button>
            </div>
            <p className="mt-1.5 flex items-center gap-1 px-1 text-[10.5px] text-muted-foreground">
              <ImageIcon className="size-3" /> Dán ảnh chụp lỗi bằng Ctrl+V · {activeJobId ? "trợ lý xem được job đang mở" : "trả lời theo hướng dẫn của app"}
            </p>
          </div>
        </section>
      )}
    </>
  )
}
