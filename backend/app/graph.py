import json
from collections.abc import AsyncGenerator
from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from app.alignment import check_alignment
from app.config import settings
from app.constants import (
    END_LABEL,
    NODE_AGENT,
    NODE_ALIGNMENT_CHECK,
    NODE_TOOL_EXECUTOR,
    STATE_ALIGNMENT_SCORE,
    STATE_CALLED_TOOLS,
    STATE_MESSAGES,
    STATE_PENDING_TOOL_CALLS,
    STATE_PENDING_TOOL_CALLS_DATA,
    STATE_REJECTED_REASON,
)
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
- Remember: the goal is learning, not just getting the right answer.

WHITEBOARD TOOL RULES:
- When you call `create_diagram` or `draw_elements`, the result renders on the student's canvas automatically.
- Give at most one short explanatory sentence about the diagram.
- NEVER paste diagram data, JSON, or element lists as text in your reply."""


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
        not context.is_empty,
        len(context.rendered),
    )

    structured_log(
        "memory_loader_done",
        has_context=not context.is_empty,
        user_id=user_id,
        subject_id=subject_id,
    )
    return {"memory_context": context.rendered, "memory_loaded": not context.is_empty}


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
    # Walk back to find the last non-empty human and ai messages (streaming leaves empty tail chunks)
    last_by_role: dict[str, str] = {}
    for msg in reversed(messages):
        role = getattr(msg, "type", "unknown")
        if role not in last_by_role:
            content = _stringify_content(getattr(msg, "content", ""))
            if content.strip():
                last_by_role[role] = content
        if "human" in last_by_role and "ai" in last_by_role:
            break

    snippet: list[dict[str, str]] = [
        {"role": role, "content": last_by_role[role][:400]}
        for role in ("human", "ai")
        if role in last_by_role
    ]

    payload = {
        "trigger": "chat_turn",
        "memory_loaded": state.get("memory_loaded", False),
        "memory_context": state.get("memory_context", "")[:2000],
        "messages": snippet,
    }

    try:
        decision = enqueue_memory_update(
            user_id=user_id,
            subject_id=subject_id,
            chat_id=None,
            payload=payload,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        log.warning("Memory updater failed, skipping update: %s", exc)
        structured_log("memory_updater_error", error=str(exc))
        return {}

    log.info("Memory updater outcome: enqueued=%s reason=%s job_id=%s", decision.enqueued, decision.reason, decision.job_id)

    structured_log(
        "memory_updater_done",
        enqueued=decision.enqueued,
        reason=decision.reason,
        job_id=decision.job_id,
        user_id=user_id,
        subject_id=subject_id,
    )
    return {}


# --- Tool executor ---


def tool_executor(state: GraphState) -> dict:
    pending_data = state.get(STATE_PENDING_TOOL_CALLS_DATA, [])
    if not pending_data:
        structured_log("tool_executor_skip", reason="no_pending_data")
        return {STATE_PENDING_TOOL_CALLS: 0, STATE_PENDING_TOOL_CALLS_DATA: []}

    called: set[str] = set(state.get(STATE_CALLED_TOOLS, []))

    fresh_calls = []
    for tc in pending_data:
        if not _is_repeat(tc["name"], tc["args"], called):
            fresh_calls.append(tc)

    if not fresh_calls:
        structured_log("tool_executor_skip", reason="all_tools_already_called", signatures=list(called))
        return {STATE_PENDING_TOOL_CALLS: 0, STATE_PENDING_TOOL_CALLS_DATA: []}

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
        STATE_PENDING_TOOL_CALLS: max(0, state.get(STATE_PENDING_TOOL_CALLS, 0) - 1),
        STATE_PENDING_TOOL_CALLS_DATA: [],
        STATE_CALLED_TOOLS: list(called | set(new_signatures)),
    }


# --- Alignment gate ---


def _latest_user_text(state: GraphState) -> str:
    messages = state.get(STATE_MESSAGES, [])
    if not messages:
        return ""
    content = messages[-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


def alignment_check(state: GraphState) -> dict:
    """First node: reject out-of-scope requests before the agent ever runs."""
    allowed, score, reason = check_alignment(_latest_user_text(state))
    structured_log(
        "alignment_check",
        allowed=allowed,
        score=score,
        threshold=settings.homework_alignment_threshold,
        reason=reason,
    )
    return {
        STATE_REJECTED_REASON: "" if allowed else reason,
        STATE_ALIGNMENT_SCORE: score,
    }


def route_after_alignment(state: GraphState) -> Literal["agent", "end"]:
    if state.get(STATE_REJECTED_REASON, ""):
        structured_log("graph_route", destination="end", reason="alignment_rejected")
        return END_LABEL
    structured_log("graph_route", destination="agent", reason="alignment_ok")
    return NODE_AGENT


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

    messages = state[STATE_MESSAGES]
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
        yield {STATE_MESSAGES: [chunk]}


async def agent(state: GraphState, config: RunnableConfig | None = None) -> AsyncGenerator[dict, None]:
    log.info("Agent node invoked")
    structured_log(
        "agent_start",
        message_count=len(state[STATE_MESSAGES]),
        last_role=getattr(state[STATE_MESSAGES][-1], "type", None) if state[STATE_MESSAGES] else None,
        pending_tool_calls=state.get(STATE_PENDING_TOOL_CALLS, 0),
    )

    pending = 0
    tc_data: dict[int, dict] = {}

    async for update in _node_with_prompt(state, AGENT_SYSTEM_PROMPT, bind_tools=ALL_TOOLS, config=config):
        chunk = update.get(STATE_MESSAGES, [None])[0]

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

        update[STATE_PENDING_TOOL_CALLS] = pending
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
        yield {STATE_PENDING_TOOL_CALLS: pending, STATE_PENDING_TOOL_CALLS_DATA: calls}


# --- Conditional edges ---


def route_after_agent(state: GraphState) -> Literal["tool_executor", "memory_updater", "end"]:
    if state.get(STATE_PENDING_TOOL_CALLS, 0) > 0:
        pending_data = state.get(STATE_PENDING_TOOL_CALLS_DATA, [])
        called: set[str] = set(state.get(STATE_CALLED_TOOLS, []))
        if pending_data and all(_is_repeat(tc["name"], tc["args"], called) for tc in pending_data):
            structured_log("graph_route", destination="memory_updater", reason="all_tools_already_called", pending_calls=state["pending_tool_calls"])
            return "memory_updater"
        structured_log("graph_route", destination="tool_executor", pending_calls=state[STATE_PENDING_TOOL_CALLS])
        return NODE_TOOL_EXECUTOR
    structured_log("graph_route", destination="end", pending_calls=0)
    return "memory_updater"


# --- Graph builder ---


def build_graph() -> CompiledStateGraph:
    log.info("Building LangGraph state machine")
    graph_builder = StateGraph(GraphState)

    graph_builder.add_node("memory_loader", memory_loader)
    graph_builder.add_node(NODE_ALIGNMENT_CHECK, alignment_check)
    graph_builder.add_node(NODE_AGENT, agent)
    graph_builder.add_node(NODE_TOOL_EXECUTOR, tool_executor)
    graph_builder.add_node("memory_updater", memory_updater)

    graph_builder.add_edge(START, "memory_loader")
    graph_builder.add_edge("memory_loader", NODE_ALIGNMENT_CHECK)
    graph_builder.add_conditional_edges(NODE_ALIGNMENT_CHECK, route_after_alignment, {
        NODE_AGENT: NODE_AGENT,
        END_LABEL: END,
    })
    graph_builder.add_conditional_edges("agent", route_after_agent, {
        "tool_executor": "tool_executor",
        "memory_updater": "memory_updater",
        END_LABEL: END,
    })
    graph_builder.add_edge(NODE_TOOL_EXECUTOR, NODE_AGENT)
    graph_builder.add_edge("memory_updater", END)

    from langgraph.checkpoint.memory import MemorySaver
    memory = MemorySaver()
    compiled = graph_builder.compile(checkpointer=memory)
    log.info("LangGraph compiled successfully")
    return compiled


compiled_graph = build_graph()
