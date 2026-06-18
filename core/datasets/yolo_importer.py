from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import cv2
import yaml

from core import store
from core.datasets.exporter import _add_size, _finish_size_stats, _new_size_stats
from core.paths import DATASETS_DIR
from core.utils import IMAGE_SUFFIXES, clean_dir, new_id, safe_name, unique_keep_order

SPLITS = ["train", "val", "test"]


def _dataset_root(dataset_dir: str | Path) -> Path:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_dataset_root` 的职责和调用边界。
    入参：dataset_dir，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    root = Path(dataset_dir).expanduser()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"数据集目录不存在: {root}")
    return root.resolve()


def _find_yaml(root: Path) -> Path:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_find_yaml` 的职责和调用边界。
    入参：root，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    for name in ("data.yaml", "dataset.yaml"):
        path = root / name
        if path.exists():
            return path
    candidates = sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError("未找到 data.yaml 或 dataset.yaml")


def _read_yaml(path: Path) -> dict[str, Any]:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_read_yaml` 的职责和调用边界。
    入参：path，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML 内容必须是对象: {path}")
    return data


def _parse_names(raw: Any) -> list[str]:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_parse_names` 的职责和调用边界。
    入参：raw，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    if isinstance(raw, list):
        return [str(item).strip() for item in raw]
    if isinstance(raw, dict):
        items = sorted(raw.items(), key=lambda item: int(item[0]))
        return [str(value).strip() for _, value in items]
    raise ValueError("YAML 缺少 names，或 names 格式不是列表/字典")


def _path_from_yaml(root: Path, raw: Any) -> Path | None:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_path_from_yaml` 的职责和调用边界。
    入参：root、raw，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    if not raw:
        return None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not raw:
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _yaml_base_root(root: Path, yaml_data: dict[str, Any]) -> Path:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_yaml_base_root` 的职责和调用边界。
    入参：root、yaml_data，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    raw = yaml_data.get("path")
    if not raw:
        return root
    path = Path(str(raw))
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _labels_for_images_dir(images_dir: Path) -> Path:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_labels_for_images_dir` 的职责和调用边界。
    入参：images_dir，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    parts = list(images_dir.parts)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index].lower() == "images":
            parts[index] = "labels"
            return Path(*parts)
    if images_dir.name.lower() == "images":
        return images_dir.parent / "labels"
    return images_dir.parent / "labels" / images_dir.name


def _split_dirs(root: Path, yaml_data: dict[str, Any]) -> dict[str, tuple[Path, Path]]:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_split_dirs` 的职责和调用边界。
    入参：root、yaml_data，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    result: dict[str, tuple[Path, Path]] = {}
    for split in SPLITS:
        images_dir = _path_from_yaml(root, yaml_data.get(split))
        if images_dir is None:
            candidates = [root / "images" / split, root / split / "images"]
            images_dir = next((item for item in candidates if item.exists()), candidates[0])
        labels_dir = _labels_for_images_dir(images_dir)
        result[split] = (images_dir, labels_dir)
    return result


def _iter_images(path: Path) -> list[Path]:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_iter_images` 的职责和调用边界。
    入参：path，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    if not path.exists():
        return []
    return sorted(item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES)


def _read_image_size(path: Path) -> tuple[int, int] | None:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_read_image_size` 的职责和调用边界。
    入参：path，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    image = cv2.imread(str(path))
    if image is None:
        return None
    height, width = image.shape[:2]
    return int(width), int(height)


def _label_path_for_image(image: Path, images_dir: Path, labels_dir: Path) -> Path:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_label_path_for_image` 的职责和调用边界。
    入参：image、images_dir、labels_dir，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    relative = image.relative_to(images_dir)
    return (labels_dir / relative).with_suffix(".txt")


def _validate_label_line(line: str, names: list[str], line_context: str) -> tuple[int, list[str]]:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_validate_label_line` 的职责和调用边界。
    入参：line、names、line_context，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    parts = line.strip().split()
    if not parts:
        raise ValueError("empty")
    if len(parts) != 5:
        raise ValueError(f"{line_context}: YOLO 检测标签必须是 5 列")
    try:
        class_id = int(float(parts[0]))
        coords = [float(value) for value in parts[1:5]]
    except ValueError as exc:
        raise ValueError(f"{line_context}: 标签行包含非数字") from exc
    if class_id < 0 or class_id >= len(names):
        raise ValueError(f"{line_context}: class id {class_id} 不在 names 范围内")
    if any(value < 0 or value > 1 for value in coords):
        raise ValueError(f"{line_context}: bbox 坐标必须在 0~1 范围内")
    if coords[2] <= 0 or coords[3] <= 0:
        raise ValueError(f"{line_context}: bbox 宽高必须大于 0")
    return class_id, parts


def _suggest_mapping(names: list[str], project: dict[str, Any]) -> dict[str, str]:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_suggest_mapping` 的职责和调用边界。
    入参：names、project，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    labels = {label["code"]: label for label in store.list_labels()}
    selected_codes = set(project.get("label_codes") or [])
    by_name = {str(label.get("name") or "").strip(): code for code, label in labels.items() if code in selected_codes}
    suggestions: dict[str, str] = {}
    for idx, name in enumerate(names):
        text = str(name).strip()
        if text in selected_codes:
            suggestions[str(idx)] = text
        elif text in by_name:
            suggestions[str(idx)] = by_name[text]
        else:
            suggestions[str(idx)] = ""
    return suggestions


def inspect_yolo_dataset(project_id: str, dataset_dir: str) -> dict[str, Any]:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `inspect_yolo_dataset` 的职责和调用边界。
    入参：project_id、dataset_dir，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    project = store.get_project(project_id)
    root = _dataset_root(dataset_dir)
    # 先按 YOLO 原始结构读取 yaml 和 split 目录，只做检查，不复制任何数据。
    yaml_path = _find_yaml(root)
    yaml_data = _read_yaml(yaml_path)
    base_root = _yaml_base_root(root, yaml_data)
    names = _parse_names(yaml_data.get("names"))
    split_dirs = _split_dirs(base_root, yaml_data)
    errors: list[str] = []
    warnings: list[str] = []
    splits: dict[str, dict[str, Any]] = {}
    total_images = 0
    total_boxes = 0
    empty_label_images = 0
    missing_label_images = 0

    for split, (images_dir, labels_dir) in split_dirs.items():
        images = _iter_images(images_dir)
        split_boxes = 0
        split_empty = 0
        split_missing = 0
        if images and not labels_dir.exists():
            warnings.append(f"{split}: labels 目录不存在，图片将作为空标签负样本处理: {labels_dir}")
        for image in images:
            label_path = _label_path_for_image(image, images_dir, labels_dir)
            if not label_path.exists():
                split_missing += 1
                continue
            lines = [line for line in label_path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
            if not lines:
                split_empty += 1
                continue
            for line_no, line in enumerate(lines, 1):
                try:
                    _validate_label_line(line, names, f"{label_path}:{line_no}")
                    split_boxes += 1
                except ValueError as exc:
                    errors.append(str(exc))
        total_images += len(images)
        total_boxes += split_boxes
        empty_label_images += split_empty
        missing_label_images += split_missing
        splits[split] = {
            "images_dir": str(images_dir),
            "labels_dir": str(labels_dir),
            "images": len(images),
            "boxes": split_boxes,
            "empty_label_images": split_empty,
            "missing_label_images": split_missing,
        }

    if total_images <= 0:
        errors.append("未找到任何图片")

    return {
        "dataset_dir": str(root),
        "yaml_path": str(yaml_path),
        "classes": [{"class_id": idx, "name": name} for idx, name in enumerate(names)],
        "suggested_mapping": _suggest_mapping(names, project),
        "splits": splits,
        "summary": {
            "images": total_images,
            "boxes": total_boxes,
            "empty_label_images": empty_label_images,
            "missing_label_images": missing_label_images,
        },
        "errors": errors,
        "warnings": warnings,
    }


def _normalized_mapping(label_mapping: dict[str, Any], names: list[str]) -> dict[int, str]:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_normalized_mapping` 的职责和调用边界。
    入参：label_mapping、names，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    output: dict[int, str] = {}
    for raw_key, raw_value in (label_mapping or {}).items():
        if raw_value is None or raw_value == "":
            continue
        # 外部类别编号必须映射到当前产品已启用的本地标签，导入时再重写 class id。
        idx = int(raw_key)
        if idx < 0 or idx >= len(names):
            raise ValueError(f"标签映射包含不存在的外部类别: {idx}")
        output[idx] = str(raw_value).strip()
    if not output:
        raise ValueError("请至少映射一个外部类别")
    return output


def _remove_output_dir(output_dir: Path) -> None:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `_remove_output_dir` 的职责和调用边界。
    入参：output_dir，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    if output_dir.exists():
        shutil.rmtree(output_dir)


def import_yolo_dataset(
    project_id: str,
    name: str,
    dataset_dir: str,
    label_mapping: dict[str, Any],
    image_scope: str = "full_image",
    focus_region_id: str | None = None,
) -> dict[str, Any]:
    """用途：说明 YOLO 数据集导入、导出和版本管理 中 `import_yolo_dataset` 的职责和调用边界。
    入参：project_id、name、dataset_dir、label_mapping、image_scope、focus_region_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取视频帧、复制数据文件、写入数据集目录和元数据文件。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    project = store.get_project(project_id)
    root = _dataset_root(dataset_dir)
    # 导入阶段重新读取并校验源数据，避免用户在 inspect 和 confirm 之间改动目录。
    yaml_path = _find_yaml(root)
    yaml_data = _read_yaml(yaml_path)
    base_root = _yaml_base_root(root, yaml_data)
    names = _parse_names(yaml_data.get("names"))
    split_dirs = _split_dirs(base_root, yaml_data)
    image_scope = image_scope if image_scope in {"full_image", "focus_region_crop"} else "full_image"
    focus_region = store.get_focus_region(focus_region_id) if image_scope == "focus_region_crop" and focus_region_id else None
    if image_scope == "focus_region_crop" and not focus_region:
        raise ValueError("关注区域裁剪数据集必须选择关注区域")
    if focus_region and focus_region["project_id"] != project_id:
        raise ValueError("关注区域不属于当前产品")

    project_label_codes = unique_keep_order(project.get("label_codes") or [])
    if not project_label_codes:
        raise ValueError("当前产品没有选择任何标签，无法导入数据集")
    mapped_codes = _normalized_mapping(label_mapping, names)
    missing_codes = [code for code in unique_keep_order(mapped_codes.values()) if code not in project_label_codes]
    if missing_codes:
        raise ValueError(f"映射标签未加入当前产品: {', '.join(missing_codes)}")
    class_map = {code: idx for idx, code in enumerate(project_label_codes)}

    dataset_id = new_id("dataset")
    output_dir = DATASETS_DIR / project_id / dataset_id
    clean_dir(output_dir)
    images_by_split = {split: output_dir / "images" / split for split in SPLITS}
    labels_by_split = {split: output_dir / "labels" / split for split in SPLITS}
    for path in [*images_by_split.values(), *labels_by_split.values()]:
        path.mkdir(parents=True, exist_ok=True)

    counts = {
        "train": 0,
        "val": 0,
        "test": 0,
        "boxes": 0,
        "source_images": 0,
        "source_boxes": 0,
        "empty_label_images": 0,
        "missing_label_images": 0,
        "skipped_unmapped_boxes": 0,
        "export_mode": "external_yolo_import",
    }
    size_stats = _new_size_stats()

    try:
        for split, (images_dir, labels_dir) in split_dirs.items():
            for image in _iter_images(images_dir):
                relative = image.relative_to(images_dir)
                stem = safe_name(str(relative.with_suffix("")), "image")
                dst_img = images_by_split[split] / f"{stem}{image.suffix.lower()}"
                dst_label = labels_by_split[split] / f"{stem}.txt"
                # 图片复制进平台数据目录后再生成标签，外部目录后续移动不会影响平台数据集版本。
                shutil.copy2(image, dst_img)
                size = _read_image_size(dst_img)
                if size:
                    _add_size(size_stats, size[0], size[1])

                out_lines: list[str] = []
                label_path = _label_path_for_image(image, images_dir, labels_dir)
                if label_path.exists():
                    raw_lines = [line for line in label_path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
                    if not raw_lines:
                        counts["empty_label_images"] += 1
                    for line_no, line in enumerate(raw_lines, 1):
                        old_class_id, parts = _validate_label_line(line, names, f"{label_path}:{line_no}")
                        code = mapped_codes.get(old_class_id)
                        if not code:
                            counts["skipped_unmapped_boxes"] += 1
                            continue
                        parts[0] = str(class_map[code])
                        out_lines.append(" ".join(parts[:5]))
                else:
                    counts["missing_label_images"] += 1
                dst_label.write_text("\n".join(out_lines), encoding="utf-8")
                counts[split] += 1
                counts["source_images"] += 1
                counts["boxes"] += len(out_lines)
                counts["source_boxes"] += len(out_lines)

        if counts["source_images"] <= 0:
            raise ValueError("未找到可导入图片")

        image_size_stats = _finish_size_stats(size_stats)
        counts["image_size_stats"] = image_size_stats
        counts["recommended_imgsz"] = image_size_stats.get("recommended_imgsz")
        metadata = {
            "source": "external_yolo",
            "external_dataset_dir": str(root),
            "external_yaml_path": str(yaml_path),
            "external_names": names,
            "label_mapping": {str(key): value for key, value in mapped_codes.items()},
            "image_scope": image_scope,
            "focus_region_id": focus_region["id"] if focus_region else None,
            "focus_region_name": focus_region["name"] if focus_region else None,
            "focus_region_rect_norm": [focus_region["x"], focus_region["y"], focus_region["w"], focus_region["h"]] if focus_region else None,
            "image_size_stats": image_size_stats,
            "recommended_imgsz": image_size_stats.get("recommended_imgsz"),
            "crop_policy": "external_already_cropped" if focus_region else "none",
            "label_codes": project_label_codes,
        }
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
                    "label_codes": project_label_codes,
                    "frame_set_ids": [],
                    "history_dataset_ids": [],
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
                "name": name or f"外部YOLO数据集-{dataset_id[-4:]}",
                "output_dir": output_dir,
                "label_codes": project_label_codes,
                "frame_set_ids": [],
                "history_dataset_ids": [],
                "status": "ready",
                "summary": counts,
                "metadata": metadata,
            }
        )
    except Exception:
        _remove_output_dir(output_dir)
        raise
