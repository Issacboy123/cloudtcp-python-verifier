"""Source-accounted registry; no reference documents are read at runtime."""

from collections import defaultdict
from dataclasses import replace

from rule_framework import Rule, RuleMetadata, RuleRegistry, RuleResult
from rules.full_evaluable import EVALUATORS, CAPABILITIES, LIMITATIONS
from rules.source_catalog import SOURCE_CATALOG
from rules.tapers import TAPER_RULE
from rules.w1_evaluable import EVALUATORS as W1_EVALUATORS


# These replacements do not require roadway ownership or freeway inference.
# Conditional replacements (TA-17, TA-38) stay blocked until their scope is known.
CA_REPLACEMENTS = {
    "Z-025": "CA-001", "B-009": "CA-002", "Z-026": "CA-005",
    "D-014": "CA-041",
}


CA_SUPPLEMENTS = {
    "CA-007": ("mutcd.TAPER-01", "mutcd.TAPER-02"),
    "CA-008": ("mutcd.CHAN-01",),
}


def _state(document):
    return document["site"]["state"].strip().upper()


def _adapt(evaluator, metadata):
    """Bind shared calculations to the canonical ID and complete source citations."""
    def evaluate(document):
        result = evaluator(document)
        return replace(
            result, rule_id=metadata.rule_id,
            findings=tuple(replace(
                finding, rule_id=metadata.rule_id,
                classification=metadata.classification,
                severity="error" if metadata.classification == "STANDARD" else "warning",
                citations=metadata.citations,
            ) for finding in result.findings),
            errors=tuple(replace(error, rule_id=metadata.rule_id) for error in result.errors),
        )
    return evaluate


def _guard(evaluator, metadata, clauses):
    source_ids = {clause.source_rule_id for clause in clauses}
    ca_only = all(rule_id.startswith("CA-") for rule_id in source_ids)
    replacement = CA_REPLACEMENTS.get(metadata.rule_id.removeprefix("mutcd."))

    def evaluate(document):
        california = _state(document) == "CA"
        if ca_only and not california:
            return RuleResult(metadata.rule_id, "not_applicable", True,
                              reason="California-only provision; site.state is not CA.")
        if california and replacement:
            return RuleResult(metadata.rule_id, "not_applicable", True,
                              reason="California replaces this provision: " + replacement + ".")
        return evaluator(document)
    return evaluate


def full_rules():
    grouped = defaultdict(list)
    for clause in SOURCE_CATALOG:
        if clause.canonical_rule_id is not None:
            grouped[clause.canonical_rule_id].append(clause)
    rules = []
    for rule_id, clauses in grouped.items():
        classifications = {clause.classification for clause in clauses}
        if len(classifications) != 1:
            raise ValueError(f"Shared check {rule_id} mixes source classifications: {classifications}")
        citations = tuple(dict.fromkeys(citation for clause in clauses for citation in clause.citations))
        key = rule_id.removeprefix("mutcd.")
        if any(clause.disposition in ("automated", "partial") for clause in clauses):
            if key not in EVALUATORS:
                raise ValueError(f"Catalog advertises executable coverage without an evaluator: {rule_id}")
        if any(clause.disposition == "automated" for clause in clauses):
            if CAPABILITIES.get(key) != "automated":
                raise ValueError(f"Catalog overstates automated capability: {rule_id}")
        # Delegated California evaluations retain the federal source trail while
        # producing a single finding for the same measured deficiency.
        for shared_id in CA_SUPPLEMENTS.get(key, ()):
            citations = tuple(dict.fromkeys((*citations, *(
                citation for clause in grouped.get(shared_id, ()) for citation in clause.citations
            ))))
        limitations = tuple(dict.fromkeys(
            limit for clause in clauses for limit in clause.limitations
        ))
        limitations = tuple(dict.fromkeys((*limitations, *LIMITATIONS.get(key, ()))))
        metadata = RuleMetadata(rule_id, clauses[0].heading, clauses[0].classification,
                                citations, limitations)
        evaluator = EVALUATORS.get(key)
        if evaluator is None:
            reason = " ".join(limitations)
            if not reason:
                raise ValueError(f"Unsupported check {rule_id} needs a specific limitation.")

            def evaluate(document, meta=metadata, explanation=reason):
                return RuleResult(meta.rule_id, "not_evaluable", False, reason=explanation)
        else:
            evaluate = _adapt(evaluator, metadata)
        rules.append(Rule(metadata, _guard(evaluate, metadata, clauses)))
    return tuple(rules)


ALL_REGISTRY = RuleRegistry(full_rules())
_FULL_RULES = {rule.metadata.rule_id: rule for rule in ALL_REGISTRY.rules}


def source_coverage(registry):
    """Return source accounting for the selected registry, never for unrelated rules."""
    if registry.rules == ALL_REGISTRY.rules:
        return SOURCE_CATALOG
    selected = []
    for rule in registry.rules:
        if rule == _FULL_RULES.get(rule.metadata.rule_id):
            selected.extend(clause for clause in SOURCE_CATALOG
                            if clause.canonical_rule_id == rule.metadata.rule_id)
            continue
        references = {(citation.source_document,
                       citation.local_reference.split(" \u2014 ", 1)[0])
                      for citation in rule.metadata.citations}
        for clause in SOURCE_CATALOG:
            if ((clause.source_document, clause.source_rule_id) not in references
                    and ("CA MUTCD", clause.source_rule_id) not in references):
                continue
            # Legacy/W1 selections do not acquire full-registry implementations.
            key = rule.metadata.rule_id.removeprefix("mutcd.")
            supported = rule == TAPER_RULE or (
                key in {"TAPER-01", "TAPER-02", "CHAN-01", "BUFFER-01",
                        "SIGN-11", "SIGN-21", "ARROW-03"}
                and rule.evaluator is W1_EVALUATORS.get(key)
            )
            disposition = clause.disposition
            if supported and disposition in ("automated", "partial"):
                disposition = "automated" if key == "T-013" else "partial"
            if not supported and disposition in ("automated", "partial"):
                disposition = "input_blocked"
            limits = tuple(dict.fromkeys((*clause.limitations, *rule.metadata.limitations)))
            if not supported:
                limits = (*limits, "This registry has no executable comparison for this clause.")
            selected.append(replace(clause, canonical_rule_id=rule.metadata.rule_id,
                                    disposition=disposition, limitations=limits))
    return tuple(selected)


def automated_rule_ids(registry, coverage):
    """Only wholly automated checks qualify; registration is not implementation."""
    by_id = defaultdict(list)
    for clause in coverage:
        if clause.canonical_rule_id is not None:
            by_id[clause.canonical_rule_id].append(clause)
    return tuple(rule.metadata.rule_id for rule in registry.rules
                 if by_id[rule.metadata.rule_id]
                 and all(clause.disposition == "automated" for clause in by_id[rule.metadata.rule_id]))
