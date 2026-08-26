"""Tab 2: Emissions & Financial Overview — CFO-facing metrics and charts.

All figures are computed from ELIGIBLE transactions only (auto-classified or
human-approved); pending low-confidence records are excluded by design and
surfaced as their own metric.
"""

import plotly.express as px
import streamlit as st

from src import database as db, recommendations as recommend

GREEN = "#1B7F4B"   # single accent — savings / positive
AMBER = "#B45309"   # flagged / leakage only
GRAY = "#8A8F98"
NEUTRALS = ["#3D5A6C", "#6B8CA3", "#9DB4C4", "#C6D4DE", "#5E7A8C"]


def render(conn):
    if not db.has_data(conn):
        st.info("Load data in the Data Upload tab to see the overview.")
        return

    eligible = db.get_eligible(conn)
    pending_n = len(db.get_pending(conn))
    recs = recommend.generate_recommendations(eligible, db.get_budgets(conn))

    total_co2e = eligible["co2e_kg"].sum()
    total_savings = sum(r["saving_eur"] for r in recs)
    leakage = eligible[eligible["leakage_flag"] == 1]

    st.subheader("Emissions & Financial Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Scope 3 footprint", f"{total_co2e / 1000:,.1f} t CO2e")
    c2.metric("Identified savings potential", f"EUR {total_savings:,.0f}")
    c3.metric("Off-channel travel spend", f"EUR {leakage['amount_eur'].sum():,.0f}",
              delta=f"{len(leakage)} flagged transactions", delta_color="inverse")
    c4.metric("Pending manual review", f"{pending_n}",
              help="Low-confidence records excluded from all figures until reviewed.")

    st.divider()
    left, right = st.columns(2)

    dept_co2e = (
        eligible[eligible["scope3_category"] != "Out of scope"]
        .groupby(["department", "scope3_category"], as_index=False)["co2e_kg"].sum()
    )
    fig = px.bar(
        dept_co2e, x="department", y="co2e_kg", color="scope3_category",
        title="Emissions by department (kg CO2e)",
        color_discrete_map={"Category 6": NEUTRALS[0], "Category 7": NEUTRALS[1]},
        labels={"co2e_kg": "kg CO2e", "department": "", "scope3_category": ""},
    )
    fig.update_layout(height=360, legend=dict(orientation="h", y=-0.15),
                      margin=dict(t=48, b=8), plot_bgcolor="rgba(0,0,0,0)")
    left.plotly_chart(fig, width="stretch")

    cat_co2e = eligible.groupby("category", as_index=False)["co2e_kg"].sum().sort_values("co2e_kg")
    fig2 = px.bar(
        cat_co2e, x="co2e_kg", y="category", orientation="h",
        title="Emissions by spend category (kg CO2e)",
        labels={"co2e_kg": "kg CO2e", "category": ""},
    )
    fig2.update_traces(marker_color=NEUTRALS[0])
    fig2.update_layout(height=360, margin=dict(t=48, b=8), plot_bgcolor="rgba(0,0,0,0)")
    right.plotly_chart(fig2, width="stretch")

    travel = eligible[eligible["expense_context"] == "Business_Trip"]
    if not travel.empty:
        channel_spend = travel.groupby(["department", "payment_channel"], as_index=False)["amount_eur"].sum()
        fig3 = px.bar(
            channel_spend, x="department", y="amount_eur", color="payment_channel",
            barmode="group",
            title="Business travel spend: corporate channel vs off-channel (EUR)",
            color_discrete_map={"TMC_Corporate": NEUTRALS[0],
                                "Personal_Card_Reimbursement": AMBER},
            labels={"amount_eur": "EUR", "department": "", "payment_channel": ""},
        )
        fig3.update_layout(height=340, legend=dict(orientation="h", y=-0.15),
                           margin=dict(t=48, b=8), plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig3, width="stretch")
        st.caption(
            "Off-channel spend (amber) is business travel paid on personal cards "
            "outside the corporate booking tool — the Category 6 leakage the "
            "platform captures."
        )
