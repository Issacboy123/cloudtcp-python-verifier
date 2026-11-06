"""Conservative checks for the complete source catalog, using schema 1.0.0.

The registry supplies final source metadata. These evaluators reuse the established
W1 checks where possible and never infer roadway classes, device associations,
equipment attributes, or engineering exceptions from free text.
"""

from dataclasses import replace
from decimal import Decimal
import math
import re

from rule_framework import Citation, Finding, RuleMetadata, RuleResult
from rules.geometry import _GeometryNotEvaluable, _in_range, _single_approach, _station_length_ft
from rules.tapers import TAPER_RULE
from rules.w1_evaluable import EVALUATORS as W1_EVALUATORS, EVALUATOR_LIMITATIONS


CA_TAPER_FT = {
    20: (80, 40, 27), 25: (125, 63, 42), 30: (180, 90, 60),
    35: (245, 123, 82), 40: (320, 160, 107), 45: (540, 270, 180),
    50: (600, 300, 200), 55: (660, 330, 220), 60: (720, 360, 240),
    65: (780, 390, 260), 70: (840, 420, 280), 75: (900, 450, 300),
}
CA_DEVICE_FT = {
    20: (20, 40, 10), 25: (25, 50, 12), 30: (30, 60, 15),
    35: (35, 70, 17), 40: (40, 80, 20), 45: (45, 90, 22),
    50: (50, 100, 25), 55: (50, 100, 25), 60: (50, 100, 25),
    65: (50, 100, 25), 70: (50, 100, 25), 75: (50, 100, 25),
}
SUPPORTED_WARNING_CODES = frozenset({
    "W20-1", "W20-3", "W20-4", "W20-5", "W20-5a", "W20-7",
    "W4-2", "W3-4", "W21-5", "W21-5a", "W21-5b",
})
SUPPORTED_CHANNELIZERS = frozenset({"cone", "drum", "vertical_panel", "tubular_marker"})


def _metadata(rule_id, title, classification="GUIDANCE"):
    return RuleMetadata(
        "mutcd." + rule_id, title, classification,
        (Citation("TCP Rules Document.md" if rule_id.startswith("CA-") else "TCP-W1-1 Rules.md",
                  rule_id, "Source citations supplied by the complete registry."),),
    )


def _ca(document):
    return document["site"]["state"].strip().upper() == "CA"


def _width(element):
    # Existing format documentation defines taper offsets in feet, including
    # when longitudinal station coordinates use meters. lane_width_ft is not W.
    try:
        return abs(float(element["end_offset"]) - float(element["start_offset"]))
    except OverflowError:
        return math.inf


def _finding(meta, message, index, element, **values):
    return Finding(
        meta.rule_id, "warning", meta.classification, message,
        (element["element_id"],), (element["zone_id"],) if "zone_id" in element else (),
        (f"/elements/{index}", "/typical_application/posted_speed_mph"),
        meta.citations, values, "feet",
    )


def _result(meta, findings, incomplete, count):
    if findings:
        return RuleResult(meta.rule_id, "fail", not incomplete, tuple(findings),
                          reason=" ".join(incomplete) or None)
    if incomplete:
        return RuleResult(meta.rule_id, "not_evaluable", False, reason=" ".join(incomplete))
    if not count:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="No supported subjects are present for this check.")
    return RuleResult(meta.rule_id, "pass", True)


def _filtered_tapers(document, rule_id):
    """Delegate CA lookup subjects without changing source finding pointers."""
    original_indices, elements = [], []
    delegated = False
    for index, element in enumerate(document["elements"]):
        if element["type"] == "taper":
            if rule_id == "TAPER-02" and element["taper_type"] == "downstream":
                delegated = True
                continue
            if (_ca(document) and document["typical_application"]["posted_speed_mph"] in CA_TAPER_FT
                    and element["taper_type"] in {"merge", "shift", "shoulder"}
                    and _width(element) == 12):
                delegated = True
                continue
            if _width(element) == 0 and "lane_width_ft" in element:
                element = {key: value for key, value in element.items() if key != "lane_width_ft"}
        original_indices.append(index)
        elements.append(element)
    result = W1_EVALUATORS[rule_id]({**document, "elements": elements})

    def restore_path(path):
        match = re.match(r"^/elements/(\d+)(/.*)?$", path)
        if match:
            return f"/elements/{original_indices[int(match[1])]}{match[2] or ''}"
        return path

    result = replace(result, findings=tuple(
        replace(finding, paths=tuple(restore_path(path) for path in finding.paths))
        for finding in result.findings
    ))
    if delegated and result.status == "not_applicable":
        result = replace(result, reason="Applicable downstream tapers are evaluated under T-013; "
                         "exact 12-ft California merge/shift/shoulder tapers under CA-007.")
    return result


def evaluate_taper_01(document):
    return _filtered_tapers(document, "TAPER-01")


def evaluate_taper_02(document):
    return _filtered_tapers(document, "TAPER-02")


def evaluate_chan_01(document):
    if _ca(document) and document["typical_application"]["posted_speed_mph"] in CA_DEVICE_FT:
        return RuleResult("mutcd.CHAN-01", "not_applicable", True,
                          reason="California exact-row spacing bounds, including the federal limits, "
                          "are evaluated once under CA-008.")
    return W1_EVALUATORS["CHAN-01"](document)


def evaluate_ca_007(document):
    meta = _metadata("CA-007", "California 12-foot-offset taper lookup")
    if not _ca(document):
        return RuleResult(meta.rule_id, "not_applicable", True, reason="The site is outside California.")
    findings, incomplete, count = [], [], 0
    speed = document["typical_application"]["posted_speed_mph"]
    for index, element in enumerate(document["elements"]):
        if element["type"] != "taper" or element["taper_type"] not in {"merge", "shift", "shoulder"}:
            continue
        width = _width(element)
        if not math.isfinite(width) or width <= 0:
            incomplete.append(f"{element['element_id']}: offset width W cannot be established.")
            continue
        if width != 12:
            continue
        count += 1
        if speed not in CA_TAPER_FT:
            incomplete.append(f"{element['element_id']}: speed {speed} mph has no exact CA-007 table row.")
            continue
        minimum = CA_TAPER_FT[speed][{"merge": 0, "shift": 1, "shoulder": 2}[element["taper_type"]]]
        length = _station_length_ft(element["start_station"], element["end_station"], document["site"]["units"])
        if not _in_range(length, minimum, float("inf"), units=document["site"]["units"]):
            findings.append(_finding(meta,
                f"{element['taper_type'].capitalize()} taper {element['element_id']} length {length} ft "
                f"is below the printed California 12-ft-offset minimum {minimum} ft.",
                index, element, length_ft=length, minimum_ft=minimum, W_ft=width, S_mph=speed))
    return _result(meta, findings, incomplete, count)


def evaluate_ca_008(document):
    """Use only bounds valid regardless of unknown taper/conflict association."""
    meta = _metadata("CA-008", "California device spacing maxima")
    if not _ca(document):
        return RuleResult(meta.rule_id, "not_applicable", True, reason="The site is outside California.")
    speed = document["typical_application"]["posted_speed_mph"]
    findings, incomplete, count = [], [], 0
    for index, element in enumerate(document["elements"]):
        if element["type"] != "device_line" or element["device"] not in SUPPORTED_CHANNELIZERS:
            continue
        count += 1
        if speed not in CA_DEVICE_FT:
            incomplete.append(f"{element['element_id']}: speed {speed} mph has no exact CA-008 table row.")
            continue
        row = CA_DEVICE_FT[speed]
        spacing = element["spacing_ft"]
        # The separate CA-008-B 20-ft cap might apply to this line; schema
        # 1.0.0 cannot exclude downstream/one-lane taper association.
        if spacing <= min(*row, 20):
            continue
        if spacing > max(row):
            findings.append(_finding(meta,
                f"Device line {element['element_id']} spacing {spacing} ft exceeds every applicable "
                f"California table maximum (largest {max(row)} ft).",
                index, element, spacing_ft=spacing, maximum_ft=max(row), S_mph=speed))
        else:
            incomplete.append(f"{element['element_id']}: taper/tangent association, conflict-spacing "
                              "applicability, and the CA-008-B 20-ft taper cap cannot be established "
                              "by schema 1.0.0.")
    return _result(meta, findings, incomplete, count)


def evaluate_sign_08(document):
    """Check ordering only for supported, explicitly facing approach signs."""
    meta = _metadata("SIGN-08", "ROAD WORK AHEAD first upstream")
    signs = [(index, element) for index, element in enumerate(document["elements"])
             if element["type"] == "sign"]
    if not signs:
        return RuleResult(meta.rule_id, "not_applicable", True, reason="No sign elements are present.")
    try:
        approach = _single_approach(document)
    except _GeometryNotEvaluable as exc:
        return RuleResult(meta.rule_id, "not_evaluable", False, reason=str(exc))
    direction = document["typical_application"]["direction"]
    if direction == "BOTH":
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason="A single explicit traffic direction is required.")
    selected, incomplete = [], []
    for index, sign in signs:
        station = sign["position"]["station"]
        code = sign["mutcd_code"]
        if code not in SUPPORTED_WARNING_CODES and not code.upper().startswith("W"):
            continue
        if not approach.warning_low <= station <= approach.warning_high:
            if ((approach.transition_reference - station) * approach.station_direction > 0
                    and sign.get("face_direction") in {None, direction}):
                incomplete.append(f"{sign['element_id']}: upstream warning lies outside the uniquely modeled warning area.")
            continue
        if "face_direction" not in sign:
            incomplete.append(f"{sign['element_id']}: warning-sign facing direction is absent.")
            continue
        if sign["face_direction"] != direction:
            continue
        if code not in SUPPORTED_WARNING_CODES:
            incomplete.append(f"{sign['element_id']}: warning code {code} is outside the supported series policy.")
            continue
        if (approach.transition_reference - station) * approach.station_direction <= 0:
            incomplete.append(f"{sign['element_id']}: sign is not strictly upstream of the transition.")
            continue
        selected.append((station * approach.station_direction, index, sign))
    selected.sort(key=lambda item: (item[0], item[2]["element_id"]))
    if len({station for station, _, _ in selected}) != len(selected):
        incomplete.append("Warning signs at the same station do not establish a unique encounter order.")
        return _result(meta, [], incomplete, len(selected))
    if len(selected) < 2:
        if incomplete:
            return _result(meta, [], incomplete, len(selected))
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="Fewer than two supported warning signs serve the modeled approach.")
    _, index, first = selected[0]
    if first["mutcd_code"] != "W20-1":
        # A missing-facing W20-1 could be an upstream candidate for this approach.
        # Unknown warning codes cannot be W20-1 and cannot repair known ordering.
        unknown_road_work = any(
            sign["mutcd_code"] == "W20-1" and sign.get("face_direction") in {None, direction}
            and ("face_direction" not in sign or not
                 approach.warning_low <= sign["position"]["station"] <= approach.warning_high)
            and sign["position"]["station"] * approach.station_direction <= selected[0][0]
            for _, sign in signs
        )
        if unknown_road_work:
            return _result(meta, [], incomplete, len(selected))
        finding = Finding(meta.rule_id, "warning", meta.classification,
            "ROAD WORK AHEAD (W20-1) is not the first supported advance warning sign encountered.",
            (first["element_id"],), (approach.warning_zone_id,),
            (f"/elements/{index}/mutcd_code", f"/elements/{index}/position/station"), meta.citations)
        return _result(meta, [finding], incomplete, len(selected))
    return _result(meta, [], incomplete, len(selected))


def evaluate_sign_26_integer(document):
    """Verify the displayed numeric value, not its match to actual zone extent."""
    meta = _metadata("SIGN-26.c02", "Whole-mile distance on ROAD WORK NEXT signs", "STANDARD")
    findings, incomplete, count = [], [], 0
    for index, sign in enumerate(document["elements"]):
        if sign["type"] != "sign" or sign["mutcd_code"] != "G20-1":
            continue
        count += 1
        match = re.fullmatch(
            r"\s*ROAD\s+WORK\s+NEXT\s+([+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))\s+MILES?\s*",
            sign.get("legend", ""), flags=re.IGNORECASE,
        )
        if match is None:
            incomplete.append(f"{sign['element_id']}: legend does not establish a supported explicit "
                              "ROAD WORK NEXT nonnegative numeric MILE(S) distance.")
            continue
        value = Decimal(match[1])
        if value != value.to_integral_value():
            findings.append(Finding(
                meta.rule_id, "error", "STANDARD",
                f"ROAD WORK NEXT sign {sign['element_id']} states {match[1]} miles rather than a whole-mile value.",
                (sign["element_id"],), (sign["zone_id"],) if "zone_id" in sign else (),
                (f"/elements/{index}/legend",), meta.citations,
            ))
    return _result(meta, findings, incomplete, count)


EVALUATORS = {
    "TAPER-01": evaluate_taper_01,
    "TAPER-02": evaluate_taper_02,
    "T-013": TAPER_RULE.evaluator,
    "CHAN-01": evaluate_chan_01,
    **{key: W1_EVALUATORS[key] for key in
       ("BUFFER-01", "SIGN-11", "SIGN-21", "ARROW-03")},
    "SIGN-08": evaluate_sign_08,
    "SIGN-26.c02": evaluate_sign_26_integer,
    "CA-007": evaluate_ca_007,
    "CA-008": evaluate_ca_008,
}
CAPABILITIES = {key: "automated" if key in {"T-013", "SIGN-26.c02"} else "partial" for key in EVALUATORS}
LIMITATIONS = {key: tuple(EVALUATOR_LIMITATIONS.get(key, ())) for key in EVALUATORS}
LIMITATIONS.update({
    "TAPER-01": LIMITATIONS["TAPER-01"] + (
        "Exact 12-ft California subjects with listed lookup speeds are delegated to CA-007; lane_width_ft alone does not establish offset width W.",),
    "TAPER-02": LIMITATIONS["TAPER-02"] + (
        "Downstream length is evaluated once under T-013; exact 12-ft California lookup subjects under CA-007.",),
    "T-013": ("Checks the inclusive 50–100 ft advisory range; engineering justification is not assessed.",),
    "CHAN-01": LIMITATIONS["CHAN-01"] + (
        "California listed-speed spacing is evaluated once under CA-008; unlisted speeds retain the established federal bounds.",),
    "SIGN-08": (
        "Requires one unambiguous warning/transition approach and explicit sign facing; only the documented supported core warning-code set is selected.",
        "Unknown warning codes and tied stations leave ordering incomplete; regulatory signs are excluded.",),
    "SIGN-26.c02": (
        "Checks only a nonnegative numeric value in the explicit ROAD WORK NEXT <number> MILE(S) legend; unknown formats remain incomplete.",
        "A whole-mile displayed value does not establish that it is the nearest rounded value to the actual TTC-zone extent.",),
    "CA-007": (
        "Exact printed 12-ft-offset merge/shift/shoulder lookup rows only; no speed interpolation or invented rounding.",
        "Taper offsets and lane_width_ft retain their documented feet semantics even when longitudinal station units are meters.",
        "Other widths and unlisted speeds retain supported federal formula checks; downstream 50–100 ft is evaluated once under T-013.",),
    "CA-008": (
        "Only supported cone, drum, tubular-marker, and vertical-panel device lines are evaluated; a barrier is not a barricade.",
        "Exact speed rows only. Without taper/tangent/conflict associations, only bounds valid for every possible table column and the separate CA-008-B 20-ft taper cap produce a decision.",),
})
