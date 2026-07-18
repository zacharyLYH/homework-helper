import streamlit as st

from auth import is_authenticated, login

st.set_page_config(page_title="homework-helper", page_icon="📚", layout="wide")

if is_authenticated():
    st.switch_page("pages/1_Chat.py")

st.title("📚 homework-helper")
st.markdown("Enter your email to get started.")

with st.form("login_form"):
    email = st.text_input("Email", placeholder="you@example.com")
    submitted = st.form_submit_button("Continue", use_container_width=True)

if submitted and email:
    login(email)
    st.rerun()
elif submitted:
    st.error("Please enter a valid email.")
