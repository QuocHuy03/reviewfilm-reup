import type { Scene, ScenePart } from "@/lib/types"

/** Một dòng phụ đề hiện trên video: câu `scene`, phần `part` (-1 = cả câu, không có thông tin dòng gốc). */
export type SubCue = { scene: number; part: number; start: number; end: number; text: string; orig?: string }

/** Python round (làm tròn về số chẵn khi đúng .5) — để chia chữ giống hệt backend. */
const pyRound = (x: number) => {
  const f = Math.floor(x)
  const d = x - f
  return d > 0.5 ? f + 1 : d < 0.5 ? f : f % 2 === 0 ? f : f + 1
}

/** Chữ để so 2 câu có cùng lời không (bỏ dấu câu, hoa / thường) — như vietsub._bare. */
const bare = (t: string) => (t || "").replace(/[^\p{L}\p{N}_\s]/gu, " ").toLowerCase().split(/\s+/).filter(Boolean).join(" ")

/** Câu dịch → chia về từng dòng gốc theo tỉ lệ độ dài lời gốc, cắt ở ranh giới từ, ưu tiên sau dấu câu (±2 từ).
 *  Y HỆT backend vietsub._split_by_parts. */
export function splitByParts(text: string, parts: ScenePart[]): string[] {
  const n = parts.length
  const words = (text || "").split(/\s+/).filter(Boolean)
  if (n <= 1 || words.length < 2) return [(text || "").trim(), ...Array(Math.max(0, n - 1)).fill("")]
  const weights = parts.map((p) => Math.max(1, String(p[2] ?? "").length))
  const total = weights.reduce((a, b) => a + b, 0)
  let acc = 0
  const cuts: number[] = []
  for (const w of weights.slice(0, -1)) {
    acc += w
    let k = Math.max(1, Math.min(words.length - 1, pyRound((acc / total) * words.length)))
    const near: number[] = []
    for (let j = Math.max(1, k - 2); j <= Math.min(words.length - 1, k + 2); j++) if (/[,.?!;:…]$/.test(words[j - 1])) near.push(j)
    if (near.length) k = near.reduce((best, j) => (Math.abs(j - k) < Math.abs(best - k) ? j : best), near[0])
    cuts.push(Math.max(cuts.length ? cuts[cuts.length - 1] : 0, k))
  }
  const bounds = [0, ...cuts, words.length]
  return parts.map((_, j) => words.slice(bounds[j], bounds[j + 1]).join(" ").trim())
}

/** Các dòng phụ đề của 1 câu — Y HỆT backend vietsub._part_cues: câu chưa sửa lời → mỗi dòng đúng bản dịch dòng đó;
 *  đã sửa → chia theo tỉ lệ; không có thông tin dòng → 1 dòng theo giờ câu. */
export function sceneCues(s: Scene, index: number): SubCue[] {
  const parts = s.parts && s.parts.length ? s.parts : null
  const texts = partTexts(s)
  if (!parts) return texts[0] ? [{ scene: index, part: -1, start: s.clip_start, end: s.clip_end, text: texts[0], orig: s.orig_text || "" }] : []
  return parts.flatMap((p, k) => (texts[k] ? [{ scene: index, part: k, start: Number(p[0]), end: Number(p[1]), text: texts[k], orig: String(p[2] ?? "") }] : []))
}

/** Chữ hiện ở từng dòng của câu (cùng số phần tử với parts; không có parts → 1 phần tử = cả câu). */
export function partTexts(s: Scene): string[] {
  const text = (s.voiceover || s.subtitle || "").trim()
  const parts = s.parts && s.parts.length ? s.parts : null
  if (!parts) return [text]
  const own = parts.map((p) => String(p[3] ?? "").trim())
  const same = own.every(Boolean) && bare(own.join(" ")) === bare(text)
  return same ? own : splitByParts(text, parts)
}

/** Các dòng của câu kèm đúng chữ đang hiện (để tách / gộp mà chữ không nhảy dòng). */
export function partsWithText(s: Scene): ScenePart[] {
  const texts = partTexts(s)
  return s.parts && s.parts.length
    ? s.parts.map((p, j) => [Number(p[0]), Number(p[1]), String(p[2] ?? ""), texts[j]] as ScenePart)
    : [[s.clip_start, s.clip_end, s.orig_text || "", texts[0]]]
}

/** Chỗ cắt chữ khi tách dòng tại tỉ lệ `ratio` (0-1): ranh giới từ, ưu tiên ngay sau dấu câu (±2 từ). → số từ của nửa đầu. */
export function cutWord(words: string[], ratio: number) {
  let k = Math.max(1, Math.min(words.length - 1, Math.round(ratio * words.length)))
  let best = -1
  for (let j = Math.max(1, k - 2); j <= Math.min(words.length - 1, k + 2); j++)
    if (/[,.?!;:…]$/.test(words[j - 1]) && (best < 0 || Math.abs(j - k) < Math.abs(best - k))) best = j
  if (best > 0) k = best
  return k
}

/** Tốc độ đọc phụ đề (ký tự / giây, không tính dấu cách) — chuẩn phụ đề chuyên nghiệp: ≤ 17 thoải mái, > 20 gấp, > 25 không kịp đọc. */
export const CPS_GOOD = 17
export function readSpeed(text: string, dur: number) {
  const n = text.replace(/\s+/g, "").length
  const cps = n / Math.max(0.05, dur)
  const level = cps > 25 || dur < 0.5 ? "bad" : cps > 20 || dur < 0.7 ? "warn" : "ok"
  return { n, cps, level: level as "ok" | "warn" | "bad", need: Math.max(0.7, n / CPS_GOOD) }
}

export function allCues(scenes: Scene[]): SubCue[] {
  return scenes.flatMap((s, i) => (s.excluded ? [] : sceneCues(s, i))).sort((a, b) => a.start - b.start)
}

/** Giờ gốc của câu (lúc AI đưa ra) — để timeline hiện làn "Gốc", hít vào và Khôi phục. Lưu kèm câu, bỏ đi trước khi gửi backend. */
export type OrigTiming = { cs: number; ce: number; parts: ScenePart[] | null }
export const origOf = (s: Scene): OrigTiming =>
  (s._o as OrigTiming | undefined) ?? { cs: s.clip_start, ce: s.clip_end, parts: s.parts ?? null }
export const withOrig = (scenes: Scene[]) => scenes.map((s) => (s._o ? s : { ...s, _o: origOf(s) }))
export const stripOrig = (scenes: Scene[]) => scenes.map(({ _o, ...s }) => s as Scene) // eslint-disable-line @typescript-eslint/no-unused-vars

/** Câu đã bị kéo / cắt khác giờ gốc chưa. */
export const isRetimed = (s: Scene) => {
  const o = origOf(s)
  const times = (ps: ScenePart[] | null | undefined) => JSON.stringify((ps ?? []).map((p) => [Number(p[0]), Number(p[1])]))
  return typeof s.voice_start === "number" || s.clip_start !== o.cs || s.clip_end !== o.ce || times(s.parts) !== times(o.parts)
}
export const resetTiming = (s: Scene): Scene => {
  const o = origOf(s)
  const { voice_start, voice_end, ...rest } = s // eslint-disable-line @typescript-eslint/no-unused-vars
  return { ...rest, clip_start: o.cs, clip_end: o.ce, parts: o.parts }
}

/** Khung lồng tiếng của câu: chỉnh tay (voice_start / voice_end) hoặc mặc định = giờ câu. */
export const voiceSlot = (s: Scene) => ({
  start: typeof s.voice_start === "number" ? s.voice_start : s.clip_start,
  end: typeof s.voice_end === "number" ? s.voice_end : s.clip_end,
  manual: typeof s.voice_start === "number",
})
