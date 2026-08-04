import sqlite3
from pathlib import Path

from memory.config import REQUIRED_MEMORY_TABLES, resolve_memory_db_path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_key TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS concept_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id INTEGER NOT NULL,
    alias TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (concept_id) REFERENCES concepts(id)
);

CREATE TABLE IF NOT EXISTS concept_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_concept_id INTEGER NOT NULL,
    to_concept_id INTEGER NOT NULL,
    relation TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (from_concept_id) REFERENCES concepts(id),
    FOREIGN KEY (to_concept_id) REFERENCES concepts(id)
);

CREATE TABLE IF NOT EXISTS learner_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    observation TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS learner_concept_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    concept_id INTEGER NOT NULL,
    mastery REAL NOT NULL DEFAULT 0.0,
    confidence REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (concept_id) REFERENCES concepts(id)
);

CREATE TABLE IF NOT EXISTS learner_traits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    trait_key TEXT NOT NULL,
    trait_value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, subject_id, trait_key)
);

CREATE TABLE IF NOT EXISTS memory_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, subject_id, version)
);

CREATE TABLE IF NOT EXISTS memory_current (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    version_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, subject_id),
    FOREIGN KEY (version_id) REFERENCES memory_versions(id)
);

CREATE TABLE IF NOT EXISTS memory_update_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    chat_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS retrieval_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    query_text TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _resolve_db_path(db_path: Path | None = None) -> Path:
    return db_path if db_path is not None else resolve_memory_db_path()


class _MemoryConnectionContext:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = _resolve_db_path(db_path)
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._conn = conn
        return conn

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        assert self._conn is not None
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False


def get_conn(db_path: Path | None = None) -> _MemoryConnectionContext:
    return _MemoryConnectionContext(db_path)


def init_db(db_path: Path | None = None) -> Path:
    resolved_path = _resolve_db_path(db_path)
    with get_conn(resolved_path) as conn:
        conn.executescript(SCHEMA_SQL)
    return resolved_path


def list_tables(db_path: Path | None = None) -> set[str]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {row[0] for row in rows}


def missing_required_tables(db_path: Path | None = None) -> list[str]:
    table_names = list_tables(db_path)
    return [table for table in REQUIRED_MEMORY_TABLES if table not in table_names]
