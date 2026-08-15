import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import get_current_user
from app.db import get_conn, get_debug_conn, list_all_users, list_chats, list_subjects, get_messages, list_structured_logs, list_structured_logs_for_message, list_messages_with_logs
from app.logging import get_logger
from app.schemas import Chat, Message, MessageTraceEntry, SqlQueryResponse, StructuredLogEntry
from shared.schemas import Subject, User

log = get_logger(__name__)
router = APIRouter()


async def _require_debug_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.email not in ("leeyihong03@gmail.com", "leeshihau@gmail.com"):
        raise HTTPException(status_code=403, detail="Access denied")
    return current_user


@router.get("/api/debug/users", response_model=list[User])
async def get_users(user: User = Depends(_require_debug_user)) -> list[User]:
    return list_all_users()


@router.get("/api/debug/users/{user_id}/subjects", response_model=list[Subject])
async def get_subjects(user_id: int, user: User = Depends(_require_debug_user)) -> list[Subject]:
    return list_subjects(user_id)


@router.get("/api/debug/subjects/{subject_id}/chats", response_model=list[Chat])
async def get_chats(subject_id: int, user: User = Depends(_require_debug_user)) -> list[Chat]:
    return list_chats(subject_id)


@router.get("/api/debug/chats/{chat_id}/messages", response_model=list[Message])
async def get_messages_endpoint(chat_id: int, user: User = Depends(_require_debug_user)) -> list[Message]:
    return get_messages(chat_id)


class SqlRequest(BaseModel):
    sql: str
    limit: int | None = None


_COMMENT_OR_STRING = re.compile(
    r"""--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'|"(?:[^"]|"")*"|`(?:[^`]|``)*`|\[[^\]]*\]""",
    re.DOTALL,
)


def _has_top_level_limit(sql: str) -> bool:
    """Detect a LIMIT clause, ignoring comments and string literals."""
    stripped = _COMMENT_OR_STRING.sub(" ", sql)
    return re.search(r"\bLIMIT\b", stripped, re.IGNORECASE) is not None


def _apply_limit(sql: str, limit: int | None) -> str:
    """Append a LIMIT clause unless the user already provided their own."""
    if not limit or limit <= 0 or _has_top_level_limit(sql):
        return sql
    head = sql.lstrip()
    upper = head[:6].upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return sql
    return f"{sql.rstrip().rstrip(';').rstrip()}\nLIMIT {limit}"


@router.post("/api/debug/sql")
async def execute_sql(req: SqlRequest, user: User = Depends(_require_debug_user)) -> SqlQueryResponse:
    sql = _apply_limit(req.sql.strip(), req.limit)
    if not sql:
        raise HTTPException(status_code=400, detail="Empty SQL")

    try:
        with get_conn() as conn:
            cursor = conn.execute(sql)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return SqlQueryResponse(columns=columns, rows=rows, row_count=len(rows))
            return SqlQueryResponse(columns=[], rows=[], row_count=0)
    except Exception as e:
        log.error("SQL execution failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/debug/logs", response_model=list[StructuredLogEntry])
async def get_logs(message_id: int | None = Query(None), user: User = Depends(_require_debug_user)) -> list[StructuredLogEntry]:
    with get_debug_conn() as conn:
        if message_id is not None:
            rows = list_structured_logs_for_message(message_id, conn)
        else:
            rows = list_structured_logs(conn)
    return [StructuredLogEntry.model_validate(r) for r in rows]


@router.get("/api/debug/traces", response_model=list[MessageTraceEntry])
async def list_traces(user: User = Depends(_require_debug_user)) -> list[MessageTraceEntry]:
    return [MessageTraceEntry.model_validate(r) for r in list_messages_with_logs()]
