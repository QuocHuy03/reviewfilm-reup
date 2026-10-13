export const fmtClock = (sec: number) => {
  const s = Math.max(0, sec || 0)
  const m = Math.floor(s / 60)
  return `${String(m).padStart(2, "0")}:${(s % 60).toFixed(1).padStart(4, "0")}`
}

export const fmtDuration = (sec: number) => {
  const s = Math.round(sec || 0)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}p ${s % 60}s`
  return `${Math.floor(m / 60)}h ${m % 60}p`
}

export const fmtRelative = (iso: string) => {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return "vừa xong"
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`
  if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`
  return new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })
}

export const basename = (p: string) => p.split(/[\\/]/).pop() ?? p
