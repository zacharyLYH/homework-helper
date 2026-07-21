# Stage 01: Backend - Database Layer Refactoring

**Sequence: 1 of 7**
**Scope: `backend/app/db.py` only**
**Goal: Make the DB layer composable, reduce line count, eliminate repetition**

---

## Why This Stage First

`db.py` (240 lines) is the foundation. Every route and service depends on it. Every function in this file has the same boilerplate: open connection, execute SQL, convert `sqlite3.Row` to a Pydantic model, close connection. Fixing this first creates clean building blocks for all subsequent stages.

---

## Guidelines (STRICT)

1. **DO NOT change any function signatures.** Every existing function must keep its exact name, parameters, and return type. Other code depends on these.
2. **DO NOT change SQL queries.** The queries work. We are only restructuring the Python code around them.
3. **DO NOT add new dependencies.** Use only what's already imported.
4. **Target: remove lines.** If you're adding more lines than you remove, you're doing it wrong.
5. **Verify: run `cd backend && python -c "from app.db import *; print('imports ok')"` after changes.**

---

## Work Items

### 1.1: Extract Row-to-Model helpers

There are 5 Pydantic models constructed from rows: `User`, `Subject`, `Chat`, `Message`. Each is constructed inline with identical patterns.

**Create these private helpers at the top of the file (after `_parse_dt`):**

```python
def _row_to_user(row) -> User:
    return User(id=row["id"], email=row["email"], created_at=_parse_dt(row["created_at"]))

def _row_to_subject(row) -> Subject:
    return Subject(id=row["id"], user_id=row["user_id"], name=row["name"], created_at=_parse_dt(row["created_at"]))

def _row_to_chat(row) -> Chat:
    return Chat(
        id=row["id"], subject_id=row["subject_id"], user_id=row["user_id"],
        mode=row["mode"], title=row["title"],
        total_tokens=row["total_tokens"], input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        created_at=_parse_dt(row["created_at"]), updated_at=_parse_dt(row["updated_at"]),
    )

def _row_to_message(row) -> Message:
    return Message(
        id=row["id"], chat_id=row["chat_id"], role=row["role"], content=row["content"],
        image_base64=row["image_base64"], image_media_type=row["image_media_type"],
        metadata_json=row["metadata_json"], token_count=row["token_count"],
        created_at=_parse_dt(row["created_at"]),
    )
```

**Then replace every inline Model(...) construction with the helper call.**

Affected functions (each has inline construction):
- `get_user_by_email` → use `_row_to_user(row)`
- `create_subject` → use `_row_to_subject(row)` after SELECT (currently returns hardcoded, change to SELECT after INSERT for consistency, OR keep the hardcoded return but use helper for consistency)
- `list_subjects` → use list comprehension with `_row_to_subject(r)`
- `create_chat` → similar to create_subject
- `list_chats` → use list comprehension with `_row_to_chat(r)`
- `get_chat` → use `_row_to_chat(row)`
- `update_chat_title` → use `_row_to_chat(row)`
- `get_messages` → use list comprehension with `_row_to_message(r)`
- `save_message` → currently returns hardcoded Model, keep or change to SELECT

**Note:** For `create_subject` and `create_chat`, the current code constructs the model from the input parameters (not from a SELECT). This is fine and actually more efficient. Keep those as-is but use the helper pattern for consistency ONLY if you do a SELECT after INSERT. The simplest approach: keep the create functions returning from parameters, use helpers only for SELECT-based functions.

### 1.2: Reduce list comprehension verbosity

Lines like this in `list_chats` (line 186) are ~200 characters long:
```python
return [Chat(id=r["id"], subject_id=r["subject_id"], ...) for r in rows]
```

After 1.1, these become:
```python
return [_row_to_chat(r) for r in rows]
```

This is already much shorter. No additional work needed beyond 1.1.

### 1.3: Simplify delete_chat

Current `delete_chat` (lines 197-201):
```python
def delete_chat(chat_id: int) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return cur.rowcount > 0
```

This is already fine. The manual cascade is necessary because the schema doesn't have `ON DELETE CASCADE`. **Leave as-is.** Don't add CASCADE to the schema as that would be a behavior change.

### 1.4: Remove `_parse_dt` if trivially replaceable

`_parse_dt` is just `datetime.fromisoformat(value)`. It's used ~10 times. It adds a layer of indirection for no real value. **Decision: keep it** since it provides a single place to change if date parsing ever needs adjustment. This is actually good composable design.

### 1.5: Verify

Run:
```bash
cd /Users/zac/Desktop/homework-helper/backend
python -c "from app.db import *; print('All DB imports OK')"
```

Then manually verify no function signatures changed by comparing:
```bash
grep "^def " app/db.py
```

The output should match the original function names exactly:
- `_resolve_db_path`, `_parse_dt`, `get_conn`, `init_db`
- `get_user_by_email`, `create_verification_code`, `verify_code`
- `create_subject`, `list_subjects`, `delete_subject`
- `create_chat`, `list_chats`, `get_chat`, `delete_chat`
- `save_message`, `get_messages`, `update_chat_title`, `update_chat_token_usage`

---

## Expected Outcome

- ~30-40 fewer lines of code (from ~240 to ~200-210)
- Zero function signature changes
- Zero SQL query changes
- All Row→Model conversions centralized in helpers
