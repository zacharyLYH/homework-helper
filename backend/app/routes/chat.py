import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.auth import get_current_user
from app.db import save_message
from app.graph import compiled_graph
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


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    thread_id = req.thread_id or str(uuid.uuid4())
    log.info("Chat request: thread_id=%s, message_length=%d", thread_id, len(req.message))

    save_message(
        chat_id=0,
        role="user",
        content=req.message,
        image_base64=req.image,
        image_media_type=req.image_media_type,
    )

    content_parts = []
    if req.image and req.image_media_type:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{req.image_media_type};base64,{req.image}"},
        })
    content_parts.append({"type": "text", "text": req.message})

    if len(content_parts) == 1:
        user_msg = HumanMessage(content=req.message)
    else:
        user_msg = HumanMessage(content=content_parts)

    initial_state = {"messages": [user_msg], "category": ""}
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
        chat_id=0,
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
    thread_id = req.thread_id or str(uuid.uuid4())
    log.info("Chat stream request: thread_id=%s, message_length=%d", thread_id, len(req.message))

    save_message(
        chat_id=0,
        role="user",
        content=req.message,
        image_base64=req.image,
        image_media_type=req.image_media_type,
    )

    content_parts = []
    if req.image and req.image_media_type:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{req.image_media_type};base64,{req.image}"},
        })
    content_parts.append({"type": "text", "text": req.message})

    if len(content_parts) == 1:
        user_msg = HumanMessage(content=req.message)
    else:
        user_msg = HumanMessage(content=content_parts)

    initial_state = {"messages": [user_msg], "category": ""}
    config = RunnableConfig(configurable={"thread_id": thread_id})

    async def event_generator():
        full_reply = ""
        last_node = "general"
        try:
            async for msg, metadata in compiled_graph.astream(
                initial_state, config=config, stream_mode="messages"
            ):
                if isinstance(msg, AIMessage) and msg.content:
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    full_reply += content
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

            save_message(
                chat_id=0,
                role="assistant",
                content=full_reply or "No response generated.",
            )
            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id})}\n\n"
        except Exception as e:
            log.error("Stream execution failed: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
