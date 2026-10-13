"""原图批量导入：持久任务、逐文件提交、同项目内容复用，不生成任何空标注。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from PIL import Image

from core import store
from core.db import get_conn, row_to_dict, rows_to_dicts
from core.paths import ASSETS_DIR, FRAMES_DIR
from core.utils import new_id

# 页面通过 limits 接口使用同一份边界，禁止在浏览器另写一个不一致的限制。
LIMITS = {"files": 10000, "file_bytes": 32 * 1024 * 1024, "pixels": 32_000_000,
          "parallel_uploads": 2, "page_size": 100, "extensions": [".jpg", ".jpeg", ".png", ".bmp", ".webp"]}
FORMATS = {"JPEG": ".jpg", "PNG": ".png", "BMP": ".bmp", "WEBP": ".webp"}


def child(root: Path, *parts: str) -> Path:
    """库中项目/帧集ID也不可信：任何路径拼接均校验解析后的包含关系。"""
    root = root.resolve()
    result = root.joinpath(*parts).resolve()
    if not result.is_relative_to(root) or result == root:
        raise ValueError("素材路径越出平台目录")
    return result


def file_descriptor(raw: dict) -> dict:
    """原名只作元数据，不作磁盘文件名；拒绝路径穿越、驱动器和控制字符。"""
    if not isinstance(raw, dict) or set(raw) != {"relative_path", "size", "last_modified", "source_group", "split"}:
        raise ValueError("文件清单字段不完整")
    value = raw["relative_path"]
    if not isinstance(value, str) or not value or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError("原始相对路径无效或过长")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts or path.name in {"", "."}:
        raise ValueError("原图只能使用安全相对路径")
    if path.suffix.lower() not in LIMITS["extensions"]:
        raise ValueError("只接受 JPEG、PNG、BMP、WebP")
    if type(raw["size"]) is not int or not 0 < raw["size"] <= LIMITS["file_bytes"]:
        raise ValueError("单图必须在 1 字节至 32 MiB 范围")
    if type(raw["last_modified"]) is not int or raw["last_modified"] < 0:
        raise ValueError("文件修改时间无效")
    group = raw["source_group"]
    if not isinstance(group, str) or not group.strip() or len(group) > 200:
        raise ValueError("请填写真实拍摄来源组，未知时使用同一组并在导出时确认划分风险")
    if raw["split"] not in {"", "train", "val", "test"}:
        raise ValueError("数据拆分无效")
    return {**raw, "relative_path": str(path), "original_name": path.name, "source_group": group.strip()}


def create_job(body: dict) -> dict:
    """短事务一次登记元数据；重试同一 client_key 返回同任务，清单变化则拒绝。"""
    if not isinstance(body, dict) or set(body) - {"project_id", "frame_set_id", "name", "client_key", "files"}:
        raise ValueError("导入任务参数无效")
    project = store.get_project(body.get("project_id", ""))
    key, name, rows = body.get("client_key"), str(body.get("name") or "").strip(), body.get("files")
    if not isinstance(key, str) or not 1 <= len(key) <= 100 or not name or len(name) > 120:
        raise ValueError("请填写名称并提供任务幂等标识")
    if not isinstance(rows, list) or not 1 <= len(rows) <= LIMITS["files"]:
        raise ValueError("每次导入需 1 至 10000 张图片")
    rows = [file_descriptor(row) for row in rows]
    identities = [(r["relative_path"], r["size"], r["last_modified"]) for r in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("文件清单含重复条目，请重新选择")
    groups = {}
    for row in rows:
        if row["split"]:
            if row["source_group"] in groups and groups[row["source_group"]] != row["split"]:
                raise ValueError("同一来源组不能跨训练/验证/测试拆分")
            groups[row["source_group"]] = row["split"]
    manifest = hashlib.sha256(json.dumps([body.get("frame_set_id"), name, rows], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT * FROM image_import_jobs WHERE project_id=? AND client_key=?", (project["id"], key)).fetchone()
        if existing:
            if existing["manifest_sha256"] != manifest:
                raise ValueError("该任务的文件清单已变化，请恢复原清单或创建新任务")
            job_id = existing["id"]
        else:
            # 新建素材集与追加同样受项目来源分组约束，不能靠另建帧集跨拆分。
            for group, split in groups.items():
                conflict = conn.execute("SELECT 1 FROM image_import_items i JOIN image_import_jobs j ON j.id=i.job_id WHERE j.project_id=? AND i.source_group=? AND i.split NOT IN ('',?) LIMIT 1", (project["id"], group, split)).fetchone()
                if conflict: raise ValueError("该拍摄来源组已声明另一数据拆分")
            frame_set_id = body.get("frame_set_id")
            if frame_set_id:
                target = conn.execute("SELECT * FROM frame_sets WHERE id=? AND project_id=?", (frame_set_id, project["id"])).fetchone()
                if not target or json.loads(target["config_json"]).get("source_type") != "browser_images":
                    raise ValueError("只可向当前项目的原图素材集追加，不修改视频帧时序")
                # 已有明确拆分不可因追加重新解释；同拍摄来源的声明必须一致。
                for group, split in groups.items():
                    conflict = conn.execute("SELECT 1 FROM frame_image_sources s JOIN frames f ON f.id=s.frame_id JOIN frame_sets fs ON fs.id=f.frame_set_id WHERE fs.project_id=? AND s.source_group=? AND s.split NOT IN ('',?) LIMIT 1", (project["id"], group, split)).fetchone()
                    if conflict: raise ValueError("已有来源组声明了另一数据拆分")
            else:
                frame_set_id, video_id = new_id("frameset"), new_id("images")
                directory = child(FRAMES_DIR, project["id"], frame_set_id)
                directory.mkdir(parents=True, exist_ok=True)
                conn.execute("INSERT INTO videos(id,project_id,name,source_type,path) VALUES(?,?,?,'image_dataset',?)", (video_id, project["id"], name, str(directory)))
                conn.execute("INSERT INTO frame_sets(id,project_id,video_id,name,output_dir,sample_every_n_frames,status,config_json) VALUES(?,?,?,?,?,1,'ready',?)", (frame_set_id, project["id"], video_id, name, str(directory), json.dumps({"source_type":"browser_images"})))
            first = conn.execute("SELECT COALESCE(MAX(frame_index)+1,0) FROM frames WHERE frame_set_id=?", (frame_set_id,)).fetchone()[0]
            reserved = conn.execute("SELECT COALESCE(MAX(first_index+total),0) FROM image_import_jobs WHERE frame_set_id=?", (frame_set_id,)).fetchone()[0]
            job_id = new_id("image_import")
            conn.execute("INSERT INTO image_import_jobs(id,project_id,frame_set_id,client_key,manifest_sha256,total,first_index) VALUES(?,?,?,?,?,?,?)", (job_id, project["id"], frame_set_id, key, manifest, len(rows), max(first, reserved)))
            conn.executemany("INSERT INTO image_import_items(job_id,ordinal,original_name,relative_path,byte_size,last_modified,source_group,split) VALUES(?,?,?,?,?,?,?,?)", [(job_id, n, r["original_name"], r["relative_path"], r["size"], r["last_modified"], r["source_group"], r["split"]) for n,r in enumerate(rows)])
    return status(job_id)


def status(job_id: str, offset: int = 0, limit: int = 100) -> dict:
    """状态与清单分页，不在每次传图后返回全部10000行。"""
    if offset < 0 or not 0 <= limit <= LIMITS["page_size"]: raise ValueError("分页超出范围")
    with get_conn() as conn:
        job = row_to_dict(conn.execute("SELECT * FROM image_import_jobs WHERE id=?", (job_id,)).fetchone())
        if not job: raise KeyError("导入任务不存在")
        counts = dict(conn.execute("SELECT state,count(*) FROM image_import_items WHERE job_id=? GROUP BY state", (job_id,)).fetchall())
        items = rows_to_dicts(conn.execute("SELECT * FROM image_import_items WHERE job_id=? ORDER BY ordinal LIMIT ? OFFSET ?", (job_id, limit, offset)).fetchall())
    return {**job, "counts": counts, "items": items, "offset":offset}


def list_jobs(project_id: str) -> list[dict]:
    """刷新恢复最近任务；历史素材本身仍可在帧集入口访问。"""
    with get_conn() as conn:
        return rows_to_dicts(conn.execute("SELECT j.*, (SELECT count(*) FROM image_import_items i WHERE i.job_id=j.id AND i.state IN ('completed','duplicate')) AS done FROM image_import_jobs j WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT 100", (project_id,)).fetchall())


def cancel(job_id: str) -> dict:
    """取消阻止未完成文件提交，不删除已成功素材/标注；可显式恢复同一任务。"""
    with get_conn() as conn:
        conn.execute("UPDATE image_import_jobs SET state='cancelled' WHERE id=? AND state='active'", (job_id,))
    return status(job_id)


def resume(job_id: str) -> dict:
    with get_conn() as conn:
        conn.execute("UPDATE image_import_jobs SET state='active' WHERE id=? AND state='cancelled'", (job_id,))
    return status(job_id)


def inspect_upload(job_id: str, ordinal: int) -> dict:
    """上传前取得任务/条目身份；最终落库前再次校验取消状态。"""
    with get_conn() as conn:
        row = row_to_dict(conn.execute("SELECT i.*,j.project_id,j.frame_set_id,j.first_index,j.state AS job_state FROM image_import_items i JOIN image_import_jobs j ON j.id=i.job_id WHERE i.job_id=? AND i.ordinal=?", (job_id, ordinal)).fetchone())
    if not row: raise KeyError("导入文件不存在")
    if row["job_state"] == "cancelled": raise ValueError("任务已取消；已导入内容保留")
    return row


def fail(job_id: str, ordinal: int, message: str):
    with get_conn() as conn:
        conn.execute("UPDATE image_import_items SET state='failed',error=? WHERE job_id=? AND ordinal=? AND state NOT IN ('completed','duplicate')", (message[:300], job_id, ordinal))


def commit_image(job_id: str, ordinal: int, temporary: Path, sha: str) -> dict:
    """先验证解码/尺寸，再以一次单图短事务复用资产及写入帧引用。

    内容寻址文件永不覆盖未知资产。若事务失败留下同摘要文件，下次重试校验后复用；
    不启动全盘清理，不覆盖已有标注。真实像素只有这一张驻留内存。
    """
    with Image.open(temporary) as image:
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > LIMITS["pixels"] or image.format not in FORMATS:
            raise ValueError("图片格式或解码像素数不符合限制")
        suffix = FORMATS[image.format]
        if getattr(image, "n_frames", 1) != 1: raise ValueError("不接受动画图片，请先选择静态原图")
        image.verify()
    with Image.open(temporary) as image:
        image.load()  # header 合法不等于文件可解码，截断图不得标为完成。
    item = inspect_upload(job_id, ordinal)
    target = child(ASSETS_DIR, "images", item["project_id"], sha + suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        latest = conn.execute("SELECT state FROM image_import_jobs WHERE id=?", (job_id,)).fetchone()
        if not latest or latest[0] == "cancelled": raise ValueError("任务已取消，未提交当前文件")
        current = conn.execute("SELECT state,sha256 FROM image_import_items WHERE job_id=? AND ordinal=?", (job_id,ordinal)).fetchone()
        if current[0] in {"completed","duplicate"}:
            if current[1] != sha: raise ValueError("已完成文件内容变化，拒绝覆盖")
            return {"state": current[0], "ordinal":ordinal, "reused":True}
        asset = conn.execute("SELECT * FROM image_assets WHERE project_id=? AND sha256=?", (item["project_id"], sha)).fetchone()
        duplicate = asset is not None
        if asset:
            asset_id, path = asset["id"], Path(asset["path"])
            child(ASSETS_DIR, str(path.relative_to(ASSETS_DIR.resolve())))
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha: raise ValueError("已有素材缺失或校验失败，不覆盖原资产")
            source = conn.execute("SELECT source_group,split FROM frame_image_sources WHERE asset_id=? ORDER BY frame_id LIMIT 1", (asset_id,)).fetchone()
            if source:
                if item["split"] and source["split"] and item["split"] != source["split"]: raise ValueError("重复素材不能跨数据拆分")
                # 原图身份优先于重命名后的来源声明；新帧仍保留自己的原名/目录。
                item["source_group"], item["split"] = source["source_group"], source["split"] or item["split"]
        else:
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != sha: raise ValueError("素材摘要路径已有不同内容，拒绝覆盖")
            else:
                temporary.replace(target)
            asset_id, path = new_id("image_asset"), target
            conn.execute("INSERT INTO image_assets VALUES(?,?,?,?,?,?)", (asset_id,item["project_id"],sha,str(path),width,height))
        frame = conn.execute("SELECT f.id FROM frames f JOIN frame_image_sources s ON s.frame_id=f.id WHERE f.frame_set_id=? AND s.asset_id=? LIMIT 1", (item["frame_set_id"], asset_id)).fetchone()
        if frame:
            frame_id = frame[0]
            original = conn.execute("SELECT source_group,split FROM frame_image_sources WHERE frame_id=?", (frame_id,)).fetchone()
            if item["split"] and original["split"] and item["split"] != original["split"]: raise ValueError("重复素材不能改写已声明拆分")
        else:
            frame_id = new_id("frame")
            video_id = conn.execute("SELECT video_id FROM frame_sets WHERE id=?", (item["frame_set_id"],)).fetchone()[0]
            conn.execute("INSERT INTO frames(id,frame_set_id,video_id,frame_index,path,width,height) VALUES(?,?,?,?,?,?,?)", (frame_id,item["frame_set_id"],video_id,item["first_index"]+ordinal,str(path),width,height))
            conn.execute("INSERT INTO frame_image_sources VALUES(?,?,?,?,?,?)", (frame_id,asset_id,item["original_name"],item["relative_path"],item["source_group"],item["split"]))
            conn.execute("UPDATE frame_sets SET frame_count=(SELECT count(*) FROM frames WHERE frame_set_id=?) WHERE id=?", (item["frame_set_id"],item["frame_set_id"]))
            conn.execute("UPDATE videos SET frame_count=(SELECT count(*) FROM frames WHERE video_id=?) WHERE id=?", (video_id,video_id))
        state = "duplicate" if duplicate else "completed"
        conn.execute("UPDATE image_import_items SET state=?,error='',frame_id=?,sha256=? WHERE job_id=? AND ordinal=?", (state,frame_id,sha,job_id,ordinal))
        conn.execute("UPDATE image_import_jobs SET state='finished' WHERE id=? AND NOT EXISTS(SELECT 1 FROM image_import_items WHERE job_id=? AND state NOT IN ('completed','duplicate'))", (job_id,job_id))
    return {"state":state,"frame_id":frame_id,"ordinal":ordinal,"sha256":sha}


def frames_page(frame_set_id: str, offset: int = 0, limit: int = 100, frame_id: str = "") -> dict:
    """按稳定顺序直接定位；只返回一页元数据，不读图片，不随请求产生空标注。"""
    if offset < 0 or not 1 <= limit <= 100: raise ValueError("分页范围无效")
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM frame_sets WHERE id=?", (frame_set_id,)).fetchone(): raise KeyError("帧集不存在")
        # 同一读事务内计数/定位/取页保持一致；追加不会挤动已预留的导入序号。
        conn.execute("BEGIN")
        total = conn.execute("SELECT count(*) FROM frames WHERE frame_set_id=?", (frame_set_id,)).fetchone()[0]
        position = None
        if frame_id:
            row = conn.execute("SELECT frame_index,id FROM frames WHERE frame_set_id=? AND id=?", (frame_set_id,frame_id)).fetchone()
            if not row: raise KeyError("上次访问的帧已不存在")
            position = conn.execute("SELECT count(*) FROM frames WHERE frame_set_id=? AND (frame_index<? OR (frame_index=? AND id<?))", (frame_set_id,row[0],row[0],row[1])).fetchone()[0]
            offset = position // limit * limit
        rows = rows_to_dicts(conn.execute("SELECT f.*,s.original_name,s.relative_path,s.source_group,s.split FROM frames f LEFT JOIN frame_image_sources s ON s.frame_id=f.id WHERE f.frame_set_id=? ORDER BY f.frame_index,f.id LIMIT ? OFFSET ?", (frame_set_id,limit,offset)).fetchall())
    return {"items":rows,"total":total,"offset":offset,"limit":limit,"position":position}
