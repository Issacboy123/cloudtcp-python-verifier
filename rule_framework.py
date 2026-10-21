"""Explicit Python rule contracts and validation; site data stays dictionaries."""

from dataclasses import asdict, dataclass, field
import json
import math
import re
from typing import Callable, Iterable


@dataclass(frozen=True)
class Citation:
    source_document: str
    local_reference: str
    mutcd_reference: str


@dataclass(frozen=True)
class RuleMetadata:
    rule_id: str
    title: str
    classification: str
    citations: tuple[Citation, ...]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    classification: str
    message: str
    element_ids: tuple[str, ...]
    zone_ids: tuple[str, ...]
    paths: tuple[str, ...]
    citations: tuple[Citation, ...]
    values: dict[str, int | float] = field(default_factory=dict)
    units: str | None = None


@dataclass(frozen=True)
class Diagnostic:
    code: str
    path: str
    message: str
    rule_id: str | None = None
    schema_path: str | None = None
    line: int | None = None
    column: int | None = None
    exception_type: str | None = None


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    status: str
    complete: bool
    findings: tuple[Finding, ...] = ()
    reason: str | None = None
    errors: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class Rule:
    metadata: RuleMetadata
    evaluator: Callable[[dict], RuleResult]


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return type(value) is str and bool(value.strip())


def _pointer(value):
    return (type(value) is str and (value == "" or value.startswith("/"))
            and re.search(r"~(?![01])", value) is None)


def _strings(values, name, *, nonempty=False, pointers=False):
    _require(type(values) is tuple, f"{name} must be a tuple.")
    _require(not nonempty or bool(values), f"{name} must not be empty.")
    valid = _pointer if pointers else lambda item: type(item) is str
    _require(all(valid(item) for item in values), f"Invalid {name}.")


def _citations(citations):
    _require(type(citations) is tuple and bool(citations), "Citations must be a nonempty tuple.")
    for citation in citations:
        _require(type(citation) is Citation, "Expected Citation.")
        _require(all(_text(value) for value in asdict(citation).values()),
                 "Every citation needs a source document, local reference and MUTCD reference.")
    _require(len(set(citations)) == len(citations), "Duplicate citations.")


def _metadata(metadata):
    _require(type(metadata) is RuleMetadata, "Expected RuleMetadata.")
    _require(type(metadata.rule_id) is str and re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)+", metadata.rule_id
    ) is not None, "Rule ID must be namespaced, e.g. mutcd.Z-026.")
    _require(_text(metadata.title), "Rule title must not be empty.")
    _require(type(metadata.classification) is str and metadata.classification in
             ("STANDARD", "GUIDANCE", "OPTION", "SUPPORT"), "Invalid rule classification.")
    _citations(metadata.citations)
    _strings(metadata.limitations, "limitations")
    _require(all(_text(item) for item in metadata.limitations), "Empty limitation.")


@dataclass(frozen=True, init=False)
class RuleRegistry:
    """Validated immutable registration order. Construct explicitly; no discovery."""

    rules: tuple[Rule, ...]

    def __init__(self, rules: Iterable[Rule] = ()):
        entries = tuple(rules)
        ids = set()
        for rule in entries:
            _require(type(rule) is Rule, "Expected Rule.")
            _metadata(rule.metadata)
            _require(callable(rule.evaluator), "Rule evaluator must be callable.")
            _require(rule.metadata.rule_id not in ids, "Duplicate rule ID.")
            ids.add(rule.metadata.rule_id)
        object.__setattr__(self, "rules", entries)


def _diagnostic(error, rule_id):
    _require(type(error) is Diagnostic, "Expected Diagnostic.")
    _require(_text(error.code) and _text(error.message), "Error needs code and message.")
    _require(error.rule_id == rule_id, "Diagnostic rule ID must match metadata.")
    _require(_pointer(error.path), "Invalid diagnostic input pointer.")
    _require(error.schema_path is None or _pointer(error.schema_path), "Invalid schema pointer.")
    for value in (error.line, error.column):
        _require(value is None or (type(value) is int and value >= 1), "Invalid parse location.")
    _require(error.exception_type is None or _text(error.exception_type), "Invalid exception type.")


def validate_result(result, metadata):
    """Reject malformed/contradictory output; the engine converts failures to errors."""
    _require(type(result) is RuleResult, "Evaluator must return RuleResult.")
    _require(result.rule_id == metadata.rule_id, "Result rule ID must match metadata.")
    _require(type(result.complete) is bool, "complete must be boolean.")
    _require(type(result.status) is str and result.status in
             ("pass", "fail", "not_applicable", "not_evaluable", "error"), "Invalid result status.")
    _require(type(result.findings) is tuple, "Findings must be a tuple.")
    _require(type(result.errors) is tuple, "Errors must be a tuple.")
    _require(result.reason is None or _text(result.reason), "Invalid reason.")
    if result.status == "fail":
        _require(bool(result.findings), "fail requires findings.")
    else:
        _require(not result.findings, "Only fail may contain findings.")
        _require(result.complete == (result.status in ("pass", "not_applicable")),
                 "Status and complete contradict each other.")
    if result.status in ("not_applicable", "not_evaluable", "error") or not result.complete:
        _require(_text(result.reason), "This result requires a readable reason.")
    _require(not result.errors or result.status == "error", "Only error may contain errors.")
    for error in result.errors:
        _diagnostic(error, metadata.rule_id)
    for finding in result.findings:
        _require(type(finding) is Finding, "Expected Finding.")
        _require(finding.rule_id == metadata.rule_id, "Finding rule ID must match metadata.")
        _require(finding.classification == metadata.classification, "Finding classification must match metadata.")
        severity = {"STANDARD": "error", "GUIDANCE": "warning"}.get(metadata.classification)
        _require(severity is not None and finding.severity == severity,
                 "STANDARD requires error, GUIDANCE warning; OPTION/SUPPORT cannot produce findings.")
        _require(_text(finding.message), "Finding needs a message.")
        _strings(finding.element_ids, "element IDs")
        _strings(finding.zone_ids, "zone IDs")
        _strings(finding.paths, "finding paths", nonempty=True, pointers=True)
        _citations(finding.citations)
        _require(finding.citations == metadata.citations, "Finding citations must match metadata.")
        _require(type(finding.values) is dict, "Numeric values must be a dictionary.")
        for key, value in finding.values.items():
            _require(_text(key) and type(value) in (int, float), "Values need text keys and numbers.")
            _require(type(value) is int or math.isfinite(value), "Numeric values must be finite.")
        _require(finding.units is None or _text(finding.units), "Invalid units.")
    # Also catches oversized integers, cycles and any unsupported serialized value.
    json.dumps(asdict(result), allow_nan=False, sort_keys=True)


def finding_key(finding):
    """Input location is the sorted pointer tuple; JSON breaks all remaining ties."""
    return (finding.rule_id, tuple(sorted(finding.paths)),
            json.dumps(asdict(finding), allow_nan=False, sort_keys=True))


def diagnostic_key(error):
    return (error.rule_id or "", error.path, error.code, error.message,
            json.dumps(asdict(error), allow_nan=False, sort_keys=True))
