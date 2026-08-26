# =============================================================================
#  STUB MODULE - TO BE REPLACED BY VIKTOR (Classification Engine workstream)
# =============================================================================
#  This is Omar's minimal stand-in so the dashboard runs end-to-end. Viktor:
#  replace the internals with the real engine (Regex + merchant dictionary +
#  distilroberta NLP for free-text fields) but KEEP the contract identical:
#
#      classify_transactions(df) -> df  with added columns:
#          category, scope3_category, confidence, leakage_flag,
#          commute_pattern, co2e_kg
#
#  Everything downstream (review queue, overview metrics, MACC engine) only
#  depends on that contract. Acceptance checks: scripts/smoke_check.py —
#  including the critical two-condition Category 6 rule
#  (Personal_Card_Reimbursement AND Business_Trip, never channel alone).
# =============================================================================

"""Stub transaction classifier — stand-in for Viktor's classification engine.

Contract (keep stable so Viktor's engine can drop in):
    classify_transactions(df) -> df with added columns
        category         merchant category (flight/hotel/transit/...)
        scope3_category  'Category 6' | 'Category 7' | 'Out of scope'
        confidence       0..1 (confidence > 0.8 auto-classifies, else review)
        leakage_flag     1 if Cat 6 off-channel leakage
        commute_pattern  1 if part of a recurring commute pattern
        co2e_kg          spend-based emissions estimate

Input df must have the 9 raw CSV columns (see esg.db.CSV_COLUMNS).
"""

import pandas as pd

from src import emissions

# Merchant dictionary: lowercase keyword -> category. One rule covers every
# transaction of that merchant (merchant-category level, per the MVP brief).
MERCHANT_DICT = {
    "lufthansa": "flight",
    "air france": "flight",
    "klm": "flight",
    "ryanair": "flight",
    "easyjet": "flight",
    "delta airlines": "flight",
    "deutsche bahn": "rail",
    "sncf": "rail",
    "eurostar": "rail",
    "trenitalia": "rail",
    "metro paris": "transit",
    "ratp": "transit",
    "bvg": "transit",
    "mvv": "transit",
    "wiener linien": "transit",
    "transport for london": "transit",
    "uber": "rideshare",
    "bolt": "rideshare",
    "free now": "rideshare",
    "taxi": "rideshare",
    "hilton": "hotel",
    "marriott": "hotel",
    "ibis": "hotel",
    "novotel": "hotel",
    "motel one": "hotel",
    "airbnb": "hotel",
    "sixt": "car_rental",
    "europcar": "car_rental",
    "shell": "fuel",
    "aral": "fuel",
    "total energies": "fuel",
    "starbucks": "food",
    "vapiano": "food",
    "pret a manger": "food",
    "restaurant": "food",
    "rewe": "food",
    "office depot": "office",
    "staples": "office",
}

TRAVEL_CATEGORIES = {"flight", "rail", "hotel", "rideshare", "car_rental", "transit", "fuel"}
COMMUTE_CATEGORIES = {"transit", "rideshare", "rail", "fuel"}

CONF_EXACT = 0.95
CONF_PARTIAL = 0.85
CONF_UNKNOWN = 0.40

COMMUTE_START, COMMUTE_END = 7, 9   # 07:00–09:59
COMMUTE_MIN_DAYS = 3


def match_merchant(merchant_name):
    """Return (category, confidence) for a raw merchant string."""
    name = str(merchant_name).strip().lower()
    if name in MERCHANT_DICT:
        return MERCHANT_DICT[name], CONF_EXACT
    for keyword, category in MERCHANT_DICT.items():
        if keyword in name:
            return category, CONF_PARTIAL
    return "unknown", CONF_UNKNOWN


def is_leakage(category, payment_channel, expense_context):
    """Category 6 leakage requires BOTH conditions (critical team rule):
    a personal-card payment alone is normal for commuting and must not flag."""
    return (
        payment_channel == "Personal_Card_Reimbursement"
        and expense_context == "Business_Trip"
        and category in TRAVEL_CATEGORIES | {"unknown"}
    )


def scope3_for(category, expense_context):
    if expense_context == "Business_Trip" and category in TRAVEL_CATEGORIES:
        return "Category 6"
    if expense_context == "Daily_Expense" and category in COMMUTE_CATEGORIES:
        return "Category 7"
    return "Out of scope"


def _commute_hour(time_str):
    try:
        return COMMUTE_START <= int(str(time_str)[:2]) <= COMMUTE_END
    except ValueError:
        return False


def classify_transactions(df):
    df = df.copy()

    matched = df["merchant_name"].map(match_merchant)
    df["category"] = matched.map(lambda m: m[0])
    df["confidence"] = matched.map(lambda m: m[1])

    df["scope3_category"] = [
        scope3_for(cat, ctx)
        for cat, ctx in zip(df["category"], df["expense_context"])
    ]
    df["leakage_flag"] = [
        int(is_leakage(cat, ch, ctx))
        for cat, ch, ctx in zip(df["category"], df["payment_channel"], df["expense_context"])
    ]

    # Category 7 commute pattern: same employee + same merchant, commute-hour
    # daily-expense transit, recurring on >= COMMUTE_MIN_DAYS distinct dates.
    candidate = (
        df["category"].isin(COMMUTE_CATEGORIES)
        & (df["expense_context"] == "Daily_Expense")
        & df["time"].map(_commute_hour)
    )
    cand = df[candidate]
    recurring_days = cand.groupby(["employee_id", "merchant_name"])["date"].transform("nunique")
    recurring_index = cand.index[recurring_days >= COMMUTE_MIN_DAYS]
    df["commute_pattern"] = 0
    df.loc[recurring_index, "commute_pattern"] = 1

    df["co2e_kg"] = [
        emissions.co2e_kg(cat, amt)
        for cat, amt in zip(df["category"], df["amount_eur"])
    ]
    return df
