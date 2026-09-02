"""SQLite data layer: schema, dataset history, ingestion, review workflow,
accounts/sessions, audit log.

Pure logic module — no Streamlit imports. Key invariants:
- The MACC engine and Overview metrics only see rows matching
  ELIGIBLE_STATUSES, so unreviewed low-confidence transactions can never
  influence recommendations.
- Every upload creates a new DATASET instead of overwriting data; exactly one
  dataset is active at a time and all queries are scoped to it, so the team
  can switch back to any earlier processed dataset (with its review state).
- Reviews are stamped with reviewer + timestamp, and notable actions land in
  an audit log (pattern ported from the NanoMedical Lab_Webapp AuditLog:
  username snapshot, no FK, action strings).
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
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    source_file TEXT,
    uploaded_by TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    n_rows INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    dataset_id INTEGER NOT NULL REFERENCES datasets(dataset_id),
    transaction_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    department TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    merchant_name TEXT NOT NULL,
    amount_eur REAL NOT NULL,
    payment_channel TEXT NOT NULL,
    expense_context TEXT NOT NULL,
    PRIMARY KEY (dataset_id, transaction_id)
);
CREATE TABLE IF NOT EXISTS classifications (
    dataset_id INTEGER NOT NULL,
    transaction_id TEXT NOT NULL,
    category TEXT NOT NULL,
    scope3_category TEXT NOT NULL,
    confidence REAL NOT NULL,
    co2e_kg REAL NOT NULL,
    leakage_flag INTEGER NOT NULL DEFAULT 0,
    commute_pattern INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL,
    reviewed_category TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    PRIMARY KEY (dataset_id, transaction_id)
);
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'analyst',
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES users(username),
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_id TEXT,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at);
"""


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_schema(conn):
    """Idempotent and cheap — safe to call on every rerun. Needed because a
    cached connection can outlive a code update (Streamlit Cloud hot-swaps
    the code without restarting the process). Legacy pre-dataset tables are
    dropped and recreated (demo data is regenerable in one click)."""
    tx_cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)")]
    if tx_cols and "dataset_id" not in tx_cols:
        conn.executescript(
            "DROP TABLE IF EXISTS classifications; DROP TABLE IF EXISTS transactions;"
        )
    cl_cols = [r[1] for r in conn.execute("PRAGMA table_info(classifications)")]
    if cl_cols and "reviewed_by" not in cl_cols:
        conn.executescript("DROP TABLE IF EXISTS classifications;")
    u_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
    migrate_pw_flag = bool(u_cols) and "must_change_password" not in u_cols
    if migrate_pw_flag:
        conn.execute(
            "ALTER TABLE users ADD COLUMN must_change_password"
            " INTEGER NOT NULL DEFAULT 0"
        )
    conn.executescript(_SCHEMA)
    ensure_default_users(conn)
    if migrate_pw_flag:
        # One-shot: accounts still using their seeded default password must
        # change it on next sign-in (ported from Lab_Webapp mustChangePassword).
        for username, password, _, _, must_change in DEFAULT_USERS:
            if must_change and verify_user(conn, username, password):
                conn.execute(
                    "UPDATE users SET must_change_password = 1 WHERE username = ?",
                    (username,),
                )
        conn.commit()


def get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    ensure_schema(conn)
    return conn


# --- Audit log ---------------------------------------------------------------

def log_action(conn, username, action, summary, entity_id=None):
    conn.execute(
        "INSERT INTO audit_log (username, action, entity_id, summary, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (str(username), str(action), entity_id, str(summary), _utcnow()),
    )
    conn.commit()


def get_audit_log(conn, limit=200):
    return pd.read_sql_query(
        "SELECT created_at, username, action, summary FROM audit_log"
        " ORDER BY id DESC LIMIT ?", conn, params=(int(limit),),
    )


# --- Dataset history ---------------------------------------------------------

def create_dataset(conn, label, source_file, uploaded_by, n_rows):
    cur = conn.execute(
        "INSERT INTO datasets (label, source_file, uploaded_by, uploaded_at,"
        " n_rows, is_active) VALUES (?, ?, ?, ?, ?, 0)",
        (str(label), source_file, str(uploaded_by), _utcnow(), int(n_rows)),
    )
    dataset_id = cur.lastrowid
    _set_active(conn, dataset_id)
    return dataset_id


def _set_active(conn, dataset_id):
    conn.execute("UPDATE datasets SET is_active = 0")
    conn.execute("UPDATE datasets SET is_active = 1 WHERE dataset_id = ?",
                 (int(dataset_id),))
    conn.commit()


def activate_dataset(conn, dataset_id, username="system"):
    _set_active(conn, dataset_id)
    log_action(conn, username, "dataset.activate",
               f"Switched active dataset to #{dataset_id}", str(dataset_id))


def active_dataset_id(conn):
    row = conn.execute(
        "SELECT dataset_id FROM datasets WHERE is_active = 1"
    ).fetchone()
    return row[0] if row else None


def list_datasets(conn):
    return pd.read_sql_query(
        "SELECT dataset_id, label, source_file, uploaded_by, uploaded_at,"
        " n_rows, is_active FROM datasets ORDER BY dataset_id DESC", conn,
    )


def delete_dataset(conn, dataset_id, username="system"):
    conn.execute("DELETE FROM classifications WHERE dataset_id = ?", (int(dataset_id),))
    conn.execute("DELETE FROM transactions WHERE dataset_id = ?", (int(dataset_id),))
    conn.execute("DELETE FROM datasets WHERE dataset_id = ?", (int(dataset_id),))
    conn.commit()
    log_action(conn, username, "dataset.delete", f"Deleted dataset #{dataset_id}",
               str(dataset_id))


# --- Ingestion ---------------------------------------------------------------

def ingest_transactions(conn, df, label="dataset", source_file=None,
                        uploaded_by="system"):
    """Store a raw transaction dataframe as a NEW dataset (history preserved)
    and make it active. Returns the dataset_id."""
    df = df[CSV_COLUMNS].copy()
    df["amount_eur"] = pd.to_numeric(df["amount_eur"], errors="coerce").fillna(0.0)

    dataset_id = create_dataset(conn, label, source_file, uploaded_by, len(df))

    for dept in sorted(df["department"].unique()):
        conn.execute(
            "INSERT OR IGNORE INTO departments (name, travel_budget_eur) VALUES (?, ?)",
            (str(dept), DEFAULT_BUDGETS.get(dept, FALLBACK_BUDGET)),
        )
    conn.executemany(
        "INSERT OR REPLACE INTO employees (employee_id, department) VALUES (?, ?)",
        [(str(r.employee_id), str(r.department))
         for r in df[["employee_id", "department"]].drop_duplicates("employee_id").itertuples(index=False)],
    )
    # Bind plain Python types only: depending on the pandas/numpy version,
    # itertuples can yield numpy/arrow scalars that sqlite3 refuses.
    conn.executemany(
        "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                dataset_id,
                str(r.transaction_id), str(r.employee_id), str(r.department),
                str(r.date), str(r.time), str(r.merchant_name),
                float(r.amount_eur), str(r.payment_channel), str(r.expense_context),
            )
            for r in df.itertuples(index=False)
        ],
    )
    conn.commit()
    log_action(conn, uploaded_by, "data.upload",
               f"Ingested dataset #{dataset_id} '{label}' ({len(df)} rows)",
               str(dataset_id))
    return dataset_id


def store_classifications(conn, df, dataset_id=None):
    """Store classifier output for a dataset (defaults to the active one).
    Expects columns: transaction_id, category, scope3_category, confidence,
    co2e_kg, leakage_flag, commute_pattern."""
    dataset_id = dataset_id if dataset_id is not None else active_dataset_id(conn)
    rows = [
        (
            int(dataset_id), str(r.transaction_id), str(r.category),
            str(r.scope3_category), float(r.confidence), float(r.co2e_kg),
            int(r.leakage_flag), int(r.commute_pattern),
            "auto" if r.confidence > 0.8 else "pending", None, None, None,
        )
        for r in df.itertuples(index=False)
    ]
    conn.execute("DELETE FROM classifications WHERE dataset_id = ?", (int(dataset_id),))
    conn.executemany(
        "INSERT INTO classifications VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


# --- Queries (always scoped to the active dataset) ---------------------------

def _joined_query(where=""):
    return f"""
        SELECT t.*, c.category, c.scope3_category, c.confidence, c.co2e_kg,
               c.leakage_flag, c.commute_pattern, c.review_status,
               c.reviewed_category, c.reviewed_by, c.reviewed_at
        FROM transactions t
        JOIN classifications c
          ON c.dataset_id = t.dataset_id
         AND c.transaction_id = t.transaction_id
        WHERE t.dataset_id = (SELECT dataset_id FROM datasets WHERE is_active = 1)
        {where}
    """


def get_eligible(conn):
    """All transactions allowed to feed metrics and the MACC engine."""
    placeholders = ",".join("?" * len(ELIGIBLE_STATUSES))
    return pd.read_sql_query(
        _joined_query(f"AND c.review_status IN ({placeholders})"),
        conn, params=ELIGIBLE_STATUSES,
    )


def get_pending(conn):
    return pd.read_sql_query(
        _joined_query("AND c.review_status = 'pending' ORDER BY t.date, t.time"),
        conn,
    )


def get_all(conn):
    return pd.read_sql_query(_joined_query(), conn)


def get_budgets(conn):
    return dict(conn.execute("SELECT name, travel_budget_eur FROM departments"))


def has_data(conn):
    ds = active_dataset_id(conn)
    if ds is None:
        return False
    return conn.execute(
        "SELECT COUNT(*) FROM classifications WHERE dataset_id = ?", (ds,)
    ).fetchone()[0] > 0


# --- Human-in-the-loop review ------------------------------------------------

def set_review(conn, transaction_id, new_category=None, reviewed_by="system"):
    """Approve a pending transaction in the active dataset; if new_category
    differs, mark it corrected, re-derive scope and recompute its CO2e.
    Stamps reviewer and timestamp (audit requirement)."""
    from src import classification as classifier, emissions

    ds = active_dataset_id(conn)
    row = conn.execute(
        "SELECT c.category, t.amount_eur, t.payment_channel, t.expense_context"
        " FROM classifications c JOIN transactions t"
        "   ON t.dataset_id = c.dataset_id AND t.transaction_id = c.transaction_id"
        " WHERE c.dataset_id = ? AND c.transaction_id = ?",
        (ds, transaction_id),
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
        " category = ?, scope3_category = ?, leakage_flag = ?, co2e_kg = ?,"
        " reviewed_by = ?, reviewed_at = ?"
        " WHERE dataset_id = ? AND transaction_id = ?",
        (status, category, category, scope3, leakage, co2e,
         str(reviewed_by), _utcnow(), ds, transaction_id),
    )
    conn.commit()
    log_action(conn, reviewed_by, "review.approve",
               f"{status} {transaction_id} as '{category}'", str(transaction_id))


# --- Accounts & refresh-proof sessions --------------------------------------
# Demo-grade auth: PBKDF2-hashed passwords in SQLite plus opaque session
# tokens (carried in the URL query string) so a browser refresh does not
# log the user out. Not production security — no rate limiting, no HTTPS
# enforcement — but a correct pattern to build on.

SESSION_HOURS = 12

# Roles: every team member can do everything (upload, review, datasets,
# reports); 'admin' additionally manages accounts in the Team Accounts tab;
# 'guest' (for the jury) uses the product fully but does not see the
# internal review/audit trail.
DEFAULT_USERS = [
    # (username, password, display name, role, must_change_password)
    ("admin", "admin", "Administrator", "admin", True),
    ("omar", "omar", "Omar (Developer)", "admin", True),
    ("viktor", "viktor", "Viktor (Developer)", "admin", True),
    ("vladlen", "vladlen", "Vladlen (Product Owner)", "analyst", True),
    ("vetalii", "vetalii", "Vetalii (Scrum Master)", "analyst", True),
    # Jury login: no forced password change (frictionless demo entry).
    ("jury", "jury", "Guest (Jury)", "guest", False),
]


def _hash_password(password, salt=None):
    import hashlib, secrets
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000
    ).hex()
    return salt, digest


def ensure_default_users(conn):
    # Insert any missing default account (create_user is a no-op on
    # duplicates), so newly added team members appear on existing databases
    # too — not only on a fresh one.
    for username, password, display_name, role, must_change in DEFAULT_USERS:
        create_user(conn, username, password, display_name, role,
                    must_change=must_change)
    # The short-lived read-only 'viewer' role was removed: everyone works,
    # only admins manage accounts. Upgrade any leftover rows.
    conn.execute("UPDATE users SET role = 'analyst' WHERE role = 'viewer'")
    conn.commit()


def create_user(conn, username, password, display_name, role="analyst",
                must_change=True):
    """Returns True on success, False if the username is taken/invalid.
    New accounts must change their password on first sign-in by default
    (Lab_Webapp mustChangePassword pattern)."""
    username = str(username).strip().lower()
    if not username or not password:
        return False
    salt, digest = _hash_password(password)
    try:
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, str(display_name).strip() or username, role, salt, digest,
             _utcnow(), int(must_change)),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def set_password(conn, username, new_password, must_change=False,
                 changed_by=None):
    """Set a new password; clears (or re-arms, for admin resets) the
    must-change flag."""
    salt, digest = _hash_password(new_password)
    conn.execute(
        "UPDATE users SET salt = ?, password_hash = ?, must_change_password = ?"
        " WHERE username = ?",
        (salt, digest, int(must_change), str(username).strip().lower()),
    )
    conn.commit()
    actor = changed_by or username
    what = "reset (temporary)" if must_change else "changed"
    log_action(conn, actor, "auth.password_change",
               f"Password {what} for '{username}'", str(username))


def verify_user(conn, username, password):
    """Returns the user dict on valid credentials, else None."""
    row = conn.execute(
        "SELECT username, display_name, role, salt, password_hash,"
        " must_change_password"
        " FROM users WHERE username = ?", (str(username).strip().lower(),)
    ).fetchone()
    if row is None:
        return None
    _, digest = _hash_password(password, salt=row[3])
    if digest != row[4]:
        return None
    return {"username": row[0], "display_name": row[1], "role": row[2],
            "must_change_password": int(row[5])}


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
    row = conn.execute(
        "SELECT u.username, u.display_name, u.role, u.must_change_password,"
        " s.expires_at"
        " FROM sessions s JOIN users u USING (username) WHERE s.token = ?",
        (str(token),),
    ).fetchone()
    if row is None or row[4] < _utcnow():
        return None
    return {"username": row[0], "display_name": row[1], "role": row[2],
            "must_change_password": int(row[3])}


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
