"""Initial sign-rule coverage and private calculations, with no caller context.

The unchanged schema cannot establish roadway applicability. These four rules
therefore never turn the private numeric comparisons into production findings.
"""

from rule_framework import Citation, Rule, RuleMetadata, RuleResult
from rules.geometry import _abc_spacings, _advance_signs_by_distance, _advance_warning_extent_ft


_SOURCE = "CA MUTCD"
_FEDERAL_ABC_FT = {
    "urban_low_speed": (100, 100, 100),
    "urban_high_speed": (350, 350, 350),
    "rural": (500, 500, 500),
    "expressway_freeway": (1000, 1500, 2640),
}


def _abc_comparisons(document, warning_sign_ids, recommended_ft):
    """Pure advisory comparisons: (label, measured ft, recommended ft, sign ID).

    No category selection or jurisdiction decision is made here. In particular,
    the private federal table is not executable California rule coverage.
    """
    return tuple((label, measured, recommended, sign_id)
                 for (label, measured, sign_id), recommended in
                 zip(_abc_spacings(document, warning_sign_ids), recommended_ft))


def _urban_distance_comparison(document, warning_sign_ids):
    """Nearest distance and 4S/8S endpoints in ft; S stays in declared mph."""
    distance, sign_id = _advance_signs_by_distance(document, warning_sign_ids)[0]
    low, high = _speed_distance_range(document["typical_application"]["posted_speed_mph"], 4, 8)
    return distance, low, high, sign_id


def _speed_distance_range(speed_mph, low_multiplier, high_multiplier):
    """Numeric endpoints only; does not resolve Z-022's 'first warning sign'."""
    return low_multiplier * speed_mph, high_multiplier * speed_mph


def _open_highway_extent_comparison(document):
    """Single warning-area length and the 1,500 ft advisory comparison value.

    Calling this calculation does not establish open-highway applicability.
    """
    return _advance_warning_extent_ft(document), 1500


Z026 = RuleMetadata(
    "mutcd.Z-026", "Federal baseline — advance warning sign spacing", "GUIDANCE",
    (Citation(_SOURCE, "Z-026 — GUIDANCE — Federal baseline — advance warning sign spacing",
              "Federal MUTCD §6B.04 para. 07; Table 6B-1; §6H.02 para. 01; PDF p. 133, 140, 171; printed p. 1223, 1230, 1261."),),
    ("Roadway category and agency/site-road-owner low/high urban speed classification are absent from schema 1.0.0.",
     "CA-005 — GUIDANCE — California replacement — advance warning sign spacing is unimplemented; the federal table is not applied to California. CA-005 cites CA MUTCD §6B.04 para. 07; Table 6B-1; PDF p. 133, 140; printed p. 1223, 1230. Its between-band interpolation and flagged footnote error remain unresolved.",
     "Spacing recommendations are approximate guidance subject to engineering judgment and field adjustment."),
)
Z020 = RuleMetadata(
    "mutcd.Z-020", "Urban nearest warning sign placement", "GUIDANCE",
    (Citation(_SOURCE, "Z-020 — GUIDANCE — Urban nearest warning sign placement",
              "Federal MUTCD §6B.04, para. 04; PDF p. 133; printed p. 1223."),),
    ("Urban-street applicability is absent from schema 1.0.0; names, highway numbers, speed, and free text do not establish it.",),
)
Z022 = RuleMetadata(
    "mutcd.Z-022", "Rural first warning sign placement", "GUIDANCE",
    (Citation(_SOURCE, "Z-022 — GUIDANCE — Rural first warning sign placement",
              "Federal MUTCD §6B.04, para. 06; PDF p. 133; printed p. 1223."),),
    ("Rural-highway applicability is absent from schema 1.0.0.",
     "The 'first warning sign' endpoint is ambiguous: first encountered upstream versus Table 6B-1's nearest sign. No endpoint is selected for the 8S–12S recommendation."),
)
Z022B = RuleMetadata(
    "mutcd.Z-022-B", "Open-highway advance warning extent", "GUIDANCE",
    (Citation(_SOURCE, "Z-022-B — GUIDANCE — Open-highway advance warning extent",
              "Federal MUTCD §6B.04, para. 06; PDF p. 133; printed p. 1223."),),
    ("Open-highway conditions, where two or more advance warning signs are normally used, are absent from schema 1.0.0. The 1,500 ft recommendation is not a universal rural requirement.",),
)


def _not_evaluable(metadata):
    def evaluate(document):
        return RuleResult(metadata.rule_id, "not_evaluable", False,
                          reason=" ".join(metadata.limitations))
    return evaluate


SIGN_RULES = tuple(Rule(metadata, _not_evaluable(metadata))
                   for metadata in (Z026, Z020, Z022, Z022B))
