// Client chatgpt.com CHỌN ĐƯỜNG: HTTP thuần trước, trình duyệt là đường lùi.
//
// ── VÌ SAO CẦN CẢ HAI ───────────────────────────────────────────────────────────────────────────
// Hai đường có điểm mạnh ngược nhau, và không đường nào đủ một mình:
//
//   chatgptHttp — chỉ là request HTTP. Nhanh (không dựng Chrome), nhẹ (không vài trăm MB), chạy
//                 song song được (không khoá profile). Nhưng phải CÓ SẴN cookie còn hạn, và có thể
//                 bị Cloudflare chặn vì vân tay TLS của Node khác Chrome.
//   ChatGPTWeb  — chạy trong Chrome thật nên qua được Cloudflare, và tự đăng nhập lại được. Nhưng
//                 mỗi lượt tốn vài giây dựng trình duyệt, và profile bị khoá nên không song song.
//
// Nên: đi HTTP, hỏng theo kiểu "bị chặn / hết phiên" thì lùi sang trình duyệt, và sau khi trình duyệt
// chạy được thì LẤY LẠI cookie mới — lượt sau lại đi HTTP. Trình duyệt trở thành thứ chỉ dùng khi
// cookie chết, chứ không phải thứ chạy mỗi lượt.
//
// Đây cũng đúng cách bản Python cũ làm: đăng nhập một lần, sau đó thuần HTTP.

import { ChatGPTError, ChatGPTWeb } from './chatgptWeb.js';
import { ChatGPTHttp } from './chatgptHttp.js';

/**
 * Lỗi nào ĐÁNG lùi sang trình duyệt?
 *
 * Chỉ những lỗi mà trình duyệt có cửa sửa được: cookie hết hạn (trình duyệt còn phiên trong profile),
 * hoặc Cloudflare chặn vân tay TLS (trình duyệt có vân tay thật). Còn model từ chối nội dung, câu hỏi
 * quá dài, mạng đứt… thì lùi cũng hỏng y hệt, chỉ tốn thêm mấy giây dựng Chrome rồi báo cùng một lỗi.
 */
export function shouldFallback(err) {
  if (!err) return false;
  // Tên loại phải KHỚP classifyChatGPTError: 'blocked' (Cloudflare chặn) và 'forbidden' (chatgpt.com
  // từ chối theo logic, thường là token sentinel hỏng) — cả hai trình duyệt đều có cửa sửa.
  const kind = err.kind || '';
  if (['auth', 'blocked', 'forbidden', 'sentinel', 'pow'].includes(kind)) return true;
  // 401/403 chưa phân loại được cũng cho lùi: hai mã này gần như luôn là phiên hoặc Cloudflare.
  return err.status === 401 || err.status === 403;
}

export class ChatGPTClient {
  /**
   * @param {object} o
   * @param {string} o.profileDir thư mục profile Chrome — đường lùi cần
   * @param {string} [o.cookies]   cookie đã lưu lúc đăng nhập
   * @param {string} [o.userAgent] UA đi kèm cookie đó (đổi UA là đổi vân tay, dễ bị soi)
   * @param {string} [o.model]
   * @param {(creds:{cookies:string,userAgent:string}) => void} [o.onCreds] gọi khi có cookie mới
   */
  constructor({ profileDir, cookies = '', userAgent = '', model = 'gpt-5-5-thinking', onCreds = null }) {
    this.profileDir = profileDir || process.cwd();
    this.cookies = String(cookies || '');
    this.userAgent = String(userAgent || '');
    this.model = model;
    this.onCreds = onCreds;
    this._web = null;
    this.lastRoute = '';        // 'http' | 'browser' — để log và để test đọc được
  }

  _http() {
    return new ChatGPTHttp({ cookies: this.cookies, userAgent: this.userAgent, model: this.model });
  }

  _browser() {
    if (!this._web) this._web = new ChatGPTWeb(this.profileDir, { headless: true, model: this.model });
    return this._web;
  }

  /**
   * Lấy cookie mới từ phiên trình duyệt và báo lên trên để ghi vào DB.
   *
   * Làm SAU khi trình duyệt gọi thành công, không phải trước: cookie lấy ở phiên vừa bị Cloudflare
   * chặn thì lưu lại cũng vô dụng, mà còn đè mất bộ cũ có khi vẫn dùng được.
   */
  async _refreshCreds() {
    try {
      const c = await this._browser().credentials();
      if (!c?.cookies) return;
      this.cookies = c.cookies;
      this.userAgent = c.userAgent || this.userAgent;
      this.onCreds?.({ cookies: this.cookies, userAgent: this.userAgent });
      console.log('[chatgpt] đã làm mới cookie từ phiên trình duyệt — lượt sau chạy lại bằng HTTP.');
    } catch (e) {
      // Không lấy được cookie thì lượt sau lại phải mở trình duyệt. Chậm, nhưng vẫn chạy.
      console.warn(`[chatgpt] không lấy được cookie mới: ${e?.message || e}`);
    }
  }

  async chat(message, opts = {}) {
    const http = this._http();
    if (http.usable) {
      try {
        this.lastRoute = 'http';
        console.log('[chatgpt] đi đường HTTP thuần (không mở trình duyệt).');
        return await http.chat(message, { ...opts, model: opts.model || this.model });
      } catch (e) {
        if (!shouldFallback(e)) throw e;
        console.warn(`[chatgpt] đường HTTP hỏng (${e.kind || e.status}: ${e.message}) — lùi sang trình duyệt.`);
      }
    } else {
      console.log('[chatgpt] chưa có cookie — chạy bằng trình duyệt để lấy phiên.');
    }

    this.lastRoute = 'browser';
    const r = await this._browser().chat(message, { ...opts, model: opts.model || this.model });
    await this._refreshCreds();
    return r;
  }

  /**
   * Tạo ảnh (kèm ảnh tham chiếu). Chỉ có đường HTTP — trình duyệt ở đây không tự tạo ảnh, nó chỉ làm
   * việc nó giỏi: vượt Cloudflare / cấp cookie mới. Nên hỏng kiểu "đáng lùi" thì lấy cookie từ
   * trình duyệt rồi chạy lại HTTP đúng một lần.
   */
  async image(prompt, opts = {}) {
    this.lastRoute = 'http';
    try {
      return await this._http().image(prompt, opts);
    } catch (e) {
      if (!shouldFallback(e)) throw e;
      console.warn(`[chatgpt] tạo ảnh qua HTTP hỏng (${e.kind || e.status}: ${e.message}) — làm mới cookie bằng trình duyệt rồi thử lại.`);
    }
    await this._refreshCreds();
    this.lastRoute = 'browser+http';
    return await this._http().image(prompt, opts);
  }

  /** Gói cước. Chỉ trình duyệt trả lời được chắc chắn, mà đây là việc hiếm nên mở Chrome cũng đáng. */
  async plan() {
    try { return await this._browser().plan(); } catch { return ''; }
  }

  async close() {
    try { await this._web?.close(); } catch { /* đóng hỏng không đáng làm chết lượt gọi */ }
    this._web = null;
  }
}

export { ChatGPTError };
