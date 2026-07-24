from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.db import (
    create_chat,
    create_subject,
    delete_chat,
    delete_subject,
    get_chat,
    get_messages,
    list_chats,
    list_subjects,
)
from app.logging import get_logger
from app.schemas import Chat, Subject, User

log = get_logger(__name__)
router = APIRouter()


# --- Ownership helpers ---


def _get_owned_subject(subject_id: int, user_id: int) -> Subject:
    """Get a subject and verify it belongs to the user. Raises 404 if not found."""
    subject = next((s for s in list_subjects(user_id) if s.id == subject_id), None)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


def _get_owned_chat(chat_id: int, user_id: int) -> Chat:
    """Get a chat and verify it belongs to the user. Raises 404 if not found."""
    chat = get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    _get_owned_subject(chat.subject_id, user_id)
    return chat


# --- Subject endpoints ---


@router.get("/api/subjects")
async def get_subjects(user: User = Depends(get_current_user)):
    return list_subjects(user.id)


@router.post("/api/subjects", response_model=Subject)
async def create_subject_route(name: str, user: User = Depends(get_current_user)):
    return create_subject(user.id, name)


@router.delete("/api/subjects/{subject_id}")
async def delete_subject_route(subject_id: int, user: User = Depends(get_current_user)):
    _get_owned_subject(subject_id, user.id)
    delete_subject(subject_id)
    return {"message": "Deleted"}


# --- Chat endpoints ---


@router.get("/api/chats")
async def get_chats(subject_id: int = Query(...), user: User = Depends(get_current_user)):
    _get_owned_subject(subject_id, user.id)
    return list_chats(subject_id)


@router.post("/api/chats", response_model=Chat)
async def create_chat_route(
    subject_id: int,
    mode: str = "guide",
    title: str = "New Chat",
    user: User = Depends(get_current_user),
):
    _get_owned_subject(subject_id, user.id)
    return create_chat(subject_id, user.id, mode, title)


@router.get("/api/chats/{chat_id}")
async def get_chat_route(chat_id: int, user: User = Depends(get_current_user)):
    return _get_owned_chat(chat_id, user.id)


@router.get("/api/chats/{chat_id}/messages")
async def get_chat_messages(chat_id: int, user: User = Depends(get_current_user)):
    _get_owned_chat(chat_id, user.id)
    return get_messages(chat_id)


@router.delete("/api/chats/{chat_id}")
async def delete_chat_route(chat_id: int, user: User = Depends(get_current_user)):
    _get_owned_chat(chat_id, user.id)
    delete_chat(chat_id)
    return {"message": "Deleted"}