export type FileFilter = { name: string; extensions: string[] }

export type AuthResult = {
  success: boolean
  key?: string
  expiry?: string | null
  start?: string | null
  remaining?: string | null
  offline?: boolean
  error?: string
}

export type Usage = {
  cpu: number
  ramUsed: number
  ramTotal: number
  gpu: { util: number; memUsed: number; memTotal: number; name: string } | null
}

export type ChatgptAccount = {
  id: number
  label: string
  email: string
  plan: string
  status: string
  errorMsg: string
  isActive: boolean
  createdAt: string
}

export type AiState = {
  chatgpt: ChatgptAccount[]
  gemini: { loggedIn: boolean; status: string; errorMsg: string; loggedAt: string }
}

export type AiResult = { ok: boolean; error?: string; warn?: string; reply?: string; route?: string; model?: string; state?: AiState }

export type PythonStatus = {
  phase: "checking" | "creating" | "installing" | "ready" | "error"
  message: string
  detail?: string
}

export type UpdateState = {
  status: "dev" | "idle" | "checking" | "available" | "downloading" | "downloaded" | "none" | "error"
  current: string
  version?: string
  notes?: string
  percent?: number
  error?: string
}

export type ReleaseNote = { version: string; date: string; body: string }

export type AppInfo = {
  version: string
  previousVersion: string | null
  justUpdated: boolean
  electron: string
  chrome: string
  node: string
  platform: string
  packaged: boolean
  dataDir: string
  logsDir: string
}

export interface ReviewFilmBridge {
  backendUrl: string
  platform: string
  pickFile: (filters?: FileFilter[]) => Promise<string | null>
  pickFiles: (filters?: FileFilter[]) => Promise<string[]>
  pickFolder: () => Promise<string | null>
  openPath: (path: string) => Promise<void>
  showInFolder: (path: string) => Promise<void>
  usage: () => Promise<Usage>
  setTheme: (theme: "dark" | "light") => Promise<void>
  setFullScreen: (on: boolean) => Promise<boolean>
  app: {
    info: () => Promise<AppInfo>
    releaseNotes: () => Promise<ReleaseNote[]>
    openLogs: () => Promise<string>
    openData: () => Promise<string>
  }
  python: {
    status: () => Promise<PythonStatus>
    retry: () => Promise<void>
    onStatus: (cb: (s: PythonStatus) => void) => () => void
  }
  update: {
    state: () => Promise<UpdateState>
    check: () => Promise<UpdateState>
    install: () => Promise<boolean>
    onState: (cb: (s: UpdateState) => void) => () => void
  }
  /** Đăng nhập nền tảng video (Douyin, TikTok, Bilibili…) — lưu cookie cho bộ tải. */
  capcut: {
    /** Mở cửa sổ capcut.com, đăng nhập xong → chuỗi cookie. Đã đăng nhập từ trước thì trả ngay. */
    login: () => Promise<string>
    logout: () => Promise<void>
  }
  ai: {
    state: () => Promise<AiState>
    chatgptLogin: () => Promise<AiResult>
    chatgptLoginDone: () => Promise<AiResult>
    chatgptCheck: (id: number) => Promise<AiResult>
    chatgptSetActive: (id: number) => Promise<AiResult>
    chatgptDelete: (id: number) => Promise<AiResult>
    geminiLogin: () => Promise<AiResult>
    geminiLogout: () => Promise<AiResult>
    geminiCheck: () => Promise<AiResult>
  }
  auth: {
    verify: () => Promise<AuthResult>
    login: (key: string) => Promise<AuthResult>
    logout: () => Promise<{ success: boolean }>
    deviceId: () => Promise<string>
  }
}

declare global {
  interface Window {
    rf?: ReviewFilmBridge
  }
}
