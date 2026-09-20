"""Camada de acesso ao SQLite: conexao, schema e migracoes incrementais."""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    provider        TEXT NOT NULL,
    remote_id       TEXT,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    request_json    TEXT NOT NULL,
    result_json     TEXT,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);

CREATE TABLE IF NOT EXISTS tracks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    sample_rate INTEGER,
    duration_s  REAL,
    lufs        REAL,
    seed        INTEGER,
    stems_json  TEXT,
    favorite    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tracks_job ON tracks(job_id);
"""

_local = threading.local()


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Conexao por thread. O Streamlit executa reruns em threads distintas."""
    key = f"conn_{db_path}"
    conn = getattr(_local, key, None)
    if conn is None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        _configure(conn)
        setattr(_local, key, conn)
    return conn


def init_schema(db_path: Path) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.executescript(_DDL)
        conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")


@contextmanager
def transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
