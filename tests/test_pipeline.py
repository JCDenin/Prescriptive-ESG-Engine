import pandas as pd

REQUIRED_COLUMNS = [
    'transaction_id', 'employee_id', 'department', 'date', 
    'time', 'merchant_name', 'amount_eur', 'payment_channel', 'expense_context'
]

def load_and_validate_data(file_path: str) -> pd.DataFrame:
    print(f" Attempting to load file: {file_path}")
    df = pd.read_csv(file_path)
    print(f" File loaded successfully. Found rows: {len(df)}, columns: {len(df.columns)}")
    
    # Check for the presence of all 9 required columns
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Error! Missing required columns: {missing_cols}")
    print(" Column check passed successfully. All 9 required columns are present.")
        
    # Data type validation
    print(" Starting data type conversion and validation...")
    
    # Count invalid amounts before filling with zeros
    invalid_amounts = pd.to_numeric(df['amount_eur'], errors='coerce').isna().sum()
    df['amount_eur'] = pd.to_numeric(df['amount_eur'], errors='coerce').fillna(0.0)
    
    # Count invalid dates
    invalid_dates = pd.to_datetime(df['date'], errors='coerce').isna().sum()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    
    if invalid_amounts > 0:
        print(f"   [Warning] Found {invalid_amounts} invalid values in 'amount_eur' (replaced with 0.0)")
    if invalid_dates > 0:
        print(f"   [Warning] Found {invalid_dates} invalid dates in 'date' (replaced with NaT)")
        
    print(" Data type validation completed successfully.\n")
    return df

# Function call
path = r"D:\ESG (VCBIP)\Prescriptive-ESG-Engine\tests\Sample Data.csv"

try:
    data = load_and_validate_data(path)
    print("--- GLOBAL STATUS ---")
    print(" Script executed the logic without critical errors!")
    print(data.head(3))  # Displays the first 3 rows for visual verification
except Exception as e:
    print(f"\n Critical error during script execution: {e}")
