"""Report models, deterministic projections, formatting, and exit decisions."""

from collections import Counter
from dataclasses import asdict, dataclass, replace
import json

from rule_framework import (
    Diagnostic,
    Finding,
    ResultStatus,
    RuleMetadata,
    RuleRegistry,
    RuleResult,
    diagnostic_key,
    finding_key,
)
from rules.full_registry import ALL_REGISTRY, automated_rule_ids, source_coverage
from rules.source_catalog import SourceClause

# Report and input schema versions are independent.
REPORT_VERSION = "2.0.0"
COVERAGE_SCOPE = "implemented_rules_only"
BASE_LIMITATIONS = (
    "Coverage includes only the registered Python rules; it is not comprehensive MUTCD compliance.",
)


@dataclass(frozen=True)
class ReportRuleResult:
    """Reported outcome with a binary score; evaluator RuleResult stays unchanged."""

    rule_id: str
    status: ResultStatus
    complete: bool
    score: int
    findings: tuple[Finding, ...] = ()
    reason: str | None = None
    errors: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class Report:
    version: str
    input_valid: bool
    implemented_rule_ids: tuple[str, ...]
    evaluation_complete: bool
    rule_metadata: tuple[RuleMetadata, ...]
    rule_results: tuple[ReportRuleResult, ...]
    findings: tuple[Finding, ...]
    errors: tuple[Diagnostic, ...]
    limitations: tuple[str, ...]
    coverage_scope: str = COVERAGE_SCOPE
    registered_rule_ids: tuple[str, ...] = ()
    automated_rule_ids: tuple[str, ...] = ()
    source_coverage: tuple[SourceClause, ...] = ()

    def to_dict(self) -> dict:
        """Return detached JSON values, preserving array order and every finding."""
        return json.loads(self.to_json())

    def to_json(self) -> str:
        return (
            json.dumps(asdict(self), ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
            + "\n"
        )

    @property
    def exit_code(self) -> int:
        return exit_code(self)


def exit_code(report: Report | None = None, *, operational_error: bool = False) -> int:
    """Shared exit decision; Python API infrastructure faults still raise."""
    if operational_error:
        return 4
    if report is None:
        raise ValueError("A report or operational_error=True is required.")
    if (
        any(error.code == "operational_error" for error in report.errors)
        or any(result.status == "error" for result in report.rule_results)
        or (report.input_valid and report.errors)
    ):
        return 4
    if not report.input_valid:
        return 2
    if report.findings:
        return 1
    if not report.evaluation_complete:
        return 3
    return 0


def report_result(result: RuleResult) -> ReportRuleResult:
    """Project a validated evaluator outcome without mutating its measurements."""
    findings = tuple(
        sorted(
            (
                replace(
                    finding,
                    values={
                        key: 0 if key == "score" else value for key, value in finding.values.items()
                    },
                )
                for finding in result.findings
            ),
            key=finding_key,
        )
    )
    return ReportRuleResult(
        rule_id=result.rule_id,
        status=result.status,
        complete=result.complete,
        score=1 if result.status == "pass" else 0,
        findings=findings,
        reason=result.reason,
        errors=result.errors,
    )


def build_report(
    registry: RuleRegistry,
    *,
    input_errors: tuple[Diagnostic, ...] = (),
    results: tuple[RuleResult, ...] | list[RuleResult] = (),
) -> Report:
    reported_results = tuple(report_result(result) for result in results)
    metadata = tuple(rule.metadata for rule in registry.rules)
    findings = tuple(
        sorted((f for result in reported_results for f in result.findings), key=finding_key)
    )
    errors = tuple(
        sorted(
            (*input_errors, *(e for r in reported_results for e in r.errors)), key=diagnostic_key
        )
    )
    limitations = list(BASE_LIMITATIONS)
    coverage = source_coverage(registry)
    if registry.rules == ALL_REGISTRY.rules:
        limitations.append(
            "Source accounting includes both repository rule documents; missing input facts, "
            "engineering review, and unavailable references remain explicit gaps. "
            "Non-California sites receive the federal baseline, not other state-specific compliance."
        )
    if not metadata:
        limitations.append("No rules are implemented in the current registry.")
    for rule in metadata:
        limitations.extend(f"{rule.rule_id}: {text}" for text in rule.limitations)
    for result in reported_results:
        if not result.complete:
            limitations.append(f"{result.rule_id}: {result.reason}")
    return Report(
        version=REPORT_VERSION,
        input_valid=not input_errors,
        implemented_rule_ids=tuple(rule.rule_id for rule in metadata),
        evaluation_complete=not input_errors
        and not errors
        and all(r.complete for r in reported_results),
        rule_metadata=metadata,
        rule_results=reported_results,
        findings=findings,
        errors=errors,
        limitations=tuple(limitations),
        registered_rule_ids=tuple(rule.rule_id for rule in metadata),
        automated_rule_ids=automated_rule_ids(registry, coverage),
        source_coverage=coverage,
    )


def exception_message(exc: Exception) -> str:
    try:
        message = str(exc)
    except Exception:
        message = "Exception message unavailable."
    return f"{type(exc).__name__}: {message}"


def operational_report(exc: Exception, retained: Report, *, input_valid: bool) -> Report:
    """Retain completed work and identify checks skipped by an operational fault."""
    completed = {result.rule_id for result in retained.rule_results}
    pending = tuple(
        f"{rule_id}: Execution did not reach this check."
        for rule_id in retained.implemented_rule_ids
        if rule_id not in completed
    )
    diagnostic = Diagnostic(
        "operational_error", "", exception_message(exc), exception_type=type(exc).__name__
    )
    return replace(
        retained,
        input_valid=input_valid,
        evaluation_complete=False,
        errors=tuple(sorted((*retained.errors, diagnostic), key=diagnostic_key)),
        limitations=(*retained.limitations, *pending),
    )


def format_text(report: Report) -> str:
    lines = [
        f"Report version: {report.version}",
        f"Input valid: {report.input_valid}",
        f"Evaluation complete: {report.evaluation_complete}",
        f"Exit code: {report.exit_code}",
        f"Coverage: {report.coverage_scope}",
        "Registered rule IDs: " + (", ".join(report.registered_rule_ids) or "(none)"),
        "Fully automated rule IDs: " + (", ".join(report.automated_rule_ids) or "(none)"),
        "Source clause coverage: "
        + (
            ", ".join(
                f"{disposition}={count}"
                for disposition, count in sorted(
                    Counter(clause.disposition for clause in report.source_coverage).items()
                )
            )
            or "(no catalog entries for this registry)"
        ),
        "implemented_rule_ids is deprecated; it lists registered checks, including unresolved checks.",
        "Rule results and citations:",
    ]
    results = {result.rule_id: result for result in report.rule_results}
    for meta in report.rule_metadata:
        result = results.get(meta.rule_id)
        status = f"{result.status}; complete={result.complete}" if result else "not executed"
        lines.append(f"  {meta.rule_id} [{meta.classification}]: {status}")
        if result:
            lines.append(f"    Score: {result.score}")
        if result and result.reason:
            lines.append(f"    Reason: {result.reason}")
        for citation in meta.citations:
            lines.append(
                f"    Citation: {citation.source_document} | "
                f"{citation.local_reference} | {citation.mutcd_reference}"
            )
    lines.append("Findings:")
    if not report.findings:
        lines.append("  (none)")
    for finding in report.findings:
        lines.extend(
            (
                f"  {finding.rule_id} [{finding.classification}/{finding.severity}]: {finding.message}",
                f"    Elements: {', '.join(finding.element_ids) or '(none)'}; "
                f"zones: {', '.join(finding.zone_ids) or '(none)'}",
                "    Paths: " + ", ".join(path or "<root>" for path in finding.paths),
            )
        )
        if finding.values:
            lines.append(
                f"    Measurements: {json.dumps(finding.values, sort_keys=True)}; "
                f"units: {finding.units or '(unspecified)'}"
            )
        for citation in finding.citations:
            lines.append(
                f"    Citation: {citation.source_document} | "
                f"{citation.local_reference} | {citation.mutcd_reference}"
            )
    lines.append("Errors:")
    if not report.errors:
        lines.append("  (none)")
    for error in report.errors:
        lines.append(
            f"  {error.rule_id or 'input/CLI'} {error.path or '<root>'} "
            f"[{error.code}]: {error.message}"
        )
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


def format_json(report: Report) -> str:
    # ASCII escapes keep JSON portable across console/pipe encodings.
    return (
        json.dumps(asdict(report), ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2)
        + "\n"
    )
