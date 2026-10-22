import { api, mediaUrl } from "@/lib/api"
import type { FontInfo } from "@/lib/types"

let list: Promise<FontInfo[]> | null = null
const requested = new Set<string>()

/**
 * Nạp font đóng gói / font người dùng thêm vào cho trình duyệt (font Windows thì trình duyệt có sẵn),
 * để khung xem trước phụ đề hiện đúng font như lúc dựng video. Gọi lặp lại an toàn.
 */
export function ensureFont(family?: string, onLoaded?: () => void) {
  const key = (family || "").trim().toLowerCase()
  if (!key || requested.has(key)) return
  requested.add(key)
  ;(list ??= api.fonts().catch(() => [])).then((fonts) => {
    const f = fonts.find((x) => x.family.toLowerCase() === key)
    if (!f || f.source === "system" || f.source === "user") return
    const face = new FontFace(f.family, `url("${mediaUrl(f.path)}")`)
    face.load().then((ff) => { document.fonts.add(ff); onLoaded?.() }).catch(() => requested.delete(key))
  })
}
