"""Tab 4: Reports — filterable drill-downs, trends, review/audit trail, and
downloadable CSV/Excel exports for the active dataset."""

import io

import pandas as pd
import plotly.express as px
import streamlit as st

from src import database as db, recommendations as recommend

NEUTRALS = ["#3D5A6C", "#6B8CA3", "#9DB4C4", "#C6D4DE", "#5E7A8C"]
AMBER = "#B45309"


def _filters(data):
    c1, c2 = st.columns([2, 2])
    departments = sorted(data["department"].unique())
    picked = c1.multiselect("Departments", departments, default=departments)
    dates = pd.to_datetime(data["date"], errors="coerce")
    lo, hi = dates.min().date(), dates.max().date()
    span = c2.date_input("Date range", (lo, hi), min_value=lo, max_value=hi)
    if isinstance(span, (list, tuple)) and len(span) == 2:
        lo, hi = span
    mask = data["department"].isin(picked) & dates.dt.date.between(lo, hi)
    return data[mask]


def _trend(view):
    daily = (
        view.assign(day=pd.to_datetime(view["date"], errors="coerce").dt.date)
        .groupby(["day", "scope3_category"], as_index=False)["co2e_kg"].sum()
    )
    daily = daily[daily["scope3_category"] != "Out of scope"]
    fig = px.area(
        daily, x="day", y="co2e_kg", color="scope3_category",
        title="Daily emissions trend (kg CO2e)",
        color_discrete_map={"Category 6": NEUTRALS[0], "Category 7": NEUTRALS[1]},
        labels={"co2e_kg": "kg CO2e", "day": "", "scope3_category": ""},
    )
    fig.update_layout(height=320, legend=dict(orientation="h", y=-0.2),
                      margin=dict(t=48, b=8), plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")


def _breakdowns(view):
    left, right = st.columns(2)
    pivot = (
        view[view["scope3_category"] != "Out of scope"]
        .pivot_table(index="department", columns="category", values="co2e_kg",
                     aggfunc="sum", fill_value=0.0)
        .round(1)
    )
    left.markdown("**Department × category (kg CO2e)**")
    left.dataframe(pivot, width="stretch")

    top = (
        view.groupby("merchant_name", as_index=False)
        .agg(co2e_kg=("co2e_kg", "sum"), spend_eur=("amount_eur", "sum"),
             transactions=("transaction_id", "count"))
        .sort_values("co2e_kg", ascending=False).head(10)
    )
    fig = px.bar(
        top.sort_values("co2e_kg"), x="co2e_kg", y="merchant_name",
        orientation="h", title="Top 10 merchants by emissions",
        labels={"co2e_kg": "kg CO2e", "merchant_name": ""},
    )
    fig.update_traces(marker_color=NEUTRALS[0])
    fig.update_layout(height=360, margin=dict(t=48, b=8), plot_bgcolor="rgba(0,0,0,0)")
    right.plotly_chart(fig, width="stretch")


def _leakage(view):
    leaks = view[view["leakage_flag"] == 1]
    st.markdown(f"**Category 6 leakage detail — {len(leaks)} transactions, "
                f"EUR {leaks['amount_eur'].sum():,.0f}**")
    if leaks.empty:
        st.caption("No off-channel business travel in the current filter.")
        return
    st.dataframe(
        leaks[["transaction_id", "date", "department", "employee_id",
               "merchant_name", "amount_eur", "category", "review_status"]]
        .sort_values("amount_eur", ascending=False),
        width="stretch", hide_index=True, height=260,
    )


def _review_trail(view, conn):
    st.markdown("**Review & audit trail**")
    reviewed = view[view["reviewed_by"].notna()]
    c1, c2 = st.columns(2)
    with c1:
        st.caption(f"Manual review decisions in this dataset: {len(reviewed)}")
        if not reviewed.empty:
            st.dataframe(
                reviewed[["transaction_id", "merchant_name", "category",
                          "review_status", "reviewed_by", "reviewed_at"]],
                width="stretch", hide_index=True, height=220,
            )
    with c2:
        st.caption("Recent activity (all users, newest first)")
        st.dataframe(db.get_audit_log(conn, limit=50), width="stretch",
                     hide_index=True, height=220)


def _exports(view, conn, include_audit=True):
    st.markdown("**Export**")
    c1, c2 = st.columns(2)
    c1.download_button(
        "Download filtered data (CSV)",
        view.to_csv(index=False).encode("utf-8"),
        file_name="esg_report_data.csv", mime="text/csv",
    )

    buffer = io.BytesIO()
    recs = recommend.generate_recommendations(
        view[view["review_status"].isin(db.ELIGIBLE_STATUSES)], db.get_budgets(conn)
    )
    recs_df = pd.DataFrame(
        [{k: v for k, v in r.items() if k != "detail"} for r in recs]
    )
    summary = pd.DataFrame({
        "metric": ["Transactions", "Total CO2e (kg)", "Total spend (EUR)",
                   "Leakage spend (EUR)", "Pending review"],
        "value": [len(view), round(view["co2e_kg"].sum(), 1),
                  round(view["amount_eur"].sum(), 2),
                  round(view.loc[view["leakage_flag"] == 1, "amount_eur"].sum(), 2),
                  int((view["review_status"] == "pending").sum())],
    })
    with pd.ExcelWriter(buffer, engine="openpyxl") as xl:
        summary.to_excel(xl, sheet_name="Summary", index=False)
        view.to_excel(xl, sheet_name="Transactions", index=False)
        view[view["leakage_flag"] == 1].to_excel(xl, sheet_name="Leakage", index=False)
        if not recs_df.empty:
            recs_df.to_excel(xl, sheet_name="Recommendations", index=False)
        if include_audit:
            db.get_audit_log(conn, limit=500).to_excel(xl, sheet_name="Audit", index=False)
    c2.download_button(
        "Download full report (Excel)", buffer.getvalue(),
        file_name="esg_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def render(conn, user):
    st.subheader("Reports")
    if not db.has_data(conn):
        st.info("Load data in the Data Upload tab to build reports.")
        return
    # Guests (jury) get the full product view without internal account
    # activity: the review/audit trail stays team-only.
    show_audit = user["role"] != "guest"

    data = db.get_all(conn)
    view = _filters(data)
    if view.empty:
        st.warning("No transactions match the current filter.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transactions", f"{len(view):,}")
    c2.metric("CO2e", f"{view['co2e_kg'].sum() / 1000:,.2f} t")
    c3.metric("Spend", f"EUR {view['amount_eur'].sum():,.0f}")
    c4.metric("Leakage", f"EUR {view.loc[view['leakage_flag'] == 1, 'amount_eur'].sum():,.0f}")

    _trend(view)
    _breakdowns(view)
    st.divider()
    _leakage(view)
    if show_audit:
        st.divider()
        _review_trail(view, conn)
    st.divider()
    _exports(view, conn, include_audit=show_audit)
