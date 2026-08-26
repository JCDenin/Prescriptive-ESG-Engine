"""Tab 3: Recommendations — MACC playbook results."""

import streamlit as st

from src import database as db, recommendations as recommend


def render(conn):
    if not db.has_data(conn):
        st.info("Load data in the Data Upload tab to see recommendations.")
        return

    eligible = db.get_eligible(conn)
    recs = recommend.generate_recommendations(eligible, db.get_budgets(conn))

    st.subheader("Recommendations (MACC Playbook)")
    st.caption(
        "Rule-based playbook defined by the Product Owner. Calculated only from "
        "high-confidence and manually approved transactions "
        f"({len(eligible):,} records in scope)."
    )

    if not recs:
        st.info("No playbook rules triggered on the current data.")
        return

    for rec in recs:
        with st.container(border=True):
            st.markdown(f"**{rec['title']}**")
            st.caption(rec["rule"])
            m1, m2, m3 = st.columns(3)
            m1.metric("Estimated saving", f"EUR {rec['saving_eur']:,.0f}")
            m2.metric("CO2e reduction", f"{rec['saving_co2e_kg']:,.0f} kg")
            m3.metric("Department(s)", rec["department"])
            st.write(rec["rationale"])
            if "detail" in rec:
                with st.expander("Flagged transactions"):
                    st.dataframe(rec["detail"], width="stretch", hide_index=True)
