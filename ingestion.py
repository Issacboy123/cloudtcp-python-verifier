"""Strict site JSON ingestion for Python 3.11+; no rules or geometry inference.

Both entry points return the validated dictionary. ``validate_document`` returns
the original object and never edits it. Expected input failures carry diagnostics;
schema/configuration failures deliberately propagate to the caller.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterable

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry


@dataclass(frozen=True)
class Diagnostic:
    """A validation failure; paths are RFC 6901 JSON Pointers (root is "")."""

    code: str
    path: str
    message: str
    schema_path: str | None = None
    line: int | None = None
    column: int | None = None


class InputValidationError(ValueError):
    """Expected input failures, ordered by input pointer, code, and message."""

    def __init__(self, diagnostics: Iterable[Diagnostic]):
        self.diagnostics = tuple(sorted(
            diagnostics, key=lambda d: (d.path, d.code, d.message)
        ))
        super().__init__("; ".join(
            f"{d.path or '<root>'}: [{d.code}] {d.message}"
            for d in self.diagnostics
        ))


_SCHEMA_PATH = Path(__file__).resolve().with_name("tcp-intermediate-format.schema.json")


def _pointer(parts):
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _deny_retrieval(uri):
    raise RuntimeError(f"External schema retrieval is disabled: {uri}")


def _validator():
    # Read only this local schema. A missing/invalid schema is an operational
    # fault, not a defect in the caller's document. Do not catch those failures.
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(
        schema, format_checker=FormatChecker(),
        registry=Registry(retrieve=_deny_retrieval),
    )


class _ObjectPairs(list):
    """Preserve JSON object pairs until duplicate keys can be given paths."""


def _unpack(value, path, diagnostics):
    if isinstance(value, _ObjectPairs):
        result = {}
        for key, child in value:
            child_path = path + (key,)
            if key in result:
                diagnostics.append(Diagnostic(
                    "duplicate_key", _pointer(child_path), f"Duplicate object key {key!r}."
                ))
            result[key] = _unpack(child, child_path, diagnostics)
        return result
    if isinstance(value, list):
        return [_unpack(child, path + (i,), diagnostics) for i, child in enumerate(value)]
    return value


def load_document(path: str | Path) -> dict:
    """Read UTF-8 (optional BOM), parse strict JSON, then validate the site."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputValidationError([Diagnostic(
            "invalid_encoding", "", "Input must be UTF-8 (an initial BOM is allowed)."
        )]) from exc
    except (FileNotFoundError, PermissionError, IsADirectoryError, NotADirectoryError) as exc:
        raise InputValidationError([Diagnostic("input_read", "", str(exc))]) from exc
    try:
        parsed = json.loads(text, object_pairs_hook=_ObjectPairs)
    except json.JSONDecodeError as exc:
        raise InputValidationError([Diagnostic(
            "invalid_json", "", exc.msg, line=exc.lineno, column=exc.colno
        )]) from exc
    except ValueError as exc:
        # CPython's configured integer conversion limit raises ValueError rather
        # than JSONDecodeError. Keep it inside the parsing failure boundary.
        raise InputValidationError([Diagnostic("invalid_json", "", str(exc))]) from exc
    diagnostics = []
    document = _unpack(parsed, (), diagnostics)
    # Includes NaN/Infinity accepted by Python's decoder and exponent overflow.
    _check_json_values(document, (), set(), diagnostics)
    if diagnostics:
        raise InputValidationError(diagnostics)
    return validate_document(document)


def _check_json_values(value, path, ancestors, diagnostics):
    kind = type(value)
    if kind is int:
        try:
            # The same conversion is needed by json.dumps and schema diagnostic
            # formatting. Honor the interpreter's JSON conversion limit without
            # changing global settings or adding a schema numeric bound.
            str(value)
        except ValueError:
            diagnostics.append(Diagnostic(
                "non_json_value", _pointer(path),
                "Integer exceeds the interpreter's JSON conversion limit."
            ))
    elif kind is float and not math.isfinite(value):
        diagnostics.append(Diagnostic("non_finite_number", _pointer(path), "Number must be finite."))
    elif kind in (dict, list):
        identity = id(value)
        if identity in ancestors:
            diagnostics.append(Diagnostic("non_json_value", _pointer(path), "Cyclic containers are not JSON values."))
            return
        ancestors.add(identity)
        children = value.items() if kind is dict else enumerate(value)
        for key, child in children:
            if kind is dict and type(key) is not str:
                diagnostics.append(Diagnostic(
                    "non_json_key", _pointer(path), "Object keys must be strings."
                ))
            else:
                _check_json_values(child, path + (key,), ancestors, diagnostics)
        ancestors.remove(identity)
    elif kind not in (str, int, float, bool, type(None)):
        diagnostics.append(Diagnostic(
            "non_json_value", _pointer(path), f"Unsupported JSON value type: {kind.__name__}."
        ))


def _schema_diagnostics(error):
    # oneOf is still evaluated in full by jsonschema. Only presentation is
    # narrowed, using the actual schema discriminator rather than a second model.
    if (error.validator == "oneOf" and isinstance(error.instance, dict)
            and tuple(error.absolute_path)[:1] == ("elements",)):
        for index, variant in enumerate(error.validator_value):
            tag = variant.get("properties", {}).get("type", {}).get("const")
            if tag is not None and error.instance.get("type") == tag:
                matching = [child for child in error.context if child.schema_path[0] == index]
                if matching:
                    for child in matching:
                        yield from _schema_diagnostics(child)
                    return
    yield Diagnostic(
        f"schema.{error.validator}", _pointer(error.absolute_path), error.message,
        schema_path=_pointer(error.absolute_schema_path),
    )


def _integrity_diagnostics(document):
    diagnostics = []
    ids = {}
    for collection, id_key in (("zones", "zone_id"), ("elements", "element_id"), ("observations", "obs_id")):
        seen = {}
        ids[collection] = seen
        for i, item in enumerate(document.get(collection, [])):
            value = item[id_key]
            path = _pointer((collection, i, id_key))
            if value in seen:
                diagnostics.append(Diagnostic(
                    "duplicate_id", path, f"Duplicate {id_key} {value!r}; first defined at {seen[value]}."
                ))
            else:
                seen[value] = path

    def check_references(items, prefix, key, targets):
        for i, item in enumerate(items):
            if key in item and item[key] not in targets:
                diagnostics.append(Diagnostic(
                    "unresolved_reference", _pointer((*prefix, i, key)),
                    f"Unknown {key} {item[key]!r}."
                ))

    for collection in ("elements", "observations"):
        check_references(document.get(collection, []), (collection,), "zone_id", ids["zones"])
    predictions = document.get("predictions", {})
    for collection in ("by_zone", "recommendations"):
        check_references(predictions.get(collection, []), ("predictions", collection), "zone_id", ids["zones"])
    check_references(predictions.get("recommendations", []), ("predictions", "recommendations"), "element_id", ids["elements"])
    application = document["typical_application"]
    if "lanes_closed" in application and application["lanes_closed"] > application["lanes_total"]:
        diagnostics.append(Diagnostic(
            "lanes_closed_exceeds_total", "/typical_application/lanes_closed",
            "lanes_closed must not exceed lanes_total."
        ))
    return diagnostics


def validate_document(document: object) -> dict:
    """Validate parsed JSON values, structure, then references; return unchanged."""
    diagnostics = []
    _check_json_values(document, (), set(), diagnostics)
    if diagnostics:
        raise InputValidationError(diagnostics)
    diagnostics = [
        diagnostic for error in _validator().iter_errors(document)
        for diagnostic in _schema_diagnostics(error)
    ]
    if diagnostics:
        raise InputValidationError(diagnostics)
    diagnostics = _integrity_diagnostics(document)
    if diagnostics:
        raise InputValidationError(diagnostics)
    return document
