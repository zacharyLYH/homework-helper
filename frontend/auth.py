import streamlit as st


def is_authenticated() -> bool:
    return st.session_state.get("authenticated", False)


def login(email: str):
    st.session_state["authenticated"] = True
    st.session_state["user_email"] = email


def logout():
    for key in ["authenticated", "user_email", "thread_id", "messages"]:
        st.session_state.pop(key, None)


def require_auth():
    """Redirect to login page if not authenticated."""
    if not is_authenticated():
        st.switch_page("app.py")
