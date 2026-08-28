"""Prescriptive ESG Dashboard — MVP entry point.

Run:  streamlit run app.py     (demo login: admin / admin)
"""

import streamlit as st

from src import database as db
from ui import accounts, overview, recommendations, review_queue, upload

st.set_page_config(
    page_title="Prescriptive ESG Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Corporate finance look: neutral base, restrained accents (see task doc).
# Palette comes from .streamlit/config.toml; CSS uses Streamlit theme
# variables so a manual switch to dark mode still renders with clean contrast.
st.markdown(
    """
    <style>
    /* Translucent neutral card: renders correctly on light AND dark themes
       (Streamlit exposes no theme CSS variables to hook into). */
    div[data-testid="stMetric"] {
        background: rgba(128, 128, 128, 0.07);
        border: 1px solid rgba(128, 128, 128, 0.28);
        border-radius: 8px; padding: 12px 16px;
    }
    /* Metric text must adapt to zoom/narrow columns instead of truncating.
       Streamlit applies the ellipsis on nested inner nodes, so the override
       must cover EVERY descendant of the metric card, not named testids. */
    div[data-testid="stMetricValue"] {
        font-size: clamp(1rem, 1.6vw + 0.35rem, 2.1rem) !important;
        line-height: 1.25 !important;
    }
    div[data-testid="stMetric"],
    div[data-testid="stMetric"] * {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        max-width: none !important;
    }
</style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_conn():
    return db.get_conn()


def restore_session(conn):
    """Refresh-proof login: a browser reload wipes st.session_state, but the
    session token survives in the URL query string — validate it against the
    sessions table and restore the user."""
    if "user" in st.session_state:
        return
    token = st.query_params.get("session")
    if token:
        user = db.session_user(conn, token)
        if user:
            st.session_state["user"] = user
            st.session_state["token"] = token


def login_gate(conn):
    st.title("Prescriptive ESG Dashboard")
    st.caption("Scope 3 Category 6 & 7 monitoring — MVP demo")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            user = db.verify_user(conn, username, password)
            if user:
                token = db.create_session(conn, user["username"])
                st.session_state["user"] = user
                st.session_state["token"] = token
                st.query_params["session"] = token
                st.rerun()
            else:
                st.error("Invalid credentials.")


def main(conn):
    user = st.session_state["user"]
    header_left, header_right = st.columns([5, 1])
    header_left.title("Prescriptive ESG Dashboard")
    header_left.caption(
        "Transaction-based Scope 3 monitoring: business-travel leakage "
        "(Category 6) and commuting patterns (Category 7)"
    )
    header_right.caption(f"{user['display_name']} · {user['role']}")
    if header_right.button("Sign out"):
        db.delete_session(conn, st.session_state.get("token", ""))
        st.query_params.clear()
        st.session_state.clear()
        st.rerun()

    review_queue.render(conn)

    tab_names = ["Data Upload", "Emissions & Financial Overview", "Recommendations"]
    if user["role"] == "admin":
        tab_names.append("Team Accounts")
    tabs = st.tabs(tab_names)
    with tabs[0]:
        upload.render(conn)
    with tabs[1]:
        overview.render(conn)
    with tabs[2]:
        recommendations.render(conn)
    if user["role"] == "admin":
        with tabs[3]:
            accounts.render(conn, user)


_conn = get_conn()
restore_session(_conn)
if st.session_state.get("user"):
    main(_conn)
else:
    login_gate(_conn)
