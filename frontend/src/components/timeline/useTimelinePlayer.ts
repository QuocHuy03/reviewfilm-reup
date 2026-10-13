import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { mediaUrl } from "@/lib/api"
import type { Scene } from "@/lib/types"

/** Một cảnh trên timeline video xuất ra. */
export type Clip = {
  index: number      // vị trí trong mảng scenes
  start: number      // giây trên timeline xuất ra
  dur: number        // = thời lượng lời đọc (cảnh trong video xuất dài đúng bằng lời)
  scene: Scene
}

export type TrackKey = "video" | "voice" | "music"

const MIN_CLIP = 0.3

/** Bố cục giống video xuất ra: các cảnh không bị bỏ nối tiếp nhau, mỗi cảnh dài bằng lời đọc. */
export function layoutClips(scenes: Scene[]): { clips: Clip[]; total: number } {
  const clips: Clip[] = []
  let t = 0
  scenes.forEach((scene, index) => {
    if (scene.excluded) return
    const dur = Math.max(MIN_CLIP, scene.tts_duration || scene.clip_end - scene.clip_start || MIN_CLIP)
    clips.push({ index, start: t, dur, scene })
    t += dur
  })
  return { clips, total: t }
}

export const clipAt = (clips: Clip[], t: number) => clips.find((c) => t >= c.start && t < c.start + c.dur) ?? null

export type EditMode = "review" | "reup"

/**
 * Tốc độ hình gốc trong cảnh — giống hệt video_editor:
 *   Review: chiếu hình gốc từ clip_start, tốc độ thường, dài đúng bằng lời (không kéo giãn).
 *   Reup:   kéo giãn đoạn clip_start → clip_end cho vừa lời (giới hạn 0.4 … 2.5×).
 */
export const sourceRate = (c: Clip, mode: EditMode) =>
  mode === "review" ? 1 : Math.min(2.5, Math.max(0.4, (c.scene.clip_end - c.scene.clip_start) / c.dur))

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
  const { clips, total } = useMemo(() => layoutClips(scenes), [layoutKey])
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState<Record<TrackKey, boolean>>({ video: false, voice: false, music: false })
  const [videoDuration, setVideoDuration] = useState(Infinity)   // độ dài video gốc — giới hạn khi nới đoạn hình

  const voice = useRef<HTMLAudioElement | null>(null)
  const bgm = useRef<HTMLAudioElement | null>(null)
  const video = useRef<HTMLVideoElement | null>(null)
  const current = useRef<Clip | null>(null)
  const silentFrom = useRef(0)             // cảnh không có file giọng: chạy theo đồng hồ
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
    const a = voice.current!
    const url = c.scene.tts_path ? mediaUrl(c.scene.tts_path) : ""
    if (url) {
      if (!a.src.endsWith(encodeURIComponent(c.scene.tts_path!))) a.src = url
      a.currentTime = offset
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
      const offset = c.scene.tts_path ? voice.current!.currentTime : (performance.now() - silentFrom.current) / 1000
      if (offset >= c.dur - 0.02 || (c.scene.tts_path && voice.current!.ended)) {
        const next = clipsRef.current.find((x) => x.start > c.start)
        if (!next) { setTime(total); stopAll(); return }
        startClip(next, 0)
        setTime(next.start)
      } else {
        setTime(c.start + offset)
      }
    }
    raf.current = requestAnimationFrame(tick)
  }, [startClip, stopAll, total])

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

  /** Video monitor đăng ký vào đây; hiện đúng khung ở đầu phát hiện tại. */
  const attachVideo = useCallback((el: HTMLVideoElement | null) => {
    video.current = el
    if (!el) return
    el.volume = Math.min(1, originalVolume / 100)
    el.muted = muted.video
    const c = clipAt(clipsRef.current, time) ?? clipsRef.current[0]
    el.addEventListener("loadedmetadata", () => {
      if (Number.isFinite(el.duration)) setVideoDuration(el.duration)
      if (c) syncVideo(c, Math.max(0, time - c.start), false)
    }, { once: true })
  }, [muted.video, originalVolume, syncVideo, time])

  // Danh sách cảnh đổi (bỏ cảnh / tạo lại giọng) → dừng để bố cục mới có hiệu lực, giữ đầu phát trong giới hạn
  useEffect(() => { stopAll(); setTime((t) => Math.min(t, total)) }, [layoutKey, stopAll, total])

  return {
    clips, total, time, playing, muted, videoDuration,
    play, pause, toggle, seek, peek, attachVideo,
    toggleMute: (k: TrackKey) => setMuted((m) => ({ ...m, [k]: !m[k] })),
    currentClip: clipAt(clips, time),
  }
}
