import hashlib
import os
import subprocess
import tempfile
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.srt_utils import cues_to_srt, parse_srt

router = APIRouter(prefix='/api', tags=['media'])

_MEDIA_EXT = {'.mp4', '.mkv', '.mov', '.webm', '.m4v', '.avi', '.ts', '.flv', '.wmv',
              '.wav', '.mp3', '.m4a', '.aac', '.ogg', '.flac', '.png', '.jpg', '.jpeg',
              '.ttf', '.otf'}       # font đóng gói / font người dùng thêm — để khung xem trước phụ đề hiện đúng font
_VIDEO_EXT = {'.mp4', '.mkv', '.mov', '.webm', '.m4v', '.avi', '.ts', '.flv', '.wmv'}


@router.get('/media')
def media(path: str):
    """Phát file video/audio local (hỗ trợ Range để tua)."""
    if os.path.splitext(path)[1].lower() not in _MEDIA_EXT:
        raise HTTPException(400, 'Định dạng không hỗ trợ.')
    if not os.path.isfile(path):
        raise HTTPException(404, 'Không tìm thấy file.')
    return FileResponse(path)


_FILMSTRIP_H = 72                 # chiều cao mỗi khung trong dải (px) — frontend tự suy bề ngang = tổng ngang / số khung
_filmstrip_locks: dict[str, threading.Lock] = {}
_filmstrip_locks_guard = threading.Lock()


def _filmstrip_dir() -> str:
    base = os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()
    d = os.path.join(base, 'VA_AutoReview', 'filmstrips')
    os.makedirs(d, exist_ok=True)
    return d


@router.get('/filmstrip')
def filmstrip(path: str, n: int = 80):
    """Dải khung hình (filmstrip) của video: 1 ảnh JPEG ghép `n` khung hình cách đều toàn video,
    cao `_FILMSTRIP_H`px. Timeline cắt từng khúc dải cho mỗi clip → hiện hình như CapCut mà chỉ tải 1 ảnh.
    Có cache theo (đường dẫn + thời điểm sửa + n) nên chỉ dựng lần đầu."""
    from core.utils import FFMPEG_EXE, get_video_duration
    if os.path.splitext(path)[1].lower() not in _VIDEO_EXT:
        raise HTTPException(400, 'Chỉ dựng được dải khung hình cho video.')
    if not os.path.isfile(path):
        raise HTTPException(404, 'Không tìm thấy file.')
    n = max(8, min(240, int(n)))
    try:
        st = os.stat(path)
        key = hashlib.md5(f'{path}|{st.st_mtime_ns}|{st.st_size}|{n}|{_FILMSTRIP_H}'.encode('utf-8')).hexdigest()
    except OSError:
        raise HTTPException(404, 'Không đọc được file.')
    out = os.path.join(_filmstrip_dir(), key + '.jpg')
    if not os.path.isfile(out):
        with _filmstrip_locks_guard:
            lock = _filmstrip_locks.setdefault(key, threading.Lock())
        with lock:
            if not os.path.isfile(out):                     # kiểm lại trong khoá: request khác có thể vừa dựng xong
                dur = get_video_duration(path) or 0.0
                if dur <= 0:
                    raise HTTPException(422, 'Không đọc được thời lượng video.')
                fps = max(0.01, n / dur)
                tmp = out + '.tmp.jpg'
                cmd = [FFMPEG_EXE, '-y', '-v', 'error', '-i', path, '-frames:v', '1',
                       '-vf', f'fps={fps:.6f},scale=-2:{_FILMSTRIP_H},tile={n}x1', '-q:v', '5', tmp]
                try:
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    os.replace(tmp, out)
                except subprocess.CalledProcessError as e:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    raise HTTPException(500, 'ffmpeg dựng dải khung hình lỗi: ' + (e.stderr.decode('utf-8', 'replace')[-200:] if e.stderr else ''))
    return FileResponse(out, media_type='image/jpeg', headers={'Cache-Control': 'max-age=86400'})


@router.get('/srt')
def read_srt(path: str):
    if not path.lower().endswith('.srt') or not os.path.isfile(path):
        raise HTTPException(404, 'Không tìm thấy file SRT.')
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        return {'path': path, 'cues': parse_srt(f.read())}


class SrtSave(BaseModel):
    path: str
    cues: list[dict]


@router.put('/srt')
def save_srt(req: SrtSave):
    if not req.path.lower().endswith('.srt'):
        raise HTTPException(400, 'Đường dẫn phải là file .srt')
    os.makedirs(os.path.dirname(os.path.abspath(req.path)), exist_ok=True)
    with open(req.path, 'w', encoding='utf-8') as f:
        f.write(cues_to_srt(req.cues))
    return {'ok': True, 'path': req.path}
