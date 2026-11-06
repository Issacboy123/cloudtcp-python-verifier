"""Score contracts must preserve status, partial findings, and report compatibility."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path

import pytest

from rule_framework import Citation, Finding, Rule, RuleMetadata, RuleRegistry, RuleResult, finding_key
from verifier import (
    ALL_REGISTRY, LEGACY_REGISTRY, W1_REGISTRY, ReportRuleResult,
    _text_report, verify_document, verify_file,
)


META = RuleMetadata("test.score", "Synthetic score", "GUIDANCE", (
    Citation("synthetic.md", "SCORE-1", "Synthetic test only"),
))


def report_for(document, result, meta=META):
    return verify_document(document, registry=RuleRegistry((Rule(meta, lambda d: result),)))


@pytest.mark.parametrize("score", [True, False, "0.5", Decimal("0.5"), float("nan"),
                                    float("inf"), -float("inf"), -0.01, 1.01, 10**1000])
def test_invalid_scores_become_structured_rule_errors(minimal, score):
    report = report_for(minimal, RuleResult(META.rule_id, "pass", True, score=score))
    assert report.exit_code == 4
    assert report.rule_results[0].status == "error"
    assert report.rule_results[0].score == 0
    assert type(report.rule_results[0].score) is int
    assert report.errors[0].code == "malformed_result"
    assert "score" in report.errors[0].message


@pytest.mark.parametrize("status,complete", [
    ("not_applicable", True), ("not_evaluable", False), ("error", False),
])
def test_unevaluated_results_cannot_claim_a_score(minimal, status, complete):
    result = RuleResult(META.rule_id, status, complete, reason="No evaluated subjects.", score=1)
    report = report_for(minimal, result)
    assert report.errors[0].code == "malformed_result"
    assert report.rule_results[0].score == 0


@pytest.mark.parametrize("score", [None, 0, 0.25, 1])
def test_passing_scores_serialize_as_integer_one(minimal, score):
    result = RuleResult(META.rule_id, "pass", True, score=score)
    report = report_for(minimal, result)
    payload = json.loads(report.to_json())
    assert payload["version"] == "2.0.0"
    assert minimal["format_version"] == "1.0.0"
    assert payload["rule_results"][0]["score"] == 1
    assert type(payload["rule_results"][0]["score"]) is int
    assert payload["rule_results"][0]["status"] == "pass"
    assert report.exit_code == 0
    assert "Score: 1" in _text_report(report)
    assert result.score == score


def test_partial_failure_scores_zero_and_keeps_findings(minimal):
    finding = Finding(META.rule_id, "warning", "GUIDANCE", "Known short subject.",
                      ("T1",), (), ("/elements",), META.citations)
    result = RuleResult(META.rule_id, "fail", False, (finding,),
                        reason="Other subjects lack width.", score=0.25)
    report = report_for(minimal, result)
    assert report.exit_code == 1
    assert not report.evaluation_complete
    assert report.rule_results[0].score == 0
    assert report.findings == (finding,)
    text = _text_report(report)
    assert "fail; complete=False" in text and "Score: 0" in text
    assert "Other subjects lack width." in text


def test_missing_facts_score_zero_in_json_and_text(minimal):
    result = RuleResult(META.rule_id, "not_evaluable", False, reason="Missing facts.")
    report = report_for(minimal, result)
    assert report.to_dict()["rule_results"][0]["score"] == 0
    assert "Score: 0" in _text_report(report)
    assert report.exit_code == 3


def test_option_score_does_not_create_a_violation(minimal):
    meta = RuleMetadata("test.option", "Synthetic option", "OPTION", META.citations)
    result = RuleResult(meta.rule_id, "pass", True, score=0.1)
    report = report_for(minimal, result, meta)
    assert report.exit_code == 0
    assert report.findings == ()
    assert report.rule_results[0].score == 1
    assert result.score == 0.1


@pytest.mark.parametrize("status,complete,expected_exit", [
    ("pass", True, 0), ("fail", True, 1), ("not_applicable", True, 0),
    ("not_evaluable", False, 3), ("error", False, 4),
])
def test_binary_scores_preserve_status_completeness_and_exit(minimal, status, complete, expected_exit):
    finding = Finding(META.rule_id, "warning", "GUIDANCE", "Known issue.",
                      ("T1",), (), ("/elements",), META.citations)
    result = RuleResult(META.rule_id, status, complete,
                        findings=(finding,) if status == "fail" else (), reason="Outcome reason.")
    report = report_for(minimal, result)
    actual = report.rule_results[0]
    assert type(actual) is ReportRuleResult
    assert actual.status == status and actual.complete == complete
    assert actual.reason == result.reason
    assert actual.score == (1 if status == "pass" else 0)
    assert type(actual.score) is int
    assert report.exit_code == expected_exit


def test_finding_scores_normalize_without_mutation_and_resort(minimal):
    first = Finding(META.rule_id, "warning", "GUIDANCE", "Known issue.",
                    ("T1",), (), ("/elements",), META.citations,
                    {"score": 0.1, "z_measurement": 20}, "feet")
    second = replace(first, values={"score": 0.9, "z_measurement": 10})
    unscored = replace(first, paths=("/site",), values={"length_ft": 125})
    findings = (first, second, unscored)
    before = deepcopy(findings)
    result = RuleResult(META.rule_id, "fail", True, findings, score=0.1)
    report = report_for(minimal, result)
    expected = tuple(sorted((
        replace(first, values={"score": 0, "z_measurement": 20}),
        replace(second, values={"score": 0, "z_measurement": 10}), unscored,
    ), key=finding_key))
    assert report.findings == report.rule_results[0].findings == expected
    assert report.findings[0].values["z_measurement"] == 10
    assert findings == before and result.score == 0.1
    assert "score" not in report.findings[-1].values
    assert all(type(f.values["score"]) is int for f in report.findings if "score" in f.values)
    assert report.to_dict()["findings"] == report.to_dict()["rule_results"][0]["findings"]
    assert report.to_json() == report_for(minimal, result).to_json()


@pytest.mark.parametrize("registry", [ALL_REGISTRY, W1_REGISTRY, LEGACY_REGISTRY])
@pytest.mark.parametrize("length", [75, 125])
def test_all_registries_and_file_api_use_binary_report_scores(registry, length):
    path = Path(__file__).resolve().parents[1] / "examples" / f"taper-{length}ft.json"
    report = verify_file(path, registry=registry)
    assert report.rule_results
    for result in report.rule_results:
        assert type(result.score) is int
        assert result.score == (1 if result.status == "pass" else 0)
        assert all(f.values["score"] == 0 for f in result.findings if "score" in f.values)
    assert report.exit_code == (3 if length == 75 else 1)


def test_actual_optional_buffer_pass_has_one_despite_internal_fractional_score():
    path = Path(__file__).resolve().parents[1] / "examples" / "w1" / "BUFFER-01" / "violating.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    rule = next(rule for rule in W1_REGISTRY.rules if rule.metadata.rule_id == "mutcd.BUFFER-01")
    internal = rule.evaluator(document)
    assert internal.status == "pass" and internal.score < 1
    report = verify_document(document, registry=RuleRegistry((rule,)))
    assert report.rule_results[0].status == "pass" and report.rule_results[0].score == 1
    assert not report.findings and report.exit_code == 0
