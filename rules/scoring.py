"""Graded compliance scores in [0, 1] for evaluated subjects."""


def min_length_score(actual, minimum):
    """1.0 when actual >= minimum; otherwise actual/minimum (floored at 0)."""
    if minimum <= 0:
        return 1.0 if actual >= minimum else 0.0
    if actual >= minimum:
        return 1.0
    return max(0.0, min(1.0, actual / minimum))


def range_score(actual, lower, upper):
    """1.0 inside [lower, upper]; decays toward 0 outside the band."""
    if lower <= actual <= upper:
        return 1.0
    if actual < lower:
        return min_length_score(actual, lower)
    span = max(upper, 1.0)
    return max(0.0, min(1.0, 1.0 - (actual - upper) / span))


def max_value_score(actual, maximum):
    """1.0 when actual <= maximum; otherwise decays with overshoot."""
    if maximum <= 0:
        return 1.0 if actual <= maximum else 0.0
    if actual <= maximum:
        return 1.0
    return max(0.0, min(1.0, maximum / actual))


def aggregate_score(scores):
    """Overall rule score is the worst subject score; empty → None."""
    values = [s for s in scores if s is not None]
    if not values:
        return None
    return min(values)


def binary_score(ok):
    return 1.0 if ok else 0.0
