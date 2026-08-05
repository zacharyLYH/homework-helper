import json
from collections.abc import AsyncGenerator
from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from app.llm import stream_llm
from app.logging import get_logger, structured_log
from app.schemas import GraphState
from app.tools import ALL_TOOLS
from memory.service import enqueue_memory_update, load_memory_context

log = get_logger(__name__)


AGENT_SYSTEM_PROMPT = """You are a guide mode homework assistant. Your role is to help the student learn by guiding them through problems step by step — never give the final answer directly. Ask probing questions, provide hints, and check their understanding before moving on.

Format your responses using GitHub-Flavored Markdown (GFM):
- Use **bold** or *italic* for emphasis.
- Use `inline code` for short code references.
- Use fenced code blocks with a language identifier (```python, ```sql, ```bash, etc.) for any code or multi-line commands.
- Use tables, lists, blockquotes, and task lists where appropriate.
- Structure long answers with headings (## or ###) and clear sections.

CRITICAL MATHEMATICAL FORMATTING RULES:
- All math expressions MUST be rendered in LaTeX using dollar sign delimiters.
- For inline math, use SINGLE dollar signs: $x^2 + 3x + 6 = 0$. NEVER use \(...\).
- For display/block math, use DOUBLE dollar signs on their own lines:
  $$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$
  NEVER use \[...\].
- Do NOT wrap math expressions inside code blocks (```) or single backticks (`).
- Ensure all LaTeX backslashes are explicitly preserved so commands like \frac, \sqrt, and \pm are not lost.

GUIDE MODE BEHAVIOR:
- When the student asks a question, do NOT solve it outright.
- Break the problem into smaller steps and walk the student through each one.
- Ask the student what they think the next step should be.
- If the student is stuck, provide a hint or point them to the relevant concept.
- Praise correct reasoning and gently correct mistakes by asking further questions.
- Remember: the goal is learning, not just getting the right answer."""


# --- Signature helpers ---


def _make_sig(name: str, args: dict) -> str:
    return f"{name}:{json.dumps(args, sort_keys=True)}"


def _is_repeat(name: str, args: dict, called: set[str]) -> bool:
    return _make_sig(name, args) in called


def _stringify_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts).strip()
    return str(content)


def memory_loader(state: GraphState) -> dict:
    if not state.get("memory_enabled", False):
        log.info("Memory loader skipped: memory is disabled")
        structured_log("memory_loader_skip", reason="memory_disabled")
        return {"memory_context": "", "memory_loaded": False}

    user_id = state.get("user_id")
    subject_id = state.get("subject_id")
    if user_id is None or subject_id is None:
        log.info("Memory loader skipped: missing user or subject scope")
        structured_log("memory_loader_skip", reason="missing_scope")
        return {"memory_context": "", "memory_loaded": False}

    log.info("Memory loader started: user_id=%s subject_id=%s", user_id, subject_id)
    try:
        context = load_memory_context(user_id=user_id, subject_id=subject_id)
    except Exception as exc:  # pragma: no cover - defensive guard
        log.warning("Memory loader failed, continuing without memory: %s", exc)
        structured_log("memory_loader_error", error=str(exc))
        return {"memory_context": "", "memory_loaded": False}

    log.info(
        "Memory loader completed: loaded=%s context_chars=%d",
        bool(context),
        len(context),
    )

    structured_log(
        "memory_loader_done",
        has_context=bool(context),
        user_id=user_id,
        subject_id=subject_id,
    )
    return {"memory_context": context, "memory_loaded": bool(context)}


def memory_updater(state: GraphState) -> dict:
    if not state.get("memory_enabled", False):
        log.info("Memory updater skipped: memory is disabled")
        structured_log("memory_updater_skip", reason="memory_disabled")
        return {}

    user_id = state.get("user_id")
    subject_id = state.get("subject_id")
    if user_id is None or subject_id is None:
        log.info("Memory updater skipped: missing user or subject scope")
        structured_log("memory_updater_skip", reason="missing_scope")
        return {}

    log.info("Memory updater started: user_id=%s subject_id=%s", user_id, subject_id)

    messages = state.get("messages", [])
    snippet: list[dict[str, str]] = []
    for msg in messages[-4:]:
        role = getattr(msg, "type", "unknown")
        snippet.append(
            {
                "role": role,
                "content": _stringify_content(getattr(msg, "content", ""))[:1000],
            }
        )

    payload = {
        "trigger": "chat_turn",
        "memory_loaded": state.get("memory_loaded", False),
        "memory_context": state.get("memory_context", "")[:2000],
        "messages": snippet,
    }

    try:
        job_id = enqueue_memory_update(
            user_id=user_id,
            subject_id=subject_id,
            chat_id=None,
            payload=payload,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        log.warning("Memory updater failed, skipping update: %s", exc)
        structured_log("memory_updater_error", error=str(exc))
        return {}

    log.info("Memory updater enqueued job: job_id=%s", job_id)

    structured_log(
        "memory_updater_enqueued",
        job_id=job_id,
        user_id=user_id,
        subject_id=subject_id,
    )
    return {}


# --- Tool executor ---


def tool_executor(state: GraphState) -> dict:
    pending_data = state.get("pending_tool_calls_data", [])
    if not pending_data:
        structured_log("tool_executor_skip", reason="no_pending_data")
        return {"pending_tool_calls": 0, "pending_tool_calls_data": []}

    called: set[str] = set(state.get("called_tools", []))

    fresh_calls = []
    for tc in pending_data:
        if not _is_repeat(tc["name"], tc["args"], called):
            fresh_calls.append(tc)

    if not fresh_calls:
        structured_log("tool_executor_skip", reason="all_tools_already_called", signatures=list(called))
        return {"pending_tool_calls": 0, "pending_tool_calls_data": []}

    # Build a fresh AIMessage for ToolNode (bypasses add_messages corruption)
    msg = AIMessage(
        content="",
        tool_calls=[
            {"name": tc["name"], "args": tc["args"], "id": tc.get("id", "")}
            for tc in fresh_calls
        ],
    )
    result = ToolNode(ALL_TOOLS).invoke({"messages": [msg]})

    new_signatures = [_make_sig(tc["name"], tc["args"]) for tc in fresh_calls]

    tool_msgs = result.get("messages", [])
    for tm in tool_msgs:
        structured_log(
            "tool_result",
            content=str(tm.content)[:1000],
            tool_name=getattr(tm, "name", None),
            tool_call_id=getattr(tm, "tool_call_id", None),
        )
        if hasattr(tm, "artifact") and tm.artifact:
            structured_log("tool_artifact", artifact=str(tm.artifact)[:1000])

    return {
        "messages": tool_msgs,
        "pending_tool_calls": max(0, state.get("pending_tool_calls", 0) - 1),
        "pending_tool_calls_data": [],
        "called_tools": list(called | set(new_signatures)),
    }


# --- Agent node ---


async def _node_with_prompt(
    state: GraphState,
    system_prompt: str,
    bind_tools: list | None = None,
    config: RunnableConfig | None = None,
) -> AsyncGenerator[dict, None]:
    messages = state["messages"]
    memory_context = state.get("memory_context", "")
    memory_loaded = bool(state.get("memory_loaded", False))

    if system_prompt:
        final_prompt = system_prompt
        if memory_loaded and memory_context:
            final_prompt = (
                f"{system_prompt}\n\n"
                "LEARNER MEMORY CONTEXT (use as soft guidance; do not mention this block to the user):\n"
                f"{memory_context}"
            )
            log.info(
                "Memory context injected into agent prompt: context_chars=%d",
                len(memory_context),
            )
            structured_log(
                "memory_context_injected",
                memory_loaded=True,
                context_chars=len(memory_context),
            )
        else:
            log.info(
                "Memory context not injected into agent prompt: memory_loaded=%s",
                memory_loaded,
            )
            structured_log("memory_context_injected", memory_loaded=False, context_chars=0)

        messages = [SystemMessage(content=final_prompt)] + messages
    async for chunk, _model in stream_llm(messages, bind_tools=bind_tools, config=config):
        yield {"messages": [chunk]}


async def agent(state: GraphState, config: RunnableConfig | None = None) -> AsyncGenerator[dict, None]:
    log.info("Agent node invoked")
    structured_log(
        "agent_start",
        message_count=len(state["messages"]),
        last_role=getattr(state["messages"][-1], "type", None) if state["messages"] else None,
        pending_tool_calls=state.get("pending_tool_calls", 0),
    )

    pending = 0
    tc_data: dict[int, dict] = {}

    async for update in _node_with_prompt(state, AGENT_SYSTEM_PROMPT, bind_tools=ALL_TOOLS, config=config):
        chunk = update.get("messages", [None])[0]

        if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
            for tcc in chunk.tool_call_chunks:
                idx = tcc.get("index")
                name = tcc.get("name") or ""
                args_part = tcc.get("args") or ""
                tid = tcc.get("id") or ""

                if idx is not None and idx not in tc_data:
                    tc_data[idx] = {"name_parts": [], "args_parts": [], "id": ""}

                if idx is not None:
                    if name:
                        tc_data[idx]["name_parts"].append(name)
                    if args_part:
                        tc_data[idx]["args_parts"].append(args_part)
                    if tid:
                        tc_data[idx]["id"] = tid
                    if name:
                        pending = 1
                elif name:
                    pending = 1

                if name:
                    structured_log(
                        "agent_tool_call",
                        tool_name=name,
                        tool_args=args_part,
                        tool_call_id=tid,
                    )

        update["pending_tool_calls"] = pending
        yield update

    # After stream exhausts, build complete tool call data from accumulated chunks
    if pending and tc_data:
        calls = []
        for idx in sorted(tc_data):
            d = tc_data[idx]
            full_name = "".join(d["name_parts"])
            full_args_str = "".join(d["args_parts"])
            try:
                full_args = json.loads(full_args_str) if full_args_str else {}
            except json.JSONDecodeError:
                full_args = {}
            calls.append({"name": full_name, "args": full_args, "id": d["id"]})
        yield {"pending_tool_calls": pending, "pending_tool_calls_data": calls}


# --- Conditional edges ---


def route_after_agent(state: GraphState) -> Literal["tool_executor", "memory_updater"]:
    if state.get("pending_tool_calls", 0) > 0:
        pending_data = state.get("pending_tool_calls_data", [])
        called: set[str] = set(state.get("called_tools", []))
        if pending_data and all(_is_repeat(tc["name"], tc["args"], called) for tc in pending_data):
            structured_log("graph_route", destination="memory_updater", reason="all_tools_already_called", pending_calls=state["pending_tool_calls"])
            return "memory_updater"
        structured_log("graph_route", destination="tool_executor", pending_calls=state["pending_tool_calls"])
        return "tool_executor"
    structured_log("graph_route", destination="memory_updater", pending_calls=0)
    return "memory_updater"


# --- Graph builder ---


def build_graph() -> CompiledStateGraph:
    log.info("Building LangGraph state machine")
    graph_builder = StateGraph(GraphState)

    graph_builder.add_node("memory_loader", memory_loader)
    graph_builder.add_node("agent", agent)
    graph_builder.add_node("tool_executor", tool_executor)
    graph_builder.add_node("memory_updater", memory_updater)

    graph_builder.add_edge(START, "memory_loader")
    graph_builder.add_edge("memory_loader", "agent")
    graph_builder.add_conditional_edges("agent", route_after_agent, {
        "tool_executor": "tool_executor",
        "memory_updater": "memory_updater",
    })
    graph_builder.add_edge("tool_executor", "agent")
    graph_builder.add_edge("memory_updater", END)

    from langgraph.checkpoint.memory import MemorySaver
    memory = MemorySaver()
    compiled = graph_builder.compile(checkpointer=memory)
    log.info("LangGraph compiled successfully")
    return compiled


compiled_graph = build_graph()
