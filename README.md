# Prescriptive ESG Engine (MVP)

A B2B SaaS platform calculating corporate Scope 3 emissions (Categories 6 & 7) from transaction-level data and delivering actionable MACC recommendations.

## Tech Stack
* **Frontend / UI:** Streamlit
* **Backend / Data Pipeline:** Python, Pandas, NumPy
* **NLP & Classification:** Hugging Face Transformers (`distilroberta`), Regex
* **Database & Auth:** Supabase

## Architecture Modules
* `data/` — Synthetic transaction datasets and emission factor benchmarks.
* `src/ingestion.py` — CSV parsing and data normalization.
* `src/classification.py` — Hybrid Regex + NLP transaction classifier.
* `src/emissions.py` — $\text{CO}_2\text{e}$ calculation engine.
* `src/recommendations.py` — Rule-based MACC recommendation playbook.
* `src/database.py` — Supabase client integration.
* `app.py` — Streamlit dashboard entry point.

## Local Setup

1. Clone the repository:
   ```bash
   git clone [https://github.com/JCDenin/Prescriptive-ESG-Engine.git](https://github.com/JCDenin/Prescriptive-ESG-Engine.git)
   cd Prescriptive-ESG-Engine
   
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   
4. Run the Streamlit application:
   ```bash
   streamlit run app.py
