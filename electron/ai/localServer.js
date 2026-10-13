// Máy chủ loopback cho backend Python gọi vào tài khoản AI web — port ý tưởng chatgptCompat của ToolYoutube.
//
//   GET  /rf/status               → { chatgpt: bool, gemini: bool }
//   POST /v1/chat/completions     → khuôn OpenAI. model: "chatgpt" | "gpt-*" | "gemini*" | "auto"
//   POST /rf/gemini/files         → { prompt, files: [đường dẫn ảnh/video trên máy], timeout? } → { content }
//
// Chỉ nghe 127.0.0.1 + bắt buộc Bearer token (sinh mỗi lần chạy, truyền cho backend qua env):
// đây là cửa vào tài khoản ChatGPT/Google của người dùng, không để tiến trình lạ trên máy gọi ké.

import { createServer } from 'http';
import { randomBytes } from 'crypto';
import { existsSync } from 'fs';
import { readiness, chatgptChat, geminiChat } from './accounts.js';

let _server = null;
let _port = 0;
const TOKEN = randomBytes(24).toString('hex');

/** Gộp messages[] OpenAI thành một prompt — các nơi gọi đều stateless nên mỗi lượt là hội thoại mới. */
export function messagesToPrompt(messages = []) {
  const parts = [];
  for (const m of messages) {
    if (!m) continue;
    const text = typeof m.content === 'string' ? m.content
      : Array.isArray(m.content) ? m.content.filter((p) => p?.type === 'text').map((p) => p.text).join('\n') : '';
    if (!text.trim()) continue;
    if (messages.length === 1 && m.role === 'user') return text;
    const role = m.role === 'system' ? 'HỆ THỐNG' : m.role === 'assistant' ? 'TRỢ LÝ (lượt trước)' : 'NGƯỜI DÙNG';
    parts.push(`### ${role}\n${text}`);
  }
  return parts.join('\n\n');
}

function completionOf(text, model, finish) {
  return {
    id: `chatcmpl-${Date.now().toString(36)}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [{ index: 0, message: { role: 'assistant', content: text }, finish_reason: finish === 'max_tokens' ? 'length' : 'stop' }],
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
  };
}

const readBody = (req) => new Promise((resolve, reject) => {
  let raw = '';
  req.setEncoding('utf8');
  req.on('data', (c) => { raw += c; if (raw.length > 30e6) reject(new Error('body quá lớn')); });
  req.on('end', () => resolve(raw));
  req.on('error', reject);
});

const sendJson = (res, code, obj) => {
  const s = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(s) });
  res.end(s);
};

const errStatus = (e) => (e?.kind === 'auth' ? 401 : e?.status >= 400 ? e.status : 502);

async function runChat(model, prompt) {
  const m = String(model || 'auto').toLowerCase();
  const ready = readiness();
  const wantGemini = m.startsWith('gemini');
  const wantGpt = m.startsWith('gpt') || m.startsWith('chatgpt');

  if (wantGemini) {
    const r = await geminiChat(prompt);
    return { text: r.content, model: 'gemini-web' };
  }
  const gptModel = m.startsWith('gpt') ? model : undefined;
  if (wantGpt || ready.chatgpt) {
    try {
      const r = await chatgptChat(prompt, { model: gptModel });
      return { text: r.message, model: r.model || 'chatgpt-web', finish: r.finish };
    } catch (e) {
      // "auto": ChatGPT hỏng mà có Gemini thì đổi engine thay vì làm hỏng cả job.
      if (wantGpt || !ready.gemini) throw e;
      console.warn(`[ai-local] ChatGPT lỗi (${e?.message || e}) → chuyển sang Gemini.`);
    }
  }
  if (ready.gemini) {
    const r = await geminiChat(prompt);
    return { text: r.content, model: 'gemini-web' };
  }
  throw Object.assign(new Error('Chưa đăng nhập tài khoản ChatGPT hoặc Gemini (Cài đặt → Tài khoản AI).'), { kind: 'auth' });
}

async function handle(req, res) {
  const url = (req.url || '').split('?')[0];
  if (req.headers.authorization !== `Bearer ${TOKEN}`) return sendJson(res, 403, { error: { message: 'forbidden' } });

  if (req.method === 'GET' && url === '/rf/status') return sendJson(res, 200, readiness());

  if (req.method === 'POST' && (url === '/v1/chat/completions' || url === '/chat/completions')) {
    let body;
    try { body = JSON.parse(await readBody(req)); } catch (e) {
      return sendJson(res, 400, { error: { message: `body không phải JSON: ${e.message}` } });
    }
    const prompt = messagesToPrompt(body?.messages);
    if (!prompt.trim()) return sendJson(res, 400, { error: { message: 'messages rỗng.' } });
    try {
      const r = await runChat(body?.model, prompt);
      return sendJson(res, 200, completionOf(r.text || '', r.model, r.finish));
    } catch (e) {
      return sendJson(res, errStatus(e), { error: { message: e?.message || String(e), type: e?.kind || 'unknown' } });
    }
  }

  if (req.method === 'POST' && url === '/rf/gemini/files') {
    let body;
    try { body = JSON.parse(await readBody(req)); } catch (e) {
      return sendJson(res, 400, { error: { message: `body không phải JSON: ${e.message}` } });
    }
    const files = (Array.isArray(body?.files) ? body.files : []).filter((f) => typeof f === 'string' && existsSync(f));
    if (!String(body?.prompt || '').trim()) return sendJson(res, 400, { error: { message: 'prompt rỗng.' } });
    try {
      const r = await geminiChat(body.prompt, { files: files.length ? files : null, timeout: body?.timeout || null });
      return sendJson(res, 200, { content: r.content || '' });
    } catch (e) {
      return sendJson(res, errStatus(e), { error: { message: e?.message || String(e), type: e?.kind || 'unknown' } });
    }
  }

  sendJson(res, 404, { error: { message: `không có route ${req.method} ${url}` } });
}

/** @returns {Promise<{url: string, token: string}>} */
export function startLocalServer() {
  if (_server) return Promise.resolve({ url: `http://127.0.0.1:${_port}`, token: TOKEN });
  return new Promise((resolve, reject) => {
    _server = createServer((req, res) => {
      // Lượt ChatGPT thinking / Gemini đọc video có thể vài phút — tắt timeout mặc định của Node.
      req.setTimeout(0);
      handle(req, res).catch((e) => { try { sendJson(res, 500, { error: { message: e?.message || String(e) } }); } catch { /* đã ngắt */ } });
    });
    _server.requestTimeout = 0;
    _server.headersTimeout = 0;
    _server.on('error', reject);
    _server.listen(0, '127.0.0.1', () => {
      _port = _server.address().port;
      console.log(`[ai-local] tài khoản AI web phục vụ tại http://127.0.0.1:${_port}`);
      resolve({ url: `http://127.0.0.1:${_port}`, token: TOKEN });
    });
  });
}

export async function stopLocalServer() {
  await new Promise((r) => (_server ? _server.close(r) : r()));
  _server = null;
  _port = 0;
}
