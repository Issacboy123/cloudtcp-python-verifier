"""Objective catalog checks without invented input facts or geometry links."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ingestion import validate_document
from rule_framework import validate_result
from rules.full_evaluable import CAPABILITIES, EVALUATORS, _metadata


PLANS = Path(__file__).resolve().parents[1] / "examples" / "w1"


def plan(rule_id="TAPER-01", state="CA", speed=25):
    document = json.loads((PLANS / rule_id / "compliant.json").read_text(encoding="utf-8"))
    document["site"]["state"] = state
    document["typical_application"]["posted_speed_mph"] = speed
    return document


def check(document, rule_id):
    before = deepcopy(document)
    validate_document(document)
    result = EVALUATORS[rule_id](document)
    assert document == before
    assert result.rule_id == "mutcd." + rule_id
    if rule_id.startswith("CA-") or rule_id in {"SIGN-08", "SIGN-26.c02"}:
        validate_result(result, _metadata(rule_id, "Test metadata", "STANDARD" if rule_id == "SIGN-26.c02" else "GUIDANCE"))
    return result


def taper(document, kind="shoulder", length=42, width=12):
    element = document["elements"][0]
    element.update(taper_type=kind, start_station=0, end_station=length,
                   start_offset=0, end_offset=width)
    document["elements"] = [element]
    return element


@pytest.mark.parametrize("kind,minimum", (("merge", 125), ("shift", 63), ("shoulder", 42)))
def test_california_printed_rounding_and_exact_boundaries(kind, minimum):
    document = plan()
    element = taper(document, kind, minimum)
    assert check(document, "CA-007").status == "pass"
    element["end_station"] = minimum - 0.01
    result = check(document, "CA-007")
    assert result.status == "fail" and result.findings[0].values["minimum_ft"] == minimum


def test_california_meter_stations_do_not_change_taper_offset_feet():
    document = plan()
    document["site"]["units"] = "meters"
    element = taper(document, length=42 * 0.3048)
    assert check(document, "CA-007").status == "pass"
    element["end_station"] = 41.99 * 0.3048
    assert check(document, "CA-007").status == "fail"


@pytest.mark.parametrize("speed", (25.1, 42, 80))
def test_california_lookup_does_not_invent_rows(speed):
    document = plan(speed=speed)
    taper(document)
    assert check(document, "CA-007").status == "not_evaluable"


def test_lookup_not_applied_to_non_california_or_other_offset():
    document = plan(state="OR")
    element = taper(document)
    assert check(document, "CA-007").status == "not_applicable"
    document["site"]["state"] = "CA"
    element["end_offset"] = 10
    assert check(document, "CA-007").status == "not_applicable"


def test_california_state_normalization_matches_registry():
    document = plan(state=" ca ")
    taper(document, length=41.5)
    assert check(document, "CA-007").status == "fail"
    assert check(document, "TAPER-02").status == "not_applicable"


def test_known_california_violation_retained_with_unknown_width():
    document = plan()
    bad = taper(document, length=41)
    unknown = {**bad, "element_id": "unknown", "end_offset": 0, "lane_width_ft": 12}
    document["elements"].append(unknown)
    result = check(document, "CA-007")
    assert result.status == "fail" and not result.complete
    assert len(result.findings) == 1 and "unknown" in result.reason


@pytest.mark.parametrize("rule_id,state", (("CA-007", "CA"), ("TAPER-01", "OR")))
def test_oversized_offset_does_not_discard_known_taper_violation(rule_id, state):
    document = plan(state=state)
    bad = taper(document, kind="merge", length=1)
    document["elements"].append({**bad, "element_id": "large-offset", "end_offset": 10**309})
    result = check(document, rule_id)
    assert result.status == "fail" and not result.complete and len(result.findings) == 1
    assert "large-offset" in result.reason


def test_generic_taper_checks_delegate_california_lookup_without_duplicates():
    document = plan()
    taper(document, length=41.5)
    assert check(document, "TAPER-02").status == "not_applicable"
    assert check(document, "CA-007").status == "fail"
    document["site"]["state"] = "OR"
    assert check(document, "TAPER-02").status == "pass"  # Federal 0.33L = 41.25.


def test_california_unlisted_speed_retains_deterministic_federal_formula():
    document = plan(speed=22)
    taper(document, kind="merge", length=90)
    assert check(document, "TAPER-01").status == "fail"
    assert check(document, "CA-007").status == "not_evaluable"
    document["typical_application"]["posted_speed_mph"] = 42
    assert check(document, "TAPER-01").status == "not_evaluable"


def test_filtering_preserves_original_finding_indices():
    document = plan()
    delegated = taper(document, kind="merge", length=125)
    bad = {**delegated, "element_id": "bad", "end_offset": 10, "end_station": 1}
    document["elements"].append(bad)
    result = check(document, "TAPER-01")
    assert result.status == "fail"
    assert "/elements/1/start_station" in result.findings[0].paths
    assert "/elements/0/start_station" not in result.findings[0].paths


def test_lane_width_does_not_establish_offset_width():
    document = plan(state="OR")
    element = taper(document, kind="merge", width=0, length=1)
    element["lane_width_ft"] = 12
    assert check(document, "TAPER-01").status == "not_evaluable"


@pytest.mark.parametrize("state", ("CA", "OR"))
def test_downstream_taper_evaluated_once_independently_of_width(state):
    document = plan(state=state)
    taper(document, kind="downstream", length=125, width=0)
    assert check(document, "TAPER-02").status == "not_applicable"
    assert check(document, "CA-007").status == "not_applicable"
    assert check(document, "T-013").status == "fail"
    assert CAPABILITIES["T-013"] == "automated"


def device_plan(spacing, speed=55, state="CA"):
    document = plan("CHAN-01", state=state, speed=speed)
    line = next(e for e in document["elements"] if e["type"] == "device_line")
    line["spacing_ft"] = spacing
    document["elements"] = [line]
    return document


@pytest.mark.parametrize("spacing,status", ((20, "pass"), (20.01, "not_evaluable"), (25, "not_evaluable"),
                                         (50, "not_evaluable"), (100, "not_evaluable"), (100.01, "fail")))
def test_california_spacing_uses_only_proven_bounds(spacing, status):
    assert check(device_plan(spacing), "CA-008").status == status


def test_california_conflict_values_keep_printed_rounding():
    assert check(device_plan(12, speed=25), "CA-008").status == "pass"
    assert check(device_plan(12.1, speed=25), "CA-008").status == "not_evaluable"


def test_possible_downstream_taper_cap_prevents_unconditional_california_spacing_pass():
    result = check(device_plan(22, speed=75), "CA-008")
    assert result.status == "not_evaluable" and "CA-008-B" in result.reason


def test_california_spacing_is_evaluated_once_but_unlisted_speed_retains_federal_bound():
    document = device_plan(150, speed=55)
    assert check(document, "CHAN-01").status == "not_applicable"
    assert check(document, "CA-008").status == "fail"
    document["typical_application"]["posted_speed_mph"] = 55.1
    assert check(document, "CHAN-01").status == "fail"
    assert check(document, "CA-008").status == "not_evaluable"


def test_california_spacing_does_not_assume_overlap_is_taper_association():
    document = device_plan(40, speed=55)
    line = document["elements"][0]
    document["elements"].append({
        "element_id": "unrelated-taper", "type": "taper", "taper_type": "merge",
        "start_station": line["start_station"], "end_station": line["end_station"],
        "start_offset": 100, "end_offset": 112,
    })
    assert check(document, "CA-008").status == "not_evaluable"


def test_spacing_keeps_failure_plus_unknown_subject_and_explicit_ft_units():
    document = device_plan(101)
    document["site"]["units"] = "meters"
    line = document["elements"][0]
    document["elements"].append({**line, "element_id": "unknown-association", "spacing_ft": 40})
    result = check(document, "CA-008")
    assert result.status == "fail" and not result.complete and len(result.findings) == 1
    assert result.findings[0].values["spacing_ft"] == 101


def test_spacing_rejects_unlisted_speed_and_excludes_barrier():
    document = device_plan(1000, speed=55.1)
    assert check(document, "CA-008").status == "not_evaluable"
    document["elements"][0]["device"] = "barrier"
    assert check(document, "CA-008").status == "not_applicable"
    assert check(device_plan(1000, state="OR"), "CA-008").status == "not_applicable"


def warning_plan():
    document = plan("SIGN-21", state="OR", speed=45)
    document["elements"] = [
        {"type": "sign", "element_id": "road-work", "mutcd_code": "W20-1", "face_direction": "NB",
         "position": {"station": 50, "offset": 10, "side": "right"}},
        {"type": "sign", "element_id": "lane-closed", "mutcd_code": "W20-5", "face_direction": "NB",
         "position": {"station": 250, "offset": 10, "side": "right"}},
    ]
    return document


def test_sign_ordering_follows_travel_direction_not_array_order():
    document = warning_plan()
    document["elements"].reverse()
    assert check(document, "SIGN-08").status == "pass"
    for zone in document["zones"]:
        zone["start_station"], zone["end_station"] = 2200-zone["start_station"], 2200-zone["end_station"]
    for sign in document["elements"]:
        sign["position"]["station"] = 2200-sign["position"]["station"]
    assert check(document, "SIGN-08").status == "pass"


def test_sign_order_failure_and_missing_road_work_sign():
    document = warning_plan()
    document["elements"][0]["position"]["station"] = 400
    assert check(document, "SIGN-08").status == "fail"
    document["elements"][0]["mutcd_code"] = "W20-7"
    assert check(document, "SIGN-08").status == "fail"


def test_sign_order_does_not_treat_regulatory_or_opposite_facing_sign_as_warning():
    document = warning_plan()
    extra = deepcopy(document["elements"][0])
    extra.update(element_id="regulatory", mutcd_code="R4-7")
    extra["position"]["station"] = 0
    document["elements"].append(extra)
    extra = deepcopy(extra)
    extra.update(element_id="opposite-warning", mutcd_code="W20-5", face_direction="SB")
    document["elements"].append(extra)
    assert check(document, "SIGN-08").status == "pass"


@pytest.mark.parametrize("condition", ("facing", "unknown-code", "tie", "both"))
def test_sign_order_ambiguity_remains_incomplete(condition):
    document = warning_plan()
    if condition == "facing":
        document["elements"][0].pop("face_direction")
    elif condition == "unknown-code":
        document["elements"][1]["mutcd_code"] = "W99-99"
    elif condition == "tie":
        document["elements"][1]["position"]["station"] = 50
    else:
        document["typical_application"]["direction"] = "BOTH"
    assert check(document, "SIGN-08").status == "not_evaluable"


def test_unknown_upstream_road_work_facing_can_prevent_false_order_failure():
    document = warning_plan()
    document["elements"][0].pop("face_direction")
    additional = deepcopy(document["elements"][1])
    additional.update(element_id="flagger-warning", mutcd_code="W20-7")
    additional["position"]["station"] = 400
    document["elements"].append(additional)
    assert check(document, "SIGN-08").status == "not_evaluable"


def test_upstream_warning_outside_declared_area_prevents_false_order_pass():
    document = warning_plan()
    extra = deepcopy(document["elements"][1])
    extra["element_id"] = "outside-warning"
    extra["position"]["station"] = -1
    document["elements"].append(extra)
    assert check(document, "SIGN-08").status == "not_evaluable"


def test_road_work_outside_declared_area_prevents_false_order_failure():
    document = warning_plan()
    document["elements"][0]["position"]["station"] = -1
    extra = deepcopy(document["elements"][1])
    extra.update(element_id="flagger-warning", mutcd_code="W20-7")
    extra["position"]["station"] = 400
    document["elements"].append(extra)
    assert check(document, "SIGN-08").status == "not_evaluable"


def test_missing_facing_road_work_at_tied_station_prevents_false_failure():
    document = warning_plan()
    document["elements"][0].pop("face_direction")
    document["elements"][0]["position"]["station"] = 250
    extra = deepcopy(document["elements"][1])
    extra.update(element_id="flagger-warning", mutcd_code="W20-7")
    extra["position"]["station"] = 400
    document["elements"].append(extra)
    assert check(document, "SIGN-08").status == "not_evaluable"


def test_ordering_known_failure_survives_unknown_other_warning():
    document = warning_plan()
    document["elements"][0]["position"]["station"] = 400
    additional = deepcopy(document["elements"][1])
    additional.update(element_id="unsupported", mutcd_code="W99-99")
    additional["position"]["station"] = 450
    document["elements"].append(additional)
    result = check(document, "SIGN-08")
    assert result.status == "fail" and not result.complete and len(result.findings) == 1


@pytest.mark.parametrize("legend,status", (
    ("ROAD WORK NEXT 2 MILES", "pass"),
    ("Road Work Next 1 Mile", "pass"),
    ("ROAD WORK NEXT 2.0 MILES", "pass"),
    ("ROAD WORK NEXT 2.5 MILES", "fail"),
    ("ROAD WORK NEXT .5 MILES", "fail"),
    ("ROAD WORK NEXT -1 MILE", "not_evaluable"),
    ("ROAD WORK NEXT 2 MILES ahead", "not_evaluable"),
    ("ROAD WORK NEXT TWO MILES", "not_evaluable"),
    ("ROAD WORK NEXT 2e0 MILES", "not_evaluable"),
    (None, "not_evaluable"),
))
def test_explicit_road_work_mileage_integer_display(legend, status):
    document = warning_plan()
    sign = document["elements"][0]
    sign["mutcd_code"] = "G20-1"
    if legend is not None:
        sign["legend"] = legend
    result = check(document, "SIGN-26.c02")
    assert result.status == status
    if status == "fail":
        assert result.findings[0].severity == "error"


def test_whole_mile_check_preserves_fractional_failure_and_unknown_other_sign():
    document = warning_plan()
    for sign in document["elements"]:
        sign["mutcd_code"] = "G20-1"
    document["elements"][0]["legend"] = "ROAD WORK NEXT 2.5 MILES"
    result = check(document, "SIGN-26.c02")
    assert result.status == "fail" and not result.complete and len(result.findings) == 1
    for sign in document["elements"]:
        sign["mutcd_code"] = "W20-1"
    assert check(document, "SIGN-26.c02").status == "not_applicable"
