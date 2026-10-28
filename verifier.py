"""Verification API and checkout CLI for implemented-rule coverage reports."""

import argparse
from copy import deepcopy
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import sys

from ingestion import InputValidationError, load_document, validate_document
from rule_framework import (
    Citation, Diagnostic, Finding, Rule, RuleMetadata, RuleRegistry, RuleResult,
    diagnostic_key, finding_key, validate_result,
)
from signs_verifier import SIGN_RULES
from rules.tapers import TAPER_RULE
from rules.w1_registry import w1_rules


# Production default remains the five initial entries. TCP-W1-1 rules use W1_REGISTRY.
DEFAULT_REGISTRY = RuleRegistry((*SIGN_RULES, TAPER_RULE))
W1_REGISTRY = RuleRegistry(w1_rules())
REPORT_VERSION = "1.0.0"
COVERAGE_SCOPE = "implemented_rules_only"
BASE_LIMITATIONS = (
    "Coverage includes only the registered Python rules; it is not comprehensive MUTCD compliance.",
)


@dataclass(frozen=True)
class Report:
    version: str
    input_valid: bool
    implemented_rule_ids: tuple[str, ...]
    evaluation_complete: bool
    rule_metadata: tuple[RuleMetadata, ...]
    rule_results: tuple[RuleResult, ...]
    findings: tuple[Finding, ...]
    errors: tuple[Diagnostic, ...]
    limitations: tuple[str, ...]
    coverage_scope: str = COVERAGE_SCOPE

    def to_dict(self) -> dict:
        """Return detached JSON values, preserving array order and every finding."""
        return json.loads(self.to_json())

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, allow_nan=False,
                          sort_keys=True, indent=2) + "\n"

    @property
    def exit_code(self) -> int:
        return exit_code(self)


def exit_code(report: Report | None = None, *, operational_error: bool = False) -> int:
    """Shared exit decision; Python API infrastructure faults still raise."""
    if operational_error:
        return 4
    if report is None:
        raise ValueError("A report or operational_error=True is required.")
    if any(error.code == "operational_error" for error in report.errors) or any(
        result.status == "error" for result in report.rule_results
    ) or (
        report.input_valid and report.errors
    ):
        return 4
    if not report.input_valid:
        return 2
    if report.findings:
        return 1
    if not report.evaluation_complete:
        return 3
    return 0


def _report(registry, *, input_errors=(), results=()):
    metadata = tuple(rule.metadata for rule in registry.rules)
    findings = tuple(sorted((f for result in results for f in result.findings), key=finding_key))
    errors = tuple(sorted((*input_errors, *(e for r in results for e in r.errors)), key=diagnostic_key))
    limitations = list(BASE_LIMITATIONS)
    if not metadata:
        limitations.append("No rules are implemented in the current registry.")
    for rule in metadata:
        limitations.extend(f"{rule.rule_id}: {text}" for text in rule.limitations)
    for result in results:
        if not result.complete:
            limitations.append(f"{result.rule_id}: {result.reason}")
    return Report(
        version=REPORT_VERSION, input_valid=not input_errors,
        implemented_rule_ids=tuple(rule.rule_id for rule in metadata),
        evaluation_complete=not input_errors and not errors and all(r.complete for r in results),
        rule_metadata=metadata, rule_results=tuple(results), findings=findings,
        errors=errors, limitations=tuple(limitations),
    )


def _invalid_report(registry, exc):
    return _report(registry, input_errors=tuple(Diagnostic(**asdict(d)) for d in exc.diagnostics))


def _exception_message(exc):
    try:
        message = str(exc)
    except Exception:
        message = "Exception message unavailable."
    return f"{type(exc).__name__}: {message}"


def _error(rule_id, code, reason, exception_type=None):
    return RuleResult(rule_id, "error", False, reason=reason, errors=(
        Diagnostic(code, "", reason, rule_id=rule_id, exception_type=exception_type),
    ))


def _execute(document, registry, *, results=None):
    # The CLI retains completed results if a later infrastructure operation fails.
    # Public API callers still receive the original exception.
    if results is None:
        results = []
    for rule in registry.rules:
        # Copy outside the evaluator catch: a copy/infrastructure fault propagates.
        isolated = deepcopy(document)
        try:
            result = rule.evaluator(isolated)
        except Exception as exc:
            result = _error(rule.metadata.rule_id, "rule_exception", _exception_message(exc), type(exc).__name__)
        else:
            try:
                validate_result(result, rule.metadata)
                # Detach retained evaluator-owned dictionaries before later rules run.
                result = deepcopy(result)
                if result.status == "error" and not result.errors:
                    result = _error(rule.metadata.rule_id, "rule_error", result.reason)
                result = replace(result,
                                 findings=tuple(sorted(result.findings, key=finding_key)),
                                 errors=tuple(sorted(result.errors, key=diagnostic_key)))
            except Exception as exc:
                result = _error(rule.metadata.rule_id, "malformed_result", _exception_message(exc), type(exc).__name__)
        results.append(result)
    return _report(registry, results=results)


def _registry(registry):
    selected = DEFAULT_REGISTRY if registry is None else registry
    if type(selected) is not RuleRegistry:
        raise TypeError("registry must be RuleRegistry.")
    return selected


def verify_document(document: object, *, registry: RuleRegistry | None = None) -> Report:
    """Validate a parsed site, then execute rules on independent copies.

    The optional registry selects Python code, not additional site/context facts.
    Expected input failures return reports; schema/configuration faults propagate.
    """
    selected = _registry(registry)
    try:
        validated = validate_document(document)
    except InputValidationError as exc:
        return _invalid_report(selected, exc)
    return _execute(validated, selected)


def verify_file(path: str | Path, *, registry: RuleRegistry | None = None) -> Report:
    """Load a site and verify it; preserve ingestion's expected/infrastructure boundary."""
    selected = _registry(registry)
    try:
        document = load_document(path)
    except InputValidationError as exc:
        return _invalid_report(selected, exc)
    return _execute(document, selected)


class _ArgumentError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _ArgumentError(message)

    def print_help(self, file=None):
        # argparse suppresses write OSErrors by default. Let the CLI boundary
        # convert them and catch flush failures before interpreter shutdown.
        stream = sys.stdout if file is None else file
        stream.write(self.format_help())
        stream.flush()


def _operational_report(exc, registry, results, input_valid, report=None):
    retained = report if report is not None else _report(registry, results=results)
    completed = {result.rule_id for result in retained.rule_results}
    pending = tuple(f"{rule_id}: Execution did not reach this check."
                    for rule_id in retained.implemented_rule_ids if rule_id not in completed)
    diagnostic = Diagnostic("operational_error", "", _exception_message(exc),
                            exception_type=type(exc).__name__)
    return replace(retained, input_valid=input_valid, evaluation_complete=False,
                   errors=tuple(sorted((*retained.errors, diagnostic), key=diagnostic_key)),
                   limitations=(*retained.limitations, *pending))


def _text_report(report):
    lines = [
        f"Report version: {report.version}",
        f"Input valid: {report.input_valid}",
        f"Evaluation complete: {report.evaluation_complete}",
        f"Exit code: {report.exit_code}",
        f"Coverage: {report.coverage_scope}",
        "Implemented rule IDs: " + (", ".join(report.implemented_rule_ids) or "(none)"),
        "Rule results and citations:",
    ]
    results = {result.rule_id: result for result in report.rule_results}
    for meta in report.rule_metadata:
        result = results.get(meta.rule_id)
        status = f"{result.status}; complete={result.complete}" if result else "not executed"
        lines.append(f"  {meta.rule_id} [{meta.classification}]: {status}")
        if result and result.reason:
            lines.append(f"    Reason: {result.reason}")
        for citation in meta.citations:
            lines.append(f"    Citation: {citation.source_document} | "
                         f"{citation.local_reference} | {citation.mutcd_reference}")
    lines.append("Findings:")
    if not report.findings:
        lines.append("  (none)")
    for finding in report.findings:
        lines.extend((
            f"  {finding.rule_id} [{finding.classification}/{finding.severity}]: {finding.message}",
            f"    Elements: {', '.join(finding.element_ids) or '(none)'}; "
            f"zones: {', '.join(finding.zone_ids) or '(none)'}",
            "    Paths: " + ", ".join(path or "<root>" for path in finding.paths),
        ))
        if finding.values:
            lines.append(f"    Measurements: {json.dumps(finding.values, sort_keys=True)}; "
                         f"units: {finding.units or '(unspecified)'}")
        for citation in finding.citations:
            lines.append(f"    Citation: {citation.source_document} | "
                         f"{citation.local_reference} | {citation.mutcd_reference}")
    lines.append("Errors:")
    if not report.errors:
        lines.append("  (none)")
    for error in report.errors:
        lines.append(f"  {error.rule_id or 'input/CLI'} {error.path or '<root>'} "
                     f"[{error.code}]: {error.message}")
        if error.line is not None:
            lines.append(f"    Line: {error.line}; column: {error.column}")
        if error.schema_path is not None:
            lines.append(f"    Schema path: {error.schema_path}")
    lines.append("Incomplete checks:")
    incomplete = [result for result in report.rule_results if not result.complete]
    pending = [rule_id for rule_id in report.implemented_rule_ids if rule_id not in results]
    for result in incomplete:
        lines.append(f"  {result.rule_id}: {result.reason}")
    for rule_id in pending:
        lines.append(f"  {rule_id}: Not executed.")
    if not incomplete and not pending:
        lines.append("  (none)")
    lines.append("Coverage limitations:")
    lines.extend(f"  {limitation}" for limitation in report.limitations)
    return "\n".join(lines) + "\n"


def _json_report(report):
    # ASCII escapes keep JSON portable across console/pipe encodings.
    return json.dumps(asdict(report), ensure_ascii=True, allow_nan=False,
                      sort_keys=True, indent=2) + "\n"


def _emit_report(report, output_format):
    emission_started = False
    try:
        with redirect_stdout(sys.stderr):
            output = _json_report(report) if output_format == "json" else _text_report(report)
        emission_started = True
        sys.stdout.write(output)
        sys.stdout.flush()
    except Exception as exc:
        report = _operational_report(exc, DEFAULT_REGISTRY, (), report.input_valid, report)
        fallback = _json_report(report)
        # Formatting and encoding failures have not emitted report bytes. A
        # write/flush I/O fault may have emitted some: do not append a second JSON
        # document to that stream or retry a broken pipe.
        fallback_written = False
        if not emission_started or isinstance(exc, UnicodeEncodeError):
            try:
                sys.stdout.write(fallback)
                sys.stdout.flush()
                fallback_written = True
            except Exception:
                pass
        if not fallback_written:
            # An unavailable output pipe cannot carry a JSON report. Use stderr
            # and prevent a second failing stdout flush during interpreter exit.
            try:
                sys.stderr.write(fallback)
                sys.stderr.flush()
            except Exception:
                pass  # Neither stream is usable; the process still returns 4.
            sys.stdout = None
    return report.exit_code


def main(argv=None):
    """Run one local file. All infrastructure catches are confined to the CLI."""
    parser = _Parser(prog="python -m verifier", allow_abbrev=False,
                     description="Verify one site JSON against implemented rules only.")
    parser.add_argument("site", metavar="SITE.json")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    registry = DEFAULT_REGISTRY
    results = []
    report = None
    input_valid = False
    try:
        args = parser.parse_args(argv)
    except _ArgumentError as exc:
        report = _report(registry, input_errors=(Diagnostic("cli_arguments", "", str(exc)),))
        return _emit_report(report, "json")
    except Exception as exc:
        return _emit_report(_operational_report(exc, registry, (), False), "json")
    # Trusted evaluator prints and incidental logs must not corrupt JSON stdout.
    with redirect_stdout(sys.stderr):
        try:
            document = load_document(args.site)
            input_valid = True
            report = _execute(document, registry, results=results)
        except InputValidationError as exc:
            report = _invalid_report(registry, exc)
        except Exception as exc:
            report = _operational_report(exc, registry, results, input_valid)
    return _emit_report(report, args.format)


if __name__ == "__main__":
    raise SystemExit(main())
