from rules.geometry import advance_signs_by_distance

#sign-01 checker

SIGN_01_TABLE = {
    "urban_low_speed":    {"A": 100, "B": 100,  "C": 100},
    "urban_high_speed":   {"A": 350, "B": 350,  "C": 350},
    "rural":              {"A": 500, "B": 500,  "C": 500},
    "expressway_freeway": {"A": 1000, "B": 1500, "C": 2640},
}
SIGN_01_CITATION = "MUTCD 11th Ed., Table 6B-1; Sec. 6B.04 para 07, p. 773"

def check_sign_01(plan, ctx):
    violations = []

    required = SIGN_01_TABLE.get(ctx.get("road_category"))
    if required is None:
        return violations

    to_ft = 1.0 if plan["site"]["units"] == "feet" else 3.28084
    tolerance_ft = ctx.get("sign_spacing_tolerance_ft", 0)

    zones = plan["zones"]
    adv = [z for z in zones if z["type"] == "advance_warning"]
    trans = [z for z in zones if z["type"] == "transition"]
    if not adv or not trans:
        return violations

    # Which way is traffic moving? Advance warning is upstream of the transition.
    adv_mid = sum(z["start_station"] + z["end_station"] for z in adv) / (2 * len(adv))
    trans_mid = sum(z["start_station"] + z["end_station"] for z in trans) / (2 * len(trans))
    direction = 1 if adv_mid < trans_mid else -1

    # Point A reference: where the transition begins, on the approaching side.
    if direction == 1:
        ref = min(z["start_station"] for z in trans)
    else:
        ref = max(z["end_station"] for z in trans)

    adv_lo = min(z["start_station"] for z in adv)
    adv_hi = max(z["end_station"] for z in adv)

    # Advance warning signs, with distance upstream of the reference point.
    signs = []
    for el in plan["elements"]:
        if el["type"] != "sign":
            continue
        st = el["position"]["station"]
        if not (adv_lo <= st <= adv_hi):
            continue
        dist_ft = (ref - st) * direction * to_ft
        if dist_ft > 0:
            signs.append((dist_ft, el["element_id"]))
    signs.sort()          # closest to the work zone first
    signs = signs[:3]     # table only defines A, B, C

    # Gap list: A = ref to 1st sign, B = 1st to 2nd, C = 2nd to 3rd
    prev_dist, prev_id = 0.0, "transition start"
    for label, (dist, sign_id) in zip("ABC", signs):
        gap = dist - prev_dist
        need = required[label]
        if gap < need - tolerance_ft:
            violations.append({
                "rule_id": "SIGN-01",
                "severity": "warning",           # Guidance = warning
                "element_ids": [sign_id],
                "message": (f"Spacing {label} between {prev_id} and {sign_id} is "
                            f"{gap:.0f} ft; minimum for {ctx['road_category']} is {need} ft"),
                "measured": gap,
                "required": need,
                "shortfall": need - gap,
                "citation": SIGN_01_CITATION,
            })
        prev_dist, prev_id = dist, sign_id

    return violations


#sign-02 checker
SIGN_02_CITATION = "MUTCD 11th Ed., Sec. 6B.04 para 04, p. 771"
URBAN = {"urban_low_speed", "urban_high_speed"}

def check_sign_02(plan, ctx):
    #nearest advance warning sign 4*S to 8*S ft from the TTC zone (urban)
    if ctx.get("road_category") not in URBAN:
        return []

    signs = advance_signs_by_distance(plan)
    if not signs:
        return []

    S = plan["typical_application"]["posted_speed_mph"]
    low = 4*S
    high = 8*S

    dist, sign_id = signs[0]
    if low <= dist <= high:
        return[]

    required = low if dist < low else high
    return [{
            "rule_id": "SIGN-02",
            "severity": "warning",                     # Guidance
            "element_ids": [sign_id],
            "message": (f"Nearest advance warning sign {sign_id} is {dist:.0f} ft from the "
                        f"transition; should be {low}-{high} ft at {S} mph"),
            "measured": dist,
            "required": (low, high),
            "shortfall": abs(dist - required),
            "citation": SIGN_02_CITATION,
    }]

#sign_03 checker
SIGN_03_CITATION = "MUTCD 11th Ed., Sec. 6B.04 para 06, p. 771"
RURAL = {"rural"}
SIGN_03_AREA_MIN_FT = 1500

def check_sign_03(plan, ctx):
    if ctx.get("road_category") not in RURAL:
        return []

    signs = advance_signs_by_distance(plan)
    if not signs:
        return []

    violations = []
    S = plan["typical_application"]["posted_speed_mph"]
    low = 8*S
    high = 12*S

    dist, sign_id = signs[0]
    if not (low <= dist <= high):
        required = low if dist < low else high
        violations.append({
            "rule_id": "SIGN-03",
            "check": "first_sign_distance",
            "severity": "warning",
            "element_ids": [sign_id],
            "message": f"Nearest sign {sign_id} is {dist:.0f} ft out; should be {low}-{high} ft at {S} mph",
            "measured": dist,
            "required": (low, high),
            "shortfall": abs(dist - required),
            "citation": SIGN_03_CITATION,
        })

    to_ft = 1.0 if plan["site"]["units"] == "feet" else 3.28084
    adv = [z for z in plan["zones"] if z["type"] == "advance_warning"]
    if adv:
        length = sum(abs(z["end_station"] - z["start_station"]) for z in adv) * to_ft
        if length < SIGN_03_AREA_MIN_FT:
            violations.append({
                "rule_id": "SIGN-03",
                "check": "advance_area_length",
                "severity": "warning",
                "element_ids": [z["zone_id"] for z in adv],
                "message": f"Advance warning area is {length:.0f} ft; should be at least {SIGN_03_AREA_MIN_FT} ft",
                "measured": length,
                "required": SIGN_03_AREA_MIN_FT,
                "shortfall": SIGN_03_AREA_MIN_FT - length,
                "citation": SIGN_03_CITATION,
        })

    return violations
            