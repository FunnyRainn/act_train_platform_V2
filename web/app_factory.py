from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.db import init_db
from core.paths import PROJECT_ROOT
from web.context import AppContext, set_context
from web.routes import annotation, bootstrap, catalog, datasets, media, packages, pages, training

VERSION = "v1.2.0.0"


def create_app() -> FastAPI:
    app = FastAPI(title="act_train_platform", version=VERSION.removeprefix("v"))
    templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
    app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")
    set_context(AppContext(templates=templates, version=VERSION))

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    app.include_router(pages.router)
    app.include_router(bootstrap.router)
    app.include_router(catalog.router)
    app.include_router(media.router)
    app.include_router(annotation.router)
    app.include_router(datasets.router)
    app.include_router(training.router)
    app.include_router(packages.router)
    return app
