"""SQLite data layer: schema, ingestion, review updates, eligibility queries.

Pure logic module — no Streamlit imports. The MACC engine and the Overview
metrics must both see only rows matching ELIGIBLE_STATUSES, so unreviewed
low-confidence transactions can never influence recommendations.
"""

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "esg.db"

# Monthly travel budgets per department (EUR). Rule 1 of the MACC playbook
# compares commuting spend against these.
DEFAULT_BUDGETS = {
    "Sales": 18000.0,
    "Engineering": 6000.0,
    "Marketing": 4000.0,
    "Consulting": 22000.0,
    "Operations": 6000.0,
}
FALLBACK_BUDGET = 10000.0

# review_status values: 'auto' (confidence > 0.8), 'pending' (needs human
# review), 'approved', 'corrected'. Only these three feed the MACC engine:
ELIGIBLE_STATUSES = ("auto", "approved", "corrected")

CSV_COLUMNS = [
    "transaction_id", "employee_id", "department", "date", "time",
    "merchant_name", "amount_eur", "payment_channel", "expense_context",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
    name TEXT PRIMARY KEY,
    travel_budget_eur REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS employees (
    employee_id TEXT PRIMARY KEY,
    department TEXT NOT NULL REFERENCES departments(name)
);
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    department TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    merchant_name TEXT NOT NULL,
    amount_eur REAL NOT NULL,
    payment_channel TEXT NOT NULL,
    expense_context TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classifications (
    transaction_id TEXT PRIMARY KEY REFERENCES transactions(transaction_id),
    category TEXT NOT NULL,
    scope3_category TEXT NOT NULL,
    confidence REAL NOT NULL,
    co2e_kg REAL NOT NULL,
    leakage_flag INTEGER NOT NULL DEFAULT 0,
    commute_pattern INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL,
    reviewed_category TEXT
);
"""


def get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.executescript(_SCHEMA)
    return conn


def ingest_transactions(conn, df):
    """Replace all stored data with the given raw transaction dataframe."""
    df = df[CSV_COLUMNS].copy()
    df["amount_eur"] = pd.to_numeric(df["amount_eur"], errors="coerce").fillna(0.0)

    conn.execute("DELETE FROM classifications")
    conn.execute("DELETE FROM transactions")
    conn.execute("DELETE FROM employees")
    conn.execute("DELETE FROM departments")

    for dept in sorted(df["department"].unique()):
        conn.execute(
            "INSERT INTO departments (name, travel_budget_eur) VALUES (?, ?)",
            (str(dept), DEFAULT_BUDGETS.get(dept, FALLBACK_BUDGET)),
        )
    employees = df[["employee_id", "department"]].drop_duplicates("employee_id")
    conn.executemany(
        "INSERT INTO employees (employee_id, department) VALUES (?, ?)",
        [(str(r.employee_id), str(r.department)) for r in employees.itertuples(index=False)],
    )
    # Bind plain Python types only: depending on the pandas/numpy version,
    # itertuples can yield numpy/arrow scalars that sqlite3 refuses
    # (InterfaceError on Streamlit Cloud, while the same code passes locally).
    conn.executemany(
        "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                str(r.transaction_id), str(r.employee_id), str(r.department),
                str(r.date), str(r.time), str(r.merchant_name),
                float(r.amount_eur), str(r.payment_channel), str(r.expense_context),
            )
            for r in df.itertuples(index=False)
        ],
    )
    conn.commit()


def store_classifications(conn, df):
    """Store classifier output. Expects columns: transaction_id, category,
    scope3_category, confidence, co2e_kg, leakage_flag, commute_pattern."""
    rows = [
        (
            str(r.transaction_id), str(r.category), str(r.scope3_category),
            float(r.confidence), float(r.co2e_kg), int(r.leakage_flag),
            int(r.commute_pattern),
            "auto" if r.confidence > 0.8 else "pending", None,
        )
        for r in df.itertuples(index=False)
    ]
    conn.execute("DELETE FROM classifications")
    conn.executemany(
        "INSERT INTO classifications VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    conn.commit()


def _joined_query(where=""):
    return f"""
        SELECT t.*, c.category, c.scope3_category, c.confidence, c.co2e_kg,
               c.leakage_flag, c.commute_pattern, c.review_status,
               c.reviewed_category
        FROM transactions t JOIN classifications c USING (transaction_id)
        {where}
    """


def get_eligible(conn):
    """All transactions allowed to feed metrics and the MACC engine."""
    placeholders = ",".join("?" * len(ELIGIBLE_STATUSES))
    return pd.read_sql_query(
        _joined_query(f"WHERE c.review_status IN ({placeholders})"),
        conn, params=ELIGIBLE_STATUSES,
    )


def get_pending(conn):
    return pd.read_sql_query(
        _joined_query("WHERE c.review_status = 'pending' ORDER BY t.date, t.time"),
        conn,
    )


def get_all(conn):
    return pd.read_sql_query(_joined_query(), conn)


def get_budgets(conn):
    return dict(conn.execute("SELECT name, travel_budget_eur FROM departments"))


def has_data(conn):
    return conn.execute("SELECT COUNT(*) FROM classifications").fetchone()[0] > 0


def set_review(conn, transaction_id, new_category=None):
    """Approve a pending transaction; if new_category differs, mark it
    corrected, re-derive scope and recompute its CO2e."""
    from src import classification as classifier, emissions

    row = conn.execute(
        "SELECT c.category, t.amount_eur, t.payment_channel, t.expense_context"
        " FROM classifications c JOIN transactions t USING (transaction_id)"
        " WHERE c.transaction_id = ?",
        (transaction_id,),
    ).fetchone()
    if row is None:
        return
    old_category, amount, channel, context = row

    category = new_category or old_category
    status = "corrected" if category != old_category else "approved"
    scope3 = classifier.scope3_for(category, context)
    leakage = int(classifier.is_leakage(category, channel, context))
    co2e = emissions.co2e_kg(category, amount)
    conn.execute(
        "UPDATE classifications SET review_status = ?, reviewed_category = ?,"
        " category = ?, scope3_category = ?, leakage_flag = ?, co2e_kg = ?"
        " WHERE transaction_id = ?",
        (status, category, category, scope3, leakage, co2e, transaction_id),
    )
    conn.commit()
