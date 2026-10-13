// Lấy/refresh cookie Gemini qua Playwright (persistent Chrome profile) — port app/gemini_login.py.
// Lần đầu chạy headless=false để user đăng nhập Google; profile lưu lại → lần sau refresh headless.

import { createRequire } from 'module';
import { join } from 'path';
import { mkdirSync } from 'fs';

const _require = createRequire(import.meta.url);

function loggedIn(cookies) {
  return cookies.some((c) => c.name === '__Secure-1PSID' && c.value);
}

/**
 * @param {string} workDir  thư mục chứa profile chrome (persistent)
 * @param {{headless?: boolean}} opts
 * @returns {Promise<string|null>} cookie string "k=v; k=v" hoặc null nếu cần đăng nhập tay
 */
export async function playwrightRefresh(workDir, { headless = true } = {}) {
  const { chromium } = _require('playwright');
  const profileDir = join(workDir || process.cwd(), '.gemini-chrome-data');
  mkdirSync(profileDir, { recursive: true });

  const ctx = await chromium.launchPersistentContext(profileDir, {
    headless,
    channel: 'chrome',
    args: ['--disable-blink-features=AutomationControlled'],
    viewport: { width: 1280, height: 900 },
  });
  try {
    const page = ctx.pages()[0] || (await ctx.newPage());
    await page.goto('https://gemini.google.com/app', { waitUntil: 'domcontentloaded', timeout: 60000 });

    let cookies = await ctx.cookies();
    if (!loggedIn(cookies)) {
      if (headless) return null; // cần đăng nhập tương tác
      // Chờ user đăng nhập (tối đa ~5 phút), poll tới khi có __Secure-1PSID.
      const deadline = Date.now() + 300000;
      while (Date.now() < deadline) {
        await page.waitForTimeout(2000);
        cookies = await ctx.cookies();
        if (loggedIn(cookies)) break;
      }
      if (!loggedIn(cookies)) return null;
    }

    // Gom cookie từ các domain Google liên quan, ưu tiên domain rộng, bắt buộc __Secure-1PSID.
    const wanted = await ctx.cookies([
      'https://gemini.google.com',
      'https://accounts.google.com',
      'https://google.com',
    ]);
    const byName = new Map();
    for (const c of wanted) {
      if (!c.value) continue;
      const prev = byName.get(c.name);
      // ưu tiên domain rộng hơn (bắt đầu bằng '.')
      if (!prev || ((c.domain || '').startsWith('.') && !(prev.domain || '').startsWith('.'))) {
        byName.set(c.name, c);
      }
    }
    if (!byName.has('__Secure-1PSID')) return null;
    return [...byName.values()].map((c) => `${c.name}=${c.value}`).join('; ');
  } finally {
    await ctx.close().catch(() => {});
  }
}
