"""Sidebar: Human-in-the-Loop review queue.

Low-confidence classifications wait here until a manager approves or corrects
them; only then do they become eligible for the Overview figures and the MACC
engine (see esg.db.ELIGIBLE_STATUSES).
"""

import streamlit as st

from src import database as db
from src.emissions import FACTORS_KG_PER_EUR

CATEGORY_OPTIONS = sorted(FACTORS_KG_PER_EUR)


def render(conn):
    st.sidebar.markdown("### Review queue")
    if not db.has_data(conn):
        st.sidebar.caption("No data loaded.")
        return

    pending = db.get_pending(conn)
    st.sidebar.markdown(f"**Pending Review ({len(pending)})**")
    if pending.empty:
        st.sidebar.caption("All records reviewed. Figures include the full dataset.")
        return

    st.sidebar.caption(
        "Low-confidence classifications. Approve or correct the category; "
        "reviewed records then count toward reports and recommendations."
    )
    for row in pending.head(15).itertuples():
        label = f"{row.merchant_name} — EUR {row.amount_eur:,.2f}"
        with st.sidebar.expander(label):
            st.caption(
                f"{row.transaction_id} · {row.date} {row.time} · "
                f"{row.department} · {row.payment_channel} · {row.expense_context}"
            )
            st.caption(f"Suggested: {row.category} (confidence {row.confidence:.0%})")
            choice = st.selectbox(
                "Category", CATEGORY_OPTIONS,
                index=CATEGORY_OPTIONS.index(row.category) if row.category in CATEGORY_OPTIONS else CATEGORY_OPTIONS.index("unknown"),
                key=f"cat_{row.transaction_id}",
            )
            if st.button("Approve", key=f"ok_{row.transaction_id}", type="primary"):
                db.set_review(conn, row.transaction_id, new_category=choice)
                st.rerun()
    if len(pending) > 15:
        st.sidebar.caption(f"...and {len(pending) - 15} more.")
