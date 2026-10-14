import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { api } from "@/lib/api"
import type { Options, Settings, SystemInfo, Voice } from "@/lib/types"

export type Page = "home" | "create" | "download" | "studio" | "subtitles" | "voices" | "jobs" | "settings"

type Store = {
  page: Page
  go: (page: Page) => void
  activeJobId: string | null
  openJob: (id: string) => void
  backendReady: boolean
  /** Studio toàn màn hình: ẩn thanh bên + thanh tiêu đề app, cửa sổ vào fullscreen */
  fullscreen: boolean
  setFullscreen: (on: boolean) => void
  options: Options | null
  settings: Settings | null
  setSettings: (s: Settings) => void
  system: SystemInfo | null
  refreshSystem: () => void
  voices: Voice[]
}

const Ctx = createContext<Store | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>("home")
  const [fullscreen, setFs] = useState(false)
  const setFullscreen = useCallback((on: boolean) => { setFs(on); window.rf?.setFullScreen(on).catch(() => {}) }, [])
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [backendReady, setReady] = useState(false)
  const [options, setOptions] = useState<Options | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [system, setSystem] = useState<SystemInfo | null>(null)
  const [voices, setVoices] = useState<Voice[]>([])

  // Chờ backend Python khởi động (Electron spawn mất vài giây)
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        await api.health()
        if (!alive) return
        const [o, s, sys, v] = await Promise.all([api.options(), api.settings(), api.system(), api.voices()])
        if (!alive) return
        setOptions(o); setSettings(s); setSystem(sys); setVoices(v); setReady(true)
      } catch {
        if (alive) setTimeout(tick, 800)
      }
    }
    tick()
    return () => { alive = false }
  }, [])

  // Sau khi lưu key / đăng nhập CapCut, AI: cả trạng thái hệ thống lẫn giọng "dùng được" đều đổi
  const refreshSystem = useCallback(() => {
    api.system().then(setSystem).catch(() => {})
    api.voices().then(setVoices).catch(() => {})
  }, [])
  const openJob = useCallback((id: string) => { setActiveJobId(id); setPage("studio") }, [])

  const value = useMemo<Store>(() => ({
    page, go: setPage, fullscreen, setFullscreen, activeJobId, openJob, backendReady, options, settings, setSettings,
    system, refreshSystem, voices,
  }), [page, fullscreen, setFullscreen, activeJobId, openJob, backendReady, options, settings, system, refreshSystem, voices])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useStore() {
  const s = useContext(Ctx)
  if (!s) throw new Error("useStore phải nằm trong StoreProvider")
  return s
}
