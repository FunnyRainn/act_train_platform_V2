from __future__ import annotations

from pathlib import Path

from . import store
from .utils import new_id


def run_prelabel(frame_set_id: str, model_path: str, conf: float = 0.25) -> dict:
    """Run YOLO pre-labeling and store detections as unconfirmed annotations."""
    from ultralytics import YOLO

    conf = float(conf)
    if conf < 0.05 or conf > 0.95:
        raise ValueError("预标注置信度需要在 0.05 到 0.95 之间")

    frame_set = store.get_frame_set(frame_set_id)
    project = store.get_project(frame_set["project_id"])
    label_codes = project["label_codes"]
    if not label_codes:
        raise ValueError("项目没有选择标签，不能预标注")
    model = YOLO(model_path)
    frames = store.list_frames(frame_set_id)
    created = 0
    for frame in frames:
        result = model.predict(source=str(Path(frame["path"])), conf=conf, verbose=False)[0]
        annotations = []
        height = float(result.orig_shape[0])
        width = float(result.orig_shape[1])
        for box in result.boxes:
            class_id = int(box.cls[0])
            if class_id >= len(label_codes):
                continue
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            annotations.append(
                {
                    "id": new_id("ann"),
                    "label_code": label_codes[class_id],
                    "x": x1 / width,
                    "y": y1 / height,
                    "w": (x2 - x1) / width,
                    "h": (y2 - y1) / height,
                    "source": "prelabel",
                    "is_keyframe": False,
                    "confirmed": False,
                    "confidence": float(box.conf[0]),
                }
            )
        if annotations:
            store.delete_frame_prelabels(frame["id"])
            for annotation in annotations:
                store.add_annotation(project["id"], frame_set_id, frame["id"], annotation)
            created += len(annotations)
    counts = store.count_frame_set_prelabels(frame_set_id)
    return {"frame_set_id": frame_set_id, "created": created, **counts}


def clear_unconfirmed_prelabels(frame_set_id: str) -> dict:
    """Clear unconfirmed pre-label boxes in a frame set without touching manual annotations."""
    return store.delete_frame_set_prelabels(frame_set_id)


def confirm_all_prelabels(frame_set_id: str) -> dict:
    return store.confirm_frame_set_prelabels(frame_set_id)
