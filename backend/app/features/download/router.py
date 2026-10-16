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


_THUMBS: dict[str, tuple[bytes, str]] = {}


@router.get('/thumb')
def thumb(url: str):
    """Ảnh bìa qua backend — trang gốc chặn hiển thị ảnh trực tiếp từ app (hotlink). Giữ tạm trong bộ nhớ."""
    import requests
    from fastapi import HTTPException, Response
    if not url.startswith('http'):
        raise HTTPException(400, 'URL không hợp lệ')
    hit = _THUMBS.get(url)
    if not hit:
        try:
            r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                                       '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'})
            r.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(502, f'Không tải được ảnh: {e}')
        hit = (r.content, r.headers.get('Content-Type', 'image/jpeg'))
        if len(_THUMBS) > 200:
            _THUMBS.clear()
        _THUMBS[url] = hit
    return Response(content=hit[0], media_type=hit[1], headers={'Cache-Control': 'max-age=3600'})
