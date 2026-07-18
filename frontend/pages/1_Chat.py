import os

import httpx
import streamlit as st

from auth import logout, require_auth

require_auth()

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Chat — homework-helper", page_icon="📚", layout="wide")

# --- Sidebar ---
with st.sidebar:
    st.markdown(f"**{st.session_state.user_email}**")
    if st.button("Logout", use_container_width=True):
        logout()
        st.rerun()

    st.divider()

    if st.button("New Conversation", use_container_width=True):
        st.session_state.pop("thread_id", None)
        st.session_state.pop("messages", None)
        st.rerun()

    if st.button("Clear History", use_container_width=True):
        st.session_state.pop("messages", None)
        st.rerun()

# --- Init session state ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None

# --- Display chat history ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Chat input ---
if prompt := st.chat_input("Ask a homework question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            payload = {
                "message": prompt,
                "thread_id": st.session_state.thread_id,
            }
            try:
                resp = httpx.post(f"{BACKEND_URL}/api/chat", json=payload, timeout=60.0)
                resp.raise_for_status()
                data = resp.json()
                reply = data["reply"]
                st.session_state.thread_id = data["thread_id"]
            except httpx.ConnectError:
                reply = "Could not connect to backend. Is it running?"
            except Exception as e:
                reply = f"Error: {e}"

        st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
