from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth import get_current_user
from app.db import get_subject
from memory.db import get_conn
from memory.service.main import load_memory_context
from shared.schemas import (
    MemoryContextResponse,
    MemoryJob,
    MemoryJobsResponse,
    User,
)


router = APIRouter(tags=["memory"])


def _memory_disabled_payload(request: Request) -> dict:
    return {
        "error": "memory_disabled",
        "reason": getattr(request.app.state, "memory_status_reason", "unknown"),
        "message": "Memory subsystem is disabled",
    }


def _require_memory_enabled(request: Request) -> None:
    if not bool(getattr(request.app.state, "memory_enabled", False)):
        raise HTTPException(status_code=503, detail=_memory_disabled_payload(request))


def _get_owned_subject_id(subject_id: int, user_id: int) -> int:
    subject = get_subject(subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject.id


@router.get("/api/memory/subjects/{subject_id}/context", response_model=MemoryContextResponse)
async def get_memory_context(
    subject_id: int,
    request: Request,
    user: User = Depends(get_current_user),
) -> MemoryContextResponse:
    _require_memory_enabled(request)
    _get_owned_subject_id(subject_id, user.id)

    context = load_memory_context(user_id=user.id, subject_id=subject_id)
    return MemoryContextResponse(
        subject_id=subject_id,
        user_id=user.id,
        memory_context=context.rendered,
        memory_loaded=not context.is_empty,
    )


@router.get("/api/memory/subjects/{subject_id}/jobs", response_model=MemoryJobsResponse)
async def list_memory_jobs(
    subject_id: int,
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    user: User = Depends(get_current_user),
) -> MemoryJobsResponse:
    _require_memory_enabled(request)
    _get_owned_subject_id(subject_id, user.id)

    rows: list = []
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, status, chat_id, payload_json, created_at, updated_at
            FROM memory_update_jobs
            WHERE user_id = ? AND subject_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (user.id, subject_id, limit),
        ).fetchall()

    jobs = [
        MemoryJob(
            id=row["id"],
            status=row["status"],
            chat_id=row["chat_id"],
            payload_json=row["payload_json"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]

    return MemoryJobsResponse(subject_id=subject_id, user_id=user.id, jobs=jobs)
