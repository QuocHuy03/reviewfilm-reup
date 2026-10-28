"""Phân tích người nói trong video: câu nào của NHÂN VẬT nào, nhân vật nam hay nữ.

Mỗi câu thoại → "dấu vân giọng" (embedding 192 chiều, model CAM++ của 3D-Speaker, huấn luyện trên tiếng Trung,
ONNX ~28MB, chạy CPU) → gom các câu cùng giọng thành nhân vật → giới tính theo cao độ TRUNG BÌNH CẢ NHÂN VẬT
(chắc hơn đoán từng câu). Lồng tiếng dùng một giọng cố định cho mỗi nhân vật suốt video.
"""
import os
import subprocess
import threading

from .utils import FFMPEG_EXE, _HIDE

MODEL_URLS = (
    'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx',
)
MODEL_MB = 27
SR = 16000
_sess = None
_lock = threading.Lock()


def _model_path():
    from app.config import DATA_DIR
    d = os.path.join(DATA_DIR, 'models')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'campplus_zh_16k.onnx')


def ensure_model(log=print):
    """Tải model nhận giọng (1 lần, ~27MB). → đường dẫn hoặc '' nếu không tải được."""
    p = _model_path()
    if os.path.isfile(p) and os.path.getsize(p) > 20_000_000:
        return p
    import urllib.request
    for url in MODEL_URLS:
        try:
            log(f'   Tải model nhận giọng nhân vật (~{MODEL_MB}MB, chỉ lần đầu)...')
            tmp = p + '.part'
            with urllib.request.urlopen(url, timeout=60) as r, open(tmp, 'wb') as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            if os.path.getsize(tmp) > 20_000_000:
                os.replace(tmp, p)
                return p
        except Exception as e:
            log(f'   [WARN] Tải model nhận giọng lỗi: {str(e)[:120]}')
    return ''


def available():
    import importlib.util
    return importlib.util.find_spec('kaldi_native_fbank') is not None and importlib.util.find_spec('onnxruntime') is not None


def _session(path):
    global _sess
    with _lock:
        if _sess is None:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = max(2, min(8, (os.cpu_count() or 4) // 2))
            _sess = ort.InferenceSession(path, opts, providers=['CPUExecutionProvider'])
        return _sess


def _fbank(samples):
    """Đặc trưng fbank 80 chiều (kaldi) cho đoạn âm thanh float [-1, 1], trừ trung bình theo thời gian."""
    import kaldi_native_fbank as knf
    import numpy as np
    opts = knf.FbankOptions()
    opts.frame_opts.dither = 0
    opts.frame_opts.samp_freq = SR
    opts.mel_opts.num_bins = 80
    fb = knf.OnlineFbank(opts)
    fb.accept_waveform(SR, samples.tolist())
    fb.input_finished()
    n = fb.num_frames_ready
    if n < 10:
        return None
    feats = np.stack([fb.get_frame(i) for i in range(n)]).astype(np.float32)
    return feats - feats.mean(axis=0, keepdims=True)


def load_audio(video):
    """Toàn bộ tiếng của video → float32 mono 16kHz."""
    import numpy as np
    r = subprocess.run([FFMPEG_EXE, '-v', 'error', '-i', video, '-vn', '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                       capture_output=True, creationflags=_HIDE)
    return np.frombuffer(r.stdout, '<i2').astype(np.float32) / 32768.0


def embed(sess, samples):
    import numpy as np
    f = _fbank(samples)
    if f is None:
        return None
    e = sess.run(None, {'x': f[None, ...]})[0][0]
    n = float(np.linalg.norm(e))
    return e / n if n > 0 else None


def _cluster(embs, threshold):
    """Gom nhóm theo độ giống giọng (cosine): lần lượt gán vào nhân vật gần nhất nếu đủ giống, rồi gộp các nhân vật
    trùng giọng; nhân vật chỉ 1 câu → gán về nhân vật gần nhất (đỡ tách vụn)."""
    import numpy as np
    labels = [-1] * len(embs)
    cents = []                                   # [tổng vector, số câu]
    for (i, e) in enumerate(embs):
        if e is None:
            continue
        if cents:
            sims = [float(np.dot(e, c[0] / np.linalg.norm(c[0]))) for c in cents]
            k = int(np.argmax(sims))
            if sims[k] >= threshold:
                cents[k][0] = cents[k][0] + e
                cents[k][1] += 1
                labels[i] = k
                continue
        cents.append([e.copy(), 1])
        labels[i] = len(cents) - 1
    # gộp nhân vật có giọng gần nhau
    unit = lambda v: v / np.linalg.norm(v)
    alias = list(range(len(cents)))
    for a in range(len(cents)):
        for b in range(a + 1, len(cents)):
            if alias[b] == b and float(np.dot(unit(cents[a][0]), unit(cents[b][0]))) >= threshold + 0.05:
                alias[b] = alias[a]
    labels = [alias[x] if x >= 0 else -1 for x in labels]
    # nhân vật chỉ 1 câu mà giọng khá giống nhân vật lớn → gộp (thường do câu ngắn nhận giọng chưa chuẩn)
    counts = {}
    for x in labels:
        if x >= 0:
            counts[x] = counts.get(x, 0) + 1
    big = [k for (k, n) in counts.items() if n >= 2]
    if big:
        for (i, x) in enumerate(labels):
            if x >= 0 and counts.get(x, 0) < 2 and embs[i] is not None:
                k = max(big, key=lambda kk: float(np.dot(embs[i], unit(cents[kk][0]))))
                if float(np.dot(embs[i], unit(cents[k][0]))) >= threshold:   # đủ giống mới gộp — không nuốt nhân vật phụ
                    labels[i] = k
    # đánh số lại theo số câu (nhân vật nói nhiều nhất = 1)
    order = sorted({x for x in labels if x >= 0}, key=lambda k: -labels.count(k))
    remap = {k: n for (n, k) in enumerate(order)}
    return [remap.get(x, -1) for x in labels]


def analyze(video, segments, log=print, threshold=0.62, max_main=6):
    """segments = [(start, end)] (giây). → {'labels': [nhân vật mỗi câu], 'speakers': {id: {'gender', 'count', 'pitch'}}}
    hoặc None nếu không phân tích được.
    1) Dựng nhân vật từ câu DÀI (≥1.5s — đủ giọng để nhận chắc). 2) Câu ngắn gán về nhân vật gần nhất CÙNG GIỚI
    (không bao giờ gán câu giọng nữ cho nhân vật nam). 3) Giữ tối đa `max_main` nhân vật chính, còn lại gộp
    "nam phụ" / "nữ phụ" — đỡ vụn giọng."""
    import numpy as np
    from app.features.jobs.vietsub import _pitch
    if not available():
        log('   [WARN] Thiếu thư viện nhận giọng (kaldi-native-fbank) — khởi động lại app để tự cài')
        return None
    path = ensure_model(log)
    if not path:
        return None
    sess = _session(path)
    audio = load_audio(video)
    if audio.size < SR or not segments:
        return None
    n = len(segments)
    (embs, pitch, durs) = ([None] * n, [0.0] * n, [0.0] * n)
    for (i, (a, b)) in enumerate(segments):
        (i0, i1) = (max(0, int(a * SR)), min(audio.size, int(b * SR)))
        seg = audio[i0:i1]
        durs[i] = seg.size / SR
        if seg.size >= int(0.6 * SR):
            embs[i] = embed(sess, seg)
        pitch[i] = _pitch((seg * 32767).astype(np.int16)) if seg.size else 0.0
    sex = lambda hz: None if hz <= 0 else ('female' if hz > 165 else 'male')
    unit = lambda v: v / np.linalg.norm(v)
    # 1) nhân vật từ câu dài
    long_idx = [i for i in range(n) if embs[i] is not None and durs[i] >= 1.5]
    if not long_idx:
        long_idx = [i for i in range(n) if embs[i] is not None]
    lab_long = _cluster([embs[i] for i in long_idx], threshold) if long_idx else []
    groups = {}
    for (i, k) in zip(long_idx, lab_long):
        if k >= 0:
            groups.setdefault(k, []).append(i)
    chars = []                                   # [centroid, gender, [chỉ số câu]]
    for idx in groups.values():
        hz = [pitch[i] for i in idx if pitch[i] > 0]
        g = sex(float(np.median(hz))) if hz else None
        chars.append([unit(np.sum([embs[i] for i in idx], axis=0)), g or 'male', list(idx)])
    # 2) mọi câu còn lại → nhân vật gần nhất cùng giới (giới theo cao độ câu đó; không rõ thì theo câu trước)
    labels = [-1] * n
    for (c, ch) in enumerate(chars):
        for i in ch[2]:
            labels[i] = c
    prev_g = 'male'
    for i in range(n):
        if labels[i] >= 0:
            prev_g = chars[labels[i]][1]
            continue
        g = sex(pitch[i]) or prev_g
        cand = [c for (c, ch) in enumerate(chars) if ch[1] == g]
        if embs[i] is not None and cand:
            c = max(cand, key=lambda cc: float(np.dot(embs[i], chars[cc][0])))
            if float(np.dot(embs[i], chars[c][0])) >= 0.40:
                labels[i] = c
        if labels[i] < 0:                        # không giống ai đủ → nhân vật phụ cùng giới
            key = f'_minor_{g}'
            hit = next((c for (c, ch) in enumerate(chars) if len(ch) > 3 and ch[3] == key), None)
            if hit is None:
                chars.append([np.zeros(192, np.float32), g, [], key])
                hit = len(chars) - 1
            labels[i] = hit
        chars[labels[i]][2].append(i) if i not in chars[labels[i]][2] else None
        prev_g = chars[labels[i]][1]
    # 3) giữ tối đa max_main nhân vật chính (nói nhiều nhất), còn lại gộp vào "phụ" cùng giới
    counts = {c: labels.count(c) for c in set(labels)}
    main = sorted([c for c in counts if len(chars[c]) <= 3], key=lambda c: -counts[c])[:max_main]
    final = {}
    for (i, c) in enumerate(labels):
        if c in main:
            key = ('main', c)
        else:
            key = ('minor', chars[c][1])
        final.setdefault(key, []).append(i)
    order = sorted(final, key=lambda k: (k[0] != 'main', -len(final[k])))
    labels = [0] * n
    speakers = {}
    for (new_id, key) in enumerate(order):
        idx = final[key]
        for i in idx:
            labels[i] = new_id
        hz = [pitch[i] for i in idx if pitch[i] > 0]
        med = float(np.median(hz)) if hz else 0.0
        g = key[1] if key[0] == 'minor' else (sex(med) or chars[key[1]][1])
        speakers[new_id] = {'gender': g, 'count': len(idx), 'pitch': round(med), 'minor': key[0] == 'minor'}
    summary = ', '.join(f"{'phụ ' if s['minor'] else ''}NV{k + 1} {'nữ' if s['gender'] == 'female' else 'nam'} ({s['count']} câu)"
                        for (k, s) in speakers.items())
    log(f"   Nhận ra {sum(1 for s in speakers.values() if not s['minor'])} nhân vật chính: {summary}")
    return {'labels': labels, 'speakers': speakers}


SCRIPT_PROMPT = """Bạn là đạo diễn lồng tiếng phim Trung Quốc → tiếng Việt. Dưới đây là các câu thoại theo thứ tự thời gian.
Mỗi câu có: "goc" (lời gốc tiếng Trung), "viet" (bản dịch, nếu có), "giong" (nhóm giọng máy nghe được — cùng nhóm thường là
cùng người nhưng có thể nhầm, nhất là câu ngắn), "cao" (máy đoán nam / nữ theo cao độ giọng, có thể sai khi có nhạc).

Các dòng là MẢNH lời nói đã tách ở chỗ ngừng: một câu có thể bị chia thành nhiều dòng liền nhau (cùng người), và 2 dòng liền nhau
cũng có thể là 2 người đối đáp (gọi tên – trả lời, hỏi – đáp, cãi nhau) — xét kỹ từng dòng, đừng gán cả cụm cho một người.
Hãy xác định AI NÓI TỪNG CÂU dựa vào NGỮ CẢNH hội thoại: cách xưng hô (爹 cha, 娘 mẹ, 夫君 phu quân, 妹妹 em gái, 哥 anh…),
tên được gọi, ai đang trả lời ai, nội dung câu, ĐỊA ĐIỂM / CẢNH đang diễn ra (ký túc xá, công ty, cửa hàng…).
Kết hợp với "giong"/"cao" nhưng ngữ cảnh rõ thì ưu tiên ngữ cảnh. LƯU Ý: phim AI / lồng tiếng hay dùng CHUNG một giọng đọc cho
nhiều vai — cùng "giong" chưa chắc là cùng nhân vật (vd bạn cùng phòng và đồng nghiệp ở công ty là 2 người khác nhau).
Người BỊ GỌI TÊN hoặc bị nói tới bằng "ông / anh / cậu / mày / ngươi" (你 / 您) trong câu thường KHÔNG phải người nói câu đó
(vd câu "王刚，Vương Tử Cường là người nhà ông" là người khác nói VỚI Vương Cương, không phải Vương Cương nói).
Lời dẫn chuyện / kể lại thì là "Người kể".
CHỈ LỒNG TIẾNG LỜI THOẠI CỦA NHÂN VẬT. Dòng CHẮC CHẮN không phải lời nhân vật nói thì gán "ma": "X" (không đưa X vào nhan_vat);
còn nghi ngờ (câu ngắn, câu cảm thán, câu nói thầm…) thì vẫn gán cho nhân vật hợp ngữ cảnh nhất. X chỉ dành cho:
lời bài hát / nhạc nền, tiếng động & hiệu ứng (砰 轰 嗖…), tiếng cười / thở / hét không thành lời, tiếng ồn đám đông,
chữ quảng cáo / kêu gọi đăng ký / cảm ơn đã xem, câu máy nghe nhầm vô nghĩa hoặc lặp lại vô lý.
{known}
Chỉ trả về JSON đúng dạng:
{{"nhan_vat": [{{"ma": "A", "ten": "<tên hoặc vai, vd Giang Phàm / Cha của Tô Nhiên / Người kể>", "gioi": "nam|nu"}}],
  "cau": [{{"i": <số>, "ma": "A"}}]}}   (mỗi câu đều phải có mặt trong "cau", câu không phải thoại → "ma": "X")

{rows}"""


def refine_with_script(texts_vi, texts_orig, acoustic, log=print, batch=60):
    """AI đọc kịch bản để biết ai nói câu nào (theo xưng hô, tên gọi, mạch hội thoại), kết hợp gợi ý nghe giọng.
    acoustic = kết quả analyze() (hoặc None). → {'labels', 'speakers': {id: {'gender', 'count', 'name'}}} hoặc None."""
    import json as _json
    from core import web_llm
    from app.features.jobs.postedit import _extract_json
    if not web_llm.available():
        return None
    n = len(texts_orig)
    ac_lab = acoustic['labels'] if acoustic else [0] * n
    ac_spk = acoustic['speakers'] if acoustic else {}
    chars = {}                                   # mã → {'ten', 'gioi'}
    line_code = [None] * n
    for k in range(0, n, batch):
        idx = list(range(k, min(n, k + batch)))
        rows = [{'i': i, 'giong': f"G{ac_lab[i] + 1}",
                 'cao': ('nu' if ac_spk.get(ac_lab[i], {}).get('gender') == 'female' else 'nam') if ac_spk else '?',
                 'goc': (texts_orig[i] or '')[:120], **({'viet': (texts_vi[i] or '')[:160]} if texts_vi else {})} for i in idx]
        known = ('Nhân vật đã xác định ở các đoạn trước (dùng lại đúng mã nếu là cùng người): '
                 + _json.dumps([{'ma': c, **v} for (c, v) in chars.items()], ensure_ascii=False)) if chars else ''
        data = None
        for _ in range(2):
            raw = web_llm.chat(SCRIPT_PROMPT.format(known=known, rows=_json.dumps(rows, ensure_ascii=False, indent=0)), log)
            data = _extract_json(raw)
            if isinstance(data, dict) and data.get('cau'):
                break
            log(f'   [WARN] AI phân vai trả kết quả không đọc được: {str(raw)[:120]!r}')
            data = None
        if not data:
            continue
        for c in data.get('nhan_vat') or []:
            try:
                code = str(c.get('ma')).strip()
                if code and code not in chars:
                    g = str(c.get('gioi', '')).strip().lower()
                    chars[code] = {'ten': str(c.get('ten') or code)[:40], 'gioi': 'nu' if g.startswith(('nu', 'nữ', 'f', 'woman')) else 'nam'}
            except AttributeError:
                continue
        for it in data.get('cau') or []:
            try:
                i = int(it.get('i'))
                code = str(it.get('ma')).strip()
            except (TypeError, ValueError, AttributeError):
                continue
            if 0 <= i < n and (code in chars or code.upper() == 'X'):
                line_code[i] = 'X' if code.upper() == 'X' and code not in chars else code
    got = sum(1 for c in line_code if c)
    if got < n * 0.6:                            # AI bỏ sót quá nhiều → không tin, dùng kết quả nghe giọng
        log(f'   [WARN] AI phân vai chỉ gán được {got}/{n} câu — dùng kết quả nghe giọng')
        return None
    # câu AI bỏ sót → theo nhóm giọng (mã AI hay gặp nhất trong cùng nhóm giọng), không có thì câu trước
    by_group = {}
    for i in range(n):
        if line_code[i] and line_code[i] != 'X':
            by_group.setdefault(ac_lab[i], []).append(line_code[i])
    real = [c for c in line_code if c and c != 'X']
    if not real:
        return None
    for i in range(n):
        if not line_code[i]:
            cand = by_group.get(ac_lab[i])
            line_code[i] = max(set(cand), key=cand.count) if cand else next((c for c in reversed(line_code[:i]) if c and c != 'X'), real[0])
    skip = line_code.count('X')
    order = sorted(set(line_code) - {'X'}, key=lambda c: -line_code.count(c))
    ids = {c: k for (k, c) in enumerate(order)}
    ids['X'] = -1                                # không phải lời thoại → không lồng tiếng
    speakers = {ids[c]: {'gender': 'female' if chars[c]['gioi'] == 'nu' else 'male', 'count': line_code.count(c),
                         'name': chars[c]['ten'], 'minor': False} for c in order}
    log('   AI phân vai theo kịch bản: ' + ', '.join(f"{s['name']} ({'nữ' if s['gender'] == 'female' else 'nam'}, {s['count']} câu)"
                                                for s in speakers.values())
        + (f' · bỏ {skip} dòng không phải lời thoại (nhạc, tiếng động…)' if skip else ''))
    return {'labels': [ids[c] for c in line_code], 'speakers': speakers}


def split_turns(video, segments, log=print, min_len=2.4, win=1.5, thr=0.38):
    """Đoạn Whisper dài gộp lời 2 người (đối đáp nhanh, không dấu câu, không ngừng) → tách ở ranh giới chữ nơi
    "dấu vân giọng" 1.5s trước và 1.5s sau khác hẳn nhau (cosine < thr; đo trên phim: khác người 0.21–0.26, cùng người 0.54–0.68). Cần 'words' [[start, end, chữ]] trong mỗi đoạn.
    → danh sách đoạn mới (đoạn không cần tách giữ nguyên)."""
    import numpy as np
    long_ = [s for s in segments if s.get('words') and s['end'] - s['start'] >= min_len and len(s['words']) >= 4]
    if not long_:
        return segments
    path = ensure_model(log)
    if not path or not available():
        return segments
    sess = _session(path)
    audio = load_audio(video)

    def emb(a, b):
        (i0, i1) = (max(0, int(a * SR)), min(len(audio), int(b * SR)))
        return embed(sess, audio[i0:i1]) if i1 - i0 > int(0.6 * SR) else None

    def cut(words):
        # ranh giới tốt nhất (giống nhau ít nhất) giữa 2 chữ, cách 2 đầu ≥ 0.8s; đệ quy tách tiếp 2 nửa
        (t0, t1) = (words[0][0], words[-1][1])
        if t1 - t0 < min_len or len(words) < 4:
            return [words]
        best = (1.0, None)
        for k in range(1, len(words)):
            b = words[k][0]
            if b - t0 < 1.2 or t1 - b < 1.2:           # mỗi bên ≥ 1.2s — ngắn hơn thì dấu vân giọng nhiễu
                continue
            (l, r) = (emb(max(t0, b - win), b), emb(b, min(t1, b + win)))
            if l is None or r is None:
                continue
            sim = float(np.dot(l, r))
            if sim < best[0]:
                best = (sim, k)
        if best[1] is None or best[0] >= thr:
            return [words]
        # bám vào chỗ ngắt tự nhiên gần nhất (±0.6s): sau dấu câu, hoặc khoảng ngừng giữa 2 chữ dài nhất — không cắt giữa từ
        k0 = best[1]
        near = [k for k in range(1, len(words)) if abs(words[k][0] - words[k0][0]) <= 0.6]
        punct = [k for k in near if words[k - 1][2].strip().endswith(('，', ',', '。', '？', '！', '?', '!', '、', '…'))]
        gaps = [j for j in near if words[j][0] - words[j - 1][1] >= 0.25]
        if punct:
            k = min(punct, key=lambda j: abs(j - k0))
        elif gaps:                              # có khoảng ngừng rõ → cắt ở khoảng ngừng dài nhất
            k = max(gaps, key=lambda j: words[j][0] - words[j - 1][1])
        else:                                   # không dấu câu: so giọng cửa sổ ngắn (0.9s) quanh điểm cắt để chọn đúng chữ
            def fine(j):
                b = words[j][0]
                (l, r) = (emb(max(t0, b - 0.9), b), emb(b, min(t1, b + 0.9)))
                return float(np.dot(l, r)) if l is not None and r is not None else 1.0
            k = min(near, key=lambda j: (fine(j), abs(j - k0)))
        return cut(words[:k]) + cut(words[k:])
    out = []
    n_split = 0
    for s in segments:
        if s not in long_:
            out.append(s)
            continue
        parts = cut(s['words'])
        n_split += len(parts) - 1
        for p in parts:
            text = ''.join(w[2] for w in p).strip()
            if text:
                out.append({'start': p[0][0], 'end': max(p[-1][1], p[0][0] + 0.2), 'text': text, 'words': p})
    if n_split:
        log(f'   Tách {n_split} chỗ đổi người nói giữa câu (đối đáp nhanh, bị nhận dạng gộp chung)', 'step')
    return out
