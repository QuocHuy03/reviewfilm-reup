import { AlertTriangle, Captions, CheckCircle2, Download, ExternalLink, FolderOpen, Languages, Link2, Loader2, Search, Wand2, XCircle } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { useStore } from "@/app/store"
import { Section, Segmented } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Textarea } from "@/components/ui/textarea"
import { api, bridge } from "@/lib/api"
import { basename, fmtClock, fmtRelative } from "@/lib/format"
import type { JobSummary, ProbeInfo } from "@/lib/types"
import { cn } from "@/lib/utils"
import { openInCreate } from "./CreatePage"

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
  const { go } = useStore()
  const [text, setText] = useState("")
  const [quality, setQuality] = useState<Quality>("best")
  /** Tải xong tạo phụ đề bằng CapCut: ngôn ngữ gốc của video (+ bản dịch Việt) */
  const [subs, setSubs] = useState<Subs>("")
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
      await api.createDownload(urls, quality, "", parsed.titles, quality === "audio" ? "" : subs)
      toast.success(links.length > 1 ? `Đang tải ${links.length} link` : "Đang tải video")
      setText(""); setInfos([]); setEpSel({}); loadJobs()
    } catch (e) { toast.error("Không tải được", { description: (e as Error).message }) }
    finally { setStarting(false) }
  }


  const okCount = infos.filter((i) => !i.error).length

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_360px] gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1 pb-6">
        <Section title="Dán link video" icon={<Link2 />} desc="Mỗi dòng 1 link — dán nguyên đoạn chia sẻ Douyin / TikTok cũng được, app tự lấy link"
          action={<Segmented size="sm" value={quality} onChange={setQuality} items={QUALITIES} />}>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} className="font-mono text-xs placeholder:font-sans"
            placeholder={"https://www.douyin.com/video/…\nhttps://www.bilibili.com/video/BV…\nhttps://www.dramabox.com/vi/video/41000107260_… (phim ngắn: tải cả bộ)\n7.43 复制打开抖音，看看… https://v.douyin.com/…"} />
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <Captions className="size-3.5" /> Tạo phụ đề (CapCut, kèm bản dịch Việt) — tiếng gốc của video:
            <Segmented size="sm" value={subs} onChange={setSubs} items={SUBS} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-muted-foreground">Hỗ trợ: {PLATFORMS.flatMap((g) => g.items).slice(0, -1).join(" · ")}</span>
            <Button className="ml-auto" onClick={start} disabled={!links.length || starting || probing || (infos.length > 0 && okCount === 0)}>
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
                      ? <img src={api.thumbUrl(i.thumbnail)} alt="" className="h-12 w-20 shrink-0 rounded bg-muted object-cover" />
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
                  </div>
                )
              })}
            </div>
          )}
        </Section>

        <Section title="Đang tải & đã tải" icon={<Download />} desc="Tải xong bấm Tạo Review / Dịch & Reup để làm video luôn">
          {jobs.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Chưa tải video nào.</p>}
          {jobs.map((j) => {
            const items = j.result.items ?? []
            const running = ["running", "queued"].includes(j.status)
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
                  {!running && j.result.out_dir && <Button size="icon-sm" variant="ghost" title="Mở thư mục tải về" onClick={() => bridge.reveal(j.result.out_dir!)}><FolderOpen /></Button>}
                </div>
                {running && <Progress value={j.progress} className="h-1 rounded-none" />}
                {items.map((it) => (
                  <div key={it.url} className="flex items-center gap-2.5 px-3 py-2 text-[12px]">
                    <span className="w-24 shrink-0 truncate text-muted-foreground">{it.platform}</span>
                    {it.path ? <>
                      <span className="min-w-0 flex-1 truncate" title={it.path}>{basename(it.path)}</span>
                      {!!it.subs?.length && <span className="shrink-0 rounded bg-muted px-1 text-[10px] font-semibold text-muted-foreground" title={it.subs.map(basename).join(", ")}>CC {it.subs.length}</span>}
                      <span className="tabular shrink-0 text-[11px] text-muted-foreground">{fmtSize(it.size)}</span>
                      <Button size="xs" variant="ghost" title="Mở video" onClick={() => bridge.open(it.path!)}><ExternalLink /></Button>
                      <Button size="xs" variant="outline" onClick={() => { openInCreate(it.path!, "review"); go("create") }}><Wand2 /> Tạo Review</Button>
                      <Button size="xs" variant="outline" onClick={() => { openInCreate(it.path!, "reup"); go("create") }}><Languages /> Dịch & Reup</Button>
                    </> : <span className={cn("min-w-0 flex-1 truncate", it.error ? "text-destructive" : "text-muted-foreground")} title={it.error || it.url}>
                      {it.error || (running ? "Đang chờ / đang tải…" : it.url)}</span>}
                  </div>
                ))}
              </div>
            )
          })}
        </Section>
      </div>

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
