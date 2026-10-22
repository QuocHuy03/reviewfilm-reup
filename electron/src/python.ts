// Chuẩn bị Python cho backend.
//
// Dev:  RF_PYTHON → backend/.venv → `python` (như trước).
// Bản cài đặt: venv riêng ở %APPDATA%/reviewfilm/python-env, tạo ở lần chạy đầu bằng Python của máy.
//   Máy chưa có Python → tự tải Python 3.12 bản portable (gói NuGet chính chủ python.org, ~15 MB) vào
//   %APPDATA%/reviewfilm/python-runtime — không cần quyền admin, không đụng PATH / registry của máy.
//   requirements.txt đổi (sau khi cập nhật app) → tự `pip install` lại. So bằng hash nên không cài thừa.
import { app, net } from "electron"
import { spawn, spawnSync } from "node:child_process"
import crypto from "node:crypto"
import fs from "node:fs"
import path from "node:path"
import { BACKEND_DIR, userDataDir } from "./paths"

export type PythonStatus = { phase: "checking" | "creating" | "installing" | "ready" | "error"; message: string; detail?: string }
type Report = (s: PythonStatus) => void

const MIN_VERSION: [number, number] = [3, 10]
// Python mới hơn (3.13/3.14) hay thiếu bản dựng sẵn của onnxruntime / ctranslate2 → cài thư viện lỗi; dùng bản portable 3.12
const MAX_MINOR = 12
const isWin = process.platform === "win32"

function venvPython(venv: string) {
  return isWin ? path.join(venv, "Scripts", "python.exe") : path.join(venv, "bin", "python")
}

/** Phiên bản của một lệnh python, hoặc null nếu không chạy được. */
function versionOf(cmd: string, args: string[] = []): [number, number] | null {
  const r = spawnSync(cmd, [...args, "-c", "import sys;print(sys.version_info[0], sys.version_info[1])"], {
    encoding: "utf8", windowsHide: true, timeout: 15000,
  })
  if (r.status !== 0) return null
  const [maj, min] = (r.stdout || "").trim().split(/\s+/).map(Number)
  return Number.isFinite(maj) && Number.isFinite(min) ? [maj, min] : null
}

const atLeast = (v: [number, number]) => v[0] > MIN_VERSION[0] || (v[0] === MIN_VERSION[0] && v[1] >= MIN_VERSION[1])

/** Python của máy để tạo venv: RF_PYTHON → py launcher (3.12/3.11/3.10/3) → python → python3. */
function findSystemPython(): { cmd: string; args: string[]; version: string } | null {
  const candidates: [string, string[]][] = []
  if (process.env.RF_PYTHON) candidates.push([process.env.RF_PYTHON, []])
  if (isWin) for (const v of ["-3.12", "-3.11", "-3.10", "-3"]) candidates.push(["py", [v]])
  candidates.push(["python", []], ["python3", []])
  for (const [cmd, args] of candidates) {
    const v = versionOf(cmd, args)
    if (v && atLeast(v) && v[0] === 3 && v[1] <= MAX_MINOR) return { cmd, args, version: v.join(".") }
  }
  return null
}

// Python portable: gói NuGet "python" (x64) — đủ venv + pip, giải nén là chạy. 2 link: CDN của NuGet làm dự phòng.
const PORTABLE_VERSION = "3.12.10"
const PORTABLE_URLS = [
  `https://www.nuget.org/api/v2/package/python/${PORTABLE_VERSION}`,
  `https://globalcdn.nuget.org/packages/python.${PORTABLE_VERSION}.nupkg`,
]
const portableExe = () => userDataDir("python-runtime", "tools", "python.exe")

async function download(url: string, dest: string, onProgress: (pct: number) => void) {
  const res = await net.fetch(url)
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
  const total = Number(res.headers.get("content-length")) || 0
  const out = fs.createWriteStream(dest)
  const reader = res.body.getReader()
  let got = 0
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      got += value.length
      if (!out.write(value)) await new Promise((r) => out.once("drain", r))
      if (total) onProgress(Math.round((got / total) * 100))
    }
  } finally {
    await new Promise((r) => out.end(r))
  }
  if (got < 5_000_000) throw new Error(`tải thiếu (${got} byte)`)
}

/** Tải + giải nén Python portable (chỉ Windows). Đã có thì dùng lại. */
async function ensurePortablePython(report: Report): Promise<string> {
  const exe = portableExe()
  if (fs.existsSync(exe) && versionOf(exe)) return exe
  if (!isWin) throw new Error(`Máy chưa có Python ${MIN_VERSION.join(".")}+ — cài Python rồi mở lại app.`)
  const dir = userDataDir("python-runtime")
  fs.rmSync(dir, { recursive: true, force: true })
  fs.mkdirSync(dir, { recursive: true })
  const zip = path.join(dir, "python.zip")
  const errors: string[] = []
  for (const url of PORTABLE_URLS) {
    try {
      report({ phase: "creating", message: `Máy chưa có Python — đang tải Python ${PORTABLE_VERSION} (~15 MB)…` })
      await download(url, zip, (pct) => report({ phase: "creating", message: `Đang tải Python ${PORTABLE_VERSION}… ${pct}%` }))
      report({ phase: "creating", message: "Đang giải nén Python…" })
      // tar.exe có sẵn từ Windows 10 1803, đọc được zip; máy cũ hơn → PowerShell Expand-Archive
      const sysTar = path.join(process.env.SystemRoot || "C:\\Windows", "System32", "tar.exe")
      try {
        await run(sysTar, ["-xf", zip, "-C", dir, "tools"], () => {})
      } catch {
        const z2 = zip.replace(/\.zip$/, "-ps.zip")
        fs.copyFileSync(zip, z2)
        await run("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command",
          `Expand-Archive -LiteralPath '${z2.replace(/'/g, "''")}' -DestinationPath '${dir.replace(/'/g, "''")}' -Force`], () => {})
        fs.rmSync(z2, { force: true })
      }
      fs.rmSync(zip, { force: true })
      if (!versionOf(exe)) throw new Error("giải nén xong nhưng python.exe không chạy được")
      return exe
    } catch (e) {
      errors.push(`${new URL(url).host}: ${(e as Error).message}`)
    }
  }
  throw new Error(`Không tải được Python tự động (${errors.join(" | ")}). Kiểm tra mạng rồi bấm thử lại, ` +
    `hoặc tự cài Python ${MIN_VERSION.join(".")}+ từ python.org (tick "Add python.exe to PATH").`)
}

// ---------- Microsoft Visual C++ Runtime ----------
// Whisper (ctranslate2), onnxruntime (quét chữ, VieNeu), OpenCV cần msvcp140 / vcruntime140_1. Windows cài mới
// không có → pip vẫn báo cài xong nhưng chạy thì "DLL load failed". Thiếu → tải bộ cài chính chủ Microsoft.
const VC_DLLS = ["msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"]
const VC_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

function vcRuntimeMissing(): string[] {
  if (!isWin) return []
  const sys32 = path.join(process.env.SystemRoot || "C:\\Windows", "System32")
  return VC_DLLS.filter((d) => !fs.existsSync(path.join(sys32, d)))
}

async function installVcRuntime(report: Report): Promise<void> {
  const exe = userDataDir("vc_redist.x64.exe")
  report({ phase: "installing", message: "Máy thiếu Microsoft Visual C++ Runtime — đang tải (~25 MB)…" })
  await download(VC_URL, exe, (pct) => report({ phase: "installing", message: `Đang tải Microsoft Visual C++ Runtime… ${pct}%` }))
  report({ phase: "installing", message: "Đang cài Microsoft Visual C++ Runtime — bấm \"Yes\" nếu Windows hỏi quyền…" })
  // cần quyền admin → Windows hiện hộp UAC; 0 = xong, 3010 = xong (nên khởi động lại), 1638 = đã có bản mới hơn
  const ps = `$p = Start-Process -FilePath '${exe.replace(/'/g, "''")}' -ArgumentList '/install','/quiet','/norestart' -Verb RunAs -Wait -PassThru; exit $p.ExitCode`
  let code = 0
  try {
    await run("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", ps], () => {})
  } catch (e) {
    const m = /thoát mã (-?\d+)/.exec((e as Error).message)
    code = m ? Number(m[1]) : 1
  }
  fs.rmSync(exe, { force: true })
  if (![0, 3010, 1638].includes(code)) {
    throw new Error(`Chưa cài được Microsoft Visual C++ Runtime (mã ${code}${code === 1 ? " — có thể đã bấm No ở hộp quyền" : ""}). ` +
      `Bấm "Thử lại" và chọn Yes, hoặc tự cài từ ${VC_URL}`)
  }
}

// ---------- Kiểm tra thư viện sau khi cài ----------
// import thật từng module quan trọng: pip "Successfully installed" chưa chắc chạy được (thiếu DLL, file tải dở…)
// [module import, tên dễ hiểu, gói pip]
const CHECK_MODULES: [string, string, string][] = [
  ["fastapi", "máy chủ app", "fastapi"], ["numpy", "xử lý số", "numpy"], ["cv2", "OpenCV (đọc khung hình)", "opencv-python"],
  ["PIL", "Pillow (ảnh)", "Pillow"], ["ctranslate2", "Whisper (nhận dạng giọng)", "ctranslate2"], ["faster_whisper", "Whisper", "faster-whisper"],
  ["onnxruntime", "onnxruntime", "onnxruntime"], ["rapidocr_onnxruntime", "quét chữ Trung", "rapidocr_onnxruntime"],
  ["soundfile", "đọc audio", "soundfile"], ["edge_tts", "Edge TTS", "edge-tts"], ["yt_dlp", "tải video", "yt-dlp"],
  ["scenedetect", "cắt cảnh", "scenedetect"],
]
const CHECK_SCRIPT = `import importlib, json
bad = {}
for m in ${JSON.stringify(CHECK_MODULES.map(([m]) => m))}:
    try:
        importlib.import_module(m)
    except BaseException as e:
        bad[m] = (type(e).__name__ + ': ' + str(e))[:300]
print('RFCHECK' + json.dumps(bad))`

async function brokenModules(py: string): Promise<Record<string, string>> {
  let out = ""
  try {
    await run(py, ["-c", CHECK_SCRIPT], (l) => { if (l.startsWith("RFCHECK")) out = l.slice(7) })
  } catch { /* in kết quả trước khi thoát; thoát lỗi vẫn đọc được */ }
  try { return out ? JSON.parse(out) : { python: "không chạy được kiểm tra" } } catch { return { python: out.slice(0, 300) } }
}

const describe = (bad: Record<string, string>) =>
  Object.entries(bad).map(([m, e]) => `• ${CHECK_MODULES.find(([x]) => x === m)?.[1] ?? m} (${m}): ${e}`).join("\n")

/** Chạy lệnh, đẩy từng dòng output ra `onLine`. Reject nếu exit code ≠ 0. */
function run(cmd: string, args: string[], onLine: (l: string) => void, cwd?: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { cwd, windowsHide: true, env: { ...process.env, PYTHONIOENCODING: "utf-8", PIP_DISABLE_PIP_VERSION_CHECK: "1" } })
    let tail = ""
    const feed = (d: Buffer) => {
      for (const line of d.toString("utf8").split(/\r?\n/)) {
        if (!line.trim()) continue
        tail = (tail + "\n" + line).slice(-2000)
        onLine(line.trim())
      }
    }
    p.stdout.on("data", feed)
    p.stderr.on("data", feed)
    p.on("error", reject)
    p.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`${path.basename(cmd)} thoát mã ${code}\n${tail.slice(-600)}`))))
  })
}

function requirementsHash(): string {
  const file = path.join(BACKEND_DIR, "requirements.txt")
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex")
}

/** Python để chạy backend. Bản cài đặt: tạo/cập nhật venv nếu cần (có thể mất vài phút ở lần đầu). */
export async function ensurePython(report: Report): Promise<string> {
  if (!app.isPackaged) {
    if (process.env.RF_PYTHON) return process.env.RF_PYTHON
    const devVenv = venvPython(path.join(BACKEND_DIR, ".venv"))
    if (fs.existsSync(devVenv)) return devVenv
    if (versionOf("python")) return "python"
    // PATH không có `python` (vd mở từ terminal khác) → lấy đường dẫn thật qua py launcher
    const sys = findSystemPython()
    if (sys) {
      const r = spawnSync(sys.cmd, [...sys.args, "-c", "import sys;print(sys.executable)"], { encoding: "utf8", windowsHide: true, timeout: 15000 })
      const exe = (r.stdout || "").trim()
      if (r.status === 0 && exe) return exe
    }
    throw new Error("Không tìm thấy Python ≥ 3.10 (PATH / py launcher). Cài Python hoặc đặt biến RF_PYTHON.")
  }

  const venv = userDataDir("python-env")
  const py = venvPython(venv)
  const stamp = path.join(venv, ".rf-requirements")

  report({ phase: "checking", message: "Kiểm tra môi trường Python…" })
  // venv hỏng (vd đã gỡ Python gốc dùng để tạo nó) → tạo lại từ đầu thay vì báo lỗi khó hiểu
  if (fs.existsSync(py) && !versionOf(py)) fs.rmSync(venv, { recursive: true, force: true })
  if (!fs.existsSync(py)) {
    const sys = findSystemPython() ?? (fs.existsSync(portableExe()) && versionOf(portableExe())
      ? { cmd: portableExe(), args: [], version: PORTABLE_VERSION } : null)
    const base = sys ?? { cmd: await ensurePortablePython(report), args: [], version: PORTABLE_VERSION }
    report({ phase: "creating", message: `Tạo môi trường Python (Python ${base.version})…` })
    fs.rmSync(venv, { recursive: true, force: true })
    try {
      await run(base.cmd, [...base.args, "-m", "venv", venv], () => {})
    } catch (e) {
      // Python của máy lỗi venv (bản thiếu module, bản Store hỏng…) → dùng bản portable
      if (base.cmd === portableExe()) throw e
      fs.rmSync(venv, { recursive: true, force: true })
      const exe = await ensurePortablePython(report)
      report({ phase: "creating", message: `Tạo môi trường Python (Python ${PORTABLE_VERSION})…` })
      await run(exe, ["-m", "venv", venv], () => {})
    }
  }

  // stamp = hash requirements + phiên bản bước kiểm tra: chỉ ghi khi cài XONG và import thử đều chạy được
  const want = requirementsHash() + ":check2"
  const have = fs.existsSync(stamp) ? fs.readFileSync(stamp, "utf8").trim() : ""
  if (want !== have) {
    if (vcRuntimeMissing().length) await installVcRuntime(report)
    report({ phase: "installing", message: have ? "Cập nhật thư viện Python cho bản mới…" : "Cài thư viện Python lần đầu (vài phút)…" })
    await run(py, ["-m", "pip", "install", "--upgrade", "pip"], () => {})
    const pipInstall = (extra: string[] = []) => run(py, ["-m", "pip", "install", ...extra, "-r", path.join(BACKEND_DIR, "requirements.txt")], (line) => {
      if (/^(Collecting|Downloading|Installing|Successfully)/.test(line)) {
        report({ phase: "installing", message: "Đang cài thư viện Python…", detail: line.slice(0, 160) })
      }
    })
    await pipInstall()
    report({ phase: "installing", message: "Kiểm tra thư viện…" })
    let bad = await brokenModules(py)
    if (Object.keys(bad).length) {
      // lỗi DLL → thường do thiếu / hỏng VC++ Runtime; còn lại → cài đè các gói (file tải dở, bản lỗi)
      if (Object.values(bad).some((e) => /DLL/i.test(e)) && isWin) await installVcRuntime(report)
      bad = await brokenModules(py)
      const pkgs = CHECK_MODULES.filter(([m]) => m in bad).map(([, , pkg]) => pkg)
      if (pkgs.length) {
        report({ phase: "installing", message: "Sửa thư viện bị lỗi…", detail: pkgs.join(", ") })
        await run(py, ["-m", "pip", "install", "--force-reinstall", "--no-deps", "--no-cache-dir", ...pkgs], () => {})
        await pipInstall()                       // bù lại phụ thuộc nếu có gói kéo theo bản khác
        bad = await brokenModules(py)
      }
    }
    if (Object.keys(bad).length) {
      throw new Error(`Một số thư viện cài xong nhưng không chạy được:
${describe(bad)}

Bấm "Thử lại"; nếu vẫn lỗi gửi file log (nút "Mở log") cho hỗ trợ.`)
    }
    fs.writeFileSync(stamp, want)
  }
  report({ phase: "ready", message: "Python sẵn sàng" })
  return py
}
