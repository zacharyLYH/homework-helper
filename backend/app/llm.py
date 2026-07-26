import json
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from openai import RateLimitError
from pydantic import SecretStr

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)


def _make_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=SecretStr(settings.openrouter_api_key) if settings.openrouter_api_key else SecretStr(""),
        model=model,
        temperature=0.7,
        max_completion_tokens=1024,
    )


def _chat_models() -> list[str]:
    if settings.environment == "dev":
        models = []
        if settings.openrouter_model and settings.openrouter_model != "openrouter/free":
            models.append(settings.openrouter_model)
        models.append("openrouter/free")
        log.info("Chat models (dev): %s", models)
        return models
    return settings.available_models


async def stream_llm(
    messages: list,
    bind_tools: list | None = None,
    config: RunnableConfig | None = None,
) -> AsyncGenerator[tuple[AIMessageChunk, str], None]:
    last_err: Exception = RuntimeError("No models configured")
    for model in _chat_models():
        llm = _make_llm(model)
        bound = llm.bind_tools(bind_tools) if bind_tools else llm

        # --- AUDIT: log the full request/response as JSON ---
        audit = get_logger("llm_audit")
        msg_list = []
        for msg in messages:
            entry = {"role": getattr(msg, "type", type(msg).__name__)}
            content = msg.content
            if isinstance(content, list):
                entry["content"] = str(content)[:500]
            else:
                entry["content"] = (str(content)[:500] + "...") if len(str(content)) > 500 else str(content)
            msg_list.append(entry)
        req_json = json.dumps({
            "model": model,
            "messages": msg_list,
            "tools": [t.name if hasattr(t, "name") else str(t) for t in bind_tools] if bind_tools else None,
        }, ensure_ascii=False)
        audit.info(">>> LLM REQUEST: %s", req_json)

        try:
            log.debug("Streaming model %s", model)
            async for chunk in bound.astream(messages, config=config):
                if isinstance(chunk, AIMessageChunk):
                    if chunk.tool_call_chunks:
                        for tcc in chunk.tool_call_chunks:
                            audit.info(">>> LLM TOOL CALL: %s", json.dumps(tcc, ensure_ascii=False))
                    yield chunk, model
            return
        except RateLimitError as e:
            log.warning("Model %s quota exceeded, trying next model", model)
            last_err = e
    raise last_err


title_llm: ChatOpenAI = _make_llm("openrouter/free")
