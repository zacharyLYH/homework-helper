# Stage 02: Backend - Core Services Refactoring

**Sequence: 2 of 7**
**Scope: `backend/app/graph.py`, `backend/app/tools.py`, `backend/app/auth.py`, `backend/app/email.py`, `backend/app/config.py`**
**Goal: Remove god-function patterns, make components composable, extract repeated logic**

---

## Why This Stage Second

These files contain the business logic. `graph.py` (183 lines) is the most complex — it has 4 nearly-identical node functions that differ only in their system prompt. `tools.py` has a clean separation already. `auth.py` and `email.py` are small but have room for cleanup.

---

## Guidelines (STRICT)

1. **DO NOT change any function signatures that are imported by other files.** Check imports before changing anything.
2. **DO NOT change the LangGraph graph topology.** The nodes, edges, and conditional routing must produce identical behavior.
3. **DO NOT change tool definitions** (calculator, word_count, text_stats, route). These are bound to the LLM and changing their signatures/descriptions changes behavior.
4. **DO NOT modify config.py settings fields.** Adding/removing settings fields changes .env requirements.
5. **Target: remove lines and reduce duplication.**
6. **Verify: `cd backend && python -c "from app.graph import compiled_graph; from app.tools import ALL_TOOLS; from app.auth import create_access_token; from app.email import send_verification_email; from app.config import settings; print('all ok')"`**

---

## Work Items

### 2.1: Deduplicate graph node functions

In `graph.py`, these 4 functions are nearly identical (lines 91-123):

```python
def router(state): ...    # no system prompt, binds ALL_TOOLS
def math_solver(state): ...  # system: "You are a math tutor...", binds REAL_TOOLS
def code_helper(state): ...  # system: "You are a senior software engineer...", no tools
def responder(state): ...    # system: "You are a helpful assistant...", no tools
```

Each does:
1. Extract messages from state
2. Optionally prepend a SystemMessage
3. Call `_cycling_invoke` (with or without bind_tools)
4. Return `{"messages": [response], "model": model}`

**Refactor: Extract a helper function `_node_with_prompt`:**

```python
def _node_with_prompt(state: GraphState, system_prompt: str, bind_tools: list | None = None) -> dict:
    messages = state["messages"]
    if system_prompt:
        messages = [SystemMessage(content=system_prompt)] + messages
    response, model = _cycling_invoke(messages, bind_tools=bind_tools)
    return {"messages": [response], "model": model}
```

**Then rewrite nodes as thin wrappers:**

```python
def router(state: GraphState) -> dict:
    log.info("Router node invoked")
    return _node_with_prompt(state, "", bind_tools=ALL_TOOLS)

def math_solver(state: GraphState) -> dict:
    log.info("Math solver node invoked")
    return _node_with_prompt(state, "You are a math tutor. Show step-by-step reasoning. Use the calculator tool when needed.", bind_tools=REAL_TOOLS)

def code_helper(state: GraphState) -> dict:
    log.info("Code helper node invoked")
    return _node_with_prompt(state, "You are a senior software engineer. Help with code questions clearly and concisely.")

def responder(state: GraphState) -> dict:
    log.info("Responder node invoked")
    return _node_with_prompt(state, "You are a helpful assistant. Answer clearly and concisely.")
```

**Important:** The `router` function currently does NOT prepend a system prompt. `_node_with_prompt` must handle empty string correctly (don't prepend empty SystemMessage).

### 2.2: Clean up tool_executor

Current `tool_executor` (lines 60-85) has an issue: it imports `ToolNode` inside the function body (line 79-80). This import should be at the top of the file.

Move `from langgraph.prebuilt import ToolNode` to the top-level imports (it's already imported at line 7, but line 79 re-imports it — remove the re-import).

### 2.3: Extract system prompts as constants

In `graph.py`, the system prompt strings are buried inside function bodies. Extract them to module-level constants:

```python
MATH_SYSTEM_PROMPT = "You are a math tutor. Show step-by-step reasoning. Use the calculator tool when needed."
CODE_SYSTEM_PROMPT = "You are a senior software engineer. Help with code questions clearly and concisely."
GENERAL_SYSTEM_PROMPT = "You are a helpful assistant. Answer clearly and concisely."
```

This makes the prompts composable — they can be imported and overridden in tests.

### 2.4: Verify graph.py

Run:
```bash
cd /Users/zac/Desktop/homework-helper/backend
python -c "
from app.graph import compiled_graph, router, math_solver, code_helper, responder, tool_executor, route_after_router, route_after_math, build_graph
print('Graph imports OK')
print('Nodes:', [n for n in compiled_graph.nodes])
"
```

Expected nodes: `['router', 'math_solver', 'code_helper', 'responder', 'tool_executor', '__start__', '__end__']`

### 2.5: Minor cleanup in auth.py

`auth.py` (48 lines) is already clean. No changes needed unless you spot dead code. Leave as-is.

### 2.6: Minor cleanup in email.py

`email.py` (45 lines) is already clean. No changes needed. Leave as-is.

### 2.7: Minor cleanup in config.py

`config.py` (30 lines) is already clean. No changes needed. Leave as-is.

### 2.8: Verify all imports

Run:
```bash
cd /Users/zac/Desktop/homework-helper/backend
python -c "
from app.graph import compiled_graph
from app.tools import ALL_TOOLS, REAL_TOOLS
from app.auth import create_access_token, get_current_user
from app.email import send_verification_email
from app.config import settings
print('All core imports OK')
"
```

---

## Expected Outcome

- `graph.py` reduced from ~183 lines to ~150 lines (from ~40 lines of duplicated node logic)
- System prompts extracted as constants (composable for tests)
- ToolNode import cleaned up
- Zero behavior changes — graph topology identical
- All function signatures preserved
