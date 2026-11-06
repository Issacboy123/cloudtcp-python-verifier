"""Runtime metadata stays usable without the human-readable extraction."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from rules.w1_common import load_w1_sections, w1_metadata
from rules.w1_metadata import W1_SECTIONS
from verifier import ALL_REGISTRY


ROOT = Path(__file__).resolve().parents[1]


def test_explicit_metadata_matches_every_extracted_heading_and_citation():
    text = (ROOT / "TCP-W1-1 Rules.md").read_text(encoding="utf-8")
    headings = list(re.finditer(
        r"^### ([A-Z0-9-]+) \u2014 (STANDARD|GUIDANCE|OPTION|SUPPORT) \u2014 (.+)$",
        text, re.MULTILINE,
    ))
    extracted = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        citations = re.findall(r"^\*\*Citation:\*\* (.+)$", text[heading.end():end], re.MULTILINE)
        assert len(citations) == 1
        rule_id, classification, title = heading.groups()
        extracted.append((rule_id, (classification, title.strip(), citations[0].strip())))

    assert len(extracted) == len(W1_SECTIONS) == 76
    assert len({rule_id for rule_id, _ in W1_SECTIONS}) == len(W1_SECTIONS)
    assert tuple(extracted) == W1_SECTIONS
    assert tuple(load_w1_sections().items()) == W1_SECTIONS


def test_returned_sections_cannot_change_later_rule_metadata():
    before = w1_metadata("SIGN-01")
    sections = load_w1_sections()
    sections["SIGN-01"] = ("OPTION", "Changed title", "Changed citation")
    sections.clear()

    assert len(load_w1_sections()) == 76
    assert w1_metadata("SIGN-01") == before


@pytest.fixture
def runtime_checkout(tmp_path):
    """Copy only executable source, the input schema, and one input plan."""
    checkout = tmp_path / "runtime"
    checkout.mkdir()
    for source in ROOT.glob("*.py"):
        shutil.copyfile(source, checkout / source.name)
    rules = checkout / "rules"
    rules.mkdir()
    for source in (ROOT / "rules").glob("*.py"):
        shutil.copyfile(source, rules / source.name)
    for source in (ROOT / "tcp-intermediate-format.schema.json", ROOT / "examples" / "taper-75ft.json"):
        shutil.copyfile(source, checkout / source.name)
    return checkout


@pytest.mark.parametrize("reference_state", ["missing", "malformed"])
def test_cli_and_full_and_w1_registries_do_not_depend_on_markdown(runtime_checkout, reference_state):
    reference = runtime_checkout / "TCP-W1-1 Rules.md"
    if reference_state == "malformed":
        reference.write_bytes(b"\xff\xfeInvalid runtime reference")
    assert reference.exists() == (reference_state == "malformed")
    environment = dict(os.environ, PYTHONPATH=str(runtime_checkout), PYTHONIOENCODING="utf-8")

    help_process = subprocess.run(
        [sys.executable, "-m", "verifier", "--help"], cwd=runtime_checkout,
        env=environment, capture_output=True, encoding="utf-8", timeout=30,
    )
    assert help_process.returncode == 0, help_process.stderr
    assert "usage:" in help_process.stdout
    assert not help_process.stderr

    program = """
import json
from pathlib import Path
import verifier
assert Path(verifier.__file__).resolve().parent == Path.cwd()
default = verifier.verify_file('taper-75ft.json')
w1 = verifier.verify_file('taper-75ft.json', registry=verifier.W1_REGISTRY)
print(json.dumps({
    'default_valid': default.input_valid,
    'default_rule_count': len(default.rule_results),
    'w1_valid': w1.input_valid,
    'w1_rule_count': len(w1.rule_results),
    'w1_errors': len(w1.errors),
}))
"""
    api_process = subprocess.run(
        [sys.executable, "-c", program], cwd=runtime_checkout, env=environment,
        capture_output=True, encoding="utf-8", timeout=30,
    )
    assert api_process.returncode == 0, api_process.stderr
    assert not api_process.stderr
    assert json.loads(api_process.stdout) == {
        "default_valid": True, "default_rule_count": len(ALL_REGISTRY.rules),
        "w1_valid": True, "w1_rule_count": 76, "w1_errors": 0,
    }
