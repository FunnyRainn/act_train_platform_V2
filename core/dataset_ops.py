from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import yaml

from . import store
from .paths import DATASETS_DIR
from .utils import clean_dir, new_id, split_by_ratio, unique_keep_order


def _yolo_line(class_id: int, ann: dict) -> str:
    x_center = float(ann["x"]) + float(ann["w"]) / 2
    y_center = float(ann["y"]) + float(ann["h"]) / 2
    return f"{class_id} {x_center:.6f} {y_center:.6f} {float(ann['w']):.6f} {float(ann['h']):.6f}"


def export_dataset(
    project_id: str,
    name: str,
    frame_set_ids: list[str],
    history_dataset_ids: list[str] | None = None,
    annotated_only: bool = False,
) -> dict:
    project = store.get_project(project_id)
    label_codes = unique_keep_order(project["label_codes"])
    if not label_codes:
        raise ValueError("项目没有选择任何标签，无法导出数据集")
    class_map = {code: idx for idx, code in enumerate(label_codes)}
    dataset_id = new_id("dataset")
    output_dir = DATASETS_DIR / project_id / dataset_id
    clean_dir(output_dir)

    images_by_split = {split: output_dir / "images" / split for split in ["train", "val", "test"]}
    labels_by_split = {split: output_dir / "labels" / split for split in ["train", "val", "test"]}
    for path in [*images_by_split.values(), *labels_by_split.values()]:
        path.mkdir(parents=True, exist_ok=True)

    all_frame_ids: list[str] = []
    frame_lookup: dict[str, dict] = {}
    frame_set_by_frame: dict[str, str] = {}
    for frame_set_id in frame_set_ids:
        frames = store.list_frames(frame_set_id)
        for frame in frames:
            all_frame_ids.append(frame["id"])
            frame_lookup[frame["id"]] = frame
            frame_set_by_frame[frame["id"]] = frame_set_id

    random.Random(42).shuffle(all_frame_ids)
    train_ids, val_ids, test_ids = split_by_ratio(all_frame_ids, 0.7, 0.2)
    split_map = {frame_id: "train" for frame_id in train_ids}
    split_map.update({frame_id: "val" for frame_id in val_ids})
    split_map.update({frame_id: "test" for frame_id in test_ids})

    counts = {
        "train": 0,
        "val": 0,
        "test": 0,
        "boxes": 0,
        "skipped_unconfirmed": 0,
        "skipped_unannotated": 0,
        "export_mode": "annotated_only" if annotated_only else "confirmed_annotations",
    }
    for frame_id, split in split_map.items():
        frame = frame_lookup[frame_id]
        anns = [
            ann
            for ann in store.list_annotations(frame_set_by_frame[frame_id], frame_id)
            if ann["confirmed"] and ann["label_code"] in class_map
        ]
        if not anns:
            counts["skipped_unannotated"] += 1
            continue
        src = Path(frame["path"])
        stem = f"{frame_set_by_frame[frame_id]}__{src.stem}"
        dst_img = images_by_split[split] / f"{stem}{src.suffix.lower()}"
        dst_label = labels_by_split[split] / f"{stem}.txt"
        shutil.copy2(src, dst_img)
        dst_label.write_text("\n".join(_yolo_line(class_map[ann["label_code"]], ann) for ann in anns), encoding="utf-8")
        counts[split] += 1
        counts["boxes"] += len(anns)

    dataset_yaml = {
        "path": str(output_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {idx: code for code, idx in class_map.items()},
    }
    (output_dir / "dataset.generated.yaml").write_text(yaml.safe_dump(dataset_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (output_dir / "dataset_version.json").write_text(
        json.dumps(
            {
                "id": dataset_id,
                "project_id": project_id,
                "name": name,
                "label_codes": label_codes,
                "frame_set_ids": frame_set_ids,
                "history_dataset_ids": history_dataset_ids or [],
                "annotated_only": annotated_only,
                "summary": counts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return store.save_dataset_version(
        {
            "id": dataset_id,
            "project_id": project_id,
            "name": name,
            "output_dir": output_dir,
            "label_codes": label_codes,
            "frame_set_ids": frame_set_ids,
            "history_dataset_ids": history_dataset_ids or [],
            "status": "ready",
            "summary": counts,
        }
    )
