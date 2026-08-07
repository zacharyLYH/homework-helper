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
    messages = state[STATE_MESSAGES]
    if system_prompt:
        messages = [SystemMessage(content=system_prompt)] + messages
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


def route_after_agent(state: GraphState) -> Literal["tool_executor", "end"]:
    if state.get(STATE_PENDING_TOOL_CALLS, 0) > 0:
        pending_data = state.get(STATE_PENDING_TOOL_CALLS_DATA, [])
        called: set[str] = set(state.get(STATE_CALLED_TOOLS, []))
        if pending_data and all(_is_repeat(tc["name"], tc["args"], called) for tc in pending_data):
            structured_log("graph_route", destination="end", reason="all_tools_already_called", pending_calls=state[STATE_PENDING_TOOL_CALLS])
            return END_LABEL
        structured_log("graph_route", destination="tool_executor", pending_calls=state[STATE_PENDING_TOOL_CALLS])
        return NODE_TOOL_EXECUTOR
    structured_log("graph_route", destination="end", pending_calls=0)
    return END_LABEL


# --- Graph builder ---


def build_graph() -> CompiledStateGraph:
    log.info("Building LangGraph state machine")
    graph_builder = StateGraph(GraphState)

    graph_builder.add_node(NODE_ALIGNMENT_CHECK, alignment_check)
    graph_builder.add_node(NODE_AGENT, agent)
    graph_builder.add_node(NODE_TOOL_EXECUTOR, tool_executor)

    graph_builder.add_edge(START, NODE_ALIGNMENT_CHECK)
    graph_builder.add_conditional_edges(NODE_ALIGNMENT_CHECK, route_after_alignment, {
        NODE_AGENT: NODE_AGENT,
        END_LABEL: END,
    })
    graph_builder.add_conditional_edges(NODE_AGENT, route_after_agent, {
        NODE_TOOL_EXECUTOR: NODE_TOOL_EXECUTOR,
        END_LABEL: END,
    })
    graph_builder.add_edge(NODE_TOOL_EXECUTOR, NODE_AGENT)

    from langgraph.checkpoint.memory import MemorySaver
    memory = MemorySaver()
    compiled = graph_builder.compile(checkpointer=memory)
    log.info("LangGraph compiled successfully")
    return compiled


compiled_graph = build_graph()
