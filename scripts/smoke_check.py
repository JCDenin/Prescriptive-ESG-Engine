"""End-to-end smoke check on the planted test cases.

Covers the five logic tests from the team task doc (control trip, leakage
flag, commute pattern, review queue, two-condition rule) plus the MACC rules
against the generated dataset.

Run:  python scripts/smoke_check.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import classification as classifier, database as db, recommendations as recommend  # noqa: E402

# ---- unit cases mirroring the team's 5-row sample --------------------------
sample = pd.DataFrame([
    # TX001 control: approved corporate flight — must not flag
    ("TX001", "EMP_010", "Sales", "2026-06-01", "09:15", "Delta Airlines",
     420.00, "TMC_Corporate", "Business_Trip"),
    # TX002 leakage: hotel on a personal card for a business trip
    ("TX002", "EMP_014", "Engineering", "2026-06-02", "19:40", "Hilton Hotel Berlin",
     210.00, "Personal_Card_Reimbursement", "Business_Trip"),
    # TX003-005 commute: same employee, Metro Paris, ~08:00, 3 days running
    ("TX003", "EMP_022", "Marketing", "2026-06-01", "08:05", "Metro Paris",
     2.10, "Personal_Card_Reimbursement", "Daily_Expense"),
    ("TX004", "EMP_022", "Marketing", "2026-06-02", "08:10", "Metro Paris",
     2.10, "Personal_Card_Reimbursement", "Daily_Expense"),
    ("TX005", "EMP_022", "Marketing", "2026-06-03", "08:02", "Metro Paris",
     2.10, "Personal_Card_Reimbursement", "Daily_Expense"),
    # TX006 unknown merchant: must land in the review queue
    ("TX006", "EMP_031", "Operations", "2026-06-04", "12:30", "Gasthaus Krone",
     54.00, "Personal_Card_Reimbursement", "Daily_Expense"),
], columns=db.CSV_COLUMNS)

out = classifier.classify_transactions(sample).set_index("transaction_id")

assert out.loc["TX001", "leakage_flag"] == 0, "control trip must not flag"
assert out.loc["TX001", "scope3_category"] == "Category 6"
assert out.loc["TX001", "confidence"] > 0.8, "known merchant must auto-classify"

assert out.loc["TX002", "leakage_flag"] == 1, "personal-card business hotel must flag"

for tx in ("TX003", "TX004", "TX005"):
    assert out.loc[tx, "commute_pattern"] == 1, f"{tx} must be a commute pattern"
    assert out.loc[tx, "scope3_category"] == "Category 7"
    # THE critical two-condition rule: commuting on a personal card is normal
    assert out.loc[tx, "leakage_flag"] == 0, f"{tx} must NOT flag as leakage"

assert out.loc["TX006", "confidence"] <= 0.8, "unknown merchant -> low confidence"
assert (out["co2e_kg"] > 0).all(), "every row needs a CO2e estimate"
print("Classifier unit cases: OK")

# ---- full pipeline over the generated dataset ------------------------------
csv_path = Path(__file__).resolve().parent.parent / "data" / "sample_transactions.csv"
raw = pd.read_csv(csv_path, dtype={"time": str, "amount_eur": float})

conn = db.get_conn(":memory:")
db.ingest_transactions(conn, raw)
db.store_classifications(conn, classifier.classify_transactions(raw))

eligible = db.get_eligible(conn)
pending = db.get_pending(conn)
assert len(eligible) + len(pending) == len(raw)
assert len(pending) >= 25, "planted ambiguous merchants must reach the queue"

recs = recommend.generate_recommendations(eligible, db.get_budgets(conn))
rule1_depts = {r["department"] for r in recs if r["rule"].startswith("Rule 1")}
assert {"Engineering", "Marketing"} <= rule1_depts, f"Rule 1 missing: {rule1_depts}"
assert not {"Sales", "Consulting", "Operations"} & rule1_depts
assert any(r["rule"].startswith("Rule 2") for r in recs), "Rule 2 must fire"

# review-queue eligibility: approving a pending row must grow the MACC input
tx_id = pending.iloc[0]["transaction_id"]
db.set_review(conn, tx_id, new_category="transit")
after = db.get_eligible(conn)
assert len(after) == len(eligible) + 1, "approved row must become eligible"
assert after.set_index("transaction_id").loc[tx_id, "review_status"] in ("approved", "corrected")

print(f"Pipeline: {len(raw)} rows -> {len(eligible)} eligible, {len(pending)} pending")
print(f"Recommendations: {[r['title'] for r in recs]}")
print("Smoke check: ALL OK")
