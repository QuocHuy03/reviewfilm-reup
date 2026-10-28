import { Film, Play } from "lucide-react"
import { useEffect, useRef, useState, type ReactNode } from "react"
import { cn } from "@/lib/utils"

/** Thời lượng kiểu trình dựng video: 00:05.08 · 12:31.47 · 1:32:10 (≥ 1 giờ bỏ phần trăm giây). */
export function fmtVideoTime(sec?: number | null) {
  if (sec == null || !isFinite(sec) || sec <= 0) return ""
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(Math.floor(s)).padStart(2, "0")}`
  const cs = Math.floor((s - Math.floor(s)) * 100)
  return `${String(m).padStart(2, "0")}:${String(Math.floor(s)).padStart(2, "0")}.${String(cs).padStart(2, "0")}`
}

/** Chỉ bật khi khung lọt vào màn hình — danh sách dài không nạp cả trăm video cùng lúc. */
function useInView<T extends Element>() {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || seen) return
    if (typeof IntersectionObserver === "undefined") { setSeen(true); return }
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { setSeen(true); io.disconnect() } }, { rootMargin: "200px" })
    io.observe(el)
    return () => io.disconnect()
  }, [seen])
  return [ref, seen] as const
}

/**
 * Ảnh bìa video kiểu thư viện dựng phim: bo góc, viền mờ, thời lượng ở góc dưới phải; rê chuột → ảnh phóng nhẹ, nổi lên, hiện nút Play.
 *  - image: ảnh bìa (poster / thumbnail). Không có → lấy 1 khung hình trong `video`.
 *  - video: link file video trên máy (mediaUrl) — đọc thời lượng khi chưa có `duration` + làm ảnh dự phòng.
 */
export function VideoThumb({ image, video, duration, className, onClick, title, icon, error, badge }: {
  image?: string; video?: string; duration?: number | null; className?: string; onClick?: () => void; title?: string
  icon?: ReactNode; error?: boolean; badge?: ReactNode
}) {
  const [ref, inView] = useInView<HTMLButtonElement>()
  const [dur, setDur] = useState<number | null>(duration ?? null)
  const [imgOk, setImgOk] = useState(true)
  useEffect(() => setDur(duration ?? null), [duration])
  useEffect(() => setImgOk(true), [image])
  const needVideo = !!video && inView && (dur == null || !image || !imgOk)
  const showImg = !!image && imgOk
  const time = fmtVideoTime(dur)
  const Tag = onClick ? "button" : "div"
  return (
    <Tag ref={ref as never} title={title} onClick={onClick} type={onClick ? "button" : undefined}
      className={cn("group/vt relative shrink-0 overflow-hidden rounded-lg bg-muted ring-1 ring-black/5 transition duration-200 dark:ring-white/10",
        onClick && "cursor-pointer hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/25 hover:ring-primary/50 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none",
        error && "bg-destructive/10 ring-destructive/30", className)}>
      {showImg && (
        <img src={image} alt="" loading="lazy" draggable={false} onError={() => setImgOk(false)}
          className="absolute inset-0 size-full object-cover transition duration-300 group-hover/vt:scale-105" />
      )}
      {needVideo && (
        // chỉ đọc metadata (+ 1 khung ở giây thứ 1 làm ảnh khi không có ảnh bìa) — không tải cả video
        <video src={`${video}#t=1`} muted playsInline preload="metadata" tabIndex={-1}
          onLoadedMetadata={(e) => { if (isFinite(e.currentTarget.duration)) setDur(e.currentTarget.duration) }}
          className={cn("absolute inset-0 size-full object-cover transition duration-300 group-hover/vt:scale-105", showImg && "invisible")} />
      )}
      {!showImg && !needVideo && (
        <span className={cn("absolute inset-0 flex items-center justify-center [&_svg]:size-4", error ? "text-destructive" : "text-muted-foreground")}>
          {icon ?? <Film />}
        </span>
      )}
      {onClick && (showImg || needVideo) && (
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-gradient-to-t from-black/45 via-black/10 to-transparent opacity-0 transition duration-200 group-hover/vt:opacity-100">
          <span className="flex size-7 items-center justify-center rounded-full bg-white/90 text-black shadow-md transition duration-200 group-hover/vt:scale-100 scale-75 [&_svg]:size-3.5 [&_svg]:translate-x-px">
            <Play fill="currentColor" />
          </span>
        </span>
      )}
      {badge && <span className="pointer-events-none absolute top-1 left-1">{badge}</span>}
      {time && (
        <span className="tabular pointer-events-none absolute right-1 bottom-1 rounded-md bg-black/70 px-1.5 py-[1px] font-mono text-[10px] leading-4 font-semibold text-white backdrop-blur-sm">
          {time}
        </span>
      )}
    </Tag>
  )
}
