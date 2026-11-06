"""Explicit source accounting, separate from executable-rule coverage.

The source data is checked against the Markdown in tests. Neither this module
nor the verifier reads rule documents at runtime. Clauses preserve mixed source
strengths; sharing a canonical check never turns missing facts into a pass.
"""

from dataclasses import dataclass
from typing import Literal, TypeAlias

from rule_framework import Citation, Classification
from rules.source_data import SOURCE_ROWS


CoverageDisposition: TypeAlias = Literal[
    "automated", "partial", "input_blocked", "review_required", "source_blocked", "informational",
]

DISPOSITIONS = frozenset({
    "automated", "partial", "input_blocked", "review_required",
    "source_blocked", "informational",
})


@dataclass(frozen=True)
class SourceClause:
    source_document: str
    source_rule_id: str
    clause_id: str
    heading: str
    citation: str
    classification: Classification
    text: str
    canonical_rule_id: str | None
    disposition: CoverageDisposition
    limitations: tuple[str, ...]

    @property
    def citations(self) -> tuple[Citation, ...]:
        return (Citation(self.source_document, self.heading, self.citation),)


SOURCE_CATALOG = tuple(SourceClause(*row) for row in SOURCE_ROWS)


def source_entries():
    """Distinct source entries in document order, before overlap resolution."""
    return tuple(dict.fromkeys(
        (clause.source_document, clause.source_rule_id)
        for clause in SOURCE_CATALOG
    ))


def selected_clauses(state):
    """Source inventory for a jurisdiction; federal baselines stay traceable.

    Rule execution applies California replacements. Source accounting retains
    baselines so that a replacement cannot make a source entry disappear.
    """
    return tuple(clause for clause in SOURCE_CATALOG
                 if not clause.source_rule_id.startswith("CA-") or state == "CA")
