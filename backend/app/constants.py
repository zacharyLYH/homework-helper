"""Shared constants for graph state keys, node names, and routing labels."""

# LangGraph state keys
STATE_MESSAGES = "messages"
STATE_PENDING_TOOL_CALLS = "pending_tool_calls"
STATE_PENDING_TOOL_CALLS_DATA = "pending_tool_calls_data"
STATE_CALLED_TOOLS = "called_tools"
STATE_REJECTED_REASON = "rejected_reason"
STATE_ALIGNMENT_SCORE = "alignment_score"
STATE_CHAT_ID = "chat_id"
STATE_USER_ID = "user_id"
STATE_SUBJECT_ID = "subject_id"
STATE_MEMORY_CONTEXT = "memory_context"
STATE_MEMORY_LOADED = "memory_loaded"
STATE_MEMORY_ENABLED = "memory_enabled"

# LangGraph node names
NODE_ALIGNMENT_CHECK = "alignment_check"
NODE_AGENT = "agent"
NODE_TOOL_EXECUTOR = "tool_executor"
NODE_MEMORY_LOADER = "memory_loader"
NODE_MEMORY_UPDATER = "memory_updater"

# Routing label used to signal end-of-graph (mapped to langgraph's END sentinel)
END_LABEL = "end"

# Memory update and structured-log values
MEMORY_UPDATE_TRIGGER_CHAT_TURN = "chat_turn"
MEMORY_LOADER_SKIP_EVENT = "memory_loader_skip"
MEMORY_LOADER_ERROR_EVENT = "memory_loader_error"
MEMORY_LOADER_DONE_EVENT = "memory_loader_done"
MEMORY_UPDATER_SKIP_EVENT = "memory_updater_skip"
MEMORY_UPDATER_ERROR_EVENT = "memory_updater_error"
MEMORY_UPDATER_OUTCOME_EVENT = "memory_updater_outcome"
MEMORY_CONTEXT_INJECTED_EVENT = "memory_context_injected"
MEMORY_DISABLED_REASON = "memory_disabled"
MISSING_SCOPE_REASON = "missing_scope"
MESSAGE_ROLE_HUMAN = "human"
MESSAGE_ROLE_AI = "ai"
