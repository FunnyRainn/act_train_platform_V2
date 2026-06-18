from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .paths import DB_PATH, ensure_runtime_dirs
from .runtime_paths import repair_runtime_paths_in_db


def connect() -> sqlite3.Connection:
    """用途：说明 SQLite 仓储读写和兼容数据访问 中 `connect` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入 SQLite，并按既有逻辑归一化返回数据。
    异常/失败语义：记录不存在、数据非法或 SQLite 操作失败时，沿用原有 KeyError、ValueError 或数据库异常语义。
    """

    ensure_runtime_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """用途：说明 SQLite 仓储读写和兼容数据访问 中 `get_conn` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入 SQLite，并按既有逻辑归一化返回数据。
    异常/失败语义：记录不存在、数据非法或 SQLite 操作失败时，沿用原有 KeyError、ValueError 或数据库异常语义。
    """

    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """用途：说明 SQLite 仓储读写和兼容数据访问 中 `row_to_dict` 的职责和调用边界。
    入参：row，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入 SQLite，并按既有逻辑归一化返回数据。
    异常/失败语义：记录不存在、数据非法或 SQLite 操作失败时，沿用原有 KeyError、ValueError 或数据库异常语义。
    """

    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """用途：说明 SQLite 仓储读写和兼容数据访问 中 `rows_to_dicts` 的职责和调用边界。
    入参：rows，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入 SQLite，并按既有逻辑归一化返回数据。
    异常/失败语义：记录不存在、数据非法或 SQLite 操作失败时，沿用原有 KeyError、ValueError 或数据库异常语义。
    """

    return [row_to_dict(row) or {} for row in rows]


def json_dumps(value: Any) -> str:
    """用途：说明 SQLite 仓储读写和兼容数据访问 中 `json_dumps` 的职责和调用边界。
    入参：value，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入 SQLite，并按既有逻辑归一化返回数据。
    异常/失败语义：记录不存在、数据非法或 SQLite 操作失败时，沿用原有 KeyError、ValueError 或数据库异常语义。
    """

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None, default: Any = None) -> Any:
    """用途：说明 SQLite 仓储读写和兼容数据访问 中 `json_loads` 的职责和调用边界。
    入参：value、default，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入 SQLite，并按既有逻辑归一化返回数据。
    异常/失败语义：记录不存在、数据非法或 SQLite 操作失败时，沿用原有 KeyError、ValueError 或数据库异常语义。
    """

    if not value:
        return default
    return json.loads(value)


def init_db() -> None:
    """用途：说明 SQLite 仓储读写和兼容数据访问 中 `init_db` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入 SQLite，并按既有逻辑归一化返回数据。
    异常/失败语义：记录不存在、数据非法或 SQLite 操作失败时，沿用原有 KeyError、ValueError 或数据库异常语义。
    """

    ensure_runtime_dirs()
    schema_path = Path(__file__).with_name("schema.sql")
    with get_conn() as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        _migrate(conn)
        repair_runtime_paths_in_db(conn)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """用途：说明 SQLite 仓储读写和兼容数据访问 中 `_has_column` 的职责和调用边界。
    入参：conn、table、column，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入 SQLite，并按既有逻辑归一化返回数据。
    异常/失败语义：记录不存在、数据非法或 SQLite 操作失败时，沿用原有 KeyError、ValueError 或数据库异常语义。
    """

    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _migrate(conn: sqlite3.Connection) -> None:
    """用途：说明 SQLite 仓储读写和兼容数据访问 中 `_migrate` 的职责和调用边界。
    入参：conn，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入 SQLite，并按既有逻辑归一化返回数据。
    异常/失败语义：记录不存在、数据非法或 SQLite 操作失败时，沿用原有 KeyError、ValueError 或数据库异常语义。
    """

    if not _has_column(conn, "videos", "asset_id"):
        conn.execute("ALTER TABLE videos ADD COLUMN asset_id TEXT")
    if not _has_column(conn, "train_jobs", "progress_json"):
        conn.execute("ALTER TABLE train_jobs ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}'")
    if not _has_column(conn, "train_jobs", "process_id"):
        conn.execute("ALTER TABLE train_jobs ADD COLUMN process_id INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS focus_regions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            x REAL NOT NULL,
            y REAL NOT NULL,
            w REAL NOT NULL,
            h REAL NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            locked INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    if not _has_column(conn, "dataset_versions", "metadata_json"):
        conn.execute("ALTER TABLE dataset_versions ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
