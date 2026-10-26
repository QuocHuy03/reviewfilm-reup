import { useCallback, useEffect, useId, useSyncExternalStore } from "react"

type QueueItem = { url: string; key: string }
type State = { playing: string | null; queueKey: string | null }

/**
 * MỘT trình phát dùng chung cả app: phát cái mới thì cái đang phát tự dừng (không bao giờ 2 tiếng chồng nhau,
 * kể cả giữa 2 ô chọn giọng / 2 trang khác nhau). Mọi nơi dùng useAudio() thấy cùng trạng thái `playing`.
 */
let audio: HTMLAudioElement | null = null
let queue: QueueItem[] = []
let state: State = { playing: null, queueKey: null }
let owner = ""                                   // nơi (hook) đang phát — nơi đó rời màn hình thì tự tắt tiếng
const subs = new Set<() => void>()

function setState(p: Partial<State>) {
  state = { ...state, ...p }
  subs.forEach((f) => f())
}

function el() {
  if (!audio) {
    audio = new Audio()
    audio.onended = () => (queue.length ? next() : setState({ playing: null, queueKey: null }))
    audio.onerror = () => (queue.length ? next() : setState({ playing: null, queueKey: null }))
  }
  return audio
}

function start(url: string) {
  const a = el()
  a.pause()
  a.src = url
  a.currentTime = 0
  setState({ playing: url })
  return a.play()
}

function next() {
  const item = queue.shift()
  if (!item) { setState({ playing: null, queueKey: null }); return }
  setState({ queueKey: item.key })
  start(item.url).catch(() => { if (state.playing === item.url) next() })   // file lỗi → bỏ qua, phát tiếp (bị huỷ vì phát cái khác thì thôi)
}

/** Dừng mọi âm thanh đang phát (vd. trước khi phát video xem trước). */
export function stopAllAudio() {
  queue = []
  audio?.pause()
  setState({ playing: null, queueKey: null })
}

const subscribe = (f: () => void) => { subs.add(f); return () => { subs.delete(f) } }
const snapshot = () => state

export function useAudio() {
  const { playing, queueKey } = useSyncExternalStore(subscribe, snapshot)
  const id = useId()
  useEffect(() => () => { if (owner === id) stopAllAudio() }, [id])

  /** Bấm lần nữa vào đúng file đang phát = dừng; file khác = dừng cái cũ, phát cái mới. */
  const play = useCallback((url: string) => {
    queue = []
    setState({ queueKey: null })
    if (state.playing === url) { stopAllAudio(); return }
    owner = id
    start(url).catch(() => { if (state.playing === url) setState({ playing: null }) })   // bấm cái khác ngay sau → lỗi của cái cũ bỏ qua
  }, [id])

  const playList = useCallback((items: QueueItem[]) => {
    owner = id
    audio?.pause()
    queue = [...items]
    next()
  }, [id])

  return { play, stop: stopAllAudio, playing, playList, queueKey }
}
