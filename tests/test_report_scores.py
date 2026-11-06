"""Score contracts must preserve status, partial findings, and report compatibility."""

from decimal import Decimal
import json

import pytest

from rule_framework import Citation, Finding, Rule, RuleMetadata, RuleRegistry, RuleResult
from verifier import _text_report, verify_document


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
    assert report.rule_results[0].score is None
    assert report.errors[0].code == "malformed_result"
    assert "score" in report.errors[0].message


@pytest.mark.parametrize("status,complete", [
    ("not_applicable", True), ("not_evaluable", False), ("error", False),
])
def test_unevaluated_results_cannot_claim_a_score(minimal, status, complete):
    result = RuleResult(META.rule_id, status, complete, reason="No evaluated subjects.", score=1)
    report = report_for(minimal, result)
    assert report.errors[0].code == "malformed_result"
    assert report.rule_results[0].score is None


@pytest.mark.parametrize("score", [0, 0.25, 1])
def test_scores_serialize_with_minor_report_version(minimal, score):
    report = report_for(minimal, RuleResult(META.rule_id, "pass", True, score=score))
    payload = json.loads(report.to_json())
    assert payload["version"] == "1.2.0"
    assert minimal["format_version"] == "1.0.0"
    assert payload["rule_results"][0]["score"] == score
    assert report.exit_code == 0
    assert f"Score: {score}" in _text_report(report)


def test_partial_failure_keeps_score_and_findings(minimal):
    finding = Finding(META.rule_id, "warning", "GUIDANCE", "Known short subject.",
                      ("T1",), (), ("/elements",), META.citations)
    result = RuleResult(META.rule_id, "fail", False, (finding,),
                        reason="Other subjects lack width.", score=0.25)
    report = report_for(minimal, result)
    assert report.exit_code == 1
    assert not report.evaluation_complete
    assert report.rule_results[0].score == 0.25
    assert report.findings == (finding,)
    text = _text_report(report)
    assert "fail; complete=False" in text and "Score: 0.25" in text
    assert "Other subjects lack width." in text


def test_unscored_result_is_explicit_in_json_and_text(minimal):
    result = RuleResult(META.rule_id, "not_evaluable", False, reason="Missing facts.")
    report = report_for(minimal, result)
    assert report.to_dict()["rule_results"][0]["score"] is None
    assert "Score: unscored" in _text_report(report)
    assert report.exit_code == 3


def test_option_score_does_not_create_a_violation(minimal):
    meta = RuleMetadata("test.option", "Synthetic option", "OPTION", META.citations)
    result = RuleResult(meta.rule_id, "pass", True, score=0.1)
    report = report_for(minimal, result, meta)
    assert report.exit_code == 0
    assert report.findings == ()
    assert report.rule_results[0].score == 0.1
