"""Team Accounts tab — admin-only user management."""

import streamlit as st

from src import database as db

ROLES = ["analyst", "admin", "viewer"]


def render(conn, current_user):
    st.subheader("Team Accounts")
    if current_user["role"] != "admin":
        st.info("Only administrators can manage accounts.")
        return

    st.caption(
        "Create a login for each team member. Admins can manage accounts; "
        "analysts get the dashboard and review queue."
    )

    with st.form("create_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        username = c1.text_input("Username")
        display_name = c2.text_input("Display name")
        c3, c4 = st.columns(2)
        password = c3.text_input("Password", type="password")
        role = c4.selectbox("Role", ROLES)
        if st.form_submit_button("Create account", type="primary"):
            if not username.strip() or not password:
                st.error("Username and password are required.")
            elif db.create_user(conn, username, password, display_name or username, role):
                st.success(f"Account '{username.strip().lower()}' created.")
                st.rerun()
            else:
                st.error("That username already exists.")

    st.markdown("**Existing accounts**")
    users = db.list_users(conn)
    st.dataframe(users, width="stretch", hide_index=True)

    removable = [u for u in users["username"] if u != current_user["username"]]
    if removable:
        c1, c2 = st.columns([2, 1])
        target = c1.selectbox("Remove account", removable)
        if c2.button("Remove", type="secondary"):
            db.delete_user(conn, target)
            st.success(f"Removed '{target}'.")
            st.rerun()
