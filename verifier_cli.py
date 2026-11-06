"""Command parsing and output recovery for the checkout CLI."""

import argparse
from contextlib import redirect_stdout
import sys
from types import ModuleType

from ingestion import InputValidationError
from rule_framework import Diagnostic
from reporting import Report, build_report, format_json, format_text, operational_report

_REGISTRY_ATTRIBUTES = {
    "default": "DEFAULT_REGISTRY",
    "all": "ALL_REGISTRY",
    "legacy": "LEGACY_REGISTRY",
    "w1": "W1_REGISTRY",
}


class _ArgumentError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _ArgumentError(message)

    def print_help(self, file=None):
        # argparse suppresses write OSErrors by default. Let the CLI boundary
        # convert them and catch flush failures before interpreter shutdown.
        stream = sys.stdout if file is None else file
        stream.write(self.format_help())
        stream.flush()


def _emit_report(report: Report, output_format: str) -> int:
    emission_started = False
    try:
        with redirect_stdout(sys.stderr):
            output = format_json(report) if output_format == "json" else format_text(report)
        emission_started = True
        sys.stdout.write(output)
        sys.stdout.flush()
    except Exception as exc:
        report = operational_report(exc, report, input_valid=report.input_valid)
        fallback = format_json(report)
        # Formatting and encoding failures have not emitted report bytes. A
        # write/flush I/O fault may have emitted some: do not append a second JSON
        # document to that stream or retry a broken pipe.
        fallback_written = False
        if not emission_started or isinstance(exc, UnicodeEncodeError):
            try:
                sys.stdout.write(fallback)
                sys.stdout.flush()
                fallback_written = True
            except Exception:
                pass
        if not fallback_written:
            # An unavailable output pipe cannot carry a JSON report. Use stderr
            # and prevent a second failing stdout flush during interpreter exit.
            try:
                sys.stderr.write(fallback)
                sys.stderr.flush()
            except Exception:
                pass  # Neither stream is usable; the process still returns 4.
            sys.stdout = None
    return report.exit_code


def _requested_registry_name(argv):
    """Resolve an explicit selector even when another argument cannot parse.

    The full parser still validates every argument. Honor the option terminator
    and argparse's last-selector-wins behavior; an invalid final value leaves
    error reports on the default registry.
    """
    name = "default"
    for index, argument in enumerate(argv):
        if argument == "--":
            break
        if argument == "--registry":
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                continue
            value = argv[index + 1]
        elif argument.startswith("--registry="):
            value = argument.split("=", 1)[1]
        else:
            continue
        name = value if value in _REGISTRY_ATTRIBUTES else "default"
    return name


def _named_registry(name: str, api: ModuleType):
    return getattr(api, _REGISTRY_ATTRIBUTES.get(name, "DEFAULT_REGISTRY"))


def main(argv: list[str] | None = None, *, api: ModuleType) -> int:
    """Run one file using the API module supplied by the verifier entry point.

    Passing the active module preserves its registries for both imports and
    ``python -m verifier`` without importing a second copy of the entry point.
    """
    parser = _Parser(
        prog="python -m verifier",
        allow_abbrev=False,
        description="Verify one site JSON and report documented rule coverage and gaps.",
    )
    parser.add_argument("site", metavar="SITE.json")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument(
        "--registry",
        choices=tuple(_REGISTRY_ATTRIBUTES),
        default="default",
        help="Full documented catalog (default/all), initial five rules (legacy), or W1.",
    )
    arguments = list(sys.argv[1:] if argv is None else argv)
    requested = _requested_registry_name(arguments)
    registry = _named_registry(requested, api)
    args = argparse.Namespace(registry=requested)
    results = []
    report = None
    input_valid = False
    try:
        parser.parse_args(arguments, namespace=args)
    except _ArgumentError as exc:
        report = build_report(registry, input_errors=(Diagnostic("cli_arguments", "", str(exc)),))
        return _emit_report(report, "json")
    except Exception as exc:
        return _emit_report(
            operational_report(exc, build_report(registry), input_valid=False), "json"
        )
    registry = _named_registry(args.registry, api)
    # Trusted evaluator prints and incidental logs must not corrupt JSON stdout.
    with redirect_stdout(sys.stderr):
        try:
            document = api.load_document(args.site)
            input_valid = True
            report = api._execute(document, registry, results=results)
        except InputValidationError as exc:
            report = api._invalid_report(registry, exc)
        except Exception as exc:
            report = operational_report(
                exc, build_report(registry, results=results), input_valid=input_valid
            )
    return _emit_report(report, args.format)
