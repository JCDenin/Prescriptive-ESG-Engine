FACTORS_KG_PER_EUR = {
    "flight": 1.10,
    "rail": 0.05,
    "transit": 0.10,
    "rideshare": 0.55,
    "car_rental": 0.60,
    "fuel": 0.90,
    "hotel": 0.30,
    "food": 0.15,
    "office": 0.05,
    "other": 0.10,
    "unknown": 0.20,
}

def co2e_kg(category: str, amount_eur: float) -> float:
    """Calculates CO2e emissions in kg using spend-based factors."""
    factor = FACTORS_KG_PER_EUR.get(str(category).lower(), FACTORS_KG_PER_EUR["unknown"])
    try:
        return round(factor * float(amount_eur), 3)
    except (ValueError, TypeError):
        return 0.0