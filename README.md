# Prescriptive ESG Engine (MVP)

A B2B SaaS platform calculating corporate Scope 3 emissions (Categories 6 & 7) from transaction-level data and delivering actionable MACC recommendations.

## Tech Stack
* **Frontend / UI:** Streamlit
* **Backend / Data Pipeline:** Python, Pandas, NumPy
* **NLP & Classification:** Hugging Face Transformers (`distilroberta`), Regex
* **Database & Auth:** SQLite for the MVP demo (`src/database.py`); Supabase planned for production

## Module Ownership & Status

| Module | Owner | Status |
|---|---|---|
| `src/ingestion.py` — CSV parsing and validation | **Viktor** | In progress (his code, untouched) |
| `src/classification.py` — transaction classifier | **Viktor** | ⚠ **STUB by Omar — replace with real engine** |
| `src/emissions.py` — CO₂e calculation / factors | **Viktor** | ⚠ **STUB by Omar — replace with real factors** |
| `src/database.py` — SQLite schema, review workflow | Omar | Done (MVP) |
| `src/recommendations.py` — MACC rule playbook | Omar | Done (MVP) |
| `app.py` + `ui/` — dashboard, tabs, review queue | Omar | Done (MVP) |
| `scripts/generate_data.py` — synthetic dataset | Omar | Done (seeded) |
| `scripts/smoke_check.py` — pipeline acceptance checks | Omar | Done |

**Viktor — integration contract:** `classify_transactions(df)` receives the 9 raw
CSV columns and must return the dataframe with added columns `category`,
`scope3_category`, `confidence` (0..1), `leakage_flag`, `commute_pattern`,
`co2e_kg`. Everything downstream (review queue, metrics, MACC) depends only on
that contract — `scripts/smoke_check.py` is the acceptance test, including the
critical two-condition Category 6 rule (`Personal_Card_Reimbursement` **and**
`Business_Trip`, never the payment channel alone).

## Local Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/JCDenin/Prescriptive-ESG-Engine.git
   cd Prescriptive-ESG-Engine
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. (Optional) Regenerate the synthetic dataset and run the acceptance checks:
   ```bash
   python scripts/generate_data.py
   python scripts/smoke_check.py
   ```

5. Run the Streamlit application:
   ```bash
   streamlit run app.py
   ```
   Demo accounts (username / password, all lowercase): **admin/admin**,
   **omar/omar**, **viktor/viktor** (admin role — developers);
   **vladlen/vladlen** (Product Owner), **vetalii/vetalii** (Scrum Master),
   both read-only viewers. Admins get a **Team Accounts** tab to create,
   list, and remove accounts (PBKDF2-hashed passwords in SQLite). Login
   survives page refresh via a session token in the URL (12h expiry);
   Sign out revokes it. In the Data Upload tab click
   **Load bundled sample dataset** (2,111 transactions, 100 employees).

## Demo Walkthrough

1. **Data Upload** — ingest + auto-classification; 99% auto-classified, 30
   low-confidence records routed to the sidebar **Pending Review** queue.
2. **Emissions & Financial Overview** — card metrics (total CO₂e, savings
   potential, off-channel spend) and department/category charts; amber =
   Category 6 leakage (personal-card business travel outside the TMC).
3. **Recommendations (MACC Playbook)** — Rule 1 (+1 hybrid day where commuting
   exceeds 30% of a department's travel budget) fires for Engineering and
   Marketing; Rule 2 (off-channel bookings > EUR 150 → lost 15% corporate
   discount) fires for 13 transactions.
4. **Sidebar review queue** — approving/correcting a record immediately makes
   it count toward reports and recommendations; unreviewed low-confidence
   records are structurally excluded from all figures.
