"""任务化原始标注：复用帧引用，保存精确类别PNG，乐观锁防止多页覆盖。"""

from __future__ import annotations

import json
import math
from typing import Any

import cv2
import numpy as np

from core import store
from core.db import get_conn
from core.task_contract import task_type
from core.utils import new_id

MAX_PIXELS = 32_000_000


def list_sets(project_id: str) -> list[dict]:
    """只返回当前项目的集合元数据，不复制图片或掺入其他任务。"""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM task_annotation_sets WHERE project_id=? ORDER BY created_at,id", (project_id,)).fetchall()
    return [_set_dict(row) for row in rows]


def _set_dict(row) -> dict:
    result = dict(row)
    result["label_codes"] = json.loads(result.pop("labels_json"))
    return result


def get_set(set_id: str) -> dict:
    """集合不存在明确报错，不能退回默认检测集合。"""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM task_annotation_sets WHERE id=?", (set_id,)).fetchone()
    if row is None:
        raise KeyError("标注集不存在")
    return _set_dict(row)


def create_set(project_id: str, name: str, task: str, labels: list[str] | None = None) -> dict:
    """标签在集合创建时固定；后续不同标签版本使用新集合，避免像素类别错位。"""
    project = store.get_project(project_id)
    task_type(task)
    codes = list(labels if labels is not None else project["label_codes"])
    if not codes or len(set(codes)) != len(codes) or any(code not in project["label_codes"] for code in codes):
        raise ValueError("请选择当前项目内不重复的有效标签")
    if task == "semantic_segment" and (len(codes) > 254 or "__background__" in codes):
        raise ValueError("当前YOLO PNG导出支持最多254个前景类，背景0、忽略255保留")
    if not name.strip():
        raise ValueError("标注集名称不能为空")
    set_id = new_id("annotation_set")
    with get_conn() as conn:
        conn.execute("INSERT INTO task_annotation_sets(id,project_id,name,task_type,labels_json) VALUES(?,?,?,?,?)", (set_id, project_id, name.strip(), task, json.dumps(codes, ensure_ascii=False)))
    return get_set(set_id)


def checked_frame(spec: dict, frame_id: str) -> dict:
    """通过帧集归属校验项目；尺寸来自服务端元数据，不信任请求中的尺寸。"""
    frame = store.get_frame(frame_id)
    frame_set = store.get_frame_set(frame["frame_set_id"])
    if frame_set["project_id"] != spec["project_id"]:
        raise ValueError("图片不属于标注集项目")
    if min(frame["width"], frame["height"]) <= 0 or frame["width"] * frame["height"] > MAX_PIXELS:
        raise ValueError("图片尺寸无效或超过标注像素上限")
    return frame


def decode_rle(runs: list, width: int, height: int, classes: int) -> np.ndarray:
    """先验证总像素和类别，再分配内存，避免请求利用游程扩展巨量数据。"""
    if not isinstance(runs, list) or len(runs) % 2 or len(runs) > width * height * 2:
        raise ValueError("类别图游程结构无效")
    total = 0
    for value, count in zip(runs[::2], runs[1::2]):
        if type(value) is not int or value not in range(classes + 1) and value != 255:
            raise ValueError("类别图含未定义类别")
        if type(count) is not int or count <= 0:
            raise ValueError("游程长度必须是正整数")
        total += count
    if total != width * height or total > MAX_PIXELS:
        raise ValueError("类别图像素数与原图不一致")
    return np.repeat(np.asarray(runs[::2], dtype=np.uint8), runs[1::2]).reshape(height, width)


def encode_rle(mask: np.ndarray) -> list[int]:
    """按行保存类别ID，PNG是持久化事实，游程只是编辑接口传输形式。"""
    flat = mask.reshape(-1)
    starts = np.r_[0, np.flatnonzero(flat[1:] != flat[:-1]) + 1]
    counts = np.diff(np.r_[starts, len(flat)])
    return np.column_stack((flat[starts], counts)).reshape(-1).tolist()


def _point(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("顶点必须是二维坐标")
    point = [float(v) for v in value]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in point):
        raise ValueError("顶点必须是原图归一化有限坐标")
    return point


def normalize_objects(spec: dict, objects: list) -> list[dict]:
    """原始实例保留多片段；YOLO表达限制留到导出检查，不破坏原标注。"""
    if not isinstance(objects, list) or len(objects) > 1000:
        raise ValueError("每帧最多1000个对象")
    result, identities = [], set()
    for item in objects:
        if set(item) - {"instance_id", "label_code", "bbox", "polygons"}:
            raise ValueError("标注包含未知字段")
        code = item.get("label_code")
        identity = str(item.get("instance_id") or "")
        if code not in spec["label_codes"] or not identity or len(identity) > 128 or identity in identities:
            raise ValueError("对象标签或实例ID无效/重复")
        identities.add(identity)
        if spec["task_type"] == "detect":
            box = item.get("bbox", [])
            if len(box) != 4 or item.get("polygons"):
                raise ValueError("检测标注必须是矩形，不能混入多边形")
            box = _point(box[:2]) + _point(box[2:])
            if box[0] >= box[2] or box[1] >= box[3]:
                raise ValueError("矩形必须具有正面积")
            result.append({"instance_id": identity, "label_code": code, "bbox": box})
        else:
            fragments = item.get("polygons", [])
            if not fragments or len(fragments) > 64 or item.get("bbox"):
                raise ValueError("实例分割必须有多边形片段，不能用框代替")
            polygons = []
            for polygon in fragments:
                if not 3 <= len(polygon) <= 2048:
                    raise ValueError("每片段需要3至2048个顶点")
                points = [_point(p) for p in polygon]
                if abs(cv2.contourArea(np.asarray(points, np.float32))) < 1e-10:
                    raise ValueError("多边形面积为零")
                polygons.append(points)
            result.append({"instance_id": identity, "label_code": code, "polygons": polygons})
    return result


def read_annotation(set_id: str, frame_id: str) -> dict:
    """未标注语义帧默认全忽略而非全背景；显式空对象帧仍可保存为有效标注。"""
    spec = get_set(set_id)
    frame = checked_frame(spec, frame_id)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM task_frame_annotations WHERE set_id=? AND frame_id=?", (set_id, frame_id)).fetchone()
    result = {"set_id": set_id, "frame_id": frame_id, "task_type": spec["task_type"], "width": frame["width"], "height": frame["height"], "revision": row["revision"] if row else 0, "objects": []}
    if spec["task_type"] == "semantic_segment":
        result["mask_rle"] = encode_rle(cv2.imdecode(np.frombuffer(row["mask_png"], np.uint8), cv2.IMREAD_UNCHANGED)) if row else [255, frame["width"] * frame["height"]]
    elif row:
        result.update(json.loads(row["payload_json"]))
    return result


def save_annotation(set_id: str, frame_id: str, payload: dict) -> dict:
    """单事务原子写入精确标注，并检查版本，冲突时保留已保存内容。"""
    spec = get_set(set_id)
    frame = checked_frame(spec, frame_id)
    if set(payload) - {"revision", "objects", "mask_rle"}:
        raise ValueError("标注请求包含未知字段")
    png, objects = None, []
    if spec["task_type"] == "semantic_segment":
        if payload.get("objects"):
            raise ValueError("语义类别图不能保存对象列表")
        mask = decode_rle(payload.get("mask_rle", []), frame["width"], frame["height"], len(spec["label_codes"]))
        ok, encoded = cv2.imencode(".png", mask)
        if not ok:
            raise ValueError("类别PNG编码失败")
        png = encoded.tobytes()
    else:
        if "mask_rle" in payload:
            raise ValueError("对象任务不能保存语义类别图")
        objects = normalize_objects(spec, payload.get("objects", []))
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT revision FROM task_frame_annotations WHERE set_id=? AND frame_id=?", (set_id, frame_id)).fetchone()
        revision = row["revision"] if row else 0
        if payload.get("revision") != revision:
            raise ValueError("标注已被其他页面修改，请重新载入后再保存")
        conn.execute("INSERT INTO task_frame_annotations(set_id,frame_id,payload_json,mask_png,revision) VALUES(?,?,?,?,?) ON CONFLICT(set_id,frame_id) DO UPDATE SET payload_json=excluded.payload_json,mask_png=excluded.mask_png,revision=excluded.revision,updated_at=CURRENT_TIMESTAMP", (set_id, frame_id, json.dumps({"objects": objects}, ensure_ascii=False), png, revision + 1))
        conn.execute("UPDATE task_annotation_sets SET revision=revision+1 WHERE id=?", (set_id,))
    return read_annotation(set_id, frame_id)
