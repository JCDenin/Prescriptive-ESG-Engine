import pandas as pd

REQUIRED_COLUMNS = [
    'transaction_id', 'employee_id', 'department', 'date', 
    'time', 'merchant_name', 'amount_eur', 'payment_channel', 'expense_context'
]

def load_and_validate_data(file_path_or_buffer) -> pd.DataFrame:
    df = pd.read_csv(file_path_or_buffer)
    
    # Перевірка наявності всіх 9 обов'язкових колонок
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
        
    df['amount_eur'] = pd.to_numeric(df['amount_eur'], errors='coerce').fillna(0.0)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    return df

# Subject to Change