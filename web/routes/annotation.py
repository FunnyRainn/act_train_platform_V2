from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from core import annotation_ops, prelabel_ops, store
from web.context import api_error

router = APIRouter()


@router.get("/api/frame-sets/{frame_set_id}/annotations-snapshot")
def get_annotation_snapshot(frame_set_id: str, frame_id: str):
    """为新工作台返回标注及修订，旧列表接口继续兼容。"""
    try:
        return store.annotation_snapshot(frame_set_id, frame_id)
    except Exception as exc:
        raise api_error(exc)


@router.put("/api/annotations/frame")
async def save_annotation_snapshot(request: Request):
    """有修订的整帧保存；冲突返回409，绝不静默覆盖其他编辑。"""
    try:
        payload = await request.json()
        revision = payload.get("revision")
        if not isinstance(revision, str) or len(revision) != 64:
            raise ValueError("保存标注必须携带有效修订")
        return store.replace_frame_annotations(payload["project_id"], payload["frame_set_id"], payload["frame_id"],
            payload.get("annotations") or [], expected_revision=revision, return_snapshot=True)
    except store.AnnotationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/frame-sets/{frame_set_id}/annotations")
def list_annotations(frame_set_id: str, frame_id: str | None = None) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_annotations` 的职责和调用边界。
    入参：frame_set_id、frame_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return store.list_annotations(frame_set_id, frame_id)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/annotations/frame")
async def save_frame_annotations(request: Request) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `save_frame_annotations` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return store.replace_frame_annotations(
            payload["project_id"],
            payload["frame_set_id"],
            payload["frame_id"],
            payload.get("annotations") or [],
        )
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/tracks")
async def create_track(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `create_track` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return store.create_or_get_track(
            payload["project_id"],
            payload["frame_set_id"],
            payload["label_code"],
            payload.get("track_id"),
        )
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/frame-sets/{frame_set_id}/tracks")
def list_tracks(frame_set_id: str) -> list[dict]:
    """用途：说明 Web 路由、请求校验和页面 API 中 `list_tracks` 的职责和调用边界。
    入参：frame_set_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        return store.list_tracks(frame_set_id)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/tracks/{track_id}/interpolate")
async def interpolate_track(track_id: str, request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `interpolate_track` 的职责和调用边界。
    入参：track_id、request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return annotation_ops.interpolate_track(payload["frame_set_id"], track_id)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/prelabel")
async def prelabel(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `prelabel` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return prelabel_ops.run_prelabel(
            payload["frame_set_id"],
            payload["model_path"],
            float(payload.get("conf") or 0.25),
        )
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/prelabel/clear")
async def clear_prelabel(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `clear_prelabel` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return prelabel_ops.clear_unconfirmed_prelabels(payload["frame_set_id"])
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/prelabel/confirm-all")
async def confirm_all_prelabel(request: Request) -> dict:
    """用途：说明 Web 路由、请求校验和页面 API 中 `confirm_all_prelabel` 的职责和调用边界。
    入参：request，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取请求体、调用业务服务、访问模板上下文或返回 HTTP 响应。
    异常/失败语义：参数缺失、资源不存在或业务异常时，沿用原有 HTTPException 或异常传播语义。
    """

    try:
        payload = await request.json()
        return prelabel_ops.confirm_all_prelabels(payload["frame_set_id"])
    except Exception as exc:
        raise api_error(exc)
