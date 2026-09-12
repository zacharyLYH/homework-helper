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

# Memory worker structured-log events
MEMORY_WORKER_LLM_START_EVENT = "memory_worker_llm_start"
MEMORY_WORKER_LLM_DONE_EVENT = "memory_worker_llm_done"
MEMORY_WORKER_LLM_ERROR_EVENT = "memory_worker_llm_error"
MEMORY_WORKER_VALIDATION_TRUNCATED_EVENT = "memory_worker_validation_truncated"
MEMORY_WORKER_APPLY_START_EVENT = "memory_worker_apply_start"
MEMORY_WORKER_APPLY_DONE_EVENT = "memory_worker_apply_done"
MEMORY_WORKER_KEY_NORMALIZED_EVENT = "memory_worker_key_normalized"

# Memory service structured-log events
MEMORY_CONTEXT_ERROR_EVENT = "memory_context_error"
MEMORY_CONTEXT_LOADED_EVENT = "memory_context_loaded"
MEMORY_TRACE_INSERT_ERROR_EVENT = "memory_trace_insert_error"
MEMORY_ENQUEUE_DECISION_EVENT = "memory_enqueue_decision"

# Memory runtime status reasons
MEMORY_STATUS_DB_MISSING = "memory_db_missing"
MEMORY_STATUS_DB_UNREADABLE = "memory_db_unreadable"
MEMORY_STATUS_SCHEMA_MISSING = "memory_schema_missing"
MEMORY_STATUS_ENABLED = "memory_enabled"
MEMORY_DISABLED_REASON = "memory_disabled"
MISSING_SCOPE_REASON = "missing_scope"
MESSAGE_ROLE_HUMAN = "human"
MESSAGE_ROLE_AI = "ai"

# Memory update payload JSON keys (app <-> worker contract).
# ``memory_loaded``/``memory_context``/``messages`` reuse the STATE_* constants
# since they share the same string values.
MEMORY_PAYLOAD_TRIGGER = "trigger"

# Message dict keys inside memory payloads
MESSAGE_ROLE = "role"
MESSAGE_CONTENT = "content"
