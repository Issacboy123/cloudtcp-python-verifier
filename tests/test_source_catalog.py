"""Source-accounting checks are distinct from evaluator correctness tests."""

from collections import Counter, defaultdict
from importlib import reload
from pathlib import Path
import re

import pytest

from rules.source_catalog import (
    DISPOSITIONS, SOURCE_CATALOG, selected_clauses, source_entries,
)


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("TCP Rules Document.md", "TCP-W1-1 Rules.md")


def extracted_sections(filename):
    text = (ROOT / filename).read_text(encoding="utf-8")
    headings = list(re.finditer(
        r"^### ([A-Z]+-\d+(?:-[A-Z])?) — (STANDARD|GUIDANCE|OPTION|SUPPORT) — (.+)$",
        text, re.M,
    ))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end():end].split("\n## ", 1)[0]
        body, citation = section.split("**Citation:** ", 1)
        yield heading.group(1), heading.group(0)[4:], body.strip(), citation.splitlines()[0].strip()


def normalized(text):
    return " ".join(text.split())


def clauses(rule_id, filename="TCP-W1-1 Rules.md"):
    return [entry for entry in SOURCE_CATALOG
            if entry.source_document == filename and entry.source_rule_id == rule_id]


def test_every_source_entry_and_all_substantive_text_are_accounted_for():
    grouped = defaultdict(list)
    for entry in SOURCE_CATALOG:
        grouped[(entry.source_document, entry.source_rule_id)].append(entry)
    expected = []
    for filename in DOCUMENTS:
        for rule_id, heading, body, citation in extracted_sections(filename):
            key = (filename, rule_id)
            expected.append(key)
            entries = grouped[key]
            assert entries, key
            # This source phrase has two independently assessed aspects:
            # integer inscription and rounding actual zone length. Both quote
            # the same source text rather than inventing separate source prose.
            reconstructed = entries
            if filename == DOCUMENTS[1] and rule_id == "SIGN-26":
                assert entries[1].text == entries[2].text
                reconstructed = entries[:2]
            assert normalized(" ".join(entry.text for entry in reconstructed)) == normalized(body), key
            assert all(entry.heading == heading and entry.citation == citation for entry in entries)
            assert all(entry.citations[0].source_document == filename for entry in entries)
            assert all(entry.citations[0].local_reference == heading for entry in entries)
            assert all(entry.citations[0].mutcd_reference == citation for entry in entries)
    assert tuple(expected) == source_entries()
    assert len(expected) == 457
    assert Counter(filename for filename, _ in expected) == {
        "TCP Rules Document.md": 381, "TCP-W1-1 Rules.md": 76,
    }


def test_each_clause_has_an_explicit_valid_disposition_and_stable_identifier():
    keys = [(entry.source_document, entry.source_rule_id, entry.clause_id)
            for entry in SOURCE_CATALOG]
    assert len(keys) == len(set(keys))
    for entry in SOURCE_CATALOG:
        assert re.fullmatch(r"c\d{2}", entry.clause_id)
        assert entry.disposition in DISPOSITIONS
        assert entry.classification in {"STANDARD", "GUIDANCE", "OPTION", "SUPPORT"}
        assert entry.text.strip()
        assert isinstance(entry.limitations, tuple)
        if entry.disposition == "informational":
            assert entry.canonical_rule_id is None
        else:
            assert entry.canonical_rule_id.startswith("mutcd.")
        if entry.disposition not in {"automated", "informational"}:
            assert entry.limitations
        assert not any("site-specific selection and conditions" in value for value in entry.limitations)


@pytest.mark.parametrize("rule_id,strengths", [
    ("SIGN-15", ["STANDARD", "OPTION"]),
    ("SIGN-17", ["GUIDANCE", "STANDARD"]),
    ("SIGN-18", ["GUIDANCE", "OPTION"]),
    ("SIGN-19", ["GUIDANCE", "STANDARD"]),
    ("SIGN-23", ["GUIDANCE", "GUIDANCE", "STANDARD"]),
    ("SIGN-24", ["STANDARD", "GUIDANCE"]),
    ("SIGN-26", ["GUIDANCE", "STANDARD", "STANDARD"]),
    ("SHLD-02", ["OPTION", "OPTION", "STANDARD"]),
    ("CHAN-04", ["STANDARD", "GUIDANCE", "STANDARD"]),
    ("CHAN-08", ["GUIDANCE", "OPTION", "STANDARD"]),
    ("CHAN-11", ["GUIDANCE", "STANDARD"]),
    ("ARROW-01", ["GUIDANCE", "STANDARD"]),
    ("ARROW-07", ["GUIDANCE", "STANDARD", "STANDARD"]),
    ("FLAG-01", ["STANDARD", "GUIDANCE"]),
    ("FLAG-02", ["STANDARD", "OPTION", "OPTION"]),
    ("FLAG-05", ["GUIDANCE", "OPTION", "GUIDANCE"]),
    ("FLAG-08", ["STANDARD", "GUIDANCE", "GUIDANCE"]),
])
def test_mixed_source_strengths_are_not_downgraded_to_heading(rule_id, strengths):
    assert [entry.classification for entry in clauses(rule_id)] == strengths


def test_downstream_length_is_atomic_and_one_lane_taper_remains_unsupported():
    source = clauses("T-013", DOCUMENTS[0])[0]
    w1 = clauses("TAPER-02")
    downstream = next(entry for entry in w1 if entry.text.startswith("downstream taper"))
    one_lane = next(entry for entry in w1 if entry.text.startswith("one-lane two-way taper"))
    ca = next(entry for entry in clauses("CA-007", DOCUMENTS[0])
              if entry.text.startswith("The downstream column"))
    assert {entry.canonical_rule_id for entry in (source, downstream, ca)} == {"mutcd.T-013"}
    assert all(entry.disposition == "automated" for entry in (source, downstream, ca))
    assert one_lane.disposition == "input_blocked"
    assert one_lane.canonical_rule_id == "mutcd.T-014"


def test_partial_handlers_do_not_claim_unsupported_subclauses():
    warning, optional_placement, application_placement = clauses("SIGN-21")
    assert warning.canonical_rule_id == "mutcd.SIGN-21"
    assert warning.disposition == "partial"
    assert optional_placement.canonical_rule_id != warning.canonical_rule_id
    assert optional_placement.disposition == "input_blocked"
    assert application_placement.classification == "GUIDANCE"
    assert application_placement.disposition == "input_blocked"
    caution, lane_shift = clauses("ARROW-03")
    assert caution.disposition == "partial"
    assert lane_shift.disposition == "input_blocked"
    assert lane_shift.canonical_rule_id != caution.canonical_rule_id


def test_numeric_merge_length_does_not_claim_adequate_driver_response():
    numeric, review = clauses("T-010", DOCUMENTS[0])
    assert numeric.canonical_rule_id == "mutcd.TAPER-01"
    assert numeric.disposition == "partial"
    assert review.disposition == "review_required"
    assert "driver speed adjustment" in " ".join(review.limitations)


def test_integer_mile_inscription_does_not_claim_correct_actual_length():
    _, integer, extent = clauses("SIGN-26")
    assert integer.canonical_rule_id == "mutcd.SIGN-26.c02"
    assert integer.disposition == "automated"
    assert extent.disposition == "input_blocked"
    assert "actual TTC-zone length" in " ".join(extent.limitations)


def test_first_warning_sign_overlap_uses_one_shared_check():
    source = clauses("Z-107", DOCUMENTS[0])[0]
    w1 = clauses("SIGN-08")[0]
    assert source.canonical_rule_id == w1.canonical_rule_id == "mutcd.SIGN-08"
    assert source.disposition == w1.disposition == "partial"


@pytest.mark.parametrize("rule_id,phrase", [
    ("CA-004", "Caltrans Standard Plans"),
    ("T-065", "incomplete"),
    ("T-089", "Figure 6P-36(CA)"),
    ("CA-035", "classification"),
])
def test_unavailable_or_ambiguous_sources_remain_explicit(rule_id, phrase):
    entry = clauses(rule_id, DOCUMENTS[0])[0]
    assert entry.disposition == "source_blocked"
    assert phrase in " ".join(entry.limitations)


def test_exact_california_table_values_and_reviewer_caveats_are_retained():
    lookup = " ".join(entry.text for entry in clauses("CA-007", DOCUMENTS[0]))
    assert "| 25 | 125 | 63 | 42 | 50 |" in lookup
    assert "| 40 | 320 | 160 | 107 | 50 |" in lookup
    assert "printed whole-foot" in " ".join(
        clauses("T-012", DOCUMENTS[0])[0].limitations)
    assert any("40" in limit and "45" in limit
               for entry in clauses("CA-007", DOCUMENTS[0]) for limit in entry.limitations)


def test_definitions_are_not_fabricated_plan_checks():
    for rule_id in ("D-001", "D-002", "D-003", "D-004", "D-013", "D-013-B"):
        entry = clauses(rule_id, DOCUMENTS[0])[0]
        assert entry.disposition == "informational"
        assert entry.canonical_rule_id is None


def test_jurisdiction_selection_does_not_lose_federal_source_accounting():
    assert len(selected_clauses("CA")) == len(SOURCE_CATALOG)
    outside = selected_clauses("NV")
    assert not any(entry.source_rule_id.startswith("CA-") for entry in outside)
    assert any(entry.source_rule_id == "Z-026" for entry in outside)


def test_catalog_has_no_runtime_markdown_dependency(monkeypatch):
    import rules.source_catalog as module

    def unavailable(*args, **kwargs):
        raise AssertionError("Runtime source-document read")

    monkeypatch.setattr(Path, "read_text", unavailable)
    assert len(reload(module).SOURCE_CATALOG) == len(SOURCE_CATALOG)
