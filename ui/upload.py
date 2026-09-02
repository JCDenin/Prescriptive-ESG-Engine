"""Tab 1: Data Upload — CSV ingest, classification run, dataset history."""

from pathlib import Path

import pandas as pd
import streamlit as st

from src import classification as classifier, database as db, ingestion, simulator

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_transactions.csv"
DEMO_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_dataset.csv"


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
        use_container_width=True, hide_index=True,
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
        if c3.button("Delete", type="secondary"):
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
    col_a, col_b, col_c = st.columns([1, 1, 2])
    if col_a.button("Process uploaded file", type="primary", disabled=uploaded is None):
        _ingest(conn, pd.read_csv(uploaded, dtype={"time": str}), uploaded.name,
                user, label)
    if DEMO_PATH.exists() and col_b.button("Load jury demo dataset"):
        # Pre-tested Monte Carlo run (seed 2029, demo mode): guaranteed
        # visible leakage findings and savings — use this for presentations.
        _ingest(conn, pd.read_csv(DEMO_PATH, dtype={"time": str}),
                DEMO_PATH.name, user, label or "Jury demo (seed 2029)")
    if SAMPLE_PATH.exists() and col_c.button("Load bundled sample dataset"):
        _ingest(conn, pd.read_csv(SAMPLE_PATH, dtype={"time": str}),
                SAMPLE_PATH.name, user, label or "Bundled sample")

    with st.expander("Generate synthetic dataset (Monte Carlo simulation)"):
        st.caption(
            "Samples a random 'company world' (commuter share, travel "
            "intensity, off-channel leakage rate, ...) from probability "
            "distributions, then simulates day-by-day transactions: commute "
            "times around personal habits, log-normal amounts, business-trip "
            "bundles. Every run without a seed produces a different dataset."
        )
        g1, g2, g3 = st.columns([1, 1, 1])
        n_rows = g1.number_input("Rows", min_value=500, max_value=50000,
                                 value=10000, step=500)
        seed_text = g2.text_input("Seed (blank = random)", value="")
        demo_mode = st.checkbox(
            "Demo mode — priors tuned to a travel-heavy company with a real "
            "off-channel problem, so findings are reliably visible",
            value=True,
        )
        if g3.button("Generate & ingest", type="primary"):
            seed = int(seed_text) if seed_text.strip().lstrip("-").isdigit() else None
            with st.spinner("Simulating and classifying..."):
                sim_df, params = simulator.simulate(
                    n_rows=int(n_rows), seed=seed, demo_mode=demo_mode
                )
                st.session_state["mc_params"] = params
                _ingest(conn, sim_df, f"monte_carlo_seed{params['seed']}.csv",
                        user, label or f"Monte Carlo #{params['seed']}")
        if "mc_params" in st.session_state:
            st.markdown("**Sampled world parameters (last run)**")
            st.json(st.session_state["mc_params"])

    # --- Interactive NLP Testing Sandbox ---
    st.divider()
    with st.expander("🧪 Free-text NLP Classifier Sandbox", expanded=False):
        st.caption(
            "Test how the zero-shot NLP model classifies unstructured "
            "free-text transaction descriptions when no merchant rule is matched."
        )
        
        user_input = st.text_input(
            "Enter transaction description or merchant name:",
            placeholder="e.g., Express shuttle bus ticket from airport to hotel",
            key="sandbox_input"
        )
        
        col_ctx, col_pay = st.columns(2)
        with col_ctx:
            context = st.selectbox(
                "Expense Context", 
                ["Business_Trip", "Daily_Expense"], 
                key="sandbox_context"
            )
        with col_pay:
            payment = st.selectbox(
                "Payment Channel", 
                ["TMC_Corporate", "Personal_Card_Reimbursement"], 
                key="sandbox_payment"
            )

        if user_input.strip():
            category, confidence = classifier.match_merchant(user_input.strip())
            scope3 = classifier.scope3_for(category, context)
            leakage = classifier.is_leakage(category, payment, context)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Predicted Category", category.title())
            m2.metric("Scope 3", scope3)
            m3.metric("Confidence Score", f"{confidence:.0%}")
            m4.metric("Leakage Flag", "🚨 Yes" if leakage else "✅ No")

            if confidence < 0.80:
                st.warning("⚠️ Confidence below 80% — this record would be routed to the **Human-in-the-Loop Review Queue**.")
            else:
                st.success("✅ High confidence — record would be **Auto-classified**.")

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
    st.dataframe(preview, use_container_width=True, height=320)