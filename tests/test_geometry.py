from copy import deepcopy

import pytest

from rules.geometry import (
    _GeometryNotEvaluable, _abc_spacings, _advance_signs_by_distance,
    _advance_warning_extent_ft, _single_approach, _station_length_ft,
)
from signs_verifier import (
    _FEDERAL_ABC_FT, _abc_comparisons, _open_highway_extent_comparison,
    _speed_distance_range, _urban_distance_comparison,
)


@pytest.fixture
def approach(minimal):
    minimal["typical_application"]["direction"] = "NB"
    minimal["typical_application"]["posted_speed_mph"] = 25
    minimal["site"]["units"] = "feet"
    minimal["zones"] = [
        {"zone_id": "AW", "type": "advance_warning", "start_station": 0, "end_station": 900},
        {"zone_id": "TR", "type": "transition", "start_station": 1000, "end_station": 1100},
    ]
    minimal["elements"] = [
        {"element_id": sign_id, "type": "sign", "mutcd_code": code,
         "face_direction": "NB", "zone_id": "AW",
         "position": {"station": station, "offset": 0, "side": "right"}}
        for sign_id, code, station in (
            ("W1", "W20-1", 900), ("W2", "W20-1", 700),
            ("W3", "W20-1", 400), ("W4", "W20-1", 0),
            ("R1", "R4-7", 950), ("U1", "UNSUPPORTED", 800),
        )
    ]
    return minimal


def selected(document):
    # Explicit test selection policy, not a general production classifier.
    return {e["element_id"] for e in document["elements"]
            if e["type"] == "sign" and e["mutcd_code"] == "W20-1"}


def transform(document, *, reverse=False, meters=False):
    def station(value):
        return (-value if reverse else value) * (0.3048 if meters else 1)
    for zone in document["zones"]:
        for key in ("start_station", "end_station"):
            zone[key] = station(zone[key])
    for element in document["elements"]:
        element["position"]["station"] = station(element["position"]["station"])
    document["site"]["units"] = "meters" if meters else "feet"


@pytest.mark.parametrize("meters", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("swap_endpoints", [False, True])
def test_abc_geometry_units_direction_and_endpoint_order(approach, meters, reverse, swap_endpoints):
    transform(approach, reverse=reverse, meters=meters)
    if swap_endpoints:
        for zone in approach["zones"]:
            zone["start_station"], zone["end_station"] = zone["end_station"], zone["start_station"]
    before = deepcopy(approach)
    geometry = _single_approach(approach)
    assert geometry.station_direction == (-1 if reverse else 1)
    assert geometry.transition_reference == pytest.approx((-1000 if reverse else 1000) * (0.3048 if meters else 1))
    signs = _advance_signs_by_distance(approach, selected(approach))
    assert [distance for distance, _ in signs] == pytest.approx([100, 300, 600, 1000])
    assert [sign_id for _, sign_id in signs] == ["W1", "W2", "W3", "W4"]
    spacings = _abc_spacings(approach, selected(approach))
    assert [gap for _, gap, _ in spacings] == pytest.approx([100, 200, 300])
    assert [label for label, _, _ in spacings] == ["A", "B", "C"]
    assert _advance_warning_extent_ft(approach) == pytest.approx(900)
    assert approach == before


@pytest.mark.parametrize("units,factor", [("feet", 1), ("meters", 0.3048)])
def test_absolute_station_lengths(units, factor):
    assert _station_length_ft(10 * factor, -40 * factor, units) == pytest.approx(50)
    assert _station_length_ft(-40 * factor, 10 * factor, units) == pytest.approx(50)
    assert _station_length_ft(0, 0, units) == 0


@pytest.mark.parametrize("mutation", [
    "missing_warning", "missing_transition", "multiple_warning", "multiple_transition",
    "degenerate_warning", "degenerate_transition", "overlap", "contained", "identical",
])
def test_ambiguous_approaches_are_not_evaluable(approach, mutation):
    zones = approach["zones"]
    if mutation.startswith("missing"):
        zones.pop(0 if mutation.endswith("warning") else 1)
    elif mutation.startswith("multiple"):
        extra = deepcopy(zones[0 if mutation.endswith("warning") else 1])
        extra["zone_id"] = "OTHER"
        extra["start_station"] += 10000
        extra["end_station"] += 10000
        zones.append(extra)
    elif mutation.startswith("degenerate"):
        zone = zones[0 if mutation.endswith("warning") else 1]
        zone["end_station"] = zone["start_station"]
    else:
        zones[1]["start_station"] = {"overlap": 850, "contained": 400, "identical": 0}[mutation]
        zones[1]["end_station"] = {"overlap": 1100, "contained": 500, "identical": 900}[mutation]
    for calculate in (
        lambda: _single_approach(approach),
        lambda: _advance_signs_by_distance(approach, selected(approach)),
        lambda: _advance_warning_extent_ft(approach),
    ):
        with pytest.raises(_GeometryNotEvaluable):
            calculate()


def test_touching_zones_and_sign_at_transition(approach):
    approach["zones"][1]["start_station"] = 900
    assert _single_approach(approach).transition_reference == 900
    with pytest.raises(_GeometryNotEvaluable, match="strictly upstream"):
        _abc_spacings(approach, selected(approach))


def test_warning_selection_excludes_regulatory_and_unknown(approach):
    # Put R4-7 inside the warning zone, even closer than the selected W20-1.
    approach["zones"][0]["end_station"] = 990
    signs = _advance_signs_by_distance(approach, selected(approach))
    assert "R1" not in {sign_id for _, sign_id in signs}
    assert "U1" not in {sign_id for _, sign_id in signs}
    assert signs[0] == (100, "W1")


def test_geometry_does_not_classify_codes(approach):
    ids = selected(approach)
    before = _advance_signs_by_distance(approach, ids)
    for element in approach["elements"]:
        element["mutcd_code"] = "opaque-to-geometry"
    assert _advance_signs_by_distance(approach, ids) == before


@pytest.mark.parametrize("mutation", ["BOTH", "missing_face", "tied", "empty", "unknown_id", "non_sign"])
def test_missing_or_ambiguous_sign_facts(approach, mutation):
    ids = selected(approach)
    if mutation == "BOTH":
        approach["typical_application"]["direction"] = "BOTH"
    elif mutation == "missing_face":
        del approach["elements"][0]["face_direction"]
    elif mutation == "tied":
        approach["elements"][1]["position"]["station"] = 900
    elif mutation == "empty":
        ids = set()
    elif mutation == "unknown_id":
        ids.add("missing")
    else:
        approach["elements"][0]["type"] = "arrow_board"
    with pytest.raises(_GeometryNotEvaluable):
        _advance_signs_by_distance(approach, ids)


def test_opposite_facing_and_outside_signs_are_excluded(approach):
    approach["elements"][0]["face_direction"] = "SB"
    approach["elements"][3]["position"]["station"] = -1
    assert _advance_signs_by_distance(approach, selected(approach)) == ((300, "W2"), (600, "W3"))
    assert _abc_spacings(approach, selected(approach)) == (("A", 300, "W2"), ("B", 300, "W3"))


@pytest.mark.parametrize("category,recommended", [
    ("urban_low_speed", (100, 100, 100)), ("urban_high_speed", (350, 350, 350)),
    ("rural", (500, 500, 500)), ("expressway_freeway", (1000, 1500, 2640)),
])
def test_private_abc_advisory_comparison_values(approach, category, recommended):
    assert _FEDERAL_ABC_FT[category] == recommended
    comparisons = _abc_comparisons(approach, selected(approach), recommended)
    assert comparisons == tuple((label, measured, target, sign_id) for label, measured, target, sign_id in
                               zip("ABC", (100, 200, 300), recommended, ("W1", "W2", "W3")))


@pytest.mark.parametrize("nearest", [99, 100, 150, 200, 201])
@pytest.mark.parametrize("meters", [False, True])
def test_private_urban_comparison_boundaries(approach, nearest, meters):
    approach["zones"][0]["end_station"] = 999
    approach["elements"][0]["position"]["station"] = 1000 - nearest
    transform(approach, meters=meters)
    distance, low, high, sign_id = _urban_distance_comparison(approach, {"W1"})
    assert distance == pytest.approx(nearest)
    assert (low, high, sign_id) == (100, 200, "W1")
    assert approach["typical_application"]["posted_speed_mph"] == 25


def test_private_rural_range_does_not_select_first_sign():
    assert _speed_distance_range(50, 8, 12) == (400, 600)


@pytest.mark.parametrize("length", [1499, 1500, 1501])
@pytest.mark.parametrize("reverse,meters", [(False, False), (True, True)])
def test_private_open_highway_extent_boundaries(approach, length, reverse, meters):
    approach["zones"][0]["start_station"] = 900 - length
    transform(approach, reverse=reverse, meters=meters)
    actual, recommended = _open_highway_extent_comparison(approach)
    assert actual == pytest.approx(length)
    assert recommended == 1500
