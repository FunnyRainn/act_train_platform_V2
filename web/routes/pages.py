from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.context import page

router = APIRouter()


@router.get("/task-annotate", response_class=HTMLResponse)
def task_annotate_page(request: Request) -> HTMLResponse:
    """统一任务标注入口；旧矩形工作台保留，不自动迁移旧标注。"""
    return page(request, "task_annotate.html", page_id="task_annotate")


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """用途：说明 Web 路由、请求校验和页面 API 中 `index` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return page(request, "index.html", page_id="overview")


@router.get("/labels", response_class=HTMLResponse)
def labels_page(request: Request) -> HTMLResponse:
    """用途：说明 Web 路由、请求校验和页面 API 中 `labels_page` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return page(request, "labels.html", page_id="labels")


@router.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request) -> HTMLResponse:
    """用途：说明 Web 路由、请求校验和页面 API 中 `projects_page` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return page(request, "projects.html", page_id="projects")


@router.get("/videos", response_class=HTMLResponse)
def videos_page(request: Request) -> HTMLResponse:
    """用途：说明 Web 路由、请求校验和页面 API 中 `videos_page` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return page(request, "videos.html", page_id="videos")


@router.get("/annotate", response_class=HTMLResponse)
def annotate_page(request: Request) -> HTMLResponse:
    """用途：说明 Web 路由、请求校验和页面 API 中 `annotate_page` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return page(request, "annotate.html", page_id="annotate")


@router.get("/datasets", response_class=HTMLResponse)
def datasets_page(request: Request) -> HTMLResponse:
    """用途：说明 Web 路由、请求校验和页面 API 中 `datasets_page` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return page(request, "datasets.html", page_id="datasets")


@router.get("/training", response_class=HTMLResponse)
def training_page(request: Request) -> HTMLResponse:
    """用途：说明 Web 路由、请求校验和页面 API 中 `training_page` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return page(request, "training.html", page_id="training")


@router.get("/packages", response_class=HTMLResponse)
def packages_page(request: Request) -> HTMLResponse:
    """用途：说明 Web 路由、请求校验和页面 API 中 `packages_page` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return page(request, "packages.html", page_id="packages")
