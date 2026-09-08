"""SQLite connection + migration runner. No ORM; plain rows keep behaviour obvious."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..config import CONFIG

_SCHEMA = Path(__file__).with_name("migrations.sql")


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else CONFIG.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit; we manage transactions explicitly
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO schema_meta(key, value) VALUES('version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("1",),
    )


def reset_db(db_path: Path | str | None = None) -> None:
    path = Path(db_path) if db_path is not None else CONFIG.db_path
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    conn = connect(path)
    try:
        migrate(conn)
    finally:
        conn.close()


def get_conn(db_path: Path | str | None = None) -> sqlite3.Connection:
    conn = connect(db_path)
    migrate(conn)
    return conn
