import json
import uuid
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.auth import get_current_user
from app.db import get_chat, get_messages, save_message, update_chat_title
from app.graph import compiled_graph, llm
from app.logging import get_logger
from app.schemas import ChatRequest, User

log = get_logger(__name__)
router = APIRouter()

def _build_lc_messages(req: ChatRequest) -> list:
    if req.messages:
        lc_messages = []
        for m in req.messages:
            if m["role"] == "user":
                lc_messages.append(HumanMessage(content=m["content"]))
            else:
                lc_messages.append(AIMessage(content=m["content"]))
        return lc_messages

    content_parts = []
    if req.image and req.image_media_type:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{req.image_media_type};base64,{req.image}"},
        })
    content_parts.append({"type": "text", "text": req.message})

    if len(content_parts) == 1:
        return [HumanMessage(content=req.message)]
    return [HumanMessage(content=content_parts)]


async def generate_title_stream(chat_id: int) -> AsyncGenerator[str, None]:
    messages = get_messages(chat_id)
    if not messages:
        return

    conversation = "\n".join(f"{m.role}: {m.content}" for m in messages[:6])
    prompt = f"Generate a short title (max 40 chars) for this conversation:\n{conversation}\nTitle:"

    try:
        async for chunk in llm.astream(prompt):
            if hasattr(chunk, "content") and chunk.content:
                yield str(chunk.content)
    except Exception as e:
        log.error("Title generation failed: %s", e)


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, user: User = Depends(get_current_user)):
    thread_id = str(req.chat_id) if req.chat_id else (req.thread_id or str(uuid.uuid4()))
    log.info("Chat stream request: thread_id=%s, chat_id=%s, message_length=%d", thread_id, req.chat_id, len(req.message))

    save_message(
        chat_id=req.chat_id or 0,
        role="user",
        content=req.message,
        image_base64=req.image,
        image_media_type=req.image_media_type,
    )

    lc_messages = _build_lc_messages(req)
    initial_state = {"messages": lc_messages, "category": ""}
    config = RunnableConfig(configurable={"thread_id": thread_id})

    async def event_generator():
        full_reply = ""
        last_node = "general"
        try:
            async for msg, metadata in compiled_graph.astream(
                initial_state, config=config, stream_mode="messages"
            ):
                if isinstance(msg, AIMessage) and msg.content:
                    node = metadata["langgraph_node"] if isinstance(metadata, dict) else ""
                    if node in ("router", "tool_executor"):
                        continue
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    full_reply += content
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

            save_message(
                chat_id=req.chat_id or 0,
                role="assistant",
                content=full_reply or "No response generated.",
            )

            if req.chat_id:
                existing = get_chat(req.chat_id)
                if existing and existing.title == "New Chat":
                    title = ""
                    async for title_chunk in generate_title_stream(req.chat_id):
                        title += title_chunk
                        yield f"data: {json.dumps({'type': 'title', 'content': title_chunk})}\n\n"
                    if title.strip():
                        update_chat_title(req.chat_id, title.strip()[:40])

            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id})}\n\n"
        except Exception as e:
            log.error("Stream execution failed: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
