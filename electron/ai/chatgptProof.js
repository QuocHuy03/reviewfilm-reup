// Sentinel proof + proof-of-work của chatgpt.com — bản Node, port từ gpt_plus.py (đã gỡ ở 7da88cd).
//
// Vì sao chatgpt.com cần món này mà claude.ai thì không: trước khi cho gọi /backend-api/f/conversation,
// chatgpt.com bắt qua hai cửa `/sentinel/chat-requirements/prepare` rồi `/finalize`. Cửa đầu trả về
// một bài toán băm (proofofwork) và một thử thách turnstile; không giải được thì không có
// `openai-sentinel-chat-requirements-token`, và mọi lượt chat đều 403.
//
// File này CHỈ chứa phần thuần, tính được offline: dựng proof token và giải bài băm. Phần turnstile
// nằm ở solver.js (bê nguyên từ bundle chatgpt.com). Tách ra để kiểm chứng được bằng test thật —
// giải xong thì băm lại mà so, chứ không phải "chạy không lỗi là coi như đúng".
//
// ⚠️ Bài băm và cách dựng token BÁM THEO BUNDLE của chatgpt.com. Bundle xoay thì phải cập nhật lại
// theo cùng cách solver.js đã ghi trong đầu file. Đây là cái giá của đường reverse, nói trước.

import { randomUUID } from 'crypto';
// KHÔNG dùng crypto.createHash('sha3-512'): Electron chạy trên BoringSSL, mà BoringSSL không cài
// SHA-3 — gọi trong app là ném "Digest method not supported". Node thuần thì có, nên test xanh mà
// app chết; đúng loại lỗi khác biệt môi trường khó lần nhất. Bản thuần JS đã đối chiếu từng bit với
// crypto của Node trong selftest.
import { sha3_512 } from './sha3.js';

const TOKEN_PREFIX = 'gAAAAAC';
const POW_PREFIX   = 'gAAAAAB';
const JS_BUCKET_UUID = 'a67561ed-f3e2-455f-901a-e2c8a3247003';

const DAYS   = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const pad2 = (n) => String(n).padStart(2, '0');

/** Chuỗi ngày giờ đúng khuôn `Date.toString()` của trình duyệt ở múi GMT+0700. */
function proofDateString(epochMs) {
  const t = new Date(epochMs + 7 * 3600 * 1000);   // dịch sang GMT+7 rồi đọc bằng getUTC*
  return `${DAYS[t.getUTCDay()]} ${MONTHS[t.getUTCMonth()]} ${pad2(t.getUTCDate())} ${t.getUTCFullYear()} `
    + `${pad2(t.getUTCHours())}:${pad2(t.getUTCMinutes())}:${pad2(t.getUTCSeconds())} GMT+0700 (Giờ Đông Dương)`;
}

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
const randLetters = (n) => Array.from({ length: n },
  () => 'abcdefghijklmnopqrstuvwxyz0123456789'[Math.floor(Math.random() * 36)]).join('');

/**
 * Proof token gửi kèm `/sentinel/chat-requirements/prepare`.
 *
 * Nội dung là một mảng "vân tay trình duyệt" đã được web app tuần tự hoá rồi base64. Thứ tự phần tử
 * là do bundle quy định — đổi chỗ một phần tử là hỏng, nên giữ nguyên như bản đã chạy được.
 */
export function buildProofToken(userAgent, clientVersion, opts = {}) {
  const {
    language = 'en-US',
    languagesJoined = 'en-US,en,vi',
    hardwareConcurrency = 12,
    urlSearchParamNames = 'utm_source,utm_medium,utm_campaign,c_id,c_agid,c_crid,c_kwid,c_ims,'
      + 'c_pms,c_nw,c_dvc,gad_source,gad_campaignid,gbraid,gclid',
    counter = 1,
  } = opts;
  const nowMs = Date.now();
  const fp = [
    3000, proofDateString(nowMs), 4294967296, counter, userAgent, null,
    clientVersion, language, languagesJoined, 0.6000000238418579,
    `hardwareConcurrency−${hardwareConcurrency}`,   // dấu MINUS (U+2212), không phải gạch nối
    `__reactContainer$${randLetters(11)}`,
    'structuredClone', Math.round((40000 + Math.random() * 40000) * 10) / 10,
    JS_BUCKET_UUID, urlSearchParamNames, hardwareConcurrency,
    Math.round(nowMs * 10) / 10, 0, 0, 0, 0, 0, 0, 0,
  ];
  return TOKEN_PREFIX + b64(JSON.stringify(fp));
}

/** Chuỗi thời gian trong cấu hình PoW — khuôn khác proofDateString, giữ đúng bản gốc. */
function powParseTime() {
  const d = new Date(Date.now() - 8 * 3600 * 1000);
  const s = `${DAYS[d.getUTCDay()]}, ${pad2(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()} `
    + `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())} GMT`;
  return s.replace('GMT', 'GMT+0100 (Central European Time)');
}

/**
 * Giải bài băm: tìm `i` sao cho sha3-512(seed + base64(config)) có tiền tố hex <= difficulty.
 *
 * Trả về chuỗi `gAAAAAB<base64>`. Hết `maxIters` mà chưa ra thì trả token dự phòng như bản gốc —
 * server sẽ từ chối, nhưng thà báo lỗi rõ ở tầng trên còn hơn treo mãi ở đây.
 */
export function solvePow(seed, difficulty, userAgent, maxIters = 200000) {
  const core   = [8, 12, 16, 24][Math.floor(Math.random() * 4)];
  const screen = [3000, 4000, 6000][Math.floor(Math.random() * 3)];
  const ua = userAgent || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';
  const config = [core + screen, powParseTime(), 4294705152, 0, ua];
  const diffLen = Math.floor(String(difficulty).length / 2);

  for (let i = 0; i < maxIters; i++) {
    config[3] = i;
    const base = b64(JSON.stringify(config));
    const hex = sha3_512(seed + base);
    if (hex.slice(0, diffLen) <= difficulty) return POW_PREFIX + base;
  }
  return 'gAAAAABwQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D' + b64(`"${seed}"`);
}

/** Kiểm lại một lời giải — dùng cho test, và để tầng trên tự soát trước khi gửi đi. */
export function verifyPow(seed, difficulty, answer) {
  if (typeof answer !== 'string' || !answer.startsWith(POW_PREFIX)) return false;
  const base = answer.slice(POW_PREFIX.length);
  const hex = sha3_512(seed + base);
  return hex.slice(0, Math.floor(String(difficulty).length / 2)) <= difficulty;
}

/**
 * Lời giải turnstile có phải là RÁC không? Trả về câu giải thích, hoặc '' nếu trông ổn.
 *
 * ── VÌ SAO CẦN ─────────────────────────────────────────────────────────────────────────────────
 * `t_n` của bundle KHÔNG NÉM khi hỏng — nó vẫn `resolve`, chỉ là resolve bằng một chuỗi rác. Có hai
 * kiểu, và cả hai đều trông y như token thật với người gọi:
 *
 *   · Hỏng trong lúc giải → resolve `btoa("<số>: <Error…>")`, tức base64 của chính câu lỗi.
 *   · Quá 5 giây          → resolve `"" + D1`, tức một con số trần trụi ("0", "17"…).
 *
 * Không soát thì ta gửi nguyên rác đó lên `/finalize`, và cái nhận về là 403 trống không — trong khi
 * nguyên nhân thật đã nằm sẵn trong tay, chỉ cần giải base64 ra đọc.
 */
export function turnstileFailure(token) {
  if (typeof token !== 'string' || !token.trim()) return 'solver không trả về gì.';
  // Số trần trụi = hết 5 giây mà chưa giải xong.
  if (/^\d+$/.test(token)) return `solver hết giờ (5 giây) sau ${token} bước.`;
  let decoded = '';
  try { decoded = Buffer.from(token, 'base64').toString('utf8'); } catch { return ''; }
  // Khuôn "<số>: <TênLỗi>" là đường thoát lỗi của bundle, không phải token hợp lệ.
  const m = /^(\d+): ((?:\w*Error|ReferenceError|TypeError|SyntaxError)\b[\s\S]*)$/.exec(decoded);
  return m ? `solver hỏng ở bước ${m[1]}: ${m[2].slice(0, 200)}` : '';
}

export { randomUUID };
