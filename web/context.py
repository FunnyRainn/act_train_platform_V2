from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


@dataclass(frozen=True)
class AppContext:
    """用途：说明 Web 应用装配和请求上下文 中 `AppContext` 的职责和调用边界。
    入参：无。
    返回：类定义本身不直接返回值；实例方法按各自说明返回。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    templates: Jinja2Templates
    version: str


_context: AppContext | None = None


def set_context(context: AppContext) -> None:
    """用途：说明 Web 应用装配和请求上下文 中 `set_context` 的职责和调用边界。
    入参：context，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    global _context
    _context = context


def get_context() -> AppContext:
    """用途：说明 Web 应用装配和请求上下文 中 `get_context` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    if _context is None:
        raise RuntimeError("App context has not been initialized")
    return _context


def page(request: Request, template: str, **context: Any) -> HTMLResponse:
    """用途：说明 Web 应用装配和请求上下文 中 `page` 的职责和调用边界。
    入参：request、template、**context，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    app_context = get_context()
    context.setdefault("version", app_context.version)
    return app_context.templates.TemplateResponse(request, template, context)


def api_error(exc: Exception) -> HTTPException:
    """用途：说明 Web 应用装配和请求上下文 中 `api_error` 的职责和调用边界。
    入参：exc，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))
