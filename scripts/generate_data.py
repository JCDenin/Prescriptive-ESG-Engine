"""Generate the synthetic transaction dataset (100 employees, June 2026).

Planted cohorts, so every demo number is known in advance:
  1. Control: normal TMC-booked business trips (must NOT flag)
  2. Category 6 leakage: personal-card business travel, amounts bimodal
     around the EUR 150 Rule-2 threshold
  3. Category 7 commuters: recurring morning transit/rideshare charges,
     concentrated in Engineering and Marketing so Rule 1 trips there
  4. Ambiguous merchants: populate the human-in-the-loop review queue
  5. Noise: everyday meals/office spend

Run:  python scripts/generate_data.py
"""

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.database import DEFAULT_BUDGETS  # noqa: E402

random.seed(42)

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_transactions.csv"

DEPARTMENTS = {
    "Sales": 25,
    "Engineering": 30,
    "Marketing": 15,
    "Consulting": 20,
    "Operations": 10,
}

WEEKDAYS = [
    d for d in (date(2026, 6, 1) + timedelta(n) for n in range(30))
    if d.weekday() < 5
]

TRANSIT_MERCHANTS = ["Metro Paris", "BVG", "MVV", "Wiener Linien"]
RIDESHARE_MERCHANTS = ["Uber BV", "Bolt Operations OU", "Free Now"]
FLIGHT_MERCHANTS = ["Lufthansa", "Air France", "KLM", "Delta Airlines", "Ryanair"]
HOTEL_MERCHANTS = ["Hilton Hotel Berlin", "Marriott Muenchen", "Ibis Paris Est", "Motel One Wien"]
RAIL_MERCHANTS = ["Deutsche Bahn", "SNCF", "Eurostar"]
FOOD_MERCHANTS = ["Starbucks", "Vapiano", "Pret A Manger", "REWE Markt", "Restaurant Adler"]
OFFICE_MERCHANTS = ["Office Depot", "Staples"]
AMBIGUOUS_MERCHANTS = [
    "Cafe Zentral GmbH", "City Parkhaus 24", "K+M Mobility Services",
    "Blue Line Shuttle", "Global Conf Services Ltd", "Snack Automat 77",
    "Hbf Kiosk", "QuickPark Flughafen", "TravelPlus Agentur", "Gasthaus Krone",
]

rows = []


def add(employee, dept, day, hh, mm, merchant, amount, channel, context):
    rows.append({
        "employee_id": employee,
        "department": dept,
        "date": day.isoformat(),
        "time": f"{hh:02d}:{mm:02d}",
        "merchant_name": merchant,
        "amount_eur": f"{amount:.2f}",
        "payment_channel": channel,
        "expense_context": context,
    })


# ---- employees -------------------------------------------------------------
employees = []
i = 1
for dept, count in DEPARTMENTS.items():
    for _ in range(count):
        employees.append((f"EMP_{i:03d}", dept))
        i += 1
by_dept = {d: [e for e, dd in employees if dd == d] for d in DEPARTMENTS}

# ---- cohort 3: commuters (Category 7) --------------------------------------
# (transit_commuters, rideshare_commuters) per department — Engineering and
# Marketing are planted above Rule 1's 30%-of-budget threshold.
commuter_mix = {
    "Engineering": (15, 12),
    "Marketing": (8, 5),
    "Sales": (4, 0),
    "Consulting": (3, 0),
    "Operations": (2, 0),
}
commute_spend = dict.fromkeys(DEPARTMENTS, 0.0)
for dept, (n_transit, n_ride) in commuter_mix.items():
    pool = random.sample(by_dept[dept], n_transit + n_ride)
    for idx, emp in enumerate(pool):
        transit = idx < n_transit
        merchant = random.choice(TRANSIT_MERCHANTS if transit else RIDESHARE_MERCHANTS)
        base_hh, base_mm = 8, random.randint(0, 45)
        for day in WEEKDAYS:
            if random.random() > 0.75:   # not every weekday (hybrid reality)
                continue
            amount = random.uniform(2.0, 3.6) if transit else random.uniform(9.0, 15.0)
            mm = max(0, min(59, base_mm + random.randint(-6, 6)))
            add(emp, dept, day, base_hh, mm, merchant, amount,
                "Personal_Card_Reimbursement", "Daily_Expense")
            commute_spend[dept] += amount

# ---- cohort 1: control business trips (TMC, no flags) ----------------------
travelers = random.sample(by_dept["Sales"], 8) + random.sample(by_dept["Consulting"], 8)
for _ in range(30):
    emp = random.choice(travelers)
    dept = dict(employees)[emp]
    day = random.choice(WEEKDAYS)
    kind = random.random()
    if kind < 0.4:
        merchant, amount = random.choice(FLIGHT_MERCHANTS), random.uniform(180, 620)
    elif kind < 0.75:
        merchant, amount = random.choice(HOTEL_MERCHANTS), random.uniform(95, 260)
    else:
        merchant, amount = random.choice(RAIL_MERCHANTS), random.uniform(40, 130)
    add(emp, dept, day, random.randint(6, 20), random.randint(0, 59),
        merchant, amount, "TMC_Corporate", "Business_Trip")

# ---- cohort 2: Category 6 leakage (personal card + business trip) ----------
leakers = random.sample(by_dept["Sales"], 6) + random.sample(by_dept["Engineering"], 4)
for n in range(25):
    emp = random.choice(leakers)
    dept = dict(employees)[emp]
    day = random.choice(WEEKDAYS)
    merchant = random.choice(HOTEL_MERCHANTS + RIDESHARE_MERCHANTS + ["Airbnb Payments", "Ryanair"])
    # bimodal: roughly half below the EUR 150 Rule-2 bar, half above
    amount = random.uniform(35, 140) if n % 2 else random.uniform(160, 430)
    add(emp, dept, day, random.randint(7, 22), random.randint(0, 59),
        merchant, amount, "Personal_Card_Reimbursement", "Business_Trip")

# ---- cohort 4: ambiguous merchants (review queue) --------------------------
for _ in range(30):
    emp, dept = random.choice(employees)
    day = random.choice(WEEKDAYS)
    context = random.choice(["Business_Trip", "Daily_Expense"])
    channel = ("Personal_Card_Reimbursement" if context == "Daily_Expense"
               else random.choice(["TMC_Corporate", "Personal_Card_Reimbursement"]))
    add(emp, dept, day, random.randint(7, 21), random.randint(0, 59),
        random.choice(AMBIGUOUS_MERCHANTS), random.uniform(6, 220), channel, context)

# ---- cohort 5: noise (meals, office) ---------------------------------------
for _ in range(1200):
    emp, dept = random.choice(employees)
    day = random.choice(WEEKDAYS)
    merchant = random.choice(FOOD_MERCHANTS * 4 + OFFICE_MERCHANTS)
    amount = random.uniform(4, 38) if merchant in FOOD_MERCHANTS else random.uniform(10, 90)
    add(emp, dept, day, random.randint(11, 19), random.randint(0, 59),
        merchant, amount, "Personal_Card_Reimbursement", "Daily_Expense")

# ---- write CSV -------------------------------------------------------------
rows.sort(key=lambda r: (r["date"], r["time"]))
for n, row in enumerate(rows, start=1):
    row["transaction_id"] = f"TX{n:04d}"

OUT_PATH.parent.mkdir(exist_ok=True)
fieldnames = ["transaction_id", "employee_id", "department", "date", "time",
              "merchant_name", "amount_eur", "payment_channel", "expense_context"]
with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} transactions for {len(employees)} employees -> {OUT_PATH}")
print("\nPlanted commuting spend vs monthly travel budget (Rule 1 fires above 30%):")
for dept in DEPARTMENTS:
    budget = DEFAULT_BUDGETS[dept]
    ratio = commute_spend[dept] / budget
    marker = "  <-- Rule 1 fires" if ratio > 0.30 else ""
    print(f"  {dept:<12} EUR {commute_spend[dept]:8,.0f} / {budget:8,.0f}  ({ratio:5.0%}){marker}")
