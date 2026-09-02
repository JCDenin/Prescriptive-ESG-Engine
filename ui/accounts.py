"""Team Accounts tab — admin-only user management."""

import streamlit as st

from src import database as db

ROLES = ["analyst", "admin", "guest"]


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

    st.caption(
        "New accounts get a temporary password: the member is asked to set "
        "their own password on first sign-in."
    )

    st.markdown("**Existing accounts**")
    users = db.list_users(conn)
    st.dataframe(users, width="stretch", hide_index=True)

    st.markdown("**Reset a password**")
    r1, r2, r3 = st.columns([2, 2, 1])
    reset_target = r1.selectbox("Account", list(users["username"]), key="pw_reset_user")
    temp_pw = r2.text_input("Temporary password", type="password", key="pw_reset_val")
    if r3.button("Reset"):
        if len(temp_pw) < 6:
            st.error("Temporary password must be at least 6 characters.")
        else:
            db.set_password(conn, reset_target, temp_pw, must_change=True,
                            changed_by=current_user["username"])
            st.success(
                f"Password for '{reset_target}' reset — they must choose a "
                "new one at next sign-in."
            )

    removable = [u for u in users["username"] if u != current_user["username"]]
    if removable:
        c1, c2 = st.columns([2, 1])
        target = c1.selectbox("Remove account", removable)
        if c2.button("Remove", type="secondary"):
            db.delete_user(conn, target)
            st.success(f"Removed '{target}'.")
            st.rerun()
