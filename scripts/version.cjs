#!/usr/bin/env node
// Tăng phiên bản theo Semantic Versioning + chốt CHANGELOG.
//
//   node scripts/version.cjs patch|minor|major|x.y.z [--dry]
//   (npm run version:patch / version:minor / version:major)
//
// Việc làm:
//   1. package.json (+ package-lock.json, frontend/package.json) → phiên bản mới — nguồn duy nhất, app/backend/bộ cài đọc từ đây.
//   2. CHANGELOG.md: mục [Unreleased] → "## [x.y.z] - YYYY-MM-DD", mở lại [Unreleased] rỗng, cập nhật link so sánh.
// Sau đó: kiểm tra CHANGELOG rồi `npm run release`.
"use strict"
const fs = require("node:fs")
const path = require("node:path")

const ROOT = path.resolve(__dirname, "..")
const PKG = path.join(ROOT, "package.json")
const LOCK = path.join(ROOT, "package-lock.json")
const FRONTEND_PKG = path.join(ROOT, "frontend", "package.json")
const CHANGELOG = path.join(ROOT, "CHANGELOG.md")
const SEMVER = /^(\d+)\.(\d+)\.(\d+)$/

function fail(msg) {
  console.error(`✖ ${msg}`)
  process.exit(1)
}

function nextVersion(current, bump) {
  const m = SEMVER.exec(current)
  if (!m) fail(`Phiên bản hiện tại "${current}" không đúng dạng x.y.z`)
  let [maj, min, pat] = m.slice(1).map(Number)
  if (bump === "major") return `${maj + 1}.0.0`
  if (bump === "minor") return `${maj}.${min + 1}.0`
  if (bump === "patch") return `${maj}.${min}.${pat + 1}`
  if (SEMVER.test(bump)) return bump
  fail(`Cách dùng: node scripts/version.cjs patch|minor|major|x.y.z [--dry]`)
}

const gt = (a, b) => {
  const [x, y] = [a, b].map((v) => v.split(".").map(Number))
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] > y[i]
  return false
}

function updateChangelog(text, from, to, date) {
  const head = /^## \[Unreleased\]\s*$/m
  if (!head.test(text)) fail("CHANGELOG.md thiếu mục \"## [Unreleased]\"")
  const start = text.search(head)
  const afterHead = text.indexOf("\n", start) + 1
  const nextHead = text.slice(afterHead).search(/^## \[/m)
  const linksAt = text.slice(afterHead).search(/^\[[^\]]+\]:\s*\S+/m)
  const endRel = [nextHead, linksAt].filter((i) => i >= 0).sort((a, b) => a - b)[0] ?? text.length - afterHead
  const body = text.slice(afterHead, afterHead + endRel).trim()
  if (!body) fail("Mục [Unreleased] đang trống — ghi thay đổi (### Added / Changed / Fixed / Removed) trước khi tăng phiên bản.")

  let out = text.slice(0, afterHead) + `\n## [${to}] - ${date}\n\n${body}\n\n` + text.slice(afterHead + endRel).replace(/^\n+/, "")
  // Link so sánh kiểu Keep a Changelog
  const repoMatch = /^\[Unreleased\]:\s*(\S+)\/compare\/v[^.\s]+\.[^.\s]+\.[^.\s]+\.\.\.HEAD/m.exec(out)
  if (repoMatch) {
    const repo = repoMatch[1]
    out = out.replace(/^\[Unreleased\]:.*$/m, `[Unreleased]: ${repo}/compare/v${to}...HEAD\n[${to}]: ${repo}/compare/v${from}...v${to}`)
  }
  return out
}

function main() {
  const [bump, ...flags] = process.argv.slice(2)
  const dry = flags.includes("--dry")
  const pkg = JSON.parse(fs.readFileSync(PKG, "utf8"))
  const from = pkg.version
  const to = nextVersion(from, bump)
  if (!gt(to, from)) fail(`Phiên bản mới ${to} phải lớn hơn ${from}`)
  const date = new Date().toISOString().slice(0, 10)
  const changelog = updateChangelog(fs.readFileSync(CHANGELOG, "utf8"), from, to, date)

  if (dry) {
    console.log(`(dry) ${from} → ${to}\n`)
    console.log(changelog.split("\n").slice(0, 40).join("\n"))
    return
  }
  pkg.version = to
  fs.writeFileSync(PKG, JSON.stringify(pkg, null, 2) + "\n")
  if (fs.existsSync(LOCK)) {
    const lock = JSON.parse(fs.readFileSync(LOCK, "utf8"))
    lock.version = to
    if (lock.packages?.[""]) lock.packages[""].version = to
    fs.writeFileSync(LOCK, JSON.stringify(lock, null, 2) + "\n")
  }
  if (fs.existsSync(FRONTEND_PKG)) {
    const fp = JSON.parse(fs.readFileSync(FRONTEND_PKG, "utf8"))
    fp.version = to
    fs.writeFileSync(FRONTEND_PKG, JSON.stringify(fp, null, 2) + "\n")
  }
  fs.writeFileSync(CHANGELOG, changelog)
  console.log(`✔ ${from} → ${to} (${date})`)
  console.log("  Tiếp theo: xem lại CHANGELOG.md → npm run check → npm run release")
}

main()
