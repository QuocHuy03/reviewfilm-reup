import { useCallback, useEffect, useRef, useState } from "react"

/** 1 audio element dùng chung: play(url) bật/tắt, `playing` = url đang phát. */
export function useAudio() {
  const ref = useRef<HTMLAudioElement | null>(null)
  const [playing, setPlaying] = useState<string | null>(null)

  useEffect(() => {
    const a = new Audio()
    a.onended = () => setPlaying(null)
    a.onerror = () => setPlaying(null)
    ref.current = a
    return () => { a.pause(); a.src = "" }
  }, [])

  const play = useCallback((url: string) => {
    const a = ref.current
    if (!a) return
    if (playing === url) { a.pause(); setPlaying(null); return }
    a.src = url
    a.currentTime = 0
    a.play().then(() => setPlaying(url)).catch(() => setPlaying(null))
  }, [playing])

  const stop = useCallback(() => { ref.current?.pause(); setPlaying(null) }, [])

  return { play, stop, playing }
}
