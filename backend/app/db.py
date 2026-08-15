import random
import sqlite3
import string
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.logging import get_logger
from app.schemas import Chat, ChatSummary, Message, SubjectWithChats
from shared.schemas import Subject, User

log = get_logger(__name__)


def _resolve_db_path() -> Path:
    if settings.database_path:
        return Path(settings.database_path)
    return Path(__file__).parent.parent.parent / "data" / "homework_helper.db"


DB_PATH = _resolve_db_path()


def _resolve_debug_db_path() -> Path:
    if settings.debug_database_path:
        return Path(settings.debug_database_path)
    return Path(__file__).parent.parent.parent / "data" / "debug.db"


DEBUG_DB_PATH = _resolve_debug_db_path()

MAIN_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        refresh_token_expires_at TEXT,
        llm_config_yaml TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL DEFAULT 'New Chat',
        total_tokens INTEGER NOT NULL DEFAULT 0,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (subject_id) REFERENCES subjects(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
        content TEXT NOT NULL,
        image_base64 TEXT,
        image_media_type TEXT,
        metadata_json TEXT,
        drawing_json TEXT,
        quote TEXT,
        token_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS verification_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
"""

DEBUG_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS structured_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        message_id INTEGER,
        log TEXT NOT NULL,
        _req_id TEXT NOT NULL
    );
"""


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


# --- Row-to-Model helpers ---


def _row_to_user(row) -> User:
    return User(id=row["id"], email=row["email"], created_at=_parse_dt(row["created_at"]))


def _row_to_subject(row) -> Subject:
    return Subject(id=row["id"], user_id=row["user_id"], name=row["name"], created_at=_parse_dt(row["created_at"]))


def _row_to_chat(row) -> Chat:
    return Chat(
        id=row["id"], subject_id=row["subject_id"], user_id=row["user_id"],
        title=row["title"],
        total_tokens=row["total_tokens"], input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        created_at=_parse_dt(row["created_at"]), updated_at=_parse_dt(row["updated_at"]),
    )


def _row_to_message(row) -> Message:
    return Message(
        id=row["id"], chat_id=row["chat_id"], role=row["role"], content=row["content"],
        image_base64=row["image_base64"], image_media_type=row["image_media_type"],
        metadata_json=row["metadata_json"], drawing_json=row["drawing_json"], quote=row["quote"],
        token_count=row["token_count"],
        created_at=_parse_dt(row["created_at"]),
    )


@contextmanager
def _conn(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_conn():
    with _conn(DB_PATH) as conn:
        yield conn


@contextmanager
def get_debug_conn():
    with _conn(DEBUG_DB_PATH) as conn:
        yield conn


@contextmanager
def _conn_ctx(conn: sqlite3.Connection | None):
    if conn is not None:
        yield conn
    else:
        with get_conn() as c:
            yield c


def init_db():
    log.info("Initializing database at %s", DB_PATH)
    with get_conn() as conn:
        conn.executescript(MAIN_SCHEMA_SQL)
        _add_missing_columns(conn)
    log.info("Database initialized")


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Idempotent migrations for databases created before a schema change."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "llm_config_yaml" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN llm_config_yaml TEXT")
        log.info("Added llm_config_yaml column to users table")


def init_debug_db():
    log.info("Initializing debug database at %s", DEBUG_DB_PATH)
    with get_debug_conn() as conn:
        conn.executescript(DEBUG_SCHEMA_SQL)
    log.info("Debug database initialized")


# --- User operations ---


def get_user_by_email(email: str) -> Optional[User]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row) if row else None


def create_verification_code(email: str) -> str:
    code = "".join(random.choices(string.digits, k=6))
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM verification_codes WHERE email = ?", (email,))
        conn.execute("INSERT INTO verification_codes (email, code, expires_at) VALUES (?, ?, ?)", (email, code, expires_at))
    return code


def verify_code(email: str, code: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM verification_codes WHERE email = ? AND code = ?", (email, code)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM verification_codes WHERE id = ?", (row["id"],))
        return datetime.now(timezone.utc) <= datetime.fromisoformat(row["expires_at"])


def set_user_refresh_expiry(user_id: int, expires_at: str | None) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET refresh_token_expires_at = ? WHERE id = ?", (expires_at, user_id))

def get_user_refresh_expiry(email: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT refresh_token_expires_at FROM users WHERE email = ?", (email,)).fetchone()
        return row["refresh_token_expires_at"] if row else None


def list_all_users(conn: sqlite3.Connection | None = None) -> list[User]:
    with _conn_ctx(conn) as c:
        rows = c.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [_row_to_user(r) for r in rows]


def get_user_llm_config_yaml(user_id: int | None) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT llm_config_yaml FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["llm_config_yaml"] if row else None


def save_user_llm_config_yaml(user_id: int, yaml_text: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET llm_config_yaml = ? WHERE id = ?", (yaml_text, user_id))


# --- Subject operations ---


def create_subject(user_id: int, name: str) -> Subject:
    with get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("INSERT INTO subjects (user_id, name, created_at) VALUES (?, ?, ?)", (user_id, name, now))
        assert cur.lastrowid is not None
        return Subject(id=cur.lastrowid, user_id=user_id, name=name, created_at=_parse_dt(now))


def list_subjects(user_id: int, conn: sqlite3.Connection | None = None) -> list[Subject]:
    with _conn_ctx(conn) as c:
        rows = c.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return [_row_to_subject(r) for r in rows]


def get_subject(subject_id: int, user_id: int) -> Optional[Subject]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (subject_id, user_id)).fetchone()
        return _row_to_subject(row) if row else None


def delete_subject(subject_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        return cur.rowcount > 0


def update_subject_name(subject_id: int, user_id: int, name: str) -> Optional[Subject]:
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM subjects WHERE user_id = ? AND name = ? AND id != ?",
            (user_id, name, subject_id),
        ).fetchone()
        if existing:
            return None
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE subjects SET name = ?, created_at = ? WHERE id = ?", (name, now, subject_id))
        row = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        return _row_to_subject(row) if row else None


# --- Chat operations ---


def create_chat(subject_id: int, user_id: int, title: str = "New Chat") -> Chat:
    with get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO chats (subject_id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (subject_id, user_id, title, now, now),
        )
        assert cur.lastrowid is not None
        dt = _parse_dt(now)
        return Chat(id=cur.lastrowid, subject_id=subject_id, user_id=user_id, title=title, created_at=dt, updated_at=dt)


def list_chats(subject_id: int, conn: sqlite3.Connection | None = None) -> list[Chat]:
    with _conn_ctx(conn) as c:
        rows = c.execute("SELECT * FROM chats WHERE subject_id = ? ORDER BY created_at DESC", (subject_id,)).fetchall()
        return [_row_to_chat(r) for r in rows]


def get_chat(chat_id: int) -> Optional[Chat]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        return _row_to_chat(row) if row else None


def delete_chat(chat_id: int) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return cur.rowcount > 0


# --- Message operations ---


def save_message(chat_id: int, role: str, content: str, image_base64: Optional[str] = None, image_media_type: Optional[str] = None, metadata_json: Optional[str] = None, drawing_json: Optional[str] = None, quote: Optional[str] = None, token_count: int = 0) -> Message:
    with get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO messages (chat_id, role, content, image_base64, image_media_type, metadata_json, drawing_json, quote, token_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chat_id, role, content, image_base64, image_media_type, metadata_json, drawing_json, quote, token_count, now),
        )
        assert cur.lastrowid is not None
        return Message(id=cur.lastrowid, chat_id=chat_id, role=role, content=content, image_base64=image_base64, image_media_type=image_media_type, metadata_json=metadata_json, drawing_json=drawing_json, quote=quote, token_count=token_count, created_at=_parse_dt(now))
    
def get_messages(chat_id: int, conn: sqlite3.Connection | None = None) -> list[Message]:
    with _conn_ctx(conn) as c:
        rows = c.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC", (chat_id,)).fetchall()
        return [_row_to_message(r) for r in rows]


def update_chat_title(chat_id: int, title: str) -> Optional[Chat]:
    with get_conn() as conn:
        chat = conn.execute("SELECT subject_id FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if not chat:
            return None
        existing = conn.execute(
            "SELECT id FROM chats WHERE subject_id = ? AND title = ? AND id != ?",
            (chat["subject_id"], title, chat_id),
        ).fetchone()
        if existing:
            return None
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE chats SET title = ?, updated_at = ? WHERE id = ?", (title, now, chat_id))
        row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        return _row_to_chat(row) if row else None


def list_messages_with_logs() -> list[dict]:
    with get_debug_conn() as dconn:
        rows = dconn.execute(
            "SELECT DISTINCT message_id FROM structured_logs WHERE message_id IS NOT NULL"
        ).fetchall()
    if not rows:
        return []
    message_ids = [r["message_id"] for r in rows]
    placeholders = ",".join("?" for _ in message_ids)
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT DISTINCT m.*, c.title AS chat_title,
                  s.name AS subject_name, u.email AS user_email
            FROM messages m
            LEFT JOIN chats c ON m.chat_id = c.id
            LEFT JOIN subjects s ON c.subject_id = s.id
            LEFT JOIN users u ON c.user_id = u.id
            WHERE m.id IN ({placeholders})
            ORDER BY m.created_at DESC
        """, message_ids).fetchall()
        return [dict(r) for r in rows]


def update_chat_token_usage(chat_id: int, input_tokens: int, output_tokens: int, total_tokens: int) -> None:
    with get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE chats SET input_tokens = input_tokens + ?, output_tokens = output_tokens + ?, total_tokens = total_tokens + ?, updated_at = ? WHERE id = ?",
            (input_tokens, output_tokens, total_tokens, now, chat_id),
        )


def list_subjects_with_chat_metadata(user_id: int) -> list[SubjectWithChats]:
    with get_conn() as conn:
        subjects = conn.execute(
            "SELECT * FROM subjects WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        if not subjects:
            return []
        subject_ids = [s["id"] for s in subjects]
        placeholders = ",".join("?" for _ in subject_ids)
        chats = conn.execute(
            f"SELECT subject_id, id, title, total_tokens FROM chats WHERE subject_id IN ({placeholders}) ORDER BY created_at DESC",
            subject_ids,
        ).fetchall()
        chats_by_subject: dict[int, list[ChatSummary]] = {}
        for c in chats:
            chats_by_subject.setdefault(c["subject_id"], []).append(
                ChatSummary(id=c["id"], title=c["title"], total_tokens=c["total_tokens"])
            )
        return [
            SubjectWithChats(
                id=s["id"], user_id=s["user_id"], name=s["name"],
                created_at=_parse_dt(s["created_at"]),
                chats=chats_by_subject.get(s["id"], []),
            )
            for s in subjects
        ]


# --- Structured log operations ---


def insert_structured_logs_batch(rows: list[tuple]) -> None:
    """Insert a batch of (type, created_at, message_id, log, req_id) rows."""
    with get_debug_conn() as conn:
        conn.executemany(
            "INSERT INTO structured_logs (type, created_at, message_id, log, _req_id) VALUES (?, ?, ?, ?, ?)",
            rows,
        )


def list_structured_logs(conn: sqlite3.Connection | None = None) -> list[dict]:
    with _conn_ctx(conn) as c:
        rows = c.execute(
            "SELECT id, type, created_at, message_id, log FROM structured_logs ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def list_structured_logs_for_message(message_id: int, conn: sqlite3.Connection | None = None) -> list[dict]:
    with _conn_ctx(conn) as c:
        rows = c.execute(
            "SELECT id, type, created_at, message_id, log FROM structured_logs WHERE message_id = ? ORDER BY created_at ASC",
            (message_id,),
        ).fetchall()
        return [dict(r) for r in rows]