import { useCallback, useEffect, useRef, useState } from "react"

type QueueItem = { url: string; key: string }

/**
 * 1 audio element dùng chung: play(url) bật/tắt, `playing` = url đang phát.
 * playList: phát lần lượt cả danh sách (nghe nhanh nhiều giọng) — `queueKey` = mục đang phát, null khi xong / dừng.
 */
export function useAudio() {
  const ref = useRef<HTMLAudioElement | null>(null)
  const queue = useRef<QueueItem[]>([])
  const [playing, setPlaying] = useState<string | null>(null)
  const [queueKey, setQueueKey] = useState<string | null>(null)

  const next = useCallback(() => {
    const a = ref.current
    const item = queue.current.shift()
    if (!a || !item) { setPlaying(null); setQueueKey(null); return }
    a.src = item.url
    a.currentTime = 0
    setQueueKey(item.key)
    a.play().then(() => setPlaying(item.url)).catch(() => next())   // file lỗi → bỏ qua, phát tiếp
  }, [])

  useEffect(() => {
    const a = new Audio()
    a.onended = () => (queue.current.length ? next() : (setPlaying(null), setQueueKey(null)))
    a.onerror = () => (queue.current.length ? next() : (setPlaying(null), setQueueKey(null)))
    ref.current = a
    return () => { a.pause(); a.src = "" }
  }, [next])

  const play = useCallback((url: string) => {
    const a = ref.current
    if (!a) return
    queue.current = []
    setQueueKey(null)
    if (playing === url) { a.pause(); setPlaying(null); return }
    a.src = url
    a.currentTime = 0
    a.play().then(() => setPlaying(url)).catch(() => setPlaying(null))
  }, [playing])

  const playList = useCallback((items: QueueItem[]) => {
    ref.current?.pause()
    queue.current = [...items]
    next()
  }, [next])

  const stop = useCallback(() => { queue.current = []; ref.current?.pause(); setPlaying(null); setQueueKey(null) }, [])

  return { play, stop, playing, playList, queueKey }
}
