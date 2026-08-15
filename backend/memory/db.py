import sqlite3
from pathlib import Path

from memory.config import REQUIRED_MEMORY_TABLES, resolve_memory_db_path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    concept_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(subject_id, concept_key)
);

CREATE INDEX IF NOT EXISTS idx_concepts_subject ON concepts (subject_id);

CREATE TABLE IF NOT EXISTS concept_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_concept_id INTEGER NOT NULL,
    to_concept_id INTEGER NOT NULL,
    relation TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(from_concept_id, to_concept_id, relation),
    FOREIGN KEY (from_concept_id) REFERENCES concepts(id),
    FOREIGN KEY (to_concept_id) REFERENCES concepts(id)
);

CREATE INDEX IF NOT EXISTS idx_edges_from ON concept_edges (from_concept_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON concept_edges (to_concept_id);

CREATE TABLE IF NOT EXISTS learner_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    observation TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_observations_scope_time ON learner_observations (user_id, subject_id, created_at DESC);

CREATE TABLE IF NOT EXISTS learner_concept_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    concept_id INTEGER NOT NULL,
    mastery REAL NOT NULL DEFAULT 0.0,
    confidence REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, subject_id, concept_id),
    FOREIGN KEY (concept_id) REFERENCES concepts(id)
);

CREATE INDEX IF NOT EXISTS idx_concept_state_scope ON learner_concept_state (user_id, subject_id, mastery);

CREATE TABLE IF NOT EXISTS learner_traits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    traits_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, subject_id)
);

CREATE TABLE IF NOT EXISTS memory_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, subject_id)
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

CREATE INDEX IF NOT EXISTS idx_jobs_status_time ON memory_update_jobs (status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_scope_time ON memory_update_jobs (user_id, subject_id, created_at DESC);

CREATE TABLE IF NOT EXISTS retrieval_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    query_text TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_traces_scope_time ON retrieval_traces (user_id, subject_id, created_at DESC);
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
    rows: list[sqlite3.Row] = []
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {row[0] for row in rows}


def missing_required_tables(db_path: Path | None = None) -> list[str]:
    table_names = list_tables(db_path)
    return [table for table in REQUIRED_MEMORY_TABLES if table not in table_names]
