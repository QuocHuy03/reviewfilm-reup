"""Trợ lý AI trong app — hỏi đáp cách dùng ReviewFilm Studio bằng tài khoản ChatGPT / Gemini web đã đăng nhập."""
import base64
import os
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import web_llm

from .guide import APP_GUIDE

router = APIRouter(prefix='/api/assistant', tags=['assistant'])

MAX_TURNS = 12
MAX_MSG_CHARS = 2000
MAX_LOG_LINES = 30
MAX_LAST_CHARS = 14000          # tin cuối được dài hơn (có thể kèm nội dung file .srt / .log người dùng gửi)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif')

NOT_READY_MSG = ('Trợ lý AI cần tài khoản ChatGPT hoặc Gemini. Vào Cài đặt (bánh răng dưới cùng thanh bên trái) → '
                 'tab "Tài khoản AI" → ChatGPT: bấm "Thêm tài khoản", hoặc Gemini: bấm "Đăng nhập Google". '
                 'Đăng nhập xong quay lại đây hỏi tiếp.')
EMPTY_MSG = 'Tài khoản AI chưa trả lời được (mạng chậm hoặc phiên hết hạn). Thử gửi lại sau ít giây nhé.'

PAGE_NAMES = {
    'home': 'Tổng quan', 'create': 'Tạo video', 'download': 'Tải video', 'studio': 'Studio',
    'subtitles': 'Phụ đề', 'voices': 'Giọng đọc', 'jobs': 'Lịch sử', 'settings': 'Cài đặt',
}
KIND_NAMES = {
    'review': 'Review phim', 'reup': 'Dịch & Reup', 'vietsub': 'Dịch phụ đề', 'srt': 'Tách SRT',
    'burn': 'Ghép phụ đề', 'download': 'Tải video',
}
STATUS_NAMES = {
    'queued': 'đang xếp hàng', 'running': 'đang chạy', 'waiting': 'đang chờ người dùng xác nhận',
    'done': 'hoàn thành', 'error': 'lỗi', 'cancelled': 'đã huỷ',
}

INSTRUCTIONS = """# VAI TRÒ
Bạn là "Trợ lý ReviewFilm" — chuyên viên hỗ trợ sản phẩm của ReviewFilm Studio {version}: app desktop Windows làm video
Review phim, Dịch & Reup (thuyết minh), Dịch phụ đề (vietsub + lồng tiếng), tải video / phim ngắn.
Người hỏi là người làm kênh video, thường không rành kỹ thuật. Bạn không phải ChatGPT hay Gemini — bạn là Trợ lý của app.

# MỤC TIÊU
Giúp người dùng làm xong việc nhanh nhất: chỉ đúng chỗ bấm, giải thích lỗi dễ hiểu, gợi ý cấu hình hợp lý cho máy và mục đích của họ.

# NGUỒN SỰ THẬT (ưu tiên từ trên xuống)
1. NGỮ CẢNH HIỆN TẠI — trang đang mở, job đang mở (trạng thái, lỗi, nhật ký): dữ liệu thật trên máy người dùng.
2. CẨM NANG APP — mô tả đúng giao diện và tính năng hiện có.
3. Ảnh / file người dùng gửi kèm.
Kiến thức chung chỉ dùng để giải thích khái niệm (SRT, FPS, GPU, nhận dạng giọng nói…), KHÔNG dùng để suy ra nút, tab, phím tắt hay tính năng của app.
Thứ không có trong 3 nguồn trên → nói rõ "Mình chưa thấy tính năng này trong app", đề xuất cách gần nhất CÓ THẬT, hoặc bấm "Hỗ trợ" ở thanh bên trái.

# CÁCH TRẢ LỜI THEO LOẠI CÂU HỎI
- "Làm sao / cách nào": 1 câu nói kết quả, rồi các bước đánh số — mỗi bước 1 thao tác, ghi rõ vị trí: Trang → tab → "Nút". Tối đa 7 bước.
  Thêm 1 dòng mẹo cuối chỉ khi thật sự có ích.
- Lỗi / sự cố — đúng khuôn:
  **Nguyên nhân:** 1–2 câu, nói thẳng, dựa trên dòng lỗi / nhật ký.
  **Cách sửa:** các bước đánh số, ưu tiên cách nhanh nhất (vd "Tiếp tục từ …" thay vì chạy lại từ đầu).
  **Nếu vẫn lỗi:** 1 phương án dự phòng.
  Trích nguyên văn dòng lỗi quan trọng trong `mã` để người dùng đối chiếu.
- "Nên chọn gì" (giọng, mức nhận dạng giọng nói, cấu hình…): 1 khuyến nghị rõ ràng trước + lý do 1 câu, rồi 1–2 lựa chọn khác kèm khi nào nên dùng.
- Khái niệm: giải thích ngắn bằng ví dụ gắn với app.
- Câu hỏi mơ hồ: trả lời theo cách hiểu khả dĩ nhất, nói rõ cách hiểu đó, rồi hỏi lại đúng 1 câu để chốt.

# CHẨN ĐOÁN KHI CÓ JOB ĐANG MỞ
1. Đọc trạng thái, dòng "Lỗi", và nhật ký cuối — tìm dòng [LỖI] / [WARN] gần nhất trước lúc job dừng.
2. Đối chiếu mục "LỖI THƯỜNG GẶP" trong cẩm nang; khớp thì dùng đúng cách xử lý ở đó.
3. Job HOÀN THÀNH mà nhật ký còn [LỖI] / [WARN] → đó là sự cố đã tự xử lý giữa chừng: báo kết quả cuối, chỉ nhắc cảnh báo nếu ảnh hưởng chất lượng.
   Job "đang chờ người dùng xác nhận" KHÔNG phải lỗi → hướng dẫn bước cần làm tiếp (sửa rồi bấm nút Xác nhận tương ứng).
4. Job đang chạy bình thường → nói đang ở bước nào và tiến độ; không khuyên dừng job nếu không cần.
5. Nhật ký không đủ để chắc → nói thẳng "nhật ký chưa đủ để kết luận", chỉ cách lấy thêm thông tin (mở Nhật ký ở Studio, gửi ảnh chụp màn hình).
   Không bịa nguyên nhân.

# ẢNH & FILE ĐÍNH KÈM
- Ảnh: nêu ngắn điều thấy được có liên quan (thông báo lỗi, nút, cấu hình đang chọn) rồi trả lời theo khuôn trên. Đọc chữ trong ảnh cẩn thận; chữ mờ thì nói không đọc rõ.
- File .srt / .log / .txt: chỉ ra đúng dòng (số dòng hoặc mốc thời gian) có vấn đề và cách sửa.

# VĂN PHONG
- Tiếng Việt tự nhiên, thân thiện, xưng "mình", gọi "bạn". Ngắn gọn: thường 60–180 từ; chỉ dài hơn khi cần nhiều bước.
- Tên nút / trang / tab đúng như giao diện, đặt trong ngoặc kép; phím tắt đặt trong `mã` (vd `Ctrl+B`).
- Markdown đơn giản: đoạn văn, danh sách, **đậm**, `mã`. Không bảng, không tiêu đề (#), không link ngoài, không emoji.
- Không lặp lại câu hỏi, không mở đầu sáo rỗng ("Câu hỏi hay!"), không kết bằng câu xã giao ("Hy vọng giúp được bạn").

# GIỚI HẠN
- Không hứa tính năng sắp có, không nói về mã nguồn / nội bộ app; không nêu tên công nghệ bên trong — dùng đúng tên trong giao diện (vd "Nhận dạng giọng nói").
- Không yêu cầu, không nhắc lại mật khẩu, API key, token, mã bản quyền của người dùng.
- Chỉ hướng dẫn thao tác trong app; không bảo sửa registry, file hệ thống hay cài phần mềm ngoài (trừ khi cẩm nang có ghi).
- Câu hỏi ngoài lề: trả lời 1–2 câu nếu đơn giản, rồi gợi ý quay lại việc làm video."""


class Msg(BaseModel):
    role: Literal['user', 'assistant']
    content: str


class AskReq(BaseModel):
    messages: list[Msg]
    job_id: Optional[str] = None
    page: Optional[str] = None
    images: list[str] = []          # ảnh đính kèm tin cuối (đường dẫn trả về từ /upload)


class UploadReq(BaseModel):
    name: str
    data: str                       # base64 (có hoặc không tiền tố data:…;base64,)


def _upload_dir():
    from app.config import DATA_DIR
    d = os.path.join(DATA_DIR, 'assistant_uploads')
    os.makedirs(d, exist_ok=True)
    return d


def _trim(text, n=MAX_MSG_CHARS):
    text = (text or '').strip()
    return text if len(text) <= n else text[:n] + ' …(đã cắt bớt)'


_CFG_LABELS = [
    # (khoá cấu hình, nhãn, hàm hiển thị) — chỉ những gì giúp chẩn đoán / tư vấn
    ('voice', 'Giọng đọc', str),
    ('dub_voice', 'Lồng tiếng Việt', lambda v: 'bật' if v else 'tắt'),
    ('burn_subtitles', 'Ghép phụ đề vào video', lambda v: 'bật' if v else 'tắt'),
    ('bilingual', 'Phụ đề song ngữ', lambda v: 'bật' if v else 'tắt'),
    ('extra_aspect', 'Xuất thêm khung', lambda v: str(v) if v else 'không'),
    ('remove_old_sub', 'Che phụ đề cũ', lambda v: 'bật' if v else 'tắt'),
    ('cover_quality', 'Kiểu che (Dịch phụ đề)', lambda v: {'fast': 'Nhanh', 'clean': 'Xoá sạch nét chữ'}.get(v, str(v))),
    ('hardsub_source', 'Video gốc có phụ đề in sẵn', lambda v: 'có' if v else 'không'),
    ('whisper_model', 'Mức nhận dạng giọng nói', lambda v: {'capcut': 'Online · nhanh nhất', 'tiny': 'Siêu nhanh', 'base': 'Nhanh', 'small': 'Cân bằng',
                                                         'medium': 'Chính xác', 'large': 'Chính xác nhất', 'large-v2': 'Chính xác cao', 'large-v3': 'Chính xác nhất'}.get(v, str(v))),
    ('device', 'Thiết bị', str),
    ('target_resolution', 'Khung hình xuất', str),
    ('ai_translate', 'Dịch bằng AI', lambda v: 'bật' if v else 'tắt (Google)'),
    ('quality', 'Chất lượng tải', str),
]


def _job_context(job_id):
    try:
        from app.features.jobs.manager import manager
        job = manager.get(job_id)
    except Exception:
        return ''
    lines = [
        f'- Loại job: {KIND_NAMES.get(job.kind, job.kind)}',
        f'- Tên: {job.title}',
        f'- Trạng thái: {STATUS_NAMES.get(job.status, job.status)}'
        + (f" (chờ ở bước {'sửa kịch bản / bản dịch' if job.waiting == 'script' else 'xem trước / hậu kỳ'})" if job.waiting else ''),
        f'- Bước hiện tại: {job.stage or "—"} · tiến độ {job.progress}%',
    ]
    if job.error:
        lines.append(f'- Lỗi khiến job dừng: {_trim(job.error, 800)}')
    try:
        if job.resumable():
            lines.append(f"- Có thể bấm \"Tiếp tục\" từ bước: {job.checkpoint.get('next_label', '')}")
    except Exception:
        pass
    cfg = job.config or {}
    shown = [f'{label}: {fmt(cfg[k])}' for (k, label, fmt) in _CFG_LABELS if k in cfg and cfg[k] not in (None, '')]
    if shown:
        lines.append('- Cấu hình chính: ' + ' · '.join(shown))
    res = job.result or {}
    outs = [f'{name}: {os.path.basename(str(res[k]))}' for (k, name) in (('output_path', 'video'), ('vi_srt', 'phụ đề Việt'),
                                                                           ('original_srt', 'phụ đề gốc')) if res.get(k)]
    outs += [f'bản khung khác: {os.path.basename(str(x))}' for x in res.get('output_variants') or []]
    if res.get('items'):
        ok = sum(1 for it in res['items'] if it.get('path'))
        outs.append(f"tải được {ok}/{len(res['items'])} mục")
    if (res.get('qa') or {}).get('score') is not None:
        outs.append(f"điểm chất lượng {res['qa']['score']}/100")
    if outs:
        lines.append('- Kết quả: ' + ' · '.join(outs))
    logs = [str(x.get('msg', '')).strip() for x in job.logs]
    # lỗi / cảnh báo trong nhật ký (gần nhất, không trùng) — tách riêng để không lẫn với dòng thường
    probs, seen = [], set()
    for m in reversed(logs):
        if ('[LỖI]' in m or '[WARN]' in m) and m not in seen:
            seen.add(m)
            probs.append(m)
        if len(probs) >= 10:
            break
    if probs:
        lines.append('- Lỗi / cảnh báo trong nhật ký (mới nhất trước):')
        lines += [f'    {_trim(m, 300)}' for m in probs]
        if job.status == 'done':
            lines.append('    (Job vẫn HOÀN THÀNH — các dòng trên là sự cố đã tự xử lý / bỏ qua giữa chừng, không phải job hỏng.)')
    tail = logs[-MAX_LOG_LINES:]
    if tail:
        lines.append(f'- {len(tail)} dòng nhật ký cuối:')
        lines += [f'    {_trim(m, 300)}' for m in tail]
    return '\n'.join(lines)


def _version():
    try:
        from app.config import APP_VERSION
        return '' if APP_VERSION in ('', 'dev') else f'v{APP_VERSION}'
    except Exception:
        return ''


def build_prompt(req: AskReq):
    v = _version()
    parts = [INSTRUCTIONS.replace(' {version}', f' {v}' if v else ''), '\n===== CẨM NANG APP =====', APP_GUIDE.strip()]
    ctx = []
    if req.page:
        ctx.append(f'- Người dùng đang ở trang: {PAGE_NAMES.get(req.page, req.page)}')
    if req.job_id:
        jc = _job_context(req.job_id)
        if jc:
            ctx.append('- Job đang mở trong Studio:\n' + jc)
    if ctx:
        parts += ['\n===== NGỮ CẢNH HIỆN TẠI =====', '\n'.join(ctx)]
    turns = [m for m in req.messages if m.content.strip()][-MAX_TURNS:]
    convo = '\n\n'.join(f"{'Người dùng' if m.role == 'user' else 'Trợ lý'}: {_trim(m.content, MAX_LAST_CHARS if k == len(turns) - 1 else MAX_MSG_CHARS)}"
                         for (k, m) in enumerate(turns))
    parts += ['\n===== CUỘC TRÒ CHUYỆN =====', convo,
              '\n===== NHIỆM VỤ =====\nViết câu trả lời tiếp theo của Trợ lý cho TIN NHẮN CUỐI của người dùng, đúng các quy tắc ở trên. '
              'Chỉ ghi nội dung trả lời (không ghi "Trợ lý:", không nhắc tới các mục "CẨM NANG" / "NGỮ CẢNH" của prompt này).']
    return '\n'.join(parts)


@router.post('/upload')
def upload(req: UploadReq):
    """Ảnh người dùng gửi kèm (ảnh chụp lỗi, giao diện…) → lưu tạm trong thư mục dữ liệu app → đường dẫn để hỏi kèm."""
    ext = os.path.splitext(req.name or '')[1].lower()
    if ext not in IMAGE_EXTS:
        raise HTTPException(400, 'Chỉ gửi kèm được ảnh PNG / JPG / WEBP / GIF.')
    raw = req.data.split(',', 1)[1] if req.data.startswith('data:') else req.data
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception:
        raise HTTPException(400, 'Ảnh lỗi, không đọc được.')
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, 'Ảnh quá lớn (tối đa 8 MB).')
    path = os.path.join(_upload_dir(), f'{uuid.uuid4().hex[:12]}{ext}')
    with open(path, 'wb') as f:
        f.write(data)
    return {'path': path}


@router.get('/status')
def status():
    s = web_llm.status()
    return {'ready': bool(s['chatgpt'] or s['gemini']), 'chatgpt': s['chatgpt'], 'gemini': s['gemini']}


@router.post('/ask')
def ask(req: AskReq):
    if not req.messages or req.messages[-1].role != 'user' or not req.messages[-1].content.strip():
        raise HTTPException(400, 'Hãy nhập câu hỏi.')
    if not web_llm.available():
        raise HTTPException(409, NOT_READY_MSG)
    root = os.path.abspath(_upload_dir())
    images = [p for p in req.images if os.path.isfile(p) and os.path.abspath(p).startswith(root)][:4]
    prompt = build_prompt(req)
    if images and web_llm.gemini_ready():
        # ảnh kèm theo → Gemini đọc ảnh (ChatGPT web trong app chỉ nhận chữ)
        answer = web_llm.gemini_files(prompt + f'\n(Người dùng gửi kèm {len(images)} ảnh — xem ảnh rồi trả lời.)', images,
                                      log_fn=lambda *_: None, timeout=240)
    else:
        if images:
            prompt += ('\n(Người dùng có gửi kèm ảnh nhưng hiện chưa đọc được ảnh vì chưa đăng nhập Gemini — trả lời dựa trên chữ; '
                       'cuối câu trả lời nhắc ngắn: muốn trợ lý xem ảnh thì đăng nhập Gemini trong Cài đặt → "Tài khoản AI".)')
        answer = web_llm.chat(prompt, log_fn=lambda *_: None, model='auto', timeout=180)
    import re
    # bỏ emoji (giao diện app dùng icon thật, không dùng emoji)
    answer = re.sub('[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]', '', answer or '')
    answer = re.sub(r'[ \t]{2,}', ' ', answer).strip()
    if answer.startswith('Trợ lý:'):
        answer = answer[len('Trợ lý:'):].strip()
    if not answer:
        raise HTTPException(502, EMPTY_MSG)
    return {'answer': answer}
