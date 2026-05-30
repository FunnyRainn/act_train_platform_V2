from __future__ import annotations

from fastapi import APIRouter, Request

from core import annotation_ops, prelabel_ops, store
from web.context import api_error

router = APIRouter()


@router.get("/api/frame-sets/{frame_set_id}/annotations")
def list_annotations(frame_set_id: str, frame_id: str | None = None) -> list[dict]:
    try:
        return store.list_annotations(frame_set_id, frame_id)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/annotations/frame")
async def save_frame_annotations(request: Request) -> list[dict]:
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
    try:
        return store.list_tracks(frame_set_id)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/tracks/{track_id}/interpolate")
async def interpolate_track(track_id: str, request: Request) -> dict:
    try:
        payload = await request.json()
        return annotation_ops.interpolate_track(payload["frame_set_id"], track_id)
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/prelabel")
async def prelabel(request: Request) -> dict:
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
    try:
        payload = await request.json()
        return prelabel_ops.clear_unconfirmed_prelabels(payload["frame_set_id"])
    except Exception as exc:
        raise api_error(exc)


@router.post("/api/prelabel/confirm-all")
async def confirm_all_prelabel(request: Request) -> dict:
    try:
        payload = await request.json()
        return prelabel_ops.confirm_all_prelabels(payload["frame_set_id"])
    except Exception as exc:
        raise api_error(exc)
