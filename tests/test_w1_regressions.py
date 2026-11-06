"""Regressions for unsupported assumptions and partially evaluable plans."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from rules.w1_evaluable import EVALUATOR_LIMITATIONS
from verifier import W1_REGISTRY, verify_document


PLANS = Path(__file__).resolve().parents[1] / "examples" / "w1"


def plan(rule_id, kind="compliant"):
    return json.loads((PLANS / rule_id / f"{kind}.json").read_text(encoding="utf-8"))


def result(document, rule_id):
    before = deepcopy(document)
    report = verify_document(document, registry=W1_REGISTRY)
    assert report.input_valid, report.errors
    assert document == before
    assert not report.errors
    return report, next(r for r in report.rule_results if r.rule_id == f"mutcd.{rule_id}")


@pytest.mark.parametrize("station", (600, 1500, 2400))
@pytest.mark.parametrize("speed", (45, 45.9))
def test_work_zone_separation_does_not_prove_stopping_sight_distance(station, speed):
    document = plan("FLAG-02")
    document["elements"][0]["position"]["station"] = station
    document["typical_application"]["posted_speed_mph"] = speed
    _, check = result(document, "FLAG-02")
    assert check.status == "not_evaluable" and check.score == 0
    assert "sight distance" in check.reason


def test_shoulder_closure_does_not_require_lane_closed_sign_or_arrow_board():
    document = plan("SIGN-20")
    document["typical_application"]["type"] = "shoulder_closure"
    document["elements"] = []
    for rule_id in ("SIGN-20", "ARROW-02"):
        _, check = result(document, rule_id)
        assert check.status == "not_applicable" and not check.findings


@pytest.mark.parametrize("rule_id", ("SIGN-20", "ARROW-02"))
def test_lane_counts_do_not_supply_missing_road_classification(rule_id):
    document = plan(rule_id)
    document["typical_application"].update(type="lane_closure", lanes_total=3, lanes_closed=1)
    document["elements"] = []
    _, check = result(document, rule_id)
    assert check.status == "not_evaluable" and check.score == 0


@pytest.mark.parametrize("size", ("30x30", "36x36", "48x48", "60x60", "unparsed"))
def test_sign_dimensions_do_not_supply_a_missing_road_tier(size):
    document = plan("SIGN-31")
    document["elements"][0]["size_inches"] = size
    _, check = result(document, "SIGN-31")
    assert check.status == "not_evaluable" and not check.findings


@pytest.mark.parametrize("unknown_first", (False, True))
@pytest.mark.parametrize("rule_id,taper_type", (("TAPER-01", "merge"), ("TAPER-02", "shift")))
def test_unknown_taper_does_not_erase_known_failure(rule_id, taper_type, unknown_first):
    document = plan("TAPER-01")
    short = document["elements"][0]
    short["taper_type"] = taper_type
    short["end_station"] = short["start_station"] + 10
    unknown = deepcopy(short)
    unknown.update(element_id="unknown-width", start_offset=0, end_offset=0)
    document["elements"] = [unknown, short] if unknown_first else [short, unknown]
    report, check = result(document, rule_id)
    assert check.status == "fail" and not check.complete
    assert check.score == 0 and "unknown-width" in check.reason
    assert len(check.findings) == 1
    assert check.findings[0].element_ids == (short["element_id"],)
    assert report.exit_code == 1 and not report.evaluation_complete


@pytest.mark.parametrize("unknown_first", (False, True))
def test_downstream_taper_failure_survives_unknown_shift(unknown_first):
    document = plan("TAPER-01")
    bad = document["elements"][0]
    bad.update(taper_type="downstream", end_station=bad["start_station"] + 125)
    unknown = deepcopy(bad)
    unknown.update(element_id="unknown-shift", taper_type="shift", start_offset=0, end_offset=0)
    document["elements"] = [unknown, bad] if unknown_first else [bad, unknown]
    _, check = result(document, "TAPER-02")
    assert check.status == "fail" and not check.complete and len(check.findings) == 1


@pytest.mark.parametrize("speed", (44.9, 45.1, 45.9))
def test_fractional_speed_is_not_truncated_to_a_table_key(speed):
    document = plan("BUFFER-01")
    document["typical_application"]["posted_speed_mph"] = speed
    _, check = result(document, "BUFFER-01")
    assert check.status == "not_evaluable" and check.score == 0
    assert str(speed) in check.reason


def test_downstream_buffer_is_outside_the_upstream_option():
    document = plan("BUFFER-01")
    for zone in document["zones"]:
        if zone["type"] == "upstream_buffer":
            zone["type"] = "downstream_buffer"
    _, check = result(document, "BUFFER-01")
    assert check.status == "not_applicable"


def warning_plan():
    document = plan("SIGN-21")
    document["elements"][0]["face_direction"] = "NB"
    return document


def test_explicit_upstream_warning_can_pass():
    _, check = result(warning_plan(), "SIGN-21")
    assert check.status == "pass" and check.score == 1


def test_reverse_station_approach_checks_travel_order():
    document = warning_plan()
    for zone in document["zones"]:
        zone["start_station"], zone["end_station"] = 2200-zone["start_station"], 2200-zone["end_station"]
    for element in document["elements"]:
        element["position"]["station"] = 2200-element["position"]["station"]
    _, check = result(document, "SIGN-21")
    assert check.status == "pass"
    document["elements"][0]["position"]["station"] = 100
    _, check = result(document, "SIGN-21")
    assert check.status == "fail"


@pytest.mark.parametrize("station", (600, 1500, 2100))
def test_warning_at_or_beyond_flagger_does_not_pass(station):
    document = warning_plan()
    document["elements"][0]["position"]["station"] = station
    _, check = result(document, "SIGN-21")
    assert check.status == "fail" and check.score == 0


def test_transition_warning_upstream_of_flagger_can_pass():
    document = warning_plan()
    document["elements"][0]["position"]["station"] = 550
    _, check = result(document, "SIGN-21")
    assert check.status == "pass"


def test_upstream_warning_outside_modeled_approach_is_incomplete():
    document = warning_plan()
    document["elements"][0]["position"]["station"] = -1
    _, check = result(document, "SIGN-21")
    assert check.status == "not_evaluable" and check.score == 0


def test_opposite_facing_warning_does_not_serve_flagger():
    document = warning_plan()
    document["elements"][0]["face_direction"] = "SB"
    _, check = result(document, "SIGN-21")
    assert check.status == "fail"


@pytest.mark.parametrize("missing", ("face_direction", "controls", "both_directions"))
def test_warning_unknown_direction_is_incomplete(missing):
    document = warning_plan()
    if missing == "face_direction":
        del document["elements"][0][missing]
    elif missing == "controls":
        del document["elements"][1][missing]
    else:
        document["typical_application"]["direction"] = "BOTH"
    _, check = result(document, "SIGN-21")
    assert check.status == "not_evaluable" and check.score == 0


def test_multiple_flaggers_retain_known_missing_warning_with_unknown_direction():
    document = warning_plan()
    document["elements"] = [document["elements"][1]]
    unknown = deepcopy(document["elements"][0])
    unknown["element_id"] = "unknown-flagger"
    del unknown["controls"]
    document["elements"].append(unknown)
    _, check = result(document, "SIGN-21")
    assert check.status == "fail" and not check.complete and len(check.findings) == 1
    assert check.score == 0 and "unknown-flagger" in check.reason


def test_two_lanes_do_not_establish_a_two_way_road():
    document = plan("ARROW-03")
    document["typical_application"].update(type="lane_closure", lanes_total=2, lanes_closed=1)
    _, check = result(document, "ARROW-03")
    assert check.status == "not_evaluable"


@pytest.mark.parametrize("spacing", (14, 20, 26))
def test_approximate_taper_spacing_does_not_invent_a_pass_fail_band(spacing):
    document = plan("TAPER-03")
    for element in document["elements"]:
        if element["type"] == "device_line":
            element["spacing_ft"] = spacing
    _, check = result(document, "TAPER-03")
    assert check.status == "not_evaluable" and check.score == 0


def test_parallel_station_overlap_does_not_prove_taper_association():
    document = plan("CHAN-01")
    document["elements"][1]["spacing_ft"] = 60
    _, check = result(document, "CHAN-01")
    assert check.status == "not_evaluable"
    document["elements"][1]["spacing_ft"] = 81
    _, check = result(document, "CHAN-01")
    assert check.status == "fail" and check.findings


def test_barrier_is_not_treated_as_a_barricade():
    document = plan("CHAN-01")
    document["elements"][1].update(device="barrier", spacing_ft=200)
    _, check = result(document, "CHAN-01")
    assert check.status == "not_applicable"


def test_sign_side_uses_station_orientation_without_rejecting_unknown_exceptions():
    document = warning_plan()
    _, check = result(document, "SIGN-11")
    assert check.status == "pass"
    document["elements"][0]["position"]["side"] = "left"
    _, check = result(document, "SIGN-11")
    assert check.status == "not_evaluable" and not check.findings


def test_evaluator_assumptions_are_in_serialized_report_metadata():
    report, _ = result(plan("TAPER-01"), "TAPER-01")
    metadata = {entry["rule_id"]: entry for entry in report.to_dict()["rule_metadata"]}
    for rule_id, limitations in EVALUATOR_LIMITATIONS.items():
        assert metadata[f"mutcd.{rule_id}"]["limitations"] == list(limitations)
        assert all(any(text in line for line in report.limitations) for text in limitations)


@pytest.mark.parametrize("rule_id,taper_type", (("TAPER-01", "merge"), ("TAPER-02", "shift")))
@pytest.mark.parametrize("huge_first", (False, True))
def test_numeric_overflow_taper_does_not_erase_known_failure(rule_id, taper_type, huge_first):
    document = plan("TAPER-01")
    short = document["elements"][0]
    short.update(taper_type=taper_type, end_station=short["start_station"] + 10)
    huge = deepcopy(short)
    huge.update(element_id="huge-width", end_offset=1e308)
    document["elements"] = [huge, short] if huge_first else [short, huge]
    _, check = result(document, rule_id)
    assert check.status == "fail" and not check.complete
    assert len(check.findings) == 1 and "numeric range" in check.reason
