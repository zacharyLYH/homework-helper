from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.db import get_conn, list_all_users, list_chats, list_subjects, get_messages
from app.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


def _check_prod():
    if settings.environment == "prod":
        raise HTTPException(status_code=403, detail="Not available in production")


@router.get("/api/debug/users")
async def get_users():
    _check_prod()
    return [u.model_dump() for u in list_all_users()]


@router.get("/api/debug/users/{user_id}/subjects")
async def get_subjects(user_id: int):
    _check_prod()
    return [s.model_dump() for s in list_subjects(user_id)]


@router.get("/api/debug/subjects/{subject_id}/chats")
async def get_chats(subject_id: int):
    _check_prod()
    return [c.model_dump() for c in list_chats(subject_id)]


@router.get("/api/debug/chats/{chat_id}/messages")
async def get_messages_endpoint(chat_id: int):
    _check_prod()
    return [m.model_dump() for m in get_messages(chat_id)]


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
