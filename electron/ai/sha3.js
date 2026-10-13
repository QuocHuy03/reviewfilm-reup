// SHA3-512 thuần JS.
//
// ── VÌ SAO PHẢI TỰ VIẾT ─────────────────────────────────────────────────────────────────────────
// Bài proof-of-work của chatgpt.com băm bằng SHA3-512. Node thường có sẵn qua
// `crypto.createHash('sha3-512')` — nhưng ELECTRON thì KHÔNG: Electron dùng BoringSSL của Chromium,
// mà BoringSSL không cài SHA-3. Gọi trong app là ném đúng câu người dùng gặp:
//
//     Digest method not supported
//
// Đây là loại lỗi tệ nhất để lần: test chạy bằng node thuần thì XANH (node có SHA-3), app thì chết.
// Không phải lỗi logic, mà là khác biệt môi trường.
//
// Cài thêm gói npm cũng được, nhưng nó phải đi kèm installer và là một phụ thuộc native nữa để lo.
// Keccak thì gọn — chép đúng thuật toán, rồi ĐỐI CHIẾU với crypto của Node trong test là chắc.
//
// Cài đặt theo cặp 32-bit (hi/lo) chứ không dùng BigInt: PoW băm hàng nghìn lượt mỗi lần giải, BigInt
// chậm hơn hàng chục lần và sẽ thành chỗ nghẽn thấy rõ.

const RC_HI = [
  0x00000000, 0x00000000, 0x80000000, 0x80000000, 0x00000000, 0x00000000, 0x80000000, 0x80000000,
  0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x80000000, 0x80000000, 0x80000000,
  0x80000000, 0x80000000, 0x00000000, 0x80000000, 0x80000000, 0x80000000, 0x00000000, 0x80000000,
];
const RC_LO = [
  0x00000001, 0x00008082, 0x0000808a, 0x80008000, 0x0000808b, 0x80000001, 0x80008081, 0x00008009,
  0x0000008a, 0x00000088, 0x80008009, 0x8000000a, 0x8000808b, 0x0000008b, 0x00008089, 0x00008003,
  0x00008002, 0x00000080, 0x0000800a, 0x8000000a, 0x80008081, 0x00008080, 0x80000001, 0x80008008,
];

// Vị trí lane sau bước ρ/π, và số bit xoay tương ứng — bảng cố định của Keccak.
const PI = [10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4, 15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1];
const ROT = [1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14, 27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44];

/** Một vòng hoán vị Keccak-f[1600] trên state 25 lane (mỗi lane = 2 số 32-bit). */
function keccakF(hi, lo) {
  const bcHi = new Int32Array(5);
  const bcLo = new Int32Array(5);

  for (let round = 0; round < 24; round++) {
    // θ
    for (let i = 0; i < 5; i++) {
      bcHi[i] = hi[i] ^ hi[i + 5] ^ hi[i + 10] ^ hi[i + 15] ^ hi[i + 20];
      bcLo[i] = lo[i] ^ lo[i + 5] ^ lo[i + 10] ^ lo[i + 15] ^ lo[i + 20];
    }
    for (let i = 0; i < 5; i++) {
      const j = (i + 1) % 5;
      const k = (i + 4) % 5;
      // xoay trái 1 bit trên cặp 64-bit
      const tHi = bcHi[k] ^ ((bcHi[j] << 1) | (bcLo[j] >>> 31));
      const tLo = bcLo[k] ^ ((bcLo[j] << 1) | (bcHi[j] >>> 31));
      for (let n = i; n < 25; n += 5) { hi[n] ^= tHi; lo[n] ^= tLo; }
    }

    // ρ và π
    let curHi = hi[1];
    let curLo = lo[1];
    for (let i = 0; i < 24; i++) {
      const j = PI[i];
      const tmpHi = hi[j];
      const tmpLo = lo[j];
      const r = ROT[i];
      if (r < 32) {
        hi[j] = (curHi << r) | (curLo >>> (32 - r));
        lo[j] = (curLo << r) | (curHi >>> (32 - r));
      } else if (r === 32) {
        hi[j] = curLo; lo[j] = curHi;
      } else {
        const s = r - 32;
        hi[j] = (curLo << s) | (curHi >>> (32 - s));
        lo[j] = (curHi << s) | (curLo >>> (32 - s));
      }
      curHi = tmpHi;
      curLo = tmpLo;
    }

    // χ
    for (let y = 0; y < 25; y += 5) {
      const h0 = hi[y], h1 = hi[y + 1], h2 = hi[y + 2], h3 = hi[y + 3], h4 = hi[y + 4];
      const l0 = lo[y], l1 = lo[y + 1], l2 = lo[y + 2], l3 = lo[y + 3], l4 = lo[y + 4];
      hi[y]     = h0 ^ (~h1 & h2);  lo[y]     = l0 ^ (~l1 & l2);
      hi[y + 1] = h1 ^ (~h2 & h3);  lo[y + 1] = l1 ^ (~l2 & l3);
      hi[y + 2] = h2 ^ (~h3 & h4);  lo[y + 2] = l2 ^ (~l3 & l4);
      hi[y + 3] = h3 ^ (~h4 & h0);  lo[y + 3] = l3 ^ (~l4 & l0);
      hi[y + 4] = h4 ^ (~h0 & h1);  lo[y + 4] = l4 ^ (~l0 & l1);
    }

    // ι
    hi[0] ^= RC_HI[round];
    lo[0] ^= RC_LO[round];
  }
}

const RATE = 72;          // SHA3-512: 1600 - 2*512 = 576 bit = 72 byte
const OUT  = 64;          // 512 bit

/**
 * @param {Buffer|Uint8Array|string} input
 * @returns {string} 128 ký tự hex
 */
export function sha3_512(input) {
  const data = typeof input === 'string' ? Buffer.from(input, 'utf8') : Buffer.from(input);
  const hi = new Int32Array(25);
  const lo = new Int32Array(25);

  // Đệm pad10*1 với domain 0x06 của SHA-3 (Keccak gốc dùng 0x01 — sai chỗ này là ra hash khác hẳn).
  const padLen = RATE - (data.length % RATE);
  const buf = Buffer.alloc(data.length + padLen);
  data.copy(buf);
  buf[data.length] = 0x06;
  buf[buf.length - 1] |= 0x80;

  for (let off = 0; off < buf.length; off += RATE) {
    for (let i = 0; i < RATE / 8; i++) {
      lo[i] ^= buf.readInt32LE(off + i * 8);
      hi[i] ^= buf.readInt32LE(off + i * 8 + 4);
    }
    keccakF(hi, lo);
  }

  const out = Buffer.alloc(OUT);
  for (let i = 0; i < OUT / 8; i++) {
    out.writeInt32LE(lo[i], i * 8);
    out.writeInt32LE(hi[i], i * 8 + 4);
  }
  return out.toString('hex');
}

export default { sha3_512 };
