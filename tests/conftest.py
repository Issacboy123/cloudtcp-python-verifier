import json
from pathlib import Path

import pytest


@pytest.fixture
def example():
    """Use the authoritative example directly, without maintaining a copy."""
    reference = Path(__file__).resolve().parents[1] / "tcp-field-reference.md"
    text = reference.read_text(encoding="utf-8")
    return json.loads(text.split("```json\n", 1)[1].split("```", 1)[0])


@pytest.fixture
def minimal(example):
    return {
        key: example[key] for key in
        ("format_version", "site", "typical_application", "zones", "elements")
    }
