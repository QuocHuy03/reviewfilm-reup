// Unofficial Gemini web client — port Node của app/gemini_web.py.
// video + prompt -> assistant text. Xử lý: scrape token trang /app, upload file lên content-push,
// StreamGenerate (TLS trình duyệt qua got-scraping), parse JSPB/XSSI, retry khi "Analyzing video".
//
// LƯU Ý: đây là reverse-engineer trang gemini.google.com (không phải Gemini API chính thức) — auth
// bằng COOKIE tài khoản Google (__Secure-1PSID bắt buộc). Google đổi web là có thể gãy.

import { readFileSync, statSync } from 'fs';
import { basename } from 'path';
import { setTimeout as sleep } from 'timers/promises';
import { randomUUID } from 'crypto';

const APP_URL = 'https://gemini.google.com/app';
const ENDPOINT =
  'https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate';
const UPLOAD_ENDPOINT = 'https://content-push.googleapis.com/upload';
const DEFAULT_TIMEOUT = 120000;
const COOKIE_REFRESH_INTERVAL = 2700 * 1000; // 45 min

export class GeminiAuthError extends Error {}
export class GeminiParseError extends Error {}

// TLS an toàn cho Electron (BoringSSL). got-scraping đôi khi random fingerprint Firefox và set
// ecdhCurve = "...:ffdhe2048:ffdhe3072" — BoringSSL của Electron KHÔNG nhận các nhóm ffdhe này ⇒ ném
// "Failed to set ECDH curve". Ta set sẵn `https.ciphers` (chuẩn Chrome, BoringSSL-safe) ⇒ tlsHook của
// got-scraping tự BỎ QUA (nó chỉ chèn khi ciphers CHƯA set), nên ecdhCurve Chrome (chỉ EC curves) được
// giữ, không còn ffdhe. Fingerprint vẫn browser-like, và mọi request đều dùng qua .extend() bên dưới.
const SAFE_TLS = {
  ciphers: [
    'ECDHE-ECDSA-AES128-GCM-SHA256', 'ECDHE-RSA-AES128-GCM-SHA256',
    'ECDHE-ECDSA-AES256-GCM-SHA384', 'ECDHE-RSA-AES256-GCM-SHA384',
    'ECDHE-ECDSA-CHACHA20-POLY1305', 'ECDHE-RSA-CHACHA20-POLY1305',
    'ECDHE-RSA-AES128-SHA', 'ECDHE-RSA-AES256-SHA',
    'AES128-GCM-SHA256', 'AES256-GCM-SHA384', 'AES128-SHA', 'AES256-SHA',
  ].join(':'),
  ecdhCurve: 'X25519:prime256v1:secp384r1',
  minVersion: 'TLSv1.2',
  maxVersion: 'TLSv1.3',
};

let _gotScraping = null;
let _gotSafe = null;
async function got() {
  if (!_gotScraping) ({ gotScraping: _gotScraping } = await import('got-scraping'));
  // .extend gắn https an toàn làm default cho MỌI request ⇒ né lỗi ECDH trên BoringSSL.
  if (!_gotSafe) _gotSafe = _gotScraping.extend({ https: SAFE_TLS });
  return _gotSafe;
}

export function cookiesFromString(raw) {
  const cookies = {};
  for (let item of (raw || '').trim().split(';')) {
    item = item.trim();
    if (!item || !item.includes('=')) continue;
    const idx = item.indexOf('=');
    const key = item.slice(0, idx).trim();
    const val = item.slice(idx + 1).trim().replace(/^"|"$/g, '');
    cookies[key] = val;
  }
  return cookies;
}

// Giải escape token scrape từ JSON string ("SNlM0e":"...") — tương đương unicode_escape của Python.
function decodeToken(raw) {
  try { return JSON.parse('"' + raw + '"'); } catch { return raw; }
}

function randInt(a, b) { return a + Math.floor(Math.random() * (b - a + 1)); }

export class GeminiWeb {
  constructor(cookies, { clientContextToken = '', onCookiesRefreshed = null, workDir = '' } = {}) {
    this.cookies = { ...(cookies || {}) };            // name -> value
    this.appUrl = APP_URL;
    this.workDir = workDir;
    this.onCookiesRefreshed = onCookiesRefreshed;

    this._at = null; this._bl = null; this._fSid = null;
    this._clientContextToken = clientContextToken || null;
    this._reqid = randInt(100000, 999999);
    this._lastRefresh = 0;

    this.conversationId = ''; this.responseId = ''; this.choiceId = '';
  }

  _cookieHeader() {
    return Object.entries(this.cookies).map(([k, v]) => `${k}=${v}`).join('; ');
  }

  _absorbSetCookie(res) {
    const sc = res.headers?.['set-cookie'];
    if (!Array.isArray(sc)) return;
    for (const line of sc) {
      const first = String(line).split(';', 1)[0];
      const idx = first.indexOf('=');
      if (idx <= 0) continue;
      const k = first.slice(0, idx).trim(), v = first.slice(idx + 1).trim();
      if (v) this.cookies[k] = v;
    }
  }

  _baseHeaders() {
    return {
      'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
      Origin: 'https://gemini.google.com',
      Referer: this.appUrl,
      'X-Same-Domain': '1',
      Cookie: this._cookieHeader(),
    };
  }

  async _get(url, headers, timeout) {
    const g = await got();
    const res = await g(url, {
      method: 'GET', headers, throwHttpErrors: false,
      timeout: { request: timeout }, responseType: 'text', followRedirect: true,
    });
    this._absorbSetCookie(res);
    return res;
  }

  async _post(url, { searchParams, body, headers, timeout, followRedirect = true }) {
    const g = await got();
    const res = await g(url, {
      method: 'POST', searchParams, body, headers, throwHttpErrors: false,
      timeout: { request: timeout }, responseType: 'text', followRedirect,
    });
    this._absorbSetCookie(res);
    return res;
  }

  // ── token discovery ──────────────────────────────────────────────────
  _extractFirst(html, patterns) {
    for (const re of patterns) {
      const m = re.exec(html);
      if (m) return decodeToken(m[1]);
    }
    return null;
  }

  _extractWizContextToken(html) {
    const m = /WIZ_global_data\s*=\s*(\{[\s\S]*?\});/.exec(html);
    if (!m) return null;
    try {
      const data = JSON.parse(m[1]);
      for (const key of ['PI9WOb', 'GWsdKe', 'IVn0ke']) {
        const val = data[key];
        if (typeof val === 'string' && val.length > 100) return '!' + val;
      }
    } catch {}
    return null;
  }

  async refreshTokens() {
    const res = await this._get(this.appUrl, this._baseHeaders(), DEFAULT_TIMEOUT);
    const html = res.body || '';
    if (html.slice(0, 500).includes('accounts.google.com') || html.slice(0, 5000).includes('Sign in')) {
      throw new GeminiAuthError('Cookie Gemini thiếu/hết hạn — cần đăng nhập lại trình duyệt.');
    }
    this._at = this._extractFirst(html, [
      /"SNlM0e"\s*:\s*"([^"]+)"/,
      /"cfb2h"\s*:\s*"([^"]+)"/,
      /name="at"\s+value="([^"]+)"/,
    ]);
    this._bl = this._extractFirst(html, [
      /(boq_assistant-bard-web-server_[^"'\\\s]+)/,
      /"bl"\s*:\s*"(boq_assistant-[^"]+)"/,
    ]);
    this._fSid = this._extractFirst(html, [/"FdrFJe"\s*:\s*"([^"]+)"/]);
    this._clientContextToken =
      this._extractFirst(html, [/"(!zs[^"]+)"/, /"(![A-Za-z0-9][A-Za-z0-9_\-]{100,})"/]) ||
      this._extractWizContextToken(html) ||
      this._clientContextToken;
    if (!this._at) throw new GeminiAuthError('Không tìm thấy token yêu cầu của Gemini (SNlM0e).');
    this._lastRefresh = Date.now();
  }

  reset() { this.conversationId = ''; this.responseId = ''; this.choiceId = ''; }

  // ── public send ──────────────────────────────────────────────────────
  static _youtubeId(text) {
    const m = /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([\w-]{11})/.exec(text);
    return m ? m[1] : null;
  }

  static _refsYoutube(response, ytId) {
    if (response.includes('googleusercontent.com')) return true;
    return new RegExp(`${ytId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}[^\\s)]*[?&]t=\\d+`).test(response);
  }

  async sendMessage(prompt, { files = null, timeout = null } = {}) {
    if (!prompt || !prompt.trim()) throw new Error('prompt must not be empty');
    const call = () => this._sendInner(prompt, { files, timeout });

    // Video UPLOAD: Gemini hay bật "data analysis tool" (async) → trả "Analyzing" chưa có text → parse fail.
    // Chờ + gửi lại vài lần thường qua được.
    const attempts = files ? 3 : 1;
    let result = null;
    for (let attempt = 0; attempt < attempts; attempt++) {
      try { result = await call(); break; }
      catch (e) {
        if (e instanceof GeminiAuthError) {
          if (attempt === 0 && (await this._refreshCookiesViaPlaywright())) continue;
          throw e;
        }
        if (e instanceof GeminiParseError) {
          const m = /BardErrorInfo[^\d]*\[(\d+)\]/.exec(String(e.message));
          if (m) {
            const code = m[1];
            // Mã đã BIẾT chắc. Không đoán nghĩa cho mã lạ: đoán sai còn tệ hơn nói không biết.
            const hints = { 1076: 'rate limit hoặc nội dung bị chặn — đợi vài phút rồi thử lại' };
            const known = hints[code];

            // Giữ nguyên response gốc trong LOG. Trước đây chỗ này thay message bằng
            // mỗi con số, nên preview 500 ký tự — thứ duy nhất giải thích được mã lạ —
            // bị vứt sạch và không ai chẩn đoán nổi.
            console.error(`[gemini] BardErrorInfo[${code}] · nguyên văn: ${String(e.message).slice(0, 800)}`);

            // Mã lạ mà còn lượt thì THỬ LẠI: nhiều mã chỉ là trục trặc nhất thời của
            // phiên. Riêng 1076 (rate limit) thì thử lại chỉ tổ dính nặng hơn.
            if (!known && attempt < attempts - 1) {
              const wait = 12000 * (attempt + 1);
              this.reset();
              await sleep(wait);
              continue;
            }

            throw new GeminiParseError(known
              ? `Gemini BardErrorInfo[${code}] — ${known}`
              : `Gemini BardErrorInfo[${code}] — Google không nói lý do. Thử theo thứ tự: `
                + 'đăng xuất rồi đăng nhập lại Gemini ở trang Accounts · đợi vài phút rồi chạy lại · '
                + 'dùng LINK YouTube thay vì upload file · thử video ngắn hơn.');
          }
          if (attempt < attempts - 1) {
            const wait = 12000 * (attempt + 1); // 12s, 24s… chờ Gemini xong "Analyzing"
            this.reset();
            await sleep(wait);
            continue;
          }
          throw new GeminiParseError(
            'Gemini chưa trả về nội dung (đang phân tích video). Thử lại, hoặc dùng LINK YouTube thay vì upload, hoặc video ngắn hơn.',
          );
        }
        throw e;
      }
    }
    if (result === null) throw new GeminiParseError('Gemini không trả về nội dung.');

    const ytId = GeminiWeb._youtubeId(prompt);
    if (ytId && !GeminiWeb._refsYoutube(result.content || '', ytId)) {
      await this._refreshCookiesViaPlaywright();
      this.reset();
      result = await call();
    }
    return result;
  }

  async _refreshCookiesViaPlaywright() {
    try {
      const { playwrightRefresh } = await import('./geminiLogin.js');
      const cookieStr = await playwrightRefresh(this.workDir, { headless: true });
      if (!cookieStr) return false;
      const fresh = cookiesFromString(cookieStr);
      if (!Object.keys(fresh).length) return false;
      this.cookies = fresh;
      this._at = null; this._lastRefresh = 0;
      if (this.onCookiesRefreshed) { try { this.onCookiesRefreshed(cookieStr); } catch {} }
      return true;
    } catch { return false; }
  }

  // ── core request ─────────────────────────────────────────────────────
  async _sendInner(prompt, { files = null, timeout = null } = {}) {
    if (!this._at || Date.now() - this._lastRefresh > COOKIE_REFRESH_INTERVAL) {
      await this.refreshTokens();
    }
    const [convId, respId, chId] = [this.conversationId, this.responseId, this.choiceId];

    let fileData = null;
    if (files && files.length) {
      await this._sendBardActivity();
      fileData = [];
      for (const fp of files) {
        const up = await this.uploadFile(fp, timeout);
        fileData.push([[up.uploadRef], up.name]);
      }
      await this._sendBardActivity();
    }

    const messageContent = [prompt, 0, null, fileData, null, null, 0];
    const metadata = [convId, respId, chId, null, null, null, null, null, null, ''];
    const uuidVal = randomUUID().toUpperCase();

    const inner = new Array(69).fill(null);
    inner[0] = messageContent;
    inner[1] = ['en'];
    inner[2] = metadata;
    inner[6] = [1]; inner[7] = 1; inner[10] = 1; inner[11] = 0;
    inner[17] = [[0]]; inner[18] = 0; inner[27] = 1; inner[30] = [4];
    inner[41] = [1]; inner[53] = 0; inner[59] = uuidVal; inner[61] = []; inner[68] = 2;

    const payload = [null, JSON.stringify(inner)];
    this._reqid += 100000;
    const searchParams = { bl: this._bl || 'boq_assistant-bard-web-server', hl: 'en', _reqid: String(this._reqid), rt: 'c' };
    if (this._fSid) searchParams['f.sid'] = this._fSid;

    const form = new URLSearchParams({ 'f.req': JSON.stringify(payload), at: this._at });
    const headers = {
      ...this._baseHeaders(),
      'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      'x-goog-ext-525005358-jspb': `["${uuidVal}",1]`,
      'x-goog-ext-73010989-jspb': '[0]',
      'x-goog-ext-73010990-jspb': '[0]',
    };

    const res = await this._post(ENDPOINT, {
      searchParams, body: form.toString(), headers, timeout: timeout || DEFAULT_TIMEOUT,
    });
    if (res.statusCode === 401 || res.statusCode === 403) {
      this._at = null; this._lastRefresh = 0;
      throw new GeminiAuthError(`Gemini auth failed (HTTP ${res.statusCode}) — cookie hết hạn.`);
    }
    const result = this._parseResponse(res.body || '');
    this.conversationId = result.conversationId || convId;
    this.responseId = result.responseId || respId;
    this.choiceId = result.choiceId || chId;
    return result;
  }

  async _sendBardActivity() {
    const searchParams = { rpcids: 'ESY5D', hl: 'en', _reqid: String(this._reqid), rt: 'c', 'source-path': '/app' };
    this._reqid += 100000;
    if (this._bl) searchParams.bl = this._bl;
    if (this._fSid) searchParams['f.sid'] = this._fSid;
    const form = new URLSearchParams({
      'f.req': JSON.stringify([[['ESY5D', '[[["bard_activity_enabled"]]]', null, 'generic']]]),
      at: this._at,
    });
    const headers = {
      ...this._baseHeaders(),
      'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      'x-goog-ext-525001261-jspb': '[1,null,null,null,null,null,null,null,[4]]',
      'x-goog-ext-73010989-jspb': '[0]',
    };
    try {
      await this._post('https://gemini.google.com/_/BardChatUi/data/batchexecute', {
        searchParams, body: form.toString(), headers, timeout: 30000,
      });
    } catch {}
  }

  // ── upload (resumable protocol, fingerprint-friendly) ─────────────────
  async uploadFile(filePath, timeout) {
    const size = statSync(filePath).size;
    const mime = guessMime(filePath);
    const uploadTimeout = timeout || Math.max(DEFAULT_TIMEOUT, 600000);
    const pushId = process.env.GEMINI_UPLOAD_PUSH_ID || 'feeds/mcudyrk2a4khkz';
    const base = {
      ...this._baseHeaders(),
      'Push-ID': pushId,
      'X-Tenant-Id': 'bard-storage',
      Referer: 'https://gemini.google.com/',
    };
    // 1) start
    const initRes = await this._post(UPLOAD_ENDPOINT, {
      headers: {
        ...base,
        'X-Goog-Upload-Protocol': 'resumable',
        'X-Goog-Upload-Command': 'start',
        'X-Goog-Upload-Header-Content-Type': mime,
        'X-Goog-Upload-Header-Content-Length': String(size),
      },
      timeout: 30000, followRedirect: false,
    });
    const uploadUrl = initRes.headers['x-goog-upload-url'] || initRes.headers.location;
    if (!uploadUrl) throw new GeminiParseError('Gemini upload không trả về X-Goog-Upload-URL.');
    // 2) upload + finalize
    const bytes = readFileSync(filePath);
    const upRes = await this._post(uploadUrl, {
      headers: {
        ...base,
        'X-Goog-Upload-Command': 'upload, finalize',
        'X-Goog-Upload-Offset': '0',
        'Content-Type': 'application/octet-stream',
      },
      body: bytes, timeout: uploadTimeout,
    });
    const ref = (upRes.body || '').trim();
    if (!ref) throw new GeminiParseError('Gemini upload trả về ref rỗng.');
    return { uploadRef: ref, name: basename(filePath), mime, size };
  }

  // ── response parsing (JSPB / XSSI) ────────────────────────────────────
  _parseResponse(text) {
    const parsedPayloads = [];
    for (const obj of this._decodeObjects(text)) {
      for (const cand of this._walk(obj)) {
        if (typeof cand === 'string' && looksLikeJson(cand)) {
          try { parsedPayloads.push(JSON.parse(cand)); } catch {}
        }
      }
    }
    if (!parsedPayloads.length) {
      for (const line of text.split(/\r?\n/)) {
        const s = line.trim();
        if (looksLikeJson(s)) { try { parsedPayloads.push(JSON.parse(s)); } catch {} }
      }
    }

    let content = '', conversationId = '', responseId = '', choiceId = '', choices = [];
    for (const payload of parsedPayloads) {
      const known = this._parseKnownBardPayload(payload);
      if (known.content && known.content.length >= content.length) {
        content = known.content;
        conversationId = known.conversationId || conversationId;
        responseId = known.responseId || responseId;
        choiceId = known.choiceId || choiceId;
        choices = known.choices || choices;
      }
    }
    if (!content) {
      const strings = [];
      for (const payload of parsedPayloads) for (const s of this._candidateStrings(payload)) if (this._isAssistantText(s)) strings.push(s);
      if (strings.length) content = strings.reduce((a, b) => (b.length > a.length ? b : a), '');
    }
    if (!content) {
      throw new GeminiParseError(`Không parse được reply Gemini. Preview: ${text.slice(0, 500).replace(/\n/g, '\\n')}`);
    }
    return { content, conversationId, responseId, choiceId, choices };
  }

  _parseKnownBardPayload(payload) {
    const result = {};
    if (!Array.isArray(payload)) return result;
    try {
      const ids = payload[1];
      if (Array.isArray(ids)) {
        result.conversationId = ids.length > 0 ? String(ids[0] || '') : '';
        result.responseId = ids.length > 1 ? String(ids[1] || '') : '';
        result.choiceId = ids.length > 2 ? String(ids[2] || '') : '';
      }
    } catch {}
    try {
      const candidates = payload[4];
      if (Array.isArray(candidates)) {
        const choices = [];
        for (const item of candidates) {
          if (!Array.isArray(item) || item.length < 2) continue;
          const cid = String(item[0] || '');
          const txt = this._stringFromCandidate(item[1]);
          if (txt) choices.push({ id: cid, content: txt });
        }
        if (choices.length) {
          result.choices = choices;
          result.choiceId = choices[0].id;
          result.content = choices[0].content;
        }
      }
    } catch {}
    return result;
  }

  *_decodeObjects(text) {
    const cleaned = text.replace(/\)\]\}'/g, '');
    for (const line of cleaned.split(/\r?\n/)) {
      const s = line.trim();
      if (!s || /^\d+$/.test(s) || !looksLikeJson(s)) continue;
      try { yield JSON.parse(s); } catch {}
    }
  }

  *_candidateStrings(value) {
    for (const item of this._walk(value)) {
      if (typeof item === 'string') { const s = item.trim(); if (s) yield s; }
    }
  }

  *_walk(value) {
    yield value;
    if (value && typeof value === 'object') {
      if (Array.isArray(value)) { for (const c of value) yield* this._walk(c); }
      else { for (const c of Object.values(value)) yield* this._walk(c); }
    }
  }

  _stringFromCandidate(value) {
    if (typeof value === 'string') return value.trim();
    if (Array.isArray(value)) return value.filter((v) => typeof v === 'string' && v.trim()).map((v) => v.trim()).join('\n').trim();
    return '';
  }

  _isAssistantText(value) {
    if (value.length < 2) return false;
    if (/^(boq_|wrb\.fr|assistant\.lamda|https:\/\/|http:\/\/|\/\/|www\.)/.test(value)) return false;
    if (value.includes('://')) return false;
    if (/^[\w.-]{20,}$/.test(value)) return false;
    if ('{['.includes(value.trimStart()[0])) return true;
    return /\s/.test(value);
  }
}

function looksLikeJson(v) { return !!v && (v[0] === '[' || v[0] === '{'); }

function guessMime(path) {
  const ext = path.toLowerCase().split('.').pop();
  const map = { mp4: 'video/mp4', mov: 'video/quicktime', webm: 'video/webm', mkv: 'video/x-matroska', avi: 'video/x-msvideo', m4v: 'video/x-m4v', jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png' };
  return map[ext] || 'application/octet-stream';
}
