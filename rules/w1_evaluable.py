"""Evaluable TCP-W1-1 rules using schema 1.0.0 facts only."""

from rule_framework import Rule, RuleResult
from rules.geometry import (
    _GeometryNotEvaluable,
    _in_range,
    _offset_width_ft,
    _posted_speed_mph,
    _station_length_ft,
    _taper_length_l_ft,
)
from rules.scoring import aggregate_score, binary_score, max_value_score, min_length_score, range_score
from rules.w1_common import finding_for, w1_metadata

# Table 6B-2 stopping sight / optional buffer lengths (ft).
TABLE_6B2_FT = {
    20: 115, 25: 155, 30: 200, 35: 250, 40: 305, 45: 360,
    50: 425, 55: 495, 60: 570, 65: 645, 70: 730, 75: 820,
}

SIGN_SIZE_CONVENTIONAL_IN = {
    "W20-1": (36, 36), "W20-3": (36, 36), "W20-4": (36, 36), "W20-5": (36, 36),
    "W20-5a": (36, 36), "W20-7": (36, 36), "W3-4": (36, 36), "W4-2": (36, 36),
    "R11-2": (48, 30), "R9-9": (24, 12), "R9-10": (24, 12), "R9-11": (24, 18),
    "R9-11a": (24, 12), "G20-1": (36, 18), "G20-2": (36, 18),
}


def _zone_ids(element):
    return (element["zone_id"],) if "zone_id" in element else ()


def _parse_size_inches(text):
    if not isinstance(text, str) or "x" not in text.lower():
        return None
    left, right = text.lower().split("x", 1)
    try:
        return int(left.strip()), int(right.strip())
    except ValueError:
        return None


def _taper_subjects(document, taper_types):
    units = document["site"]["units"]
    out = []
    for index, element in enumerate(document["elements"]):
        if element["type"] != "taper" or element["taper_type"] not in taper_types:
            continue
        length = _station_length_ft(element["start_station"], element["end_station"], units)
        out.append((index, element, length))
    return out, units


def _required_l(document, element):
    speed = _posted_speed_mph(document)
    width = _offset_width_ft(element)
    if width <= 0 and element.get("lane_width_ft"):
        width = float(element["lane_width_ft"])
    if width <= 0:
        raise _GeometryNotEvaluable("Taper offset width W cannot be established.")
    return _taper_length_l_ft(width, speed), width, speed


def evaluate_taper_01(document):
    """TAPER-01: L formula; merge tapers should be at least L."""
    meta = w1_metadata("TAPER-01", limitations=(
        "Applies Table 6B-4 L to merge tapers using offset width W and posted speed S.",
        "No formula branch for 40 < S < 45 mph.",
        "Shifting/shoulder minima are evaluated under TAPER-02.",
    ))
    subjects, _units = _taper_subjects(document, {"merge"})
    if not subjects:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no merge taper elements.")
    findings, scores = [], []
    for index, element, length in subjects:
        try:
            required, width, speed = _required_l(document, element)
        except _GeometryNotEvaluable as exc:
            return RuleResult(meta.rule_id, "not_evaluable", False, reason=str(exc))
        score = min_length_score(length, required)
        scores.append(score)
        if length + 0 >= required:  # numeric compare; meter conversion noise handled in TAPER-02 ranges
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
    overall = aggregate_score(scores)
    if findings:
        return RuleResult(meta.rule_id, "fail", True, tuple(findings), score=overall)
    return RuleResult(meta.rule_id, "pass", True, score=overall)


def evaluate_taper_02(document):
    """TAPER-02: shifting 0.5L, shoulder 0.33L, downstream 50–100 ft."""
    meta = w1_metadata("TAPER-02", limitations=(
        "One-lane two-way taper type is absent from schema 1.0.0; those subjects are not evaluated.",
        "Merge taper minima are evaluated under TAPER-01.",
        "Uses 0.5L and 0.33L table factors (not exact 1/2 or 1/3 prose).",
    ))
    findings, scores = [], []
    evaluated = 0
    units = document["site"]["units"]

    for index, element, length in _taper_subjects(document, {"shift", "shoulder"})[0]:
        try:
            required_l, width, speed = _required_l(document, element)
        except _GeometryNotEvaluable as exc:
            return RuleResult(meta.rule_id, "not_evaluable", False, reason=str(exc))
        factor = 0.5 if element["taper_type"] == "shift" else 0.33
        minimum = factor * required_l
        evaluated += 1
        score = min_length_score(length, minimum)
        scores.append(score)
        if length >= minimum:
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
        if _in_range(length, 50, 100, units=units):
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

    if not evaluated:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="No shift, shoulder, or downstream taper elements to evaluate.")
    overall = aggregate_score(scores)
    if findings:
        return RuleResult(meta.rule_id, "fail", True, tuple(findings), score=overall)
    return RuleResult(meta.rule_id, "pass", True, score=overall)


def evaluate_taper_03(document):
    """TAPER-03: device spacing ~20 ft on downstream tapers."""
    meta = w1_metadata("TAPER-03", limitations=(
        "Compares device_line spacing_ft on lines overlapping a downstream taper to ~20 ft.",
        "One-lane two-way taper type is absent from schema 1.0.0.",
        "Approximate spacing treated as inclusive 15–25 ft band for grading.",
    ))
    downstream = [
        e for e in document["elements"]
        if e["type"] == "taper" and e["taper_type"] == "downstream"
    ]
    if not downstream:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no downstream taper elements.")
    findings, scores = [], []
    count = 0
    for index, element in enumerate(document["elements"]):
        if element["type"] != "device_line":
            continue
        line_low, line_high = sorted((element["start_station"], element["end_station"]))
        overlaps = False
        for taper in downstream:
            t0, t1 = sorted((taper["start_station"], taper["end_station"]))
            if line_high < t0 or line_low > t1:
                continue
            overlaps = True
            break
        if not overlaps:
            continue
        count += 1
        spacing = float(element["spacing_ft"])
        score = range_score(spacing, 15, 25)
        scores.append(score)
        if 15 <= spacing <= 25:
            continue
        findings.append(finding_for(
            meta,
            f"Device line {element['element_id']} spacing {spacing} ft on a downstream taper "
            "is outside the approximate 20 ft guidance band (graded as 15–25 ft).",
            element_ids=(element["element_id"],), zone_ids=_zone_ids(element),
            paths=(f"/elements/{index}/spacing_ft",),
            values={"spacing_ft": spacing, "recommended_ft": 20, "score": score},
            units="feet",
        ))
    if not count:
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason="Downstream tapers are present but no overlapping device_line spacing is provided.")
    overall = aggregate_score(scores)
    if findings:
        return RuleResult(meta.rule_id, "fail", True, tuple(findings), score=overall)
    return RuleResult(meta.rule_id, "pass", True, score=overall)


def evaluate_chan_01(document):
    """CHAN-01: taper spacing ≤ 1×S; tangent ≤ 2×S."""
    meta = w1_metadata("CHAN-01", limitations=(
        "Device lines overlapping any taper use the 1×S maximum; others use 2×S.",
        "Applies to cone, tubular_marker, vertical_panel, drum, and barricade-like lines in schema.",
    ))
    speed = _posted_speed_mph(document)
    tapers = [e for e in document["elements"] if e["type"] == "taper"]
    findings, scores = [], []
    count = 0
    allowed = {"cone", "tubular_marker", "vertical_panel", "drum", "barrier"}
    for index, element in enumerate(document["elements"]):
        if element["type"] != "device_line" or element["device"] not in allowed:
            continue
        count += 1
        line_low, line_high = sorted((element["start_station"], element["end_station"]))
        in_taper = False
        for taper in tapers:
            t0, t1 = sorted((taper["start_station"], taper["end_station"]))
            if line_high < t0 or line_low > t1:
                continue
            in_taper = True
            break
        maximum = speed if in_taper else 2 * speed
        spacing = float(element["spacing_ft"])
        score = max_value_score(spacing, maximum)
        scores.append(score)
        if spacing <= maximum:
            continue
        kind = "taper" if in_taper else "tangent"
        findings.append(finding_for(
            meta,
            f"Device line {element['element_id']} {kind} spacing {spacing} ft exceeds "
            f"maximum {maximum} ft ({'1' if in_taper else '2'}×S, S={speed} mph).",
            element_ids=(element["element_id"],), zone_ids=_zone_ids(element),
            paths=(f"/elements/{index}/spacing_ft", "/typical_application/posted_speed_mph"),
            values={"spacing_ft": spacing, "maximum_ft": maximum, "S_mph": speed, "score": score},
            units="feet",
        ))
    if not count:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no channelizing device_line elements.")
    overall = aggregate_score(scores)
    if findings:
        return RuleResult(meta.rule_id, "fail", True, tuple(findings), score=overall)
    return RuleResult(meta.rule_id, "pass", True, score=overall)


def evaluate_buffer_01(document):
    """BUFFER-01: optional longitudinal buffer length vs Table 6B-2.

    OPTION rules cannot emit findings; short buffers reduce score but still pass.
    """
    meta = w1_metadata("BUFFER-01", limitations=(
        "OPTION: table lengths are suggested when a longitudinal buffer is used.",
        "Short buffers reduce the graded score but do not produce findings.",
        "Speed must match a Table 6B-2 key exactly; no interpolation.",
    ))
    buffers = [z for z in document["zones"] if z["type"] in ("upstream_buffer", "downstream_buffer")]
    if not buffers:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no longitudinal buffer zones.")
    speed = int(_posted_speed_mph(document))
    if speed not in TABLE_6B2_FT:
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason=f"Posted speed {speed} mph is not a Table 6B-2 key; no interpolation.")
    suggested = TABLE_6B2_FT[speed]
    units = document["site"]["units"]
    scores = []
    for zone in buffers:
        length = _station_length_ft(zone["start_station"], zone["end_station"], units)
        scores.append(min_length_score(length, suggested))
    return RuleResult(meta.rule_id, "pass", True, score=aggregate_score(scores))


def evaluate_flag_02(document):
    """FLAG-02: flagger station distance vs Table 6B-2 default."""
    meta = w1_metadata("FLAG-02", limitations=(
        "Defaults to Table 6B-2 distance from flagger station to the nearest work-zone start.",
        "Engineering-judgment relocation when sight distance cannot be achieved is not assessed.",
        "Speed must match a Table 6B-2 key exactly.",
    ))
    flaggers = [(i, e) for i, e in enumerate(document["elements"]) if e["type"] == "flagger"]
    if not flaggers:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no flagger elements.")
    work = [z for z in document["zones"] if z["type"] == "work"]
    if not work:
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason="Flagger present but no work zone establishes the intended stopping point.")
    speed = int(_posted_speed_mph(document))
    if speed not in TABLE_6B2_FT:
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason=f"Posted speed {speed} mph is not a Table 6B-2 key; no interpolation.")
    required = TABLE_6B2_FT[speed]
    units = document["site"]["units"]
    findings, scores = [], []
    for index, flagger in flaggers:
        station = flagger["position"]["station"]
        distances = [
            _station_length_ft(station, min(z["start_station"], z["end_station"]), units)
            for z in work
        ]
        distance = min(distances)
        score = min_length_score(distance, required)
        scores.append(score)
        if distance >= required:
            continue
        findings.append(finding_for(
            meta,
            f"Flagger {flagger['element_id']} is {distance} ft from the nearest work zone start; "
            f"Table 6B-2 suggests at least {required} ft at {speed} mph.",
            element_ids=(flagger["element_id"],), zone_ids=_zone_ids(flagger),
            paths=(f"/elements/{index}/position/station", "/typical_application/posted_speed_mph"),
            values={"distance_ft": distance, "required_ft": required, "S_mph": speed, "score": score},
            units="feet",
        ))
    overall = aggregate_score(scores)
    if findings:
        return RuleResult(meta.rule_id, "fail", True, tuple(findings), score=overall)
    return RuleResult(meta.rule_id, "pass", True, score=overall)


def evaluate_sign_11(document):
    """SIGN-11: signs should be on the right-hand side."""
    meta = w1_metadata("SIGN-11", limitations=(
        "Checks position.side == 'right'. Left/center placements are findings.",
        "SIGN-12 dual-side emphasis option is not auto-applied as an exception.",
    ))
    findings, scores = [], []
    count = 0
    for index, element in enumerate(document["elements"]):
        if element["type"] != "sign":
            continue
        count += 1
        side = element["position"]["side"]
        ok = side == "right"
        score = binary_score(ok)
        scores.append(score)
        if ok:
            continue
        findings.append(finding_for(
            meta,
            f"Sign {element['element_id']} is placed on the {side} side; guidance prefers the right-hand side.",
            element_ids=(element["element_id"],), zone_ids=_zone_ids(element),
            paths=(f"/elements/{index}/position/side",),
            values={"score": score},
        ))
    if not count:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no sign elements.")
    overall = aggregate_score(scores)
    if findings:
        return RuleResult(meta.rule_id, "fail", True, tuple(findings), score=overall)
    return RuleResult(meta.rule_id, "pass", True, score=overall)


def evaluate_sign_20(document):
    """SIGN-20: Lane Closed sign required for multi-lane through-lane closure."""
    meta = w1_metadata("SIGN-20", limitations=(
        "Triggers when lanes_total > 1 and lanes_closed >= 1.",
        "Accepts W20-5 or W20-5a codes only; legend text is not parsed.",
    ))
    ta = document["typical_application"]
    lanes_total = ta.get("lanes_total")
    lanes_closed = ta.get("lanes_closed")
    if lanes_closed is None:
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason="lanes_closed is absent; multi-lane closure applicability cannot be established.")
    if not (lanes_total > 1 and lanes_closed >= 1):
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="Not a multi-lane through-lane closure under lanes_total/lanes_closed.")
    codes = {e.get("mutcd_code") for e in document["elements"] if e["type"] == "sign"}
    ok = bool(codes & {"W20-5", "W20-5a"})
    score = binary_score(ok)
    if ok:
        return RuleResult(meta.rule_id, "pass", True, score=score)
    finding = finding_for(
        meta,
        "A Lane(s) Closed sign (W20-5 or W20-5a) is required in advance of a multi-lane through-lane closure.",
        paths=("/typical_application/lanes_closed", "/typical_application/lanes_total"),
        values={"lanes_total": lanes_total, "lanes_closed": lanes_closed, "score": score},
    )
    return RuleResult(meta.rule_id, "fail", True, (finding,), score=score)


def evaluate_sign_21(document):
    """SIGN-21: W20-7 should precede a flagger station."""
    meta = w1_metadata("SIGN-21", limitations=(
        "Requires a W20-7 sign element whenever any flagger element is present.",
        "Does not verify upstream ordering relative to the flagger station.",
    ))
    if not any(e["type"] == "flagger" for e in document["elements"]):
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no flagger elements.")
    ok = any(e["type"] == "sign" and e.get("mutcd_code") == "W20-7" for e in document["elements"])
    score = binary_score(ok)
    if ok:
        return RuleResult(meta.rule_id, "pass", True, score=score)
    finding = finding_for(
        meta,
        "A Flagger (W20-7) sign should be used in advance of a flagger station.",
        paths=("/elements",),
        values={"score": score},
    )
    return RuleResult(meta.rule_id, "fail", True, (finding,), score=score)


def evaluate_sign_31(document):
    """SIGN-31: conventional-road sizes for known codes when size_inches is present."""
    meta = w1_metadata("SIGN-31", limitations=(
        "Checks conventional-road sizes from the extracted Table 6H-1/6G-1 rows only.",
        "Signs without size_inches are skipped; freeway/expressway size tier is not selected.",
        "Multi-lane conventional larger minima from Part 2 tables are not in this source.",
    ))
    findings, scores = [], []
    count = 0
    for index, element in enumerate(document["elements"]):
        if element["type"] != "sign":
            continue
        code = element.get("mutcd_code")
        if code not in SIGN_SIZE_CONVENTIONAL_IN or "size_inches" not in element:
            continue
        count += 1
        expected = SIGN_SIZE_CONVENTIONAL_IN[code]
        actual = _parse_size_inches(element["size_inches"])
        ok = actual == expected
        score = binary_score(ok)
        scores.append(score)
        if ok:
            continue
        findings.append(finding_for(
            meta,
            f"Sign {element['element_id']} ({code}) size {element['size_inches']} does not match "
            f"conventional {expected[0]}x{expected[1]} in.",
            element_ids=(element["element_id"],), zone_ids=_zone_ids(element),
            paths=(f"/elements/{index}/size_inches", f"/elements/{index}/mutcd_code"),
            values={"expected_w_in": expected[0], "expected_h_in": expected[1], "score": score},
            units="inches",
        ))
    if not count:
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason="No signs with both a supported mutcd_code and size_inches are present.")
    overall = aggregate_score(scores)
    if findings:
        return RuleResult(meta.rule_id, "fail", True, tuple(findings), score=overall)
    return RuleResult(meta.rule_id, "pass", True, score=overall)


def evaluate_arrow_03(document):
    """ARROW-03: caution mode for shoulder work / one lane of two-lane two-way."""
    meta = w1_metadata("ARROW-03", limitations=(
        "Treats flashing and diamond modes as caution; sequential_arrow/chevron indicate lane closure.",
        "Applies when typical_application.type is shoulder_closure, or lanes_total==2 with lane_closure.",
    ))
    ta = document["typical_application"]
    shoulder = ta["type"] == "shoulder_closure"
    two_lane_closure = ta["type"] == "lane_closure" and ta.get("lanes_total") == 2
    if not (shoulder or two_lane_closure):
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="Not shoulder work or a one-lane closure on a two-lane two-way road.")
    boards = [(i, e) for i, e in enumerate(document["elements"]) if e["type"] == "arrow_board"]
    if not boards:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="The input contains no arrow_board elements.")
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
    """ARROW-02: separate arrow board per closed lane on multi-lane closures."""
    meta = w1_metadata("ARROW-02", limitations=(
        "Uses lanes_closed as the required arrow_board count for multi_lane_closure or lane_closure "
        "with lanes_total > 2. Freeway-specific applicability is not separately classified.",
    ))
    ta = document["typical_application"]
    lanes_closed = ta.get("lanes_closed")
    if lanes_closed is None:
        return RuleResult(meta.rule_id, "not_evaluable", False,
                          reason="lanes_closed is absent.")
    applicable = ta["type"] == "multi_lane_closure" or (
        ta["type"] in ("lane_closure", "multi_lane_closure") and ta.get("lanes_total", 0) > 2 and lanes_closed >= 1
    )
    if not applicable or lanes_closed < 1:
        return RuleResult(meta.rule_id, "not_applicable", True,
                          reason="Not an applicable multiple-lane closure under available schema facts.")
    boards = sum(1 for e in document["elements"] if e["type"] == "arrow_board")
    score = min_length_score(boards, lanes_closed)
    if boards >= lanes_closed:
        return RuleResult(meta.rule_id, "pass", True, score=1.0)
    finding = finding_for(
        meta,
        f"{boards} arrow board(s) present for {lanes_closed} closed lane(s); a separate board per closed lane is required.",
        paths=("/typical_application/lanes_closed",),
        values={"arrow_boards": boards, "lanes_closed": lanes_closed, "score": score},
    )
    return RuleResult(meta.rule_id, "fail", True, (finding,), score=score)


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
    return tuple(Rule(w1_metadata(rule_id), evaluator) for rule_id, evaluator in EVALUATORS.items())
