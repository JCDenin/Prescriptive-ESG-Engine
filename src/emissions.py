# =============================================================================
#  STUB MODULE - TO BE REPLACED BY VIKTOR (Emissions Calculation workstream)
# =============================================================================
#  Placeholder spend-based factors so the pipeline produces CO2e numbers.
#  Viktor: replace with the real emission-factor set (see
#  data/emission_factors_placeholder.csv). Keep the contract:
#      co2e_kg(category, amount_eur) -> float
# =============================================================================

"""Spend-based emission factors (kg CO2e per EUR) for the MVP.

Coarse by design: the MVP demonstrates the pipeline, not accounting-grade
factors. Values are in the range of published spend-based factors for each
category.
"""

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


def co2e_kg(category, amount_eur):
    return round(FACTORS_KG_PER_EUR.get(category, FACTORS_KG_PER_EUR["unknown"]) * float(amount_eur), 3)
