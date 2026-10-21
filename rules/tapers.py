"""The initial downstream-taper advisory length check only."""

from rule_framework import Citation, Finding, Rule, RuleMetadata, RuleResult
from rules.geometry import _in_range, _station_length_ft


T013 = RuleMetadata(
    "mutcd.T-013", "Downstream taper length", "GUIDANCE",
    (Citation("CA MUTCD", "T-013 — GUIDANCE — Downstream taper length",
              "Federal MUTCD §6B.08, para. 12; PDF p. 135; printed p. 1225 / Table 6B-3, PDF 142; Figure 6B-3, PDF 139."),),
    ("Checks longitudinal length against the inclusive 50–100 ft advisory range only; engineering justification and field adjustment are not assessed.",),
)


def _downstream_taper_lengths(document):
    findings = []
    count = 0
    units = document["site"]["units"]
    for index, element in enumerate(document["elements"]):
        if element["type"] != "taper" or element["taper_type"] != "downstream":
            continue
        count += 1
        start, end = element["start_station"], element["end_station"]
        length = _station_length_ft(start, end, units)
        if _in_range(length, 50, 100, units=units):
            continue
        findings.append(Finding(
            T013.rule_id, "warning", T013.classification,
            f"Downstream taper {element['element_id']} has longitudinal length {length} ft, "
            "outside the recommended inclusive 50–100 ft range. Engineering justification was not assessed.",
            (element["element_id"],),
            (element["zone_id"],) if "zone_id" in element else (),
            (f"/elements/{index}/taper_type", f"/elements/{index}/start_station",
             f"/elements/{index}/end_station", "/site/units"),
            T013.citations,
            {"length_ft": length, "recommended_lower_ft": 50, "recommended_upper_ft": 100},
            "feet",
        ))
    if not count:
        return RuleResult(T013.rule_id, "not_applicable", True,
                          reason="The input contains no downstream taper elements.")
    if findings:
        return RuleResult(T013.rule_id, "fail", True, tuple(findings))
    return RuleResult(T013.rule_id, "pass", True)


TAPER_RULE = Rule(T013, _downstream_taper_lengths)
