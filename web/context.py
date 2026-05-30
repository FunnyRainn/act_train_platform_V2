from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


@dataclass(frozen=True)
class AppContext:
    templates: Jinja2Templates
    version: str


_context: AppContext | None = None


def set_context(context: AppContext) -> None:
    global _context
    _context = context


def get_context() -> AppContext:
    if _context is None:
        raise RuntimeError("App context has not been initialized")
    return _context


def page(request: Request, template: str, **context: Any) -> HTMLResponse:
    app_context = get_context()
    context.setdefault("version", app_context.version)
    return app_context.templates.TemplateResponse(request, template, context)


def api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))
