import os
import threading
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import constants as C
from app.config import DATA_DIR, get_key
from core.utils import VOICE_SAMPLE_KINDS, voice_samples_dir

router = APIRouter(prefix='/api/voices', tags=['voices'])

_PREVIEW_DIR = os.path.join(DATA_DIR, 'voice_preview')
_cache: dict[tuple, dict] = {}
_busy = threading.Lock()


def _group(label, vid):
    if vid.startswith('vieneu3-'):
        return 'VieNeu 3'
    if vid.startswith('vieneu-'):
        return 'VieNeu'
    if vid.startswith('vi-VN-'):
        return 'Edge TTS'
    if vid.startswith('capcut-'):
        return 'CapCut'
    return 'Cao cấp (FPT.AI)'


def _gender(label, vid):
    l = (label + ' ' + vid).lower()
    if 'giọng bé' in l:
        return 'neutral'
    if 'nữ' in l or any(h in l for h in ('lena', 'mia', 'ban mai', 'thu minh', 'quỳnh anh', 'thảo chi', 'yến', 'hoaimy', 'ngọc', 'mỹ', 'trúc', 'linh san', 'lan nhi')):
        return 'female'
    if 'nam' in l or any(h in l for h in ('dũng', 'sơn', 'long', 'tùng', 'khánh', 'quang', 'huy')):
        return 'male'
    return 'neutral'


def sample_path(vid):
    keys = {vid}
    for p in ('vieneu3-', 'vieneu-'):
        if vid.startswith(p):
            keys.add(vid[len(p):])
    keys |= {k.replace('-', '_') for k in keys}
    keys |= {'fpt_' + k for k in list(keys)}
    for kind in VOICE_SAMPLE_KINDS:
        folder = voice_samples_dir(kind)
        if not os.path.isdir(folder):
            continue
        for k in keys:
            for ext in ('.wav', '.mp3'):
                p = os.path.join(folder, k + ext)
                if os.path.isfile(p):
                    return p
    return ''


_vieneu_ready = None


def _vieneu_available():
    """VieNeu cần runtime/Model Pack riêng — dò một lần (dò ổ đĩa khá chậm)."""
    global _vieneu_ready
    if _vieneu_ready is None:
        try:
            from core.tts_engine import _get_vieneu_cmd
            _vieneu_ready = _get_vieneu_cmd()[0] is not None
        except Exception:
            _vieneu_ready = False
    return _vieneu_ready


def availability(vid):
    """→ (dùng được?, cần gì). Giọng chưa dùng được sẽ tự đổi sang Edge TTS khi tạo giọng."""
    if vid.startswith('vi-VN-'):
        return True, ''
    if vid.startswith('capcut-'):
        return True, ''          # cookie CapCut tuỳ chọn
    if vid.startswith(('vieneu3-', 'vieneu-')):
        return (True, '') if _vieneu_available() else (False, 'Cần cài Model Pack VieNeu')
    return (True, '') if get_key('FPT_API_KEY') else (False, 'Cần FPT_API_KEY (Cài đặt → Key giọng đọc)')


@router.get('')
def list_voices():
    out = []
    for label, vid in C.VOICE_OPTIONS.items():
        ok, need = availability(vid)
        group = _group(label, vid)
        # tier: free = dùng ngay, miễn phí · key = cần API key (Cài đặt) · install = cần cài thêm trên máy
        tier = 'key' if group == 'Cao cấp (FPT.AI)' else 'install' if vid.startswith(('vieneu3-', 'vieneu-')) else 'free'
        out.append({'label': label, 'id': vid, 'group': group, 'gender': _gender(label, vid),
                    'sample': sample_path(vid), 'tier': tier, 'free': tier != 'key', 'available': ok, 'need': need})
    return out


class TestVoiceRequest(BaseModel):
    voice: str
    text: str = 'Đây là thử nghiệm giọng đọc, xin chào các bạn, chúc một ngày tốt lành.'


@router.post('/test')
def test_voice(req: TestVoiceRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, 'Câu thử đang trống.')
    key = (req.voice, text)
    hit = _cache.get(key)
    if hit and os.path.isfile(hit['path']):
        return {**hit, 'cached': True}
    if not _busy.acquire(timeout=1):
        raise HTTPException(409, 'Đang tạo giọng thử khác — đợi xong rồi bấm tiếp.')
    logs = []
    try:
        from app.features.jobs.pipelines import synthesize
        out_dir = os.path.join(_PREVIEW_DIR, uuid.uuid4().hex[:8])
        res = synthesize([{'voiceover': text, 'subtitle': text, 'clip_start': 0, 'clip_end': 5}], req.voice, out_dir,
                         lambda m, t=None: logs.append(str(m)))
        if not res or not res[0].get('tts_path') or not os.path.isfile(res[0]['tts_path']):
            raise HTTPException(500, 'Không tạo được audio thử. ' + ' | '.join(logs[-3:]))
        out = {'path': res[0]['tts_path'], 'duration': res[0].get('tts_duration', 0),
               'engine': res[0].get('_tts_engine_used', ''), 'logs': logs[-6:]}
        _cache[key] = out
        return {**out, 'cached': False}
    finally:
        _busy.release()
