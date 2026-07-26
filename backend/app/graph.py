from collections.abc import AsyncGenerator
from typing import Literal

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from app.llm import stream_llm
from app.logging import get_logger, structured_log
from app.schemas import GraphState
from app.tools import ALL_TOOLS

log = get_logger(__name__)


AGENT_SYSTEM_PROMPT = """You are a helpful homework assistant. Answer clearly and concisely using the tools available to you."""


# --- Tool executor ---


def tool_executor(state: GraphState) -> dict:
    last_msg = state["messages"][-1]
    result = ToolNode(ALL_TOOLS).invoke({"messages": [last_msg]})
    tpc = state.get("pending_tool_calls", 0)

    tool_msgs = result.get("messages", [])
    for msg in tool_msgs:
        structured_log(
            "tool_result",
            content=str(msg.content)[:1000],
            tool_name=getattr(msg, "name", None),
            tool_call_id=getattr(msg, "tool_call_id", None),
        )
        if hasattr(msg, "artifact") and msg.artifact:
            structured_log("tool_artifact", artifact=str(msg.artifact)[:1000])

    return {"messages": result.get("messages", []), "pending_tool_calls": max(0, tpc - 1)}


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
    async for update in _node_with_prompt(state, AGENT_SYSTEM_PROMPT, bind_tools=ALL_TOOLS, config=config):
        chunk = update.get("messages", [None])[0]
        if not pending and hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
            for tcc in chunk.tool_call_chunks:
                if tcc.get("name"):
                    pending = 1
                    structured_log(
                        "agent_tool_call",
                        tool_name=tcc.get("name"),
                        tool_args=tcc.get("args"),
                        tool_call_id=tcc.get("id"),
                    )
                    break
        update["pending_tool_calls"] = pending
        yield update


# --- Conditional edges ---


def route_after_agent(state: GraphState) -> Literal["tool_executor", "end"]:
    if state.get("pending_tool_calls", 0) > 0:
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
