"""MACC recommendation engine — the PO's rule-based playbook.

Consumes ONLY eligible transactions (auto-classified high-confidence or
human-approved/corrected); callers must pass the dataframe returned by
esg.db.get_eligible(). Rules and thresholds are defined by the Product Owner.
"""

COMMUTE_BUDGET_THRESHOLD = 0.30   # Rule 1: commuting > 30% of travel budget
HYBRID_DAY_FRACTION = 1 / 5       # one extra hybrid day removes ~1/5 of commutes
LEAKAGE_AMOUNT_THRESHOLD = 150.0  # Rule 2: off-channel transaction > 150 EUR
CORPORATE_DISCOUNT = 0.15         # missed corporate-rate discount


def rule_commuting(eligible_df, budgets):
    """Rule 1: per department, commuting spend vs travel budget."""
    recs = []
    commuting = eligible_df[eligible_df["scope3_category"] == "Category 7"]
    for dept, group in commuting.groupby("department"):
        budget = budgets.get(dept)
        if not budget:
            continue
        spend = group["amount_eur"].sum()
        ratio = spend / budget
        if ratio <= COMMUTE_BUDGET_THRESHOLD:
            continue
        saved_eur = spend * HYBRID_DAY_FRACTION
        saved_co2e = group["co2e_kg"].sum() * HYBRID_DAY_FRACTION
        recs.append({
            "rule": "Rule 1 — Commuting",
            "title": f"Add 1 hybrid work day for {dept}",
            "department": dept,
            "saving_eur": round(saved_eur, 2),
            "saving_co2e_kg": round(saved_co2e, 1),
            "rationale": (
                f"{dept} commuting spend is EUR {spend:,.0f} — "
                f"{ratio:.0%} of its EUR {budget:,.0f} monthly travel budget "
                f"(threshold {COMMUTE_BUDGET_THRESHOLD:.0%}). One additional "
                f"hybrid day removes ~{HYBRID_DAY_FRACTION:.0%} of commutes."
            ),
        })
    return recs


def rule_leakage(eligible_df):
    """Rule 2: off-channel business-travel transactions above the threshold."""
    recs = []
    leaks = eligible_df[
        (eligible_df["leakage_flag"] == 1)
        & (eligible_df["amount_eur"] > LEAKAGE_AMOUNT_THRESHOLD)
    ]
    if leaks.empty:
        return recs
    lost = leaks["amount_eur"].sum() * CORPORATE_DISCOUNT
    recs.append({
        "rule": "Rule 2 — Travel Leakage",
        "title": f"Policy review: {len(leaks)} off-channel bookings over "
                 f"EUR {LEAKAGE_AMOUNT_THRESHOLD:.0f}",
        "department": ", ".join(sorted(leaks["department"].unique())),
        "saving_eur": round(lost, 2),
        "saving_co2e_kg": 0.0,
        "rationale": (
            f"EUR {leaks['amount_eur'].sum():,.0f} of business travel was paid "
            f"on personal cards outside the corporate booking tool, forfeiting "
            f"the ~{CORPORATE_DISCOUNT:.0%} corporate discount. Route these "
            f"bookings through the TMC to recover the saving."
        ),
        "detail": leaks[
            ["transaction_id", "department", "date", "merchant_name", "amount_eur"]
        ].sort_values("amount_eur", ascending=False),
    })
    return recs


def generate_recommendations(eligible_df, budgets):
    if eligible_df.empty:
        return []
    return rule_commuting(eligible_df, budgets) + rule_leakage(eligible_df)
