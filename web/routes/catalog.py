from __future__ import annotations

from fastapi import APIRouter, Request

from core import store
from web.context import api_error

router = APIRouter()


@router.get("/api/labels")
def list_labels() -> list[dict]:
    return store.list_labels()


@router.post("/api/labels")
async def save_label(request: Request) -> dict:
    try:
        return store.upsert_label(await request.json())
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/projects")
def list_projects() -> list[dict]:
    return store.list_projects()


@router.post("/api/projects")
async def save_project(request: Request) -> dict:
    try:
        return store.save_project(await request.json())
    except Exception as exc:
        raise api_error(exc)
