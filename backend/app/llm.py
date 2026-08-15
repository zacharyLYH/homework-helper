from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.logging import get_logger, structured_log

log = get_logger(__name__)


def make_llm(*, base_url: str, api_key: str, model: str) -> ChatOpenAI:
    """Build a ChatOpenAI client for an OpenAI-compatible endpoint."""
    return ChatOpenAI(
        base_url=base_url,
        api_key=SecretStr(api_key) if api_key else SecretStr(""),
        model=model,
        temperature=0.7,
        max_completion_tokens=1024,
        max_retries=0,
    )


async def stream_model(
    messages: list,
    *,
    base_url: str,
    api_key: str,
    model: str,
    bind_tools: list | None = None,
    config: RunnableConfig | None = None,
) -> AsyncGenerator[BaseMessage, None]:
    """Stream model output chunks from a single OpenAI-compatible endpoint."""
    llm = make_llm(base_url=base_url, api_key=api_key, model=model)
    bound = llm.bind_tools(bind_tools) if bind_tools else llm

    msg_list = []
    for msg in messages:
        entry = {"role": getattr(msg, "type", type(msg).__name__)}
        content = msg.content
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

    log.debug("Streaming model %s", model)
    structured_log("llm_stream_start", model=model)
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
        yield chunk
    structured_log("llm_stream_end", model=model)


async def invoke_model(
    prompt: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> str:
    """Invoke a model once (non-streaming) and return its text content."""
    llm = make_llm(base_url=base_url, api_key=api_key, model=model)
    structured_log("llm_invoke", model=model)
    resp = await llm.ainvoke(prompt)
    content = str(resp.content)
    structured_log("llm_invoke_end", model=model, content_length=len(content))
    return content
