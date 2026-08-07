import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.auth import get_current_user
from app.config import settings
from app.constants import (
    NODE_ALIGNMENT_CHECK,
    NODE_TOOL_EXECUTOR,
    STATE_ALIGNMENT_SCORE,
    STATE_CALLED_TOOLS,
    STATE_MESSAGES,
    STATE_MODEL,
    STATE_PENDING_TOOL_CALLS,
    STATE_PENDING_TOOL_CALLS_DATA,
    STATE_REJECTED_REASON,
)
from app.db import get_chat, get_messages, save_message, update_chat_title, update_chat_token_usage
from app.graph import compiled_graph
from app.llm import title_llm
from app.logging import get_logger, structured_log
from app.schemas import ChatRequest, User
from app.structured_log import force_structured_logger, init_structured_logger

log = get_logger(__name__)
router = APIRouter()


# --- Helpers ---


def _build_lc_messages(req: ChatRequest) -> list:
    if req.messages:
        msgs: list = [
            HumanMessage(content=m["content"]) if m["role"] == "user"
            else AIMessage(content=m["content"])
            for m in req.messages
        ]
        if req.quote:
            for i in range(len(req.messages) - 1, -1, -1):
                if req.messages[i]["role"] == "user":
                    original = msgs[i].content
                    msgs[i] = HumanMessage(content=f'{original}\n\n[quoting: "{req.quote}"]')
                    break
        return msgs

    if req.image and req.image_media_type:
        return [HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": f"data:{req.image_media_type};base64,{req.image}"}},
            {"type": "text", "text": req.message},
        ])]
    content = req.message
    if req.quote:
        content = f'{content}\n\n[quoting: "{req.quote}"]'
    return [HumanMessage(content=content)]


def _save_user_message(req: ChatRequest) -> None:
    save_message(
        chat_id=req.chat_id or 0,
        role="user",
        content=req.message,
        image_base64=req.image,
        image_media_type=req.image_media_type,
        quote=req.quote,
    )


def _save_assistant_message(chat_id: int | None, full_reply: str, model_used: str, total_usage: dict, tool_calls: list[dict] | None = None) -> None:
    metadata = {"model": model_used, "usage": total_usage}
    if tool_calls:
        metadata["tool_calls"] = tool_calls
    msg = save_message(
        chat_id=chat_id or 0,
        role="assistant",
        content=full_reply or "No response generated.",
        metadata_json=json.dumps(metadata),
        token_count=total_usage["total_tokens"],
    )
    from app.structured_log import get_structured_logger
    logger = get_structured_logger()
    if logger is not None:
        logger.set_message_id(msg.id)
    if chat_id and total_usage["total_tokens"] > 0:
        update_chat_token_usage(
            chat_id,
            input_tokens=total_usage["input_tokens"],
            output_tokens=total_usage["output_tokens"],
            total_tokens=total_usage["total_tokens"],
        )


async def generate_title_stream(chat_id: int) -> AsyncGenerator[str, None]:
    messages = get_messages(chat_id)
    if not messages:
        return

    conversation = "\n".join(f"{m.role}: {m.content}" for m in messages[:6])
    prompt = f"Generate a short title (max 40 chars) for this conversation:\n{conversation}\nTitle:"

    try:
        async for chunk in title_llm.astream(prompt):
            if hasattr(chunk, "content") and chunk.content:
                yield str(chunk.content)
    except Exception as e:
        log.error("Title generation failed: %s", e)


async def _maybe_generate_title(chat_id: int | None) -> AsyncGenerator[str, None]:
    if not chat_id:
        return
    existing = get_chat(chat_id)
    if not existing or existing.title != "New Chat":
        return
    title = ""
    async for title_chunk in generate_title_stream(chat_id):
        title += title_chunk
        yield f"data: {json.dumps({'type': 'title', 'content': title_chunk})}\n\n"
    if title.strip():
        update_chat_title(chat_id, title.strip()[:40])


# --- Route ---


def _rejection_reply(reason: str) -> str:
    if reason == "encoder_unavailable":
        return "I can't process that request right now. Please try again in a moment."
    return (
        "I can't help with that. This app is for homework questions only — "
        "math, science, economics, finance, and similar subjects. "
        "Ask me a specific homework question and I'll guide you through it step by step."
    )


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, user: User = Depends(get_current_user)):
    thread_id = str(uuid.uuid4())

    sl = init_structured_logger(settings.structured_logging_pct)
    if sl:
        log.info("Structured logging ACTIVE for request: %s", thread_id)
        structured_log("chat_request", message=req.message, message_length=len(req.message), chat_id=req.chat_id, thread_id=thread_id, has_image=bool(req.image))
    else:
        log.info("Structured logging SKIPPED for request: %s", thread_id)

    lc_messages = _build_lc_messages(req)
    initial_state = {
        STATE_MESSAGES: lc_messages,
        STATE_MODEL: "unknown",
        STATE_PENDING_TOOL_CALLS: 0,
        STATE_PENDING_TOOL_CALLS_DATA: [],
        STATE_CALLED_TOOLS: [],
        STATE_REJECTED_REASON: "",
        STATE_ALIGNMENT_SCORE: 0.0,
    }
    config = RunnableConfig(configurable={"thread_id": thread_id})

    async def event_generator():
        full_reply = ""
        model_used = "unknown"
        total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        title_events: list[str] = []
        queue: asyncio.Queue = asyncio.Queue()
        pending_tool_calls = 0
        tool_calls_meta: list[dict] = []
        rejection_reason = ""
        rejection_score = 0.0
        alignment_done = asyncio.Event()

        async def _stream_graph():
            nonlocal full_reply, model_used, total_usage, pending_tool_calls, tool_calls_meta, rejection_reason, rejection_score
            try:
                async for event in compiled_graph.astream_events(
                    initial_state, config=config, version="v2"
                ):
                    node_name = event.get("metadata", {}).get("langgraph_node", "")

                    if node_name == NODE_ALIGNMENT_CHECK and event["event"] == "on_chain_end":
                        output = event["data"].get("output") or {}
                        if isinstance(output, dict):
                            rejection_reason = output.get(STATE_REJECTED_REASON, "")
                            rejection_score = output.get(STATE_ALIGNMENT_SCORE, 0.0)
                            alignment_done.set()
                            if rejection_reason:
                                return

                    if event["event"] == "on_chat_model_end":
                        output = event["data"].get("output")
                        if isinstance(output, AIMessage) and output.tool_calls:
                            for tc in output.tool_calls:
                                if tc["name"] == "route":
                                    continue
                                pending_tool_calls += 1
                                tool_calls_meta.append({"name": tc["name"], "args": tc["args"], "id": tc["id"]})
                                await queue.put(f"data: {json.dumps({'type': 'tool_call', 'name': tc['name'], 'args': tc['args'], 'id': tc['id']})}\n\n")

                    if pending_tool_calls > 0:
                        if node_name == NODE_TOOL_EXECUTOR and event["event"] == "on_chain_end":
                            pending_tool_calls = 0
                        continue

                    if node_name == NODE_TOOL_EXECUTOR:
                        continue

                    if event["event"] == "on_chat_model_stream":
                        chunk = event["data"].get("chunk")
                        if not isinstance(chunk, AIMessageChunk) or not chunk.content:
                            continue

                        content = str(chunk.content)
                        full_reply += content
                        await queue.put(f"data: {json.dumps({'type': 'token', 'content': content})}\n\n")

                    elif event["event"] == "on_chat_model_end":
                        output = event["data"].get("output")
                        if isinstance(output, AIMessage):
                            resp_meta = getattr(output, "response_metadata", None) or {}
                            raw_model = resp_meta.get("model_name", "")
                            if raw_model:
                                n = len(raw_model)
                                for r in range(n, 0, -1):
                                    if n % r == 0:
                                        part_len = n // r
                                        part = raw_model[:part_len]
                                        if part * r == raw_model:
                                            model_used = part
                                            break
                            usage = getattr(output, "usage_metadata", None)
                            if usage:
                                total_usage["input_tokens"] = usage.get("input_tokens", 0)
                                total_usage["output_tokens"] = usage.get("output_tokens", 0)
                                total_usage["total_tokens"] = usage.get("total_tokens", 0)
            except Exception as e:
                log.error("Stream execution failed: %s", e, exc_info=True)
                structured_log("stream_error", error=str(e))
            finally:
                alignment_done.set()
                await queue.put(None)

        async def _stream_title():
            if req.chat_id:
                async for event in _maybe_generate_title(req.chat_id):
                    title_events.append(event)

        graph_task = asyncio.create_task(_stream_graph())
        await alignment_done.wait()

        if rejection_reason:
            if sl is None:
                force_structured_logger()
            structured_log(
                "chat_rejected",
                message=req.message,
                message_length=len(req.message),
                score=rejection_score,
                threshold=settings.homework_alignment_threshold,
                reason=rejection_reason,
                chat_id=req.chat_id,
                thread_id=thread_id,
                has_image=bool(req.image),
            )
            log.info("Chat request rejected: thread_id=%s reason=%s score=%.3f", thread_id, rejection_reason, rejection_score)
            await graph_task
            yield f"data: {json.dumps({'type': 'token', 'content': _rejection_reply(rejection_reason)})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id, 'model': 'none', 'usage': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}})}\n\n"
            return

        log.info("Chat stream request: thread_id=%s, chat_id=%s, message_length=%d", thread_id, req.chat_id, len(req.message))
        _save_user_message(req)

        title_task = asyncio.create_task(_stream_title())
        await title_task
        for event in title_events:
            yield event

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

        await graph_task
        _save_assistant_message(
            req.chat_id, full_reply, model_used, total_usage,
            tool_calls=tool_calls_meta if tool_calls_meta else None,
        )
        tool_names = [tc["name"] for tc in tool_calls_meta] if tool_calls_meta else []
        structured_log("chat_response", model=model_used, usage=total_usage, tools_used=tool_names, reply_length=len(full_reply), reply_preview=full_reply[:500])
        yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id, 'model': model_used, 'usage': total_usage})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
