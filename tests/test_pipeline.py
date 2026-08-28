import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io
import pandas as pd
from src.ingestion import load_and_validate_data
from src.classification import classify_transactions

SAMPLE_CSV = """transaction_id,employee_id,department,date,time,merchant_name,amount_eur,payment_channel,expense_context
TX001,EMP_010,Sales,2026-06-01,9:15,Delta Airlines,420.00,TMC_Corporate,Business_Trip
TX002,EMP_014,Engineering,2026-06-02,19:40,Hilton Hotel Berlin,210.00,Personal_Card_Reimbursement,Business_Trip
TX003,EMP_022,Marketing,2026-06-01,8:05,Metro Paris,2.10,Personal_Card_Reimbursement,Daily_Expense
TX004,EMP_022,Marketing,2026-06-02,8:10,Metro Paris,2.10,Personal_Card_Reimbursement,Daily_Expense
TX005,EMP_022,Marketing,2026-06-03,8:02,Metro Paris,2.10,Personal_Card_Reimbursement,Daily_Expense"""

def test_full_pipeline():
    raw_df = load_and_validate_data(io.StringIO(SAMPLE_CSV))
    result_df = classify_transactions(raw_df)
    
    # Check 1: TX001 is normal approved travel (no leakage)
    assert result_df.loc[result_df['transaction_id'] == 'TX001', 'leakage_flag'].values[0] == 0
    assert result_df.loc[result_df['transaction_id'] == 'TX001', 'scope3_category'].values[0] == 'Category 6'
    
    # Check 2: TX002 is Category 6 Leakage (Personal Card + Business Trip)
    assert result_df.loc[result_df['transaction_id'] == 'TX002', 'leakage_flag'].values[0] == 1
    assert result_df.loc[result_df['transaction_id'] == 'TX002', 'scope3_category'].values[0] == 'Category 6'
    
    # Check 3: TX003-005 are recurring Category 7 commute patterns (no leakage)
    assert (result_df.loc[result_df['transaction_id'].isin(['TX003', 'TX004', 'TX005']), 'leakage_flag'] == 0).all()
    assert (result_df.loc[result_df['transaction_id'].isin(['TX003', 'TX004', 'TX005']), 'commute_pattern'] == 1).all()
    assert (result_df.loc[result_df['transaction_id'].isin(['TX003', 'TX004', 'TX005']), 'scope3_category'] == 'Category 7').all()
    
    print(" All validation checks passed successfully!")

if __name__ == "__main__":
    test_full_pipeline()