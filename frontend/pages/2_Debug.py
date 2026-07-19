import json
import sqlite3
from pathlib import Path

import streamlit as st

from auth import require_auth

require_auth()

st.set_page_config(page_title="Debug — homework-helper", page_icon="🔍", layout="wide")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "homework_helper.db"

st.title("🔍 Debug")

if not DB_PATH.exists():
    st.warning(f"Database not found at `{DB_PATH}`. Start the backend first.")
    st.stop()


def query(sql: str, params: tuple = ()):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


# --- Init drill-down state ---
if "debug_stack" not in st.session_state:
    st.session_state.debug_stack = []  # list of (level, label, id)


def drill(level: int, label: str, id_: int):
    # slice to current level, then push
    st.session_state.debug_stack = st.session_state.debug_stack[:level]
    st.session_state.debug_stack.append((level, label, id_))


def jump(level: int):
    st.session_state.debug_stack = st.session_state.debug_stack[:level]


# --- Breadcrumb ---
stack = st.session_state.debug_stack
parts = ["Users"]
for _, label, _ in stack:
    parts.append(label)

cols = st.columns(len(parts))
for i, part in enumerate(parts):
    with cols[i]:
        if i < len(parts) - 1:
            if st.button(part, key=f"bc_{i}", use_container_width=True):
                jump(i)
                st.rerun()
        else:
            st.markdown(f"**{part}**")

st.divider()

# --- Render current level ---
current_level = len(stack)

# Level 0: Users
if current_level == 0:
    users = query("SELECT * FROM users ORDER BY created_at")
    if not users:
        st.info("No users yet.")
    for u in users:
        msg_count = query("SELECT count(*) as cnt FROM messages m JOIN chats c ON c.id = m.chat_id WHERE c.user_id = ?", (u["id"],))[0]["cnt"]
        if st.button(f"**{u['email']}**", key=f"u_{u['id']}", use_container_width=True):
            drill(0, u["email"], u["id"])
            st.rerun()
        st.caption(f"id={u['id']}  |  {msg_count} messages  |  {u['created_at']}")

# Level 1: Subjects for user
elif current_level == 1:
    user_id = stack[0][2]
    subjects = query("SELECT * FROM subjects WHERE user_id = ? ORDER BY created_at", (user_id,))
    if not subjects:
        st.info("No subjects for this user.")
    for s in subjects:
        chat_count = query("SELECT count(*) as cnt FROM chats WHERE subject_id = ?", (s["id"],))[0]["cnt"]
        if st.button(f"**{s['name']}**", key=f"s_{s['id']}", use_container_width=True):
            drill(1, s["name"], s["id"])
            st.rerun()
        st.caption(f"id={s['id']}  |  {chat_count} chats  |  {s['created_at']}")

# Level 2: Chats for subject
elif current_level == 2:
    subject_id = stack[1][2]
    chats = query("SELECT * FROM chats WHERE subject_id = ? ORDER BY created_at DESC", (subject_id,))
    if not chats:
        st.info("No chats for this subject.")
    for c in chats:
        msg_count = query("SELECT count(*) as cnt FROM messages WHERE chat_id = ?", (c["id"],))[0]["cnt"]
        if st.button(f"**{c['title']}** [{c['mode']}]", key=f"c_{c['id']}", use_container_width=True):
            drill(2, c["title"], c["id"])
            st.rerun()
        st.caption(f"id={c['id']}  |  {msg_count} messages  |  {c['created_at']}")

# Level 3: Messages for chat
elif current_level == 3:
    chat_id = stack[2][2]
    chat = query("SELECT * FROM chats WHERE id = ?", (chat_id,))
    if chat:
        c = chat[0]
        st.caption(f"**{c['title']}** — mode: {c['mode']}  |  created: {c['created_at']}")

    messages = query("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at", (chat_id,))
    if not messages:
        st.info("No messages in this chat.")

    for m in messages:
        meta = {}
        if m["metadata_json"]:
            try:
                meta = json.loads(m["metadata_json"])
            except json.JSONDecodeError:
                pass

        with st.expander(f"#{m['id']}  {m['role']}  {m['created_at']}", expanded=False):
            st.text_area("content", m["content"], height=150, disabled=True, key=f"c_{m['id']}")
            if meta:
                c1, c2 = st.columns(2)
                with c1:
                    if meta.get("node"):
                        st.caption(f"**node:** {meta['node']}")
                    if meta.get("tool_calls"):
                        st.caption(f"**tool_calls:** {len(meta['tool_calls'])}")
                with c2:
                    if meta.get("token_usage"):
                        tu = meta["token_usage"]
                        st.caption(f"**tokens:** {tu.get('total_tokens', '?')}")
            if m["image_base64"]:
                st.caption(f"**image:** {m['image_media_type']} ({len(m['image_base64'])} chars)")

# --- Orphan messages (messages with no chat) ---
if current_level == 0:
    st.divider()
    orphans = query("SELECT * FROM messages WHERE chat_id IS NULL OR chat_id = 0 ORDER BY created_at DESC LIMIT 50")
    if orphans:
        st.subheader(f"Orphan Messages ({len(orphans)})")
        st.caption("Messages not linked to any chat")
        for m in orphans:
            meta = {}
            if m["metadata_json"]:
                try:
                    meta = json.loads(m["metadata_json"])
                except json.JSONDecodeError:
                    pass
            with st.expander(f"#{m['id']}  {m['role']}  {m['created_at']}", expanded=False):
                st.text_area("content", m["content"], height=150, disabled=True, key=f"o_{m['id']}")
                if meta:
                    st.json(meta)

# --- SQL Editor (always at bottom) ---
st.divider()
st.subheader("SQL Editor")
sql = st.text_area("Query", value="SELECT * FROM messages ORDER BY created_at DESC LIMIT 20;", height=100)
if st.button("Run"):
    try:
        rows = query(sql)
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("No results.")
    except Exception as e:
        st.error(str(e))
