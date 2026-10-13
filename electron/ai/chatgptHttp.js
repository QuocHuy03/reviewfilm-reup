// Client chatgpt.com bằng HTTP THUẦN — không lái trình duyệt.
//
// Đây mới là "reverse" đúng nghĩa, và là cách bản Python cũ (gpt_plus.py) vẫn làm: lấy cookie MỘT
// LẦN lúc đăng nhập, rồi mọi lượt chat sau đó chỉ là request HTTP bình thường.
//
// ── VÌ SAO KHÔNG LÁI TRÌNH DUYỆT CHO TỪNG LƯỢT ──────────────────────────────────────────────────
// Bản trước mở Chrome rồi `fetch` ngay trong trang. Chạy được, nhưng mỗi lượt chat phải dựng cả một
// trình duyệt: chậm vài giây, ngốn vài trăm MB, và profile bị khoá nên hai lượt không chạy song song
// được. Với pipeline gọi hàng chục lượt thì hoàn toàn không dùng nổi.
//
// ── ĐIỀU DUY NHẤT PHẢI CẨN THẬN: VÂN TAY TLS ────────────────────────────────────────────────────
// Cloudflare có nhìn vân tay TLS, và vân tay của Node khác Chrome. Bản Python giải bằng `curl_cffi`
// (giả vân tay). Ở Node không có món tương đương gọn gàng, nên ở đây đi đường khác: lấy CẢ
// `cf_clearance` từ phiên trình duyệt lúc đăng nhập và gửi kèm — đó chính là tấm vé Cloudflare cấp
// sau khi đã vượt thử thách.
//
// Không bảo đảm 100%: Cloudflare có thể buộc phải khớp cả vân tay TLS. Nên nơi gọi phải giữ đường lùi
// sang ChatGPTWeb (trình duyệt) khi đường này bị chặn — chatgptClient.js làm đúng việc đó.

import { randomUUID } from 'crypto';
import { buildProofToken, solvePow, verifyPow, turnstileFailure } from './chatgptProof.js';
import { ChatGPTError, classifyChatGPTError, decodeStream, chatBody } from './chatgptWeb.js';

const BASE     = 'https://chatgpt.com';
const PREPARE  = '/backend-api/sentinel/chat-requirements/prepare';
const FINALIZE = '/backend-api/sentinel/chat-requirements/finalize';
const CHAT     = '/backend-api/f/conversation';

/** Header chung của mọi lượt gọi — chép đúng bộ mà web app gửi (xem gpt_plus._base_headers). */
function baseHeaders({ cookies, userAgent, deviceId, clientBuild, clientVersion, sessionId }) {
  return {
    Accept: '*/*',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
    'Content-Type': 'application/json',
    Cookie: cookies,
    'User-Agent': userAgent,
    Origin: BASE,
    Referer: `${BASE}/`,
    'OAI-Device-Id': deviceId,
    'OAI-Language': 'en-US',
    'oai-client-build-number': clientBuild || '',
    'oai-client-version': clientVersion || '',
    'oai-session-id': sessionId,
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
  };
}

export class ChatGPTHttp {
  /**
   * @param {{cookies: string, userAgent: string, model?: string}} cred cookie + UA lấy lúc đăng nhập
   */
  constructor({ cookies, userAgent, model = 'gpt-5-5-thinking' }) {
    this.cookies = String(cookies || '');
    this.userAgent = String(userAgent || '');
    this.model = model;
    this.deviceId = randomUUID();
    this._bootstrap = null;
    this._bootstrapAt = 0;
    this._token = '';
    this._tokenAt = 0;
  }

  get usable() {
    return !!this.cookies.trim() && !!this.userAgent.trim();
  }

  async _req(path, { method = 'GET', headers = {}, body = null, label = path } = {}) {
    const res = await fetch(BASE + path, { method, headers, body, redirect: 'manual' });
    const text = await res.text();
    console.log(`[chatgpt-http] ${label} → HTTP ${res.status} (${text.length} ký tự)`);
    if (res.status >= 400) {
      const c = classifyChatGPTError(res.status, text);
      throw new ChatGPTError(`[${label}] ${c.msg} · ${text.slice(0, 200)}`, c.kind, res.status);
    }
    return { status: res.status, text };
  }

  /** Token phiên. Nhớ 10 phút — mỗi lượt chat mà hỏi lại là thêm một lần chạm Cloudflare vô ích. */
  async accessToken() {
    if (this._token && Date.now() - this._tokenAt < 600000) return this._token;
    const r = await this._req('/api/auth/session', {
      headers: { Cookie: this.cookies, 'User-Agent': this.userAgent, Accept: 'application/json' },
      label: 'lấy phiên',
    });
    const token = JSON.parse(r.text || '{}')?.accessToken;
    if (!token) throw new ChatGPTError('Cookie chatgpt.com hết hạn — đăng nhập lại ở trang Accounts.', 'auth', 200);
    this._token = token;
    this._tokenAt = Date.now();
    return token;
  }

  /** `client-bootstrap` bóc từ HTML trang chủ — solver cần. Thiếu thì chạy tiếp với {}. */
  async bootstrap() {
    if (this._bootstrap && Date.now() - this._bootstrapAt < 300000) return this._bootstrap;
    try {
      const r = await this._req('/', {
        headers: { Cookie: this.cookies, 'User-Agent': this.userAgent, Accept: 'text/html' },
        label: 'tải trang chủ',
      });
      const m = r.text.match(/<script[^>]*id="client-bootstrap"[^>]*>([\s\S]*?)<\/script>/);
      this._bootstrap = m ? JSON.parse(m[1]) : {};
      if (!m) console.warn('[chatgpt-http] không thấy client-bootstrap trong HTML — chạy tiếp với {}.');
    } catch (e) {
      // Trang chủ hỏng không đáng làm chết lượt chat: solver vẫn nhận {} như bản Python.
      console.warn(`[chatgpt-http] không tải được trang chủ (${e.message}) — chạy tiếp với {}.`);
      this._bootstrap = {};
    }
    this._bootstrapAt = Date.now();
    return this._bootstrap;
  }

  async sentinel(h, clientVersion) {
    const proofToken = buildProofToken(this.userAgent, clientVersion);
    const r1 = await this._req(PREPARE, {
      method: 'POST',
      headers: { ...h, 'x-openai-target-path': PREPARE, 'x-openai-target-route': PREPARE },
      body: JSON.stringify({ p: proofToken }),
      label: 'sentinel/prepare',
    });
    const prep = JSON.parse(r1.text);

    const seed = prep?.proofofwork?.seed;
    const difficulty = prep?.proofofwork?.difficulty;
    const powAnswer = solvePow(seed, difficulty, this.userAgent);
    if (!verifyPow(seed, difficulty, powAnswer)) {
      throw new ChatGPTError('Không giải được bài băm sentinel (proof-of-work).', 'pow', 0);
    }

    // Solver chạy trong Node, không cần trình duyệt — nó vốn là bản port hàm t_n của bundle.
    const { createRequire } = await import('module');
    const { setupEnv, t_n } = createRequire(import.meta.url)('./solver.cjs');
    setupEnv({ bootstrap: await this.bootstrap(), userAgent: this.userAgent });
    const tsAnswer = await t_n(proofToken, prep?.turnstile?.dx);
    // Soát TRƯỚC khi gửi: t_n hỏng thì vẫn resolve bằng rác, gửi lên chỉ đổi lấy một cái 403 trống không.
    const tsHong = turnstileFailure(tsAnswer);
    if (tsHong) throw new ChatGPTError(`Giải turnstile thất bại — ${tsHong}`, 'sentinel', 0);

    const r2 = await this._req(FINALIZE, {
      method: 'POST',
      headers: { ...h, 'x-openai-target-path': FINALIZE, 'x-openai-target-route': FINALIZE },
      body: JSON.stringify({ prepare_token: prep.prepare_token, proofofwork: powAnswer, turnstile: tsAnswer }),
      label: 'sentinel/finalize',
    });
    const finalToken = JSON.parse(r2.text)?.token;
    if (!finalToken) throw new ChatGPTError('[sentinel/finalize] không có token', 'sentinel', r2.status);
    return { powAnswer, tsAnswer, finalToken };
  }

  async chat(message, { convId = null, parentMessageId = null, model = null } = {}) {
    if (!this.usable) throw new ChatGPTError('Chưa có cookie chatgpt.com — đăng nhập ở trang Accounts.', 'auth', 0);
    const boot = await this.bootstrap();
    const clientVersion = boot?.clientVersion || boot?.client_version || '';
    const clientBuild = String(boot?.buildNumber || boot?.build_number || '');
    const accessToken = await this.accessToken();
    const sessionId = randomUUID();

    const h = {
      ...baseHeaders({
        cookies: this.cookies, userAgent: this.userAgent, deviceId: this.deviceId,
        clientBuild, clientVersion, sessionId,
      }),
      Authorization: `Bearer ${accessToken}`,
    };

    const { powAnswer, tsAnswer, finalToken } = await this.sentinel(h, clientVersion);

    const r = await this._req(CHAT, {
      method: 'POST',
      headers: {
        ...h,
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

    const dec = decodeStream(r.text);
    if (!dec.message.trim() && dec.error) {
      throw new ChatGPTError(`chatgpt.com báo lỗi: ${JSON.stringify(dec.error).slice(0, 300)}`, 'stream', 200);
    }
    return { message: dec.message, convId: dec.conversationId, messageId: dec.messageId, finish: dec.finish, model: dec.model };
  }

  /** Không có trình duyệt nào để đóng — có mặt để nơi gọi dùng chung một khuôn với ChatGPTWeb. */
  async close() {}
}
