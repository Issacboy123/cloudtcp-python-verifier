"""Real child-process CLI acceptance; injected rules are synthetic tests only."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from verifier import load_document, verify_document, verify_file


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def run_cli(*args, cwd=ROOT, setup=None, env_overrides=None):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    env.update(env_overrides or {})
    if setup is None:
        command = [sys.executable, "-m", "verifier", *map(str, args)]
    else:
        command = [sys.executable, "-c", setup + "\nraise SystemExit(verifier.main())", *map(str, args)]
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          encoding="utf-8", timeout=30)


@pytest.mark.parametrize("name,expected,status", [
    ("taper-75ft.json", 3, "pass"), ("taper-125ft.json", 1, "fail"),
    ("invalid.json", 2, None),
])
@pytest.mark.parametrize("explicit", [False, True])
def test_json_examples_match_python_api(name, expected, status, explicit):
    path = EXAMPLES / name
    args = (path, "--format", "json") if explicit else (path,)
    process = run_cli(*args)
    assert process.returncode == expected
    assert process.stderr == ""
    report = json.loads(process.stdout)
    assert report == verify_file(path).to_dict()
    assert report["coverage_scope"] == "implemented_rules_only"
    if status:
        assert report["rule_results"][-1]["status"] == status
        assert [r["status"] for r in report["rule_results"][:4]] == ["not_evaluable"] * 4
        assert "CA-005" in " ".join(report["limitations"])
        assert "endpoint" in " ".join(report["limitations"])
    else:
        assert report["rule_results"] == []


@pytest.mark.parametrize("name,expected", [
    ("taper-75ft.json", 3), ("taper-125ft.json", 1), ("invalid.json", 2),
])
def test_text_findings_citations_and_every_gap(name, expected):
    process = run_cli(EXAMPLES / name, "--format", "text")
    assert process.returncode == expected and process.stderr == ""
    output = process.stdout
    assert "Coverage: implemented_rules_only" in output
    assert "not comprehensive MUTCD compliance" in output
    assert "Incomplete checks:" in output
    for rule_id in ("mutcd.Z-026", "mutcd.Z-020", "mutcd.Z-022", "mutcd.Z-022-B"):
        assert rule_id in output.split("Incomplete checks:", 1)[1]
    assert "CA MUTCD" in output and "Federal MUTCD" in output
    assert "TCP Rules Document.md" not in output
    assert "CA-005" in output and "endpoint" in output
    if expected == 1:
        assert "GUIDANCE/warning" in output
        assert "taper-1" in output and "termination-1" in output
        assert "/elements/0/end_station" in output
        assert '"length_ft": 125' in output and "units: feet" in output
        assert "Table 6B-3" in output
    if expected == 2:
        assert "[schema.required]" in output and "not executed" in output


@pytest.mark.parametrize("args", [
    (), ("--bogus",), ("file.json", "second.json"),
    ("file.json", "--format", "xml"), ("file.json", "--format"),
    ("--format", "text"), ("file.json", "--for", "json"),
])
def test_argument_errors_are_structured_json(args):
    process = run_cli(*args)
    assert process.returncode == 2 and process.stderr == ""
    report = json.loads(process.stdout)
    assert report["errors"][0]["code"] == "cli_arguments"
    assert report["rule_results"] == [] and not report["input_valid"]


def test_help():
    process = run_cli("--help")
    assert process.returncode == 0 and process.stderr == ""
    assert "SITE.json" in process.stdout and "--format {json,text}" in process.stdout


@pytest.mark.parametrize("content,code", [
    ('{"format_version":', "invalid_json"),
    ('{"format_version":"1.0.0","format_version":"1.0.0"}', "duplicate_key"),
    ('{"format_version":NaN}', "non_finite_number"),
    ('{}', "schema.required"),
])
def test_invalid_input_never_executes_rules(tmp_path, content, code):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    setup = '''
import verifier
from rule_framework import Rule, RuleRegistry
def forbidden(document):
    raise AssertionError("RULE EXECUTED ON INVALID INPUT")
verifier.DEFAULT_REGISTRY = RuleRegistry(Rule(r.metadata, forbidden) for r in verifier.DEFAULT_REGISTRY.rules)
'''
    process = run_cli(path, setup=setup)
    assert process.returncode == 2 and process.stderr == ""
    report = json.loads(process.stdout)
    assert code in {e["code"] for e in report["errors"]}
    assert report["rule_results"] == report["findings"] == []


def test_missing_input_is_invalid(tmp_path):
    process = run_cli(tmp_path / "missing.json")
    assert process.returncode == 2
    report = json.loads(process.stdout)
    assert not report["input_valid"] and report["rule_results"] == []


def test_another_cwd_and_checkout_api(tmp_path):
    path = EXAMPLES / "taper-75ft.json"
    process = run_cli(path, cwd=tmp_path)
    assert process.returncode == 3 and process.stderr == ""
    assert json.loads(process.stdout) == verify_document(load_document(path)).to_dict()
    process = subprocess.run(
        [sys.executable, "-c", "from verifier import load_document, verify_document, verify_file; "
         "import sys; p=sys.argv[1]; r=verify_file(p); "
         "assert r.to_dict() == verify_document(load_document(p)).to_dict(); print(r.to_json(), end='')",
         str(path)], cwd=tmp_path, env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8"),
        capture_output=True, encoding="utf-8", timeout=30,
    )
    assert process.returncode == 0 and process.stderr == ""
    assert json.loads(process.stdout)["rule_results"][-1]["status"] == "pass"


@pytest.mark.parametrize("format", ["json", "text"])
@pytest.mark.parametrize("failure", ["exception", "malformed", "copy"])
def test_execution_error_retains_other_findings_and_gaps(format, failure):
    setup = '''
import verifier
from rule_framework import Rule, RuleMetadata, RuleRegistry, RuleResult
meta = RuleMetadata("test.crash", "Synthetic crash", "GUIDANCE", verifier.TAPER_RULE.metadata.citations)
def crash(document):
    raise RuntimeError("synthetic execution failure")
verifier.DEFAULT_REGISTRY = RuleRegistry((*verifier.DEFAULT_REGISTRY.rules, Rule(meta, crash)))
'''
    if failure == "malformed":
        setup += '\nverifier.DEFAULT_REGISTRY = RuleRegistry((*verifier.DEFAULT_REGISTRY.rules[:-1], Rule(meta, lambda d: None)))\n'
    if failure == "copy":
        setup += '''
original = verifier.deepcopy
calls = 0
def copy_failure(value):
    global calls
    calls += 1
    if calls == 11:  # two copies per completed rule; fail before sixth evaluator
        raise OSError("synthetic copy infrastructure failure")
    return original(value)
verifier.deepcopy = copy_failure
'''
    process = run_cli(EXAMPLES / "taper-125ft.json", "--format", format, setup=setup)
    assert process.returncode == 4 and process.stderr == ""
    if format == "json":
        report = json.loads(process.stdout)
        assert len(report["findings"]) == 1
        assert report["findings"][0]["rule_id"] == "mutcd.T-013"
        assert [r["status"] for r in report["rule_results"][:4]] == ["not_evaluable"] * 4
        assert report["errors"][0]["code"] == {
            "exception": "rule_exception", "malformed": "malformed_result", "copy": "operational_error",
        }[failure]
        assert not report["evaluation_complete"]
        if failure == "copy":
            assert "test.crash: Execution did not reach this check." in report["limitations"]
    else:
        assert "GUIDANCE/warning" in process.stdout
        assert "mutcd.Z-026:" in process.stdout.split("Incomplete checks:")[1]
        assert "test.crash" in process.stdout and "CA-005" in process.stdout


@pytest.mark.parametrize("fault", ["schema", "load"])
def test_operational_input_fault_is_structured_and_api_still_raises(fault):
    setup = '''
import ingestion
import verifier
def broken(*args):
    raise RuntimeError("synthetic infrastructure failure")
'''
    setup += "ingestion._validator = broken\n" if fault == "schema" else "verifier.load_document = broken\n"
    setup += '''
try:
    verifier.verify_file(__import__('sys').argv[1])
except RuntimeError:
    pass
else:
    raise AssertionError("Python API swallowed infrastructure failure")
'''
    process = run_cli(EXAMPLES / "taper-75ft.json", setup=setup)
    assert process.returncode == 4 and process.stderr == ""
    report = json.loads(process.stdout)
    assert report["errors"][0]["code"] == "operational_error"
    assert report["errors"][0]["exception_type"] == "RuntimeError"
    assert not report["input_valid"] and not report["evaluation_complete"]
    assert report["rule_results"] == []
    assert len([s for s in report["limitations"] if "Execution did not reach" in s]) == 5


def test_resolved_registry_exit_zero_and_incidental_output_goes_to_stderr():
    setup = '''
import verifier
from rule_framework import Rule, RuleRegistry, RuleResult
def resolved(document):
    print("incidental evaluator output")
    return RuleResult("mutcd.T-013", "pass", True)
verifier.DEFAULT_REGISTRY = RuleRegistry((Rule(verifier.TAPER_RULE.metadata, resolved),))
'''
    process = run_cli(EXAMPLES / "taper-75ft.json", setup=setup)
    assert process.returncode == 0
    assert process.stderr == "incidental evaluator output\n"
    assert json.loads(process.stdout)["evaluation_complete"]


def test_partial_findings_take_precedence_over_incomplete():
    setup = '''
import verifier
from dataclasses import replace
from rule_framework import Rule, RuleRegistry
def partial(document):
    return replace(verifier.TAPER_RULE.evaluator(document), complete=False, reason="Synthetic missing subject facts")
verifier.DEFAULT_REGISTRY = RuleRegistry((Rule(verifier.TAPER_RULE.metadata, partial),))
'''
    process = run_cli(EXAMPLES / "taper-125ft.json", setup=setup)
    assert process.returncode == 1 and process.stderr == ""
    report = json.loads(process.stdout)
    assert report["findings"] and not report["rule_results"][0]["complete"]
    assert "Synthetic missing subject facts" in " ".join(report["limitations"])


def test_text_render_failure_retains_report_in_json_fallback():
    setup = '''
import verifier
def broken(report):
    raise RuntimeError("synthetic text rendering failure")
verifier._text_report = broken
'''
    process = run_cli(EXAMPLES / "taper-125ft.json", "--format", "text", setup=setup)
    assert process.returncode == 4 and process.stderr == ""
    report = json.loads(process.stdout)
    assert len(report["findings"]) == 1 and len(report["rule_results"]) == 5
    assert report["errors"][0]["code"] == "operational_error"
    assert "CA-005" in " ".join(report["limitations"])


def test_json_is_portable_with_non_ascii_input(tmp_path):
    document = load_document(EXAMPLES / "taper-125ft.json")
    document["elements"][0]["element_id"] = "taper-雪-🚧"
    path = tmp_path / "unicode.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    process = run_cli(path)
    assert process.returncode == 1 and process.stderr == ""
    assert process.stdout.isascii()
    assert json.loads(process.stdout)["findings"][0]["element_ids"] == ["taper-雪-🚧"]


def test_text_encoding_failure_is_structured_and_retains_findings():
    process = run_cli(EXAMPLES / "taper-125ft.json", "--format", "text",
                      env_overrides={"PYTHONIOENCODING": "ascii"})
    assert process.returncode == 4 and process.stderr == ""
    report = json.loads(process.stdout)
    assert report["errors"][0]["code"] == "operational_error"
    assert report["errors"][0]["exception_type"] == "UnicodeEncodeError"
    assert len(report["findings"]) == 1 and len(report["rule_results"]) == 5
    assert "CA-005" in " ".join(report["limitations"])


def test_unicode_argument_error_uses_portable_json():
    process = run_cli("file.json", "--unknown-雪", env_overrides={"PYTHONIOENCODING": "ascii"})
    assert process.returncode == 2 and process.stderr == ""
    error = json.loads(process.stdout)["errors"][0]
    assert error["code"] == "cli_arguments" and "雪" in error["message"]


@pytest.mark.parametrize("failure", ["write", "flush"])
def test_unavailable_stdout_has_structured_stderr_fallback(failure):
    setup = '''
import sys
import verifier
class BrokenOutput:
    def write(self, text):
        raise BrokenPipeError("synthetic stdout write failure")
    def flush(self):
        raise BrokenPipeError("synthetic stdout flush failure")
sys.stdout = BrokenOutput()
'''
    if failure == "flush":
        setup = setup.replace('raise BrokenPipeError("synthetic stdout write failure")', 'return len(text)')
    process = run_cli(EXAMPLES / "taper-125ft.json", setup=setup)
    assert process.returncode == 4 and process.stdout == ""
    report = json.loads(process.stderr)
    assert report["errors"][0]["exception_type"] == "BrokenPipeError"
    assert len(report["findings"]) == 1 and len(report["rule_results"]) == 5
    assert "CA-005" in " ".join(report["limitations"])


def test_help_write_failure_is_operational():
    setup = '''
import sys
import verifier
class BrokenOutput:
    def write(self, text):
        raise BrokenPipeError("synthetic help output failure")
    def flush(self):
        raise BrokenPipeError("synthetic help flush failure")
sys.stdout = BrokenOutput()
'''
    process = run_cli("--help", setup=setup)
    assert process.returncode == 4 and process.stdout == ""
    report = json.loads(process.stderr)
    assert report["errors"][0]["code"] == "operational_error"
    assert report["rule_results"] == []


def test_flush_failure_does_not_append_second_json_report():
    setup = '''
import sys
import verifier
original_stdout = sys.stdout
class FailedFlush:
    def write(self, text):
        return original_stdout.write(text)
    def flush(self):
        original_stdout.flush()
        raise OSError("synthetic flush failure after delivery")
sys.stdout = FailedFlush()
'''
    process = run_cli(EXAMPLES / "taper-125ft.json", setup=setup)
    assert process.returncode == 4
    assert len(json.loads(process.stdout)["findings"]) == 1
    assert json.loads(process.stderr)["errors"][0]["code"] == "operational_error"
