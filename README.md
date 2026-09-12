# Prescriptive ESG Engine (MVP)

A B2B SaaS platform calculating corporate Scope 3 emissions (Categories 6 & 7) from transaction-level data and delivering actionable MACC recommendations.

**Live demo:** https://emprint.streamlit.app

## Tech Stack
* **Frontend / UI:** Streamlit
* **Backend / Data Pipeline:** Python, Pandas, NumPy
* **NLP & Classification:** Regex + merchant dictionary, with a Hugging Face
  zero-shot fallback (`typeform/distilbert-base-uncased-mnli`) for free-text
  merchants
* **Database & Auth:** SQLite for the MVP demo (`src/database.py`); Supabase planned for production

## Module Ownership & Status

| Module | Owner | Status |
|---|---|---|
| `src/ingestion.py` — CSV parsing and validation | Viktor | Done (MVP) |
| `src/classification.py` — transaction classifier | Viktor | Done (MVP) |
| `src/emissions.py` — CO2e calculation / factors | Viktor | Done (MVP) |
| `src/database.py` — SQLite schema, accounts, review workflow | Omar | Done (MVP) |
| `src/recommendations.py` — MACC rule playbook | Omar | Done (MVP) |
| `src/simulator.py` — Monte Carlo dataset generator | Omar | Done (MVP) |
| `app.py` + `ui/` — dashboard, tabs, review queue, reports | Omar | Done (MVP) |
| `scripts/monte_carlo.py` — batch dataset generation | Omar | Done |
| `scripts/smoke_check.py` — pipeline acceptance checks | Omar | Done |

## Accounts

Each team member has a personal account — ask Omar for your login. On first
sign-in the app requires you to replace
the temporary password with your own; admins can reset any account back to a
temporary password from the **Team Accounts** tab (PBKDF2-hashed, stored in SQLite).

The only account documented here is the guest login used for the defense:

| Login | Password | Access |
|---|---|---|
| `jury` | `jury` | Full product view; internal audit trail and developer tools hidden. Not read-only — a guest can still approve review-queue records and switch or delete datasets. |

Every team member can upload, review, manage datasets and export reports; only
admins additionally get the **Team Accounts** tab. Sessions survive a page refresh
via a token in the URL (12 h expiry); Sign out revokes it.

> Note: the deployed demo uses an ephemeral SQLite database. Whenever the app
> reboots, accounts reset to their seeded temporary passwords.

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

4. (Optional) Generate a fresh Monte Carlo dataset and run the acceptance checks:
   ```bash
   python scripts/monte_carlo.py --rows 10000 --demo
   python scripts/smoke_check.py
   ```

5. Run the Streamlit application:
   ```bash
   streamlit run app.py
   ```
   Sign in, then click **Load Demo Company Data** in the Data Upload tab.

## Demo Walkthrough

The bundled demo dataset (`data/demo_dataset.csv`, 10,000 transactions across 400
employees) is a frozen, pre-tested Monte Carlo run so the figures below are
reproducible.

1. **Data Upload** — ingest + auto-classification: 98% auto-classified, 223
   low-confidence records routed to the sidebar **Pending Review** queue. The
   header states which engine produced the figures (`Classification: rules + NLP`
   or `rules only`).
2. **Emissions & Financial Overview** — 101.1 t CO2e, EUR 12,315 identified
   savings, EUR 54,128 off-channel travel spend across 333 flagged transactions;
   amber = Category 6 leakage (personal-card business travel outside the TMC).
3. **Recommendations (MACC Playbook)** — Rule 1 (+1 hybrid day where commuting
   exceeds 30% of a department's travel budget) contributes EUR 6,122 across all
   five departments; Rule 2 (off-channel bookings > EUR 150 forfeit the 15%
   corporate discount) contributes EUR 6,193 across 146 bookings.
4. **Sidebar review queue** — approving/correcting a record immediately makes
   it count toward reports and recommendations; unreviewed low-confidence
   records are structurally excluded from all figures.
5. **Reports** — filters, trends, leakage detail, review/audit trail (team
   accounts only) and CSV / multi-sheet Excel export.

## Deployment

Deployed on Streamlit Community Cloud from `main`; pushes redeploy automatically.
The NLP model is a ~256 MB runtime download, so the first start after a reboot is
slow — wake the app before a demo and confirm the header reads
`Classification: rules + NLP`.
