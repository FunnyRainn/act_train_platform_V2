"""三任务数据集导出：读取一致快照，原标注不变，YOLO产物有独立版本。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import yaml

from core import store
from core.db import get_conn
from core.paths import DATASETS_DIR
from core.runtime_paths import resolve_runtime_path
from core.task_annotations import get_set, checked_frame
from core.utils import new_id


def crop_bounds(width: int, height: int, rect: list[float] | None) -> tuple[int, int, int, int]:
    """归一化xywh转换为有界像素矩形，拒绝零面积和越界裁剪。"""
    if rect is None:
        return 0, 0, width, height
    if len(rect) != 4 or not all(np.isfinite(v) for v in rect):
        raise ValueError("裁剪区域必须为有限xywh")
    x, y, w, h = rect
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1 or y + h > 1:
        raise ValueError("裁剪区域越界或面积为零")
    bounds = (round(x * width), round(y * height), round((x + w) * width), round((y + h) * height))
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise ValueError("裁剪区域小于一个像素")
    return bounds


def object_labels(spec: dict, objects: list[dict], width: int, height: int, bounds: tuple) -> list[str]:
    """不支持的实例片段明确失败；裁剪实例按像素轮廓导出并记录转换精度。"""
    x0, y0, x1, y1 = bounds
    cw, ch = x1 - x0, y1 - y0
    lines = []
    for item in objects:
        cls = spec["label_codes"].index(item["label_code"])
        if spec["task_type"] == "detect":
            bx0, by0, bx1, by1 = np.asarray(item["bbox"]) * [width, height, width, height]
            bx0, by0, bx1, by1 = max(bx0, x0), max(by0, y0), min(bx1, x1), min(by1, y1)
            if bx0 >= bx1 or by0 >= by1:
                continue
            coords = [(bx0 + bx1 - 2 * x0) / (2 * cw), (by0 + by1 - 2 * y0) / (2 * ch), (bx1 - bx0) / cw, (by1 - by0) / ch]
        else:
            if len(item["polygons"]) != 1:
                raise ValueError(f"实例{item['instance_id']}有多个可见片段，当前单多边形导出格式不能无损表达；请调整导出选择，不会自动合并")
            points = np.asarray(item["polygons"][0], np.float32)
            if bounds != (0, 0, width, height):
                mask = np.zeros((height, width), np.uint8)
                pixel_points = np.rint(points * [width, height]).astype(np.int32)
                cv2.fillPoly(mask, [pixel_points], 1)
                contours, hierarchy = cv2.findContours(mask[y0:y1, x0:x1].copy(), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
                if not contours:
                    continue
                if len(contours) != 1:
                    raise ValueError(f"实例{item['instance_id']}裁剪后产生多片段/孔洞，当前导出格式不支持")
                if len(contours[0]) < 3 or cv2.contourArea(contours[0]) <= 0:
                    raise ValueError("裁剪后的实例不足以形成有效多边形")
                points = contours[0].reshape(-1, 2) / [cw, ch]
            coords = points.reshape(-1).tolist()
        lines.append(str(cls) + " " + " ".join(f"{float(v):.8f}" for v in coords))
    return lines


def export_set(set_id: str, name: str, focus_region_id: str | None = None, split_by_video: dict | None = None) -> dict:
    """先验证所有标注，再生成单一不可变导出版本；至少两帧避免训练验证同图。"""
    spec = get_set(set_id)
    focus = None
    if focus_region_id:
        focus = next((row for row in store.list_focus_regions(spec["project_id"]) if row["id"] == focus_region_id), None)
        if focus is None:
            raise ValueError("关注区域不属于当前项目")
    rect = [focus[key] for key in ("x", "y", "w", "h")] if focus else None
    # 在同一读取事务内取得集合修订与所有标注，导出过程中编辑不会污染本版本。
    with get_conn() as conn:
        conn.execute("BEGIN")
        revision = conn.execute("SELECT revision FROM task_annotation_sets WHERE id=?", (set_id,)).fetchone()[0]
        rows = conn.execute("SELECT * FROM task_frame_annotations WHERE set_id=? ORDER BY frame_id", (set_id,)).fetchall()
    if len(rows) < 2:
        raise ValueError("至少保存两张标注图片，分别用于训练和验证")
    prepared = []
    for row in rows:
        frame = checked_frame(spec, row["frame_id"])
        image_path = resolve_runtime_path(frame["path"], "标注原图", require_exists=True)
        image = cv2.imread(str(image_path))
        if image is None or image.shape[:2] != (frame["height"], frame["width"]):
            raise ValueError(f"原图无法读取或尺寸改变: {frame['id']}")
        bounds = crop_bounds(frame["width"], frame["height"], rect)
        x0, y0, x1, y1 = bounds
        mask, lines = None, None
        if spec["task_type"] == "semantic_segment":
            mask = cv2.imdecode(np.frombuffer(row["mask_png"], np.uint8), cv2.IMREAD_UNCHANGED)[y0:y1, x0:x1]
            if not np.any(mask != 255):
                raise ValueError(f"图片{frame['id']}裁剪区域全部未标注/忽略")
        else:
            lines = object_labels(spec, json.loads(row["payload_json"])["objects"], frame["width"], frame["height"], bounds)
        # 预检查后只保留压缩PNG，不把整个数据集的解码mask常驻内存。
        prepared.append((frame, image_path, bounds, row["mask_png"], lines, row["revision"]))
    dataset_id = new_id("dataset")
    output = DATASETS_DIR / spec["project_id"] / dataset_id
    labels = (["__background__"] if spec["task_type"] == "semantic_segment" else []) + spec["label_codes"]
    ordered = sorted(prepared, key=lambda row: hashlib.sha256(row[0]["id"].encode()).hexdigest())
    val_count = max(1, round(len(ordered) * .2))
    source_splits = {}
    for frame_set_id in {row[0]["frame_set_id"] for row in prepared}:
        frame_set = store.get_frame_set(frame_set_id)
        source_splits.update(frame_set.get("config", {}).get("source_splits", {}))
    # 只要导入集声明拆分，就必须完整保留；混合未声明帧时拒绝隐式重新分配。
    if source_splits and any(row[0]["id"] not in source_splits for row in prepared):
        raise ValueError("当前集合混合了有来源拆分和无拆分的帧，请分开导出")
    if source_splits and not {"train", "val"} <= {source_splits[row[0]["id"]] for row in prepared}:
        raise ValueError("保留来源拆分的导出必须同时包含train和val，不能自动移动样本")
    video_groups = {}
    for frame, *_ in prepared:
        video_groups.setdefault(frame["video_id"], []).append(frame["id"])
    group_splits = {}
    if split_by_video is not None:
        if (not isinstance(split_by_video, dict) or set(split_by_video) != set(video_groups)
                or not set(split_by_video.values()) <= {"train", "val", "test"}
                or not {"train", "val"} <= set(split_by_video.values())):
            raise ValueError("视频分组划分必须完整覆盖当前视频，且至少包含训练和验证组")
        group_splits = split_by_video
    elif not source_splits and len(video_groups) >= 2:
        # 视频分组优先，样本量最大的来源作为训练；其余来源独立留出，不拆相邻帧。
        groups = sorted(video_groups, key=lambda key: (-len(video_groups[key]), key))
        group_splits = {key: "train" for key in groups}
        group_splits[groups[-1]] = "val"
        if len(groups) >= 3:
            group_splits[groups[-2]] = "test"
    if group_splits:
        source_identities = {}
        for video_id, split in group_splits.items():
            video = store.get_video(video_id)
            identity = str(video.get("asset_id") or Path(video["path"]).resolve())
            if identity in source_identities and source_identities[identity] != split:
                raise ValueError("同一来源视频不能跨训练、验证、测试组")
            source_identities[identity] = split
        for frame, *_ in prepared:
            desired = group_splits[frame["video_id"]]
            if frame["id"] in source_splits and source_splits[frame["id"]] != desired:
                raise ValueError("视频分组与已导入来源划分冲突，不自动移动样本")
            source_splits[frame["id"]] = desired
    index = []
    for number, (frame, source, bounds, mask_png, lines, frame_revision) in enumerate(ordered):
        split = source_splits[frame["id"]] if source_splits else ("val" if number < val_count else "train")
        image_dir = output / "images" / split
        label_dir = output / ("masks" if mask_png is not None else "labels") / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        x0, y0, x1, y1 = bounds
        image = cv2.imread(str(source))[y0:y1, x0:x1]
        if not cv2.imwrite(str(image_dir / f"{frame['id']}.png"), image):
            raise OSError("数据集图片写入失败")
        if mask_png is not None:
            mask = cv2.imdecode(np.frombuffer(mask_png, np.uint8), cv2.IMREAD_UNCHANGED)[y0:y1, x0:x1]
            if not cv2.imwrite(str(label_dir / f"{frame['id']}.png"), mask):
                raise OSError("类别mask写入失败")
        else:
            (label_dir / f"{frame['id']}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        index.append({"frame_id": frame["id"], "video_id": frame["video_id"], "annotation_revision": frame_revision, "split": split, "original_hw": [frame["height"], frame["width"]], "crop_xyxy": list(bounds)})
    config = {"path": str(output), "train": "images/train", "val": "images/val", "names": dict(enumerate(labels)), "task_type": spec["task_type"]}
    if any(row["split"] == "test" for row in index):
        config["test"] = "images/test"
    if spec["task_type"] == "semantic_segment":
        config["masks_dir"] = "masks"
    (output / "dataset.generated.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    (output / "annotation_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {"task_type": spec["task_type"], "annotation_set_id": set_id, "annotation_revision": revision, "background_id": 0 if spec["task_type"] == "semantic_segment" else None, "ignore_id": 255 if spec["task_type"] == "semantic_segment" else None, "image_scope": "focus_region_crop" if focus else "full_image", "recommended_imgsz": 640, "crop_polygon_precision": "one_pixel" if focus and spec["task_type"] == "instance_segment" else "original", "split_policy": "deterministic_frame_hash_not_accuracy_benchmark"}
    if focus:
        metadata.update(focus_region_id=focus["id"], focus_region_name=focus["name"], focus_region_rect_norm=rect)
    if source_splits:
        metadata["split_policy"] = "preserved_import_source"
    if group_splits:
        metadata.update(split_policy="video_source_groups", split_by_video=group_splits)
    counts = {f"{split}_count": sum(row["split"] == split for row in index) for split in ("train", "val", "test")}
    return store.save_dataset_version({"id": dataset_id, "project_id": spec["project_id"], "name": name or spec["name"], "output_dir": output, "label_codes": labels, "frame_set_ids": sorted({row[0]["frame_set_id"] for row in prepared}), "summary": {"frame_count": len(rows), **counts, "task_type": spec["task_type"]}, "metadata": metadata, "status": "ready"})
