from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from colayout.api.orientation_routes import router as orientation_router
from colayout.api.routes import router

ROOT = Path(__file__).resolve().parents[3]
KENNEY_DIR = ROOT / "kenney_furniture-kit" / "Models" / "OBJ format"
WEB_DIST = ROOT / "web" / "dist"


def create_app() -> FastAPI:
    load_dotenv(ROOT / ".env")
    app = FastAPI(title="Co-Layout Viewer API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(orientation_router)

    if KENNEY_DIR.is_dir():
        app.mount("/kenney", StaticFiles(directory=str(KENNEY_DIR)), name="kenney")
    if WEB_DIST.is_dir():
        app.mount("/app", StaticFiles(directory=str(WEB_DIST), html=True), name="app")

    return app


app = create_app()
