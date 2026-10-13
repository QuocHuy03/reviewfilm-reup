// Chạy Electron với env sạch: VS Code / một số terminal set ELECTRON_RUN_AS_NODE=1
// khiến require("electron") trả về đường dẫn binary thay vì API → app crash.
const { spawn } = require("node:child_process")
const electron = require("electron")

const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE
const child = spawn(electron, ["."], { stdio: "inherit", env, cwd: require("node:path").resolve(__dirname, "..") })
child.on("exit", (code) => process.exit(code ?? 0))
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig))
