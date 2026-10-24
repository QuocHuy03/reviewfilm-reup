from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_env_into_process

load_env_into_process()

from app.features.download.router import router as download_router  # noqa: E402
from app.features.glossary.router import router as glossary_router  # noqa: E402
from app.features.jobs.router import router as jobs_router  # noqa: E402
from app.features.media.router import router as media_router  # noqa: E402
from app.features.settings.router import router as settings_router  # noqa: E402
from app.features.voices.router import router as voices_router  # noqa: E402

app = FastAPI(title='ReviewFilm API', version='2.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

for r in (jobs_router, download_router, voices_router, settings_router, media_router, glossary_router):
    app.include_router(r)


@app.on_event('startup')
def _startup():
    from core.downloader import auto_update
    auto_update()          # yt-dlp mới nhất (ngầm, 1 lần/tuần)


@app.get('/api/health')
def health():
    return {'ok': True}


@app.on_event('startup')
def warm_fonts():
    import threading
    from core.fonts import families
    threading.Thread(target=families, daemon=True, name='warm-fonts').start()


@app.on_event('startup')
def warm_whisper():
    """Tải sẵn model Whisper đang chọn trong Cài đặt (chỉ lần đầu / khi đổi model)."""
    import threading
    from app.config import load_settings
    from core.transcriber import prefetch_model
    st = load_settings()
    threading.Thread(target=prefetch_model, args=(st.get('whisper_model') or 'base', st.get('output_dir') or ''),
                     daemon=True, name='warm-whisper').start()
