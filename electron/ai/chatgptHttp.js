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
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { basename, join } from 'path';
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

  /** Header đã gắn Bearer — dùng chung cho chat, upload và tải ảnh. */
  async _authHeaders() {
    if (!this.usable) throw new ChatGPTError('Chưa có cookie chatgpt.com — đăng nhập ở trang Accounts.', 'auth', 0);
    const boot = await this.bootstrap();
    const clientVersion = boot?.clientVersion || boot?.client_version || '';
    const clientBuild = String(boot?.buildNumber || boot?.build_number || '');
    const accessToken = await this.accessToken();
    const h = {
      ...baseHeaders({
        cookies: this.cookies, userAgent: this.userAgent, deviceId: this.deviceId,
        clientBuild, clientVersion, sessionId: randomUUID(),
      }),
      Authorization: `Bearer ${accessToken}`,
    };
    return { h, clientVersion };
  }

  /** Qua sentinel rồi gửi một lượt hội thoại. Trả về văn bản SSE thô. */
  async _send(h, clientVersion, body, label) {
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
      body: JSON.stringify(body),
      label,
    });
    return r.text;
  }

  async chat(message, { convId = null, parentMessageId = null, model = null } = {}) {
    const { h, clientVersion } = await this._authHeaders();
    const text = await this._send(h, clientVersion, chatBody(message, model || this.model, convId, parentMessageId), 'gửi chat');
    const dec = decodeStream(text);
    if (!dec.message.trim() && dec.error) {
      throw new ChatGPTError(`chatgpt.com báo lỗi: ${JSON.stringify(dec.error).slice(0, 300)}`, 'stream', 200);
    }
    return { message: dec.message, convId: dec.conversationId, messageId: dec.messageId, finish: dec.finish, model: dec.model };
  }

  /**
   * Đưa một ảnh trên máy lên chatgpt.com để làm tham chiếu — đúng ba bước web app làm khi kéo ảnh vào
   * ô chat: xin chỗ (`/files`) → PUT thẳng lên blob storage → báo đã xong (`/files/{id}/uploaded`).
   */
  async uploadImage(h, filePath) {
    const buf = readFileSync(filePath);
    const info = imageInfo(buf);
    if (!info) throw new ChatGPTError(`Không đọc được ảnh tham chiếu (chỉ nhận PNG/JPEG/WEBP): ${filePath}`, 'input', 0);
    const name = basename(filePath);
    const r1 = await this._req('/backend-api/files', {
      method: 'POST', headers: h, label: `xin chỗ upload ${name}`,
      body: JSON.stringify({ file_name: name, file_size: buf.length, use_case: 'multimodal', width: info.width, height: info.height }),
    });
    const { file_id: id, upload_url: uploadUrl } = JSON.parse(r1.text);
    if (!id || !uploadUrl) throw new ChatGPTError(`[upload ${name}] chatgpt.com không trả chỗ upload`, 'upload', r1.status);
    // Blob storage của Azure, không phải chatgpt.com — KHÔNG gửi cookie/Bearer sang đây.
    const put = await fetch(uploadUrl, {
      method: 'PUT', body: buf,
      headers: { 'x-ms-blob-type': 'BlockBlob', 'x-ms-version': '2020-04-08', 'Content-Type': info.mime },
    });
    if (put.status >= 300) throw new ChatGPTError(`[upload ${name}] blob storage trả HTTP ${put.status}`, 'upload', put.status);
    await this._req(`/backend-api/files/${id}/uploaded`, { method: 'POST', headers: h, body: '{}', label: `xác nhận upload ${name}` });
    return { id, name, size: buf.length, ...info };
  }

  /**
   * Tạo ảnh (kèm 0..n ảnh tham chiếu) và tải kết quả về `outDir`.
   *
   * Ảnh kết quả là message của `tool` trong hội thoại, part `image_asset_pointer` dạng `sediment://`.
   * Thường đã có ngay khi luồng SSE đóng, nhưng vẫn thăm dò thêm vì tool có thể ghi muộn hơn.
   * Link tải (`estuary/content`) đòi cookie + Bearer — thiếu là nhận về JSON "access denied" 39 byte.
   *
   * @returns {Promise<{files: string[], convId: string, text: string}>}
   */
  async image(prompt, { refs = [], outDir, model = 'auto', pollMs = 5000, timeoutMs = 300000 } = {}) {
    if (!outDir) throw new ChatGPTError('Thiếu outDir để lưu ảnh.', 'input', 0);
    const { h, clientVersion } = await this._authHeaders();
    const ups = await Promise.all(refs.map((p) => this.uploadImage(h, p)));

    const body = chatBody(prompt, model);
    const msg = body.messages[0];
    if (ups.length) {
      msg.content = {
        content_type: 'multimodal_text',
        parts: [
          ...ups.map((u) => ({ content_type: 'image_asset_pointer', asset_pointer: `file-service://${u.id}`,
            size_bytes: u.size, width: u.width, height: u.height })),
          String(prompt ?? ''),
        ],
      };
      msg.metadata.attachments = ups.map((u) => ({ id: u.id, size: u.size, name: u.name, mime_type: u.mime, width: u.width, height: u.height }));
    }
    body.system_hints = ['picture_v2'];
    msg.metadata.system_hints = ['picture_v2'];

    const text = await this._send(h, clientVersion, body, `tạo ảnh (${ups.length} tham chiếu)`);
    const dec = decodeStream(text);
    if (!dec.conversationId) {
      throw new ChatGPTError(`chatgpt.com không mở hội thoại tạo ảnh: ${JSON.stringify(dec.error || '').slice(0, 300)}`, 'stream', 200);
    }

    const deadline = Date.now() + timeoutMs;
    let pointers = [];
    while (true) {
      const r = await this._req(`/backend-api/conversation/${dec.conversationId}`, { headers: h, label: 'đọc hội thoại tạo ảnh' });
      pointers = toolImagePointers(JSON.parse(r.text));
      if (pointers.length || Date.now() > deadline) break;
      await new Promise((res) => setTimeout(res, pollMs));
    }
    // Không có ảnh mà model trả lời bằng chữ — thường là từ chối nội dung. Đưa nguyên câu đó lên.
    if (!pointers.length) {
      throw new ChatGPTError(`chatgpt.com không trả ảnh. ${dec.message.trim().slice(0, 400) || 'Hết thời gian chờ.'}`, 'noimage', 200);
    }

    mkdirSync(outDir, { recursive: true });
    const files = [];
    for (const ptr of pointers) {
      const fid = ptr.split('://')[1];
      const r = await this._req(`/backend-api/files/download/${fid}?conversation_id=${dec.conversationId}&inline=false`,
        { headers: h, label: 'lấy link tải ảnh' });
      const url = JSON.parse(r.text)?.download_url;
      if (!url) throw new ChatGPTError(`[tải ảnh] không có download_url cho ${fid}`, 'download', r.status);
      const img = await fetch(url, { headers: { Cookie: this.cookies, 'User-Agent': this.userAgent, Authorization: h.Authorization, Referer: `${BASE}/` } });
      const buf = Buffer.from(await img.arrayBuffer());
      if (img.status >= 400 || !String(img.headers.get('content-type') || '').startsWith('image/')) {
        throw new ChatGPTError(`[tải ảnh] HTTP ${img.status}: ${buf.toString('utf8', 0, 200)}`, 'download', img.status);
      }
      const ext = (imageInfo(buf)?.mime || 'image/png').split('/')[1].replace('jpeg', 'jpg');
      const out = join(outDir, `${fid}.${ext}`);
      writeFileSync(out, buf);
      files.push(out);
    }
    return { files, convId: dec.conversationId, text: dec.message };
  }

  /** Không có trình duyệt nào để đóng — có mặt để nơi gọi dùng chung một khuôn với ChatGPTWeb. */
  async close() {}
}

/** Con trỏ ảnh do tool tạo ra (bỏ qua ảnh tham chiếu người dùng gửi lên), theo thứ tự thời gian. */
export function toolImagePointers(conv) {
  const nodes = Object.values(conv?.mapping || {})
    .map((n) => n?.message)
    .filter((m) => m?.author?.role === 'tool')
    .sort((a, b) => (a.create_time || 0) - (b.create_time || 0));
  const out = [];
  for (const m of nodes) {
    for (const p of m.content?.parts || []) {
      const ptr = p?.content_type === 'image_asset_pointer' ? p.asset_pointer : '';
      if (ptr && !out.includes(ptr)) out.push(ptr);
    }
  }
  return out;
}

/** Kích thước + mime đọc từ header file — chatgpt.com đòi width/height lúc xin chỗ upload. */
export function imageInfo(buf) {
  if (buf.length > 24 && buf.readUInt32BE(0) === 0x89504e47) {
    return { mime: 'image/png', width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
  }
  if (buf.length > 30 && buf.toString('ascii', 0, 4) === 'RIFF' && buf.toString('ascii', 8, 12) === 'WEBP') {
    const kind = buf.toString('ascii', 12, 16);
    if (kind === 'VP8X') return { mime: 'image/webp', width: 1 + buf.readUIntLE(24, 3), height: 1 + buf.readUIntLE(27, 3) };
    if (kind === 'VP8L') {
      const b = buf.readUInt32LE(21);
      return { mime: 'image/webp', width: 1 + (b & 0x3fff), height: 1 + ((b >> 14) & 0x3fff) };
    }
    return { mime: 'image/webp', width: buf.readUInt16LE(26) & 0x3fff, height: buf.readUInt16LE(28) & 0x3fff };
  }
  if (buf.length > 4 && buf[0] === 0xff && buf[1] === 0xd8) {
    // Lần theo các segment tới SOFn — chỗ duy nhất JPEG ghi kích thước.
    let i = 2;
    while (i + 9 < buf.length) {
      if (buf[i] !== 0xff) { i++; continue; }
      const marker = buf[i + 1];
      const len = buf.readUInt16BE(i + 2);
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
        return { mime: 'image/jpeg', height: buf.readUInt16BE(i + 5), width: buf.readUInt16BE(i + 7) };
      }
      i += 2 + len;
    }
  }
  return null;
}
