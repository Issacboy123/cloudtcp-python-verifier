from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from itertools import product
import json
from pathlib import Path
import sys

import pytest

import ingestion
import verifier
from rule_framework import (
    Citation, Diagnostic, Finding, Rule, RuleMetadata, RuleRegistry, RuleResult,
)
from verifier import exit_code, verify_document, verify_file


CITATION = Citation("synthetic.md", "TEST-1", "Synthetic reference; no production requirement")


def metadata(rule_id="test.one", classification="GUIDANCE", **changes):
    return replace(RuleMetadata(rule_id, "Synthetic test rule", classification, (CITATION,)), **changes)


def finding(meta=None, **changes):
    meta = meta or metadata()
    return replace(Finding(
        meta.rule_id, "error" if meta.classification == "STANDARD" else "warning",
        meta.classification, "Synthetic finding", ("E1",), ("Z1",),
        ("/elements/0",), meta.citations, {"actual": 10.0, "expected": 20}, "feet",
    ), **changes)


def registry_for(result, meta=None):
    return RuleRegistry([Rule(meta or metadata(), lambda document: result)])


def test_public_reexports_and_explicit_empty_registry(example):
    assert verifier.load_document is ingestion.load_document
    assert verifier.InputValidationError is ingestion.InputValidationError
    report = verify_document(example, registry=RuleRegistry())
    assert report.input_valid and report.evaluation_complete
    assert report.rule_results == report.findings == report.errors == ()
    assert report.implemented_rule_ids == ()
    assert report.coverage_scope == "implemented_rules_only"
    assert "No rules" in report.limitations[1]
    assert report.exit_code == 0
    assert report.to_dict()["version"] == "1.0.0"


@pytest.mark.parametrize("status,complete,has_findings", tuple(product(
    ("pass", "fail", "not_applicable", "not_evaluable", "error"), (True, False), (True, False)
)))
def test_exact_status_matrix(example, status, complete, has_findings):
    result = RuleResult("test.one", status, complete,
                        (finding(),) if has_findings else (), reason="Readable reason")
    report = verify_document(example, registry=registry_for(result))
    allowed = ((status == "fail" and has_findings)
               or (status in ("pass", "not_applicable") and complete and not has_findings)
               or (status in ("not_evaluable", "error") and not complete and not has_findings))
    actual = report.rule_results[0]
    if allowed:
        assert actual.status == status
        assert actual.complete == complete
        assert actual.findings == result.findings
        assert report.evaluation_complete == complete
        if status == "error":
            assert report.errors[0].code == "rule_error"
    else:
        assert actual.status == "error" and not actual.complete
        assert not actual.findings and not report.evaluation_complete
        assert report.errors[0].code == "malformed_result"


@pytest.mark.parametrize("status,complete", [
    ("not_applicable", True), ("not_evaluable", False), ("error", False), ("fail", False),
])
@pytest.mark.parametrize("reason", [None, "", "  ", 12])
def test_required_readable_reasons(example, status, complete, reason):
    result = RuleResult("test.one", status, complete,
                        (finding(),) if status == "fail" else (), reason=reason)
    report = verify_document(example, registry=registry_for(result))
    assert report.errors[0].code == "malformed_result"


def test_multiple_findings_and_missing_facts_retained(example):
    first = finding(message="first", paths=("/elements/0",))
    second = finding(message="second", paths=("/elements/1",))
    result = RuleResult("test.one", "fail", False, (second, first), "Other subjects lack facts.")
    report = verify_document(example, registry=registry_for(result))
    assert report.findings == (first, second)
    assert report.rule_results[0].findings == report.findings
    assert not report.evaluation_complete and report.exit_code == 1
    assert "Other subjects lack facts." in report.limitations[-1]
    assert report.errors == ()


def test_exceptions_and_malformed_output_do_not_stop_later_rules(example):
    calls = []

    def crash(document):
        calls.append("crash")
        raise RuntimeError("Synthetic failure")

    def malformed(document):
        calls.append("malformed")
        return {"status": "pass"}

    def good(document):
        calls.append("good")
        return RuleResult("test.good", "pass", True)

    registry = RuleRegistry([Rule(metadata("test.crash"), crash),
                             Rule(metadata("test.malformed"), malformed),
                             Rule(metadata("test.good"), good)])
    report = verify_document(example, registry=registry)
    assert calls == ["crash", "malformed", "good"]
    assert [r.status for r in report.rule_results] == ["error", "error", "pass"]
    assert [e.code for e in report.errors] == ["rule_exception", "malformed_result"]
    assert report.errors[0].exception_type == "RuntimeError"
    assert report.errors[0].message == "RuntimeError: Synthetic failure"
    assert report.exit_code == 4


def test_exception_with_broken_str_is_contained(example):
    class BrokenError(Exception):
        def __str__(self):
            raise ValueError("cannot format")

    def evaluate(document):
        raise BrokenError()

    report = verify_document(example, registry=RuleRegistry([Rule(metadata(), evaluate)]))
    assert report.errors[0].message == "BrokenError: Exception message unavailable."
    json.loads(report.to_json())


@pytest.mark.parametrize("changes", [
    {"rule_id": "wrong.id"}, {"status": "unknown"}, {"status": []}, {"complete": 1},
    {"findings": []}, {"findings": (object(),)}, {"errors": []},
    {"errors": (Diagnostic("bad", "", "bad", "test.one"),)},
    {"reason": float("nan")},
])
def test_malformed_results(example, changes):
    result = replace(RuleResult("test.one", "pass", True), **changes)
    report = verify_document(example, registry=registry_for(result))
    assert report.errors[0].code == "malformed_result"
    assert report.rule_results[0].status == "error"


@pytest.mark.parametrize("changes", [
    {"rule_id": "other.rule"}, {"classification": "STANDARD"}, {"severity": "error"},
    {"message": " "}, {"element_ids": ["E1"]}, {"zone_ids": (1,)},
    {"paths": ()}, {"paths": ("elements/0",)}, {"paths": ("/bad~2pointer",)},
    {"citations": ()}, {"citations": (Citation("other.md", "x", "other"),)},
    {"values": {"actual": float("nan")}}, {"values": {"actual": float("inf")}},
    {"values": {"actual": -float("inf")}}, {"values": {"actual": True}},
    {"values": {"actual": object()}}, {"values": {"actual": "10"}},
    {"values": {"actual": {1}}}, {"values": {1: 2}}, {"values": []}, {"units": " "},
])
def test_finding_integrity(example, changes):
    result = RuleResult("test.one", "fail", True, (finding(**changes),))
    report = verify_document(example, registry=registry_for(result))
    assert report.errors[0].code == "malformed_result"
    assert report.findings == ()


def test_oversized_integer_output_is_malformed(example):
    limit = sys.get_int_max_str_digits()
    if not limit:
        pytest.skip("Integer conversion limit disabled")
    result = RuleResult("test.one", "fail", True, (finding(values={"actual": 10 ** limit}),))
    report = verify_document(example, registry=registry_for(result))
    assert report.errors[0].code == "malformed_result"
    report.to_json()


@pytest.mark.parametrize("classification,severity,allowed", [
    ("STANDARD", "error", True), ("STANDARD", "warning", False),
    ("GUIDANCE", "warning", True), ("GUIDANCE", "error", False),
    ("OPTION", "warning", False), ("SUPPORT", "error", False),
])
def test_classification_severity_contract(example, classification, severity, allowed):
    meta = metadata(classification=classification)
    result = RuleResult(meta.rule_id, "fail", True, (finding(meta, severity=severity),))
    report = verify_document(example, registry=registry_for(result, meta))
    assert report.rule_results[0].status == ("fail" if allowed else "error")
    if allowed:
        # Finding severity 'error' is a violation (1), not an execution failure (4).
        assert report.exit_code == 1


@pytest.mark.parametrize("classification", ["OPTION", "SUPPORT"])
def test_informational_rules_can_resolve_without_findings(example, classification):
    report = verify_document(example, registry=registry_for(
        RuleResult("test.one", "pass", True), metadata(classification=classification)))
    assert report.exit_code == 0


@pytest.mark.parametrize("changes", [
    {"rule_id": "bare"}, {"rule_id": ""}, {"rule_id": "test."}, {"rule_id": ".one"},
    {"rule_id": "test one.id"}, {"rule_id": 1}, {"title": " "},
    {"classification": "standard"}, {"classification": "bogus"}, {"classification": []},
    {"citations": ()}, {"citations": []}, {"citations": ("reference",)},
    {"citations": (Citation("", "local", "MUTCD"),)},
    {"citations": (Citation("doc", " ", "MUTCD"),)},
    {"citations": (Citation("doc", "local", ""),)}, {"citations": (CITATION, CITATION)},
    {"limitations": ["gap"]}, {"limitations": (" ",)},
])
def test_registry_rejects_invalid_metadata(changes):
    with pytest.raises(ValueError):
        RuleRegistry([Rule(metadata(**changes), lambda document: None)])


def test_registry_rejects_duplicates_noncallables_and_nonrules():
    rule = Rule(metadata(), lambda document: None)
    for rules in ([rule, rule], [Rule(metadata(), None)], [object()], [Rule(None, lambda d: None)]):
        with pytest.raises(ValueError):
            RuleRegistry(rules)
    with pytest.raises(FrozenInstanceError):
        RuleRegistry([rule]).rules = ()
    with pytest.raises(FrozenInstanceError):
        rule.metadata.title = "changed"


def test_new_source_and_rule_need_only_registration(example):
    meta = metadata("agency.synthetic", citations=(Citation("agency-guide.md", "A-1", "6B synthetic"),),
                    limitations=("Synthetic source limitation.",))
    registry = RuleRegistry([Rule(meta, lambda document: RuleResult(meta.rule_id, "fail", True, (finding(meta),)))])
    report = verify_document(example, registry=registry)
    assert report.findings[0].citations == meta.citations
    assert report.rule_metadata == (meta,)
    assert report.implemented_rule_ids == ("agency.synthetic",)
    assert "agency.synthetic: Synthetic source limitation." in report.limitations


def test_isolation_from_caller_and_between_rules_including_crash(example):
    before = deepcopy(example)
    observations = []

    def mutate(document):
        document["site"]["name"] = "corrupted"
        document["zones"].clear()
        document["elements"][0]["position"]["station"] = 1e6
        raise ValueError("After mutation")

    def inspect(document):
        observations.append(deepcopy(document))
        document["elements"].clear()
        return RuleResult("test.inspect", "pass", True)

    registry = RuleRegistry([Rule(metadata("test.mutate"), mutate), Rule(metadata("test.inspect"), inspect)])
    report = verify_document(example, registry=registry)
    assert report.rule_results[1].status == "pass"
    assert observations == [before]
    assert example == before


def test_output_is_detached_before_other_rules_run(example):
    retained = finding()

    def second(document):
        retained.values["actual"] = 999
        return RuleResult("test.second", "pass", True)

    registry = RuleRegistry([Rule(metadata(), lambda d: RuleResult("test.one", "fail", True, (retained,))),
                             Rule(metadata("test.second"), second)])
    report = verify_document(example, registry=registry)
    assert report.findings[0].values["actual"] == 10
    assert retained.values["actual"] == 999
    copied = report.to_dict()
    copied["findings"][0]["values"]["actual"] = -1
    assert report.findings[0].values["actual"] == 10


def test_invalid_document_short_circuits_and_aggregates(example):
    def forbidden(document):
        pytest.fail("Invalid input reached an evaluator")

    registry = RuleRegistry([Rule(metadata(), forbidden)])
    example["format_version"] = "unsupported"
    example["site"]["units"] = "yards"
    before = deepcopy(example)
    report = verify_document(example, registry=registry)
    assert not report.input_valid and not report.evaluation_complete
    assert report.rule_results == report.findings == ()
    assert report.implemented_rule_ids == ("test.one",)
    assert [e.path for e in report.errors] == ["/format_version", "/site/units"]
    assert all(e.rule_id is None for e in report.errors)
    assert all(e.schema_path is not None for e in report.errors)
    assert report.exit_code == 2 and example == before


@pytest.mark.parametrize("content", ["{", '{"x": 1, "x": 2}', "[]", "NaN"])
def test_verify_file_invalid_inputs(tmp_path, content):
    source = tmp_path / "bad.json"
    source.write_text(content, encoding="utf-8")
    def forbidden(document):
        pytest.fail("Invalid file reached a rule")
    report = verify_file(source, registry=RuleRegistry([Rule(metadata(), forbidden)]))
    assert not report.input_valid and report.exit_code == 2
    assert report.rule_results == () and report.errors
    if content == "{":
        assert report.errors[0].line == 1 and report.errors[0].column == 2


def test_file_api_and_document_api_agree(example, tmp_path):
    path = tmp_path / "valid.json"
    path.write_text(json.dumps(example), encoding="utf-8-sig")
    registry = registry_for(RuleResult("test.one", "not_evaluable", False, reason="Missing facts."))
    assert verify_file(path, registry=registry) == verify_document(example, registry=registry)
    assert verify_file(tmp_path / "missing.json").exit_code == 2
    assert verify_file(tmp_path).exit_code == 2


@pytest.mark.parametrize("api", ["document", "file"])
def test_infrastructure_faults_propagate(example, tmp_path, monkeypatch, api):
    path = tmp_path / "site.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    monkeypatch.setattr(ingestion, "_SCHEMA_PATH", tmp_path / "missing-schema.json")
    with pytest.raises(FileNotFoundError):
        if api == "document":
            verify_document(example)
        else:
            verify_file(path)


def test_unexpected_file_io_propagates(monkeypatch):
    def failure(*args, **kwargs):
        raise OSError("Device unavailable")
    monkeypatch.setattr(Path, "read_text", failure)
    with pytest.raises(OSError, match="Device unavailable"):
        verify_file("site.json")


def test_copy_infrastructure_fault_propagates(example, monkeypatch):
    def failure(*args, **kwargs):
        raise RuntimeError("Copy unavailable")
    monkeypatch.setattr(verifier, "deepcopy", failure)
    with pytest.raises(RuntimeError, match="Copy unavailable"):
        verify_document(example, registry=registry_for(RuleResult("test.one", "pass", True)))


def test_deterministic_reports_registry_order_and_all_errors(example):
    meta_z, meta_a = metadata("test.z"), metadata("test.a")
    f_z = finding(meta_z, paths=("/elements/2", "/elements/0"))
    f_a1 = finding(meta_a, paths=("/elements/1",), message="b")
    f_a0 = finding(meta_a, paths=("/elements/0",), message="a")
    r_z = RuleResult(meta_z.rule_id, "fail", False, (f_z,), "Missing facts.")
    r_a = RuleResult(meta_a.rule_id, "fail", True, (f_a1, f_a0, f_a0))
    errors = (Diagnostic("b", "/zones/1", "second", "test.e"),
              Diagnostic("a", "/zones/0", "first", "test.e"))
    r_e = RuleResult("test.e", "error", False, reason="Computation unavailable", errors=errors)
    registry = RuleRegistry([Rule(meta_z, lambda d: r_z), Rule(meta_a, lambda d: r_a),
                             Rule(metadata("test.e"), lambda d: r_e)])
    report = verify_document(example, registry=registry)
    assert report.implemented_rule_ids == ("test.z", "test.a", "test.e")
    assert [r.rule_id for r in report.rule_results] == list(report.implemented_rule_ids)
    assert report.findings == (f_a0, f_a0, f_a1, f_z)  # duplicates are not discarded
    assert [e.path for e in report.errors] == ["/zones/0", "/zones/1"]
    assert report.to_json() == verify_document(example, registry=registry).to_json()
    assert json.loads(report.to_json()) == report.to_dict()
    assert "timestamp" not in report.to_dict()
    assert report.exit_code == 4


@pytest.mark.parametrize("error", [
    Diagnostic("", "", "message", "test.one"), Diagnostic("x", "bad", "message", "test.one"),
    Diagnostic("x", "", " ", "test.one"), Diagnostic("x", "", "message", "wrong.id"),
    Diagnostic("x", "", "message", "test.one", line=True),
    Diagnostic("x", "", "message", "test.one", column=0),
    Diagnostic("x", "", "message", "test.one", schema_path="/~"),
    Diagnostic("x", "", "message", "test.one", exception_type=12), object(),
])
def test_malformed_structured_errors(example, error):
    result = RuleResult("test.one", "error", False, reason="Unavailable.", errors=(error,))
    report = verify_document(example, registry=registry_for(result))
    assert report.errors[0].code == "malformed_result"


@pytest.mark.parametrize("statuses,expected", [
    (["pass", "not_applicable"], 0), (["not_evaluable"], 3),
    (["fail", "not_evaluable"], 1), (["error", "not_evaluable", "fail"], 4),
])
def test_exit_precedence(example, statuses, expected):
    rules = []
    for i, status in enumerate(statuses):
        meta = metadata(f"test.r{i}")
        result = RuleResult(meta.rule_id, status, status in ("pass", "fail", "not_applicable"),
                            (finding(meta),) if status == "fail" else (), reason="Synthetic reason")
        rules.append(Rule(meta, lambda d, result=result: result))
    report = verify_document(example, registry=RuleRegistry(rules))
    assert exit_code(report) == report.exit_code == expected
    assert exit_code(report, operational_error=True) == 4


def test_operational_error_beats_invalid_input():
    report = verify_document({})
    assert exit_code(report) == 2
    assert exit_code(report, operational_error=True) == 4
    assert exit_code(operational_error=True) == 4
    with pytest.raises(ValueError):
        exit_code()
    with pytest.raises(TypeError):
        verify_document({}, registry=[])
