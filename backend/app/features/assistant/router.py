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
MAX_LOG_LINES = 40
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

INSTRUCTIONS = """Bạn là chuyên viên hỗ trợ của ReviewFilm Studio — app desktop làm video review phim, dịch & reup, dịch phụ đề.
Quy tắc trả lời:
- Luôn trả lời bằng tiếng Việt, thân thiện, ngắn gọn, đi thẳng vào việc.
- Câu hỏi "làm sao / cách nào" → trả lời bằng các bước đánh số (1. 2. 3.), mỗi bước một thao tác.
- Gọi đúng tên nút / trang / tab như trong giao diện, đặt trong ngoặc kép, vd: Cài đặt → "Tài khoản AI" → "Thêm tài khoản".
- CHỈ dựa vào CẨM NANG bên dưới và ngữ cảnh được cung cấp. Không bịa tính năng, nút hay phím tắt không có trong cẩm nang.
- Không chắc thì nói thẳng là không chắc và gợi ý cách kiểm tra (xem Nhật ký job, bấm "Hỗ trợ" ở thanh bên để liên hệ).
- Khi có thông tin job (trạng thái, lỗi, nhật ký): giải thích lỗi bằng lời dễ hiểu, nêu nguyên nhân có khả năng nhất và cách sửa cụ thể.
- Dùng markdown đơn giản: đoạn văn, danh sách, **in đậm**, `mã`. Không dùng bảng, không dùng tiêu đề lớn, không chèn link lạ.
- KHÔNG dùng emoji / biểu tượng cảm xúc — viết chữ thuần, chuyên nghiệp.
- Câu hỏi không liên quan tới app: trả lời ngắn nếu đơn giản, rồi gợi ý quay lại việc làm video."""


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
        lines.append(f'- Lỗi: {_trim(job.error, 800)}')
    try:
        if job.resumable():
            lines.append(f"- Có thể bấm \"Tiếp tục\" từ bước: {job.checkpoint.get('next_label', '')}")
    except Exception:
        pass
    logs = list(job.logs[-MAX_LOG_LINES:])
    if logs:
        lines.append('- Nhật ký gần nhất:')
        lines += [f"    {_trim(str(x.get('msg', '')), 300)}" for x in logs]
    return '\n'.join(lines)


def build_prompt(req: AskReq):
    parts = [INSTRUCTIONS, '\n===== CẨM NANG APP =====', APP_GUIDE.strip()]
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
              '\nHãy viết câu trả lời tiếp theo của Trợ lý cho tin nhắn cuối của người dùng (chỉ nội dung trả lời, không lặp lại "Trợ lý:").']
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
