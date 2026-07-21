from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from openai import RateLimitError
from pydantic import SecretStr

from app.config import settings
from app.logging import get_logger
from app.schemas import GraphState
from app.tools import ALL_TOOLS, REAL_TOOLS

log = get_logger(__name__)

# --- LLM ---

def _make_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=SecretStr(settings.openrouter_api_key) if settings.openrouter_api_key else SecretStr(""),
        model=model,
        temperature=0.7,
        max_completion_tokens=1024,
    )

def _chat_models() -> list[str]:
    """Returns ordered list of models to try for main chat.
    Dev uses openrouter/free; prod cycles through Gemini models on quota errors."""
    if settings.environment == "dev":
        return ["openrouter/free"]
    return settings.available_models

def _cycling_invoke(messages: list, bind_tools: list | None = None) -> tuple[BaseMessage, str]:
    """Invoke LLM, cycling through chat models on quota exhaustion.
    Returns (response_message, model_used)."""
    models = _chat_models()
    last_err: Exception = RuntimeError("No models configured")
    for model in models:
        llm = _make_llm(model)
        bound = llm.bind_tools(bind_tools) if bind_tools else llm
        try:
            log.debug(f"Invoking model {model} with messages: {messages}")
            result = bound.invoke(messages)
            return result, model  # Return both the message and the model used
        except RateLimitError as e:
            log.warning(f"Model {model} quota exceeded, trying next model")
            last_err = e
    raise last_err

# Always use the free model for lightweight tasks like title generation
title_llm: ChatOpenAI = _make_llm("openrouter/free")


# --- Custom tool executor that updates category in state ---


def tool_executor(state: GraphState) -> dict:
    """Execute tool calls and update category if the route tool was called."""
    last_msg = state["messages"][-1]
    if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
        return {"messages": []}

    tool_results = []
    category = state.get("category", "")

    for tc in last_msg.tool_calls:
        if tc["name"] == "route":
            cat_value = tc["args"].get("category", "general")
            category = cat_value
            log.info("Route tool called: category=%s", cat_value)
            tool_results.append(AIMessage(
                content=f"Routed to: {cat_value}",
                tool_call_id=tc["id"],
            ))
        else:
            from langgraph.prebuilt import ToolNode
            tool_node = ToolNode(REAL_TOOLS)
            result = tool_node.invoke({"messages": [last_msg]})
            tool_results.extend(result.get("messages", []))
            break

    return {"messages": tool_results, "category": category}


# --- Nodes ---


def router(state: GraphState) -> dict:
    """Classify the user message and optionally call tools."""
    messages = state["messages"]
    log.info("Router node invoked")
    response, model = _cycling_invoke(messages, bind_tools=ALL_TOOLS)
    return {"messages": [response], "model": model}


def math_solver(state: GraphState) -> dict:
    """Specialized math tutor node."""
    messages = state["messages"]
    log.info("Math solver node invoked")
    system = SystemMessage(content="You are a math tutor. Show step-by-step reasoning. Use the calculator tool when needed.")
    response, model = _cycling_invoke([system] + messages, bind_tools=REAL_TOOLS)
    return {"messages": [response], "model": model}


def code_helper(state: GraphState) -> dict:
    """Senior software engineer response."""
    messages = state["messages"]
    log.info("Code helper node invoked")
    system = SystemMessage(content="You are a senior software engineer. Help with code questions clearly and concisely.")
    response, model = _cycling_invoke([system] + messages)
    return {"messages": [response], "model": model}


def responder(state: GraphState) -> dict:
    """General-purpose response node."""
    messages = state["messages"]
    log.info("Responder node invoked")
    system = SystemMessage(content="You are a helpful assistant. Answer clearly and concisely.")
    response, model = _cycling_invoke([system] + messages)
    return {"messages": [response], "model": model}


# --- Conditional edges ---


def route_after_router(state: GraphState) -> Literal["math_solver", "code_helper", "tool_executor", "responder"]:
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tool_executor"
    category = state.get("category", "")
    if category == "math":
        return "math_solver"
    if category == "code":
        return "code_helper"
    return "responder"


def route_after_math(state: GraphState) -> Literal["tool_executor", "router"]:
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tool_executor"
    return "router"


# --- Graph builder ---


def build_graph() -> CompiledStateGraph:
    log.info("Building LangGraph state machine")
    graph_builder = StateGraph(GraphState)

    graph_builder.add_node("router", router)
    graph_builder.add_node("math_solver", math_solver)
    graph_builder.add_node("code_helper", code_helper)
    graph_builder.add_node("responder", responder)
    graph_builder.add_node("tool_executor", tool_executor)

    graph_builder.add_edge(START, "router")
    graph_builder.add_conditional_edges("router", route_after_router, {
        "math_solver": "math_solver",
        "code_helper": "code_helper",
        "tool_executor": "tool_executor",
        "responder": "responder",
    })
    graph_builder.add_conditional_edges("math_solver", route_after_math, {
        "tool_executor": "tool_executor",
        "router": "router",
    })
    graph_builder.add_edge("tool_executor", "router")
    graph_builder.add_edge("code_helper", END)
    graph_builder.add_edge("responder", END)

    from langgraph.checkpoint.memory import MemorySaver
    memory = MemorySaver()
    compiled = graph_builder.compile(checkpointer=memory)
    log.info("LangGraph compiled successfully")
    return compiled


compiled_graph = build_graph()
