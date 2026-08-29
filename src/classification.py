import pandas as pd
from src import emissions

MERCHANT_DICT = {
    "lufthansa": "flight",
    "air france": "flight",
    "klm": "flight",
    "ryanair": "flight",
    "easyjet": "flight",
    "delta airlines": "flight",
    "deutsche bahn": "rail",
    "sncf": "rail",
    "eurostar": "rail",
    "trenitalia": "rail",
    "metro paris": "transit",
    "ratp": "transit",
    "bvg": "transit",
    "mvv": "transit",
    "wiener linien": "transit",
    "transport for london": "transit",
    "uber": "rideshare",
    "bolt": "rideshare",
    "free now": "rideshare",
    "taxi": "rideshare",
    "hilton": "hotel",
    "marriott": "hotel",
    "ibis": "hotel",
    "novotel": "hotel",
    "motel one": "hotel",
    "airbnb": "hotel",
    "sixt": "car_rental",
    "europcar": "car_rental",
    "shell": "fuel",
    "aral": "fuel",
    "total energies": "fuel",
    "starbucks": "food",
    "vapiano": "food",
    "pret a manger": "food",
    "restaurant": "food",
    "rewe": "food",
    "office depot": "office",
    "staples": "office",
}

TRAVEL_CATEGORIES = {"flight", "rail", "hotel", "rideshare", "car_rental", "transit", "fuel"}
COMMUTE_CATEGORIES = {"transit", "rideshare", "rail", "fuel"}

CONF_EXACT = 0.95
CONF_PARTIAL = 0.85
CONF_UNKNOWN = 0.40

COMMUTE_START, COMMUTE_END = 7, 9  # 07:00–09:59
COMMUTE_MIN_DAYS = 3

# Optional: Lazy-loaded NLP classifier for unstructured free-text
_nlp_pipeline = None

def _get_nlp_classifier():
    global _nlp_pipeline
    if _nlp_pipeline is None:
        try:
            from transformers import pipeline
            _nlp_pipeline = pipeline(
                "zero-shot-classification", 
                model="typeform/distilbert-base-uncased-mnli"
            )
        except Exception:
            _nlp_pipeline = False
    return _nlp_pipeline

from functools import lru_cache

@lru_cache(maxsize=4096)  # NOTE (Viktor): pure optimization — merchant names
# repeat heavily in large datasets, and without this each unknown-merchant ROW
# triggers a fresh NLP inference. Same inputs -> same result, so caching is safe.
def match_merchant(merchant_name: str):
    """Matches merchant name against dictionary with NLP fallback."""
    name = str(merchant_name).strip().lower()
    
    # 1. Exact match
    if name in MERCHANT_DICT:
        return MERCHANT_DICT[name], CONF_EXACT
        
    # 2. Regex / Substring match
    for keyword, category in MERCHANT_DICT.items():
        if keyword in name:
            return category, CONF_PARTIAL
            
    # 3. NLP Inference for free-text descriptions
    classifier = _get_nlp_classifier()
    if classifier:
        try:
            candidate_labels = ["flight travel", "hotel stay", "public transit", "taxi ride", "office expense"]
            result = classifier(name, candidate_labels)
            top_label = result['labels'][0]
            top_score = result['scores'][0]
            
            label_map = {
                "flight travel": "flight",
                "hotel stay": "hotel",
                "public transit": "transit",
                "taxi ride": "rideshare",
                "office expense": "office"
            }
            if top_score >= 0.70:
                return label_map.get(top_label, "unknown"), round(float(top_score), 2)
        except Exception:
            pass
            
    return "unknown", CONF_UNKNOWN

def is_leakage(category: str, payment_channel: str, expense_context: str) -> bool:
    """Category 6 leakage requires BOTH conditions."""
    return (
        payment_channel == "Personal_Card_Reimbursement"
        and expense_context == "Business_Trip"
        and category in (TRAVEL_CATEGORIES | {"unknown"})
    )

def scope3_for(category: str, expense_context: str) -> str:
    if expense_context == "Business_Trip" and category in TRAVEL_CATEGORIES:
        return "Category 6"
    if expense_context == "Daily_Expense" and category in COMMUTE_CATEGORIES:
        return "Category 7"
    return "Out of scope"

def _commute_hour(time_str: str) -> bool:
    try:
        clean_time = str(time_str).strip()
        hour = int(clean_time.split(":")[0])
        return COMMUTE_START <= hour <= COMMUTE_END
    except (ValueError, IndexError):
        return False

def classify_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Core classification engine maintaining Omar's UI/DB contract."""
    df = df.copy()

    # Step 1: Merchant & Category matching
    matched = df["merchant_name"].map(match_merchant)
    df["category"] = matched.map(lambda m: m[0])
    df["confidence"] = matched.map(lambda m: m[1])

    # Step 2: Scope 3 Category mapping
    df["scope3_category"] = [
        scope3_for(cat, ctx)
        for cat, ctx in zip(df["category"], df["expense_context"])
    ]

    # Step 3: Two-condition Category 6 Leakage flag
    df["leakage_flag"] = [
        int(is_leakage(cat, ch, ctx))
        for cat, ch, ctx in zip(df["category"], df["payment_channel"], df["expense_context"])
    ]

    # Step 4: Category 7 recurring commute pattern detection
    candidate = (
        df["category"].isin(COMMUTE_CATEGORIES)
        & (df["expense_context"] == "Daily_Expense")
        & df["time"].map(_commute_hour)
    )
    cand = df[candidate]
    recurring_days = cand.groupby(["employee_id", "merchant_name"])["date"].transform("nunique")
    recurring_index = cand.index[recurring_days >= COMMUTE_MIN_DAYS]
    
    df["commute_pattern"] = 0
    df.loc[recurring_index, "commute_pattern"] = 1

    # Step 5: Emissions calculation
    df["co2e_kg"] = [
        emissions.co2e_kg(cat, amt)
        for cat, amt in zip(df["category"], df["amount_eur"])
    ]
    
    return df