import { Film } from "lucide-react"
import { mediaUrl } from "@/lib/api"
import { fmtClock } from "@/lib/format"

/** Màn hình xem trước: hình gốc chạy theo đầu phát (player điều khiển qua attachVideo) + phụ đề đè lên. */
export function Monitor({ videoPath, attachVideo, subtitle, time, total, label }: {
  videoPath?: string
  attachVideo: (el: HTMLVideoElement | null) => void
  subtitle: string
  time: number
  total: number
  label: string
}) {
  return (
    <div className="relative flex min-h-0 items-center justify-center overflow-hidden bg-black">
      {videoPath ? (
        <video ref={attachVideo} src={mediaUrl(videoPath)} preload="auto" playsInline className="max-h-full max-w-full" />
      ) : (
        <div className="flex flex-col items-center gap-2 text-xs text-white/40"><Film className="size-6" /> Không có file video gốc để xem trước</div>
      )}
      {subtitle && (
        <div className="pointer-events-none absolute inset-x-0 bottom-[7%] flex justify-center px-[10%]">
          <span className="line-clamp-2 rounded bg-black/55 px-2 py-0.5 text-center text-[13px] leading-snug font-semibold break-words text-white [text-shadow:0_1px_2px_#000]">{subtitle}</span>
        </div>
      )}
      <span className="tabular absolute top-2 left-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10.5px] text-white/80">{fmtClock(time)} / {fmtClock(total)}</span>
      {label && <span className="absolute top-2 right-2 rounded bg-black/60 px-1.5 py-0.5 text-[10.5px] text-white/80">{label}</span>}
    </div>
  )
}

/**
 * Đoạn phụ đề đang hiện tại `offset` giây trong cảnh dài `dur` giây — chia lời thành các đoạn ≤ maxChars
 * (ưu tiên ngắt ở dấu câu) rồi rải đều theo thời gian, giống cách video_editor ghép phụ đề.
 */
export function subtitleChunk(text: string, offset: number, dur: number, maxChars = 80) {
  const words = (text || "").replace(/\s+/g, " ").trim().split(" ").filter(Boolean)
  if (!words.length) return ""
  const chunks: string[] = []
  let cur = ""
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w
    if (next.length > maxChars && cur) { chunks.push(cur); cur = w } else cur = next
    if (/[.!?…;]$/.test(w) && cur.length > maxChars * 0.45) { chunks.push(cur); cur = "" }
  }
  if (cur) chunks.push(cur)
  const i = Math.min(chunks.length - 1, Math.max(0, Math.floor((offset / Math.max(0.1, dur)) * chunks.length)))
  return chunks[i]
}
