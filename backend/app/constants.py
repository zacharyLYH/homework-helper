"""Shared constants for graph state keys, node names, and routing labels."""

# LangGraph state keys
STATE_MESSAGES = "messages"
STATE_MODEL = "model"
STATE_PENDING_TOOL_CALLS = "pending_tool_calls"
STATE_PENDING_TOOL_CALLS_DATA = "pending_tool_calls_data"
STATE_CALLED_TOOLS = "called_tools"
STATE_REJECTED_REASON = "rejected_reason"
STATE_ALIGNMENT_SCORE = "alignment_score"

# LangGraph node names
NODE_ALIGNMENT_CHECK = "alignment_check"
NODE_AGENT = "agent"
NODE_TOOL_EXECUTOR = "tool_executor"

# Routing label used to signal end-of-graph (mapped to langgraph's END sentinel)
END_LABEL = "end"
