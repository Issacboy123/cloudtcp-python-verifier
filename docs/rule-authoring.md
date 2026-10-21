# Authoring Python rules

Rules are ordinary Python functions accepting one validated site dictionary.
Register `Rule(metadata, evaluator)` entries explicitly in `RuleRegistry` order.
Pass the registry using `verify_document(site, registry=registry)` or
`verify_file(path, registry=registry)`. This selects executable rules, not caller
context. The default production registry contains the five initial
GUIDANCE entries documented in the README. There is no rule discovery, DSL,
or plugin protocol.

Use a unique namespaced ID such as `agency.rule-name` or `mutcd.Z-026`.
`RuleMetadata` requires an ID, readable title, classification, and nonempty
tuple of `Citation` records. Each citation includes `source_document`,
`local_reference`, and `mutcd_reference`. Copy exact source headings and MUTCD
references from the supplied document when implementing production rules.
Another source document needs only different metadata. Record unsupported
source interpretations and dependencies in metadata `limitations`.

This executable synthetic template illustrates missing facts, established
inapplicability, and complete or partial findings without creating a production
rule. The threshold and citations are synthetic acceptance examples only:

```python
from rule_framework import Citation, Finding, Rule, RuleMetadata, RuleRegistry, RuleResult
from verifier import verify_document

META = RuleMetadata(
    rule_id="example.synthetic",
    title="Synthetic station check",
    classification="GUIDANCE",
    citations=(Citation("synthetic.md", "EXAMPLE-1", "Synthetic MUTCD reference"),),
    limitations=("Synthetic example; not a compliance requirement.",),
)

def evaluate(site):
    subjects = site["elements"]
    if not subjects:
        return RuleResult(META.rule_id, "not_applicable", True,
                          reason="The input contains no elements.")
    findings = []
    missing = False
    for index, element in enumerate(subjects):
        position = element.get("position")
        if position is None:
            missing = True
            continue
        station = position["station"]
        if station < 0:  # synthetic condition, not a production requirement
            findings.append(Finding(
                rule_id=META.rule_id, severity="warning",
                classification=META.classification,
                message="Synthetic negative-station finding.",
                element_ids=(element["element_id"],),
                zone_ids=(element["zone_id"],) if "zone_id" in element else (),
                paths=(f"/elements/{index}/position/station",),
                citations=META.citations,
                values={"actual": station, "threshold": 0}, units=site["site"]["units"],
            ))
    reason = "Some elements lack point positions." if missing else None
    if findings:
        return RuleResult(META.rule_id, "fail", not missing, tuple(findings), reason)
    if missing:
        return RuleResult(META.rule_id, "not_evaluable", False, reason=reason)
    return RuleResult(META.rule_id, "pass", True)

REGISTRY = RuleRegistry((Rule(META, evaluate),))
# report = verify_document(validated_site, registry=REGISTRY)
```

Applicability must follow supplied facts. Missing or ambiguous applicability is
`not_evaluable`, never `pass` or `not_applicable`. Geometry belongs in ordinary
private helpers with documented units, direction, subject selection, and ambiguity
handling; the framework imposes no geometry or sign-category inference. Do not
add context arguments or change the input schema to make a rule evaluable.

The exact result matrix is:

| Status | complete | Findings | Required reason |
|---|---|---|---|
| pass | true | none | no |
| fail | true or false | one or more | when incomplete |
| not_applicable | true | none | yes |
| not_evaluable | false | none | yes |
| error | false | none | yes |

Known findings plus unevaluated subjects must retain every finding as incomplete
`fail`. Use `not_evaluable` only when there are no findings. Overall completeness
requires valid input, no execution errors, and complete results for every rule.
The engine validates the matrix; the author must establish the factual meaning
of pass, inapplicability, and missing facts in evaluator logic and tests.

Use `STANDARD` with severity `error`, or `GUIDANCE` with severity `warning`.
`OPTION` and `SUPPORT` may return no-finding results but cannot independently
produce violations. Findings must match metadata ID, classification, and the
exact citation tuple. Every finding needs a readable message, ID tuples (empty
is permitted, including for site-level findings), a nonempty tuple of RFC 6901
input pointers (root is `""`), and citations. Optional `values` is a dictionary
of names to finite `int`/`float` values (no booleans); `units` is optional text.
Escape pointer segments with `~0` for `~` and `~1` for `/`.

Return tuples for findings, errors, citations, IDs, paths, and limitations. A
returned `error` may include structured `Diagnostic` entries with matching rule
IDs, codes, messages and input paths; otherwise the engine adds `rule_error`.
Crashes become `rule_exception`, invalid output becomes `malformed_result`.
These errors are separate from input diagnostics. No error result has findings.

Each invocation receives a deep copy of the validated site. Accepted output is
also detached before the next evaluator runs. Registry metadata is immutable.
This isolates data mutation; Python evaluators remain trusted code and should
avoid global state, I/O, clocks, random output, and retaining caller objects.

Add evaluator tests for applicability, missing facts, every subject, boundaries,
units, multiple findings, partial evaluation, citation fidelity, and unchanged
input. Framework acceptance uses only synthetic evaluators in
`tests/test_verifier.py`; ingestion validation tests live in `tests/test_ingestion.py`.
Initial-rule and private geometry checks live in `tests/test_initial_rules.py`
and `tests/test_geometry.py`. Geometry accepts explicitly selected warning IDs;
the tests select W20-1 and exclude R4-7 and unknown codes. Geometry never chooses
sign classes. Future executable sign rules must document a supported-code policy
and establish applicability without additional caller context. Current sign
entries remain unevaluable; numeric helpers are not proof of applicability.
Adding an evaluator or a new source citation requires registration and tests,
with no changes to engine execution or reporting.

CLI integration acceptance lives in `tests/test_cli.py`. It runs child processes
with synthetic registries to check all exit branches, partial findings, rule and
operational failures alongside retained findings/gaps, invalid-input short
circuiting, and checkout use from another working directory. The production CLI
accepts only one site file and the output format; it has no rule selection or
context flags. `main(argv)` returns the exit code; `python -m verifier` exits with
that code. Keep infrastructure exception conversion at this boundary so API
callers retain the established exception behavior. Before completing a change,
run the full test suite, exercise the CLI examples, and resolve review findings.
