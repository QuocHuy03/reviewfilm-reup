from fastapi import APIRouter
from pydantic import BaseModel

from core import user_glossary

router = APIRouter(prefix='/api/glossary', tags=['glossary'])


class Entry(BaseModel):
    goc: str = ''        # chữ gốc (tiếng Trung…) — AI dịch đúng theo "viet"
    sai: str = ''        # cách dịch sai — dịch xong tự thay thành "viet"
    viet: str


class Entries(BaseModel):
    entries: list[Entry]


@router.get('')
def get_glossary():
    return {'entries': user_glossary.load()}


@router.put('')
def put_glossary(req: Entries):
    """Ghi đè cả từ điển (màn hình quản lý từ điển)."""
    return {'entries': user_glossary.save([e.model_dump() for e in req.entries])}


@router.post('')
def add_entries(req: Entries):
    """Thêm / cập nhật vài mục (vd "Tìm & thay" có tích Lưu vào từ điển)."""
    return {'entries': user_glossary.add([e.model_dump() for e in req.entries])}
