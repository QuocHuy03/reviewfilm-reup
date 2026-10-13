

"""Autosave Studio (ADR-008, Giai doan 1) — luu ben trang thai chinh sua tay
(_scenes/mixer/video_path/stage) xuong dia, song sot qua crash/dong nham app.

Schema la TAP CON CHINH THUC cua Project Format tuong lai (ADR-008 rang buoc 1) —
CHI luu business state (text/timing/uid/style/tts_path...), KHONG serialize
object UI/QWidget nao (rang buoc 4). Ghi ATOMIC (temp file + os.replace, dung
khuon core/billing_ledger.py da co) + giu 1 ban "last known good" o session.json.bak
(rang buoc 5) + checksum sha256 de phat hien file cat cut giua chung (rang buoc 6).
"""
from __future__ import annotations
import os
import json
import time
import hashlib
import logging
from core.project_type import DEFAULT_PROJECT_TYPE, normalize_project_type, validate_project_type_strict
log = logging.getLogger(__name__)
_SESSION_DIR = os.path.join(os.path.expandvars('%APPDATA%\\AutoReviewStudio'), 'autosave')
SESSION_FILE = os.path.join(_SESSION_DIR, 'session.json')
BAK_FILE = os.path.join(_SESSION_DIR, 'session.json.bak')
SCHEMA_VERSION = 1
_MIGRATION_DEFAULTED_FLAG = '_migration_project_type_defaulted'
def _payload_checksum(payload):
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return 'sha256:' + hashlib.sha256(blob.encode('utf-8')).hexdigest()
def _save_atomic(path, data):
    os.makedirs(_SESSION_DIR, exist_ok=True)
    tmp_path = path + f'''.tmp{os.getpid()}'''
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
def _read_and_validate(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        chk = data.get('checksum')
        if chk and _payload_checksum({k: v for (k, v) in data.items() if k != 'checksum'}) != chk:
            return None
        if 'project_type' not in data:
            data[_MIGRATION_DEFAULTED_FLAG] = True
        return data
    except Exception:
        return None
def save_session(scenes, video_path, output_dir, stage, mixer_settings=None, audio_temp_dir='', app_version='', studio_review_charge_id='', studio_review_cost=0, studio_review_req_mins=None, studio_review_video_path='', project_type=None):
    _pt_canonical = None
    if project_type is not None:
        _pt_canonical = validate_project_type_strict(project_type)
    try:
        current = _read_and_validate(SESSION_FILE)
        if current is not None:
            current = {k: v for (k, v) in current.items() if not k.startswith('_migration_')}
            _save_atomic(BAK_FILE, current)
        payload = {'schema_version': SCHEMA_VERSION, 'saved_at': time.time(), 'app_version': app_version, 'video_path': video_path, 'output_dir': output_dir, 'stage': stage, 'scenes': scenes, 'mixer_settings': mixer_settings or {}, 'audio_temp_dir': audio_temp_dir, 'studio_review_charge_id': studio_review_charge_id or '', 'studio_review_cost': studio_review_cost or 0, 'studio_review_req_mins': studio_review_req_mins, 'studio_review_video_path': studio_review_video_path or ''}
        if _pt_canonical is not None:
            payload['project_type'] = _pt_canonical
        payload['checksum'] = _payload_checksum(payload)
        _save_atomic(SESSION_FILE, payload)
        return True
    except Exception:
        return False
def load_session():
    data = _read_and_validate(SESSION_FILE)
    if data is None:
        data = _read_and_validate(BAK_FILE)
    if data is None:
        return
    if data.pop(_MIGRATION_DEFAULTED_FLAG, False):
        log.warning("Session cũ không có project_type; tạm dùng mặc định 'review' trong phiên này. Field sẽ được lưu khi luồng project state được nối ở Batch B (ADR-010).")
        data['project_type'] = DEFAULT_PROJECT_TYPE
    else:
        _raw = data.get('project_type')
        _norm = normalize_project_type(_raw)
        if _norm != _raw:
            log.warning("project_type không hợp lệ (%r), dùng mặc định '%s'.", _raw, _norm)
            data['project_type'] = _norm
    return data
def clear_session():
    for p in (SESSION_FILE, BAK_FILE):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
def session_file_exists():
    return os.path.exists(SESSION_FILE) or os.path.exists(BAK_FILE)
def referenced_audio_dirs():
    refs = set()
    for path in (SESSION_FILE, BAK_FILE):
        try:
            data = _read_and_validate(path)
        except Exception:
            continue
        if not data:
            continue
        at = data.get('audio_temp_dir') or ''
        if at:
            refs.add(os.path.normcase(os.path.normpath(at)))
        for s in data.get('scenes') or []:
            tp = s.get('tts_path') if isinstance(s, dict) else None
            if tp:
                refs.add(os.path.normcase(os.path.normpath(os.path.dirname(tp))))
    return refs
def backup_corrupt_session_files():
    ts = time.strftime('%Y%m%d-%H%M%S')
    ok = True
    for (src, suffix) in ((SESSION_FILE, 'json'), (BAK_FILE, 'bak')):
        try:
            if os.path.exists(src):
                dst = os.path.join(_SESSION_DIR, f'''session.corrupt.{ts}.{suffix}''')
                os.replace(src, dst)
        except Exception:
            ok = False
    return ok