from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import yaml

from . import store
from .paths import DATASETS_DIR
from .utils import clean_dir, new_id, split_by_ratio, unique_keep_order


SPLITS = ["train", "val", "test"]


def _yolo_line(class_id: int, ann: dict) -> str:
    x_center = float(ann["x"]) + float(ann["w"]) / 2
    y_center = float(ann["y"]) + float(ann["h"]) / 2
    return f"{class_id} {x_center:.6f} {y_center:.6f} {float(ann['w']):.6f} {float(ann['h']):.6f}"


def _require_history_structure(dataset: dict) -> Path:
    output_dir = Path(dataset["output_dir"])
    if not output_dir.exists():
        raise FileNotFoundError(f"历史训练数据集目录不存在: {output_dir}")
    for root_name in ["images", "labels"]:
        root = output_dir / root_name
        if not root.exists():
            raise FileNotFoundError(f"历史训练数据集缺少 {root_name} 目录: {output_dir}")
        for split in SPLITS:
            split_dir = root / split
            if not split_dir.exists():
                raise FileNotFoundError(f"历史训练数据集缺少 {root_name}/{split} 目录: {output_dir}")
    return output_dir


def _remap_label_file(src_label: Path, dst_label: Path, history_label_codes: list[str], current_class_map: dict[str, int]) -> int:
    lines: list[str] = []
    for raw in src_label.read_text(encoding="utf-8").splitlines():
        parts = raw.strip().split()
        if len(parts) < 5:
            continue
        old_class_id = int(float(parts[0]))
        if old_class_id >= len(history_label_codes):
            continue
        code = history_label_codes[old_class_id]
        if code not in current_class_map:
            continue
        parts[0] = str(current_class_map[code])
        lines.append(" ".join(parts[:5]))
    if not lines:
        return 0
    dst_label.parent.mkdir(parents=True, exist_ok=True)
    dst_label.write_text("\n".join(lines), encoding="utf-8")
    return len(lines)


def _copy_history_dataset(
    dataset: dict,
    images_by_split: dict[str, Path],
    labels_by_split: dict[str, Path],
    current_class_map: dict[str, int],
    counts: dict,
) -> None:
    output_dir = _require_history_structure(dataset)
    history_label_codes = dataset["label_codes"]
    missing_codes = [code for code in history_label_codes if code not in current_class_map]
    if missing_codes:
        raise ValueError(f"历史数据集包含当前产品未选择的标签: {', '.join(missing_codes)}")

    source_summary = {"id": dataset["id"], "name": dataset["name"], "images": 0, "boxes": 0}
    for split in SPLITS:
        image_dir = output_dir / "images" / split
        label_dir = output_dir / "labels" / split
        for src_img in sorted(path for path in image_dir.iterdir() if path.is_file()):
            src_label = label_dir / f"{src_img.stem}.txt"
            if not src_label.exists():
                counts["skipped_history_missing_label"] += 1
                continue
            stem = f"{dataset['id']}__{src_img.stem}"
            dst_label = labels_by_split[split] / f"{stem}.txt"
            box_count = _remap_label_file(src_label, dst_label, history_label_codes, current_class_map)
            if box_count <= 0:
                counts["skipped_history_empty_label"] += 1
                continue
            dst_img = images_by_split[split] / f"{stem}{src_img.suffix.lower()}"
            shutil.copy2(src_img, dst_img)
            counts[split] += 1
            counts["boxes"] += box_count
            counts["history_images"] += 1
            counts["history_boxes"] += box_count
            source_summary["images"] += 1
            source_summary["boxes"] += box_count
    counts["history_sources"].append(source_summary)


def export_dataset(
    project_id: str,
    name: str,
    frame_set_ids: list[str],
    history_dataset_ids: list[str] | None = None,
    annotated_only: bool = False,
) -> dict:
    frame_set_ids = frame_set_ids or []
    history_dataset_ids = history_dataset_ids or []
    if not frame_set_ids and not history_dataset_ids:
        raise ValueError("请至少选择一个帧集或一个历史训练数据集")

    project = store.get_project(project_id)
    label_codes = unique_keep_order(project["label_codes"])
    if not label_codes:
        raise ValueError("项目没有选择任何标签，无法导出数据集")
    class_map = {code: idx for idx, code in enumerate(label_codes)}
    dataset_id = new_id("dataset")
    output_dir = DATASETS_DIR / project_id / dataset_id
    clean_dir(output_dir)

    images_by_split = {split: output_dir / "images" / split for split in SPLITS}
    labels_by_split = {split: output_dir / "labels" / split for split in SPLITS}
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
        "current_frames": 0,
        "current_boxes": 0,
        "history_images": 0,
        "history_boxes": 0,
        "history_sources": [],
        "skipped_unconfirmed": 0,
        "confirmed_prelabel_boxes": 0,
        "skipped_unconfirmed_prelabel_boxes": 0,
        "skipped_unannotated": 0,
        "skipped_history_missing_label": 0,
        "skipped_history_empty_label": 0,
        "export_mode": "annotated_only" if annotated_only else "confirmed_annotations",
    }
    for frame_id, split in split_map.items():
        frame = frame_lookup[frame_id]
        raw_anns = [ann for ann in store.list_annotations(frame_set_by_frame[frame_id], frame_id) if ann["label_code"] in class_map]
        counts["skipped_unconfirmed_prelabel_boxes"] += sum(1 for ann in raw_anns if ann.get("source") == "prelabel" and not ann["confirmed"])
        anns = [ann for ann in raw_anns if ann["confirmed"]]
        counts["confirmed_prelabel_boxes"] += sum(1 for ann in anns if ann.get("source") == "prelabel")
        if not anns:
            counts["skipped_unannotated"] += 1
            continue
        src = Path(frame["path"])
        if not src.exists():
            counts["skipped_unannotated"] += 1
            continue
        stem = f"{frame_set_by_frame[frame_id]}__{src.stem}"
        dst_img = images_by_split[split] / f"{stem}{src.suffix.lower()}"
        dst_label = labels_by_split[split] / f"{stem}.txt"
        shutil.copy2(src, dst_img)
        dst_label.write_text("\n".join(_yolo_line(class_map[ann["label_code"]], ann) for ann in anns), encoding="utf-8")
        counts[split] += 1
        counts["boxes"] += len(anns)
        counts["current_frames"] += 1
        counts["current_boxes"] += len(anns)

    for history_dataset_id in history_dataset_ids:
        history_dataset = store.get_dataset_version(history_dataset_id)
        _copy_history_dataset(history_dataset, images_by_split, labels_by_split, class_map, counts)

    if counts["current_frames"] + counts["history_images"] <= 0:
        raise ValueError("没有可导出的已确认标注帧或历史数据集内容")

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
                "history_dataset_ids": history_dataset_ids,
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
            "history_dataset_ids": history_dataset_ids,
            "status": "ready",
            "summary": counts,
        }
    )
