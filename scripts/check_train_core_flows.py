from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _write_tiny_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 48))
    if not writer.isOpened():
        raise RuntimeError("无法创建测试视频")
    for index in range(8):
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        frame[:, :, 1] = 40 + index * 20
        cv2.rectangle(frame, (10, 10), (35, 30), (0, 0, 255), -1)
        writer.write(frame)
    writer.release()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="act_train_flow_") as tmp:
        os.environ["ACT_TRAIN_DATA_ROOT"] = str(Path(tmp) / "data")

        from web.app_factory import create_app

        client = TestClient(create_app())
        client.__enter__()
        try:
            label = client.post(
                "/api/labels",
                json={"code": "A1", "name": "测试动作", "description": "", "box_instruction": "", "enabled": True},
            )
            assert label.status_code == 200, label.text
            project = client.post(
                "/api/projects",
                json={
                    "name": "测试产品",
                    "product_name": "测试产品",
                    "sop_name": "测试SOP",
                    "station_name": "测试工位",
                    "label_codes": ["A1"],
                    "notes": "",
                },
            )
            assert project.status_code == 200, project.text
            project_id = project.json()["id"]

            video_path = Path(tmp) / "tiny.mp4"
            _write_tiny_video(video_path)
            with video_path.open("rb") as f:
                upload = client.post(
                    "/api/videos/upload",
                    data={"project_id": project_id},
                    files={"file": ("tiny.mp4", f, "video/mp4")},
                )
            assert upload.status_code == 200, upload.text
            video = upload.json()

            extract = client.post(
                "/api/frame-sets/extract",
                json={
                    "video_id": video["id"],
                    "sample_every_n_frames": 1,
                    "max_frames": 4,
                    "jpeg_quality": 90,
                    "name": "测试帧集",
                },
            )
            assert extract.status_code == 200, extract.text
            frame_set = extract.json()
            assert frame_set["frame_count"] == 4, frame_set

            frames = client.get(f"/api/frame-sets/{frame_set['id']}/frames")
            assert frames.status_code == 200, frames.text
            frame = frames.json()[0]
            anns = client.post(
                "/api/annotations/frame",
                json={
                    "project_id": project_id,
                    "frame_set_id": frame_set["id"],
                    "frame_id": frame["id"],
                    "annotations": [
                        {
                            "label_code": "A1",
                            "x": 0.2,
                            "y": 0.2,
                            "w": 0.3,
                            "h": 0.3,
                            "source": "manual",
                            "confirmed": True,
                        }
                    ],
                },
            )
            assert anns.status_code == 200, anns.text

            export = client.post(
                "/api/datasets/export",
                json={
                    "project_id": project_id,
                    "name": "测试数据集",
                    "frame_set_ids": [frame_set["id"]],
                    "history_dataset_ids": [],
                    "annotated_only": True,
                },
            )
            assert export.status_code == 200, export.text
            dataset = export.json()
            output_dir = Path(dataset["output_dir"])
            assert (output_dir / "dataset.generated.yaml").exists(), dataset
            assert any((output_dir / "labels" / split).glob("*.txt") for split in ["train", "val", "test"]), dataset
        finally:
            client.__exit__(None, None, None)
    print("train core flow smoke passed")


if __name__ == "__main__":
    main()
