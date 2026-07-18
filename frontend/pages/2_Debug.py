import json
import sqlite3
from pathlib import Path

import streamlit as st

from auth import require_auth

require_auth()

st.set_page_config(page_title="Debug — homework-helper", page_icon="🔍", layout="wide")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "homework_helper.db"


def get_conn():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


st.title("🔍 Debug Dashboard")

conn = get_conn()
if not conn:
    st.warning(f"Database not found at `{DB_PATH}`. Start the backend first.")
    st.stop()

# --- Users ---
st.header("Users")
users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
if users:
    st.dataframe([dict(r) for r in users], use_container_width=True)
else:
    st.info("No users yet.")

# --- Messages ---
st.header("Messages")
messages = conn.execute("""
    SELECT id, chat_id, role, content, image_base64 IS NOT NULL as has_image, metadata_json, created_at
    FROM messages
    ORDER BY created_at DESC
    LIMIT 50
""").fetchall()

if messages:
    rows = []
    for m in messages:
        row = dict(m)
        # Parse metadata for display
        meta = {}
        if row["metadata_json"]:
            try:
                meta = json.loads(row["metadata_json"])
            except json.JSONDecodeError:
                meta = {"raw": row["metadata_json"]}
        row["node"] = meta.get("node", "")
        row["tool_calls"] = json.dumps(meta.get("tool_calls", [])) if meta.get("tool_calls") else ""
        row["token_usage"] = json.dumps(meta.get("token_usage", {})) if meta.get("token_usage") else ""
        del row["metadata_json"]
        del row["has_image"]
        rows.append(row)
    st.dataframe(rows, use_container_width=True)
else:
    st.info("No messages yet.")

# --- Raw message detail ---
st.header("Message Detail")
if messages:
    selected_id = st.selectbox("Select message ID", [m["id"] for m in messages])
    msg = conn.execute("SELECT * FROM messages WHERE id = ?", (selected_id,)).fetchone()
    if msg:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Content")
            st.text_area("content", msg["content"], height=200, disabled=True)
        with col2:
            st.subheader("Metadata")
            if msg["metadata_json"]:
                try:
                    meta = json.loads(msg["metadata_json"])
                    st.json(meta)
                except json.JSONDecodeError:
                    st.code(msg["metadata_json"])
            else:
                st.info("No metadata")

        if msg["image_base64"]:
            st.subheader("Image")
            st.info(f"Image stored ({len(msg['image_base64'])} chars base64, type: {msg['image_media_type']})")

conn.close()
