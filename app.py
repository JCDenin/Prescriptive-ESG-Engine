"""Prescriptive ESG Dashboard — MVP entry point.

Run:  streamlit run app.py     (demo login: admin / admin)
"""

import streamlit as st

from src import database as db
from ui import overview, recommendations, review_queue, upload

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
    /* Metric text must adapt to zoom/narrow columns instead of truncating
       with an ellipsis: viewport-relative font size + wrapping fallback. */
    div[data-testid="stMetricValue"] {
        font-size: clamp(1.05rem, 1.6vw + 0.4rem, 2.1rem) !important;
    }
    div[data-testid="stMetricValue"] > div,
    div[data-testid="stMetricLabel"],
    div[data-testid="stMetricLabel"] p,
    div[data-testid="stMetricDelta"],
    div[data-testid="stMetricDelta"] > div {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
</style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_conn():
    return db.get_conn()


def login_gate():
    st.title("Prescriptive ESG Dashboard")
    st.caption("Scope 3 Category 6 & 7 monitoring — MVP demo")
    with st.form("login"):
        user = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            if user == "admin" and password == "admin":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Invalid credentials.")


def main():
    conn = get_conn()
    header_left, header_right = st.columns([5, 1])
    header_left.title("Prescriptive ESG Dashboard")
    header_left.caption(
        "Transaction-based Scope 3 monitoring: business-travel leakage "
        "(Category 6) and commuting patterns (Category 7)"
    )
    if header_right.button("Sign out"):
        st.session_state.clear()
        st.rerun()

    review_queue.render(conn)

    tab_upload, tab_overview, tab_recs = st.tabs(
        ["Data Upload", "Emissions & Financial Overview", "Recommendations"]
    )
    with tab_upload:
        upload.render(conn)
    with tab_overview:
        overview.render(conn)
    with tab_recs:
        recommendations.render(conn)


if st.session_state.get("authenticated"):
    main()
else:
    login_gate()
