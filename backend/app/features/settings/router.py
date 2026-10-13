import os
import shutil
import subprocess
import sys

from fastapi import APIRouter
from pydantic import BaseModel

from app import constants as C
from app import config

router = APIRouter(prefix='/api', tags=['settings'])

SPEEDS = ['0.85x (chậm hơn)', '0.9x', '0.95x', '1.0x (mặc định)', '1.05x', '1.1x', '1.15x', '1.2x', '1.3x (nhanh hơn)']


@router.get('/options')
def options():
    return {
        'languages': list(C.LANGUAGE_MAP.keys()),
        'whisper_models': C.WHISPER_MODELS,
        'devices': C.COMPUTE_DEVICES,
        'speeds': SPEEDS,
        'sub_styles': {k: v for k, v in C.SUBTITLE_STYLE_PRESETS.items() if v},
        'sub_layouts': C.SUBTITLE_LAYOUT_PRESETS,
        'sub_sources': list(C.SUBTITLE_SOURCE_OPTIONS.keys()),
    }


@router.get('/settings')
def get_settings():
    return config.load_settings()


@router.put('/settings')
def put_settings(patch: dict):
    return config.save_settings(patch)


@router.get('/keys')
def get_keys():
    return config.get_api_keys_masked()


@router.get('/fonts')
def list_fonts(refresh: bool = False):
    """Font dùng được cho phụ đề: hệ thống + font người dùng thêm. vi=False → thiếu dấu tiếng Việt."""
    from core.fonts import families
    return families(refresh=refresh)


class FontImport(BaseModel):
    path: str


@router.post('/fonts/import')
def import_font(req: FontImport):
    from fastapi import HTTPException
    from core.fonts import import_font as _imp
    try:
        return _imp(req.path)
    except ValueError as e:
        raise HTTPException(400, str(e))


class KeysRequest(BaseModel):
    values: dict[str, str]


@router.put('/keys')
def put_keys(req: KeysRequest):
    config.save_api_keys(req.values)
    return config.get_api_keys_masked()


_gpu_cache = None


def _gpu_name():
    global _gpu_cache
    if _gpu_cache is not None:
        return _gpu_cache
    exe = shutil.which('nvidia-smi')
    name = ''
    if exe:
        try:
            r = subprocess.run([exe, '--query-gpu=name', '--format=csv,noheader'], capture_output=True, text=True,
                               timeout=5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            name = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ''
        except Exception:
            name = ''
    _gpu_cache = name
    return name


def _web_ai_status():
    from core import web_llm
    return web_llm.status(force=True)


@router.get('/web-ai')
def web_ai():
    return _web_ai_status()


@router.get('/system')
def system():
    from core.utils import FFMPEG_EXE, FFPROBE_EXE, get_free_space_gb
    out_dir = config.load_settings()['output_dir']
    probe = out_dir if os.path.isdir(out_dir) else os.path.splitdrive(os.path.abspath(out_dir))[0] + os.sep
    return {
        'version': config.APP_VERSION,
        'python': sys.version.split()[0],
        'ffmpeg': os.path.isfile(FFMPEG_EXE) or bool(shutil.which(FFMPEG_EXE)),
        'ffprobe': os.path.isfile(FFPROBE_EXE) or bool(shutil.which(FFPROBE_EXE)),
        'gpu': _gpu_name(),
        'free_gb': round(get_free_space_gb(probe), 1),
        'keys': {k['name']: k['set'] for k in config.get_api_keys_masked()},
        'web_ai': _web_ai_status(),
    }
