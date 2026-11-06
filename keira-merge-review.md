# Keira branch merge review

Follow-up: pull request #2 was merged into main. The subsequent fixes are now
implemented locally on `fix/w1-rule-correctness`, with **538 tests passing**.
They preserve partial findings, remove unsupported applicability assumptions,
correct sign ordering and exact speed lookup, retain evaluator limitations,
replace runtime Markdown parsing with explicit metadata, add CLI W1 selection,
version and validate report scores, and remove duplicate extensionless examples.
Checks lacking facts in schema 1.0.0 now report `not_evaluable`; this does not
make those checks fully implemented. See [current W1 coverage](docs/w1-coverage.md)
for the resulting behavior. The original pre-merge findings below are retained
as review history. These follow-up changes have not been committed or pushed.

Reviewed 2026-11-05. Draft pull request: https://github.com/Issacboy123/cloudtcp-python-verifier/pull/2. Source: `keira-rules-verifier` (`63c6469b33165f05bfe5eb69bcfb6cf786683b3e`). Target: remote `main` (`9d6ee945ed96d1c1b0fbd609734b667462ac3de8`).

## Merge readiness

The source contains all target commits and is one commit ahead, zero behind. There are no divergent edits to resolve at these revisions. The merge needs correctness changes rather than textual conflict resolution. Recommendation: keep this pull request in draft until the high-priority findings below are addressed.

The current local checkout is `feat/json-verification` and has three additional commits beyond remote main; those commits are outside this pull request. The local `main` reference is also older than remote main. This review uses freshly fetched remote references and isolated exports, leaving the checkout unchanged.

## Important differences

| Area | Main | Keira branch |
| --- | --- | --- |
| Default behavior | Five initial rules; four sign checks are not evaluable | Same five default rules |
| Additional coverage | No W1 registry | Opt-in `W1_REGISTRY`: 76 entries, 12 evaluators, 64 not-evaluable placeholders |
| API selection | Optional Python rule registry | Select W1 with `verify_document(..., registry=W1_REGISTRY)` or `verify_file(...)` |
| CLI | Uses default registry | Still uses default registry; no W1 selection flag |
| Reports | No rule score | Adds optional numeric `RuleResult.score` and scores in finding values; report version stays `1.0.0` |
| Runtime data | Schema and Python rules | Additionally parses `TCP-W1-1 Rules.md` at verifier import to construct W1 metadata |
| Change size | Baseline | 316 files changed, 18,342 insertions, 4 deletions; 304 files are W1 example plans |

No changes to input schema or dependency requirements. The examples include 152 JSON files plus 152 extensionless counterparts with identical content.

## High-priority findings

These findings concern implementation behavior relative to the branch's own extracted rule document, not an independent regulatory certification.

1. **Flagger stopping-distance check measures the wrong relationship.** `rules/w1_evaluable.py:291` compares the absolute distance between the flagger and the smallest station of a work zone. The source describes the distance available to approaching road users to stop at the intended stopping point. With the supplied compliant FLAG-02 plan, moving the flagger to station 1500 inside work zone 1000-2000 still returns `pass`, score 1.0. Work-zone distance does not establish approach sight distance. Add explicit stopping-point, approach, and sight-distance facts; return `not_evaluable` until the required facts exist.

2. **Roadway applicability is inferred without sufficient facts.** `rules/w1_evaluable.py:373` requires W20-5/5a based only on lane counts. Changing the supplied SIGN-20 plan to `shoulder_closure` and removing signs still returns a STANDARD failure, without establishing a through-lane closure. At `:503`, a three-lane road with one closed lane and no boards produces a STANDARD failure even though freeway status is absent; the source distinguishes freeway closure from more general multiple-lane closure. At `:465`, two lanes alone are treated as a two-way road. Gate rules on explicit relevant facts and preserve `not_evaluable` for unknown classifications.

3. **Sign-size evaluation assumes one road tier and exact dimensions.** `rules/w1_evaluable.py:424` treats conventional dimensions as exact equality without road classification. Changing the supplied W20-1 SIGN-31 plan to `48x48` returns a STANDARD failure, although the branch's source lists that size for freeway/expressway signs. Add a typed road tier and an explicit supported size policy, or keep this check unevaluable when the tier is unknown. Do not reject larger signs solely because they differ from the conventional row.

4. **Advance-warning presence is mistaken for correct placement.** `rules/w1_evaluable.py:402` passes SIGN-21 if any W20-7 exists anywhere. Moving the example's W20-7 to station 2100, beyond the work zone, still returns `pass`, score 1.0. SIGN-20 likewise does not establish upstream placement or correct W20-5 versus W20-5a selection. Associate signs with approaches and flaggers/closures, verify travel order and sign variant, and return incomplete results when direction cannot be established.

5. **A later unknown taper erases earlier known violations.** `rules/w1_evaluable.py:64` and `:103` return immediately on an unknown required width. A 100-ft merge taper at 45 mph with a 10-ft width fails alone, but appending a separate zero-width taper changes the rule to `not_evaluable` with no findings. Retain known findings and return `fail` with `complete=False` and an explanation for unevaluable subjects, as supported by the existing result contract.

6. **Evaluator limitations are missing from emitted metadata.** Each evaluator constructs metadata with important assumptions, but `evaluable_rules()` at `rules/w1_evaluable.py:549` registers fresh `w1_metadata(rule_id)` without those limitations. For example, the registry's TAPER-01 limitations are empty. As a result, reports omit caveats such as the invented 15-25-ft spacing band, ignored sign ordering, and road-tier assumptions. Register the same complete metadata used by evaluation and verify those limitations appear in serialized reports.

## Additional integration issues

- **Fractional speeds are silently truncated.** BUFFER-01 and FLAG-02 use `int(_posted_speed_mph(...))` at `rules/w1_evaluable.py:278` and `:306`. A valid 45.9-mph FLAG-02 plan passes using the 45-mph row, despite the documented exact-key policy. Preserve the original number and reject unsupported table keys as `not_evaluable`.
- **An optional registry introduces a global startup dependency.** `verifier.py:23` eagerly builds W1_REGISTRY by parsing Markdown (`rules/w1_common.py:15`). Temporarily removing that document in the isolated export makes even `python -m verifier --help` fail with an uncaught FileNotFoundError. Prefer explicit Python metadata or lazy W1 loading; if retained as runtime data, validate and distribute it deliberately. Include a missing/malformed-source regression test.
- **Define score compatibility and interpretation.** The extra field changes every serialized rule result while report version remains 1.0.0. Confirm whether additive fields are allowed; update API documentation and version policy accordingly. Text reports do not show rule-level scores. BUFFER-01 intentionally passes with a score below one because it is OPTION; document that score is not a substitute for status, completeness, or compliance.
- **Clarify how W1 should be exposed.** If users should run W1 from the CLI, add an explicit registry selection option and test it. If Python-only access is intentional, retain that distinction clearly. Do not automatically replace the default registry or double-count overlapping T-013/TAPER-02 checks.
- **Remove redundant example copies.** All 152 extensionless examples duplicate their .json counterparts exactly. Keep the JSON versions unless there is a documented consumer requiring both.

## Verification and proposed merge work

- Fresh remote references establish main is the source branch's ancestor: no rebase or conflict resolution is required at these revisions.
- Python 3.14.7, existing development environment: main **362 passed**; Keira **453 passed**. Full suites ran successfully outside the sandbox after sandbox temporary-directory permissions prevented reliable initial runs.
- Additional probes used schema-valid modifications of supplied examples and confirmed the behaviors described above. The existing tests cover selected per-rule compliant/violating plans but miss these applicability, ordering, incomplete-subject, and metadata cases.
- Before merging: fix or conservatively disable unsupported evaluators, retain partial failures, preserve limitations, add focused regression cases, decide the score/report and CLI contracts, and remove unnecessary example duplication. Re-run both existing tests and the new edge-case regressions.
- This review does not modify implementation code or merge the branches.
