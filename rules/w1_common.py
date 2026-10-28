"""Shared TCP-W1-1 metadata loading and result helpers."""

from functools import lru_cache
from pathlib import Path
import re

from rule_framework import Citation, Finding, Rule, RuleMetadata, RuleResult

SOURCE = "TCP-W1-1 Rules.md"
_ROOT = Path(__file__).resolve().parents[1]
_DOC = _ROOT / SOURCE


@lru_cache(maxsize=1)
def load_w1_sections():
    """Parse TCP-W1-1 Rules.md into {rule_id: (classification, title, citation)}."""
    text = _DOC.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^### ([A-Z0-9-]+) — (STANDARD|GUIDANCE|OPTION|SUPPORT) — (.+)\n"
        r"\n"
        r"([\s\S]*?)"
        r"\*\*Citation:\*\* (.+)",
        re.MULTILINE,
    )
    sections = {}
    for match in pattern.finditer(text):
        rule_id, classification, title, _body, citation = match.groups()
        sections[rule_id] = (classification, title.strip(), citation.strip())
    return sections


def w1_metadata(rule_id, *, limitations=()):
    classification, title, mutcd = load_w1_sections()[rule_id]
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
