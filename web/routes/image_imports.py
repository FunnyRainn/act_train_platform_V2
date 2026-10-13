"""浏览器原图入口：原始请求体流式接收，禁止整批或整张无界读入内存。"""
import hashlib
import json
import threading
from PIL import UnidentifiedImageError

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from core import image_imports as service
from core.paths import UPLOADS_DIR
from core.utils import new_id
from web.context import api_error

router = APIRouter()
uploads = threading.BoundedSemaphore(service.LIMITS["parallel_uploads"])


@router.get("/api/image-imports/limits")
def limits():
    return service.LIMITS


@router.get("/api/image-imports")
def list_jobs(project_id: str):
    return service.list_jobs(project_id)


@router.post("/api/image-imports")
async def create(request: Request):
    try:
        # 10000条元数据通常不足数MiB；未知长度的请求同样有读取上限。
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 8 * 1024 * 1024: raise ValueError("文件清单超过8MiB")
            data.extend(chunk)
        return await run_in_threadpool(service.create_job, json.loads(data))
    except Exception as exc:
        raise api_error(exc)


@router.get("/api/image-imports/{job_id}")
def status(job_id: str, offset: int = 0, limit: int = 100):
    try: return service.status(job_id, offset, limit)
    except Exception as exc: raise api_error(exc)


@router.post("/api/image-imports/{job_id}/{action}")
def control(job_id: str, action: str):
    try:
        if action == "cancel": return service.cancel(job_id)
        if action == "resume": return service.resume(job_id)
        raise ValueError("未知任务操作")
    except Exception as exc: raise api_error(exc)


@router.put("/api/image-imports/{job_id}/files/{ordinal}")
async def upload(job_id: str, ordinal: int, request: Request):
    if not uploads.acquire(blocking=False):
        raise HTTPException(429, "同时最多上传两个文件，请稍后重试")
    temporary = None
    try:
        item = await run_in_threadpool(service.inspect_upload, job_id, ordinal)
        folder = service.child(UPLOADS_DIR, "image_imports")
        folder.mkdir(parents=True, exist_ok=True)
        temporary = service.child(folder, new_id("upload") + ".part")
        count, digest = 0, hashlib.sha256()
        with temporary.open("xb") as target:
            async for chunk in request.stream():
                count += len(chunk)
                if count > min(service.LIMITS["file_bytes"], item["byte_size"]):
                    raise ValueError("文件大小超出清单或32MiB限制")
                digest.update(chunk)
                await run_in_threadpool(target.write, chunk)
        if count != item["byte_size"]: raise ValueError("上传长度不完整，请重新选择原文件重试")
        return await run_in_threadpool(service.commit_image, job_id, ordinal, temporary, digest.hexdigest())
    except Exception as exc:
        # 请求中断不会误标成功，刷新后同一条目可以重试。已有成功条目不被失败覆盖。
        await run_in_threadpool(service.fail, job_id, ordinal, str(exc))
        if isinstance(exc, UnidentifiedImageError):
            raise HTTPException(400, "图片无法识别，请检查原图后重试")
        raise api_error(exc)
    finally:
        if temporary is not None:
            # 仅清理本请求新建的可重建part，不扫描目录；已转成正式资产的文件不存在于此路径。
            temporary.unlink(missing_ok=True)
        uploads.release()


@router.get("/api/frame-sets/{frame_set_id}/frames-page")
def frames_page(frame_set_id: str, offset: int = 0, limit: int = 100, frame_id: str = ""):
    try: return service.frames_page(frame_set_id, offset, limit, frame_id)
    except Exception as exc: raise api_error(exc)
