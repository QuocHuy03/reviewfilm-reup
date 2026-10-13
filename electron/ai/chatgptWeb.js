// Client chatgpt.com (reverse) — bản Node, port từ gpt_plus.py (đã gỡ ở 7da88cd, lấy lại từ git).
//
// Đặt cạnh claude/ và gemini/ vì cùng một kiểu: dùng TÀI KHOẢN CỦA CHÍNH NGƯỜI DÙNG, gọi đúng
// endpoint mà web app gọi. Khác một điểm lớn, và đó là toàn bộ độ khó của file này:
//
//   claude.ai  — chỉ cần cookie `sessionKey`, gọi thẳng bằng fetch của Node là xong.
//   chatgpt.com — trước mỗi lượt chat phải qua hai cửa sentinel (prepare → finalize), giải một bài
//                 băm và một thử thách turnstile. Thiếu token là 403.
//
// ── VÌ SAO GỌI TRONG TRANG, KHÔNG GỌI BẰNG fetch CỦA NODE ────────────────────────────────────────
// Bản Python cũ đi bằng `curl_cffi` với `impersonate` — tức GIẢ VÂN TAY TLS của Chrome. Không phải
// làm màu: Cloudflare của chatgpt.com nhìn vân tay TLS/JA3, mà vân tay của Node khác Chrome nên gọi
// thẳng từ Node rất dễ ăn 403 ngay ở bước đầu, trước cả khi tới sentinel.
//
// Ở đây chọn đường khác, rẻ hơn và bền hơn: mở CHÍNH Chrome (Playwright, profile giữ lại như
// claudeLogin/geminiLogin đang làm) rồi chạy `fetch` NGAY TRONG TRANG chatgpt.com. Được cả ba thứ
// miễn phí: vân tay TLS thật, cookie tự đính kèm, và cùng origin nên không vướng CORS.
//
// ⚠️ Đường reverse này bám theo BUNDLE của chatgpt.com. Bundle xoay thì phải cập nhật solver.js và
// chatgptProof.js. Đây là lý do dự án từng bỏ nó để sang 9router — giữ 9router làm đường lùi.

import { createRequire } from 'module';
import { join } from 'path';
import { mkdirSync } from 'fs';
import { randomUUID } from 'crypto';
import { buildProofToken, solvePow, verifyPow, turnstileFailure } from './chatgptProof.js';

const _require = createRequire(import.meta.url);

const BASE     = 'https://chatgpt.com';
const PREPARE  = '/backend-api/sentinel/chat-requirements/prepare';
const FINALIZE = '/backend-api/sentinel/chat-requirements/finalize';
const CHAT     = '/backend-api/f/conversation';

export class ChatGPTError extends Error {
  constructor(message, kind = 'unknown', status = 0) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

/** Phân loại lỗi để tầng trên biết phải làm gì, thay vì ném nguyên mã HTTP cho người dùng đọc. */
export function classifyChatGPTError(status, body = '') {
  const b = String(body).slice(0, 400);
  if (status === 401) {
    return { kind: 'auth', msg: 'Phiên chatgpt.com hết hạn — đăng nhập lại ở trang Accounts.' };
  }
  if (status === 403) {
    // Phân biệt HAI loại 403 rất khác nhau, vì cách sửa ngược nhau:
    //   · Cloudflare chặn  — thân phản hồi là TRANG HTML (có <html>, "Just a moment", "cf-").
    //     Cách sửa: mở trình duyệt lên vượt thử thách, hoặc chờ.
    //   · chatgpt.com từ chối theo LOGIC (token sentinel sai/hết hạn, tài khoản bị hạn chế) — thân là
    //     JSON. Cách sửa: đăng nhập lại, hoặc xem lại proof/PoW.
    // Gộp làm một là người dùng đi mở trình duyệt trong khi lỗi nằm ở token, và ngược lại.
    const looksCloudflare = /<html|just a moment|cf-browser-verification|cloudflare/i.test(b);
    return looksCloudflare
      ? { kind: 'blocked', msg: 'Cloudflare chặn — mở trình duyệt đăng nhập chatgpt.com một lần cho qua thử thách, rồi thử lại.' }
      : { kind: 'forbidden', msg: 'chatgpt.com từ chối yêu cầu (không phải Cloudflare). Thường là token sentinel hỏng hoặc tài khoản bị hạn chế.' };
  }
  if (status === 429) {
    return { kind: 'ratelimit', msg: 'chatgpt.com báo quá nhiều yêu cầu — chờ rồi thử lại.' };
  }
  if (status >= 500) return { kind: 'server', msg: `chatgpt.com lỗi máy chủ (${status}).` };
  return { kind: 'unknown', msg: `chatgpt.com trả HTTP ${status}: ${b}` };
}

// ── Giải mã luồng SSE ────────────────────────────────────────────────────────
//
// chatgpt.com trả về một chuỗi delta kiểu JSON-patch: mỗi dòng `data:` có thể mang `p` (đường dẫn),
// `o` (phép toán) và `v` (giá trị) — và khi thiếu `p`/`o` thì DÙNG LẠI cái của dòng trước. Bỏ qua
// luật "dùng lại" đó là mất phần lớn nội dung, vì phần thân câu trả lời toàn là dòng chỉ có `v`.

/** Tách từng sự kiện SSE thành object JSON. */
function* iterSse(text) {
  let buf = [];
  const flush = () => {
    if (!buf.length) return null;
    const p = buf.join('\n').trim();
    buf = [];
    if (!p || p === '[DONE]') return null;
    try { return JSON.parse(p); } catch { return null; }
  };
  for (const raw of String(text ?? '').split(/\r?\n/)) {
    if (raw === '') {
      const ev = flush();
      if (ev) yield ev;
    } else if (raw.startsWith(':') || raw.startsWith('event:')) {
      continue;
    } else if (raw.startsWith('data:')) {
      buf.push(raw.slice(5).replace(/^\s+/, ''));
    } else {
      buf.push(raw);
    }
  }
  const ev = flush();
  if (ev) yield ev;
}

const CONTROL_TYPES = new Set([
  'title_generation', 'moderation_response', 'conversation_detail_metadata', 'message_stream_complete',
]);

/**
 * Gom nội dung câu trả lời từ luồng SSE.
 *
 * Chỉ lấy đúng thứ app cần: chữ của assistant, conversationId, messageId, và cờ kết thúc. Bản Python
 * còn gom reasoning/citations/tool_calls — bỏ, vì không nơi nào trong app dùng tới, mà giữ thì thành
 * ba trăm dòng không ai kiểm.
 */
export function decodeStream(text) {
  const out = {
    conversationId: null, messageId: null, model: null,
    finish: null, endTurn: null, streamComplete: false,
    message: '', error: null,
  };
  let lastPath = '', lastOp = 'append';
  let emitted = 0;   // số ký tự đã lấy — để lượt "cả cụm" không nhân đôi phần đã có

  const takeAppend = (op, path, v) => {
    if (typeof v === 'string' && op === 'append' && path.includes('/parts/0') && v) {
      out.message += v;
      emitted += v.length;
    }
  };

  for (const ev of iterSse(text)) {
    if (!ev || typeof ev !== 'object') continue;
    if (ev.conversation_id) out.conversationId = ev.conversation_id;
    if (ev.error) out.error = ev.error;

    const etype = ev.type;
    if (etype === 'message_stream_complete') { out.streamComplete = true; continue; }
    if (CONTROL_TYPES.has(etype)) continue;

    // Gói "cả bản tin" (không có v/o/p): lấy metadata và phần chữ còn thiếu so với những gì đã gom.
    if (ev.message && ev.v === undefined && ev.o === undefined && ev.p === undefined) {
      const msg = ev.message;
      if (msg?.id) out.messageId = msg.id;
      if (msg?.metadata?.model_slug) out.model = msg.metadata.model_slug;
      if (msg?.metadata?.finish_details?.type) out.finish = msg.metadata.finish_details.type;
      if (msg?.end_turn !== undefined) out.endTurn = msg.end_turn;
      if (msg?.author?.role === 'assistant') {
        const parts = (msg.content?.parts ?? []).filter((x) => typeof x === 'string').join('');
        if (parts.length > emitted) { out.message += parts.slice(emitted); emitted = parts.length; }
      }
      continue;
    }
    if (ev.v === undefined && ev.o === undefined && ev.p === undefined) continue;

    // LUẬT "DÙNG LẠI": thiếu p/o thì lấy của dòng trước. Bỏ luật này là mất phần thân câu trả lời.
    if (ev.p !== undefined) lastPath = ev.p;
    if (ev.o !== undefined) lastOp = ev.o;
    const op = lastOp || 'append';
    const v = ev.v;

    if (op === 'patch' && Array.isArray(v)) {
      for (const sub of v) {
        if (sub && typeof sub === 'object') takeAppend(sub.o ?? 'append', sub.p ?? '', sub.v);
      }
    } else if (typeof v === 'string') {
      takeAppend(op, lastPath, v);
    } else if (v && typeof v === 'object') {
      const msg = v.message;
      if (msg?.author?.role === 'assistant') {
        const parts = (msg.content?.parts ?? []).filter((x) => typeof x === 'string').join('');
        if (parts.length > emitted) { out.message += parts.slice(emitted); emitted = parts.length; }
      }
      if (v.conversation_id) out.conversationId = v.conversation_id;
    }
  }
  return out;
}

// ── Thân yêu cầu chat ────────────────────────────────────────────────────────
export function chatBody(message, model, conversationId = null, parentMessageId = null) {
  const body = {
    action: 'next',
    messages: [{
      id: randomUUID(), author: { role: 'user' }, create_time: Date.now() / 1000,
      content: { content_type: 'text', parts: [String(message ?? '')] },
      metadata: {
        developer_mode_connector_ids: [], selected_github_repos: [],
        selected_all_github_repos: false, system_hints: [],
        serialization_metadata: { custom_symbol_offsets: [] },
      },
    }],
    parent_message_id: parentMessageId || 'client-created-root',
    model,
    client_prepare_state: 'success',
    timezone_offset_min: -420, timezone: 'Asia/Bangkok',
    conversation_mode: { kind: 'primary_assistant' },
    enable_message_followups: true, system_hints: [],
    supports_buffering: true, supported_encodings: ['v1'], supported_tools: [],
    client_contextual_info: {
      is_dark_mode: true, time_since_loaded: 7, page_height: 945, page_width: 1106,
      pixel_ratio: 1, screen_height: 1080, screen_width: 1920, app_name: 'chatgpt.com',
    },
    paragen_cot_summary_display_override: 'allow',
    force_parallel_switch: 'auto', thinking_effort: 'standard',
  };
  if (conversationId) body.conversation_id = conversationId;
  return body;
}

// ── Lớp mạng: fetch NGAY TRONG TRANG chatgpt.com ─────────────────────────────
export class ChatGPTWeb {
  /**
   * @param {string} workDir thư mục chứa profile Chrome (giữ giữa các lần chạy, như claudeLogin)
   * @param {{headless?: boolean, model?: string}} opts
   */
  constructor(workDir, { headless = true, model = 'gpt-5-5-thinking' } = {}) {
    this.workDir = workDir || process.cwd();
    this.headless = headless;
    this.model = model;
    this._ctx = null;
    this._page = null;
    this._bootstrap = null;
    this._bootstrapAt = 0;
  }

  async _ensurePage() {
    if (this._page && !this._page.isClosed()) return this._page;
    const { chromium } = _require('playwright');
    const profileDir = join(this.workDir, '.chatgpt-chrome-data');
    mkdirSync(profileDir, { recursive: true });
    // Cùng cấu hình với claudeLogin: profile BÌNH THƯỜNG, không cờ tự động hoá — trang đăng nhập
    // và Cloudflare đối xử với profile "sạch" khác hẳn với profile bị đánh dấu automation.
    // KHÔNG dùng headless thật, kể cả khi gọi là "chạy ngầm".
    //
    // Cloudflare của chatgpt.com soi headless gắt hơn hẳn: cùng một profile, đăng nhập bằng Chrome
    // HIỆN thì qua, chạy lại bằng headless thì 403 — đúng triệu chứng "đăng nhập được nhưng Kiểm tra
    // bị từ chối". Ngoài ra profile được tạo ra trong phiên có giao diện; mở lại bằng headless là đổi
    // hàng loạt tín hiệu (kích thước màn hình, WebGL, danh sách plugin).
    //
    // Nên chạy Chrome THẬT nhưng đẩy cửa sổ ra ngoài màn hình: vân tay y như người dùng bình thường,
    // mà không có gì nhảy ra che việc của họ.
    const hidden = this.headless;
    this._ctx = await chromium.launchPersistentContext(profileDir, {
      headless: false,
      channel: 'chrome',
      args: [
        '--disable-blink-features=AutomationControlled',
        ...(hidden ? ['--window-position=-32000,-32000', '--window-size=1280,900'] : []),
      ],
      ignoreDefaultArgs: ['--enable-automation'],
      viewport: { width: 1280, height: 900 },
    });
    this._page = this._ctx.pages()[0] || await this._ctx.newPage();
    if (!this._page.url().startsWith(BASE)) {
      await this._page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    }
    return this._page;
  }

  /**
   * Nhả cookie + User-Agent của phiên hiện tại, để đường HTTP THUẦN (chatgptHttp) dùng lại.
   *
   * Đây là cả lý do tồn tại của trình duyệt trong luồng này: nó vượt Cloudflare một lần lúc đăng nhập
   * và lấy được `cf_clearance`; xong rồi thì mọi lượt chat sau chỉ cần cookie, không phải dựng lại cả
   * một Chrome cho từng lượt.
   *
   */
  async credentials() {
    const page = await this._ensurePage();
    const userAgent = await page.evaluate(() => navigator.userAgent);
    // cookies(url) chỉ trả về cookie SẼ ĐƯỢC GỬI tới url đó — nên không dính cookie Google/Auth0 mà
    // profile còn giữ từ lượt đăng nhập bằng tài khoản ngoài.
    const all = await this._ctx.cookies(BASE);
    const cookies = all.map((c) => `${c.name}=${c.value}`).join('; ');
    return { cookies, userAgent };
  }

  async close() {
    try { await this._ctx?.close(); } catch { /* đóng hỏng không đáng làm chết lượt gọi */ }
    this._ctx = null; this._page = null;
  }

  /**
   * Gọi một endpoint của chatgpt.com TỪ TRONG TRANG — mang cookie và vân tay TLS thật.
   *
   * `label` là tên bước, để câu lỗi nói được CHỖ NÀO hỏng. Lượt chat đi qua bốn lời gọi khác nhau
   * (phiên → prepare → finalize → conversation); báo "chatgpt.com từ chối" trống không thì phải đoán
   * cả bốn, mà cách sửa mỗi chỗ một khác.
   */
  async _api(path, { method = 'GET', headers = {}, body = null, label = path } = {}) {
    const page = await this._ensurePage();
    const r = await page.evaluate(async ({ path, method, headers, body }) => {
      const res = await fetch(path, { method, headers, body, credentials: 'include' });
      return { status: res.status, text: await res.text() };
    }, { path, method, headers, body });
    // In MỌI lượt gọi ra log: bốn bước nối nhau, biết bước nào ra mã gì là lần được ngay chỗ hỏng.
    // Không in thân phản hồi ở đây — nó có thể chứa dữ liệu tài khoản; chỉ nơi báo lỗi mới trích một đoạn.
    console.log(`[chatgpt] ${label} → HTTP ${r.status} (${r.text.length} ký tự)`);
    return { ...r, label };
  }

  /** Token phiên — web app đọc từ /api/auth/session, hết hạn thì phải đăng nhập lại. */
  async accessToken() {
    const r = await this._api('/api/auth/session', { headers: { Accept: 'application/json' }, label: 'lấy phiên' });
    if (r.status !== 200) {
      const c = classifyChatGPTError(r.status, r.text);
      throw new ChatGPTError(`[lấy phiên] ${c.msg} · ${r.text.slice(0, 200)}`, c.kind, r.status);
    }
    let token = null;
    try { token = JSON.parse(r.text)?.accessToken || null; } catch { /* rơi xuống câu lỗi dưới */ }
    if (!token) throw new ChatGPTError('Chưa đăng nhập chatgpt.com (không có accessToken).', 'auth', r.status);
    return token;
  }

  /**
   * `client-bootstrap` — solver dùng để dựng môi trường trình duyệt giả. Nhớ 5 phút.
   *
   * Ba đường, thử lần lượt, vì mỗi đường hụt theo một kiểu khác nhau:
   *   1. Đọc thẻ trong DOM — nhanh nhất, nhưng chatgpt.com là SPA: React hydrate xong thường DỌN
   *      luôn thẻ đó, và nếu trang đã điều hướng sang /c/<id> thì càng không còn. Đây đúng là lỗi
   *      "Không thấy client-bootstrap trong trang" gặp trên máy người dùng.
   *   2. TẢI LẠI HTML gốc bằng fetch('/') rồi bóc bằng regex — chính cách bản Python cũ làm. HTML
   *      server trả về luôn có thẻ đó, không phụ thuộc DOM đã bị React đụng vào hay chưa.
   *   3. Chịu thua thì trả {} và CẢNH BÁO, KHÔNG ném lỗi. Bản Python cũng gửi `bootstrap || {}` cho
   *      solver — thiếu nó có thể vẫn giải được. Ném lỗi ở đây là giết cả lượt chat vì một thứ
   *      chưa chắc bắt buộc.
   */
  async bootstrap() {
    if (this._bootstrap && Date.now() - this._bootstrapAt < 300000) return this._bootstrap;
    const page = await this._ensurePage();

    let json = await page.evaluate(() => {
      const el = document.querySelector('script#client-bootstrap');
      return el ? el.textContent : null;
    });

    if (!json) {
      json = await page.evaluate(async () => {
        const res = await fetch('/', { credentials: 'include', headers: { Accept: 'text/html' } });
        const html = await res.text();
        const m = html.match(/<script[^>]*id="client-bootstrap"[^>]*>([\s\S]*?)<\/script>/);
        return m ? m[1] : null;
      });
      if (json) console.log('[chatgpt] client-bootstrap không có trong DOM — lấy được từ HTML gốc.');
    }

    if (!json) {
      console.warn('[chatgpt] KHÔNG thấy client-bootstrap ở cả DOM lẫn HTML gốc — chạy tiếp với {}. '
        + 'Nếu sentinel từ chối thì đây là chỗ đáng ngờ đầu tiên (chatgpt.com đổi bundle).');
      this._bootstrap = {};
      this._bootstrapAt = Date.now();
      return this._bootstrap;
    }

    try {
      this._bootstrap = JSON.parse(json);
    } catch (e) {
      console.warn(`[chatgpt] client-bootstrap không parse được (${e.message}) — chạy tiếp với {}.`);
      this._bootstrap = {};
    }
    this._bootstrapAt = Date.now();
    return this._bootstrap;
  }

  /**
   * Gói cước của tài khoản (Plus / Free / Pro…).
   *
   * `/api/auth/session` KHÔNG có thông tin này — phải hỏi endpoint account. Trả về chuỗi ngắn để
   * hiện thẳng lên UI; hỏi hụt thì trả '' chứ không ném: không biết gói cước là chuyện nhỏ, chặn
   * đăng nhập vì nó mới là chuyện lớn.
   */
  async plan() {
    try {
      // PHẢI có Bearer. Chỉ cookie thôi thì chatgpt.com trả về hồ sơ KHÁCH VÃNG LAI, gói cước đọc ra
      // đúng chữ "Guest" — nhãn sai chình ình trên UI của một tài khoản đã đăng nhập hẳn hoi.
      const r = await this._api('/backend-api/accounts/check/v4-2023-04-27', {
        headers: { Accept: 'application/json', Authorization: `Bearer ${await this.accessToken()}` },
      });
      if (r.status !== 200) return '';
      const j = JSON.parse(r.text || '{}');
      const accounts = j?.accounts || {};
      const acc = accounts.default || Object.values(accounts)[0] || {};
      const raw = acc?.entitlement?.subscription_plan || acc?.entitlement?.plan_type || '';
      // Trường vắng mặt thì THÔI, đừng đoán: `String(null)` ra "null" rồi chuẩn hoá thành "Null" —
      // một nhãn vô nghĩa hiện chình ình trên UI.
      if (typeof raw !== 'string' || !raw.trim()) return '';
      // "chatgptplusplan" → "Plus", "chatgptfreeplan" → "Free", "chatgptproplan" → "Pro"…
      const m = /chatgpt(\w+?)plan/i.exec(raw);
      const name = m ? m[1] : raw.replace(/chatgpt|plan/gi, '').trim();
      return name ? name.charAt(0).toUpperCase() + name.slice(1).toLowerCase() : '';
    } catch {
      return '';
    }
  }

  /** Hai cửa sentinel: prepare (nhận đề) → giải → finalize (nhận token cho lượt chat). */
  async sentinel(baseHeaders, userAgent, clientVersion) {
    const proofToken = buildProofToken(userAgent, clientVersion);
    const h1 = { ...baseHeaders, 'x-openai-target-path': PREPARE, 'x-openai-target-route': PREPARE };
    const r1 = await this._api(PREPARE, { method: 'POST', headers: h1, body: JSON.stringify({ p: proofToken }), label: 'sentinel/prepare' });
    if (r1.status !== 200) {
      const c = classifyChatGPTError(r1.status, r1.text);
      throw new ChatGPTError(`[sentinel/prepare] ${c.msg} · ${r1.text.slice(0, 200)}`, c.kind, r1.status);
    }
    const prep = JSON.parse(r1.text);

    const seed = prep?.proofofwork?.seed;
    const difficulty = prep?.proofofwork?.difficulty;
    const powAnswer = solvePow(seed, difficulty, userAgent);
    // Tự soát trước khi gửi: giải hụt thì biết NGAY ở đây, thay vì đọc 403 rồi đoán tại đâu.
    if (!verifyPow(seed, difficulty, powAnswer)) {
      throw new ChatGPTError('Không giải được bài băm sentinel (proof-of-work) — thử lại hoặc đăng nhập lại.', 'pow', 0);
    }

    const { setupEnv, t_n } = _require('./solver.cjs');
    setupEnv({ bootstrap: await this.bootstrap(), userAgent });
    const tsAnswer = await t_n(proofToken, prep?.turnstile?.dx);
    // Soát TRƯỚC khi gửi: t_n hỏng thì vẫn resolve bằng rác, gửi lên chỉ đổi lấy một cái 403 trống không.
    const tsHong = turnstileFailure(tsAnswer);
    if (tsHong) throw new ChatGPTError(`Giải turnstile thất bại — ${tsHong}`, 'sentinel', 0);

    const h2 = { ...baseHeaders, 'x-openai-target-path': FINALIZE, 'x-openai-target-route': FINALIZE };
    const r2 = await this._api(FINALIZE, {
      method: 'POST', headers: h2,
      body: JSON.stringify({ prepare_token: prep.prepare_token, proofofwork: powAnswer, turnstile: tsAnswer }),
      label: 'sentinel/finalize',
    });
    if (r2.status !== 200) {
      const c = classifyChatGPTError(r2.status, r2.text);
      throw new ChatGPTError(`[sentinel/finalize] ${c.msg} · ${r2.text.slice(0, 200)}`, c.kind, r2.status);
    }
    const finalToken = JSON.parse(r2.text)?.token;
    if (!finalToken) throw new ChatGPTError('finalize: không có token', 'sentinel', r2.status);
    return { powAnswer, tsAnswer, finalToken };
  }

  /**
   * Gửi một lượt chat.
   * @returns {Promise<{message:string, convId:string|null, messageId:string|null, finish:string|null}>}
   */
  async chat(message, { convId = null, parentMessageId = null, model = null } = {}) {
    const page = await this._ensurePage();
    const userAgent = await page.evaluate(() => navigator.userAgent);
    const boot = await this.bootstrap();
    const clientVersion = boot?.clientVersion || boot?.client_version || '';
    const clientBuild = String(boot?.buildNumber || boot?.build_number || '');
    const accessToken = await this.accessToken();
    const sessionId = randomUUID();
    const deviceId = randomUUID();

    const baseHeaders = {
      Accept: '*/*', 'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
      'OAI-Device-Id': deviceId, 'OAI-Language': 'en-US',
      'oai-client-build-number': clientBuild, 'oai-client-version': clientVersion,
      'oai-session-id': sessionId,
    };

    const { powAnswer, tsAnswer, finalToken } = await this.sentinel(baseHeaders, userAgent, clientVersion);

    const r = await this._api(CHAT, {
      method: 'POST',
      headers: {
        ...baseHeaders,
        Accept: 'text/event-stream',
        'openai-sentinel-chat-requirements-token': finalToken,
        'openai-sentinel-proof-token': powAnswer,
        'openai-sentinel-turnstile-token': tsAnswer,
        'x-oai-turn-trace-id': randomUUID(),
        'x-openai-target-path': CHAT, 'x-openai-target-route': CHAT,
      },
      body: JSON.stringify(chatBody(message, model || this.model, convId, parentMessageId)),
      label: 'gửi chat',
    });
    if (r.status !== 200) {
      const c = classifyChatGPTError(r.status, r.text);
      throw new ChatGPTError(`[gửi chat] ${c.msg} · ${r.text.slice(0, 300)}`, c.kind, r.status);
    }

    const dec = decodeStream(r.text);
    if (!dec.message.trim() && dec.error) {
      throw new ChatGPTError(`chatgpt.com báo lỗi: ${JSON.stringify(dec.error).slice(0, 300)}`, 'stream', 200);
    }
    return {
      message: dec.message,
      convId: dec.conversationId,
      messageId: dec.messageId,
      finish: dec.finish,
      model: dec.model,
    };
  }
}
