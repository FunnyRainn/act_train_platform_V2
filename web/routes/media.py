from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from core import store, video_ops
from core.runtime_paths import resolve_runtime_path
from web.context import api_error

router = APIRouter()


@router.get("/api/videos")
def list_videos(project_id: str | None = None) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_videos` 的职责和调用边界。
    入参：project_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return store.list_videos(project_id)


@router.get("/api/video-assets")
def list_video_assets() -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_video_assets` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return store.list_video_assets()


@router.post("/api/videos/upload")
async def upload_video(project_id: str = Form(...), file: UploadFile = File(...)) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `upload_video` 的职责和调用边界。
    入参：project_id、file，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        data = await file.read()
        return video_ops.register_uploaded_video(project_id, file.filename or "video.mp4", data)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/videos/import")
async def import_video(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `import_video` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return video_ops.register_imported_video(
            payload["project_id"],
            payload["path"],
            bool(payload.get("copy_to_platform", False)),
        )
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/frame-sets/extract")
async def extract_frames(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `extract_frames` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return video_ops.extract_frames(
            payload["video_id"],
            int(payload.get("sample_every_n_frames") or 5),
            int(payload.get("max_frames") or 0),
            int(payload.get("jpeg_quality") or 95),
            payload.get("name"),
            bool(payload.get("overwrite", False)),
        )
    except Exception as exc:
        raise api_error(exc)


@router.delete("/api/frame-sets/{frame_set_id}")
def delete_frame_set(frame_set_id: str) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `delete_frame_set` 的职责和调用边界。
    入参：frame_set_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return store.delete_frame_set(frame_set_id)
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/frame-sets")
def list_frame_sets(project_id: str | None = None) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_frame_sets` 的职责和调用边界。
    入参：project_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return store.list_frame_sets(project_id)


@router.get("/api/focus-regions")
def list_focus_regions(project_id: str | None = None) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_focus_regions` 的职责和调用边界。
    入参：project_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    return store.list_focus_regions(project_id)


@router.post("/api/focus-regions")
async def save_focus_region(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `save_focus_region` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return store.save_focus_region(await request.json())
    except Exception as exc:
        raise api_error(exc)


@router.delete("/api/focus-regions/{region_id}")
def delete_focus_region(region_id: str) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `delete_focus_region` 的职责和调用边界。
    入参：region_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return store.delete_focus_region(region_id)
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/frame-sets/{frame_set_id}/frames")
def list_frames(frame_set_id: str) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_frames` 的职责和调用边界。
    入参：frame_set_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return store.list_frames(frame_set_id)
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/frames/{frame_id}/image")
def frame_image(frame_id: str) -> FileResponse:
    """用途：说明 Web 路由、请求校验和页面 API 中 `frame_image` 的职责和调用边界。
    入参：frame_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        frame = store.get_frame(frame_id)
        path = resolve_runtime_path(frame["path"], "帧图片", require_exists=True)
        return FileResponse(path)
    except Exception as exc:
        raise api_error(exc)
