"""
sports.py
---------
Sport definitions: thresholds, weights, extreme limits, display config.

All wind values here are in KNOTS (the internal unit).
The transformer converts Open-Meteo m/s → knots before scoring.

Scoring logic (per user clarification):
  - Within [min_range, max_range]         → component_score = 1.0
  - Between boundary and extreme threshold → linear decay 1.0 → 0.0
  - Beyond extreme threshold              → component_score = 0.0
  - Total score = sum(weight * component_score) * 100  →  0–100
"""

SPORTS = {
    "Kitesurf": {
        "color": "#2563EB",        # Blue
        "icon": "🪁",
        "variables": {
            "wind_knots": {
                "weight": 0.70,
                "min_range": 12,
                "max_range": 30,
                "extreme": 40,     # above this → 0
            },
            "wave_height_m": {
                "weight": 0.20,
                "min_range": 0,
                "max_range": 1,
                "extreme": 4,
            },
            "precipitation_mm": {
                "weight": 0.10,
                "min_range": 0,
                "max_range": 10,
                "extreme": 20,
            },
        },
    },
    "Surfing": {
        "color": "#EA580C",        # Orange
        "icon": "🏄",
        "variables": {
            "wind_knots": {
                "weight": 0.10,
                "min_range": 5,
                "max_range": 20,
                "extreme": 25,
            },
            "wave_height_m": {
                "weight": 0.80,
                "min_range": 1,
                "max_range": 3,
                "extreme": 6,
            },
            "precipitation_mm": {
                "weight": 0.10,
                "min_range": 0,
                "max_range": 10,
                "extreme": 20,
            },
        },
    },
    "SUP": {
        "color": "#16A34A",        # Green
        "icon": "🏄‍♂️",
        "variables": {
            "wind_knots": {
                "weight": 0.20,
                "min_range": 0,
                "max_range": 3,
                "extreme": 20,
            },
            "wave_height_m": {
                "weight": 0.50,
                "min_range": 0,
                "max_range": 0.2,
                "extreme": 2,
            },
            "precipitation_mm": {
                "weight": 0.30,
                "min_range": 0,
                "max_range": 5,
                "extreme": 20,
            },
        },
    },
}

GRADE_TIERS = [
    (76, 100, "Optimal",   "#16A34A"),   # Green
    (51,  75, "Good",      "#84CC16"),   # Light green
    (26,  50, "Caution",   "#EAB308"),   # Yellow
    (0,   25, "Dangerous", "#DC2626"),   # Red
]


def get_grade(score: float) -> tuple[str, str]:
    """Return (label, hex_color) for a 0–100 score."""
    for lo, hi, label, color in GRADE_TIERS:
        if lo <= score <= hi:
            return label, color
    return "Dangerous", "#DC2626"


# Unit conversion helpers
MS_TO_KNOTS = 1.94384
MS_TO_KMH   = 3.6
MS_TO_MPH   = 2.23694

WIND_UNIT_FACTORS = {
    "knots": MS_TO_KNOTS,
    "km/h":  MS_TO_KMH,
    "m/s":   1.0,
    "mph":   MS_TO_MPH,
}

WAVE_UNIT_FACTORS = {
    "meters": 1.0,
    "feet":   3.28084,
}
