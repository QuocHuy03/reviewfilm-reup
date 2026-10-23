// Tài khoản AI web (chatgpt.com + gemini.google.com) — port từ ToolYoutube chatgptService/videoTemplateService.
//
// "Tự login" = mở Chrome THẬT (profile riêng, không cờ automation) cho người dùng đăng nhập MỘT lần.
// App lấy cookie + giữ profile, các lượt sau gọi thẳng API nội bộ của site (không bấm UI):
//   · ChatGPT: cookie → HTTP thuần; cookie chết/bị chặn → mở lại profile (ẩn ngoài màn hình) rồi ghi cookie mới.
//   · Gemini : cookie __Secure-1PSID → StreamGenerate; auth hỏng → refresh cookie từ profile (headless).
//
// Lưu ở %APPDATA%/reviewfilm/ai/accounts.json (không dùng sqlite để khỏi rebuild native module).
// Cookie KHÔNG bao giờ đi qua IPC: publicState() lọc bỏ.

import { mkdirSync, existsSync, rmSync, cpSync, readFileSync, writeFileSync, renameSync } from 'fs';
import { join } from 'path';
import { ChatGPTWeb } from './chatgptWeb.js';
import { ChatGPTClient } from './chatgptClient.js';
import { GeminiWeb, cookiesFromString } from './geminiWeb.js';
import { playwrightRefresh } from './geminiLogin.js';

const BASE = 'https://chatgpt.com';
export const DEFAULT_CHATGPT_MODEL = 'gpt-5-5-thinking';

let ROOT = '';
let STORE_FILE = '';
let store = { chatgpt: [], gemini: { cookies: '', clientContextToken: '', status: '', errorMsg: '', loggedAt: '' }, nextId: 1 };

export function initAccounts(userDataDir) {
  ROOT = join(userDataDir, 'ai');
  STORE_FILE = join(ROOT, 'accounts.json');
  mkdirSync(ROOT, { recursive: true });
  try {
    const raw = JSON.parse(readFileSync(STORE_FILE, 'utf8'));
    store = { ...store, ...raw, gemini: { ...store.gemini, ...(raw.gemini || {}) } };
  } catch { /* lần đầu chạy */ }
}

function save() {
  const tmp = STORE_FILE + '.tmp';
  writeFileSync(tmp, JSON.stringify(store, null, 2), 'utf8');
  renameSync(tmp, STORE_FILE);
}

/** Windows giữ khoá file profile vài trăm ms sau khi Chrome đóng → xoá có thử lại. */
async function wipeDir(dir, tries = 5) {
  for (let i = 0; i < tries; i++) {
    try {
      rmSync(dir, { recursive: true, force: true });
      if (!existsSync(dir)) return true;
    } catch { /* còn khoá */ }
    await new Promise((r) => setTimeout(r, 300 * (i + 1)));
  }
  return !existsSync(dir);
}

const safeNameOf = (email) => String(email || 'mac-dinh').replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 60);
const now = () => new Date().toISOString();

// ───────────────────────────── trạng thái cho UI ─────────────────────────────

export function publicState() {
  return {
    chatgpt: store.chatgpt.map((a) => ({
      id: a.id, label: a.label, email: a.email, plan: a.plan || '',
      status: a.status || '', errorMsg: a.errorMsg || '', isActive: !!a.isActive, createdAt: a.createdAt,
    })),
    gemini: {
      loggedIn: !!(store.gemini.cookies || '').trim(),
      status: store.gemini.status || '', errorMsg: store.gemini.errorMsg || '', loggedAt: store.gemini.loggedAt || '',
    },
  };
}

export function readiness() {
  return {
    chatgpt: store.chatgpt.some((a) => a.isActive),
    gemini: !!(store.gemini.cookies || '').trim(),
  };
}

// ───────────────────────────────── ChatGPT ───────────────────────────────────

let _loginDone = false;
export function chatgptLoginDone() { _loginDone = true; return { ok: true }; }

export async function chatgptLogin({ timeoutMs = 300000 } = {}) {
  const tmpDir = join(ROOT, 'chatgpt', '_dang-nhap');
  await wipeDir(tmpDir);
  mkdirSync(tmpDir, { recursive: true });
  const web = new ChatGPTWeb(tmpDir, { headless: false });
  try {
    const page = await web._ensurePage();
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 60000 });

    // Chờ người dùng bấm "Xong" trong app hoặc đóng cửa sổ — lấy phiên ĐANG đăng nhập lúc đó.
    _loginDone = false;
    const deadline = Date.now() + timeoutMs;
    let session = null;
    while (Date.now() < deadline) {
      if (_loginDone || page.isClosed()) break;
      try {
        const r = await page.evaluate(async () => {
          const res = await fetch('/api/auth/session', { credentials: 'include' });
          return { status: res.status, text: await res.text() };
        });
        if (r.status === 200) {
          const j = JSON.parse(r.text || '{}');
          session = j?.accessToken ? j : null;
        }
      } catch { /* đang chuyển trang */ }
      try { await page.waitForTimeout(1500); } catch { break; }
    }
    if (!session) {
      return { ok: false, error: (_loginDone || page.isClosed())
        ? 'Chưa đăng nhập chatgpt.com trong cửa sổ vừa mở.'
        : 'Hết thời gian chờ đăng nhập ChatGPT.' };
    }

    const email = session?.user?.email || '';
    const plan = await web.plan().catch(() => '');
    let creds = { cookies: '', userAgent: '' };
    try { creds = await web.credentials(); } catch (e) { console.warn(`[chatgpt] không lấy được cookie: ${e?.message || e}`); }
    await web.close();

    const dest = join(ROOT, 'chatgpt', safeNameOf(email));
    try {
      await wipeDir(dest);
      mkdirSync(dest, { recursive: true });
      cpSync(join(tmpDir, '.chatgpt-chrome-data'), join(dest, '.chatgpt-chrome-data'), { recursive: true });
    } catch (e) {
      return { ok: false, error: `Đăng nhập được nhưng không lưu được profile: ${e?.message || e}` };
    }

    let acc = store.chatgpt.find((a) => email && a.email === email);
    if (!acc) {
      acc = { id: store.nextId++, createdAt: now() };
      store.chatgpt.push(acc);
    }
    Object.assign(acc, { label: email || 'ChatGPT', email, profileDir: dest, plan, cookies: creds.cookies,
      userAgent: creds.userAgent, status: 'ok', errorMsg: '' });
    if (!store.chatgpt.some((a) => a.isActive)) acc.isActive = true;
    save();
    resetChatgptClient();
    return { ok: true, email, state: publicState() };
  } catch (e) {
    return { ok: false, error: e?.message || String(e) };
  } finally {
    await web.close();
  }
}

function clientFor(acc, model) {
  return new ChatGPTClient({
    profileDir: acc.profileDir || '',
    cookies: acc.cookies || '',
    userAgent: acc.userAgent || '',
    model: model || DEFAULT_CHATGPT_MODEL,
    onCreds: (creds) => {
      acc.cookies = creds.cookies || acc.cookies;
      acc.userAgent = creds.userAgent || acc.userAgent;
      try { save(); } catch { /* đang thoát app */ }
    },
  });
}

export async function chatgptCheck(id) {
  const acc = store.chatgpt.find((a) => a.id === Number(id));
  if (!acc) return { ok: false, error: 'Không tìm thấy tài khoản.' };
  const client = clientFor(acc);
  try {
    const r = await client.chat('Trả lời đúng một từ: OK');
    const reply = (r.message || '').trim();
    if (!reply) throw new Error('chatgpt.com trả về rỗng.');
    acc.status = 'ok'; acc.errorMsg = '';
    try { acc.plan = (await client.plan()) || acc.plan; } catch { /* không quan trọng */ }
    save();
    return { ok: true, reply: reply.slice(0, 200), model: r.model || '', route: client.lastRoute, state: publicState() };
  } catch (e) {
    acc.status = 'error'; acc.errorMsg = e?.message || String(e);
    save();
    return { ok: false, error: acc.errorMsg, kind: e?.kind || 'unknown', state: publicState() };
  } finally {
    await client.close();
  }
}

export function chatgptSetActive(id) {
  for (const a of store.chatgpt) a.isActive = a.id === Number(id);
  save();
  resetChatgptClient();
  return { ok: true, state: publicState() };
}

export async function chatgptDelete(id) {
  const acc = store.chatgpt.find((a) => a.id === Number(id));
  store.chatgpt = store.chatgpt.filter((a) => a.id !== Number(id));
  if (acc?.isActive && store.chatgpt.length) store.chatgpt[0].isActive = true;
  save();
  resetChatgptClient();
  if (acc?.profileDir && !(await wipeDir(acc.profileDir))) {
    return { ok: true, state: publicState(),
      warn: `Đã xoá tài khoản nhưng chưa xoá được profile Chrome ở "${acc.profileDir}" (Chrome còn mở?). Đóng Chrome rồi xoá tay.` };
  }
  return { ok: true, state: publicState() };
}

// Client dùng chung — giữ cookie/token giữa các lượt; dựng lại khi đổi tài khoản.
let _gpt = null;
let _gptAccId = -1;
let _gptQueue = Promise.resolve();

function resetChatgptClient() {
  _gpt?.close().catch(() => {});
  _gpt = null;
  _gptAccId = -1;
}

/** Gửi 1 prompt qua tài khoản ChatGPT đang chọn. Tuần tự hoá: client giữ một phiên trình duyệt. */
export function chatgptChat(prompt, { model } = {}) {
  const run = async () => {
    const acc = store.chatgpt.find((a) => a.isActive);
    if (!acc) throw Object.assign(new Error('Chưa đăng nhập tài khoản ChatGPT (Cài đặt → Tài khoản AI).'), { kind: 'auth' });
    if (!_gpt || _gptAccId !== acc.id) { resetChatgptClient(); _gpt = clientFor(acc); _gptAccId = acc.id; }
    try {
      const r = await _gpt.chat(prompt, model ? { model } : {});
      if (acc.status !== 'ok') { acc.status = 'ok'; acc.errorMsg = ''; save(); }
      return r;
    } catch (e) {
      acc.status = 'error'; acc.errorMsg = e?.message || String(e); save();
      throw e;
    }
  };
  const p = _gptQueue.then(run, run);
  _gptQueue = p.catch(() => {});
  return p;
}

/**
 * Tạo ảnh qua tài khoản ChatGPT đang chọn. `refs` là đường dẫn ảnh tham chiếu trên máy.
 * Đi chung hàng đợi với chat: lượt lùi sang trình duyệt dùng chung một profile bị khoá.
 */
export function chatgptImage(prompt, { refs = [], outDir, timeoutMs } = {}) {
  const run = async () => {
    const acc = store.chatgpt.find((a) => a.isActive);
    if (!acc) throw Object.assign(new Error('Chưa đăng nhập tài khoản ChatGPT (Cài đặt → Tài khoản AI).'), { kind: 'auth' });
    if (!_gpt || _gptAccId !== acc.id) { resetChatgptClient(); _gpt = clientFor(acc); _gptAccId = acc.id; }
    try {
      const r = await _gpt.image(prompt, { refs, outDir: outDir || join(ROOT, 'images'), ...(timeoutMs ? { timeoutMs } : {}) });
      if (acc.status !== 'ok') { acc.status = 'ok'; acc.errorMsg = ''; save(); }
      return r;
    } catch (e) {
      // Bị từ chối nội dung không có nghĩa tài khoản hỏng — không đánh dấu lỗi tài khoản.
      if (e?.kind !== 'noimage' && e?.kind !== 'input') { acc.status = 'error'; acc.errorMsg = e?.message || String(e); save(); }
      throw e;
    }
  };
  const p = _gptQueue.then(run, run);
  _gptQueue = p.catch(() => {});
  return p;
}

// ───────────────────────────────── Gemini ────────────────────────────────────

const geminiWorkDir = () => join(ROOT, 'gemini');

export async function geminiLogin() {
  try {
    const cookieStr = await playwrightRefresh(geminiWorkDir(), { headless: false });
    if (!cookieStr) return { ok: false, error: 'Chưa đăng nhập được Gemini (thiếu cookie __Secure-1PSID).' };
    Object.assign(store.gemini, { cookies: cookieStr, clientContextToken: '', status: 'ok', errorMsg: '', loggedAt: now() });
    save();
    _gem = null;
    return { ok: true, state: publicState() };
  } catch (e) {
    return { ok: false, error: e?.message || String(e) };
  }
}

export async function geminiLogout() {
  Object.assign(store.gemini, { cookies: '', clientContextToken: '', status: '', errorMsg: '', loggedAt: '' });
  save();
  _gem = null;
  const wiped = await wipeDir(join(geminiWorkDir(), '.gemini-chrome-data'));
  return { ok: true, state: publicState(), ...(wiped ? {} : { warn: 'Chưa xoá được profile Chrome của Gemini (Chrome còn mở?).' }) };
}

let _gem = null;
let _gemQueue = Promise.resolve();

function geminiClient() {
  const cookies = cookiesFromString(store.gemini.cookies || '');
  if (!cookies['__Secure-1PSID']) {
    throw Object.assign(new Error('Chưa đăng nhập Gemini (Cài đặt → Tài khoản AI).'), { kind: 'auth' });
  }
  if (!_gem) {
    _gem = new GeminiWeb(cookies, {
      clientContextToken: store.gemini.clientContextToken || '',
      workDir: geminiWorkDir(),
      onCookiesRefreshed: (str) => { store.gemini.cookies = str; try { save(); } catch { /* thoát app */ } },
    });
  }
  return _gem;
}

/** Một lượt Gemini độc lập (hội thoại mới), có thể kèm file ảnh/video trên máy. */
export function geminiChat(prompt, { files = null, timeout = null } = {}) {
  const run = async () => {
    const g = geminiClient();
    g.reset();
    try {
      const r = await g.sendMessage(prompt, { files, timeout });
      if (store.gemini.status !== 'ok') { store.gemini.status = 'ok'; store.gemini.errorMsg = ''; save(); }
      return r;
    } catch (e) {
      store.gemini.status = 'error'; store.gemini.errorMsg = e?.message || String(e); save();
      throw e;
    }
  };
  const p = _gemQueue.then(run, run);
  _gemQueue = p.catch(() => {});
  return p;
}

export async function geminiCheck() {
  try {
    const r = await geminiChat('Trả lời đúng một từ: OK');
    return { ok: true, reply: String(r?.content || '').slice(0, 200), state: publicState() };
  } catch (e) {
    return { ok: false, error: e?.message || String(e), state: publicState() };
  }
}

export async function closeAll() {
  resetChatgptClient();
  _gem = null;
}
