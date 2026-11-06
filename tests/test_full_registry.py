"""Full-source selection and honest report coverage, including legacy isolation."""

from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

from rule_framework import Rule, RuleRegistry, RuleResult
from rules.source_catalog import SOURCE_CATALOG, source_entries
from verifier import ALL_REGISTRY, DEFAULT_REGISTRY, LEGACY_REGISTRY, W1_REGISTRY, verify_document, verify_file


ROOT = Path(__file__).resolve().parents[1]


def result(report, rule_id):
    return next(r for r in report.rule_results if r.rule_id == rule_id)


def test_full_default_accounts_for_both_sources(minimal):
    report = verify_document(minimal)
    assert DEFAULT_REGISTRY is ALL_REGISTRY
    assert len(source_entries()) == 457
    assert Counter(document for document, _ in source_entries()) == {
        "TCP Rules Document.md": 381, "TCP-W1-1 Rules.md": 76,
    }
    assert report.source_coverage == SOURCE_CATALOG
    assert report.registered_rule_ids == report.implemented_rule_ids
    assert set(report.automated_rule_ids) < set(report.registered_rule_ids)
    assert "mutcd.T-013" in report.automated_rule_ids
    assert report.version == "2.0.0" and not report.evaluation_complete
    assert not report.errors
    assert report.to_dict() == verify_document(minimal, registry=ALL_REGISTRY).to_dict()


def test_selected_source_coverage_never_claims_unrelated_entries(minimal):
    legacy = verify_document(minimal, registry=LEGACY_REGISTRY)
    assert len(legacy.registered_rule_ids) == 5
    assert {c.source_rule_id for c in legacy.source_coverage} == {
        "Z-026", "Z-020", "Z-022", "Z-022-B", "T-013",
    }
    assert legacy.automated_rule_ids == ("mutcd.T-013",)
    w1 = verify_document(minimal, registry=W1_REGISTRY)
    assert len(w1.registered_rule_ids) == 76
    assert {c.source_document for c in w1.source_coverage} == {"TCP-W1-1 Rules.md"}
    assert len({c.source_rule_id for c in w1.source_coverage}) == 76


def test_custom_evaluator_cannot_acquire_automated_coverage_by_reusing_metadata(minimal):
    original = LEGACY_REGISTRY.rules[-1]
    fake = Rule(original.metadata, lambda d: RuleResult(original.metadata.rule_id, "pass", True))
    report = verify_document(minimal, registry=RuleRegistry((fake,)))
    assert not report.automated_rule_ids
    assert all(c.disposition not in ("automated", "partial") for c in report.source_coverage)


def test_copied_full_registry_preserves_source_accounting(minimal):
    report = verify_document(minimal, registry=RuleRegistry(ALL_REGISTRY.rules))
    assert report.source_coverage == SOURCE_CATALOG
    assert report.to_dict() == verify_document(minimal).to_dict()


def test_california_replacements_apply_to_shared_source_aliases(minimal):
    minimal["site"]["state"] = "CA"
    ca = verify_document(minimal)
    for federal, replacement in (("Z-025", "CA-001"), ("B-009", "CA-002"),
                                  ("Z-026", "CA-005"), ("D-014", "CA-041")):
        old = result(ca, "mutcd." + federal)
        assert old.status == "not_applicable" and replacement in old.reason
        assert result(ca, "mutcd." + replacement).status == "not_evaluable"
    minimal["site"]["state"] = "NV"
    federal = verify_document(minimal)
    assert result(federal, "mutcd.CA-005").status == "not_applicable"
    assert result(federal, "mutcd.Z-026").status == "not_evaluable"


def test_downstream_overlap_emits_one_finding_with_all_citations():
    report = verify_file(ROOT / "examples/taper-125ft.json")
    downstream = [f for f in report.findings if "taper-1" in f.element_ids]
    assert len(downstream) == 1
    finding = downstream[0]
    assert finding.rule_id == "mutcd.T-013"
    assert {c.source_document for c in finding.citations} == {
        "TCP Rules Document.md", "TCP-W1-1 Rules.md",
    }
    assert any(c.local_reference.startswith("CA-007 ") for c in finding.citations)


def test_informational_source_clauses_do_not_fabricate_passes(minimal):
    report = verify_document(minimal)
    informational = [c for c in report.source_coverage if c.disposition == "informational"]
    assert informational and all(c.canonical_rule_id is None for c in informational)
    assert all(c.limitations for c in report.source_coverage if c.disposition != "automated")
    assert all(f.classification in ("STANDARD", "GUIDANCE") for f in report.findings)


def test_invalid_input_retains_catalog_without_executing():
    report = verify_document({})
    assert report.exit_code == 2 and not report.rule_results
    assert report.source_coverage == SOURCE_CATALOG


def test_isolated_full_check_does_not_claim_other_clauses(minimal):
    downstream = next(r for r in ALL_REGISTRY.rules if r.metadata.rule_id == "mutcd.T-013")
    report = verify_document(minimal, registry=RuleRegistry((downstream,)))
    assert report.source_coverage
    assert all(c.canonical_rule_id == "mutcd.T-013" for c in report.source_coverage)
    assert report.automated_rule_ids == ("mutcd.T-013",)


def test_all_cli_alias_matches_default_and_api():
    path = ROOT / "examples/taper-75ft.json"
    outputs = []
    for selector in ((), ("--registry", "all"), ("--registry", "default")):
        process = subprocess.run([sys.executable, "-m", "verifier", str(path), *selector],
                                 cwd=ROOT, capture_output=True, encoding="utf-8", timeout=30)
        assert process.returncode == 3 and not process.stderr
        outputs.append(json.loads(process.stdout))
    assert outputs[0] == outputs[1] == outputs[2] == verify_file(path).to_dict()
