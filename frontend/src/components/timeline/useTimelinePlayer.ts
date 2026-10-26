import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { mediaUrl } from "@/lib/api"
import type { Scene } from "@/lib/types"

/** Một cảnh trên timeline video xuất ra. */
export type Clip = {
  index: number      // vị trí trong mảng scenes
  start: number      // giây trên timeline xuất ra
  dur: number        // độ dài cảnh trong video xuất (Review: = lời đọc; Reup: xem reupFit)
  scene: Scene
  pts?: number       // Reup: hình chậm lại bao nhiêu lần (1 = tốc độ thật)
  voiceRate?: number // Reup: giọng đọc nhanh bao nhiêu lần (1 = tốc độ gốc)
}

export type TrackKey = "video" | "voice" | "music"

const MIN_CLIP = 0.3

/** Reup — GIỐNG HỆT backend (video_editor.build_review_video): hình chạy tốc độ thật; lời dài hơn câu gốc thì mượn khoảng
 *  lặng tới câu sau → giọng nhanh tối đa 1.35× → hình chậm tối đa 1.25× → giữ khung cuối. Không bao giờ tua nhanh hình. */
export const REUP_MAX_VOICE = 1.35
export const REUP_MAX_SLOW = 1.25
export function reupFit(scenes: Scene[]): Map<number, { out: number; pts: number; voiceRate: number }> {
  const order = scenes.map((s, i) => ({ s, i })).filter((x) => !x.s.excluded).sort((a, b) => a.s.clip_start - b.s.clip_start)
  const fit = new Map<number, { out: number; pts: number; voiceRate: number }>()
  order.forEach(({ s, i }, k) => {
    const src = Math.max(0.05, s.clip_end - s.clip_start)
    const tts = s.tts_duration && s.tts_duration > 0.05 ? s.tts_duration : src
    const next = order[k + 1]?.s.clip_start ?? s.clip_start + Math.max(src, tts)
    const room = Math.max(src, next - s.clip_start)
    if (tts <= src) fit.set(i, { out: src, pts: 1, voiceRate: 1 })
    else if (tts <= room) fit.set(i, { out: tts, pts: 1, voiceRate: 1 })
    else {
      const voiceRate = Math.min(REUP_MAX_VOICE, tts / room)
      const voice = tts / voiceRate
      if (voice <= room + 0.01) fit.set(i, { out: voice, pts: 1, voiceRate })
      else {
        const pts = Math.min(REUP_MAX_SLOW, voice / room)
        fit.set(i, { out: Math.max(room * pts, voice), pts, voiceRate })
      }
    }
  })
  return fit
}

/** Bố cục giống video xuất ra: các cảnh không bị bỏ nối tiếp nhau. Review: mỗi cảnh dài bằng lời đọc.
 *  Reup: dài theo reupFit (đoạn lặng giữa các câu — tiếng gốc — không hiện trên timeline sửa lời). */
export function layoutClips(scenes: Scene[], mode: EditMode = "review"): { clips: Clip[]; total: number } {
  const clips: Clip[] = []
  const fit = mode === "reup" ? reupFit(scenes) : null
  let t = 0
  scenes.forEach((scene, index) => {
    if (scene.excluded) return
    const f = fit?.get(index)
    const dur = Math.max(MIN_CLIP, f ? f.out : scene.tts_duration || scene.clip_end - scene.clip_start || MIN_CLIP)
    clips.push({ index, start: t, dur, scene, pts: f?.pts, voiceRate: f?.voiceRate })
    t += dur
  })
  return { clips, total: t }
}

export const clipAt = (clips: Clip[], t: number) => clips.find((c) => t >= c.start && t < c.start + c.dur) ?? null


/**
 * Tốc độ hình gốc trong cảnh — giống hệt video_editor:
 *   Review: chiếu hình gốc từ clip_start, tốc độ thường, dài đúng bằng lời (không kéo giãn).
 *   Reup:   tốc độ thật; chỉ chậm lại (≤ 1.25×) khi lời quá dài so với khoảng trống tới câu sau. Không tua nhanh.
 */
export const sourceRate = (c: Clip, mode: EditMode) => (mode === "review" ? 1 : 1 / (c.pts ?? 1))
export type EditMode = "review" | "reup"

type Options = { scenes: Scene[]; bgmPath: string; bgmVolume: number; originalVolume: number; mode?: EditMode }

/**
 * Phát lại timeline: nối các file lời đọc theo thứ tự, video gốc chạy đồng bộ (đúng đoạn, đúng tốc độ),
 * nhạc nền chạy song song. Đầu phát cập nhật theo requestAnimationFrame.
 */
export function useTimelinePlayer({ scenes, bgmPath, bgmVolume, originalVolume, mode = "review" }: Options) {
  // Chỉ dựng lại bố cục khi thứ ảnh hưởng thời gian đổi (bỏ cảnh, tạo lại giọng) — gõ sửa lời không làm dừng phát.
  // UI lấy chữ mới nhất qua scenes[clip.index].
  const layoutKey = scenes.map((s) => `${s.excluded ? 1 : 0}|${s.tts_path ?? ""}|${s.tts_duration ?? 0}|${s.clip_start}|${s.clip_end}`).join(";")
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const { clips, total } = useMemo(() => layoutClips(scenes, mode), [layoutKey, mode])
  const timeRef = useRef(0)              // thời gian phát mới nhất cho callback ổn định (attachVideo)
  const [time, setTimeState] = useState(0)
  const setTime = useCallback((v: number | ((t: number) => number)) => {
    setTimeState((prev) => { const next = typeof v === "function" ? v(prev) : v; timeRef.current = next; return next })
  }, [])
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState<Record<TrackKey, boolean>>({ video: false, voice: false, music: false })
  const mutedRef = useRef(muted)
  mutedRef.current = muted
  const originalVolumeRef = useRef(originalVolume)
  originalVolumeRef.current = originalVolume
  const [videoDuration, setVideoDuration] = useState(Infinity)   // độ dài video gốc — giới hạn khi nới đoạn hình

  const voice = useRef<HTMLAudioElement | null>(null)
  const bgm = useRef<HTMLAudioElement | null>(null)
  const video = useRef<HTMLVideoElement | null>(null)
  const current = useRef<Clip | null>(null)
  const silentFrom = useRef(0)             // cảnh không có file giọng: chạy theo đồng hồ
  const endedAt = useRef<number | null>(null)
  const lastSync = useRef(0)   // lúc giọng của cảnh phát xong (cảnh còn tiếp → đếm theo đồng hồ)
  const raf = useRef(0)
  const playingRef = useRef(false)
  const clipsRef = useRef(clips)
  clipsRef.current = clips

  useEffect(() => {
    voice.current = new Audio()
    bgm.current = new Audio()
    bgm.current.loop = true
    return () => {
      for (const a of [voice.current, bgm.current]) { a?.pause(); if (a) a.src = "" }
      cancelAnimationFrame(raf.current)
    }
  }, [])

  // Âm lượng / tắt tiếng theo track
  useEffect(() => { if (voice.current) voice.current.muted = muted.voice }, [muted.voice])
  useEffect(() => {
    if (video.current) { video.current.volume = Math.min(1, originalVolume / 100); video.current.muted = muted.video }
  }, [muted.video, originalVolume])
  useEffect(() => {
    if (bgm.current) { bgm.current.volume = Math.min(1, bgmVolume / 100); bgm.current.muted = muted.music }
  }, [muted.music, bgmVolume])
  useEffect(() => {
    if (!bgm.current) return
    bgm.current.src = bgmPath ? mediaUrl(bgmPath) : ""
  }, [bgmPath])

  /** Đưa hình gốc tới đúng khung của thời điểm t trong clip. */
  const syncVideo = useCallback((c: Clip, offset: number, play: boolean) => {
    const v = video.current
    if (!v) return
    const rate = sourceRate(c, mode)
    const target = c.scene.clip_start + offset * rate
    if (Math.abs(v.currentTime - target) > 0.25) v.currentTime = target
    v.playbackRate = rate
    if (play) v.play().catch(() => {})
    else v.pause()
  }, [mode])

  const stopAll = useCallback(() => {
    playingRef.current = false
    setPlaying(false)
    cancelAnimationFrame(raf.current)
    voice.current?.pause()
    bgm.current?.pause()
    video.current?.pause()
  }, [])

  const startClip = useCallback((c: Clip, offset: number) => {
    current.current = c
    endedAt.current = null
    const a = voice.current!
    const url = c.scene.tts_path ? mediaUrl(c.scene.tts_path) : ""
    if (url) {
      if (!a.src.endsWith(encodeURIComponent(c.scene.tts_path!))) a.src = url
      a.playbackRate = c.voiceRate ?? 1             // Reup: giọng nhanh nhẹ như video xuất (giữ cao độ)
      a.currentTime = offset * (c.voiceRate ?? 1)
      a.play().catch(() => {})
    } else {
      a.pause()
      silentFrom.current = performance.now() - offset * 1000
    }
    syncVideo(c, offset, true)
  }, [syncVideo])

  const tick = useCallback(() => {
    if (!playingRef.current) return
    const c = current.current
    if (c) {
      // vị trí trong cảnh: theo giọng đang phát; giọng hết mà cảnh còn (Reup: lời ngắn hơn câu gốc → hình chạy tiếp, lặng)
      // thì đếm tiếp theo đồng hồ — cảnh dài đúng như video xuất
      let offset: number
      const a = voice.current!
      if (c.scene.tts_path) {
        if (a.ended || a.error) {
          if (endedAt.current === null) endedAt.current = performance.now()
          offset = (Number.isFinite(a.duration) ? a.duration : 0) / (c.voiceRate ?? 1) + (performance.now() - endedAt.current) / 1000
        } else offset = a.currentTime / (c.voiceRate ?? 1)
      } else offset = (performance.now() - silentFrom.current) / 1000
      if (offset >= c.dur - 0.02) {
        const next = clipsRef.current.find((x) => x.start > c.start)
        if (!next) { setTime(total); stopAll(); return }
        startClip(next, 0)
        setTime(next.start)
      } else {
        setTime(c.start + offset)
        // giữa cảnh: chỉnh lại hình mỗi ~0.5s nếu lệch > 0.25s so với giọng (trước chỉ đồng bộ lúc bắt đầu cảnh → lệch dần)
        const now = performance.now()
        if (now - lastSync.current > 500) { lastSync.current = now; syncVideo(c, offset, true) }
      }
    }
    raf.current = requestAnimationFrame(tick)
  }, [startClip, stopAll, syncVideo, total])

  const play = useCallback((from?: number) => {
    let t = from ?? time
    if (t >= total - 0.05) t = 0
    const c = clipAt(clipsRef.current, t) ?? clipsRef.current[0]
    if (!c) return
    playingRef.current = true
    setPlaying(true)
    startClip(c, Math.max(0, t - c.start))
    if (bgm.current?.src) {
      const b = bgm.current
      if (Number.isFinite(b.duration) && b.duration > 0) b.currentTime = t % b.duration
      b.play().catch(() => {})
    }
    cancelAnimationFrame(raf.current)
    raf.current = requestAnimationFrame(tick)
  }, [startClip, tick, time, total])

  const pause = useCallback(() => stopAll(), [stopAll])

  /** Dừng phát và hiện đúng khung hình gốc tại giây `sourceT` — xem trước khi kéo mép cắt cảnh. */
  const peek = useCallback((sourceT: number) => {
    stopAll()
    const v = video.current
    if (v) v.currentTime = Math.max(0, Math.min(sourceT, Number.isFinite(v.duration) ? v.duration - 0.05 : sourceT))
  }, [stopAll])
  const toggle = useCallback(() => (playingRef.current ? pause() : play()), [pause, play])

  const seek = useCallback((t: number) => {
    const clamped = Math.max(0, Math.min(total, t))
    setTime(clamped)
    const c = clipAt(clipsRef.current, clamped) ?? clipsRef.current[clipsRef.current.length - 1]
    if (!c) return
    if (playingRef.current) play(clamped)
    else { current.current = c; syncVideo(c, Math.max(0, clamped - c.start), false) }
  }, [play, syncVideo, total])

  /**
   * Video monitor đăng ký vào đây; hiện đúng khung ở đầu phát hiện tại.
   * Ổn định (không phụ thuộc thời gian phát) — nếu đổi theo từng khung hình, React tháo/gắn ref liên tục
   * và mỗi lần lại thêm 1 listener loadedmetadata không bao giờ gỡ (rò bộ nhớ khi phát).
   */
  const attachVideo = useCallback((el: HTMLVideoElement | null) => {
    if (video.current === el) return
    video.current = el
    if (!el) return
    el.volume = Math.min(1, originalVolumeRef.current / 100)
    el.muted = mutedRef.current.video
    const onMeta = () => {
      if (Number.isFinite(el.duration)) setVideoDuration(el.duration)
      const t = timeRef.current
      const c = clipAt(clipsRef.current, t) ?? clipsRef.current[0]
      if (c) syncVideo(c, Math.max(0, t - c.start), false)
    }
    if (el.readyState >= 1) onMeta()
    else el.addEventListener("loadedmetadata", onMeta, { once: true })
  }, [syncVideo])

  // Danh sách cảnh đổi (bỏ cảnh / tạo lại giọng) → dừng để bố cục mới có hiệu lực, giữ đầu phát trong giới hạn
  useEffect(() => { stopAll(); setTime((t) => Math.min(t, total)) }, [layoutKey, stopAll, total])

  return {
    clips, total, time, playing, muted, videoDuration,
    play, pause, toggle, seek, peek, attachVideo,
    toggleMute: (k: TrackKey) => setMuted((m) => ({ ...m, [k]: !m[k] })),
    currentClip: clipAt(clips, time),
  }
}
