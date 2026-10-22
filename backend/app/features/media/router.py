import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.srt_utils import cues_to_srt, parse_srt

router = APIRouter(prefix='/api', tags=['media'])

_MEDIA_EXT = {'.mp4', '.mkv', '.mov', '.webm', '.m4v', '.avi', '.ts', '.flv', '.wmv',
              '.wav', '.mp3', '.m4a', '.aac', '.ogg', '.flac', '.png', '.jpg', '.jpeg',
              '.ttf', '.otf'}       # font đóng gói / font người dùng thêm — để khung xem trước phụ đề hiện đúng font


@router.get('/media')
def media(path: str):
    """Phát file video/audio local (hỗ trợ Range để tua)."""
    if os.path.splitext(path)[1].lower() not in _MEDIA_EXT:
        raise HTTPException(400, 'Định dạng không hỗ trợ.')
    if not os.path.isfile(path):
        raise HTTPException(404, 'Không tìm thấy file.')
    return FileResponse(path)


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
