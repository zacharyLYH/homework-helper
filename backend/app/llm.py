from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from openai import RateLimitError
from pydantic import SecretStr

from app.config import settings
from app.logging import get_logger, structured_log

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
    for attempt, model in enumerate(_chat_models(), 1):
        llm = _make_llm(model)
        bound = llm.bind_tools(bind_tools) if bind_tools else llm

        msg_list = []
        for msg in messages:
            entry = {"role": getattr(msg, "type", type(msg).__name__)}
            content = msg.content
            if isinstance(content, list):
                entry["content"] = str(content)[:1000]
            else:
                entry["content"] = str(content)[:1000]
            msg_list.append(entry)

        structured_log(
            "llm_request",
            model=model,
            messages=msg_list,
            tools=[t.name for t in bind_tools] if bind_tools else None,
            tool_count=len(bind_tools) if bind_tools else 0,
            message_count=len(msg_list),
        )

        try:
            log.debug("Streaming model %s", model)
            structured_log("llm_stream_start", model=model, attempt=attempt)
            async for chunk in bound.astream(messages, config=config):
                if isinstance(chunk, AIMessageChunk):
                    if chunk.tool_call_chunks:
                        for tcc in chunk.tool_call_chunks:
                            structured_log(
                                "llm_tool_call",
                                tool_name=tcc.get("name"),
                                tool_args=tcc.get("args"),
                                tool_call_id=tcc.get("id"),
                                model=model,
                            )
                    yield chunk, model
            structured_log("llm_stream_end", model=model, attempt=attempt)
            return
        except RateLimitError as e:
            log.warning("Model %s quota exceeded, trying next model", model)
            structured_log(
                "llm_quota_error",
                model=model,
                error=str(e)[:500],
                remaining_models=[m for m in _chat_models() if m != model],
            )
            last_err = e
    structured_log(
        "llm_all_models_exhausted",
        models_attempted=_chat_models(),
        error=str(last_err)[:500],
    )
    raise last_err


title_llm: ChatOpenAI = _make_llm("openrouter/free")
