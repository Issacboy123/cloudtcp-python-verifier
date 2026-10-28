"""Register every TCP-W1-1 rule: evaluable logic or explicit not_evaluable stub."""

from rules.w1_common import load_w1_sections, not_evaluable_rule
from rules.w1_evaluable import EVALUATORS, evaluable_rules

# Schema / judgment gaps for rules that cannot emit production findings yet.
STUB_LIMITATIONS = {
    "SIGN-01": (
        "Roadway category and agency urban low/high speed classification are absent from schema 1.0.0.",
        "Federal Table 6B-1 defaults cannot be selected without those facts.",
    ),
    "SIGN-02": (
        "Urban-street applicability is absent from schema 1.0.0.",
    ),
    "SIGN-03": (
        "Rural-highway and open-highway applicability are absent from schema 1.0.0.",
        "The 'first warning sign' endpoint (upstream-first vs nearest) is unresolved.",
    ),
    "SIGN-04": (
        "Single-sign / low-speed residential applicability is absent from schema 1.0.0.",
    ),
    "SIGN-05": (
        "Freeway/expressway classification is absent from schema 1.0.0.",
    ),
    "SIGN-06": (
        "Field-adjustment and engineering-judgment overrides are user/agency inputs, not schema facts.",
    ),
    "SIGN-07": (
        "Roadway type needed to choose the 100 ft vs 1,000 ft closest-sign band is absent.",
    ),
    "SIGN-08": (
        "Requires ordered advance-warning sign identification and approach direction; "
        "supported warning-code policy and unique approach geometry are not established for production findings.",
    ),
    "SIGN-09": (
        "Crossroad / major driveway inventory is absent from schema 1.0.0.",
    ),
    "SIGN-10": (
        "Work-road vs detour-road association for W20-1 is absent from schema 1.0.0.",
    ),
    "SIGN-12": (
        "OPTION: dual-side, in-roadway portable, and barricade mounting are allowed, not required.",
    ),
    "SIGN-13": (
        "Sign mounting height above pavement is absent from schema 1.0.0.",
    ),
    "SIGN-14": (
        "Sign mounting height and sidewalk/curb context are absent from schema 1.0.0.",
    ),
    "SIGN-15": (
        "Portable-support mounting height is absent from schema 1.0.0.",
    ),
    "SIGN-16": (
        "Roadway category (rural/urban with or without curb) needed for lateral offset bands is absent.",
    ),
    "SIGN-17": (
        "Sidewalk / bicycle-facility polygons and ADA clear-width facts are absent from schema 1.0.0.",
    ),
    "SIGN-18": (
        "Installation duration and Part 2 mounting-height compliance are absent from schema 1.0.0.",
    ),
    "SIGN-19": (
        "Barricade rail coverage ratios and ground clearance for large signs are absent from schema 1.0.0.",
    ),
    "SIGN-22": (
        "Whether both directions share a single lane is not established beyond optional free text.",
    ),
    "SIGN-23": (
        "Full roadway closure vs reduced-lane operation distinction needs facts beyond type alone for R11-2 placement.",
    ),
    "SIGN-24": (
        "Shoulder-work legend variants and freeway sequence ordering need sign-schedule facts not fully modeled.",
    ),
    "SIGN-25": (
        "Whether END ROAD WORK is used and where the termination area ends is engineering judgment.",
    ),
    "SIGN-26": (
        "TTC zone length in miles is not a first-class schema field.",
    ),
    "SIGN-27": (
        "Sidewalk closure geometry and parallel-sidewalk facts are absent from schema 1.0.0.",
    ),
    "SIGN-28": (
        "Audible information device presence is absent from schema 1.0.0.",
    ),
    "SIGN-29": (
        "Curb parking restriction extents are absent from schema 1.0.0.",
    ),
    "SIGN-30": (
        "Advisory plaque pairing and agency speed determination are absent from schema 1.0.0.",
    ),
    "SHLD-02": (
        "Operation duration (≤60 minutes) and vehicle lighting equipment facts are absent from schema 1.0.0.",
    ),
    "SHLD-03": (
        "Work-space offset behind curb/barrier/roadway edge is absent from schema 1.0.0.",
    ),
    "TAPER-04": (
        "OPTION / engineering judgment: taper adjustments near ramps, crossroads, and curves.",
    ),
    "TAPER-05": (
        "Whether a shoulder is used as a travel lane is absent from schema 1.0.0.",
    ),
    "TAPER-06": (
        "Near-side intersection geometry and dual-direction merge intent are absent from schema 1.0.0.",
    ),
    "BUFFER-02": (
        "Work/storage occupancy of buffer space and lateral buffer width are not modeled; lateral width is judgment.",
    ),
    "CHAN-02": (
        "Whether devices could lead traffic out of the intended path (Fig. 6P-39) is not a schema fact.",
    ),
    "CHAN-03": (
        "Cone height, night/high-speed context, and retroreflectorization are absent from schema 1.0.0.",
    ),
    "CHAN-04": (
        "Tubular marker dimensions and pavement attachment are absent from schema 1.0.0.",
    ),
    "CHAN-05": (
        "Vertical panel stripe geometry is absent from schema 1.0.0.",
    ),
    "CHAN-06": (
        "Drum dimensions and stripe pattern are absent from schema 1.0.0.",
    ),
    "CHAN-07": (
        "Barricade rail length/stripe and retroreflective area are absent from schema 1.0.0.",
    ),
    "CHAN-08": (
        "Barricade type selection and permitted-use legend requirements lack typed schema fields.",
    ),
    "CHAN-09": (
        "Direction Indicator Barricade series placement is absent from schema 1.0.0.",
    ),
    "CHAN-10": (
        "Temporary barrier use on a merging taper and low-speed urban classification are absent.",
    ),
    "CHAN-11": (
        "Lane-separator base dimensions and pedestrian opening width are absent from schema 1.0.0.",
    ),
    "CHAN-12": (
        "Warning-light mode, flash rate, and mounting height are absent from schema 1.0.0.",
    ),
    "PED-01": (
        "Pedestrian facility width and passing-space intervals are absent from schema 1.0.0.",
    ),
    "PED-02": (
        "Detectable closure-plate and hand-trailing dimensions are absent from schema 1.0.0.",
    ),
    "PED-03": (
        "Temporary ramp slope and landing dimensions are absent from schema 1.0.0.",
    ),
    "PED-04": (
        "Pedestrian diversion routing and signal covering are absent from schema 1.0.0.",
    ),
    "PED-05": (
        "Crosswalk occupancy by the work space is absent from schema 1.0.0.",
    ),
    "SHLD-01": (
        "Paved shoulder width (≥8 ft) is absent from schema 1.0.0.",
    ),
    "ARROW-01": (
        "Major multi-lane / heavy-volume / limited-sight classification for arrow mode is absent.",
    ),
    "ARROW-04": (
        "Shoulder width and precise 'beginning of merging taper' placement need richer geometry than schema 1.0.0.",
    ),
    "ARROW-05": (
        "Relative board placement across sequential tapers needs closed-lane identity facts not in schema 1.0.0.",
    ),
    "ARROW-06": (
        "Arrow board type/size/legibility/element count are absent from schema 1.0.0.",
    ),
    "ARROW-07": (
        "Mounting height, flash rate, dimming, and vehicle warning lights are absent from schema 1.0.0.",
    ),
    "FLAG-01": (
        "Flagger control device (paddle/flag/AFAD) is absent from schema 1.0.0.",
    ),
    "FLAG-03": (
        "Escape route, isolation from equipment, and in-lane timing are absent from schema 1.0.0.",
    ),
    "FLAG-04": (
        "Night illumination and emergency exception flags are absent from schema 1.0.0.",
    ),
    "FLAG-05": (
        "End-to-end visibility and designated coordinator communication are absent from schema 1.0.0.",
    ),
    "FLAG-06": (
        "Flag-transfer method and one-way segment length are absent from schema 1.0.0.",
    ),
    "FLAG-07": (
        "Horizontal/crest curve location relative to the one-lane taper is absent from schema 1.0.0.",
    ),
    "FLAG-08": (
        "AFAD equipment, attendance, and Method 1/2 staffing are absent from schema 1.0.0.",
    ),
    "FLAG-09": (
        "STOP/SLOW AFAD sign height and size are absent from schema 1.0.0.",
    ),
    "FLAG-10": (
        "Planned closure duration (≤20 minutes) and daytime-only constraint are absent from schema 1.0.0.",
    ),
}


def stub_rules():
    sections = load_w1_sections()
    rules = []
    for rule_id in sections:
        if rule_id in EVALUATORS:
            continue
        limits = STUB_LIMITATIONS.get(
            rule_id,
            ("Required applicability or measurement facts are absent from schema 1.0.0.",),
        )
        rules.append(not_evaluable_rule(rule_id, *limits))
    return tuple(rules)


def w1_rules():
    """All TCP-W1-1 rules in document order: stubs and evaluators interleaved by ID order in the file."""
    sections = load_w1_sections()
    evaluable = {rule.metadata.rule_id.split(".", 1)[1]: rule for rule in evaluable_rules()}
    ordered = []
    for rule_id in sections:
        if rule_id in evaluable:
            ordered.append(evaluable[rule_id])
        else:
            limits = STUB_LIMITATIONS.get(
                rule_id,
                ("Required applicability or measurement facts are absent from schema 1.0.0.",),
            )
            ordered.append(not_evaluable_rule(rule_id, *limits))
    return tuple(ordered)
