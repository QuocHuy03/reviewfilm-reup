import { Check, Copy, ExternalLink, FolderOpen, ImageIcon, Loader2, Megaphone, RefreshCw, Sparkles } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Segmented } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { api, bridge, mediaUrl } from "@/lib/api"
import type { PublishPack, PublishPost } from "@/lib/types"
import { cn } from "@/lib/utils"

const PLATFORMS = [
  { key: "youtube", label: "YouTube", title: 100, body: 5000 },
  { key: "shorts", label: "Shorts", title: 100, body: 1000 },
  { key: "tiktok", label: "TikTok", title: 0, body: 2200 },
  { key: "facebook", label: "Facebook", title: 0, body: 2000 },
  { key: "instagram", label: "Instagram", title: 0, body: 2200 },
] as const
type PlatformKey = (typeof PLATFORMS)[number]["key"]

const TONES = [
  { value: "hap-dan", label: "Hấp dẫn" },
  { value: "hai-huoc", label: "Hài hước" },
  { value: "nghiem-tuc", label: "Nghiêm túc" },
  { value: "cam-xuc", label: "Cảm xúc" },
]

function useCopy() {
  const [done, setDone] = useState("")
  const copy = async (id: string, text: string) => {
    try { await navigator.clipboard.writeText(text); setDone(id); setTimeout(() => setDone((d) => (d === id ? "" : d)), 1500) }
    catch { toast.error("Không sao chép được") }
  }
  return { done, copy }
}

/** Ô nội dung có đếm ký tự theo giới hạn nền tảng + nút sao chép. */
function CopyField({ id, label, value, onChange, limit, rows = 1, copy, done }: {
  id: string; label: string; value: string; onChange: (v: string) => void; limit?: number; rows?: number
  copy: (id: string, t: string) => void; done: string
}) {
  const over = limit ? value.length > limit : false
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <div className="flex items-center gap-2">
          {limit ? <span className={cn("tabular text-[10.5px]", over ? "text-destructive" : "text-muted-foreground")}>{value.length}/{limit}</span> : null}
          <Button variant="ghost" size="xs" onClick={() => copy(id, value)} disabled={!value}>
            {done === id ? <Check /> : <Copy />} {done === id ? "Đã chép" : "Chép"}
          </Button>
        </div>
      </div>
      {rows > 1
        ? <Textarea value={value} rows={rows} onChange={(e) => onChange(e.target.value)} className="resize-y text-[13px] leading-relaxed" />
        : <Input value={value} onChange={(e) => onChange(e.target.value)} className="text-[13px]" />}
    </div>
  )
}

/** Tóm tắt ở cột phải màn Hoàn thành + nút mở hộp Bài đăng AI. */
export function PublishSummary({ jobId, initial }: { jobId: string; initial?: PublishPack }) {
  const [open, setOpen] = useState(false)
  const [pack, setPack] = useState(initial)
  useEffect(() => setPack(initial), [initial])
  const n = pack ? Object.keys(pack.platforms).length : 0
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <h4 className="text-[10.5px] font-semibold tracking-wider text-muted-foreground uppercase">Bài đăng AI</h4>
        {pack && <span className="text-[10.5px] text-success">{n} nền tảng · {pack.thumbnails.length} thumbnail</span>}
      </div>
      <button onClick={() => setOpen(true)}
        className="flex w-full items-center gap-3 rounded-lg border border-border bg-background/40 px-3 py-2.5 text-left transition hover:border-primary/40">
        {pack?.thumbnails[0]
          ? <img src={`${mediaUrl(pack.thumbnails[0].path)}&v=${pack.thumbnails[0].v ?? 0}`} className="h-10 w-[71px] shrink-0 rounded object-cover" alt="" />
          : <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary"><Megaphone className="size-4" /></span>}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[12.5px] font-medium">{pack?.platforms.youtube?.title || (pack ? "Đã có bài đăng" : "Viết bài đăng cho YouTube, TikTok, Facebook…")}</span>
          <span className="block text-[11px] text-muted-foreground">{pack ? "Bấm để xem, sửa, sao chép" : "AI viết tiêu đề, mô tả, hashtag + thumbnail"}</span>
        </span>
      </button>
      <PublishDialog jobId={jobId} open={open} onOpenChange={setOpen} pack={pack} setPack={setPack} />
    </section>
  )
}

function PublishDialog({ jobId, open, onOpenChange, pack, setPack }: {
  jobId: string; open: boolean; onOpenChange: (v: boolean) => void; pack?: PublishPack; setPack: (p: PublishPack) => void
}) {
  const [tab, setTab] = useState<PlatformKey>("youtube")
  const [tone, setTone] = useState(pack?.tone ?? "hap-dan")
  const [extra, setExtra] = useState("")
  const [busy, setBusy] = useState(false)
  const [edits, setEdits] = useState<Record<string, PublishPost>>({})
  const [thumbText, setThumbText] = useState<Record<number, string>>({})
  const [thumbBusy, setThumbBusy] = useState<number | null>(null)
  const { done, copy } = useCopy()

  useEffect(() => { setEdits({}); setThumbText({}) }, [pack?.at])

  const run = async () => {
    setBusy(true)
    try { const p = await api.publish(jobId, { tone, extra }); setPack(p); toast.success("Đã viết bài đăng cho 5 nền tảng") }
    catch (e) { toast.error("Chưa viết được bài đăng", { description: (e as Error).message }) }
    finally { setBusy(false) }
  }
  const redraw = async (i: number) => {
    setThumbBusy(i)
    try { setPack(await api.publishThumbnail(jobId, i, thumbText[i] ?? pack!.thumbnails[i].text)) }
    catch (e) { toast.error((e as Error).message) }
    finally { setThumbBusy(null) }
  }

  const spec = PLATFORMS.find((p) => p.key === tab)!
  const post = edits[tab] ?? pack?.platforms[tab]
  const setPost = (patch: Partial<PublishPost>) => post && setEdits({ ...edits, [tab]: { ...post, ...patch } })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Megaphone className="size-4 text-primary" /> Bài đăng AI</DialogTitle>
          <DialogDescription>ChatGPT/Gemini viết tiêu đề, mô tả, hashtag đúng kiểu từng nền tảng. Sửa trực tiếp rồi bấm Chép để dán lên nền tảng.</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-2">
          <Segmented size="sm" value={tone} onChange={setTone} items={TONES} />
          <Input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="Yêu cầu thêm (tuỳ chọn) — vd: nhắc tên kênh Phim Hay Mỗi Ngày" className="h-8 min-w-60 flex-1 text-xs" />
          <Button size="sm" onClick={run} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : pack ? <RefreshCw /> : <Sparkles />} {busy ? "AI đang viết…" : pack ? "Viết lại" : "Viết bài đăng"}
          </Button>
        </div>

        {!pack ? (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border px-6 py-12 text-center">
            <Megaphone className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">Chưa có bài đăng</p>
            <p className="max-w-md text-xs text-muted-foreground">Chọn giọng văn rồi bấm <b>Viết bài đăng</b> — khoảng 30–60 giây. Kết quả gồm YouTube (có mốc chương), Shorts, TikTok, Facebook, Instagram và 3 thumbnail.</p>
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
            <div className="flex min-w-0 flex-col gap-3">
              <Segmented value={tab} onChange={setTab} items={PLATFORMS.map((p) => ({ value: p.key, label: p.label }))} />
              {post && <>
                {spec.title > 0 && <CopyField id={`${tab}-title`} label="Tiêu đề" value={post.title ?? ""} onChange={(v) => setPost({ title: v })} limit={spec.title} copy={copy} done={done} />}
                <CopyField id={`${tab}-text`} label={tab === "youtube" ? "Mô tả (đã gồm mốc chương + hashtag)" : "Nội dung đăng (đã gồm hashtag)"}
                  value={post.text} onChange={(v) => setPost({ text: v })} limit={spec.body} rows={tab === "youtube" ? 12 : 7} copy={copy} done={done} />
                {tab === "youtube" && (post.tags?.length ?? 0) > 0 &&
                  <CopyField id="yt-tags" label="Tags (dán vào ô Thẻ của YouTube Studio)" value={(post.tags ?? []).join(", ")}
                    onChange={(v) => setPost({ tags: v.split(",").map((x) => x.trim()).filter(Boolean) })} limit={500} copy={copy} done={done} />}
                {tab === "youtube" && !post.chapters?.length &&
                  <p className="text-[11px] text-muted-foreground">Không chèn mốc chương: YouTube chỉ nhận chương khi video ≥ 1 phút và có ≥ 3 mốc cách nhau ≥ 10 giây.</p>}
              </>}
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-xs font-medium text-muted-foreground">Thumbnail · {pack.thumbnails.length}</span>
              {pack.thumbnails.length === 0 && <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><ImageIcon className="size-3.5" /> Chưa tạo được thumbnail</p>}
              {pack.thumbnails.map((t, i) => (
                <div key={t.path} className="flex flex-col gap-1.5 rounded-lg border border-border p-2">
                  <img src={`${mediaUrl(t.path)}&v=${t.v ?? 0}`} alt="" className="w-full rounded object-cover" />
                  <div className="flex gap-1.5">
                    <Input value={thumbText[i] ?? t.text} onChange={(e) => setThumbText({ ...thumbText, [i]: e.target.value })} className="h-8 text-xs" placeholder="Chữ trên ảnh" />
                    <Button variant="outline" size="icon-sm" title="Vẽ lại với chữ này" disabled={thumbBusy !== null} onClick={() => redraw(i)}>
                      {thumbBusy === i ? <Loader2 className="animate-spin" /> : <RefreshCw />}
                    </Button>
                    <Button variant="ghost" size="icon-sm" title="Mở ảnh" onClick={() => bridge.open(t.path)}><ExternalLink /></Button>
                  </div>
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() => bridge.reveal(pack.dir)}><FolderOpen /> Mở thư mục bài đăng</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
