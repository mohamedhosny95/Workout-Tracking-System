def parse_sets(text: str) -> int | None:
    """Return int 1–20 or None if invalid."""
    try:
        val = int(text)
        return val if 1 <= val <= 20 else None
    except (ValueError, TypeError):
        return None


def parse_reps(text: str) -> int | None:
    """Return int 1–100 or None if invalid."""
    try:
        val = int(text)
        return val if 1 <= val <= 100 else None
    except (ValueError, TypeError):
        return None


def parse_weight(text: str) -> float | None:
    """Return float >= 0 or None if invalid."""
    try:
        val = float(text)
        return val if val >= 0 else None
    except (ValueError, TypeError):
        return None


def parse_rpe(text: str) -> float | None:
    """Return float 1–10 or None if invalid."""
    try:
        val = float(text)
        return val if 1 <= val <= 10 else None
    except (ValueError, TypeError):
        return None
