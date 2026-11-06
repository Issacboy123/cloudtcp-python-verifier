"""Verification API and compatible entry point for the checkout CLI."""

from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
import sys

from ingestion import InputValidationError, load_document, validate_document
from rule_framework import (
    Citation as Citation, Diagnostic, Rule as Rule, RuleMetadata as RuleMetadata,
    RuleRegistry, RuleResult, diagnostic_key, finding_key, validate_result,
    Finding as Finding,
)
from reporting import (
    BASE_LIMITATIONS as BASE_LIMITATIONS, COVERAGE_SCOPE as COVERAGE_SCOPE,
    REPORT_VERSION as REPORT_VERSION, Report as Report, ReportRuleResult as ReportRuleResult,
    build_report, exception_message, exit_code as exit_code,
)
from signs_verifier import SIGN_RULES
from rules.tapers import TAPER_RULE
from rules.w1_registry import w1_rules
from rules.full_registry import ALL_REGISTRY as ALL_REGISTRY


# Preserve historical selections while making documented coverage the default.
LEGACY_REGISTRY = RuleRegistry((*SIGN_RULES, TAPER_RULE))
W1_REGISTRY = RuleRegistry(w1_rules())
DEFAULT_REGISTRY = ALL_REGISTRY


def _invalid_report(registry, exc):
    return build_report(registry, input_errors=tuple(Diagnostic(**asdict(d)) for d in exc.diagnostics))


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
            result = _error(rule.metadata.rule_id, "rule_exception", exception_message(exc), type(exc).__name__)
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
                result = _error(rule.metadata.rule_id, "malformed_result", exception_message(exc), type(exc).__name__)
        results.append(result)
    return build_report(registry, results=results)


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


def main(argv=None):
    """Run the CLI with this API module's registries and execution boundary."""
    from verifier_cli import main as cli_main

    return cli_main(argv, api=sys.modules[__name__])


if __name__ == "__main__":
    raise SystemExit(main())
