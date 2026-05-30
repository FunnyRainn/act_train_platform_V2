from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.context import page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return page(request, "index.html", page_id="overview")


@router.get("/labels", response_class=HTMLResponse)
def labels_page(request: Request) -> HTMLResponse:
    return page(request, "labels.html", page_id="labels")


@router.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request) -> HTMLResponse:
    return page(request, "projects.html", page_id="projects")


@router.get("/videos", response_class=HTMLResponse)
def videos_page(request: Request) -> HTMLResponse:
    return page(request, "videos.html", page_id="videos")


@router.get("/annotate", response_class=HTMLResponse)
def annotate_page(request: Request) -> HTMLResponse:
    return page(request, "annotate.html", page_id="annotate")


@router.get("/datasets", response_class=HTMLResponse)
def datasets_page(request: Request) -> HTMLResponse:
    return page(request, "datasets.html", page_id="datasets")


@router.get("/training", response_class=HTMLResponse)
def training_page(request: Request) -> HTMLResponse:
    return page(request, "training.html", page_id="training")


@router.get("/packages", response_class=HTMLResponse)
def packages_page(request: Request) -> HTMLResponse:
    return page(request, "packages.html", page_id="packages")
