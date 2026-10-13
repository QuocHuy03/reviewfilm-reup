from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_env_into_process

load_env_into_process()

from app.features.jobs.router import router as jobs_router  # noqa: E402
from app.features.media.router import router as media_router  # noqa: E402
from app.features.settings.router import router as settings_router  # noqa: E402
from app.features.voices.router import router as voices_router  # noqa: E402

app = FastAPI(title='ReviewFilm API', version='2.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

for r in (jobs_router, voices_router, settings_router, media_router):
    app.include_router(r)


@app.get('/api/health')
def health():
    return {'ok': True}


@app.on_event('startup')
def warm_fonts():
    import threading
    from core.fonts import families
    threading.Thread(target=families, daemon=True, name='warm-fonts').start()
