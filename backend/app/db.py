import random
import sqlite3
import string
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.logging import get_logger
from app.schemas import Chat, Message, Subject, User

log = get_logger(__name__)


def _resolve_db_path() -> Path:
    if settings.database_path:
        return Path(settings.database_path)
    return Path(__file__).parent.parent.parent / "data" / "homework_helper.db"


DB_PATH = _resolve_db_path()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
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


def init_db():
    log.info("Initializing database at %s", DB_PATH)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
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
                mode TEXT NOT NULL CHECK(mode IN ('guide', 'just-solve')),
                title TEXT NOT NULL DEFAULT 'New Chat',
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
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS verification_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
    log.info("Database initialized")


# --- User operations ---


def get_user_by_email(email: str) -> Optional[User]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            return None
        return User(id=row["id"], email=row["email"], created_at=_parse_dt(row["created_at"]))


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
        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            conn.execute("DELETE FROM verification_codes WHERE id = ?", (row["id"],))
            return False
        conn.execute("DELETE FROM verification_codes WHERE id = ?", (row["id"],))
        return True


# --- Subject operations ---


def create_subject(user_id: int, name: str) -> Subject:
    with get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("INSERT INTO subjects (user_id, name, created_at) VALUES (?, ?, ?)", (user_id, name, now))
        assert cur.lastrowid is not None
        return Subject(id=cur.lastrowid, user_id=user_id, name=name, created_at=_parse_dt(now))


def list_subjects(user_id: int) -> list[Subject]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return [Subject(id=r["id"], user_id=r["user_id"], name=r["name"], created_at=_parse_dt(r["created_at"])) for r in rows]


def delete_subject(subject_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        return cur.rowcount > 0


# --- Chat operations ---


def create_chat(subject_id: int, user_id: int, mode: str, title: str = "New Chat") -> Chat:
    with get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO chats (subject_id, user_id, mode, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (subject_id, user_id, mode, title, now, now),
        )
        assert cur.lastrowid is not None
        return Chat(id=cur.lastrowid, subject_id=subject_id, user_id=user_id, mode=mode, title=title, created_at=_parse_dt(now), updated_at=_parse_dt(now))


def list_chats(subject_id: int) -> list[Chat]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM chats WHERE subject_id = ? ORDER BY created_at DESC", (subject_id,)).fetchall()
        return [Chat(id=r["id"], subject_id=r["subject_id"], user_id=r["user_id"], mode=r["mode"], title=r["title"], created_at=_parse_dt(r["created_at"]), updated_at=_parse_dt(r["updated_at"])) for r in rows]


def get_chat(chat_id: int) -> Optional[Chat]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if not row:
            return None
        return Chat(id=row["id"], subject_id=row["subject_id"], user_id=row["user_id"], mode=row["mode"], title=row["title"], created_at=_parse_dt(row["created_at"]), updated_at=_parse_dt(row["updated_at"]))


def delete_chat(chat_id: int) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return cur.rowcount > 0


# --- Message operations ---


def save_message(chat_id: int, role: str, content: str, image_base64: Optional[str] = None, image_media_type: Optional[str] = None, metadata_json: Optional[str] = None) -> Message:
    with get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO messages (chat_id, role, content, image_base64, image_media_type, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chat_id, role, content, image_base64, image_media_type, metadata_json, now),
        )
        assert cur.lastrowid is not None
        return Message(id=cur.lastrowid, chat_id=chat_id, role=role, content=content, image_base64=image_base64, image_media_type=image_media_type, metadata_json=metadata_json, created_at=_parse_dt(now))


def get_messages(chat_id: int) -> list[Message]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC", (chat_id,)).fetchall()
        return [Message(id=r["id"], chat_id=r["chat_id"], role=r["role"], content=r["content"], image_base64=r["image_base64"], image_media_type=r["image_media_type"], metadata_json=r["metadata_json"], created_at=_parse_dt(r["created_at"])) for r in rows]
