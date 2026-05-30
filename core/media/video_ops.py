from __future__ import annotations

from pathlib import Path

import cv2

from core import store
from core.paths import ASSETS_DIR, FRAMES_DIR, UPLOADS_DIR
from core.utils import copy_file, new_id, safe_name


def probe_video(path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"无法打开视频: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    duration = frame_count / fps if fps > 0 else 0
    return {
        "fps": fps,
        "frame_count": frame_count,
        "duration_sec": duration,
        "width": width,
        "height": height,
    }


def _create_product_video_from_asset(project_id: str, asset: dict) -> dict:
    video_id = new_id("video")
    src = Path(asset["stored_path"])
    dst = UPLOADS_DIR / project_id / f"{video_id}_{safe_name(src.stem)}{src.suffix}"
    copy_file(src, dst)
    return store.create_video(
        {
            "id": video_id,
            "project_id": project_id,
            "asset_id": asset["id"],
            "name": asset["name"],
            "source_type": "asset_copy",
            "path": dst,
            "fps": asset["fps"],
            "frame_count": asset["frame_count"],
            "duration_sec": asset["duration_sec"],
            "width": asset["width"],
            "height": asset["height"],
        }
    )


def register_uploaded_video(project_id: str, filename: str, bytes_data: bytes) -> dict:
    asset_id = new_id("asset")
    suffix = Path(filename).suffix or ".mp4"
    save_path = ASSETS_DIR / f"{asset_id}_{safe_name(Path(filename).stem)}{suffix}"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(bytes_data)
    meta = probe_video(save_path)
    asset = store.create_video_asset(
        {
            "id": asset_id,
            "name": Path(filename).stem,
            "source_type": "upload",
            "original_path": filename,
            "stored_path": save_path,
            **meta,
        }
    )
    return _create_product_video_from_asset(project_id, asset)


def register_imported_video(project_id: str, source_path: str, copy_to_platform: bool = False) -> dict:
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"视频不存在: {src}")
    asset_id = new_id("asset")
    stored = ASSETS_DIR / f"{asset_id}_{safe_name(src.stem)}{src.suffix}"
    copy_file(src, stored)
    meta = probe_video(stored)
    asset = store.create_video_asset(
        {
            "id": asset_id,
            "name": src.stem,
            "source_type": "import_copy" if copy_to_platform else "import_ref_copy",
            "original_path": src,
            "stored_path": stored,
            **meta,
        }
    )
    return _create_product_video_from_asset(project_id, asset)


def extract_frames(
    video_id: str,
    sample_every_n_frames: int,
    max_frames: int = 0,
    jpeg_quality: int = 95,
    name: str | None = None,
    overwrite: bool = False,
) -> dict:
    video = store.get_video(video_id)
    if sample_every_n_frames <= 0:
        raise ValueError("抽帧间隔必须大于 0")
    frame_set_name = (name or f"{video['name']} 抽帧 {sample_every_n_frames}").strip()
    if not frame_set_name:
        raise ValueError("帧集名称不能为空")
    existing = store.find_frame_set_by_name(video["project_id"], frame_set_name)
    if existing:
        if not overwrite:
            raise ValueError(f"帧集名称已存在: {frame_set_name}")
        store.delete_frame_set(existing["id"])

    video_path = Path(video["path"])
    frame_set_id = new_id("frameset")
    output_dir = FRAMES_DIR / video["project_id"] / frame_set_id
    output_dir.mkdir(parents=True, exist_ok=True)
    store.create_frame_set(
        {
            "id": frame_set_id,
            "project_id": video["project_id"],
            "video_id": video_id,
            "name": frame_set_name,
            "output_dir": output_dir,
            "sample_every_n_frames": sample_every_n_frames,
            "max_frames": max_frames,
            "status": "running",
            "config": {
                "jpeg_quality": jpeg_quality,
                "width": video["width"],
                "height": video["height"],
            },
        }
    )

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        store.update_frame_set_status(frame_set_id, "failed", 0)
        raise ValueError(f"无法打开视频: {video_path}")

    saved_paths: list[Path] = []
    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_index % sample_every_n_frames == 0:
            save_path = output_dir / f"frame_{frame_index:06d}.jpg"
            cv2.imwrite(str(save_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
            saved_paths.append(save_path)
            if max_frames > 0 and len(saved_paths) >= max_frames:
                break
        frame_index += 1
    cap.release()

    store.insert_frames(frame_set_id, video_id, saved_paths)
    store.update_frame_set_status(frame_set_id, "ready", len(saved_paths))
    return store.get_frame_set(frame_set_id)
