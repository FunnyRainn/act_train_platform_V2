from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.db import init_db
from core.paths import PROJECT_ROOT
from web.context import AppContext, set_context
from web.routes import annotation, bootstrap, catalog, datasets, media, packages, pages, training

VERSION = "V2.4.0.1"


def create_app() -> FastAPI:
    """用途：说明 Web 应用装配和请求上下文 中 `create_app` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    app = FastAPI(title="act_train_platform", version=VERSION.removeprefix("v"))
    templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
    app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")
    set_context(AppContext(templates=templates, version=VERSION))

    @app.get("/version")
    def version() -> dict[str, str]:
        """返回训练平台版本，供 V1/V2 同机部署时核对进程身份。"""

        return {"version": VERSION}

    @app.on_event("startup")
    def on_startup() -> None:
        """用途：说明 Web 应用装配和请求上下文 中 `on_startup` 的职责和调用边界。
        入参：无。
        返回：保持原函数既有返回类型和返回内容。
        副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
        异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
        """

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
