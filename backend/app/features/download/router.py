"""Tải video: xem trước link (nhiều link song song) và ảnh bìa qua backend (tránh trang gốc chặn hotlink)."""
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix='/api/download', tags=['download'])


class ProbeRequest(BaseModel):
    urls: list[str]


@router.post('/probe')
def probe(req: ProbeRequest):
    """Thông tin nhiều link cùng lúc (song song) — tiêu đề, thời lượng, ảnh bìa, nền tảng, lỗi nếu có."""
    from core.downloader import extract_url, probe as _probe
    urls = list(dict.fromkeys(extract_url(u) for u in req.urls if u.strip()))[:30]
    with ThreadPoolExecutor(4) as ex:
        return list(ex.map(_probe, urls))


class PosterRequest(BaseModel):
    image: str                     # link ảnh bìa (từ xem trước)
    title: str = ''
    out_dir: str = ''


@router.post('/poster')
def poster(req: PosterRequest):
    """Tải nhanh poster (ảnh bìa) → '<thư mục tải>/Poster/<tên phim>.jpg'."""
    import os
    from fastapi import HTTPException
    from app.config import load_settings
    from core.downloader import _safe_name, save_poster, unique_path
    out = os.path.join(req.out_dir or os.path.join(load_settings()['output_dir'], 'Downloads'), 'Poster')
    path = save_poster(req.image, unique_path(os.path.join(out, _safe_name(req.title or 'poster') + '.jpg')))
    if not path:
        raise HTTPException(502, 'Không tải được ảnh bìa (link ảnh hết hạn hoặc bị chặn).')
    return {'path': path}


_THUMBS: dict[str, tuple[bytes, str]] = {}


@router.get('/thumb')
def thumb(url: str, full: bool = False):
    """Ảnh bìa qua backend — trang gốc chặn hiển thị ảnh trực tiếp từ app (hotlink). Giữ tạm trong bộ nhớ."""
    import requests
    from fastapi import HTTPException, Response
    if not url.startswith('http'):
        raise HTTPException(400, 'URL không hợp lệ')
    key = ('full:' if full else '') + url
    hit = _THUMBS.get(key)
    if not hit:
        from core.downloader import _poster_candidates
        r, err = None, ''
        for u in (_poster_candidates(url) if full else [url]):     # full: bản gốc nét nhất (xem trước poster)
            try:
                r = requests.get(u, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                                         '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'})
                r.raise_for_status()
                break
            except requests.RequestException as e:
                (r, err) = (None, str(e))
        if r is None:
            raise HTTPException(502, f'Không tải được ảnh: {err}')
        hit = (r.content, r.headers.get('Content-Type', 'image/jpeg'))
        if len(_THUMBS) > 200:
            _THUMBS.clear()
        _THUMBS[key] = hit
    return Response(content=hit[0], media_type=hit[1], headers={'Cache-Control': 'max-age=3600'})
