"""TCP-W1-1 rule coverage: citations, scores, compliant and violating plans."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from rules.w1_common import load_w1_sections
from rules.w1_evaluable import EVALUATORS
from rules.w1_registry import w1_rules
from verifier import W1_REGISTRY, verify_document, verify_file

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "examples" / "w1"
W1_DOC = ROOT / "TCP-W1-1 Rules.md"
EVALUABLE_IDS = tuple(EVALUATORS)
ALL_IDS = tuple(load_w1_sections())


def result_for(rule_id, document):
    report = verify_document(document, registry=W1_REGISTRY)
    matches = [r for r in report.rule_results if r.rule_id == f"mutcd.{rule_id}"]
    assert len(matches) == 1
    return matches[0]


def load_plan(rule_id, kind):
    return json.loads((PLANS / rule_id / f"{kind}.json").read_text(encoding="utf-8"))


def test_w1_registry_covers_every_extracted_rule():
    assert len(w1_rules()) == len(ALL_IDS) == 76
    assert tuple(r.metadata.rule_id for r in W1_REGISTRY.rules) == tuple(
        f"mutcd.{rule_id}" for rule_id in ALL_IDS
    )


def test_w1_citations_match_source_document():
    text = W1_DOC.read_text(encoding="utf-8")
    for rule in W1_REGISTRY.rules:
        assert len(rule.metadata.citations) == 1
        citation = rule.metadata.citations[0]
        assert citation.source_document == "TCP-W1-1 Rules.md"
        heading = f"### {citation.local_reference}\n"
        assert heading in text
        section = text.split(heading, 1)[1].split("\n### ", 1)[0]
        assert "**Citation:** " in section
        source = section.split("**Citation:** ", 1)[1].split("\n", 1)[0].strip()
        assert citation.mutcd_reference == source


@pytest.mark.parametrize("rule_id", EVALUABLE_IDS)
def test_evaluable_compliant_plan_passes_with_score_one(rule_id):
    plan = load_plan(rule_id, "compliant")
    before = deepcopy(plan)
    result = result_for(rule_id, plan)
    assert plan == before
    assert result.status == "pass" and result.complete
    assert result.score == pytest.approx(1.0)
    assert not result.findings


@pytest.mark.parametrize("rule_id", EVALUABLE_IDS)
def test_evaluable_violating_plan_scores_below_one(rule_id):
    plan = load_plan(rule_id, "violating")
    result = result_for(rule_id, plan)
    assert result.score is not None and 0 <= result.score < 1
    if rule_id == "BUFFER-01":
        # OPTION: short buffer grades down without findings.
        assert result.status == "pass" and result.complete and not result.findings
    else:
        assert result.status == "fail" and result.complete and result.findings
        assert all(0 <= f.values["score"] <= 1 for f in result.findings)


@pytest.mark.parametrize("rule_id", [r for r in ALL_IDS if r not in EVALUATORS])
def test_stub_plans_are_not_evaluable_with_null_score(rule_id):
    for kind in ("compliant", "violating"):
        result = result_for(rule_id, load_plan(rule_id, kind))
        assert result.status == "not_evaluable" and not result.complete
        assert result.score is None and result.reason


def test_cli_plan_files_round_trip(tmp_path):
    path = PLANS / "TAPER-01" / "violating.json"
    report = verify_file(path, registry=W1_REGISTRY)
    assert report.input_valid
    taper = next(r for r in report.rule_results if r.rule_id == "mutcd.TAPER-01")
    assert taper.status == "fail" and taper.score < 1
