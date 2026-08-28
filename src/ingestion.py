import io
from typing import Union
import pandas as pd

REQUIRED_COLUMNS = [
    'transaction_id', 'employee_id', 'department', 'date', 
    'time', 'merchant_name', 'amount_eur', 'payment_channel', 'expense_context'
]

def load_and_validate_data(source: Union[str, io.BytesIO, io.StringIO, pd.DataFrame]) -> pd.DataFrame:
    """Loads and validates corporate transaction data.
    
    Accepts a file path string, file-like buffer (from Streamlit uploader), or DataFrame.
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = pd.read_csv(source)
        
    # Check for presence of all 9 required columns
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
        
    # Data type normalization
    df['amount_eur'] = pd.to_numeric(df['amount_eur'], errors='coerce').fillna(0.0)
    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
    df['time'] = df['time'].astype(str).str.strip()
    df['merchant_name'] = df['merchant_name'].astype(str).str.strip()
    df['payment_channel'] = df['payment_channel'].astype(str).str.strip()
    df['expense_context'] = df['expense_context'].astype(str).str.strip()
    
    return df

if __name__ == "__main__":
    # Local debugging
    sample_path = "tests/Sample Data.csv"
    try:
        data = load_and_validate_data(sample_path)
        print("Data loaded successfully:")
        print(data.head())
    except Exception as err:
        print(f"Ingestion failed: {err}")