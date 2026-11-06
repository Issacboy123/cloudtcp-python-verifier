# API and CLI reference

See the [README](../README.md) for setup and quick-start commands.

## CLI behavior

The [75-ft example](../examples/taper-75ft.json) has a downstream taper from station
1000 to 1075 feet. The [violating example](../examples/taper-125ft.json) ends at 1125.
The [invalid example](../examples/invalid.json) deliberately omits required fields.
Malformed JSON also produces exit 2 with parsing diagnostics. The complete JSON
report goes to stdout without logs or tracebacks; incidental evaluator stdout is
redirected to stderr. Text includes every finding, local-source and MUTCD citation,
errors, incomplete/unexecuted checks, and coverage limitations. `--format` accepts
only `json` or `text`; missing/extra arguments and unknown flags return a structured
JSON report with `cli_arguments` and exit 2, even when `--format text` was requested.
`--help` prints usage to stdout and exits 0 without reading input or running rules.

## Using another working directory

From another directory, use the checkout on `PYTHONPATH` and absolute input paths.
In PowerShell, start in the repository root and capture its absolute path before
changing directories:

```powershell
$project = (Get-Location).Path
$env:PYTHONPATH = $project
Set-Location $env:TEMP
& "$project/.venv/Scripts/python.exe" -m verifier "$project/examples/taper-75ft.json"
# exit 3; the same PYTHONPATH supports `from verifier import verify_file`
Set-Location $project
```

On macOS, likewise start in the repository root:

```sh
project="$PWD"
export PYTHONPATH="$project${PYTHONPATH:+:$PYTHONPATH}"
cd "${TMPDIR:-/tmp}"
"$project/.venv/bin/python" -m verifier "$project/examples/taper-75ft.json"
# exit 3; the same PYTHONPATH supports `from verifier import verify_file`
cd "$project"
```

## Input validation and Python API

Python API use, from the checkout root or with the checkout on `PYTHONPATH`:

```python
from ingestion import InputValidationError, load_document, validate_document

document = load_document("examples/taper-75ft.json")
validate_document(document)  # returns the same dictionary without mutation
```

Both APIs raise `InputValidationError` for expected input failures. Its
`diagnostics` tuple is sorted by JSON Pointer `path`, `code`, and `message`.
Each diagnostic also has optional `schema_path`, `line`, and `column` fields.
The root pointer is the empty string. Missing-property errors point to the
containing object; duplicate IDs and unresolved references point to the field.
Schema errors use `schema.<keyword>` codes; parsing, JSON-value, and integrity
errors have descriptive codes such as `invalid_json`, `duplicate_key`,
`non_finite_number`, `duplicate_id`, and `unresolved_reference`.

Validation stops at the first failing boundary: JSON-compatible values, schema,
then integrity. Independent failures within that boundary are aggregated.
Missing/unreadable input paths are input failures; unexpected I/O faults and
missing, invalid, or unresolvable schemas propagate as operational exceptions.
Schema retrieval is local and external retrieval is disabled.
The JSON boundary honors the interpreter's integer conversion limit: oversized
integer text and parsed integers that the standard JSON encoder cannot represent
produce structured input diagnostics without changing global interpreter settings.

Verification returns a report for both valid and expected-invalid input:

```python
from verifier import verify_document, verify_file, load_document, InputValidationError

report = verify_file("examples/taper-75ft.json")
print(report.to_json())
code = report.exit_code  # shared exit decision; does not exit the Python process
assert code == 3
assert report.to_dict() == verify_document(load_document("examples/taper-75ft.json")).to_dict()
```

`verify_document(document)` accepts parsed site dictionaries. Both verification
APIs validate before executing any rules. Invalid input yields structured
`errors`, no rule results, and `evaluation_complete=False`. Unexpected I/O,
schema/configuration, and input-copy faults propagate to Python callers.
Evaluator exceptions and malformed output become per-rule error results while
independent rules continue. `load_document` and `InputValidationError` are
re-exported unchanged from ingestion.

At the CLI boundary, unexpected operational exceptions become structured
`operational_error` diagnostics and exit 4. Completed findings, results and gaps
are retained; checks that execution did not reach are listed as limitations.
If text formatting or output encoding fails, the CLI falls back to an ASCII-safe
JSON error report. If stdout is unavailable (including a broken pipe), that
structured report goes to stderr and the process exits 4.
`input_valid=False` on an early operational error means validation did not finish,
not that the input was proved invalid. Python API infrastructure exceptions still
propagate to callers, including a copy failure after earlier rules ran.

## Report fields and source coverage

Reports provide version `2.0.0`, `input_valid`, metadata and citations,
`evaluation_complete`, every rule result and finding, structured errors, and
coverage limitations. `registered_rule_ids` lists selected registry entries;
`automated_rule_ids` identifies checks whose mapped clauses are all classified
as automated; partial checks remain visible in `source_coverage`. The deprecated
`implemented_rule_ids` remains an alias for the registered list for compatibility;
it must not be interpreted as a count of fully implemented checks.
`source_coverage` accounts for the source entries and distinguishes executable
coverage from missing input facts, review requirements, source dependencies, and
informational provisions. Source accounting does not establish plan compliance. Each clause records its
source heading and citation, classification, canonical check ID when applicable,
and limitations. Dispositions are `automated`, `partial`, `input_blocked`,
`review_required`, `source_blocked`, and `informational`. They describe available
coverage, while rule results describe what happened for the particular input.

## Registries and jurisdictions

`ALL_REGISTRY` is the default (`DEFAULT_REGISTRY` is its alias). Select it with
`--registry all` or `--registry default`, or pass `registry=ALL_REGISTRY` to the
Python API. The catalog covers 381 headings in
[TCP Rules Document.md](../TCP%20Rules%20Document.md) and 76 headings in
[TCP-W1-1 Rules.md](../TCP-W1-1%20Rules.md). These 457 source entries overlap;
they are not 457 independent requirements. Shared checks retain source traceability
and avoid duplicate findings. Mixed headings retain the classification of each
substantive clause rather than downgrading mandatory clauses to guidance.

For `site.state == "CA"`, explicit California replacements and supplements apply
to the federal baseline. Other states receive federal coverage only; no other
state's supplements are supplied. State-highway ownership, freeway status,
application numbers, and exceptions are not inferred from names or free text.
Missing facts leave affected checks incomplete. Input schema 1.0.0 is unchanged;
no evidence file, context argument, external-source retrieval, or approval workflow
is added. Unavailable standards and unresolved extraction errors remain explicit
limitations.

`LEGACY_REGISTRY` (`--registry legacy`) preserves the original five entries, in
order: `mutcd.Z-026`, `mutcd.Z-020`, `mutcd.Z-022`, `mutcd.Z-022-B`, and
`mutcd.T-013`. Four sign entries remain unevaluable, and the downstream-taper
length check runs.

`W1_REGISTRY` (`--registry w1`) preserves the historical 76-entry extraction.
It contains 64 explicit placeholders and 12 specialized handlers; some handlers
can establish only missing facts or inapplicability. See
[W1 coverage and interpretation](w1-coverage.md) for their supported behavior.
Registry selection chooses checks; it does not supply missing facts.

## Scores and report versions

Each report result retains its status and includes a required integer `score`:
`pass` receives `1`; `fail`, `not_applicable`, `not_evaluable`, and `error` receive
`0`. Incomplete failures retain known findings, `complete=False`, and their
reason. A zero score alone does not distinguish a violation from missing facts,
inapplicability, or an execution error; read status, completeness, findings, and
limitations alongside it. An OPTION such as BUFFER-01 that passes receives `1`,
even when its internal evaluator assigns a fractional grade. Existing scores in
finding measurements become integer `0`; other measurements and citations are
preserved, and findings without a score do not gain one. Text reports display
rule scores alongside status and completeness.

Report version 2.0.0 replaces fractional/nullable reported scores with this binary
contract. `Report.rule_results` contains `ReportRuleResult` objects; direct
evaluator `RuleResult` objects retain their existing optional graded scores and
validation contract. Version 1.1.0 introduced rule-result scores and 1.2.0 added
source-coverage fields. Consumers should tolerate additive fields within a major
report version; the input schema remains version 1.0.0. Scores are not a regulatory
compliance percentage, and no aggregate plan score is supplied.

Example plans are under `examples/w1/<RULE-ID>/compliant.json` and
`violating.json`. Those historical names describe the intended scenarios; they
do not guarantee a pass or failure when the input lacks required facts. W1
metadata is defined explicitly in Python, with source citations checked against
the extracted document in tests. The Markdown document is not runtime input.

## Legacy rules and geometry

In the legacy registry, the four sign provisions always report `not_evaluable`: schema 1.0.0 lacks
roadway/applicability classifications. Names, highway numbers, speeds and free
text cannot supply those facts. Z-022 also retains the unresolved meaning of
"first warning sign"; Z-022-B's 1,500 ft recommendation concerns open-highway
conditions rather than every rural highway. CA-005 is the California replacement for Z-026; its roadway-category and
speed-band/footnote dependencies remain explicit. The federal spacing table is
not applied to California as a substitute.

| Registered sign entry | Initial coverage and missing facts |
|---|---|
| `mutcd.Z-026` (former SIGN-01) | Federal A/B/C advisory spacing; roadway category and agency/owner urban speed classification absent. California replacement CA-005 requires roadway facts, with interpolation and flagged footnote issues unresolved. |
| `mutcd.Z-020` (former SIGN-02) | Urban nearest warning sign 4S–8S recommendation; urban-street applicability absent. |
| `mutcd.Z-022` (former SIGN-03 distance) | Rural 8S–12S recommendation; rural applicability absent and “first warning sign” endpoint unresolved between first encountered upstream and nearest sign. |
| `mutcd.Z-022-B` (former SIGN-03 extent) | Open-highway advance-warning extent, nominally 1,500 ft; open-highway applicability absent. This is not a universal rural minimum. |

T-013 checks every downstream taper against the inclusive 50–100 ft advisory
range. Each deviation produces a cited warning with the element ID, optional
zone ID, input paths, measured feet and recommended range. No downstream taper
returns `not_applicable`. Length uses the absolute station difference, converted
from meters with 0.3048 meters per foot; lateral offsets do not contribute.
Explicitly suffixed `_ft`, `_mph` and `_inches` fields retain their declared
units. Boundary comparisons absorb only two floating-point ULPs at each bound
for meter conversion roundoff; station-origin uncertainty does not widen the
range. Input endpoint errors larger than that allowance remain deviations.
Findings do not assess engineering justification or field adjustment.

With the legacy registry, valid input remains `evaluation_complete=False`
because of the sign coverage gaps. Its exit code is 1 when a taper warning is
present, otherwise 3. The full registry also retains every unresolved applicable
check; complete source accounting never turns missing evidence into a pass. An explicitly empty custom registry still reports empty
coverage and no pending checks.

## Result statuses

Interpret each result using both `status` and `complete`:

| Status | Meaning |
|---|---|
| `pass` | All applicable subjects passed; complete. |
| `fail` | Known findings exist; `complete=False` also signals unevaluated subjects. |
| `not_applicable` | Input facts establish no applicable subjects; complete. |
| `not_evaluable` | Missing facts or ambiguous interpretation; incomplete, with a reason. |
| `error` | Evaluator failure or malformed output; incomplete, with diagnostics. |

Invalid input yields no rule results. Empty findings alone do not establish a
complete evaluation. `evaluation_complete` requires valid input, no execution
errors and every implemented result complete. A report can be complete and have
findings. Read `errors`, `limitations`, and every result alongside `findings`.

Private geometry/calculation helpers retain A/B/C distances, the urban 4S–8S
range, rural 8S–12S numeric endpoints and open-highway warning-area extent.
They do not create production sign findings. Approach geometry requires exactly
one nondegenerate, non-overlapping warning/transition pair, allowing shared zone
endpoints and either station direction. Warning-sign calculations require
explicitly selected IDs, a single traffic direction and known facing; opposite
facing signs are excluded and tied sign stations are ambiguous. Test selection
supports W20-1 only and excludes R4-7 and unknown codes; no general classifier or
public selection/context argument is provided.

## Serialization and exit codes

`Report.to_dict()` returns detached JSON values; `to_json()` uses sorted keys,
two-space indentation, a trailing newline, finite numbers, and no timestamps.
Rule results follow registry order. Findings sort by rule ID, then the sorted
tuple of input pointers; errors sort by rule ID then input pointer. Canonical
JSON breaks ties (error code/message precede that tie-break). The same order is
used inside each result. Repeated findings are preserved. Determinism assumes
evaluators themselves return deterministic data.

`exit_code(report, operational_error=False)` and `report.exit_code` apply this
precedence: **4** operational/rule error, **2** invalid input, **1** any finding,
**3** incomplete evaluation without findings, **0** all implemented checks
resolved without findings. Finding severity `error` indicates a STANDARD
violation and yields 1; an execution error yields 4. The CLI uses structured
operational errors without changing API exceptions.

| Exit | Condition, in precedence order |
|---|---|
| 4 | Operational or rule execution error, even alongside findings/gaps. |
| 2 | Invalid input or command arguments; no rules execute. |
| 1 | Any finding, including GUIDANCE warnings, even with incomplete checks. |
| 3 | Incomplete evaluation without findings or execution errors. |
| 0 | All implemented checks resolved without findings (`--help` also exits 0). |

Higher-precedence exits retain known findings and gaps in the report. Exit 0
addresses implemented coverage only. Unresolved requirements normally leave full-registry inputs at exit 3 or 1
unless an execution error requires exit 4.

## Rule authoring

To author a rule, establish applicability from the existing input, copy source
citations into metadata, implement a single-dictionary evaluator with private
geometry helpers as needed, register it explicitly, and test applicability,
boundaries, units, findings, missing facts and isolation. The
[rule-authoring guide](rule-authoring.md) supplies the executable synthetic
template and full contracts. No schema extensions or additional caller facts
are accepted. Run the complete suite, exercise the CLI examples, and resolve
review findings before completing a change. Keep the source catalog and its
coverage dispositions synchronized with any production rule changes.
