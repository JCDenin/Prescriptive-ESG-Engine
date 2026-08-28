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
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'analyst',
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES users(username),
    expires_at TEXT NOT NULL
);
"""


def ensure_schema(conn):
    """Idempotent and cheap — safe to call on every rerun. Needed because a
    cached connection can outlive a code update (Streamlit Cloud hot-swaps
    the code without restarting the process), so newly added tables must be
    created on existing connections too."""
    conn.executescript(_SCHEMA)
    ensure_default_users(conn)


def get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    ensure_schema(conn)
    return conn


# --- Accounts & refresh-proof sessions --------------------------------------
# Demo-grade auth: PBKDF2-hashed passwords in SQLite plus opaque session
# tokens (carried in the URL query string) so a browser refresh does not
# log the user out. Not production security — no rate limiting, no HTTPS
# enforcement — but a correct pattern to build on.

SESSION_HOURS = 12

DEFAULT_USERS = [
    # (username, password, display name, role)
    ("admin", "admin", "Administrator", "admin"),
    ("omar", "omar", "Omar", "admin"),
    ("viktor", "viktor", "Viktor", "analyst"),
]


def _hash_password(password, salt=None):
    import hashlib, secrets
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000
    ).hex()
    return salt, digest


def ensure_default_users(conn):
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        for username, password, display_name, role in DEFAULT_USERS:
            create_user(conn, username, password, display_name, role)


def create_user(conn, username, password, display_name, role="analyst"):
    """Returns True on success, False if the username is taken/invalid."""
    from datetime import datetime, timezone
    username = str(username).strip().lower()
    if not username or not password:
        return False
    salt, digest = _hash_password(password)
    try:
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
            (username, str(display_name).strip() or username, role, salt, digest,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(conn, username, password):
    """Returns {username, display_name, role} on valid credentials, else None."""
    row = conn.execute(
        "SELECT username, display_name, role, salt, password_hash"
        " FROM users WHERE username = ?", (str(username).strip().lower(),)
    ).fetchone()
    if row is None:
        return None
    _, digest = _hash_password(password, salt=row[3])
    if digest != row[4]:
        return None
    return {"username": row[0], "display_name": row[1], "role": row[2]}


def create_session(conn, username):
    import secrets
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    conn.execute("DELETE FROM sessions WHERE expires_at < ?",
                 (now.isoformat(timespec="seconds"),))
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?)",
        (token, username,
         (now + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")),
    )
    conn.commit()
    return token


def session_user(conn, token):
    """Returns the user dict for a valid, unexpired session token, else None."""
    from datetime import datetime, timezone
    row = conn.execute(
        "SELECT u.username, u.display_name, u.role, s.expires_at"
        " FROM sessions s JOIN users u USING (username) WHERE s.token = ?",
        (str(token),),
    ).fetchone()
    if row is None or row[3] < datetime.now(timezone.utc).isoformat(timespec="seconds"):
        return None
    return {"username": row[0], "display_name": row[1], "role": row[2]}


def delete_session(conn, token):
    conn.execute("DELETE FROM sessions WHERE token = ?", (str(token),))
    conn.commit()


def list_users(conn):
    return pd.read_sql_query(
        "SELECT username, display_name, role, created_at FROM users ORDER BY username",
        conn,
    )


def delete_user(conn, username):
    conn.execute("DELETE FROM sessions WHERE username = ?", (username,))
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()


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
