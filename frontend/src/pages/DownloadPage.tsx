import {
  AlertTriangle, Captions, ChevronDown, Layers, Subtitles, CheckCircle2, Download, ExternalLink, FolderOpen, ImageDown, Languages, Link2, Loader2, RotateCw,
  Search, Wand2, X, XCircle,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Section, Segmented } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { confirmAction } from "@/components/ConfirmHost"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { api, bridge, mediaUrl } from "@/lib/api"
import { basename, fmtClock, fmtRelative } from "@/lib/format"
import type { DownloadItem, JobSummary, ProbeInfo } from "@/lib/types"
import { cn } from "@/lib/utils"
import { openBatchInCreate, openInCreate } from "./CreatePage"

type Quality = "best" | "1080" | "720" | "audio"
const QUALITIES: { value: Quality; label: string }[] = [
  { value: "best", label: "Tốt nhất" }, { value: "1080", label: "1080p" }, { value: "720", label: "720p" }, { value: "audio", label: "Chỉ âm thanh" },
]
/** Nền tảng đã test tải thật được, không cần đăng nhập. Thêm nền tảng mới → test xong mới thêm vào đây. */
const PLATFORMS: { group: string; items: string[] }[] = [
  { group: "Trung Quốc", items: ["Douyin", "Bilibili", "Weibo", "AcFun", "Youku", "Tencent Video", "Mango TV", "Huya"] },
  { group: "Quốc tế", items: ["TikTok", "YouTube", "Instagram", "Pinterest", "Dailymotion", "Twitch"] },
  { group: "Phim ngắn · tải cả bộ", items: ["DramaBox", "GoodShort", "ShortMax", "NetShort", "FreeReels", "KissKH", "Hồng Quả", "DramaWave", "RaptDrama", "FlexTV", "StardustTV"] },
  { group: "Khác", items: ["Link video .mp4 trực tiếp"] },
]
type Subs = "" | "zh" | "en" | "ko" | "ja"
const SUBS: { value: Subs; label: string }[] = [
  { value: "", label: "Tắt" }, { value: "zh", label: "Trung" }, { value: "en", label: "Anh" }, { value: "ko", label: "Hàn" }, { value: "ja", label: "Nhật" },
]
const linesOf = (v: string) => Array.from(new Set(v.split(/\r?\n/).map((x) => x.trim()).filter(Boolean)))
type PastedQuality = { url: string; height?: number; bitrate?: number; codec?: string }
/**
 * Dán nguyên kết quả JSON của trang tải Douyin (có "qualities") → chọn bản tốt nhất.
 * Ưu tiên H.264 (xem trước trong app phát được trên mọi máy), rồi độ phân giải, rồi bitrate.
 */
function parsePasted(text: string): { links: string[]; titles: Record<string, string> } {
  const t = text.trim()
  if (t.startsWith("{") && t.includes("qualities")) {
    try {
      const d = JSON.parse(t) as { title?: string; qualities?: PastedQuality[] }
      const qs = (d.qualities ?? []).filter((q) => q.url)
      const h264 = qs.filter((q) => (q.codec ?? "").includes("264"))
      const best = [...(h264.length ? h264 : qs)].sort((a, b) => (b.height ?? 0) - (a.height ?? 0) || (b.bitrate ?? 0) - (a.bitrate ?? 0))[0]
      if (best) return { links: [best.url], titles: { [best.url]: d.title ?? "" } }
    } catch { /* không phải JSON hợp lệ → xử lý như danh sách link */ }
  }
  return { links: linesOf(text), titles: {} }
}

const fmtSize = (b?: number) => (b ? (b > 1 << 30 ? `${(b / (1 << 30)).toFixed(2)} GB` : `${(b / (1 << 20)).toFixed(1)} MB`) : "")

export function DownloadPage() {
  const { go, settings } = useStore()
  // thư mục lưu: chọn ngay ở đây (nhớ lần trước); trống = <Thư mục xuất trong Cài đặt>/Downloads
  const [outDir, setOutDir] = useState(() => { try { return localStorage.getItem("rf.dl.dir") || "" } catch { return "" } })
  const saveDir = (v: string) => { setOutDir(v); try { localStorage.setItem("rf.dl.dir", v) } catch { /* bỏ qua */ } }
  const shownDir = outDir || (settings?.output_dir ? `${settings.output_dir.replace(/[\\/]+$/, "")}\\Downloads` : "Thư mục xuất \\ Downloads")
  const pickDir = async () => { const d = await bridge.pickFolder(); if (d) saveDir(d) }
  /** xem trước poster (phóng to) */
  const [preview, setPreview] = useState<PosterView | null>(null)
  const [query, setQuery] = useState("")
  const [text, setText] = useState("")
  const [quality, setQuality] = useState<Quality>("best")
  /** Tải xong tạo phụ đề bằng CapCut: ngôn ngữ gốc của video (+ bản dịch Việt) */
  const [subs, setSubs] = useState<Subs>("")
  /** lưu poster (ảnh bìa) cùng video — nhớ lựa chọn */
  const [poster, setPoster] = useState(() => { try { return localStorage.getItem("rf.dl.poster") !== "0" } catch { return true } })
  const togglePoster = (v: boolean) => { setPoster(v); try { localStorage.setItem("rf.dl.poster", v ? "1" : "0") } catch { /* bỏ qua */ } }
  const [savingPoster, setSavingPoster] = useState<string | null>(null)
  const quickPoster = async (i: ProbeInfo) => {
    if (!i.thumbnail) return
    setSavingPoster(i.url)
    try {
      const r = await api.savePoster(i.thumbnail, parsed.titles[i.url] || i.title || "poster", outDir)
      toast.success("Đã lưu poster", { description: basename(r.path), action: { label: "Mở thư mục", onClick: () => bridge.reveal(r.path) } })
    } catch (e) { toast.error("Không lưu được poster", { description: (e as Error).message }) }
    finally { setSavingPoster(null) }
  }
  const [infos, setInfos] = useState<ProbeInfo[]>([])
  const [probing, setProbing] = useState(false)
  const [starting, setStarting] = useState(false)
  const [jobs, setJobs] = useState<JobSummary[]>([])
  /** Phim ngắn: link phim → các tập muốn tải ("1-10,15", trống = tất cả) */
  const [epSel, setEpSel] = useState<Record<string, string>>({})
  const parsed = useMemo(() => parsePasted(text), [text])
  const links = parsed.links
  const dramaOf = (link: string) => infos.find((i) => i.episodes && (i.url === link || link.includes(i.url)))
  const countEps = (i: ProbeInfo, spec: string) => {
    const want = new Set<number>()
    for (const part of spec.split(",")) {
      const [a, b] = part.split("-").map((x) => parseInt(x, 10))
      if (Number.isNaN(a)) continue
      for (let k = a; k <= (Number.isNaN(b) ? a : b); k++) want.add(k)
    }
    return (i.episodes ?? []).filter((e) => !e.locked && (!want.size || want.has(e.num))).length
  }

  const loadJobs = () => api.jobs().then((j) => setJobs(j.filter((x) => x.kind === "download"))).catch(() => {})
  useEffect(() => {
    loadJobs()
    const t = setInterval(() => { if (!document.hidden) loadJobs() }, 1500)
    return () => clearInterval(t)
  }, [])

  // Tự xem trước khi dán link (chờ ngừng gõ 0.8s)
  const probeSeq = useRef(0)
  useEffect(() => {
    if (!links.length) { setInfos([]); return }
    const seq = ++probeSeq.current
    const t = setTimeout(async () => {
      setProbing(true)
      try { const r = await api.downloadProbe(links); if (seq === probeSeq.current) setInfos(r) }
      catch (e) { toast.error("Không xem trước được", { description: (e as Error).message }) }
      finally { if (seq === probeSeq.current) setProbing(false) }
    }, 800)
    return () => clearTimeout(t)
  }, [links.join("\n")]) // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    setStarting(true)
    try {
      const urls = links.map((l) => {
        const d = dramaOf(l)
        const sel = d && (epSel[d.url] ?? d.ep ?? "").replace(/\s+/g, "")
        return d ? (sel ? `${d.url}#ep=${sel}` : d.url) : l
      })
      await api.createDownload(urls, quality, outDir, parsed.titles, quality === "audio" ? "" : subs, poster)
      toast.success(links.length > 1 ? `Đang tải ${links.length} link` : "Đang tải video")
      setText(""); setInfos([]); setEpSel({}); loadJobs()
    } catch (e) { toast.error("Không tải được", { description: (e as Error).message }) }
    finally { setStarting(false) }
  }


  const okCount = infos.filter((i) => !i.error).length
  const q = query.trim().toLowerCase()
  const shownJobs = q ? jobs.filter((j) => j.title.toLowerCase().includes(q)
    || (j.result.items ?? []).some((it) => (it.series || "").toLowerCase().includes(q) || basename(it.path || "").toLowerCase().includes(q))) : jobs

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_360px] gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1 pb-6">
        <Section title="Dán link video" icon={<Link2 />} desc="Mỗi dòng 1 link — dán nguyên đoạn chia sẻ Douyin / TikTok cũng được, app tự lấy link"
          action={<Segmented size="sm" value={quality} onChange={setQuality} items={QUALITIES} />}>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} className="font-mono text-xs placeholder:font-sans"
            placeholder={"https://www.douyin.com/video/…\nhttps://www.bilibili.com/video/BV…\nhttps://www.dramabox.com/vi/video/41000107260_… (phim ngắn: tải cả bộ)\n7.43 复制打开抖音，看看… https://v.douyin.com/…"} />
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-2">
              <Captions className="size-3.5" /> Tạo phụ đề (kèm bản dịch Việt):
              <Segmented size="sm" value={subs} onChange={setSubs} items={SUBS} />
            </span>
            <label className="flex cursor-pointer items-center gap-2" title="Phim nhiều tập: poster.jpg trong thư mục phim · Video lẻ: ảnh -poster.jpg cạnh video">
              <ImageDown className="size-3.5" /> Lưu poster <Switch size="sm" checked={poster} onCheckedChange={togglePoster} />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex min-w-0 flex-1 items-center gap-1.5 rounded-md border border-border bg-background/40 py-1 pr-1 pl-2.5 text-[12px]">
              <FolderOpen className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="shrink-0 text-muted-foreground">Lưu vào</span>
              <span className="min-w-0 flex-1 truncate font-medium" title={shownDir}>{shownDir}</span>
              {outDir && <Button size="icon-xs" variant="ghost" title="Về mặc định (Cài đặt)" onClick={() => saveDir("")}><X /></Button>}
              <Button size="xs" variant="ghost" onClick={pickDir}>Đổi</Button>
            </div>
            <Button onClick={start} disabled={!links.length || starting || probing || (infos.length > 0 && okCount === 0)}>
              {starting ? <Loader2 className="animate-spin" /> : <Download />} Tải {links.length > 1 ? `${links.length} video` : "video"}
            </Button>
          </div>
          {(probing || infos.length > 0) && (
            <div className="flex flex-col divide-y divide-border/60 rounded-lg border border-border">
              {probing && !infos.length && <p className="flex items-center gap-2 px-3 py-3 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> Đang đọc thông tin link…</p>}
              {infos.map((i) => {
                return (
                  <div key={i.url} className="flex items-center gap-3 px-3 py-2.5">
                    {i.thumbnail && !i.error
                      ? <button title="Xem poster" className="group relative shrink-0 overflow-hidden rounded"
                          onClick={() => setPreview({ src: api.thumbUrl(i.thumbnail!, true), title: parsed.titles[i.url] || i.title || "", probe: i })}>
                          <img src={api.thumbUrl(i.thumbnail)} alt="" className="h-12 w-20 bg-muted object-cover transition group-hover:scale-105" />
                          <span className="absolute inset-0 flex items-center justify-center bg-black/45 text-white opacity-0 transition group-hover:opacity-100"><Search className="size-4" /></span>
                        </button>
                      : <span className={cn("flex h-12 w-20 shrink-0 items-center justify-center rounded", i.error ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground")}>
                          {i.error ? <XCircle className="size-4" /> : <Search className="size-4" />}</span>}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium">{parsed.titles[i.url] || i.title || i.url}</p>
                      <p className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                        <span className="rounded bg-muted px-1.5 font-medium text-foreground">{i.platform_label}</span>
                        {i.duration ? <span className="tabular">{fmtClock(i.duration)}</span> : null}
                        {i.height ? <span>{i.height}p</span> : null}
                        {i.uploader && <span className="truncate">{i.uploader}</span>}
                        {i.source === "dtk" && <span className="text-success">· 1080p không logo</span>}
                      </p>
                      {i.error && <p className="mt-0.5 text-[11px] text-destructive">{i.error}</p>}
                      {i.episodes && !i.error && (() => {
                        const sel = epSel[i.url] ?? i.ep ?? ""
                        return (
                          <div className="mt-1.5 flex items-center gap-2 text-[11px]">
                            <span className="text-muted-foreground">Tập:</span>
                            <Input value={sel} onChange={(e) => setEpSel((s) => ({ ...s, [i.url]: e.target.value }))}
                              placeholder={`tất cả (1-${i.episodes.length})`} className="h-6 w-40 px-2 font-mono text-[11px] placeholder:font-sans" />
                            <span className="text-muted-foreground">→ tải <b className="text-foreground">{countEps(i, sel)}</b> tập · vd 1-10,15</span>
                          </div>
                        )
                      })()}
                    </div>
                    {i.thumbnail && !i.error && (
                      <Button size="xs" variant="ghost" className="shrink-0" title="Tải poster (ảnh bìa, bản nét nhất) về thư mục Downloads/Poster"
                        disabled={savingPoster === i.url} onClick={() => quickPoster(i)}>
                        {savingPoster === i.url ? <Loader2 className="animate-spin" /> : <ImageDown />} Poster
                      </Button>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </Section>

        <Section title="Đang tải & đã tải" icon={<Download />} desc="Tải xong bấm Review / Reup / Dịch phụ đề — hoặc làm cả bộ"
          action={jobs.length > 0 && (
            <div className="flex items-center gap-1.5">
              <div className="relative">
                <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm phim / video…" className="h-7 w-44 pl-7 text-[12px]" />
              </div>
              {jobs.filter((x) => !["running", "queued"].includes(x.status)).length > 1 && (
                <Button size="sm" variant="ghost" title="Ẩn mọi job đã xong khỏi danh sách — file đã tải vẫn giữ nguyên" onClick={async () => {
                  const fin = jobs.filter((x) => !["running", "queued"].includes(x.status))
                  if (!await confirmAction({ title: `Dọn ${fin.length} job đã xong?`, action: "Dọn", desc: "Chỉ ẩn khỏi danh sách. File đã tải vẫn giữ nguyên." })) return
                  await Promise.allSettled(fin.map((x) => api.deleteJob(x.id)))
                  loadJobs()
                }}>Dọn</Button>
              )}
            </div>
          )}>
          {jobs.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Chưa tải video nào.</p>}
          {jobs.length > 0 && shownJobs.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Không có phim / video nào khớp "{query}".</p>}
          {shownJobs.map((j) => {
            const items = j.result.items ?? []
            const running = ["running", "queued"].includes(j.status)
            const failed = items.filter((x) => x.error && !x.path).length
            return (
              <div key={j.id} className="rounded-lg border border-border">
                <div className="flex items-center gap-3 border-b border-border/60 px-3 py-2">
                  {running ? <Loader2 className="size-4 animate-spin text-primary" /> : j.status === "done" ? <CheckCircle2 className="size-4 text-success" />
                    : <AlertTriangle className="size-4 text-destructive" />}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12.5px] font-medium">{j.title}</p>
                    <p className="text-[11px] text-muted-foreground">{running ? j.stage : j.error || `${items.filter((x) => x.path).length}/${items.length} video · ${fmtRelative(j.created_at)}`}</p>
                  </div>
                  {running && <Button size="sm" variant="ghost" onClick={() => api.cancel(j.id)}>Dừng</Button>}
                  {!running && items.filter((x) => x.path).length >= 2 && (
                    <Button size="sm" variant="outline" title="Đưa cả lô sang Tạo video → Nhiều video (chạy lần lượt, tự động hoàn toàn)"
                      onClick={() => { openBatchInCreate(items.filter((x) => x.path).map((x) => x.path!)); go("create") }}>
                      <Layers /> Làm hàng loạt ({items.filter((x) => x.path).length})
                    </Button>
                  )}
                  {!running && failed > 0 && (
                    <Button size="sm" variant="outline" title="Tải lại đúng các mục lỗi — mục đã tải xong tự bỏ qua" onClick={async () => {
                      try { await api.retryDownload(j.id); toast.success(`Đang tải lại ${failed} mục lỗi`); loadJobs() }
                      catch (e) { toast.error("Không tải lại được", { description: (e as Error).message }) }
                    }}><RotateCw /> Tải lại {failed} lỗi</Button>
                  )}
                  {!running && j.result.out_dir && <Button size="icon-sm" variant="ghost" title="Mở thư mục tải về" onClick={() => bridge.reveal(j.result.out_dir!)}><FolderOpen /></Button>}
                  {!running && (
                    <Button size="icon-sm" variant="ghost" title="Ẩn khỏi danh sách (file vẫn giữ)" onClick={async () => {
                      try { await api.deleteJob(j.id); loadJobs() } catch (e) { toast.error((e as Error).message) }
                    }}><X /></Button>
                  )}
                </div>
                {running && <Progress value={j.progress} className="h-1 rounded-none" />}
                {groupItems(items).map((g) => g.series
                  ? <SeriesGroup key={g.key} name={g.series} items={g.items} running={running} onView={setPreview} onCreate={(p, m) => { openInCreate(p, m); go("create") }}
                      onBatch={(ps) => { openBatchInCreate(ps); go("create") }} />
                  : <ItemRow key={g.key} it={g.items[0]} running={running} onView={setPreview} onCreate={(p, m) => { openInCreate(p, m); go("create") }} />)}
              </div>
            )
          })}
        </Section>
      </div>

      <PosterDialog view={preview} saving={!!preview?.probe && savingPoster === preview.probe.url}
        onClose={() => setPreview(null)} onSave={(i) => quickPoster(i)} />

      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto pb-6">
        <Section title="Nền tảng hỗ trợ" icon={<CheckCircle2 />} desc="Không cần đăng nhập — dán link là tải">
          <div className="flex flex-col gap-3">
            {PLATFORMS.map((g) => (
              <div key={g.group}>
                <p className="mb-1.5 text-[10.5px] font-semibold tracking-wider text-muted-foreground uppercase">{g.group}</p>
                <div className="flex flex-wrap gap-1.5">
                  {g.items.map((x) => <span key={x} className="rounded-md border border-border bg-background/40 px-2 py-1 text-[12px]">{x}</span>)}
                </div>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  )
}

type Mode = "review" | "reup" | "vietsub"

/** Gom tập phim nhiều tập theo phim; video lẻ mỗi cái 1 dòng — giữ thứ tự xuất hiện. */
function groupItems(items: DownloadItem[]) {
  const out: { key: string; series?: string; items: DownloadItem[] }[] = []
  const at = new Map<string, number>()
  for (const it of items) {
    const k = it.drama && it.series ? `s:${it.drama}` : ""
    if (k && at.has(k)) { out[at.get(k)!].items.push(it); continue }
    if (k) at.set(k, out.length)
    out.push({ key: k || it.url, series: k ? it.series : undefined, items: [it] })
  }
  return out
}

/** Poster đang xem phóng to: ảnh từ link (chưa tải) hoặc file đã lưu trên máy. */
type PosterView = { src: string; title: string; probe?: ProbeInfo; path?: string }

function Poster({ path, className, title, onView, error }: { path?: string; className?: string; title?: string; onView?: (v: PosterView) => void; error?: boolean }) {
  if (!path) return <span className={cn("flex shrink-0 items-center justify-center rounded", error ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground", className)}>
    {error ? <AlertTriangle className="size-3.5" /> : <Download className="size-3.5" />}</span>
  return (
    <button title="Xem poster" className={cn("group relative shrink-0 overflow-hidden rounded bg-muted", className)}
      onClick={() => onView?.({ src: mediaUrl(path), title: title || basename(path), path })}>
      <img src={mediaUrl(path)} alt="" loading="lazy" className="size-full object-cover transition group-hover:scale-105" />
    </button>
  )
}

function PosterDialog({ view, saving, onClose, onSave }: { view: PosterView | null; saving: boolean; onClose: () => void; onSave: (i: ProbeInfo) => void }) {
  const [size, setSize] = useState("")
  const [state, setState] = useState<"loading" | "ok" | "error">("loading")
  useEffect(() => { setState("loading"); setSize("") }, [view?.src])
  return (
    <Dialog open={!!view} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="w-auto max-w-[min(92vw,720px)] gap-3 p-3">
        <DialogTitle className="truncate pr-8 text-[13px]">{view?.title || "Poster"}</DialogTitle>
        {view && (
          <div className="relative mx-auto flex min-h-72 min-w-56 items-center justify-center rounded-md bg-muted">
            {state === "loading" && <Loader2 className="absolute size-6 animate-spin text-muted-foreground" />}
            {state === "error" && <p className="absolute px-4 text-center text-xs text-muted-foreground">Không tải được ảnh (link hết hạn hoặc bị chặn)</p>}
            <img key={view.src} src={view.src} alt=""
              onLoad={(e) => { setState("ok"); setSize(`${e.currentTarget.naturalWidth}×${e.currentTarget.naturalHeight}`) }} onError={() => setState("error")}
              className={cn("max-h-[70vh] rounded-md object-contain transition-opacity", state === "ok" ? "opacity-100" : "opacity-0")} />
          </div>
        )}
        <div className="flex items-center gap-2">
          <span className="tabular text-[11px] text-muted-foreground">{size}</span>
          <div className="ml-auto flex gap-1.5">
            {view?.path && <Button size="sm" variant="outline" onClick={() => bridge.reveal(view.path!)}><FolderOpen /> Mở thư mục</Button>}
            {view?.probe && (
              <Button size="sm" disabled={saving} onClick={() => onSave(view.probe!)}>
                {saving ? <Loader2 className="animate-spin" /> : <ImageDown />} Lưu poster
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function CreateButtons({ path, onCreate }: { path: string; onCreate: (p: string, m: Mode) => void }) {
  return <>
    <Button size="xs" variant="outline" title="Tạo review phim" onClick={() => onCreate(path, "review")}><Wand2 /> Review</Button>
    <Button size="xs" variant="outline" title="Dịch & Reup (lồng tiếng thuyết minh)" onClick={() => onCreate(path, "reup")}><Languages /> Reup</Button>
    <Button size="xs" variant="outline" title="Dịch phụ đề (xoá phụ đề cũ, ghép phụ đề Việt, lồng tiếng)" onClick={() => onCreate(path, "vietsub")}><Subtitles /> Dịch phụ đề</Button>
  </>
}

/** 1 video lẻ: poster · tên file · nền tảng · dung lượng · thao tác. */
function ItemRow({ it, running, onCreate, label, onView }: {
  it: DownloadItem; running: boolean; onCreate: (p: string, m: Mode) => void; label?: string; onView?: (v: PosterView) => void
}) {
  return (
    <div className="flex items-center gap-2.5 px-3 py-2 text-[12px]">
      {label ? <span className="w-14 shrink-0 text-muted-foreground tabular">{label}</span> : <Poster path={it.poster} className="h-9 w-14" title={basename(it.path || it.url)} onView={onView} error={!!it.error && !it.path} />}
      {it.path ? <>
        <div className="min-w-0 flex-1">
          <p className="truncate" title={it.path}>{basename(it.path)}</p>
          {!label && <p className="truncate text-[10.5px] text-muted-foreground">{it.platform}</p>}
        </div>
        {!!it.subs?.length && <span className="shrink-0 rounded bg-muted px-1 text-[10px] font-semibold text-muted-foreground" title={it.subs.map(basename).join(", ")}>CC {it.subs.length}</span>}
        <span className="tabular shrink-0 text-[11px] text-muted-foreground">{fmtSize(it.size)}</span>
        <Button size="xs" variant="ghost" title="Mở video" onClick={() => bridge.open(it.path!)}><ExternalLink /></Button>
        {!label && it.folder && <Button size="xs" variant="ghost" title="Mở thư mục" onClick={() => bridge.reveal(it.path!)}><FolderOpen /></Button>}
        <CreateButtons path={it.path} onCreate={onCreate} />
      </> : <span className={cn("min-w-0 flex-1 truncate", it.error ? "text-destructive" : "text-muted-foreground")} title={it.error || it.url}>
        {it.error || (running ? "Đang chờ / đang tải…" : it.url)}</span>}
    </div>
  )
}

/** Phim nhiều tập: 1 khối gọn (poster · tên phim · số tập · dung lượng), bấm để xem từng tập. */
function SeriesGroup({ name, items, running, onCreate, onBatch, onView }: {
  name: string; items: DownloadItem[]; running: boolean; onCreate: (p: string, m: Mode) => void; onBatch: (paths: string[]) => void; onView?: (v: PosterView) => void
}) {
  const [open, setOpen] = useState(false)
  const done = items.filter((x) => x.path)
  const failed = items.filter((x) => x.error).length
  const size = done.reduce((n, x) => n + (x.size ?? 0), 0)
  const first = items[0]
  const folder = first.folder
  return (
    <div className="border-b border-border/60 last:border-b-0">
      <div className="flex items-center gap-3 px-3 py-2.5">
        <Poster path={first.poster} className="h-14 w-10" title={name} onView={onView} />
        <button className="min-w-0 flex-1 text-left" onClick={() => setOpen(!open)}>
          <p className="flex items-center gap-1.5 truncate text-[13px] font-medium">
            {name} <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition", open && "rotate-180")} />
          </p>
          <p className="text-[11px] text-muted-foreground">
            {first.platform.split(" · ")[0]} · <b className="text-foreground">{done.length}/{items.length}</b> tập
            {failed > 0 && <span className="text-destructive"> · {failed} lỗi</span>}
            {size > 0 && ` · ${fmtSize(size)}`}
          </p>
        </button>
        {done.length >= 2 && (
          <Button size="xs" variant="outline" title="Đưa cả bộ sang Tạo video → Nhiều video (chạy lần lượt)" onClick={() => onBatch(done.map((x) => x.path!))}>
            <Layers /> Làm cả bộ ({done.length})
          </Button>
        )}
        {folder && <Button size="xs" variant="ghost" title="Mở thư mục phim" onClick={() => bridge.reveal(done[0]?.path ?? folder)}><FolderOpen /></Button>}
      </div>
      {open && (
        <div className="max-h-72 overflow-y-auto border-t border-border/40 bg-muted/20">
          {items.map((it) => <ItemRow key={it.url} it={it} running={running} onCreate={onCreate} label={`Tập ${it.ep ?? ""}`} />)}
        </div>
      )}
    </div>
  )
}
