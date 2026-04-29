from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from webui.routes.api import router as api_router
from webui.routes.events import router as events_router
from webui.routes.pages import router as pages_router
from webui.routes.ws import router as ws_router


def create_app() -> FastAPI:
    app = FastAPI(title="sql-agent web UI")

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(pages_router)
    app.include_router(api_router, prefix="/api")
    app.include_router(events_router, prefix="/events")
    app.include_router(ws_router, prefix="/ws")

    return app


app = create_app()
