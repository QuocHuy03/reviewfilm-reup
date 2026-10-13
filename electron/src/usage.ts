import { execFile } from "node:child_process"
import os from "node:os"

export type Usage = {
  cpu: number                       // % toàn máy
  ramUsed: number; ramTotal: number // bytes
  gpu: { util: number; memUsed: number; memTotal: number; name: string } | null
}

let prev = os.cpus().map((c) => c.times)

function cpuPercent() {
  const cur = os.cpus().map((c) => c.times)
  let idle = 0, total = 0
  cur.forEach((t, i) => {
    const p = prev[i] ?? t
    const d = (k: keyof typeof t) => t[k] - p[k]
    const all = d("user") + d("nice") + d("sys") + d("irq") + d("idle")
    idle += d("idle"); total += all
  })
  prev = cur
  return total > 0 ? Math.round((1 - idle / total) * 100) : 0
}

// nvidia-smi: kiểm tra 1 lần, máy không có GPU NVIDIA thì bỏ qua luôn
let hasNvidia: boolean | null = null
function gpuUsage(): Promise<Usage["gpu"]> {
  if (hasNvidia === false) return Promise.resolve(null)
  return new Promise((resolve) => {
    execFile("nvidia-smi", ["--query-gpu=utilization.gpu,memory.used,memory.total,name", "--format=csv,noheader,nounits"],
      { timeout: 3000, windowsHide: true }, (err, out) => {
        if (err || !out.trim()) { hasNvidia = false; return resolve(null) }
        hasNvidia = true
        const [util, used, total, ...name] = out.trim().split("\n")[0].split(",").map((s) => s.trim())
        resolve({ util: +util, memUsed: +used * 1048576, memTotal: +total * 1048576, name: name.join(",") })
      })
  })
}

export async function usage(): Promise<Usage> {
  return { cpu: cpuPercent(), ramUsed: os.totalmem() - os.freemem(), ramTotal: os.totalmem(), gpu: await gpuUsage() }
}
