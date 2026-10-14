import { ArrowRight, AudioLines, Captions, CheckCircle2, Clapperboard, Cpu, Download, HardDrive, History, KeyRound, Languages, XCircle } from "lucide-react"
import { setCreateMode } from "@/pages/CreatePage"
import type { ReactNode } from "react"
import { useEffect, useState } from "react"
import { useStore, type Page } from "@/app/store"
import { KIND_LABEL, StatusBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { fmtRelative } from "@/lib/format"
import type { JobSummary } from "@/lib/types"
import { cn } from "@/lib/utils"

type Action = { page: Page; title: string; desc: string; icon: ReactNode; mode?: "review" | "reup" }
const ACTIONS: Action[] = [
  { page: "download", title: "Tải video", desc: "Douyin, TikTok, Bilibili, Kuaishou, YouTube… tải về rồi làm video luôn.", icon: <Download /> },
  { page: "create", mode: "review", title: "Tạo review phim", desc: "AI xem phim, viết kịch bản, lồng tiếng, dựng video và viết bài đăng.", icon: <Clapperboard /> },
  { page: "create", mode: "reup", title: "Dịch & Reup", desc: "Nhận dạng lời thoại, dịch sang tiếng Việt, lồng tiếng thuyết minh.", icon: <Languages /> },
  { page: "subtitles", title: "Phụ đề", desc: "Tách SRT bằng Whisper, sửa phụ đề, ghép phụ đề vào video.", icon: <Captions /> },
  { page: "voices", title: "Giọng đọc", desc: "", icon: <AudioLines /> },
]

export function HomePage() {
  const { go, system, openJob, voices } = useStore()
  const ready = voices.filter((v) => v.available).length
  const [jobs, setJobs] = useState<JobSummary[]>([])
  useEffect(() => { api.jobs().then(setJobs).catch(() => {}) }, [])
  const aiAccounts = [system?.web_ai?.chatgpt && "ChatGPT", system?.web_ai?.gemini && "Gemini"].filter(Boolean).join(" + ")
  const done = jobs.filter((j) => j.status === "done").length

  return (
    <div className="flex flex-col gap-6 pb-8">
      <div className="relative overflow-hidden rounded-2xl border border-border bg-card px-7 py-6">
        <div className="pointer-events-none absolute -top-24 -right-16 size-72 rounded-full bg-primary/10 blur-3xl" />
        <p className="text-xs font-medium tracking-wide text-primary uppercase">ReviewFilm Studio</p>
        <h2 className="mt-1.5 text-2xl font-semibold tracking-tight">Biến phim dài thành video review trong vài cú nhấp</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Tải video từ Douyin/TikTok/Bilibili… → AI hiểu nội dung và viết lời thuyết minh → lồng tiếng → dựng video kèm phụ đề → tự kiểm tra lỗi và viết sẵn bài đăng cho từng nền tảng.</p>
        <div className="mt-5 flex gap-2">
          <Button onClick={() => go("create")}><Clapperboard /> Tạo video mới</Button>
          {aiAccounts ? (
            <Button variant="outline" onClick={() => go("jobs")}><History /> Lịch sử job</Button>
          ) : (
            <Button variant="outline" onClick={() => go("settings")}><KeyRound /> Đăng nhập tài khoản AI</Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-5 gap-3">
        {ACTIONS.map((a) => (
          <button key={a.title} onClick={() => { if (a.mode) setCreateMode(a.mode); go(a.page) }}
            className="group relative overflow-hidden rounded-xl border border-border bg-card p-4 text-left transition hover:border-primary/50 hover:bg-accent/40">
            <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary [&_svg]:size-4">{a.icon}</span>
            <p className="mt-3 text-sm font-semibold">{a.title}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {a.page === "voices" ? `${voices.length} giọng tiếng Việt · ${ready} dùng được ngay — CapCut, Edge, FPT.AI, VieNeu.` : a.desc}
            </p>
            <ArrowRight className="absolute top-4 right-4 size-4 text-muted-foreground opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
          </button>
        ))}
      </div>

      <div className="grid grid-cols-[1fr_340px] gap-4">
        <div className="rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <p className="text-[13px] font-semibold">Job gần đây</p>
            <Button variant="ghost" size="sm" onClick={() => go("jobs")}>Xem tất cả <ArrowRight /></Button>
          </div>
          {jobs.length === 0 && <p className="px-4 py-10 text-center text-xs text-muted-foreground">Chưa có job nào.</p>}
          {jobs.slice(0, 7).map((j) => (
            <button key={j.id} onClick={() => openJob(j.id)} className="flex w-full items-center gap-3 border-b border-border/60 px-4 py-2.5 text-left last:border-0 hover:bg-muted/40">
              <span className="w-24 shrink-0 text-[11px] text-muted-foreground">{KIND_LABEL[j.kind]}</span>
              <span className="min-w-0 flex-1 truncate text-[13px]">{j.title.split(" · ").slice(1).join(" · ") || j.title}</span>
              <span className="text-[11px] text-muted-foreground">{fmtRelative(j.created_at)}</span>
              <StatusBadge status={j.status} />
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
          <p className="text-[13px] font-semibold">Hệ thống</p>
          <Stat icon={<CheckCircle2 />} label="Video hoàn thành" value={String(done)} />
          <Stat icon={<Cpu />} label="GPU" value={system?.gpu || "Không có (dùng CPU)"} />
          <Stat icon={<HardDrive />} label="Ổ đĩa xuất còn trống" value={system ? `${system.free_gb} GB` : "—"} warn={!!system && system.free_gb < 3} />
          <Stat icon={<KeyRound />} label="Tài khoản AI" value={aiAccounts || "Chưa đăng nhập"} warn={!aiAccounts} />
          <Stat icon={system?.ffmpeg ? <CheckCircle2 /> : <XCircle />} label="ffmpeg / ffprobe" value={system?.ffmpeg && system.ffprobe ? "Sẵn sàng" : "Thiếu"} warn={!system?.ffmpeg} />
        </div>
      </div>
    </div>
  )
}

function Stat({ icon, label, value, warn }: { icon: ReactNode; label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className={cn("flex size-7 items-center justify-center rounded-md bg-muted [&_svg]:size-3.5", warn ? "text-warning" : "text-muted-foreground")}>{icon}</span>
      <span className="flex-1 text-muted-foreground">{label}</span>
      <span className={cn("max-w-40 truncate font-medium", warn && "text-warning")}>{value}</span>
    </div>
  )
}
