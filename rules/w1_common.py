"""Shared TCP-W1-1 metadata loading and result helpers."""

from types import MappingProxyType

from rule_framework import Citation, Finding, Rule, RuleMetadata, RuleResult
from rules.w1_metadata import W1_SECTIONS

SOURCE = "TCP-W1-1 Rules.md"
_SECTIONS = MappingProxyType(dict(W1_SECTIONS))


def load_w1_sections():
    """Return detached citation metadata in the extracted document's order.

    The reference Markdown is not opened at runtime. Returning a fresh mapping
    prevents callers from changing metadata used by later registries.
    """
    return dict(_SECTIONS)


def w1_metadata(rule_id, *, limitations=()):
    classification, title, mutcd = _SECTIONS[rule_id]
    heading = f"{rule_id} — {classification} — {title}"
    return RuleMetadata(
        f"mutcd.{rule_id}",
        title,
        classification,
        (Citation(SOURCE, heading, mutcd),),
        tuple(limitations),
    )


def not_evaluable_rule(rule_id, *limitation_lines):
    meta = w1_metadata(rule_id, limitations=limitation_lines)

    def evaluate(document):
        return RuleResult(
            meta.rule_id, "not_evaluable", False,
            reason=" ".join(meta.limitations),
        )

    return Rule(meta, evaluate)


def finding_for(meta, message, *, element_ids=(), zone_ids=(), paths=("",), values=None, units=None):
    severity = "error" if meta.classification == "STANDARD" else "warning"
    return Finding(
        meta.rule_id, severity, meta.classification, message,
        tuple(element_ids), tuple(zone_ids), tuple(paths), meta.citations,
        dict(values or {}), units,
    )
