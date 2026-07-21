# Stage 04: Backend - Schema Cleanup & Dead Code Removal

**Sequence: 4 of 7**
**Scope: `backend/app/schemas.py`, `backend/app/main.py`, `backend/app/logging.py`, `backend/app/routes/` (imports), dead `backend/app/services/` directory**
**Goal: Remove unused code, clean imports, remove dead directories**

---

## Why This Stage Fourth

After the structural refactoring in stages 1-3, we do a cleanup pass. This catches unused imports, dead code, and the empty `services/` directory. This is the "remove lines" stage — pure subtractive work.

---

## Guidelines (STRICT)

1. **DO NOT remove anything that is imported by another file.** Always grep before removing.
2. **DO NOT remove `RouteCategory` enum.** It's used by the `route` tool in `tools.py`.
3. **DO NOT remove `GraphState`.** It's the LangGraph state definition.
4. **Verify after each removal.**

---

## Work Items

### 4.1: Remove dead `services/` directory

The `backend/app/services/` directory contains only `__pycache__/` with stale `.pyc` files. The source files that created them no longer exist.

```bash
rm -rf /Users/zac/Desktop/homework-helper/backend/app/services
```

### 4.2: Clean up unused imports in schemas.py

Current `schemas.py` imports:
- `enum` → used by `RouteCategory`
- `datetime` → used by model fields
- `Any`, `Optional` → used by `ChatRequest`
- `BaseMessage` → used by `GraphState`
- `add_messages` → used by `GraphState`
- `BaseModel`, `ConfigDict` → used by all models
- `Annotated`, `TypedDict` → used by `GraphState`

All imports are used. No changes needed to schemas.py imports.

### 4.3: Verify schemas.py is clean

Check that `RouteCategory` is actually used:
```bash
cd /Users/zac/Desktop/homework-helper/backend
grep -r "RouteCategory" app/
```

Expected: used in `app/tools.py` (line 67: `def route(category: RouteCategory)`). Keep it.

### 4.4: Clean up imports across route files

Check each route file for unused imports:

**`routes/auth.py`**: Check if all imports are used:
- `APIRouter, Depends, HTTPException, Response` → all used
- `create_access_token, get_current_user` → both used
- `create_verification_code, get_user_by_email, verify_code` → all used
- `send_verification_email` → used
- All schema imports → all used

**`routes/chat.py`**: Check:
- `json, uuid` → both used
- `Any, AsyncGenerator` → both used
- `APIRouter, Depends, HTTPException` → all used (HTTPException not currently used — check if it's needed)
- `StreamingResponse` → used
- `AIMessage, HumanMessage` → both used
- `RunnableConfig` → used
- `get_current_user` → used
- DB functions → all used
- `compiled_graph, title_llm` → both used
- `ChatRequest, User` → both used

**If `HTTPException` is unused in chat.py, remove it.**

**`routes/subjects_chats.py`**: Check:
- `Query` → used in `get_chats`
- `Chat, Message` → check if `Message` is used (it's imported but may not be used in endpoint return types)

**If `Message` is unused in subjects_chats.py, remove it.**

**`routes/debug.py`**: Check all imports — likely clean.

### 4.5: Verify no broken imports

Run:
```bash
cd /Users/zac/Desktop/homework-helper/backend
python -c "
from app.routes import api_router
from app.schemas import GraphState, RouteCategory, ChatRequest, Chat, Message, User, Subject
from app.graph import compiled_graph
from app.tools import ALL_TOOLS
print('All imports OK after cleanup')
"
```

### 4.6: Verify services directory is gone

```bash
ls /Users/zac/Desktop/homework-helper/backend/app/services 2>&1
# Should print: No such file or directory
```

---

## Expected Outcome

- Dead `services/` directory removed
- Unused imports cleaned from route files
- ~5-10 lines removed from import sections
- Zero functionality changes
