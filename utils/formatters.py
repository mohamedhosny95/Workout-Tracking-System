from datetime import datetime


def fmt_date(date_str: str) -> str:
    """'2025-06-10' → 'Tue Jun 10'"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %b %d").replace(" 0", " ")
    except Exception:
        return date_str


def fmt_weight(weight: float, unit: str) -> str:
    if weight == 0 or unit == "bodyweight":
        return "bodyweight"
    return f"{weight:g}{unit}"


def fmt_sets_reps(sets: int, reps: int, weight: float, unit: str) -> str:
    return f"{sets}×{reps} @ {fmt_weight(weight, unit)}"
