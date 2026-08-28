"""Tab 1: Data Upload — CSV ingest, classification run, summary."""

from pathlib import Path

import pandas as pd
import streamlit as st

from src import classification as classifier, database as db, ingestion

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_transactions.csv"


def _ingest(conn, raw: pd.DataFrame, source: str):
    try:
        validated_df = ingestion.load_and_validate_data(raw)
    except ValueError as e:
        st.error(f"Invalid file: {e}")
        return

    validated_df = validated_df.astype({"time": str})
    db.ingest_transactions(conn, validated_df)
    db.store_classifications(conn, classifier.classify_transactions(validated_df))
    st.session_state["last_ingest"] = source
    st.rerun()


def render(conn):
    st.subheader("Data Upload")
    st.caption(
        "Upload a transaction export from the corporate expense system. "
        "Records are classified automatically; low-confidence records are "
        "routed to the review queue in the sidebar."
    )

    uploaded = st.file_uploader("Transaction CSV", type="csv")
    col_a, col_b = st.columns([1, 3])
    if col_a.button("Process uploaded file", type="primary", disabled=uploaded is None):
        _ingest(conn, pd.read_csv(uploaded, dtype={"time": str}), uploaded.name)
    if SAMPLE_PATH.exists() and col_b.button("Load bundled sample dataset"):
        _ingest(conn, pd.read_csv(SAMPLE_PATH, dtype={"time": str}), SAMPLE_PATH.name)

    if not db.has_data(conn):
        st.info("No data loaded yet. Upload a CSV or load the sample dataset.")
        return

    data = db.get_all(conn)
    if "last_ingest" in st.session_state:
        st.success(f"Loaded and classified: {st.session_state['last_ingest']}")

    st.markdown("**Ingest summary**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transactions", f"{len(data):,}")
    c2.metric("Employees", f"{data['employee_id'].nunique()}")
    c3.metric("Auto-classified", f"{(data['review_status'] != 'pending').mean():.0%}")
    c4.metric("Pending review", f"{(data['review_status'] == 'pending').sum()}")

    st.markdown("**Classified records (first 100)**")
    preview = data[
        ["transaction_id", "date", "time", "department", "merchant_name",
         "amount_eur", "payment_channel", "category", "scope3_category",
         "confidence", "review_status"]
    ].head(100)
    st.dataframe(preview, use_container_width=True, height=320)