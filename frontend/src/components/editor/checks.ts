import type { Scene } from "@/lib/types"
import { reupFit } from "@/components/timeline/useTimelinePlayer"

export type IssueLevel = "error" | "warn"
export type Issue = { index: number; level: IssueLevel; code: string; message: string }

// Ngưỡng kéo giãn hình của video_editor (_pr kẹp trong 0.4 … 2.5) — vượt ra thì hình và lời lệch nhau.
const MAX_STRETCH = 2.5
const JUNK = /:::|\[\s*Cảnh|\bid\s*=|```|\*\*|[{}<>]|^\s*#/i

// Cùng ngưỡng với QA backend (jobs/qa.py) — preview báo gì thì video xuất ra kiểm tra y như vậy.
const OVERLAP_S = 1.0
const SHORT_RATIO = 0.5
const TEXT_OVERLAP = 0.2
const TEXT_SHARED_MIN = 3

/** Đoạn hình gốc cảnh thật sự chiếu: Review = từ clip_start dài bằng lời; Reup = clip_start → clip_end (tốc độ thật). */
const usedSpan = (s: Scene, mode: "review" | "reup"): [number, number] =>
  mode === "reup" ? [s.clip_start, s.clip_end] : [s.clip_start, s.clip_start + (s.tts_duration || 0)]

const trigrams = (text: string) => {
  const w = (text || "").toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []
  const g = new Set<string>()
  for (let k = 0; k + 3 <= w.length; k++) g.add(w.slice(k, k + 3).join(" "))
  return { g, w }
}

/** Kiểm tra hậu kỳ không cần AI: chạy ngay trên trình duyệt mỗi khi kịch bản đổi (khớp với QA sau khi xuất). */
export function checkScenes(scenes: Scene[], mode: "review" | "reup" = "review"): Issue[] {
  const out: Issue[] = []
  const live = scenes.map((s, i) => ({ s, i })).filter((x) => !x.s.excluded)
  const starts = live.map((x) => x.s.clip_start)
  const grams = live.map((x) => trigrams(x.s.voiceover))
  // cụm có ở hầu hết các cảnh (tên nhân vật…) không tính là lặp
  const df = new Map<string, number>()
  grams.forEach(({ g }) => g.forEach((x) => df.set(x, (df.get(x) ?? 0) + 1)))
  const common = new Set([...df].filter(([, n]) => live.length >= 3 && n >= Math.max(3, live.length * 0.6)).map(([x]) => x))
  const fit = mode === "reup" ? reupFit(scenes) : null
  const norm = (t: string) => (t || "").replace(/\s+/g, " ").trim()

  live.forEach(({ s, i }, k) => {
    const text = (s.voiceover || "").trim()
    const clip = Math.max(0, s.clip_end - s.clip_start)
    const tts = s.tts_duration || 0

    if (!text) out.push({ index: i, level: "error", code: "empty", message: "Cảnh không có lời đọc" })
    if (!s.tts_path) out.push({ index: i, level: "error", code: "no-voice", message: "Chưa có giọng đọc — bấm “Tạo lại giọng”" })
    if (JUNK.test(text)) out.push({ index: i, level: "error", code: "junk", message: "Lời đọc còn ký hiệu / mã / dấu cảnh — sẽ bị đọc thành tiếng" })
    if (tts > 0 && tts < 0.8 && text) out.push({ index: i, level: "warn", code: "tiny", message: "Lời đọc quá ngắn (<0.8s)" })
    if (s.tts_path && typeof s.tts_text === "string" && norm(s.tts_text) !== norm(text))
      out.push({ index: i, level: "error", code: "stale-voice", message: "Đã sửa lời nhưng giọng vẫn đọc câu cũ — bấm “Tạo lại giọng” (xác nhận xuất sẽ tự đọc lại)" })

    // Lời vừa hình
    if (clip > 0.1 && tts > 0.1) {
      if (mode === "reup") {
        // giống video_editor.reup_fit: hình tốc độ thật, lời dài thì mượn khoảng lặng → giọng nhanh → hình chậm
        const f = fit?.get(i)
        if (f && f.pts > 1) out.push({ index: i, level: "warn", code: "long", message: `Lời quá dài so với khoảng tới câu sau — giọng nhanh ${f.voiceRate.toFixed(2)}× và hình chậm ${f.pts.toFixed(2)}×, nên rút gọn lời` })
        else if (f && f.voiceRate > 1.2) out.push({ index: i, level: "warn", code: "long", message: `Lời dài — giọng phải đọc nhanh ${f.voiceRate.toFixed(2)}×, nên rút gọn lời` })
        else if (clip > 3 && tts < clip * 0.35) out.push({ index: i, level: "warn", code: "short", message: `Lời ${tts.toFixed(1)}s / câu gốc ${clip.toFixed(1)}s — lặng ${(clip - tts).toFixed(1)}s` })
      } else {
        const later = starts.filter((x) => x > s.clip_start + 0.05)
        const nxt = later.length ? Math.min(...later) : null
        const own = nxt !== null ? Math.min(clip, nxt - s.clip_start) : clip
        if (nxt !== null && s.clip_start + tts - nxt > OVERLAP_S)
          out.push({ index: i, level: "warn", code: "long", message: `Lời ${tts.toFixed(0)}s dài hơn hình ${(nxt - s.clip_start).toFixed(0)}s — sẽ chiếu lặp ${(s.clip_start + tts - nxt).toFixed(0)}s hình cảnh sau, nên rút gọn lời` })
        else if (own > 4 && tts < own * SHORT_RATIO)
          out.push({ index: i, level: "warn", code: "short", message: `Lời ${tts.toFixed(0)}s / hình ${own.toFixed(0)}s — bỏ phí ${(own - tts).toFixed(0)}s hình, nên thêm lời` })
      }
    }

    // Lặp hình: chiếu lại đoạn hình một cảnh đứng trước đã chiếu (mọi cặp)
    const [a0, a1] = usedSpan(s, mode)
    for (let j = 0; j < k; j++) {
      const [b0, b1] = usedSpan(live[j].s, mode)
      const ov = Math.min(a1, b1) - Math.max(a0, b0)
      if (ov <= OVERLAP_S || (mode === "review" && b0 < a0 - 0.05)) continue
      out.push({ index: i, level: "warn", code: "footage", message: `Chiếu lại ${ov.toFixed(0)}s hình đã dùng ở cảnh #${live[j].i + 1} — kéo mép / dời đoạn hình sang chỗ khác` })
      break
    }

    // Lặp lời
    if (k > 0 && grams[k].w.length >= 6) {
      const gi = new Set([...grams[k].g].filter((x) => !common.has(x)))
      let hit = ""
      for (let j = 0; j < k && !hit; j++) {
        const gj = new Set([...grams[j].g].filter((x) => !common.has(x)))
        const shared = [...gi].filter((x) => gj.has(x))
        if (gi.size && gj.size && (shared.length >= TEXT_SHARED_MIN || shared.length / Math.min(gi.size, gj.size) >= TEXT_OVERLAP))
          hit = `Lặp ý với cảnh #${live[j].i + 1} (vd “${shared[0]}”) — viết lại khác đi`
      }
      if (!hit && grams[k].w.slice(0, 3).join(" ") === grams[k - 1].w.slice(0, 3).join(" "))
        hit = `Mở đầu giống hệt cảnh #${live[k - 1].i + 1} (“${grams[k].w.slice(0, 3).join(" ")}…”)`
      if (hit) out.push({ index: i, level: "warn", code: "repeat", message: hit })
    }
  })
  return out
}

/** Mức nặng nhất của từng cảnh — để đánh dấu trên timeline. */
export function issueLevels(issues: Issue[]): Record<number, IssueLevel> {
  const m: Record<number, IssueLevel> = {}
  for (const it of issues) if (m[it.index] !== "error") m[it.index] = it.level
  return m
}

/**
 * Tự căn đoạn hình cho khớp lời đọc (giới hạn kéo giãn của video_editor là 0.4…2.5×).
 * - Hình dài hơn lời quá nhiều → cắt bớt đuôi, giữ phần đầu cảnh (dài ≈ 1.2× lời).
 * - Lời dài hơn hình quá nhiều → nới đuôi (dài ≈ lời / 1.2), không vượt quá cuối video.
 * Trả về kịch bản mới + danh sách cảnh đã chỉnh.
 */
export function fixDurations(scenes: Scene[], videoDuration = Infinity, mode: "review" | "reup" = "review"): { scenes: Scene[]; changed: number[] } {
  const changed: number[] = []
  // Reup: mốc câu là mốc câu thoại GỐC — không căn hình theo lời (bước dựng tự mượn khoảng lặng / tăng tốc giọng)
  if (mode === "reup") return { scenes, changed }
  const starts = scenes.filter((s) => !s.excluded).map((s) => s.clip_start)
  const out = scenes.map((s, i) => {
    if (s.excluded || !s.tts_duration) return s
    const src = s.clip_end - s.clip_start
    const tts = s.tts_duration
    let end = s.clip_end
    if (src > tts * MAX_STRETCH) end = s.clip_start + tts * 1.2
    else if (tts > src * MAX_STRETCH) {
      // Không nới lấn sang hình của cảnh phía sau — phần thiếu để AI rút lời
      const later = starts.filter((x) => x > s.clip_start + 0.05)
      const cap = later.length ? Math.max(s.clip_end, Math.min(...later)) : Infinity
      end = Math.min(videoDuration, cap, s.clip_start + tts / 1.2)
    }
    end = +end.toFixed(2)
    if (Math.abs(end - s.clip_end) < 0.05 || end <= s.clip_start + 0.2) return s
    changed.push(i)
    return { ...s, clip_end: end }
  })
  return { scenes: out, changed }
}
