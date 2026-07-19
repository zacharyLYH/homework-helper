from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.db import get_conn
from app.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


def _check_prod():
    if settings.environment == "prod":
        raise HTTPException(status_code=403, detail="Not available in production")


@router.get("/api/debug/users")
async def get_users():
    _check_prod()
    with get_conn() as conn:
        users = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [dict(u) for u in users]


@router.get("/api/debug/users/{user_id}/subjects")
async def get_subjects(user_id: int):
    _check_prod()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM subjects WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/api/debug/subjects/{subject_id}/chats")
async def get_chats(subject_id: int):
    _check_prod()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM chats WHERE subject_id = ? ORDER BY created_at DESC", (subject_id,)
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/api/debug/chats/{chat_id}/messages")
async def get_messages(chat_id: int):
    _check_prod()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC", (chat_id,)
        ).fetchall()
        return [dict(r) for r in rows]


class SqlRequest(BaseModel):
    sql: str


@router.post("/api/debug/sql")
async def execute_sql(req: SqlRequest):
    _check_prod()
    sql = req.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="Empty SQL")

    try:
        with get_conn() as conn:
            cursor = conn.execute(sql)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return {"columns": columns, "rows": rows, "row_count": len(rows)}
            return {"columns": [], "rows": [], "row_count": 0}
    except Exception as e:
        log.error("SQL execution failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
