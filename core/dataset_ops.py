from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import cv2
import yaml

from . import store
from .paths import DATASETS_DIR
from .utils import clean_dir, new_id, split_by_ratio, unique_keep_order


SPLITS = ["train", "val", "test"]


def _yolo_line(class_id: int, ann: dict) -> str:
    x_center = float(ann["x"]) + float(ann["w"]) / 2
    y_center = float(ann["y"]) + float(ann["h"]) / 2
    return f"{class_id} {x_center:.6f} {y_center:.6f} {float(ann['w']):.6f} {float(ann['h']):.6f}"


def _ann_inside_region(ann: dict, region: dict) -> bool:
    ax1, ay1 = float(ann["x"]), float(ann["y"])
    ax2, ay2 = ax1 + float(ann["w"]), ay1 + float(ann["h"])
    rx1, ry1 = float(region["x"]), float(region["y"])
    rx2, ry2 = rx1 + float(region["w"]), ry1 + float(region["h"])
    eps = 1e-6
    return ax1 >= rx1 - eps and ay1 >= ry1 - eps and ax2 <= rx2 + eps and ay2 <= ry2 + eps


def _translate_ann_to_region(ann: dict, region: dict) -> dict:
    rx, ry = float(region["x"]), float(region["y"])
    rw, rh = float(region["w"]), float(region["h"])
    translated = dict(ann)
    translated["x"] = (float(ann["x"]) - rx) / rw
    translated["y"] = (float(ann["y"]) - ry) / rh
    translated["w"] = float(ann["w"]) / rw
    translated["h"] = float(ann["h"]) / rh
    return translated


def _crop_image_to_region(src: Path, dst: Path, region: dict) -> tuple[int, int]:
    image = cv2.imread(str(src))
    if image is None:
        raise FileNotFoundError(f"无法读取帧图片: {src}")
    height, width = image.shape[:2]
    x1 = max(0, min(width - 1, int(round(float(region["x"]) * width))))
    y1 = max(0, min(height - 1, int(round(float(region["y"]) * height))))
    x2 = max(x1 + 1, min(width, int(round((float(region["x"]) + float(region["w"])) * width))))
    y2 = max(y1 + 1, min(height, int(round((float(region["y"]) + float(region["h"])) * height))))
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), image[y1:y2, x1:x2])
    return width, height


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


def _dataset_scope(dataset: dict) -> tuple[str, str | None]:
    metadata = dataset.get("metadata") or {}
    return str(metadata.get("image_scope") or "full_image"), metadata.get("focus_region_id")


def _validate_history_scope(history_dataset: dict, image_scope: str, focus_region_id: str | None, force_mixed_scope: bool) -> list[str]:
    warnings: list[str] = []
    history_scope, history_region_id = _dataset_scope(history_dataset)
    if history_scope != image_scope or history_region_id != focus_region_id:
        message = f"历史数据集 {history_dataset['name']} 的视野({history_scope}/{history_region_id or '-'})与当前导出({image_scope}/{focus_region_id or '-'})不同"
        if not force_mixed_scope:
            raise ValueError(message + "，如确认要混入请勾选强制继续")
        warnings.append(message)
    return warnings


def export_dataset(
    project_id: str,
    name: str,
    frame_set_ids: list[str],
    history_dataset_ids: list[str] | None = None,
    annotated_only: bool = False,
    image_scope: str = "full_image",
    focus_region_ids: list[str] | None = None,
    history_by_focus_region: dict[str, list[str]] | None = None,
    force_mixed_scope: bool = False,
) -> dict:
    image_scope = image_scope if image_scope in {"full_image", "focus_region_crop"} else "full_image"
    focus_region_ids = focus_region_ids or []
    if image_scope == "focus_region_crop":
        if not focus_region_ids:
            raise ValueError("关注区域裁剪导出必须至少选择一个关注区域")
        results = []
        for region_id in focus_region_ids:
            region = store.get_focus_region(region_id)
            history_ids = (history_by_focus_region or {}).get(region_id, history_dataset_ids or [])
            region_name = region["name"]
            region_dataset_name = name if len(focus_region_ids) == 1 else f"{name}-{region_name}"
            results.append(
                _export_one_dataset(
                    project_id,
                    region_dataset_name,
                    frame_set_ids,
                    history_ids,
                    annotated_only,
                    image_scope,
                    region,
                    force_mixed_scope,
                )
            )
        return {"created": len(results), "datasets": results}
    return _export_one_dataset(project_id, name, frame_set_ids, history_dataset_ids or [], annotated_only, "full_image", None, force_mixed_scope)


def _export_one_dataset(
    project_id: str,
    name: str,
    frame_set_ids: list[str],
    history_dataset_ids: list[str],
    annotated_only: bool,
    image_scope: str,
    focus_region: dict | None,
    force_mixed_scope: bool,
) -> dict:
    frame_set_ids = frame_set_ids or []
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
        "scope_warnings": [],
        "skipped_unconfirmed": 0,
        "confirmed_prelabel_boxes": 0,
        "skipped_unconfirmed_prelabel_boxes": 0,
        "skipped_unannotated": 0,
        "skipped_outside_focus_region": 0,
        "skipped_history_missing_label": 0,
        "skipped_history_empty_label": 0,
        "export_mode": "annotated_only" if annotated_only else "confirmed_annotations",
    }
    for frame_id, split in split_map.items():
        frame = frame_lookup[frame_id]
        raw_anns = [ann for ann in store.list_annotations(frame_set_by_frame[frame_id], frame_id) if ann["label_code"] in class_map]
        counts["skipped_unconfirmed_prelabel_boxes"] += sum(1 for ann in raw_anns if ann.get("source") == "prelabel" and not ann["confirmed"])
        anns = [ann for ann in raw_anns if ann["confirmed"]]
        if focus_region is not None:
            before = len(anns)
            anns = [_translate_ann_to_region(ann, focus_region) for ann in anns if _ann_inside_region(ann, focus_region)]
            counts["skipped_outside_focus_region"] += before - len(anns)
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
        if focus_region is None:
            shutil.copy2(src, dst_img)
            source_frame_size = [int(frame.get("width") or 0), int(frame.get("height") or 0)]
        else:
            width, height = _crop_image_to_region(src, dst_img, focus_region)
            source_frame_size = [width, height]
        dst_label.write_text("\n".join(_yolo_line(class_map[ann["label_code"]], ann) for ann in anns), encoding="utf-8")
        counts[split] += 1
        counts["boxes"] += len(anns)
        counts["current_frames"] += 1
        counts["current_boxes"] += len(anns)

    for history_dataset_id in history_dataset_ids:
        history_dataset = store.get_dataset_version(history_dataset_id)
        counts["scope_warnings"].extend(_validate_history_scope(history_dataset, image_scope, focus_region["id"] if focus_region else None, force_mixed_scope))
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
    metadata = {
        "image_scope": image_scope,
        "focus_region_id": focus_region["id"] if focus_region else None,
        "focus_region_name": focus_region["name"] if focus_region else None,
        "focus_region_rect_norm": [focus_region["x"], focus_region["y"], focus_region["w"], focus_region["h"]] if focus_region else None,
        "source_frame_size": source_frame_size if "source_frame_size" in locals() else None,
        "crop_policy": "strict_inside_translate" if focus_region else "none",
        "history_dataset_ids": history_dataset_ids,
        "label_codes": label_codes,
        "force_mixed_scope": force_mixed_scope,
    }
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
                "metadata": metadata,
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
            "metadata": metadata,
        }
    )
