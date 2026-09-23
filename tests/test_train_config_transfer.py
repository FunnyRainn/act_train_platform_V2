from __future__ import annotations

"""Train 独立配置迁移工具的隔离数据库回归测试。"""

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "train_config_transfer.py"
SPEC = importlib.util.spec_from_file_location("train_config_transfer", SCRIPT)
assert SPEC and SPEC.loader
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)
SCHEMA = (Path(__file__).resolve().parents[1] / "core" / "schema.sql").read_text(encoding="utf-8")


def digest(path: Path) -> str:
    """计算测试数据库哈希，用于证明恢复后字节一致。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_root(path: Path, *, populated: bool = False) -> Path:
    """创建不接触真实数据的最小 Train 根目录。"""

    database = path / "data" / "act_train_platform.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA)
        if populated:
            connection.execute("INSERT INTO labels(code,group_code,name,description,box_instruction,enabled) VALUES(?,?,?,?,?,?)",
                               ("C1", "C", "托盘", "完整托盘", "框完整外接矩形", 1))
            connection.execute("INSERT INTO projects(id,name,product_name,sop_name,station_name,label_codes_json,notes) VALUES(?,?,?,?,?,?,?)",
                               ("project-1", "产品配置一", "产品一", "仅追溯", "工位一", '[\"C1\"]', "备注"))
    return path


class TrainConfigTransferTests(unittest.TestCase):
    """使用临时目录覆盖正常迁移、阻断和恢复路径。"""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_windows_cmd_files_use_crlf_only(self) -> None:
        """Windows CMD 必须使用 CRLF，避免现场 cmd.exe 把相邻命令错误拼接。"""

        command_root = SCRIPT.parent / "train_config_transfer"
        for command in sorted(command_root.glob("*.cmd")):
            content = command.read_bytes()
            self.assertIn(b"\r\n", content, command.name)
            self.assertNotIn(b"\n", content.replace(b"\r\n", b""), command.name)

    def test_export_import_idempotent_and_rollback(self) -> None:
        source, target = make_root(self.root / "source", populated=True), make_root(self.root / "target")
        package = self.root / "package"
        transfer.export_config(source, package)
        before = digest(target / transfer.DATABASE_RELATIVE)
        first_batch = transfer.import_config(target, package)
        with sqlite3.connect(target / transfer.DATABASE_RELATIVE) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM labels").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT station_name FROM projects").fetchone()[0], "工位一")
        second_batch = transfer.import_config(target, package)
        report = transfer.read_json(second_batch / "REPORT.json")
        self.assertEqual(report["actions"]["skip_labels"], ["C1"])
        transfer.rollback(target, second_batch)
        transfer.rollback(target, first_batch)
        self.assertEqual(digest(target / transfer.DATABASE_RELATIVE), before)

    def test_missing_label_and_tampered_package_are_rejected(self) -> None:
        source, package = make_root(self.root / "source", populated=True), self.root / "package"
        transfer.export_config(source, package)
        config_path = package / transfer.CONFIG_NAME
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["labels"] = []
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(transfer.TransferError, "哈希不一致"):
            transfer.verify_package(package)
        config["projects"][0]["label_codes"] = ["C9"]
        with self.assertRaisesRegex(transfer.TransferError, "未导出的标签"):
            transfer.validate_config(config)

    def test_conflict_is_rejected_without_writing(self) -> None:
        source = make_root(self.root / "source", populated=True)
        target = make_root(self.root / "target", populated=True)
        package = self.root / "package"
        transfer.export_config(source, package)
        database = target / transfer.DATABASE_RELATIVE
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE labels SET name='冲突名称' WHERE code='C1'")
        before = digest(database)
        with self.assertRaisesRegex(transfer.TransferError, "不同配置"):
            transfer.import_config(target, package)
        self.assertEqual(digest(database), before)

    def test_transaction_failure_restores_original_bytes(self) -> None:
        source, target = make_root(self.root / "source", populated=True), make_root(self.root / "target")
        package = self.root / "package"
        transfer.export_config(source, package)
        database, before = target / transfer.DATABASE_RELATIVE, digest(target / transfer.DATABASE_RELATIVE)
        original_connect = transfer.sqlite3.connect

        class FailingConnection:
            """在产品写入时注入异常，其余操作转发给真实连接。"""

            def __init__(self, connection):
                self.connection = connection

            def execute(self, sql, parameters=()):
                if sql.startswith("INSERT INTO projects"):
                    raise sqlite3.OperationalError("injected failure")
                return self.connection.execute(sql, parameters)

            def __getattr__(self, name):
                return getattr(self.connection, name)

        def failing_connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)
            return FailingConnection(connection) if Path(args[0]).resolve() == database.resolve() else connection

        with patch.object(transfer.sqlite3, "connect", side_effect=failing_connect):
            with self.assertRaisesRegex(sqlite3.OperationalError, "injected failure"):
                transfer.import_config(target, package)
        self.assertEqual(digest(database), before)

    def test_sidecar_is_treated_as_running_state(self) -> None:
        root = make_root(self.root / "root")
        database = root / transfer.DATABASE_RELATIVE
        Path(f"{database}-wal").write_bytes(b"running")
        with self.assertRaisesRegex(transfer.TransferError, "运行侧文件"):
            transfer.assert_no_sqlite_sidecars(database)

    def test_source_and_packaged_train_processes_are_rejected(self) -> None:
        """源码默认端口和根目录内成品进程都必须触发停服门禁。"""

        root = make_root(self.root / "root")
        rows = [{"ProcessId": "101", "Name": "python.exe", "ExecutablePath": "D:\\Python\\python.exe",
                 "CommandLine": "python app.py --host 0.0.0.0 --port 28100"}]
        with patch.object(transfer, "_windows_process_rows", return_value=rows):
            with self.assertRaisesRegex(transfer.TransferError, "Train 仍在运行"):
                transfer.assert_train_stopped(root)
        rows = [{"ProcessId": "102", "Name": "act_train_platform.exe",
                 "ExecutablePath": str(root.resolve() / "act_train_platform.exe"), "CommandLine": "act_train_platform.exe"}]
        with patch.object(transfer, "_windows_process_rows", return_value=rows):
            with self.assertRaisesRegex(transfer.TransferError, "Train 仍在运行"):
                transfer.assert_train_stopped(root)


if __name__ == "__main__":
    unittest.main()
