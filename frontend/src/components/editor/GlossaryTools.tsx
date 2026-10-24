import { BookA, ChevronDown, ChevronUp, Loader2, Plus, Replace, Search, Trash2 } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"
import type { GlossaryEntry, Scene } from "@/lib/types"

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")

/** Khớp như backend (core/user_glossary.py): đúng chữ, riêng chữ cái đầu được khác hoa / thường; không cắt giữa từ. */
export function findPattern(find: string) {
  const s = find.trim()
  if (!s) return null
  const c = s[0]
  const head = c.toLowerCase() !== c.toUpperCase() ? `[${esc(c.toLowerCase())}${esc(c.toUpperCase())}]` : esc(c)
  return new RegExp(`(?<![\\p{L}\\p{N}_])${head}${esc(s.slice(1))}(?![\\p{L}\\p{N}_])`, "gu")
}

function replaceIn(text: string, rx: RegExp, good: string) {
  return text.replace(rx, (m) => (m[0] !== m[0].toLowerCase() && good[0] === good[0]?.toLowerCase() ? good[0].toUpperCase() + good.slice(1) : good))
}

/** Thanh "Tìm & thay" cho cả bản dịch — sửa 1 tên / cụm sai ở mọi câu một lần, tuỳ chọn lưu vào Từ điển cho các lần dịch sau. */
export function FindReplaceBar({ scenes, onChange, onPick }: {
  scenes: Scene[]; onChange: (next: Scene[]) => void; onPick: (index: number) => void
}) {
  const [find, setFind] = useState("")
  const [repl, setRepl] = useState("")
  const [save, setSave] = useState(true)
  const [cursor, setCursor] = useState(0)
  const [dictOpen, setDictOpen] = useState(false)
  const rx = useMemo(() => findPattern(find), [find])
  const hits = useMemo(() => {
    if (!rx) return []
    const one = new RegExp(rx.source, "u")       // không cờ g → test không nhớ vị trí giữa các câu
    return scenes.flatMap((s, i) => (one.test(s.voiceover || "") ? [i] : []))
  }, [rx, scenes])
  useEffect(() => setCursor(0), [find])

  const go = (d: number) => {
    if (!hits.length) return
    const k = (cursor + d + hits.length) % hits.length
    setCursor(k)
    onPick(hits[k])
  }

  const replaceAll = async () => {
    if (!rx || !hits.length) return
    const good = repl.trim()
    onChange(scenes.map((s) => {
      const t = replaceIn(s.voiceover || "", rx, good)
      return t === s.voiceover ? s : { ...s, voiceover: t, subtitle: t }
    }))
    let saved = false
    if (save && good && good !== find.trim()) {
      try { await api.addGlossary([{ goc: "", sai: find.trim(), viet: good }]); saved = true }
      catch (e) { toast.error("Không lưu được vào từ điển: " + (e as Error).message) }
    }
    toast.success(`Đã thay ở ${hits.length} câu` + (saved ? " · đã lưu vào Từ điển (lần sau dịch tự sửa)" : ""))
    setFind("")
    setRepl("")
  }

  return (
    <div className="sticky top-0 z-10 flex flex-col gap-2 border-b border-border/60 bg-card px-3 py-2.5 shadow-[0_1px_0_0_var(--border)]">
      <div className="flex items-center gap-1.5">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Tìm (vd tên dịch sai)…" className="h-8 pl-7 text-[13px]"
            onKeyDown={(e) => { if (e.key === "Enter") go(e.shiftKey ? -1 : 1) }} />
        </div>
        <span className="tabular min-w-12 text-center text-[11px] text-muted-foreground">
          {find.trim() ? (hits.length ? `${Math.min(cursor + 1, hits.length)}/${hits.length}` : "0 câu") : ""}
        </span>
        <Button variant="ghost" size="icon-xs" title="Câu trước (Shift+Enter)" disabled={!hits.length} onClick={() => go(-1)}><ChevronUp /></Button>
        <Button variant="ghost" size="icon-xs" title="Câu sau (Enter)" disabled={!hits.length} onClick={() => go(1)}><ChevronDown /></Button>
        <Button variant="outline" size="sm" className="h-8 gap-1 px-2 text-[12px]" title="Từ điển dịch của bạn" onClick={() => setDictOpen(true)}>
          <BookA className="size-3.5" /> Từ điển
        </Button>
      </div>
      {find.trim() && (
        <div className="flex items-center gap-1.5">
          <div className="relative flex-1">
            <Replace className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={repl} onChange={(e) => setRepl(e.target.value)} placeholder="Thay bằng…" className="h-8 pl-7 text-[13px]"
              onKeyDown={(e) => { if (e.key === "Enter") replaceAll() }} />
          </div>
          <Button size="sm" className="h-8 px-2.5 text-[12px]" disabled={!hits.length} onClick={replaceAll}>Thay tất cả</Button>
        </div>
      )}
      {find.trim() && (
        <label className="flex cursor-pointer items-center gap-2 text-[11.5px] text-muted-foreground">
          <Checkbox checked={save} onCheckedChange={(v) => setSave(v === true)} />
          Lưu vào Từ điển — các lần dịch sau tự sửa "{find.trim()}" thành "{repl.trim() || "…"}"
        </label>
      )}
      <GlossaryDialog open={dictOpen} onOpenChange={setDictOpen} />
    </div>
  )
}

/** Quản lý Từ điển dịch: chữ gốc → AI dịch đúng; cách dịch sai → tự thay sau khi dịch. */
export function GlossaryDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [rows, setRows] = useState<GlossaryEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    api.glossary().then((r) => setRows(r.entries)).catch((e) => toast.error((e as Error).message)).finally(() => setLoading(false))
  }, [open])

  const set = (i: number, patch: Partial<GlossaryEntry>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)))
  const valid = (e: GlossaryEntry) => !!e.viet.trim() && !!(e.goc.trim() || e.sai.trim())

  const saveAll = async () => {
    setSaving(true)
    try {
      const r = await api.saveGlossary(rows.filter(valid))
      setRows(r.entries)
      toast.success(`Đã lưu Từ điển · ${r.entries.length} mục`)
      onOpenChange(false)
    } catch (e) { toast.error((e as Error).message) } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Từ điển dịch của bạn</DialogTitle>
          <DialogDescription>
            Sửa 1 lần, các lần dịch sau tự theo. <b>Chữ gốc</b> (tiếng Trung…): AI luôn dịch đúng như cột "Dịch đúng".
            <b> Dịch sai</b>: dịch xong, mọi chỗ này tự thay thành "Dịch đúng". Điền ít nhất 1 trong 2 cột đầu.
          </DialogDescription>
        </DialogHeader>
        <div className="flex max-h-[55vh] flex-col gap-1.5 overflow-y-auto pr-1">
          <div className="grid grid-cols-[1fr_1fr_1fr_28px] gap-1.5 px-0.5 text-[11px] font-medium text-muted-foreground">
            <span>Chữ gốc (tuỳ chọn)</span><span>Dịch sai (tuỳ chọn)</span><span>Dịch đúng</span><span />
          </div>
          {loading && <div className="flex justify-center py-6 text-muted-foreground"><Loader2 className="animate-spin" /></div>}
          {!loading && rows.length === 0 && <p className="py-4 text-center text-[12px] text-muted-foreground">Chưa có mục nào — dùng "Tìm & thay" có tích Lưu, hoặc bấm Thêm.</p>}
          {rows.map((e, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_1fr_28px] items-center gap-1.5">
              <Input value={e.goc} onChange={(v) => set(i, { goc: v.target.value })} placeholder="vd 孟月" className="h-8 text-[13px]" />
              <Input value={e.sai} onChange={(v) => set(i, { sai: v.target.value })} placeholder="vd Mệnh Nguyệt" className="h-8 text-[13px]" />
              <Input value={e.viet} onChange={(v) => set(i, { viet: v.target.value })} placeholder="vd Mạnh Nguyệt"
                className={"h-8 text-[13px]" + (!valid(e) && (e.goc || e.sai || e.viet) ? " border-destructive" : "")} />
              <Button variant="ghost" size="icon-xs" title="Xoá" onClick={() => setRows((r) => r.filter((_, j) => j !== i))}><Trash2 /></Button>
            </div>
          ))}
        </div>
        <DialogFooter className="sm:justify-between">
          <Button variant="outline" size="sm" onClick={() => setRows((r) => [...r, { goc: "", sai: "", viet: "" }])}><Plus /> Thêm</Button>
          <Button size="sm" disabled={saving || loading} onClick={saveAll}>{saving && <Loader2 className="animate-spin" />} Lưu từ điển</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
