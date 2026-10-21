"""Private longitudinal geometry in feet; callers select eligible warning signs.

No sign-code or roadway classifier lives here. Input dictionaries are never
normalized in place: only station differences are converted, so explicit _ft,
_mph and _inches fields keep their declared units.
"""

from dataclasses import dataclass
from fractions import Fraction
import math


METERS_PER_FOOT = 0.3048


class _GeometryNotEvaluable(ValueError):
    """Required geometry or subject direction cannot be established uniquely."""


def _station_length_ft(start, end, units):
    """Use decimal station values without cancellation or intermediate overflow.

    Return exact integer feet where possible, otherwise the nearest float. Beyond
    the float range, nearest integer feet retain a finite JSON measurement (with
    at most half a foot of rounding on an astronomical length).
    """
    length = abs(Fraction(str(end)) - Fraction(str(start)))
    if units == "meters":
        length /= Fraction(str(METERS_PER_FOOT))
    elif units != "feet":
        raise ValueError("Station units must be feet or meters.")
    if length.denominator == 1:
        return length.numerator
    try:
        return float(length)
    except OverflowError:
        return round(length)


def _conversion_noise_ft(boundary, units):
    """A floating-point roundoff budget, never a configurable policy tolerance.

    Allow two ULPs at the compared boundary for meter conversion representation
    noise. This never depends on station origin or measured length; input station
    uncertainty cannot widen the policy range. Native feet need no allowance.
    """
    if units == "feet":
        return 0.0
    return 2 * math.ulp(float(boundary))


def _in_range(value, lower, upper, *, units="feet"):
    return (lower - _conversion_noise_ft(lower, units) <= value
            <= upper + _conversion_noise_ft(upper, units))


@dataclass(frozen=True)
class _Approach:
    warning_zone_id: str
    transition_zone_id: str
    warning_low: float
    warning_high: float
    transition_reference: float
    station_direction: int


def _single_approach(document):
    warning = [z for z in document["zones"] if z["type"] == "advance_warning"]
    transition = [z for z in document["zones"] if z["type"] == "transition"]
    if len(warning) != 1 or len(transition) != 1:
        raise _GeometryNotEvaluable("A single advance-warning/transition pair is required.")
    aw, tr = warning[0], transition[0]
    aw_low, aw_high = sorted((aw["start_station"], aw["end_station"]))
    tr_low, tr_high = sorted((tr["start_station"], tr["end_station"]))
    if aw_low == aw_high or tr_low == tr_high:
        raise _GeometryNotEvaluable("Advance-warning and transition zones must be nondegenerate.")
    # Adjacent zones may share an endpoint, but their interiors cannot overlap.
    if aw_high <= tr_low:
        direction, reference = 1, tr_low
    elif tr_high <= aw_low:
        direction, reference = -1, tr_high
    else:
        raise _GeometryNotEvaluable("Advance-warning and transition zones overlap.")
    return _Approach(aw["zone_id"], tr["zone_id"], aw_low, aw_high, reference, direction)


def _advance_signs_by_distance(document, warning_sign_ids):
    """Return (feet upstream of transition, ID), nearest first.

    The caller explicitly selects supported warning IDs; geometry does not inspect
    MUTCD codes. Tests select W20-1 and exclude R4-7. A single traffic direction
    and explicit sign facing are needed to associate signs with the approach.
    Opposite-facing or out-of-area signs are excluded. No compass label determines
    increasing/decreasing station direction. Tied stations have no unique order.
    """
    approach = _single_approach(document)
    traffic_direction = document["typical_application"]["direction"]
    if traffic_direction == "BOTH":
        raise _GeometryNotEvaluable("Warning-sign approach direction is ambiguous (BOTH).")
    selected = frozenset(warning_sign_ids)
    elements = {e["element_id"]: e for e in document["elements"]}
    if not selected <= elements.keys() or any(elements[i]["type"] != "sign" for i in selected):
        raise _GeometryNotEvaluable("Selected warning IDs must identify existing signs.")
    signs = []
    for sign_id in selected:
        sign = elements[sign_id]
        station = sign["position"]["station"]
        if not approach.warning_low <= station <= approach.warning_high:
            continue
        if "face_direction" not in sign:
            raise _GeometryNotEvaluable("A selected warning sign has no explicit facing direction.")
        if sign["face_direction"] != traffic_direction:
            continue
        if (approach.transition_reference - station) * approach.station_direction <= 0:
            raise _GeometryNotEvaluable("A warning sign is not strictly upstream of the transition.")
        distance = _station_length_ft(station, approach.transition_reference, document["site"]["units"])
        signs.append((distance, sign_id))
    signs.sort()
    if not signs:
        raise _GeometryNotEvaluable("No selected warning signs serve the single approach.")
    if len({distance for distance, _ in signs}) != len(signs):
        raise _GeometryNotEvaluable("Warning signs at the same station have ambiguous ordering.")
    return tuple(signs)


def _abc_spacings(document, warning_sign_ids):
    """Available A/B/C gaps, never a requirement to provide three signs."""
    signs = _advance_signs_by_distance(document, warning_sign_ids)[:3]
    previous = 0
    gaps = []
    for label, (distance, sign_id) in zip("ABC", signs):
        gaps.append((label, distance - previous, sign_id))
        previous = distance
    return tuple(gaps)


def _advance_warning_extent_ft(document):
    approach = _single_approach(document)
    return _station_length_ft(approach.warning_low, approach.warning_high, document["site"]["units"])
