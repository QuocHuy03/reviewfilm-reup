import asyncio
import json
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import load_settings
from .manager import TERMINAL, manager
from .models import (AiPolishRequest, BurnJobRequest, ConfirmRequest, DownloadJobRequest, DraftRequest, PublishRequest, ReeditRequest, RegenRequest, SrtJobRequest,
                     ThumbnailRequest, VideoJobRequest)
from . import pipelines, vietsub

router = APIRouter(prefix='/api/jobs', tags=['jobs'])


def _title(inp, prefix):
    name = inp.rsplit('/', 1)[-1] if inp.startswith('http') else os.path.basename(inp)
    return f'{prefix} · {name}'


# Loại job → (pipeline, tiền tố tiêu đề). Dùng chung cho tạo mới và chạy lại.
RUNNERS = {
    'review': (pipelines.run_video_pipeline, 'Review'),
    'reup': (pipelines.run_video_pipeline, 'Dịch & Reup'),
    'vietsub': (vietsub.run_vietsub_pipeline, 'Dịch phụ đề'),
    'srt': (pipelines.run_srt_pipeline, 'Tách SRT'),
    'burn': (pipelines.run_burn_pipeline, 'Ghép phụ đề'),
    'download': (pipelines.run_download_pipeline, 'Tải video'),
}


MIN_FREE_GB = 3


def _check_disk(out_dir):
    """Thư mục tạm nằm cùng ổ với thư mục xuất (video tải về + audio + clip) — hết chỗ giữa chừng thì job hỏng."""
    import shutil
    try:
        os.makedirs(out_dir, exist_ok=True)
        free = shutil.disk_usage(out_dir).free / 1024 ** 3
    except OSError:
        return
    if free < MIN_FREE_GB:
        drive = os.path.splitdrive(os.path.abspath(out_dir))[0] or out_dir
        raise HTTPException(400, f'Ổ {drive} chỉ còn {free:.1f} GB trống — cần ít nhất {MIN_FREE_GB} GB để xử lý video. '
                                 'Dọn bớt ổ hoặc đổi thư mục xuất sang ổ khác (Cài đặt).')


def _start(kind, cfg):
    """Kiểm tra đầu vào → xếp hàng. Đang có job chạy thì job mới chờ lượt."""
    try:
        cfg['inp'] = pipelines.validate_input(cfg.get('inp', ''))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if kind == 'burn' and not os.path.isfile(cfg.get('srt_path', '')):
        raise HTTPException(400, 'Không tìm thấy file SRT.')
    cfg['out_dir'] = cfg.get('out_dir') or load_settings()['output_dir']
    _check_disk(cfg['out_dir'])
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


@router.post('/download')
def create_download(req: DownloadJobRequest):
    """Tải 1 hoặc nhiều video từ link — 1 job, tải lần lượt."""
    from core.downloader import detect_platform, extract_url
    urls = list(dict.fromkeys(extract_url(u) for u in req.urls if u.strip()))
    urls = [u for u in urls if u.startswith('http')]
    if not urls:
        raise HTTPException(400, 'Chưa có link hợp lệ (cần bắt đầu bằng http…).')
    out_dir = req.out_dir or os.path.join(load_settings()['output_dir'], 'Downloads')
    _check_disk(out_dir)
    cfg = {'urls': urls, 'quality': req.quality, 'out_dir': out_dir, 'titles': req.titles}
    title = f'Tải video · {detect_platform(urls[0])[1]} · {urls[0].split("?")[0][-40:]}' if len(urls) == 1 else f'Tải video · {len(urls)} link'
    return manager.start('download', cfg, pipelines.run_download_pipeline, title).summary()


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


@router.post('/{job_id}/reedit')
def reedit_job(job_id: str, req: ReeditRequest):
    """Mở lại hậu kỳ cho video đã xong: job mới dùng lại kịch bản cũ, đọc lại giọng rồi dừng ở bước Xem trước.
    Bỏ qua Whisper + Vision AI + viết kịch bản (vài phút). Job cũ giữ nguyên trong lịch sử."""
    try:
        old = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    # Job lỗi / huỷ mà mất thư mục tạm (không "Tiếp tục" được) nhưng đã có kịch bản → vẫn dùng lại được kịch bản
    has_script = any((s.get('voiceover') or '').strip() for s in old.scenes or [])
    if old.kind not in ('review', 'reup') or old.status not in ('done', 'error', 'cancelled') or not has_script:
        raise HTTPException(409, 'Chỉ mở lại được job Review / Reup đã có kịch bản.')
    video = old.result.get('video_path') or (old.config.get('inp') if os.path.isfile(old.config.get('inp', '')) else '')
    if not video or not os.path.isfile(video):
        raise HTTPException(409, 'Không còn file video gốc (video tải từ link đã bị dọn cùng thư mục tạm) — hãy Chạy lại từ đầu.')
    cfg = dict(old.config)
    if req.voice:
        cfg['voice'] = req.voice
    cfg.update(script_edit=False, scene_preview=True, auto_post=False)   # giữ nguyên kịch bản đã duyệt, dừng ở Xem trước
    keep = ('voiceover', 'subtitle', 'clip_start', 'clip_end', 'original_text', 'speaker', 'scene_id', 'description')
    scenes = [{k: s[k] for k in keep if k in s} for s in old.scenes if not s.get('excluded')]
    base = os.path.splitext(os.path.basename(old.result.get('output_path') or video))[0]
    base = base.removesuffix('_review').removesuffix('_reup')
    checkpoint = {'done': 'edit', 'next_label': 'Tạo giọng đọc', 'video_path': video, 'base': base,
                  'lang': cfg.get('source_lang', 'auto'), 'transcript': {'segments': []}, 'mixer': {}}
    result = {k: old.result[k] for k in ('video_path', 'original_srt', 'film') if old.result.get(k)}
    (runner, prefix) = RUNNERS[old.kind]
    name = old.title.split(' · ', 1)[-1]
    job = manager.start_seeded(old.kind, cfg, runner, f'{prefix} · {name} (hậu kỳ lại)', scenes, checkpoint, result)
    job.log(f'[HẬU KỲ LẠI] Dùng lại kịch bản {len(scenes)} cảnh từ job {old.id} — bỏ qua Whisper & AI viết kịch bản', 'info')
    return job.summary()


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


@router.put('/{job_id}/draft')
def save_draft(job_id: str, req: DraftRequest):
    """Tự lưu chỉnh sửa đang làm ở bước chờ (sửa kịch bản / xem trước) — quay lại màn hình hay mở lại app vẫn còn."""
    import time
    try:
        job = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    stage = job.waiting or (job.draft or {}).get('waiting')
    if not stage:
        raise HTTPException(409, 'Job không ở bước chờ chỉnh sửa.')
    job.draft = {'waiting': stage, 'scenes': req.scenes, 'mixer': req.mixer, 'at': time.time()}
    job.save()
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


# ---------- Hậu kỳ: AI quét chữ Trung trên video gốc → vùng che theo từng đoạn (sửa được trước khi dựng) ----------
_scans: dict[str, dict] = {}


class TextScanRequest(BaseModel):
    interval: float = Field(1.0, ge=0.5, le=5)
    scenes: list[dict] = Field(default_factory=list)      # cảnh đang sửa (khoảng hình có thể đã đổi so với job)


@router.post('/{job_id}/text-scan')
def start_text_scan(job_id: str, req: TextScanRequest):
    import threading
    from core import text_cover
    try:
        job = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    video = job.result.get('video_path') or job.config.get('inp', '')
    if not video or not os.path.isfile(video):
        raise HTTPException(409, 'Không còn file video gốc để quét.')
    if not text_cover.available():
        raise HTTPException(409, 'Chưa cài bộ quét chữ (rapidocr) — khởi động lại app để tự cài.')
    st = _scans.get(job_id)
    if st and st.get('running'):
        return st
    st = _scans[job_id] = {'running': True, 'done': 0, 'total': 0, 'regions': None, 'error': ''}
    ranges = pipelines.scan_ranges(req.scenes or job.scenes, job.kind == 'review')

    def work():
        try:
            def prog(d, t):
                st.update(done=d, total=t)
            regs = text_cover.scan(video, ranges, req.interval, log_fn=lambda m, *a: None,
                                   should_stop=lambda: st.get('cancel', False), progress=prog)
            st['regions'] = None if st.get('cancel') else regs      # huỷ giữa chừng → không coi là "không có chữ"
        except Exception as e:
            st['error'] = str(e)[:300]
        finally:
            if st.get('regions') is not None:
                st['done'] = st['total'] = max(st['done'], st['total'])
            st['running'] = False
    threading.Thread(target=work, daemon=True, name=f'text-scan-{job_id}').start()
    return st


@router.get('/{job_id}/text-scan')
def get_text_scan(job_id: str):
    return _scans.get(job_id) or {'running': False, 'done': 0, 'total': 0, 'regions': None, 'error': ''}


@router.post('/{job_id}/text-scan/cancel')
def cancel_text_scan(job_id: str):
    st = _scans.get(job_id)
    if st:
        st['cancel'] = True
    return st or {}


class RedubRequest(BaseModel):
    voice: str = ''
    voice_female: str = ''
    dub_by_gender: bool = False
    dub_orig_volume: int = Field(20, ge=0, le=100)
    char_voices: dict[str, str] = Field(default_factory=dict)   # {mã nhân vật: giọng} — đổi giọng từng nhân vật
    reuse_cast: bool = True                                     # giữ phân vai lần trước (không phân tích lại)


class SubBoxRequest(BaseModel):
    inp: str
    target_resolution: str = '1920x1080'
    crop_box: list[float] = Field(default_factory=list)
    crop_fill: bool = True


@router.post('/detect-sub-box')
def detect_sub_box(req: SubBoxRequest):
    """AI dò chỗ phụ đề cũ trên video (24 khung rải cả phim, ~30 giây) → vùng che % khung xuất."""
    import time
    from core import text_cover
    from .vietsub import auto_cover_box
    if not os.path.isfile(req.inp):
        raise HTTPException(400, 'Chọn file video trên máy để dò.')
    if not text_cover.available():
        raise HTTPException(409, 'Chưa cài bộ quét chữ (rapidocr) — khởi động lại app để tự cài.')
    t = time.time()
    (_, _, dur) = text_cover._probe(req.inp)
    regs = text_cover.scan(req.inp, text_cover.sample_ranges(dur), 1.0, log_fn=lambda *a: None)
    (w, h) = [int(v) for v in req.target_resolution.split('x')]
    box = auto_cover_box({'crop_box': req.crop_box, 'crop_fill': req.crop_fill}, regs, req.inp, w, h)
    return {'box': box, 'found': box is not None, 'seconds': round(time.time() - t, 1)}


@router.post('/{job_id}/redub')
def redub_job(job_id: str, req: RedubRequest):
    """Dịch phụ đề đã xong → job mới LỒNG TIẾNG từ bản dịch có sẵn (không chạy lại Whisper / dịch). Video cũ giữ nguyên."""
    try:
        old = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    if old.kind != 'vietsub' or old.status != 'done':
        raise HTTPException(409, 'Chỉ lồng tiếng lại được job Dịch phụ đề đã xong.')
    video = old.result.get('video_path') or (old.config.get('inp') if os.path.isfile(old.config.get('inp', '')) else '')
    if not video or not os.path.isfile(video):
        raise HTTPException(409, 'Không còn file video gốc (video tải từ link đã bị dọn) — hãy chạy lại từ đầu.')
    vi = old.result.get('vi_srt') or ''
    if not os.path.isfile(vi):
        raise HTTPException(409, 'Không còn file phụ đề tiếng Việt của job này.')
    cfg = dict(old.config)
    cfg.update(inp=video, vi_srt_path=vi, orig_srt_path=old.result.get('original_srt') or '', dub_voice=True,
               voice=req.voice or cfg.get('voice', ''), voice_female=req.voice_female, dub_by_gender=req.dub_by_gender and bool(req.voice_female),
               dub_orig_volume=req.dub_orig_volume, script_edit=True, char_voices=req.char_voices, cast_reuse=None)
    if old.result.get('dub_units'):              # câu lồng tiếng theo thời gian nói thật + vai từng câu (phân tích trên SRT gốc)
        cfg['dub_plan_reuse'] = {'units': old.result['dub_units'], 'res': old.result.get('dub_cast') if req.reuse_cast else None}
    if req.reuse_cast and old.result.get('cast_labels') and old.result.get('cast'):
        cfg['cast_reuse'] = {'labels': old.result['cast_labels'],
                             'speakers': {str(c['id']): {'gender': c['gender'], 'count': c['count'], 'name': c['name']} for c in old.result['cast']}}
    (runner, prefix) = RUNNERS['vietsub']
    name = old.title.split(' · ', 1)[-1]
    job = manager.start('vietsub', cfg, runner, f'{prefix} · {name} (lồng tiếng)')
    return job.summary()


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


def _done_video_job(job_id):
    try:
        job = manager.get(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    if not job.result.get('output_path') or job.kind not in ('review', 'reup'):
        raise HTTPException(409, 'Job chưa có video.')
    return job


@router.post('/{job_id}/publish')
def make_publish(job_id: str, req: PublishRequest):
    """AI viết bài đăng theo nền tảng (YouTube, Shorts, TikTok, Facebook, Instagram) + thumbnail."""
    from .publish import generate
    job = _done_video_job(job_id)
    try:
        pack = generate(job, req.platforms, req.tone, req.extra, job.log)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    job.save()
    return pack


@router.post('/{job_id}/publish/thumbnail')
def edit_thumbnail(job_id: str, req: ThumbnailRequest):
    from .publish import redo_thumbnail
    job = _done_video_job(job_id)
    try:
        pack = redo_thumbnail(job, req.index, req.text, job.log)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    job.save()
    return pack


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
