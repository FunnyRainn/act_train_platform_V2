from __future__ import annotations

from fastapi import APIRouter, Request

from core import store
from web.context import api_error

router = APIRouter()


@router.get("/api/labels")
def list_labels() -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_labels` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return store.list_labels()


@router.post("/api/labels")
async def save_label(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `save_label` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return store.upsert_label(await request.json())
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/projects")
def list_projects() -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_projects` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return store.list_projects()


@router.post("/api/projects")
async def save_project(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `save_project` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return store.save_project(await request.json())
    except Exception as exc:
        raise api_error(exc)
