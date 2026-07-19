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
from app.schemas import (
    ChatRequest,
    ChatResponse,
    RunMetadata,
    ToolCallInfo,
    User,
)

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


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    thread_id = str(req.chat_id) if req.chat_id else (req.thread_id or str(uuid.uuid4()))
    log.info("Chat request: thread_id=%s, chat_id=%s, message_length=%d", thread_id, req.chat_id, len(req.message))

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

    try:
        result = compiled_graph.invoke(initial_state, config=config)
    except Exception as e:
        log.error("Graph execution failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph execution failed: {e}")

    messages = result.get("messages", [])
    category = result.get("category", "")
    reply = ""
    tool_calls: list[ToolCallInfo] = []
    token_usage: dict[str, int] | None = None
    last_node = category or "general"

    for msg in messages:
        if isinstance(msg, AIMessage):
            if msg.content:
                reply = msg.content if isinstance(msg.content, str) else str(msg.content)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append(ToolCallInfo(
                        name=tc["name"],
                        args=tc.get("args", {}),
                        result="",
                    ))
            if msg.usage_metadata:
                tu = msg.usage_metadata
                if isinstance(tu, dict):
                    token_usage = {
                        "input_tokens": int(tu.get("input_tokens", 0) or 0),
                        "output_tokens": int(tu.get("output_tokens", 0) or 0),
                        "total_tokens": int(tu.get("total_tokens", 0) or 0),
                    }
                else:
                    token_usage = {
                        "input_tokens": tu.input_tokens,
                        "output_tokens": tu.output_tokens,
                        "total_tokens": tu.total_tokens,
                    }

    if not reply and messages:
        last = messages[-1]
        if hasattr(last, "content"):
            reply = last.content if isinstance(last.content, str) else str(last.content)

    final_reply = reply or "No response generated."

    save_message(
        chat_id=req.chat_id or 0,
        role="assistant",
        content=final_reply,
        metadata_json=json.dumps({
            "node": last_node,
            "tool_calls": [tc.model_dump() for tc in tool_calls],
            "token_usage": token_usage,
        }),
    )

    log.info("Chat response: thread_id=%s, node=%s, reply_length=%d", thread_id, last_node, len(final_reply))

    return ChatResponse(
        reply=final_reply,
        thread_id=thread_id,
        run=RunMetadata(
            node=last_node,
            thread_id=thread_id,
            token_usage=token_usage,
            tool_calls=tool_calls,
        ),
    )


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
