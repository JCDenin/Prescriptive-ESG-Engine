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
st.markdown(
    """
    <style>
    .stApp { background-color: #FAFAFA; }
    section[data-testid="stSidebar"] { background-color: #F1F3F5; }
    div[data-testid="stMetric"] {
        background: #FFFFFF; border: 1px solid #E3E6E8;
        border-radius: 8px; padding: 12px 16px;
    }
    h1, h2, h3 { color: #1F2933; }
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
