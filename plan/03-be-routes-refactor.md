# Stage 03: Backend - Routes Refactoring

**Sequence: 3 of 7**
**Scope: `backend/app/routes/auth.py`, `backend/app/routes/chat.py`, `backend/app/routes/subjects_chats.py`, `backend/app/routes/debug.py`, `backend/app/routes/health.py`, `backend/app/routes/tools.py`**
**Goal: Extract shared patterns, reduce chat.py complexity, remove duplication**

---

## Why This Stage Third

Routes are the API surface. They have the most visible duplication: ownership verification (check subject belongs to user, check chat belongs to user) is copy-pasted across 4 endpoints in `subjects_chats.py`. `chat.py` is a god-function with streaming, title generation, token tracking, and message saving all in one endpoint.

---

## Guidelines (STRICT)

1. **DO NOT change API paths, HTTP methods, or response shapes.** Frontend depends on these.
2. **DO NOT change authentication behavior.** `get_current_user` dependency must stay.
3. **DO NOT remove debug endpoints.** They're gated by ENVIRONMENT check, not dead code.
4. **Verify: `cd backend && python -c "from app.routes import api_router; print(len(api_router.routes), 'routes registered')"`**

---

## Work Items

### 3.1: Extract ownership verification helper

In `subjects_chats.py`, these 4 endpoints repeat the same pattern:

```python
# Pattern: get chat -> get subject -> check subject belongs to user
chat = get_chat(chat_id)
if not chat:
    raise HTTPException(status_code=404, detail="Chat not found")
subject = next((s for s in list_subjects(user.id) if s.id == chat.subject_id), None)
if not subject:
    raise HTTPException(status_code=404, detail="Subject not found")
```

**Extract into a helper at the top of `subjects_chats.py`:**

```python
def _get_owned_chat(chat_id: int, user_id: int) -> Chat:
    """Get a chat and verify it belongs to the user. Raises 404 if not found."""
    chat = get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    subject = next((s for s in list_subjects(user_id) if s.id == chat.subject_id), None)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return chat

def _get_owned_subject(subject_id: int, user_id: int) -> Subject:
    """Get a subject and verify it belongs to the user. Raises 404 if not found."""
    subject = next((s for s in list_subjects(user_id) if s.id == subject_id), None)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject
```

**Then replace the duplicated code in:**
- `get_chat_route` → use `_get_owned_chat`
- `get_chat_messages` → use `_get_owned_chat`
- `delete_chat_route` → use `_get_owned_chat`
- `get_chats` → use `_get_owned_subject`
- `create_chat_route` → use `_get_owned_subject`
- `delete_subject_route` → use `_get_owned_subject`

### 3.2: Simplify subjects_chats.py endpoints

After 3.1, endpoints become very short. For example:

```python
@router.get("/api/chats/{chat_id}")
async def get_chat_route(chat_id: int, user: User = Depends(get_current_user)):
    return _get_owned_chat(chat_id, user.id)
```

```python
@router.delete("/api/chats/{chat_id}")
async def delete_chat_route(chat_id: int, user: User = Depends(get_current_user)):
    _get_owned_chat(chat_id, user.id)
    delete_chat(chat_id)
    return {"message": "Deleted"}
```

### 3.3: Extract streaming concerns in chat.py

`chat.py` is the most complex route file. The `chat_stream` endpoint (lines 58-135) does 5 things in one function:
1. Saves the user message
2. Builds LangChain messages
3. Streams the graph response
4. Saves the assistant message
5. Generates a title (if new chat)
6. Updates token usage

**Refactor approach: Extract the post-streaming logic into helpers:**

```python
def _save_user_message(chat_id: int, req: ChatRequest) -> None:
    """Persist the incoming user message."""
    save_message(
        chat_id=chat_id or 0,
        role="user",
        content=req.message,
        image_base64=req.image,
        image_media_type=req.image_media_type,
    )

def _save_assistant_message(chat_id: int, full_reply: str, model_used: str, total_usage: dict) -> None:
    """Persist the assistant response and update token usage."""
    metadata = {"model": model_used, "usage": total_usage}
    save_message(
        chat_id=chat_id or 0,
        role="assistant",
        content=full_reply or "No response generated.",
        metadata_json=json.dumps(metadata),
        token_count=total_usage["total_tokens"],
    )
    if chat_id and total_usage["total_tokens"] > 0:
        update_chat_token_usage(
            chat_id,
            input_tokens=total_usage["input_tokens"],
            output_tokens=total_usage["output_tokens"],
            total_tokens=total_usage["total_tokens"],
        )

async def _maybe_generate_title(chat_id: int) -> AsyncGenerator[str, None]:
    """Generate and emit a title for new chats. Yields SSE title events."""
    if not chat_id:
        return
    existing = get_chat(chat_id)
    if not existing or existing.title != "New Chat":
        return
    title = ""
    async for title_chunk in generate_title_stream(chat_id):
        title += title_chunk
        yield f"data: {json.dumps({'type': 'title', 'content': title_chunk})}\n\n"
    if title.strip():
        update_chat_title(chat_id, title.strip()[:40])
```

**Then the event_generator becomes:**

```python
async def event_generator():
    full_reply = ""
    model_used = "unknown"
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    try:
        async for msg, metadata in compiled_graph.astream(
            initial_state, config=config, stream_mode="messages"
        ):
            if isinstance(msg, AIMessage) and msg.content:
                node = metadata["langgraph_node"] if isinstance(metadata, dict) else ""
                if node in ("router", "tool_executor"):
                    continue
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                full_reply += content
                yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
            if isinstance(msg, AIMessage):
                resp_meta = getattr(msg, "response_metadata", None) or {}
                if resp_meta.get("model_name"):
                    model_used = resp_meta["model_name"]
                usage = getattr(msg, "usage_metadata", None)
                if usage:
                    total_usage["input_tokens"] += usage.get("input_tokens", 0)
                    total_usage["output_tokens"] += usage.get("output_tokens", 0)
                    total_usage["total_tokens"] += usage.get("total_tokens", 0)

        _save_assistant_message(req.chat_id, full_reply, model_used, total_usage)
        async for event in _maybe_generate_title(req.chat_id):
            yield event
        yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id, 'model': model_used, 'usage': total_usage})}\n\n"
    except Exception as e:
        log.error("Stream execution failed: %s", e, exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
```

**Also move `_save_user_message` call before event_generator definition for clarity.**

### 3.4: Verify

Run:
```bash
cd /Users/zac/Desktop/homework-helper/backend
python -c "
from app.routes import api_router
print(f'{len(api_router.routes)} routes registered')
# Check all expected route paths exist
paths = [r.path for r in api_router.routes]
expected = [
    '/api/auth/request-code', '/api/auth/verify', '/api/auth/logout', '/api/auth/me',
    '/', '/health',
    '/api/chat/stream',
    '/api/tools',
    '/api/debug/users', '/api/debug/sql',
    '/api/subjects', '/api/chats',
]
for p in expected:
    assert any(p in path for path in paths), f'Missing route: {p}'
print('All expected routes present')
"
```

---

## Expected Outcome

- `subjects_chats.py` reduced from ~92 lines to ~60 lines
- `chat.py` logic decomposed into 3 focused helper functions
- Zero API contract changes
- All ownership checks centralized in 2 helper functions
