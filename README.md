# cloudtcp-python-verifier

Python 3.11+ checkout-based ingestion, verification API and single-file CLI. Site validation
uses the unchanged local Draft 2020-12 schema, then checks IDs, references, and
lane counts. The default registry accounts for both supplied rule documents,
shares checks for overlapping provisions, and evaluates the clauses supported by
input schema 1.0.0. Other clauses identify missing facts, engineering review,
unavailable sources, or informational interpretation explicitly.
This tool reads local site JSON. It does not parse DGN/CAD files or establish
comprehensive MUTCD compliance. Predictions and observations are validated data,
not automatically compliance evidence.

## Setup

From the repository root, create and activate a project-local environment using
Python 3.11 or newer.

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS (Terminal, zsh or bash):

```sh
python3 -m venv .venv
source .venv/bin/activate
```

With the environment active, the following commands work on either platform:

```sh
python -m pip install -r requirements.txt
```

You can also skip activation and replace `python` in the commands below with
`.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on macOS.

To run the tests and author rules, also install the development requirements:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
```

Use this checkout directly; no distribution packaging, service or installation
of the repository as a package is provided.

## Quick start

Run from the checkout root. JSON is the default output format:

```sh
python -m verifier examples/taper-75ft.json
# exit 3: taper passes; missing facts leave other checks incomplete
python -m verifier examples/taper-125ft.json --format text
# exit 1: a taper warning, with other checks still incomplete
python -m verifier examples/invalid.json
# exit 2: invalid input; no rules execute
python -m verifier --help
```

The default registry accounts for both supplied rule documents. Select the
historical W1 registry with `--registry w1`, or the original five entries with
`--registry legacy`. `--registry all` and `--registry default` select the full
catalog. Registry selection chooses checks; it does not supply missing facts.

Use the Python API from the checkout root or with this checkout on `PYTHONPATH`:

```python
from verifier import verify_file

report = verify_file("examples/taper-75ft.json")
print(report.to_json())
assert report.exit_code == 3
```

Exit codes are `0` for all selected checks resolved without findings, `1` for
findings, `2` for invalid input or arguments, `3` for an incomplete evaluation
without findings, and `4` for execution or operational errors. Read statuses,
completeness, and coverage limitations alongside scores; a score is not a
regulatory compliance percentage.

## Documentation and development

- [API and CLI reference](docs/reference.md): validation boundaries, report fields,
  scores, registries, serialization, exit precedence, and use from another directory.
- [Rule-authoring guide](docs/rule-authoring.md): evaluator contracts and acceptance checks.
- [W1 coverage and interpretation](docs/w1-coverage.md): supported historical behavior.
- [Input field reference](tcp-field-reference.md) and
  [JSON schema](tcp-intermediate-format.schema.json).

`verifier.py` owns validation and rule execution and re-exports the public report
API. `reporting.py` owns report models, projections, and formatting.
`verifier_cli.py` handles arguments and output recovery. `rules/geometry.py`
provides the shared internal geometry interface; individual rules establish
applicability and choose subjects.

Run `python -m pytest` and `python -m ruff check .` before completing a change.
CI runs these checks on Windows and Linux with Python 3.11 and 3.14. Ruff's
formatter configuration is available for files being edited via
`python -m ruff format path/to/file.py`; repository-wide formatting is a separate
change. Static source records and extracted metadata are excluded from formatting.
