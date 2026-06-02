from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from core import store, video_ops
from core.runtime_paths import resolve_runtime_path
from web.context import api_error

router = APIRouter()


@router.get("/api/videos")
def list_videos(project_id: str | None = None) -> list[dict]:
    return store.list_videos(project_id)


@router.get("/api/video-assets")
def list_video_assets() -> list[dict]:
    return store.list_video_assets()


@router.post("/api/videos/upload")
async def upload_video(project_id: str = Form(...), file: UploadFile = File(...)) -> dict:
    try:
        data = await file.read()
        return video_ops.register_uploaded_video(project_id, file.filename or "video.mp4", data)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/videos/import")
async def import_video(request: Request) -> dict:
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
    try:
        return store.delete_frame_set(frame_set_id)
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/frame-sets")
def list_frame_sets(project_id: str | None = None) -> list[dict]:
    return store.list_frame_sets(project_id)


@router.get("/api/focus-regions")
def list_focus_regions(project_id: str | None = None) -> list[dict]:
    return store.list_focus_regions(project_id)


@router.post("/api/focus-regions")
async def save_focus_region(request: Request) -> dict:
    try:
        return store.save_focus_region(await request.json())
    except Exception as exc:
        raise api_error(exc)


@router.delete("/api/focus-regions/{region_id}")
def delete_focus_region(region_id: str) -> dict:
    try:
        return store.delete_focus_region(region_id)
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/frame-sets/{frame_set_id}/frames")
def list_frames(frame_set_id: str) -> list[dict]:
    try:
        return store.list_frames(frame_set_id)
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/frames/{frame_id}/image")
def frame_image(frame_id: str) -> FileResponse:
    try:
        frame = store.get_frame(frame_id)
        path = resolve_runtime_path(frame["path"], "帧图片", require_exists=True)
        return FileResponse(path)
    except Exception as exc:
        raise api_error(exc)
