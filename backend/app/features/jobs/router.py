import asyncio
import json
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import load_settings
from .manager import TERMINAL, manager
from .models import AiPolishRequest, BurnJobRequest, ConfirmRequest, RegenRequest, SrtJobRequest, VideoJobRequest
from . import pipelines

router = APIRouter(prefix='/api/jobs', tags=['jobs'])


def _title(inp, prefix):
    name = inp.rsplit('/', 1)[-1] if inp.startswith('http') else os.path.basename(inp)
    return f'{prefix} · {name}'


# Loại job → (pipeline, tiền tố tiêu đề). Dùng chung cho tạo mới và chạy lại.
RUNNERS = {
    'review': (pipelines.run_video_pipeline, 'Review'),
    'reup': (pipelines.run_video_pipeline, 'Dịch & Reup'),
    'srt': (pipelines.run_srt_pipeline, 'Tách SRT'),
    'burn': (pipelines.run_burn_pipeline, 'Ghép phụ đề'),
}


def _start(kind, cfg):
    """Kiểm tra đầu vào → xếp hàng. Đang có job chạy thì job mới chờ lượt."""
    try:
        cfg['inp'] = pipelines.validate_input(cfg.get('inp', ''))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if kind == 'burn' and not os.path.isfile(cfg.get('srt_path', '')):
        raise HTTPException(400, 'Không tìm thấy file SRT.')
    cfg['out_dir'] = cfg.get('out_dir') or load_settings()['output_dir']
    (runner, prefix) = RUNNERS[kind]
    return manager.start(kind, cfg, runner, _title(cfg['inp'], prefix)).summary()


@router.get('')
def list_jobs():
    return [j.summary() for j in manager.list()]


@router.post('/video')
def create_video_job(req: VideoJobRequest):
    return _start(req.mode, req.model_dump())


@router.post('/srt')
def create_srt_job(req: SrtJobRequest):
    return _start('srt', req.model_dump())


@router.post('/burn')
def create_burn_job(req: BurnJobRequest):
    return _start('burn', req.model_dump())


@router.post('/{job_id}/resume')
def resume_job(job_id: str):
    """Tiếp tục job lỗi/đã huỷ từ bước bị hỏng (không làm lại các bước đã xong)."""
    try:
        job = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    if job.kind not in ('review', 'reup'):
        raise HTTPException(400, 'Chỉ job Review / Dịch & Reup tiếp tục được — loại này hãy chạy lại.')
    try:
        return manager.resume(job_id, RUNNERS[job.kind][0]).summary()
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post('/{job_id}/retry')
def retry_job(job_id: str):
    """Chạy lại job đã kết thúc với đúng cấu hình cũ — tạo job mới, job cũ giữ nguyên trong lịch sử."""
    try:
        old = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    if old.status not in TERMINAL:
        raise HTTPException(409, 'Job đang chạy — chờ xong hoặc dừng trước khi chạy lại.')
    if old.kind not in RUNNERS:
        raise HTTPException(400, 'Loại job này không chạy lại được.')
    return _start(old.kind, dict(old.config))


@router.get('/{job_id}')
def get_job(job_id: str):
    try:
        return manager.get(job_id).detail(with_logs=True)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post('/{job_id}/confirm')
def confirm(job_id: str, req: ConfirmRequest):
    try:
        job = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    if not job.waiting:
        raise HTTPException(409, 'Job không ở trạng thái chờ xác nhận.')
    job.resolve(req.model_dump())
    return {'ok': True}


@router.post('/{job_id}/scenes/{idx}/tts')
def regen_scene(job_id: str, idx: int, req: RegenRequest):
    try:
        job = manager.get(job_id)
        return pipelines.regenerate_scene(job, idx, req.text.strip(), req.scene)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except (ValueError, IndexError) as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@router.post('/{job_id}/ai-polish')
def ai_polish(job_id: str, req: AiPolishRequest):
    """AI hậu kỳ: đề xuất sửa lời / phụ đề / bỏ cảnh cho kịch bản đang xem trước (chỉ đề xuất, chưa áp dụng)."""
    from .postedit import suggest_edits
    try:
        job = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    if job.waiting != 'preview':
        raise HTTPException(409, 'Chỉ dùng được ở bước Xem trước.')
    try:
        edits = suggest_edits(req.scenes, job.kind, req.instruction, job.log)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    job.log(f'   [AI hậu kỳ] {len(edits)} đề xuất', 'info')
    return {'edits': edits}


@router.post('/{job_id}/qa')
def recheck_quality(job_id: str):
    """Chạy lại kiểm tra chất lượng cho video đã xuất của job."""
    try:
        job = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    if not job.result.get('output_path') or job.kind not in ('review', 'reup'):
        raise HTTPException(409, 'Job chưa có video để kiểm tra.')
    qa = pipelines.run_qa(job)
    job.save()
    return qa


@router.post('/{job_id}/cancel')
def cancel(job_id: str):
    try:
        return manager.cancel(job_id).summary()
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.delete('/{job_id}')
def delete(job_id: str):
    try:
        manager.delete(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {'ok': True}


@router.get('/{job_id}/stream')
async def stream(job_id: str, request: Request, since: int = 0):
    """SSE: đẩy log mới + trạng thái job. `since` = chỉ số log tuyệt đối đã nhận."""
    try:
        job = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))

    async def gen():
        cursor = since
        last_state = None
        while True:
            if await request.is_disconnected():
                break
            start = max(0, cursor - job.log_offset)
            new_logs = job.logs[start:]
            state = job.summary()
            state_key = json.dumps(state, sort_keys=True, default=str)
            if new_logs or state_key != last_state:
                payload = {'state': state, 'logs': new_logs, 'cursor': job.log_offset + len(job.logs)}
                if state_key != last_state and (job.waiting or state['status'] in TERMINAL):
                    payload['scenes'] = job.scenes
                cursor = payload['cursor']
                last_state = state_key
                yield f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            if state['status'] in TERMINAL and not new_logs:
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
