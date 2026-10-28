from copy import deepcopy
from decimal import Decimal
import importlib
import inspect
import json
import math
from pathlib import Path
import re

import pytest

import signs_verifier
from rule_framework import RuleRegistry
from rules.tapers import TAPER_RULE
from verifier import DEFAULT_REGISTRY, verify_document, verify_file


RULE_IDS = ("mutcd.Z-026", "mutcd.Z-020", "mutcd.Z-022", "mutcd.Z-022-B", "mutcd.T-013")


def taper(length, *, start=0, factor=1, element_id="T1", zone_id=None, taper_type="downstream"):
    # Equivalent unit fixtures use exact decimal multiplication, so a large
    # station origin does not inject an unrelated binary product error.
    def station(value):
        return float(Decimal(str(value)) * Decimal(str(factor))) if factor != 1 else value
    element = {
        "element_id": element_id, "type": "taper", "taper_type": taper_type,
        "start_station": station(start), "end_station": station(start + length),
        "start_offset": 0, "end_offset": 9999, "lane_width_ft": 12,
    }
    if zone_id is not None:
        element["zone_id"] = zone_id
    return element


@pytest.fixture
def site(minimal):
    minimal["site"]["units"] = "feet"
    minimal["zones"] = [{"zone_id": "Z1", "type": "termination", "start_station": 0, "end_station": 1000}]
    minimal["elements"] = []
    return minimal


def t013(site):
    report = verify_document(site)
    assert report.input_valid and not report.errors
    matches = [r for r in report.rule_results if r.rule_id == "mutcd.T-013"]
    assert len(matches) == 1
    return matches[0]


def test_imports_registry_order_and_guidance_only():
    for name in ("ingestion", "rule_framework", "verifier", "signs_verifier", "rules", "rules.geometry", "rules.tapers"):
        importlib.import_module(name)
    assert tuple(rule.metadata.rule_id for rule in DEFAULT_REGISTRY.rules) == RULE_IDS
    assert {rule.metadata.classification for rule in DEFAULT_REGISTRY.rules} == {"GUIDANCE"}


@pytest.mark.parametrize("name,speed,state", [
    ("Rural open highway", 65, "TX"), ("Urban low-speed residential", 20, "CA"),
    ("Freeway expressway", 75, "California"), ("", 0, ""),
])
@pytest.mark.parametrize("direction", ["NB", "BOTH"])
def test_sign_rules_missing_roadway_facts_never_inferred(site, name, speed, state, direction):
    site["site"].update(name=name, road_name=name, highway_number="I-5", state=state, location_description=name)
    site["typical_application"].update(direction=direction, posted_speed_mph=speed, description=name)
    report = verify_document(site)
    assert report.implemented_rule_ids == RULE_IDS
    assert [r.status for r in report.rule_results] == ["not_evaluable"] * 4 + ["not_applicable"]
    assert all(not result.complete and result.reason for result in report.rule_results[:4])
    assert not report.findings and not report.evaluation_complete
    assert report.exit_code == 3
    assert "first warning sign" in report.rule_results[2].reason
    assert "No endpoint is selected" in report.rule_results[2].reason
    assert "Open-highway conditions" in report.rule_results[3].reason
    assert "CA-005" in report.rule_results[0].reason and "unimplemented" in report.rule_results[0].reason
    assert "not applied to California" in report.rule_results[0].reason


@pytest.mark.parametrize("length,expected", [(0, "fail"), (49.999999999, "fail"), (50, "pass"),
                                            (75, "pass"), (100, "pass"), (100.000000001, "fail"), (101, "fail")])
@pytest.mark.parametrize("meters", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_taper_boundaries_units_and_direction(site, length, expected, meters, reverse):
    site["site"]["units"] = "meters" if meters else "feet"
    site["elements"] = [taper(-length if reverse else length, start=500,
                              factor=0.3048 if meters else 1, zone_id="Z1")]
    before = deepcopy(site)
    result = t013(site)
    assert result.status == expected and result.complete
    assert len(result.findings) == (1 if expected == "fail" else 0)
    if result.findings:
        finding = result.findings[0]
        assert finding.values["length_ft"] == pytest.approx(length)
        assert finding.values["recommended_lower_ft"] == 50
        assert finding.values["recommended_upper_ft"] == 100
        assert finding.units == "feet"
        assert finding.element_ids == ("T1",) and finding.zone_ids == ("Z1",)
        assert finding.severity == "warning" and finding.classification == "GUIDANCE"
        assert "recommended inclusive 50–100 ft" in finding.message
        assert "Engineering justification was not assessed" in finding.message
        assert "minimum" not in finding.message and "mandatory" not in finding.message
        for path in finding.paths:
            node = site
            for part in path.lstrip("/").split("/"):
                node = node[int(part)] if isinstance(node, list) else node[part]
        assert {"/elements/0/start_station", "/elements/0/end_station", "/site/units"} <= set(finding.paths)
    assert site == before


@pytest.mark.parametrize("length", [math.nextafter(50, 0), math.nextafter(100, math.inf)])
def test_native_feet_has_no_conversion_tolerance(site, length):
    site["elements"] = [taper(length)]
    assert t013(site).status == "fail"


@pytest.mark.parametrize("length", [50, 100])
@pytest.mark.parametrize("start", [-100000, 0, 100000])
def test_meter_station_roundoff_absorbed_only_at_boundaries(site, length, start):
    site["site"]["units"] = "meters"
    site["elements"] = [taper(length, start=start, factor=0.3048)]
    assert t013(site).status == "pass"
    outside = length + (-1e-7 if length == 50 else 1e-7)
    site["elements"] = [taper(outside, start=start, factor=0.3048)]
    assert t013(site).status == "fail"


@pytest.mark.parametrize("start,end", [(1e18, 1e18), (1e18, 1e18 + 128),
                                      (-1e308, 1e308), (10**309, 10**309)])
def test_large_meter_stations_cannot_expand_advisory_range(site, start, end):
    site["site"]["units"] = "meters"
    element = taper(0)
    element.update(start_station=start, end_station=end)
    site["elements"] = [element]
    result = t013(site)
    assert result.status == "fail" and result.complete
    assert len(result.findings) == 1
    measured = result.findings[0].values["length_ft"]
    assert (measured == 0) if start == end else (measured > 100)


def test_extreme_and_ordinary_tapers_all_retain_warnings(site):
    site["site"]["units"] = "meters"
    huge = taper(0, element_id="huge")
    huge.update(start_station=-1e308, end_station=1e308)
    site["elements"] = [taper(49, factor=0.3048), huge, taper(101, factor=0.3048, element_id="last")]
    result = t013(site)
    assert result.status == "fail" and len(result.findings) == 3
    assert {f.element_ids for f in result.findings} == {("T1",), ("huge",), ("last",)}


def test_input_product_noise_is_not_a_station_origin_tolerance(site):
    site["site"]["units"] = "meters"
    element = taper(0)
    # Conventional binary multiplication can inject endpoint error larger than
    # conversion roundoff at the 100 ft bound. Input uncertainty is not excused.
    element.update(start_station=100000 * 0.3048, end_station=100100 * 0.3048)
    site["elements"] = [element]
    assert t013(site).status == "fail"


def test_only_boundary_scale_meter_conversion_noise_is_absorbed(site):
    site["site"]["units"] = "meters"
    element = taper(0)
    element["end_station"] = math.nextafter(15.24, 0)
    site["elements"] = [element]
    assert t013(site).status == "pass"
    element["end_station"] = 15.24 - 1e-10
    assert t013(site).status == "fail"


def test_all_tapers_one_finding_per_deviation_and_separate_ids(site):
    site["elements"] = [
        taper(49, element_id="short", zone_id="Z1"),
        taper(50, element_id="at_lower"), taper(75, element_id="inside"),
        taper(100, element_id="at_upper"), taper(-101, element_id="long"),
        taper(1, element_id="merge", taper_type="merge"),
        taper(1000, element_id="shift", taper_type="shift"),
        taper(1, element_id="shoulder", taper_type="shoulder"),
    ]
    report = verify_document(site)
    result = report.rule_results[-1]
    assert result.status == "fail" and result.complete
    assert len(report.findings) == 2 and report.exit_code == 1
    assert [f.element_ids for f in report.findings] == [("short",), ("long",)]
    assert [f.zone_ids for f in report.findings] == [("Z1",), ()]
    assert len({f.paths for f in report.findings}) == 2
    assert not report.evaluation_complete  # sign-rule coverage remains incomplete


@pytest.mark.parametrize("elements", [[], [taper(1, taper_type="merge")], [taper(1, taper_type="shift")],
                                     [taper(1, taper_type="shoulder")]])
def test_no_downstream_taper_is_not_applicable(site, elements):
    site["elements"] = elements
    result = t013(site)
    assert result.status == "not_applicable" and result.complete
    assert not result.findings and "no downstream taper" in result.reason


def test_explicit_units_unchanged_and_longitudinal_only(site):
    site["site"]["units"] = "meters"
    site["elements"] = [taper(75, factor=0.3048), {
        "element_id": "S1", "type": "sign", "mutcd_code": "R4-7", "size_inches": "36x36",
        "position": {"station": 0, "offset": 2, "side": "right"}}, {
        "element_id": "D1", "type": "device_line", "device": "cone", "start_station": 0,
        "end_station": 10, "start_offset": 0, "end_offset": 1, "spacing_ft": 20}]
    site["typical_application"]["posted_speed_mph"] = 55
    before = deepcopy(site)
    assert t013(site).status == "pass"
    assert site == before


def test_citations_match_exact_source_headings_and_text():
    root = Path(__file__).resolve().parents[1]
    text = (root / "TCP Rules Document.md").read_text(encoding="utf-8")
    for rule in DEFAULT_REGISTRY.rules:
        for citation in rule.metadata.citations:
            assert citation.source_document == "CA MUTCD"
            heading = f"### {citation.local_reference}\n"
            assert heading in text
            section = text.split(heading, 1)[1].split("\n### ", 1)[0]
            source_citation = re.search(r"\*\*Citation:\*\* (.+)", section).group(1)
            assert citation.mutcd_reference == source_citation.replace("\\.", ".")
        assert rule.metadata.title in rule.metadata.citations[0].local_reference
    ca_section = text.split("### CA-005 — GUIDANCE — California replacement — advance warning sign spacing\n", 1)[1].split("\n### ", 1)[0]
    ca_citation = re.search(r"\*\*Citation:\*\* (.+)", ca_section).group(1).replace("\\.", ".")
    assert ca_citation in " ".join(DEFAULT_REGISTRY.rules[0].metadata.limitations)


def test_no_legacy_context_api_or_public_selection(site):
    assert not any(hasattr(signs_verifier, name) for name in ("check_sign_01", "check_sign_02", "check_sign_03"))
    for api in (verify_document, verify_file):
        assert list(inspect.signature(api).parameters) == ["document" if api is verify_document else "path", "registry"]
    for rule in DEFAULT_REGISTRY.rules:
        assert list(inspect.signature(rule.evaluator).parameters) == ["document"]
    with pytest.raises(TypeError):
        verify_document(site, context={"road_category": "rural"})


def test_default_file_and_document_interfaces_deterministic(site, tmp_path):
    site["elements"] = [taper(49)]
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site), encoding="utf-8")
    first = verify_document(site)
    assert first == verify_file(path)
    assert first.to_json() == verify_document(site).to_json()
    assert json.loads(first.to_json())["implemented_rule_ids"] == list(RULE_IDS)
    # An explicit test registry can resolve just this implemented provision.
    assert verify_document(site, registry=RuleRegistry((TAPER_RULE,))).evaluation_complete
