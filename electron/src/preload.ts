import { contextBridge, ipcRenderer } from "electron"

const arg = process.argv.find((a) => a.startsWith("--rf-backend="))
const backendUrl = arg ? arg.slice("--rf-backend=".length) : "http://127.0.0.1:8765"

contextBridge.exposeInMainWorld("rf", {
  backendUrl,
  platform: process.platform,
  pickFile: (filters?: { name: string; extensions: string[] }[]) => ipcRenderer.invoke("rf:pickFile", filters),
  pickFiles: (filters?: { name: string; extensions: string[] }[]) => ipcRenderer.invoke("rf:pickFiles", filters),
  pickFolder: () => ipcRenderer.invoke("rf:pickFolder"),
  openPath: (p: string) => ipcRenderer.invoke("rf:openPath", p),
  showInFolder: (p: string) => ipcRenderer.invoke("rf:showInFolder", p),
  usage: () => ipcRenderer.invoke("sys:usage"),
  setTheme: (theme: "dark" | "light") => ipcRenderer.invoke("rf:setTheme", theme),
  setFullScreen: (on: boolean) => ipcRenderer.invoke("rf:setFullScreen", on),
  app: {
    info: () => ipcRenderer.invoke("app:info"),
    releaseNotes: () => ipcRenderer.invoke("app:releaseNotes"),
    openLogs: () => ipcRenderer.invoke("app:openLogs"),
    openData: () => ipcRenderer.invoke("app:openData"),
  },
  python: {
    status: () => ipcRenderer.invoke("py:status"),
    retry: () => ipcRenderer.invoke("py:retry"),
    onStatus: (cb: (s: unknown) => void) => {
      const h = (_e: unknown, s: unknown) => cb(s)
      ipcRenderer.on("py:status", h)
      return () => { ipcRenderer.removeListener("py:status", h) }
    },
  },
  update: {
    state: () => ipcRenderer.invoke("update:state"),
    check: () => ipcRenderer.invoke("update:check"),
    install: () => ipcRenderer.invoke("update:install"),
    onState: (cb: (s: unknown) => void) => {
      const h = (_e: unknown, s: unknown) => cb(s)
      ipcRenderer.on("update:state", h)
      return () => { ipcRenderer.removeListener("update:state", h) }
    },
  },
  capcut: {
    login: () => ipcRenderer.invoke("capcut:login"),
    logout: () => ipcRenderer.invoke("capcut:logout"),
  },
  ai: {
    state: () => ipcRenderer.invoke("ai:state"),
    chatgptLogin: () => ipcRenderer.invoke("ai:chatgptLogin"),
    chatgptLoginDone: () => ipcRenderer.invoke("ai:chatgptLoginDone"),
    chatgptCheck: (id: number) => ipcRenderer.invoke("ai:chatgptCheck", id),
    chatgptSetActive: (id: number) => ipcRenderer.invoke("ai:chatgptSetActive", id),
    chatgptDelete: (id: number) => ipcRenderer.invoke("ai:chatgptDelete", id),
    geminiLogin: () => ipcRenderer.invoke("ai:geminiLogin"),
    geminiLogout: () => ipcRenderer.invoke("ai:geminiLogout"),
    geminiCheck: () => ipcRenderer.invoke("ai:geminiCheck"),
  },
  auth: {
    verify: () => ipcRenderer.invoke("auth:verify"),
    login: (key: string) => ipcRenderer.invoke("auth:login", key),
    logout: () => ipcRenderer.invoke("auth:logout"),
    deviceId: () => ipcRenderer.invoke("auth:get-device-id"),
  },
})
