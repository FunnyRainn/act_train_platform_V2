from __future__ import annotations

from pathlib import Path

import cv2

from . import store
from .paths import FRAMES_DIR, UPLOADS_DIR
from .utils import copy_file, new_id, safe_name


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


def register_uploaded_video(project_id: str, filename: str, bytes_data: bytes) -> dict:
    video_id = new_id("video")
    suffix = Path(filename).suffix or ".mp4"
    save_path = UPLOADS_DIR / project_id / f"{video_id}_{safe_name(Path(filename).stem)}{suffix}"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(bytes_data)
    meta = probe_video(save_path)
    return store.create_video(
        {
            "id": video_id,
            "project_id": project_id,
            "name": Path(filename).stem,
            "source_type": "upload",
            "path": save_path,
            **meta,
        }
    )


def register_imported_video(project_id: str, source_path: str, copy_to_platform: bool = False) -> dict:
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"视频不存在: {src}")
    video_id = new_id("video")
    if copy_to_platform:
        dst = UPLOADS_DIR / project_id / f"{video_id}_{safe_name(src.stem)}{src.suffix}"
        copy_file(src, dst)
        path = dst
        source_type = "import_copy"
    else:
        path = src
        source_type = "import_ref"
    meta = probe_video(path)
    return store.create_video(
        {
            "id": video_id,
            "project_id": project_id,
            "name": src.stem,
            "source_type": source_type,
            "path": path,
            **meta,
        }
    )


def extract_frames(video_id: str, sample_every_n_frames: int, max_frames: int = 0, jpeg_quality: int = 95) -> dict:
    video = store.get_video(video_id)
    if sample_every_n_frames <= 0:
        raise ValueError("抽帧间隔必须大于 0")
    video_path = Path(video["path"])
    frame_set_id = new_id("frameset")
    output_dir = FRAMES_DIR / video["project_id"] / frame_set_id
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_set = store.create_frame_set(
        {
            "id": frame_set_id,
            "project_id": video["project_id"],
            "video_id": video_id,
            "name": f"{video['name']} 抽帧 {sample_every_n_frames}",
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
