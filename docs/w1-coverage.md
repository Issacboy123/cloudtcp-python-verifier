# W1 coverage and interpretation

Select the extracted W1 rules with `python -m verifier SITE.json --registry w1`
or pass `registry=W1_REGISTRY` to the Python API. This historical registry remains
available independently of the full catalog, which is now the default. Select
`--registry legacy` or pass `registry=LEGACY_REGISTRY` for the original five
entries. W1 includes 76 registered entries: 64 explicit
placeholders and 12 specialized handlers. Some handlers can establish only
inapplicability or missing facts under input schema 1.0.0.

| Entry | Supported behavior and limits |
| --- | --- |
| TAPER-01 | Computes merge-taper length from offset width and posted speed using the supplied formula branches. Unknown widths or unsupported speed branches leave subjects incomplete. |
| TAPER-02 | Checks shifting, shoulder, and downstream taper lengths. Known violations survive other subjects lacking required facts. The schema has no one-lane two-way taper type. |
| TAPER-03 | Reports missing evaluation facts for downstream tapers. The source's approximate 20-ft spacing has no authored numeric tolerance; the verifier does not invent a 15–25-ft acceptance band. |
| CHAN-01 | Checks supported channelizing-device spacing against bounds that can be established. Longitudinal overlap alone cannot prove a device line belongs to a taper. A barrier is not treated as a barricade. |
| BUFFER-01 | Grades declared upstream buffer lengths against exact speed keys from the supplied table. This OPTION does not produce violations for short buffers. Fractional speeds are not rounded or truncated into table rows. |
| FLAG-02 | Reports missing approach sight-distance and intended stopping-point facts when flaggers exist. Distance to a work-zone boundary cannot establish stopping sight distance. |
| SIGN-11 | Requires a known approach orientation and explicit matching sign facing. Left or center placement remains incomplete because the schema cannot establish permitted exceptions. |
| SIGN-20 | Reports missing through-lane identity, roadway applicability, and placement facts rather than inferring them from lane counts or sign presence. |
| SIGN-21 | Evaluates explicit W20-7 placement only when the approach, travel direction, sign facing, and flagger control direction establish the relationship. Unknown associations remain incomplete. |
| SIGN-31 | Reports missing road-tier facts rather than comparing all signs with an exact conventional-road size. |
| ARROW-02 | Reports missing freeway applicability or distinct board-to-closed-lane associations. Board count alone cannot establish the requirement. |
| ARROW-03 | Checks caution mode for explicitly declared shoulder closures. Lane count alone cannot establish two-way operation or lane-shift intent. |

Every registered handler carries its assumptions in rule metadata. Reports
include those limitations even when the handler passes or finds a violation.
Runtime metadata is explicit Python data in `rules/w1_metadata.py`; tests compare
all entries and citations with the extracted Markdown source. The source
document is for reference and test verification, not a runtime dependency.

In reports, missing facts produce `not_evaluable`, `complete=False`, and integer
`score=0`. Known violations plus unknown subjects produce incomplete `fail`
results that retain the known findings and also score `0`. Every reported `pass`
scores `1`; every other status scores `0`, including `not_applicable` and `error`.
Existing finding-level scores become integer `0` without changing measurements
or adding absent score fields. Direct W1 evaluators still return their existing
optional graded scores; the report projection changes neither evaluator logic
nor validation. These scores are not a measurement of overall plan compliance.
Always inspect status, completeness, findings, errors, and limitations together.

The example filenames `compliant.json` and `violating.json` are historical
scenario labels. A scenario remains unevaluable if schema 1.0.0 cannot express
the facts needed to decide it. Only the JSON copies are maintained.

Input schema 1.0.0 remains unchanged. Making the currently unsupported checks
fully evaluable requires separately designed input facts and source policies,
including roadway classification, through-lane identity, approach associations,
sight distance, sign-size tier, and permitted exceptions.

The full catalog accounts for the W1 source headings alongside the 381 entries
in `TCP Rules Document.md`. Source overlap is represented explicitly rather than
counted as independent coverage. The full registry can apply California provisions
using `site.state`, while this historical W1 registry retains its documented
behavior. Do not interpret W1-only results as evaluation of California replacements.

Report 2.0.0 retains separate `registered_rule_ids`, `automated_rule_ids`, and
`source_coverage`. The legacy `implemented_rule_ids` field remains a registered-list
alias. All 76 W1 IDs appearing there does not mean all 76 checks are automated.
Input 1.0.0 is unchanged, so full source accounting still includes explicit
missing-fact, review, and source-dependency outcomes.
