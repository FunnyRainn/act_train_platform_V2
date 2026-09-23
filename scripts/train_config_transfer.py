from __future__ import annotations

"""Train 标签和产品配置的独立离线迁移工具，仅使用 Python 标准库。"""

import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any
import uuid


FORMAT_NAME = "act-train-config-transfer"
FORMAT_VERSION = 1
DATABASE_RELATIVE = Path("data") / "act_train_platform.sqlite3"
TRANSFER_RELATIVE = Path("data") / "config-transfer"
CONFIG_NAME = "train-config.json"
MANIFEST_NAME = "MANIFEST.json"
COMPLETE_NAME = "COMPLETE.json"
REQUIRED_TABLE_COLUMNS = {
    "labels": {"code", "group_code", "name", "description", "box_instruction", "enabled"},
    "projects": {"id", "name", "product_name", "sop_name", "station_name", "label_codes_json", "notes"},
}


class TransferError(RuntimeError):
    """表示可向现场人员直接展示的受控迁移错误。"""


def canonical_json(value: Any) -> str:
    """生成稳定 JSON，供文件落盘和 SHA-256 校验共同使用。"""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value: Any) -> None:
    """以 UTF-8 和稳定换行写入 JSON，避免 Windows 中文乱码。"""

    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    """读取 UTF-8 JSON，并把解析错误转换为清晰的迁移错误。"""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransferError(f"无法读取 JSON：{path}：{exc}") from exc


def sha256_file(path: Path) -> str:
    """流式计算文件 SHA-256，避免把大文件一次读入内存。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def now_text() -> str:
    """返回适合报告和审计使用的本地时间。"""

    return datetime.now().astimezone().isoformat(timespec="seconds")


def require(condition: bool, message: str) -> None:
    """统一执行失败即停止的安全检查。"""

    if not condition:
        raise TransferError(message)


def database_path(train_root: Path) -> Path:
    """只接受 Train 根目录下的正式数据库位置。"""

    root = train_root.resolve()
    database = (root / DATABASE_RELATIVE).resolve()
    require(database.is_relative_to(root), "数据库路径越出 Train 根目录")
    require(database.is_file(), f"未找到 Train 数据库：{database}")
    return database


def assert_no_sqlite_sidecars(database: Path) -> None:
    """拒绝仍有 WAL/SHM 的数据库，防止备份遗漏未合并事务。"""

    paths = [Path(f"{database}{suffix}") for suffix in ("-wal", "-shm", "-journal")]
    existing = [path.name for path in paths if path.exists()]
    require(not existing, f"数据库仍有运行侧文件，请正常停止 Train 后重试：{', '.join(existing)}")


def _windows_process_rows() -> list[dict[str, str]]:
    """通过 Windows 自带 PowerShell 读取进程命令行，不依赖 psutil。"""

    if os.name != "nt":
        return []
    powershell = ("$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
                  "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Csv -NoTypeInformation")
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", powershell]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    require(result.returncode == 0, f"无法检查 Train 进程：{result.stderr.strip() or result.stdout.strip()}")
    return [dict(row) for row in csv.DictReader(io.StringIO(result.stdout))]


def assert_train_stopped(train_root: Path) -> None:
    """在 Windows 上按命令行和可执行文件位置识别仍在运行的 Train 服务。"""

    root_text = str(train_root.resolve()).casefold()
    matches: list[str] = []
    for row in _windows_process_rows():
        pid_text = str(row.get("ProcessId") or "0")
        if pid_text.isdigit() and int(pid_text) == os.getpid():
            continue
        command_line = str(row.get("CommandLine") or "").casefold()
        executable = str(row.get("ExecutablePath") or "").casefold()
        name = str(row.get("Name") or "").casefold()
        references_root = root_text in command_line or root_text in executable
        packaged_train = "act_train_platform" in command_line or name == "act_train_platform.exe"
        source_train = "app.py" in command_line and ("--port 28100" in command_line or "--port 18100" in command_line)
        if (references_root and packaged_train) or source_train:
            matches.append(f"PID={pid_text} {row.get('Name') or ''}")
    require(not matches, f"检测到 Train 仍在运行，请先正常停止：{'；'.join(matches)}")


def connect_read_only(database: Path) -> sqlite3.Connection:
    """以 SQLite URI 只读方式打开源数据库，禁止导出过程写入。"""

    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def validate_schema(connection: sqlite3.Connection) -> None:
    """只接受包含当前标签和产品白名单字段的数据库结构。"""

    for table, required in REQUIRED_TABLE_COLUMNS.items():
        actual = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        missing = sorted(required - actual)
        require(not missing, f"Train 数据库结构不兼容：{table} 缺少字段 {', '.join(missing)}")


def normalize_label(row: Any) -> dict[str, Any]:
    """只保留标签配置白名单字段并归一化基础类型。"""

    return {"code": str(row["code"]).strip().upper(), "group_code": str(row["group_code"]).strip().upper(),
            "name": str(row["name"] or "").strip(), "description": str(row["description"] or "").strip(),
            "box_instruction": str(row["box_instruction"] or "").strip(), "enabled": bool(row["enabled"])}


def normalize_project(row: Any) -> dict[str, Any]:
    """只保留产品配置白名单字段，并稳定化标签顺序。"""

    raw_codes = row["label_codes"] if isinstance(row, dict) and "label_codes" in row else json.loads(str(row["label_codes_json"] or "[]"))
    require(isinstance(raw_codes, list), f"产品 {row['id']} 的标签绑定不是列表")
    return {"id": str(row["id"]).strip(), "name": str(row["name"] or "").strip(),
            "product_name": str(row["product_name"] or "").strip(), "station_name": str(row["station_name"] or "").strip(),
            "sop_name": str(row["sop_name"] or "").strip(),
            "label_codes": sorted({str(code).strip().upper() for code in raw_codes if str(code).strip()}),
            "notes": str(row["notes"] or "").strip()}


def validate_config(config: dict[str, Any]) -> None:
    """校验配置结构、唯一键、A/B/C 标签规则和产品引用完整性。"""

    require(config.get("format") == FORMAT_NAME and config.get("format_version") == FORMAT_VERSION, "配置包格式不受支持")
    labels, projects = config.get("labels"), config.get("projects")
    require(isinstance(labels, list) and isinstance(projects, list), "配置包缺少标签或产品列表")
    label_codes: set[str] = set()
    for raw in labels:
        require(isinstance(raw, dict), "标签记录格式错误")
        label = normalize_label(raw)
        require(label["code"] and label["group_code"] in {"A", "B", "C"}, f"标签编码不合法：{label['code']}")
        require(label["code"].startswith(label["group_code"]), f"标签分组与编码不一致：{label['code']}")
        require(label["code"] not in label_codes, f"标签编码重复：{label['code']}")
        label_codes.add(label["code"])
    project_ids: set[str] = set()
    for raw in projects:
        require(isinstance(raw, dict), "产品记录格式错误")
        project = normalize_project(raw)
        require(project["id"] and project["id"] not in project_ids, f"产品 ID 为空或重复：{project['id']}")
        project_ids.add(project["id"])
        missing = sorted(set(project["label_codes"]) - label_codes)
        require(not missing, f"产品 {project['name']} 引用了未导出的标签：{', '.join(missing)}")


def read_config(database: Path) -> dict[str, Any]:
    """从源数据库读取标签和产品的逻辑配置快照。"""

    with connect_read_only(database) as connection:
        validate_schema(connection)
        labels = [normalize_label(row) for row in connection.execute("SELECT * FROM labels ORDER BY group_code,code")]
        projects = [normalize_project(row) for row in connection.execute("SELECT * FROM projects ORDER BY id")]
    config = {"format": FORMAT_NAME, "format_version": FORMAT_VERSION, "labels": labels, "projects": projects}
    validate_config(config)
    return config


def export_config(train_root: Path, output: Path) -> Path:
    """生成带完整性清单和完成标记的独立 JSON 配置包。"""

    assert_train_stopped(train_root)
    database = database_path(train_root)
    assert_no_sqlite_sidecars(database)
    require(not output.exists(), f"输出目录已存在：{output}")
    output.mkdir(parents=True)
    write_json(output / "INCOMPLETE.json", {"created_at": now_text()})
    config = read_config(database)
    config_path = output / CONFIG_NAME
    write_json(config_path, config)
    manifest = {"format": FORMAT_NAME, "format_version": FORMAT_VERSION, "package_id": uuid.uuid4().hex,
                "exported_at": now_text(), "counts": {"labels": len(config["labels"]), "projects": len(config["projects"])},
                "files": {CONFIG_NAME: {"sha256": sha256_file(config_path), "size": config_path.stat().st_size}}}
    manifest_path = output / MANIFEST_NAME
    write_json(manifest_path, manifest)
    write_json(output / COMPLETE_NAME, {"manifest_sha256": sha256_file(manifest_path)})
    (output / "INCOMPLETE.json").unlink()
    verify_package(output)
    return output


def verify_package(package: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """验证完成标记、清单、文件哈希、数量和配置引用。"""

    require(package.is_dir() and not (package / "INCOMPLETE.json").exists(), "迁移包不存在或导出未完成")
    complete, manifest_path = read_json(package / COMPLETE_NAME), package / MANIFEST_NAME
    require(manifest_path.is_file() and complete.get("manifest_sha256") == sha256_file(manifest_path), "迁移包清单已被修改")
    manifest = read_json(manifest_path)
    require(manifest.get("format") == FORMAT_NAME and manifest.get("format_version") == FORMAT_VERSION, "迁移包格式不受支持")
    files = manifest.get("files")
    require(set(files or {}) == {CONFIG_NAME}, "迁移包文件清单不符合白名单")
    config_path, record = package / CONFIG_NAME, files[CONFIG_NAME]
    require(config_path.is_file() and record.get("sha256") == sha256_file(config_path), f"迁移包文件哈希不一致：{CONFIG_NAME}")
    require(record.get("size") == config_path.stat().st_size, f"迁移包文件大小不一致：{CONFIG_NAME}")
    config = read_json(config_path)
    validate_config(config)
    require(manifest.get("counts") == {"labels": len(config["labels"]), "projects": len(config["projects"])}, "迁移包数量统计不一致")
    return manifest, config


def preflight_import(database: Path, config: dict[str, Any]) -> dict[str, list[str]]:
    """导入前比较目标配置；同键不同内容一律拒绝。"""

    with connect_read_only(database) as connection:
        validate_schema(connection)
        labels = {row["code"]: normalize_label(row) for row in connection.execute("SELECT * FROM labels")}
        projects = {row["id"]: normalize_project(row) for row in connection.execute("SELECT * FROM projects")}
    result = {"insert_labels": [], "skip_labels": [], "insert_projects": [], "skip_projects": []}
    conflicts: list[str] = []
    for raw in config["labels"]:
        item = normalize_label(raw)
        if item["code"] not in labels:
            result["insert_labels"].append(item["code"])
        elif labels[item["code"]] == item:
            result["skip_labels"].append(item["code"])
        else:
            conflicts.append(f"标签 {item['code']}")
    for raw in config["projects"]:
        item = normalize_project(raw)
        if item["id"] not in projects:
            result["insert_projects"].append(item["id"])
        elif projects[item["id"]] == item:
            result["skip_projects"].append(item["id"])
        else:
            conflicts.append(f"产品 {item['id']} ({item['name']})")
    require(not conflicts, f"目标存在同编码或同 ID 的不同配置，未执行导入：{'；'.join(conflicts)}")
    return result


def import_config(train_root: Path, package: Path) -> Path:
    """先备份目标数据库，再在单个事务中导入通过预检的新配置。"""

    assert_train_stopped(train_root)
    database = database_path(train_root)
    assert_no_sqlite_sidecars(database)
    manifest, config = verify_package(package)
    actions = preflight_import(database, config)
    transfer_root = train_root.resolve() / TRANSFER_RELATIVE
    transfer_root.mkdir(parents=True, exist_ok=True)
    # 微秒和随机短标识共同避免同一迁移包在一秒内重复导入时审计目录碰撞。
    batch = transfer_root / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{manifest['package_id'][:8]}-{uuid.uuid4().hex[:6]}"
    require(not batch.exists(), f"迁移批次已存在：{batch}")
    batch.mkdir(parents=True)
    before_hash, backup = sha256_file(database), batch / "before.sqlite3"
    shutil.copy2(database, backup)
    require(sha256_file(backup) == before_hash, "导入前数据库备份校验失败")
    write_json(batch / "INCOMPLETE.json", {"started_at": now_text(), "before_sha256": before_hash})
    try:
        connection = sqlite3.connect(database)
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            connection.execute("BEGIN IMMEDIATE")
            timestamp = now_text()
            for raw in config["labels"]:
                item = normalize_label(raw)
                if item["code"] in actions["insert_labels"]:
                    connection.execute("INSERT INTO labels(code,group_code,name,description,box_instruction,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                                       (item["code"], item["group_code"], item["name"], item["description"], item["box_instruction"], int(item["enabled"]), timestamp, timestamp))
            for raw in config["projects"]:
                item = normalize_project(raw)
                if item["id"] in actions["insert_projects"]:
                    connection.execute("INSERT INTO projects(id,name,product_name,sop_name,station_name,label_codes_json,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                                       (item["id"], item["name"], item["product_name"], item["sop_name"], item["station_name"], canonical_json(item["label_codes"]), item["notes"], timestamp, timestamp))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        report = {"status": "committed", "finished_at": now_text(), "package_id": manifest["package_id"],
                  "before_sha256": before_hash, "after_sha256": sha256_file(database), "actions": actions}
        write_json(batch / "REPORT.json", report)
        (batch / "INCOMPLETE.json").unlink()
        write_json(batch / "COMPLETE.json", {"report_sha256": sha256_file(batch / "REPORT.json")})
        return batch
    except Exception:
        require(sha256_file(backup) == before_hash, "导入失败且备份校验异常，请保留现场并停止操作")
        shutil.copy2(backup, database)
        require(sha256_file(database) == before_hash, "导入失败后的自动恢复校验失败，请保留现场并停止操作")
        raise


def _latest_batch(train_root: Path) -> Path:
    """选择最近一个已完成且尚未恢复的导入批次。"""

    root = train_root.resolve() / TRANSFER_RELATIVE
    batches = sorted((path for path in root.glob("*") if (path / "COMPLETE.json").is_file()), reverse=True)
    candidates = [path for path in batches if not (path / "RESTORED.json").exists()]
    require(bool(candidates), "没有可恢复的 Train 配置导入批次")
    return candidates[0]


def rollback(train_root: Path, batch: Path | None = None) -> Path:
    """仅在目标未被后续修改时恢复导入前数据库，并保存恢复前副本。"""

    assert_train_stopped(train_root)
    database = database_path(train_root)
    assert_no_sqlite_sidecars(database)
    selected = batch.resolve() if batch else _latest_batch(train_root)
    report = read_json(selected / "REPORT.json")
    require(report.get("status") == "committed" and not (selected / "RESTORED.json").exists(), "所选批次不可恢复")
    require(sha256_file(database) == report.get("after_sha256"), "导入后数据库已发生变化，拒绝覆盖新配置")
    backup = selected / "before.sqlite3"
    require(backup.is_file() and sha256_file(backup) == report.get("before_sha256"), "导入前备份缺失或校验失败")
    current = selected / "before-restore.sqlite3"
    shutil.copy2(database, current)
    with tempfile.NamedTemporaryFile(prefix="train-config-restore-", suffix=".sqlite3", dir=database.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copy2(backup, temporary)
        require(sha256_file(temporary) == report["before_sha256"], "恢复临时文件校验失败")
        os.replace(temporary, database)
    finally:
        temporary.unlink(missing_ok=True)
    require(sha256_file(database) == report["before_sha256"], "恢复后数据库哈希与导入前不一致")
    write_json(selected / "RESTORED.json", {"restored_at": now_text(), "restored_sha256": report["before_sha256"], "preserved_sha256": sha256_file(current)})
    return selected


def inspect(train_root: Path) -> dict[str, Any]:
    """只读显示源配置数量和数据库路径，便于操作前核对。"""

    database = database_path(train_root)
    config = read_config(database)
    return {"database": str(database), "labels": len(config["labels"]), "projects": len(config["projects"])}


def build_parser() -> argparse.ArgumentParser:
    """构造稳定的 inspect/export/verify/import/rollback 命令接口。"""

    value = argparse.ArgumentParser(description="Train 标签和产品配置独立迁移工具")
    commands = value.add_subparsers(dest="command", required=True)
    for name in ("inspect", "export", "import", "rollback"):
        sub = commands.add_parser(name)
        sub.add_argument("--train-root", required=True, type=Path)
        if name == "export":
            sub.add_argument("--output", required=True, type=Path)
        elif name == "import":
            sub.add_argument("--package", required=True, type=Path)
        elif name == "rollback":
            sub.add_argument("--batch", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("--package", required=True, type=Path)
    return value


def main(argv: list[str] | None = None) -> int:
    """执行命令并输出单一明确结果；受控错误不打印冗长堆栈。"""

    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            print(json.dumps(inspect(args.train_root), ensure_ascii=False, indent=2))
        elif args.command == "export":
            print(f"EXPORTED：{export_config(args.train_root, args.output)}")
        elif args.command == "verify":
            print(f"VERIFIED：{verify_package(args.package)[0]['package_id']}")
        elif args.command == "import":
            print(f"IMPORTED：{import_config(args.train_root, args.package)}")
        elif args.command == "rollback":
            print(f"RESTORED：{rollback(args.train_root, args.batch)}")
        return 0
    except (TransferError, OSError, sqlite3.Error) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
