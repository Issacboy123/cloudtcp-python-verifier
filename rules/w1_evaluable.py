"""Evaluable TCP-W1-1 rules using schema 1.0.0 facts only."""

import math

from rules.constants import SUPPORTED_CHANNELIZERS
from rule_framework import Rule, RuleResult
from rules.geometry import (
    GeometryNotEvaluable,
    in_range,
    offset_width_ft,
    posted_speed_mph,
    single_approach,
    station_length_ft,
    taper_length_l_ft,
)
from rules.scoring import aggregate_score, binary_score, max_value_score, min_length_score, range_score
from rules.w1_common import finding_for, w1_metadata

# Table 6B-2 stopping sight / optional buffer lengths (ft).
TABLE_6B2_FT = {
    20: 115, 25: 155, 30: 200, 35: 250, 40: 305, 45: 360,
    50: 425, 55: 495, 60: 570, 65: 645, 70: 730, 75: 820,
}

EVALUATOR_LIMITATIONS = {
    'TAPER-01': (
        "Applies Table 6B-4 L to merge tapers using offset width W and posted speed S.",
        "No formula branch for 40 < S < 45 mph.",
        "Shifting/shoulder minima are evaluated under TAPER-02.",
    ),
    'TAPER-02': (
        "One-lane two-way taper type is absent from schema 1.0.0; those subjects are not evaluated.",
        "Merge taper minima are evaluated under TAPER-01.",
        "Uses 0.5L and 0.33L table factors (not exact 1/2 or 1/3 prose).",
    ),
    'TAPER-03': (
        'The source gives approximate 20-ft spacing, not a numeric acceptance tolerance.',
        'Schema 1.0.0 has no authored tolerance or unambiguous device-to-taper association; no pass/fail band is invented.',
    ),
    'CHAN-01': (
        "Applies to cone, tubular_marker, vertical_panel, and drum lines; barrier is not a barricade.",
        "Longitudinal overlap alone does not establish taper association: spacing between S and 2S remains incomplete when a taper overlaps.",
        "Spacing at most S satisfies either limit; spacing above 2S violates either limit.",
    ),
    'BUFFER-01': (
        "OPTION: table lengths are suggested for declared upstream_buffer zones only.",
        "Short buffers reduce the graded score but do not produce findings.",
        "Speed must match a Table 6B-2 key exactly; no interpolation.",
    ),
    'FLAG-02': (
        'Schema 1.0.0 lacks available approach sight distance and the intended stopping point.',
        'Distance between a flagger and a work-zone boundary does not establish stopping sight distance.',
    ),
    'SIGN-11': (
        'Right-hand side is relative to approach travel direction; position.side is relative to increasing station.',
        'A single non-overlapping warning/transition pair is required to establish station direction.',
        'Left/center placement exceptions cannot be established in schema 1.0.0, so they are not classified as violations.',
    ),
    'SIGN-20': (
        'Schema 1.0.0 lacks through-lane identity and roadway/closure classification sufficient to establish applicability.',
        'Sign code presence alone does not establish the required variant, association, or advance placement.',
    ),
    'SIGN-21': (
        'Requires a single warning/transition approach, one explicit traffic direction, and matching flagger controls.',
        'Explicit matching-facing W20-7 signs must be strictly upstream of the flagger on the uniquely modeled approach.',
        'Missing sign-facing/flagger-direction facts or upstream signs outside the modeled approach leave affected subjects incomplete.',
    ),
    'SIGN-31': (
        'Schema 1.0.0 lacks the road tier needed to select conventional/freeway-expressway/minimum size rows.',
        'Dimensions are not rejected solely because they differ from the conventional table row.',
    ),
    'ARROW-03': (
        'Explicit shoulder_closure supports the caution-mode check.',
        'Two lanes alone do not establish a two-way road; other operation types remain not evaluable when boards exist.',
        'The schema lacks lane-shift intent and cannot establish the source prohibition on arrow boards indicating lane shifts.',
    ),
    'ARROW-02': (
        'A single closed lane requires freeway applicability, which is absent from schema 1.0.0.',
        'Multiple closed lanes require distinct board-to-closed-lane associations; schema 1.0.0 provides no lane identity.',
    ),
}


def evaluator_metadata(rule_id):
    return w1_metadata(rule_id, limitations=EVALUATOR_LIMITATIONS[rule_id])


def _zone_ids(element):
    return (element["zone_id"],) if "zone_id" in element else ()


def _subject_result(meta, findings, scores, incomplete):
    """Retain known failures while documenting subjects that could not execute."""
    reason = " ".join(incomplete) or None
    if findings:
        return RuleResult(meta.rule_id, "fail", not incomplete, tuple(findings),
                          reason=reason, score=None if incomplete else aggregate_score(scores))
    if incomplete:
        return RuleResult(meta.rule_id, "not_evaluable", False, reason=reason)
    return RuleResult(meta.rule_id, "pass", True, score=aggregate_score(scores))


def _taper_subjects(document, taper_types):
    units = document["site"]["units"]
    out = []
    for index, element in enumerate(document["elements"]):
        if element["type"] != "taper" or element["taper_type"] not in taper_types:
            continue
        length = station_length_ft(element["start_station"], element["end_station"], units)
        out.append((index, element, length))
    return out, units


def _required_l(document, element):
    try:
        speed = posted_speed_mph(document)
        width = offset_width_ft(element)
        if width <= 0 and element.get("lane_width_ft"):
            width = float(element["lane_width_ft"])
        if width <= 0:
            raise GeometryNotEvaluable("Taper offset width W cannot be established.")
        required = taper_length_l_ft(width, speed)
    except OverflowError as exc:
        raise GeometryNotEvaluable("Taper formula exceeds supported numeric range.") from exc
    if not all(math.isfinite(value) for value in (speed, width, required)):
        raise GeometryNotEvaluable("Taper formula exceeds supported numeric range.")
    return required, width, speed


def evaluate_taper_01(document):
    """TAPER-01: L formula; merge tapers should be at least L."""
    meta = evaluator_metadata("TAPER-01")
    subjects, _units = _taper_subjects(document, {"merge"})
    if not subjects:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no merge taper elements.")
    findings, scores, incomplete = [], [], []
    for index, element, length in subjects:
        try:
            required, width, speed = _required_l(document, element)
        except GeometryNotEvaluable as exc:
            incomplete.append(f"{element['element_id']}: {exc}")
            continue
        score = min_length_score(length, required)
        scores.append(score)
        if in_range(length, required, float("inf"), units=_units):
            continue
        findings.append(finding_for(
            meta,
            f"Merge taper {element['element_id']} length {length} ft is below L={required} ft "
            f"(W={width} ft, S={speed} mph).",
            element_ids=(element["element_id"],), zone_ids=_zone_ids(element),
            paths=(f"/elements/{index}/start_station", f"/elements/{index}/end_station",
                   f"/elements/{index}/start_offset", f"/elements/{index}/end_offset",
                   "/typical_application/posted_speed_mph"),
            values={"length_ft": length, "required_L_ft": required, "W_ft": width,
                    "S_mph": speed, "score": score},
            units="feet",
        ))
    return _subject_result(meta, findings, scores, incomplete)


def evaluate_taper_02(document):
    """TAPER-02: shifting 0.5L, shoulder 0.33L, downstream 50–100 ft."""
    meta = evaluator_metadata("TAPER-02")
    findings, scores, incomplete = [], [], []
    evaluated = 0
    units = document["site"]["units"]

    for index, element, length in _taper_subjects(document, {"shift", "shoulder"})[0]:
        try:
            required_l, width, speed = _required_l(document, element)
        except GeometryNotEvaluable as exc:
            incomplete.append(f"{element['element_id']}: {exc}")
            continue
        factor = 0.5 if element["taper_type"] == "shift" else 0.33
        minimum = factor * required_l
        evaluated += 1
        score = min_length_score(length, minimum)
        scores.append(score)
        if in_range(length, minimum, float("inf"), units=units):
            continue
        findings.append(finding_for(
            meta,
            f"{element['taper_type'].capitalize()} taper {element['element_id']} length {length} ft "
            f"is below {factor}L={minimum} ft (L={required_l} ft, W={width} ft, S={speed} mph).",
            element_ids=(element["element_id"],), zone_ids=_zone_ids(element),
            paths=(f"/elements/{index}/taper_type", f"/elements/{index}/start_station",
                   f"/elements/{index}/end_station", "/typical_application/posted_speed_mph"),
            values={"length_ft": length, "minimum_ft": minimum, "L_ft": required_l,
                    "factor": factor, "score": score},
            units="feet",
        ))

    for index, element, length in _taper_subjects(document, {"downstream"})[0]:
        evaluated += 1
        score = range_score(length, 50, 100)
        scores.append(score)
        if in_range(length, 50, 100, units=units):
            continue
        findings.append(finding_for(
            meta,
            f"Downstream taper {element['element_id']} length {length} ft is outside 50–100 ft.",
            element_ids=(element["element_id"],), zone_ids=_zone_ids(element),
            paths=(f"/elements/{index}/start_station", f"/elements/{index}/end_station", "/site/units"),
            values={"length_ft": length, "recommended_lower_ft": 50, "recommended_upper_ft": 100,
                    "score": score},
            units="feet",
        ))

    if not evaluated and not incomplete:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="No shift, shoulder, or downstream taper elements to evaluate.")
    return _subject_result(meta, findings, scores, incomplete)


def evaluate_taper_03(document):
    """Do not invent an acceptance band for approximate spacing guidance."""
    meta = evaluator_metadata("TAPER-03")
    if not any(e["type"] == "taper" and e["taper_type"] == "downstream"
               for e in document["elements"]):
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no downstream taper elements.")
    return RuleResult(meta.rule_id, "not_evaluable", False,
                      reason=" ".join(meta.limitations))


def evaluate_chan_01(document):
    """Evaluate only spacing bounds established independently of ambiguous overlap."""
    meta = evaluator_metadata("CHAN-01")
    speed = document["typical_application"]["posted_speed_mph"]
    tapers = [e for e in document["elements"] if e["type"] == "taper"]
    findings, scores, incomplete = [], [], []
    count = 0
    for index, element in enumerate(document["elements"]):
        if element["type"] != "device_line" or element["device"] not in SUPPORTED_CHANNELIZERS:
            continue
        count += 1
        line_low, line_high = sorted((element["start_station"], element["end_station"]))
        overlaps = any(not (line_high < min(t["start_station"], t["end_station"])
                           or line_low > max(t["start_station"], t["end_station"]))
                       for t in tapers)
        spacing = element["spacing_ft"]
        if overlaps and speed < spacing <= 2 * speed:
            incomplete.append(f"{element['element_id']}: longitudinal overlap does not establish taper association.")
            continue
        maximum = speed if overlaps and spacing <= speed else 2 * speed
        score = max_value_score(spacing, maximum)
        scores.append(score)
        if spacing <= maximum:
            continue
        findings.append(finding_for(
            meta, f"Device line {element['element_id']} spacing {spacing} ft exceeds the 2S maximum {maximum} ft.",
            element_ids=(element["element_id"],), zone_ids=_zone_ids(element),
            paths=(f"/elements/{index}/spacing_ft", "/typical_application/posted_speed_mph"),
            values={"spacing_ft": spacing, "maximum_ft": maximum, "S_mph": speed, "score": score},
            units="feet",
        ))
    if not count:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no supported channelizing device_line elements.")
    return _subject_result(meta, findings, scores, incomplete)


def evaluate_buffer_01(document):
    """BUFFER-01: optional longitudinal buffer length vs Table 6B-2.

    OPTION rules cannot emit findings; short buffers reduce score but still pass.
    """
    meta = evaluator_metadata("BUFFER-01")
    buffers = [z for z in document["zones"] if z["type"] == "upstream_buffer"]
    if not buffers:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no upstream_buffer zones.")
    speed = document["typical_application"]["posted_speed_mph"]
    if speed not in TABLE_6B2_FT:
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason=f"Posted speed {speed} mph is not a Table 6B-2 key; no interpolation.")
    suggested = TABLE_6B2_FT[speed]
    units = document["site"]["units"]
    scores = []
    for zone in buffers:
        length = station_length_ft(zone["start_station"], zone["end_station"], units)
        scores.append(min_length_score(length, suggested))
    return RuleResult(meta.rule_id, "pass", True, score=aggregate_score(scores))


def evaluate_flag_02(document):
    """Work-zone separation is not a measurement of approach sight distance."""
    meta = evaluator_metadata("FLAG-02")
    if not any(e["type"] == "flagger" for e in document["elements"]):
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no flagger elements.")
    return RuleResult(meta.rule_id, "not_evaluable", False,
                      reason=" ".join(meta.limitations))


def evaluate_sign_11(document):
    """Evaluate right-side placements only when approach orientation is known."""
    meta = evaluator_metadata("SIGN-11")
    signs = [e for e in document["elements"] if e["type"] == "sign"]
    if not signs:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no sign elements.")
    try:
        approach = single_approach(document)
    except GeometryNotEvaluable as exc:
        return RuleResult(meta.rule_id, "not_evaluable", False, reason=str(exc))
    direction = document["typical_application"]["direction"]
    right = "right" if approach.station_direction == 1 else "left"
    if direction == "BOTH" or any(sign.get("face_direction") != direction for sign in signs):
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason="Every sign needs an explicit facing direction matching one approach.")
    if any(sign["position"]["side"] != right for sign in signs):
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason="Left/center placement exceptions cannot be established from schema 1.0.0.")
    return RuleResult(meta.rule_id, "pass", True, score=1.0)


def evaluate_sign_20(document):
    """Do not infer a multi-lane through-lane closure from lane counts alone."""
    meta = evaluator_metadata("SIGN-20")
    ta = document["typical_application"]
    if ta["type"] == "shoulder_closure" or ta.get("lanes_closed") == 0:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="No through-lane closure is declared.")
    return RuleResult(meta.rule_id, "not_evaluable", False,
                      reason=" ".join(meta.limitations))


def evaluate_sign_21(document):
    """Check explicit W20-7 warning signs for a uniquely modeled approach."""
    meta = evaluator_metadata("SIGN-21")
    flaggers = [(i, e) for i, e in enumerate(document["elements"]) if e["type"] == "flagger"]
    if not flaggers:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no flagger elements.")
    try:
        approach = single_approach(document)
    except GeometryNotEvaluable as exc:
        return RuleResult(meta.rule_id, "not_evaluable", False, reason=str(exc))
    direction = document["typical_application"]["direction"]
    if direction == "BOTH":
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason="A single traffic approach direction is required.")
    signs = [(i, e) for i, e in enumerate(document["elements"])
             if e["type"] == "sign" and e["mutcd_code"] == "W20-7"]
    findings, scores, incomplete = [], [], []
    for index, flagger in flaggers:
        if flagger.get("controls") != direction:
            incomplete.append(f"{flagger['element_id']}: controls must explicitly match the single approach.")
            continue
        station = flagger["position"]["station"]
        if (station - approach.transition_reference) * approach.station_direction < 0:
            incomplete.append(f"{flagger['element_id']}: its position is outside the modeled downstream approach.")
            continue
        upstream = [sign for _, sign in signs
                    if (station - sign["position"]["station"]) * approach.station_direction > 0]
        # The source requires advance placement, not membership in one zone.
        # Include the transition portion of the uniquely modeled approach.
        approach_start = approach.warning_low if approach.station_direction == 1 else approach.warning_high
        candidates = [sign for sign in upstream
                      if (sign["position"]["station"] - approach_start) * approach.station_direction >= 0]
        if any(sign.get("face_direction") == direction for sign in candidates):
            scores.append(1.0)
            continue
        if any("face_direction" not in sign for sign in upstream):
            incomplete.append(f"{flagger['element_id']}: candidate W20-7 facing direction is absent.")
            continue
        if any(sign.get("face_direction") == direction for sign in upstream):
            incomplete.append(f"{flagger['element_id']}: upstream W20-7 lies outside the uniquely modeled approach.")
            continue
        scores.append(0.0)
        findings.append(finding_for(
            meta, f"Flagger {flagger['element_id']} has no matching-facing W20-7 upstream on its approach.",
            element_ids=(flagger["element_id"],), zone_ids=_zone_ids(flagger),
            paths=(f"/elements/{index}/position/station", f"/elements/{index}/controls", "/elements"),
            values={"score": 0.0},
        ))
    return _subject_result(meta, findings, scores, incomplete)


def evaluate_sign_31(document):
    """Road tier is required before selecting a sign-size table row."""
    meta = evaluator_metadata("SIGN-31")
    if not any(e["type"] == "sign" for e in document["elements"]):
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no sign elements.")
    return RuleResult(meta.rule_id, "not_evaluable", False,
                      reason=" ".join(meta.limitations))


def evaluate_arrow_03(document):
    """ARROW-03: caution mode for shoulder work / one lane of two-lane two-way."""
    meta = evaluator_metadata("ARROW-03")
    ta = document["typical_application"]
    shoulder = ta["type"] == "shoulder_closure"
    boards = [(i, e) for i, e in enumerate(document["elements"]) if e["type"] == "arrow_board"]
    if not boards:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no arrow_board elements.")
    if not shoulder:
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason=" ".join(meta.limitations))
    caution = {"flashing", "diamond"}
    findings, scores = [], []
    for index, board in boards:
        ok = board["mode"] in caution
        score = binary_score(ok)
        scores.append(score)
        if ok:
            continue
        findings.append(finding_for(
            meta,
            f"Arrow board {board['element_id']} mode {board['mode']} is not caution mode; "
            "arrow/chevron mode shall not be used for shoulder work or closing one lane of a two-lane road.",
            element_ids=(board["element_id"],), zone_ids=_zone_ids(board),
            paths=(f"/elements/{index}/mode",),
            values={"score": score},
        ))
    overall = aggregate_score(scores)
    if findings:
        return RuleResult(meta.rule_id, "fail", True, tuple(findings), score=overall)
    return RuleResult(meta.rule_id, "pass", True, score=overall)


def evaluate_arrow_02(document):
    """Require explicit road classification and board-to-lane associations."""
    meta = evaluator_metadata("ARROW-02")
    ta = document["typical_application"]
    if ta["type"] == "shoulder_closure" or ta.get("lanes_closed") == 0:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="No through-lane closure is declared.")
    return RuleResult(meta.rule_id, "not_evaluable", False,
                      reason=" ".join(meta.limitations))


EVALUATORS = {
    "TAPER-01": evaluate_taper_01,
    "TAPER-02": evaluate_taper_02,
    "TAPER-03": evaluate_taper_03,
    "CHAN-01": evaluate_chan_01,
    "BUFFER-01": evaluate_buffer_01,
    "FLAG-02": evaluate_flag_02,
    "SIGN-11": evaluate_sign_11,
    "SIGN-20": evaluate_sign_20,
    "SIGN-21": evaluate_sign_21,
    "SIGN-31": evaluate_sign_31,
    "ARROW-02": evaluate_arrow_02,
    "ARROW-03": evaluate_arrow_03,
}


def evaluable_rules():
    return tuple(Rule(evaluator_metadata(rule_id), evaluator) for rule_id, evaluator in EVALUATORS.items())
