"""Monte Carlo transaction simulator.

Generates realistic corporate expense datasets by sampling from probability
distributions instead of fixed planted patterns:

1. A "world" is drawn first — commuter share, rideshare adoption, travel
   intensity, off-channel leakage probability, unknown-merchant rate,
   attendance — each from a prior range. Every run therefore produces a
   different but plausible company.
2. Employee behavior profiles are sampled from the world (who commutes, by
   what mode, who travels), then day-by-day transactions are simulated:
   commute times ~ Normal around a personal morning habit, amounts ~
   log-normal per category, business trips as flight/rail + hotel + taxi
   bundles, booked off-channel with the world's leakage probability.

Same seed -> same dataset (reproducible for tests); no seed -> a fresh world
every time (Monte Carlo mode for stress-testing and the jury demo).
"""

import random
from datetime import date, timedelta

import pandas as pd

DEPARTMENT_WEIGHTS = {
    "Sales": 0.25, "Engineering": 0.30, "Marketing": 0.15,
    "Consulting": 0.20, "Operations": 0.10,
}

TRANSIT = ["Metro Paris", "BVG", "MVV", "Wiener Linien", "RATP"]
RIDESHARE = ["Uber BV", "Bolt Operations OU", "Free Now"]
FLIGHTS = ["Lufthansa", "Air France", "KLM", "Delta Airlines", "Ryanair", "EasyJet"]
HOTELS = ["Hilton Hotel Berlin", "Marriott Muenchen", "Ibis Paris Est",
          "Motel One Wien", "Novotel Amsterdam", "Airbnb Payments"]
RAIL = ["Deutsche Bahn", "SNCF", "Eurostar", "Trenitalia"]
FOOD = ["Starbucks", "Vapiano", "Pret A Manger", "REWE Markt", "Restaurant Adler"]
OFFICE = ["Office Depot", "Staples"]
UNKNOWN = ["Cafe Zentral GmbH", "City Parkhaus 24", "K+M Mobility Services",
           "Blue Line Shuttle", "Global Conf Services Ltd", "Snack Automat 77",
           "Hbf Kiosk", "QuickPark Flughafen", "TravelPlus Agentur",
           "Gasthaus Krone", "Stadtwerke Payment", "Kantine Nord"]


def sample_world(rng):
    """Draw the company-level parameters (the Monte Carlo priors)."""
    return {
        "commuter_share": rng.uniform(0.35, 0.65),
        "rideshare_adoption": rng.uniform(0.10, 0.35),
        "traveler_share": rng.uniform(0.10, 0.30),
        "trip_prob_per_day": rng.uniform(0.02, 0.06),
        "leakage_prob": rng.uniform(0.05, 0.20),
        "unknown_merchant_prob": rng.uniform(0.01, 0.04),
        "attendance_rate": rng.uniform(0.55, 0.80),
        "months": rng.choice([1, 2, 3]),
    }


def _lognormal(rng, median, sigma, lo, hi):
    import math
    return round(min(hi, max(lo, rng.lognormvariate(math.log(median), sigma))), 2)


def simulate(n_rows=10000, seed=None, world=None):
    """Returns (df, params). df has the 9 standard CSV columns; params
    documents the sampled world so a run is explainable to a jury."""
    if seed is None:
        seed = random.randrange(1_000_000)
    rng = random.Random(seed)
    world = dict(world) if world else sample_world(rng)

    start = date(2026, 6, 1)
    days = [start + timedelta(d) for d in range(world["months"] * 30)
            if (start + timedelta(d)).weekday() < 5]

    # Size the workforce so the period overshoots n_rows, then sample down.
    approx_rows_per_emp_day = (
        world["attendance_rate"] * (world["commuter_share"] * 1.8 + 0.6 + 0.03)
        + world["traveler_share"] * world["trip_prob_per_day"] * 3.5
    )
    n_emp = max(40, int(n_rows * 1.3 / (len(days) * approx_rows_per_emp_day)))

    depts, weights = zip(*DEPARTMENT_WEIGHTS.items())
    employees = [(f"EMP_{i + 1:04d}", rng.choices(depts, weights)[0])
                 for i in range(n_emp)]
    profiles = {}
    for emp, _ in employees:
        rideshare = rng.random() < world["rideshare_adoption"]
        profiles[emp] = {
            "commuter": rng.random() < world["commuter_share"],
            "traveler": rng.random() < world["traveler_share"],
            "commute_merchant": rng.choice(RIDESHARE if rideshare else TRANSIT),
            "commute_cost": (_lognormal(rng, 12, 0.3, 6, 30) if rideshare
                             else round(rng.uniform(2.0, 3.8), 2)),
            "habit_minute": rng.randint(-45, 55),  # personal offset from 08:00
        }

    rows = []

    def add(emp, dept, day, hh, mm, merchant, amount, channel, context):
        if rng.random() < world["unknown_merchant_prob"]:
            merchant = rng.choice(UNKNOWN)
        rows.append((emp, dept, day.isoformat(),
                     f"{max(0, min(23, hh)):02d}:{max(0, min(59, mm)):02d}",
                     merchant, round(amount, 2), channel, context))

    for day in days:
        for emp, dept in employees:
            p = profiles[emp]
            attends = rng.random() < world["attendance_rate"]
            if attends and p["commuter"]:
                m = int(rng.gauss(p["habit_minute"], 22))
                hh, mm = 8 + m // 60, m % 60
                add(emp, dept, day, hh, mm, p["commute_merchant"],
                    p["commute_cost"] * rng.uniform(0.9, 1.1),
                    "Personal_Card_Reimbursement", "Daily_Expense")
                if rng.random() < 0.8:  # evening return
                    add(emp, dept, day, rng.randint(17, 19), rng.randint(0, 59),
                        p["commute_merchant"], p["commute_cost"] * rng.uniform(0.9, 1.1),
                        "Personal_Card_Reimbursement", "Daily_Expense")
            if attends and rng.random() < 0.6:  # lunch
                add(emp, dept, day, rng.randint(11, 14), rng.randint(0, 59),
                    rng.choice(FOOD), _lognormal(rng, 13, 0.5, 4, 60),
                    "Personal_Card_Reimbursement", "Daily_Expense")
            if rng.random() < 0.03:  # office supplies
                add(emp, dept, day, rng.randint(9, 17), rng.randint(0, 59),
                    rng.choice(OFFICE), _lognormal(rng, 30, 0.6, 8, 200),
                    "Personal_Card_Reimbursement", "Daily_Expense")
            if p["traveler"] and rng.random() < world["trip_prob_per_day"]:
                # Business trip bundle; off-channel with leakage probability.
                off_channel = rng.random() < world["leakage_prob"]
                channel = ("Personal_Card_Reimbursement" if off_channel
                           else "TMC_Corporate")
                if rng.random() < 0.7:
                    add(emp, dept, day, rng.randint(6, 20), rng.randint(0, 59),
                        rng.choice(FLIGHTS), _lognormal(rng, 280, 0.5, 80, 1500),
                        channel, "Business_Trip")
                else:
                    add(emp, dept, day, rng.randint(6, 20), rng.randint(0, 59),
                        rng.choice(RAIL), _lognormal(rng, 70, 0.5, 25, 350),
                        channel, "Business_Trip")
                for night in range(rng.randint(1, 3)):
                    add(emp, dept, day + timedelta(night), rng.randint(15, 22),
                        rng.randint(0, 59), rng.choice(HOTELS),
                        _lognormal(rng, 140, 0.4, 60, 600), channel, "Business_Trip")
                for _ in range(rng.randint(0, 2)):
                    add(emp, dept, day, rng.randint(7, 22), rng.randint(0, 59),
                        rng.choice(RIDESHARE), _lognormal(rng, 16, 0.6, 5, 90),
                        channel, "Business_Trip")

    if len(rows) > n_rows:
        rows = rng.sample(rows, n_rows)
    rows.sort(key=lambda r: (r[2], r[3]))

    df = pd.DataFrame(rows, columns=[
        "employee_id", "department", "date", "time", "merchant_name",
        "amount_eur", "payment_channel", "expense_context",
    ])
    df.insert(0, "transaction_id", [f"TX{i + 1:05d}" for i in range(len(df))])

    params = {"seed": seed, "n_rows": len(df), "n_employees": n_emp,
              "period_days": len(days),
              **{k: (round(v, 3) if isinstance(v, float) else v)
                 for k, v in world.items()}}
    return df, params
