from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from core.db import get_conn, json_dumps, json_loads, row_to_dict, rows_to_dicts
from core.paths import FRAMES_DIR
from core.utils import new_id, now_text, safe_name


def _path_exists(value: str | Path | None) -> bool:
    return bool(value) and Path(value).exists()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def list_labels(enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM labels"
    params: list[Any] = []
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY group_code, code"
    with get_conn() as conn:
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def upsert_label(payload: dict[str, Any]) -> dict[str, Any]:
    code = str(payload["code"]).strip().upper()
    group_code = code[:1]
    if group_code not in {"A", "B", "C"}:
        raise ValueError("标签编码必须以 A、B 或 C 开头")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO labels(code, group_code, name, description, box_instruction, enabled, updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                box_instruction=excluded.box_instruction,
                enabled=excluded.enabled,
                updated_at=excluded.updated_at
            """,
            (
                code,
                group_code,
                str(payload.get("name") or code).strip(),
                str(payload.get("description") or "").strip(),
                str(payload.get("box_instruction") or "").strip(),
                1 if payload.get("enabled", True) else 0,
                now_text(),
            ),
        )
        row = conn.execute("SELECT * FROM labels WHERE code=?", (code,)).fetchone()
        return row_to_dict(row) or {}


def list_projects() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall())
    for row in rows:
        row["label_codes"] = json_loads(row.pop("label_codes_json"), [])
    return rows


def get_project(project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())
    if not row:
        raise KeyError(f"项目不存在: {project_id}")
    row["label_codes"] = json_loads(row.pop("label_codes_json"), [])
    return row


def save_project(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = payload.get("id") or new_id("project")
    label_codes = payload.get("label_codes") or []
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projects(id, name, product_name, sop_name, station_name, label_codes_json, notes, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                product_name=excluded.product_name,
                sop_name=excluded.sop_name,
                station_name=excluded.station_name,
                label_codes_json=excluded.label_codes_json,
                notes=excluded.notes,
                updated_at=excluded.updated_at
            """,
            (
                project_id,
                str(payload.get("name") or "未命名训练项目").strip(),
                str(payload.get("product_name") or "").strip(),
                str(payload.get("sop_name") or "").strip(),
                str(payload.get("station_name") or "").strip(),
                json_dumps(label_codes),
                str(payload.get("notes") or "").strip(),
                now_text(),
            ),
        )
    return get_project(project_id)


def list_videos(project_id: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM videos"
    params: list[Any] = []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(project_id)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute(sql, params).fetchall())
    return [row for row in rows if _path_exists(row.get("path"))]


def list_video_assets() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM video_assets ORDER BY created_at DESC").fetchall())
    return [row for row in rows if _path_exists(row.get("stored_path"))]


def get_video_asset(asset_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM video_assets WHERE id=?", (asset_id,)).fetchone())
    if not row:
        raise KeyError(f"素材不存在: {asset_id}")
    return row


def create_video_asset(payload: dict[str, Any]) -> dict[str, Any]:
    asset_id = payload.get("id") or new_id("asset")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO video_assets(id, name, source_type, original_path, stored_path, fps, frame_count, duration_sec, width, height)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                asset_id,
                payload["name"],
                payload["source_type"],
                str(payload["original_path"]),
                str(payload["stored_path"]),
                float(payload.get("fps") or 0),
                int(payload.get("frame_count") or 0),
                float(payload.get("duration_sec") or 0),
                int(payload.get("width") or 0),
                int(payload.get("height") or 0),
            ),
        )
    return get_video_asset(asset_id)


def get_video(video_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone())
    if not row:
        raise KeyError(f"视频不存在: {video_id}")
    return row


def create_video(payload: dict[str, Any]) -> dict[str, Any]:
    video_id = payload.get("id") or new_id("video")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO videos(id, project_id, asset_id, name, source_type, path, fps, frame_count, duration_sec, width, height)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                video_id,
                payload["project_id"],
                payload.get("asset_id"),
                payload["name"],
                payload["source_type"],
                str(payload["path"]),
                float(payload.get("fps") or 0),
                int(payload.get("frame_count") or 0),
                float(payload.get("duration_sec") or 0),
                int(payload.get("width") or 0),
                int(payload.get("height") or 0),
            ),
        )
    return get_video(video_id)


def list_frame_sets(project_id: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM frame_sets"
    params: list[Any] = []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(project_id)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute(sql, params).fetchall())
        frame_rows = {
            row["id"]: rows_to_dicts(
                conn.execute("SELECT path FROM frames WHERE frame_set_id=? LIMIT 20", (row["id"],)).fetchall()
            )
            for row in rows
        }
    for row in rows:
        row["config"] = json_loads(row.pop("config_json"), {})
    valid_rows = []
    for row in rows:
        output_dir = Path(row["output_dir"])
        has_existing_frame = any(_path_exists(frame.get("path")) for frame in frame_rows.get(row["id"], []))
        if output_dir.exists() and has_existing_frame:
            valid_rows.append(row)
    return valid_rows


def find_frame_set_by_name(project_id: str, name: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = row_to_dict(
            conn.execute(
                "SELECT * FROM frame_sets WHERE project_id=? AND name=? ORDER BY created_at DESC LIMIT 1",
                (project_id, name),
            ).fetchone()
        )
    if not row:
        return None
    row["config"] = json_loads(row.pop("config_json"), {})
    return row


def get_frame_set(frame_set_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM frame_sets WHERE id=?", (frame_set_id,)).fetchone())
    if not row:
        raise KeyError(f"帧集不存在: {frame_set_id}")
    row["config"] = json_loads(row.pop("config_json"), {})
    return row


def create_frame_set(payload: dict[str, Any]) -> dict[str, Any]:
    frame_set_id = payload.get("id") or new_id("frameset")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO frame_sets(id, project_id, video_id, name, output_dir, sample_every_n_frames, max_frames, frame_count, status, config_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                frame_set_id,
                payload["project_id"],
                payload["video_id"],
                payload["name"],
                str(payload["output_dir"]),
                int(payload["sample_every_n_frames"]),
                int(payload.get("max_frames") or 0),
                int(payload.get("frame_count") or 0),
                payload.get("status") or "created",
                json_dumps(payload.get("config") or {}),
            ),
        )
    return get_frame_set(frame_set_id)


def update_frame_set_status(frame_set_id: str, status: str, frame_count: int | None = None) -> None:
    with get_conn() as conn:
        if frame_count is None:
            conn.execute("UPDATE frame_sets SET status=? WHERE id=?", (status, frame_set_id))
        else:
            conn.execute("UPDATE frame_sets SET status=?, frame_count=? WHERE id=?", (status, frame_count, frame_set_id))


def insert_frames(frame_set_id: str, video_id: str, frame_paths: list[Path]) -> None:
    frame_set = get_frame_set(frame_set_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM frames WHERE frame_set_id=?", (frame_set_id,))
        for path in frame_paths:
            stem = path.stem
            frame_index = int(stem.split("_")[-1]) if stem.split("_")[-1].isdigit() else 0
            conn.execute(
                """
                INSERT INTO frames(id, frame_set_id, video_id, frame_index, path, width, height)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    new_id("frame"),
                    frame_set_id,
                    video_id,
                    frame_index,
                    str(path),
                    int(frame_set["config"].get("width") or 0),
                    int(frame_set["config"].get("height") or 0),
                ),
            )


def _normalize_rect(payload: dict[str, Any]) -> tuple[float, float, float, float]:
    x = max(0.0, min(1.0, float(payload.get("x") or 0)))
    y = max(0.0, min(1.0, float(payload.get("y") or 0)))
    w = max(0.001, min(1.0, float(payload.get("w") or 0.001)))
    h = max(0.001, min(1.0, float(payload.get("h") or 0.001)))
    if x + w > 1:
        w = 1 - x
    if y + h > 1:
        h = 1 - y
    return x, y, max(0.001, w), max(0.001, h)


def _rects_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ax1, ay1 = float(a["x"]), float(a["y"])
    ax2, ay2 = ax1 + float(a["w"]), ay1 + float(a["h"])
    bx1, by1 = float(b["x"]), float(b["y"])
    bx2, by2 = bx1 + float(b["w"]), by1 + float(b["h"])
    return max(ax1, bx1) < min(ax2, bx2) and max(ay1, by1) < min(ay2, by2)


def list_focus_regions(project_id: str | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM focus_regions"
    params: list[Any] = []
    where: list[str] = []
    if project_id:
        where.append("project_id=?")
        params.append(project_id)
    if enabled_only:
        where.append("enabled=1")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at, name"
    with get_conn() as conn:
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def get_focus_region(region_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM focus_regions WHERE id=?", (region_id,)).fetchone())
    if not row:
        raise KeyError(f"关注区域不存在: {region_id}")
    return row


def save_focus_region(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload["project_id"])
    region_id = payload.get("id") or new_id("focus")
    name = str(payload.get("name") or "未命名关注区域").strip()
    x, y, w, h = _normalize_rect(payload)
    candidate = {"id": region_id, "x": x, "y": y, "w": w, "h": h}
    for region in list_focus_regions(project_id, enabled_only=True):
        if region["id"] != region_id and _rects_overlap(candidate, region):
            raise ValueError(f"关注区域不能重叠：{name} 与 {region['name']} 有重叠")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO focus_regions(id, project_id, name, x, y, w, h, enabled, locked, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                x=excluded.x,
                y=excluded.y,
                w=excluded.w,
                h=excluded.h,
                enabled=excluded.enabled,
                locked=excluded.locked,
                updated_at=excluded.updated_at
            """,
            (
                region_id,
                project_id,
                name,
                x,
                y,
                w,
                h,
                1 if payload.get("enabled", True) else 0,
                1 if payload.get("locked", True) else 0,
                now_text(),
            ),
        )
    return get_focus_region(region_id)


def delete_focus_region(region_id: str) -> dict[str, Any]:
    region = get_focus_region(region_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM focus_regions WHERE id=?", (region_id,))
    return {"id": region_id, "project_id": region["project_id"], "deleted": True}


def delete_frame_set(frame_set_id: str) -> dict[str, Any]:
    frame_set = get_frame_set(frame_set_id)
    output_dir = Path(frame_set["output_dir"])
    if output_dir.exists():
        if not _is_under(output_dir, FRAMES_DIR):
            raise ValueError(f"帧集目录不在平台抽帧目录内，拒绝删除: {output_dir}")
        shutil.rmtree(output_dir)
    with get_conn() as conn:
        conn.execute("DELETE FROM frame_sets WHERE id=?", (frame_set_id,))
    return {"id": frame_set_id, "deleted": True}


def list_frames(frame_set_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        return rows_to_dicts(
            conn.execute("SELECT * FROM frames WHERE frame_set_id=? ORDER BY frame_index", (frame_set_id,)).fetchall()
        )


def get_frame(frame_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM frames WHERE id=?", (frame_id,)).fetchone())
    if not row:
        raise KeyError(f"帧不存在: {frame_id}")
    return row


def list_annotations(frame_set_id: str, frame_id: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM annotations WHERE frame_set_id=?"
    params: list[Any] = [frame_set_id]
    if frame_id:
        sql += " AND frame_id=?"
        params.append(frame_id)
    sql += " ORDER BY created_at"
    with get_conn() as conn:
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def replace_frame_annotations(project_id: str, frame_set_id: str, frame_id: str, annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = get_frame(frame_id)
    if frame["frame_set_id"] != frame_set_id:
        raise ValueError(f"帧 {frame_id} 不属于帧集 {frame_set_id}，拒绝覆盖标注")
    with get_conn() as conn:
        conn.execute("DELETE FROM annotations WHERE frame_id=?", (frame_id,))
        for item in annotations:
            conn.execute(
                """
                INSERT INTO annotations(id, project_id, frame_set_id, frame_id, track_id, label_code, x, y, w, h, source, is_keyframe, confirmed, confidence, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.get("id") or new_id("ann"),
                    project_id,
                    frame_set_id,
                    frame_id,
                    item.get("track_id") or None,
                    item["label_code"],
                    float(item["x"]),
                    float(item["y"]),
                    float(item["w"]),
                    float(item["h"]),
                    item.get("source") or "manual",
                    1 if item.get("is_keyframe") else 0,
                    1 if item.get("confirmed", True) else 0,
                    item.get("confidence"),
                    now_text(),
                ),
            )
    return list_annotations(frame_set_id, frame_id)


def add_annotation(project_id: str, frame_set_id: str, frame_id: str, item: dict[str, Any]) -> dict[str, Any]:
    annotation_id = item.get("id") or new_id("ann")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO annotations(id, project_id, frame_set_id, frame_id, track_id, label_code, x, y, w, h, source, is_keyframe, confirmed, confidence, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                annotation_id,
                project_id,
                frame_set_id,
                frame_id,
                item.get("track_id") or None,
                item["label_code"],
                float(item["x"]),
                float(item["y"]),
                float(item["w"]),
                float(item["h"]),
                item.get("source") or "manual",
                1 if item.get("is_keyframe") else 0,
                1 if item.get("confirmed", True) else 0,
                item.get("confidence"),
                now_text(),
            ),
        )
        return row_to_dict(conn.execute("SELECT * FROM annotations WHERE id=?", (annotation_id,)).fetchone()) or {}


def delete_track_interpolated(frame_set_id: str, track_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM annotations WHERE frame_set_id=? AND track_id=? AND source='interpolated' AND is_keyframe=0",
            (frame_set_id, track_id),
        )


def delete_frame_prelabels(frame_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM annotations WHERE frame_id=? AND source='prelabel' AND confirmed=0", (frame_id,))


def delete_frame_set_prelabels(frame_set_id: str) -> dict[str, Any]:
    get_frame_set(frame_set_id)
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM annotations WHERE frame_set_id=? AND source='prelabel' AND confirmed=0",
            (frame_set_id,),
        )
        return {"frame_set_id": frame_set_id, "deleted": cur.rowcount}


def confirm_frame_set_prelabels(frame_set_id: str) -> dict[str, Any]:
    get_frame_set(frame_set_id)
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE annotations SET confirmed=1, updated_at=CURRENT_TIMESTAMP WHERE frame_set_id=? AND source='prelabel' AND confirmed=0",
            (frame_set_id,),
        )
        return {"frame_set_id": frame_set_id, "confirmed": cur.rowcount}


def count_frame_set_prelabels(frame_set_id: str) -> dict[str, Any]:
    get_frame_set(frame_set_id)
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM annotations WHERE frame_set_id=? AND source='prelabel'", (frame_set_id,)).fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM annotations WHERE frame_set_id=? AND source='prelabel' AND confirmed=0", (frame_set_id,)).fetchone()[0]
        confirmed = conn.execute("SELECT COUNT(*) FROM annotations WHERE frame_set_id=? AND source='prelabel' AND confirmed=1", (frame_set_id,)).fetchone()[0]
        frames = conn.execute("SELECT COUNT(DISTINCT frame_id) FROM annotations WHERE frame_set_id=? AND source='prelabel'", (frame_set_id,)).fetchone()[0]
    return {"total": total, "pending": pending, "confirmed": confirmed, "frames": frames}


def create_or_get_track(project_id: str, frame_set_id: str, label_code: str, track_id: str | None = None) -> dict[str, Any]:
    with get_conn() as conn:
        if track_id:
            row = row_to_dict(conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone())
            if row:
                return row
        track_id = track_id or new_id("track")
        conn.execute(
            "INSERT INTO tracks(id, project_id, frame_set_id, label_code, name) VALUES(?,?,?,?,?)",
            (track_id, project_id, frame_set_id, label_code, f"{label_code}-{track_id[-4:]}"),
        )
        return row_to_dict(conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()) or {}


def list_tracks(frame_set_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM tracks WHERE frame_set_id=? ORDER BY created_at", (frame_set_id,)).fetchall())


def save_dataset_version(payload: dict[str, Any]) -> dict[str, Any]:
    dataset_id = payload.get("id") or new_id("dataset")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO dataset_versions(id, project_id, name, output_dir, label_codes_json, frame_set_ids_json, history_dataset_ids_json, status, summary_json, metadata_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                dataset_id,
                payload["project_id"],
                payload["name"],
                str(payload["output_dir"]),
                json_dumps(payload["label_codes"]),
                json_dumps(payload["frame_set_ids"]),
                json_dumps(payload.get("history_dataset_ids") or []),
                payload.get("status") or "created",
                json_dumps(payload.get("summary") or {}),
                json_dumps(payload.get("metadata") or {}),
            ),
        )
    return get_dataset_version(dataset_id)


def get_dataset_version(dataset_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM dataset_versions WHERE id=?", (dataset_id,)).fetchone())
    if not row:
        raise KeyError(f"数据集版本不存在: {dataset_id}")
    row["label_codes"] = json_loads(row.pop("label_codes_json"), [])
    row["frame_set_ids"] = json_loads(row.pop("frame_set_ids_json"), [])
    row["history_dataset_ids"] = json_loads(row.pop("history_dataset_ids_json"), [])
    row["summary"] = json_loads(row.pop("summary_json"), {})
    row["metadata"] = json_loads(row.pop("metadata_json"), {})
    return row


def list_dataset_versions(project_id: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM dataset_versions"
    params: list[Any] = []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(project_id)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute(sql, params).fetchall())
    for row in rows:
        row["label_codes"] = json_loads(row.pop("label_codes_json"), [])
        row["frame_set_ids"] = json_loads(row.pop("frame_set_ids_json"), [])
        row["history_dataset_ids"] = json_loads(row.pop("history_dataset_ids_json"), [])
        row["summary"] = json_loads(row.pop("summary_json"), {})
        row["metadata"] = json_loads(row.pop("metadata_json"), {})
    return rows


def save_train_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = payload.get("id") or new_id("train")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO train_jobs(id, project_id, dataset_version_id, name, base_model_path, output_dir, status, params_json, progress_json, metrics_json, log_text, process_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                job_id,
                payload["project_id"],
                payload["dataset_version_id"],
                payload["name"],
                str(payload["base_model_path"]),
                str(payload["output_dir"]),
                payload.get("status") or "created",
                json_dumps(payload.get("params") or {}),
                json_dumps(payload.get("progress") or {}),
                json_dumps(payload.get("metrics") or {}),
                payload.get("log_text") or "",
                int(payload.get("process_id") or 0),
            ),
        )
    return get_train_job(job_id)


def update_train_job(job_id: str, **updates: Any) -> None:
    allowed = {"status", "progress_json", "metrics_json", "log_text", "process_id", "started_at", "finished_at"}
    fields = []
    values = []
    for key, value in updates.items():
        if key not in allowed:
            continue
        fields.append(f"{key}=?")
        values.append(value)
    if not fields:
        return
    values.append(job_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE train_jobs SET {', '.join(fields)} WHERE id=?", values)


def get_train_job(job_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM train_jobs WHERE id=?", (job_id,)).fetchone())
    if not row:
        raise KeyError(f"训练任务不存在: {job_id}")
    row["params"] = json_loads(row.pop("params_json"), {})
    row["progress"] = json_loads(row.pop("progress_json", None), {})
    row["metrics"] = json_loads(row.pop("metrics_json"), {})
    return row


def list_train_jobs(project_id: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM train_jobs"
    params: list[Any] = []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(project_id)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute(sql, params).fetchall())
    for row in rows:
        row["params"] = json_loads(row.pop("params_json"), {})
        row["progress"] = json_loads(row.pop("progress_json", None), {})
        row["metrics"] = json_loads(row.pop("metrics_json"), {})
    return rows


def save_model_package(payload: dict[str, Any]) -> dict[str, Any]:
    package_id = payload.get("id") or new_id("package")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO model_packages(id, project_id, train_job_id, name, package_dir, status, metadata_json)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                package_id,
                payload["project_id"],
                payload["train_job_id"],
                payload["name"],
                str(payload["package_dir"]),
                payload.get("status") or "created",
                json_dumps(payload.get("metadata") or {}),
            ),
        )
    return get_model_package(package_id)


def get_model_package(package_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM model_packages WHERE id=?", (package_id,)).fetchone())
    if not row:
        raise KeyError(f"模型包不存在: {package_id}")
    row["metadata"] = json_loads(row.pop("metadata_json"), {})
    return row


def list_model_packages(project_id: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM model_packages"
    params: list[Any] = []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(project_id)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute(sql, params).fetchall())
    for row in rows:
        row["metadata"] = json_loads(row.pop("metadata_json"), {})
    return rows


def make_named_dir(root: Path, name: str) -> Path:
    path = root / safe_name(name)
    path.mkdir(parents=True, exist_ok=True)
    return path
