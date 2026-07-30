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

log = get_logger(__name__)


AGENT_SYSTEM_PROMPT = """You are a helpful homework assistant. Answer clearly and concisely using the tools available to you.

Format your responses using GitHub-Flavored Markdown (GFM):
- Use **bold** or *italic* for emphasis.
- Use `inline code` for short code references.
- Use fenced code blocks with a language identifier (```python, ```sql, ```bash, etc.) for any code or multi-line commands.
- Use tables, lists, blockquotes, and task lists where appropriate.
- For mathematical expressions, use LaTeX: inline with $...$ and display with $$...$$.
- Structure long answers with headings (## or ###) and clear sections."""


# --- Signature helpers ---


def _make_sig(name: str, args: dict) -> str:
    return f"{name}:{json.dumps(args, sort_keys=True)}"


def _is_repeat(name: str, args: dict, called: set[str]) -> bool:
    return _make_sig(name, args) in called


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
    if system_prompt:
        messages = [SystemMessage(content=system_prompt)] + messages
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


def route_after_agent(state: GraphState) -> Literal["tool_executor", "end"]:
    if state.get("pending_tool_calls", 0) > 0:
        pending_data = state.get("pending_tool_calls_data", [])
        called: set[str] = set(state.get("called_tools", []))
        if pending_data and all(_is_repeat(tc["name"], tc["args"], called) for tc in pending_data):
            structured_log("graph_route", destination="end", reason="all_tools_already_called", pending_calls=state["pending_tool_calls"])
            return "end"
        structured_log("graph_route", destination="tool_executor", pending_calls=state["pending_tool_calls"])
        return "tool_executor"
    structured_log("graph_route", destination="end", pending_calls=0)
    return "end"


# --- Graph builder ---


def build_graph() -> CompiledStateGraph:
    log.info("Building LangGraph state machine")
    graph_builder = StateGraph(GraphState)

    graph_builder.add_node("agent", agent)
    graph_builder.add_node("tool_executor", tool_executor)

    graph_builder.add_edge(START, "agent")
    graph_builder.add_conditional_edges("agent", route_after_agent, {
        "tool_executor": "tool_executor",
        "end": END,
    })
    graph_builder.add_edge("tool_executor", "agent")

    from langgraph.checkpoint.memory import MemorySaver
    memory = MemorySaver()
    compiled = graph_builder.compile(checkpointer=memory)
    log.info("LangGraph compiled successfully")
    return compiled


compiled_graph = build_graph()
