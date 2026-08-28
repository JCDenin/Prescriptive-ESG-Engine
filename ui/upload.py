"""Tab 1: Data Upload — CSV ingest, classification run, dataset history."""

from pathlib import Path

import pandas as pd
import streamlit as st

from src import classification as classifier, database as db, ingestion

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_transactions.csv"


def _ingest(conn, raw: pd.DataFrame, source: str, user: dict, label: str):
    try:
        validated_df = ingestion.load_and_validate_data(raw)
    except ValueError as e:
        st.error(f"Invalid file: {e}")
        return

    validated_df = validated_df.astype({"time": str})
    dataset_id = db.ingest_transactions(
        conn, validated_df,
        label=label or source, source_file=source,
        uploaded_by=user["username"],
    )
    db.store_classifications(
        conn, classifier.classify_transactions(validated_df), dataset_id
    )
    st.session_state["last_ingest"] = source
    st.rerun()


def _history(conn, user):
    datasets = db.list_datasets(conn)
    if datasets.empty:
        return
    st.markdown("**Dataset history**")
    st.caption(
        "Every upload is kept as its own dataset, including its review "
        "decisions. Activate an earlier one to go back to it — all reports "
        "and recommendations follow the active dataset."
    )
    view = datasets.rename(columns={"is_active": "active"})
    view["active"] = view["active"].map({1: "● active", 0: ""})
    st.dataframe(
        view[["dataset_id", "label", "uploaded_by", "uploaded_at", "n_rows", "active"]],
        width="stretch", hide_index=True,
    )
    inactive = datasets[datasets["is_active"] == 0]
    if not inactive.empty:
        options = {
            f"#{r.dataset_id} — {r.label} ({r.uploaded_at}, {r.n_rows} rows)": r.dataset_id
            for r in inactive.itertuples()
        }
        c1, c2, c3 = st.columns([3, 1, 1])
        choice = c1.selectbox("Switch to dataset", list(options), label_visibility="collapsed")
        if c2.button("Activate"):
            db.activate_dataset(conn, options[choice], user["username"])
            st.rerun()
        if user["role"] == "admin" and c3.button("Delete", type="secondary"):
            db.delete_dataset(conn, options[choice], user["username"])
            st.rerun()


def render(conn, user):
    st.subheader("Data Upload")
    st.caption(
        "Upload a transaction export from the corporate expense system. "
        "Records are classified automatically; low-confidence records are "
        "routed to the review queue in the sidebar."
    )

    label = st.text_input(
        "Dataset label (for the history)", placeholder="e.g. June 2026 export",
    )
    uploaded = st.file_uploader("Transaction CSV", type="csv")
    col_a, col_b = st.columns([1, 3])
    if col_a.button("Process uploaded file", type="primary", disabled=uploaded is None):
        _ingest(conn, pd.read_csv(uploaded, dtype={"time": str}), uploaded.name,
                user, label)
    if SAMPLE_PATH.exists() and col_b.button("Load bundled sample dataset"):
        _ingest(conn, pd.read_csv(SAMPLE_PATH, dtype={"time": str}),
                SAMPLE_PATH.name, user, label or "Bundled sample")

    st.divider()
    _history(conn, user)

    if not db.has_data(conn):
        st.info("No data loaded yet. Upload a CSV or load the sample dataset.")
        return

    data = db.get_all(conn)
    if "last_ingest" in st.session_state:
        st.success(f"Loaded and classified: {st.session_state['last_ingest']}")

    st.markdown("**Ingest summary (active dataset)**")
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
    st.dataframe(preview, width="stretch", height=320)
