from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import socket
import sys

import pytest
from jsonschema.exceptions import SchemaError
from referencing.exceptions import Unresolvable

import ingestion
from ingestion import InputValidationError, load_document, validate_document


def failures(document):
    with pytest.raises(InputValidationError) as caught:
        validate_document(document)
    return caught.value.diagnostics


def test_field_reference_example_and_unchanged_input(example, tmp_path):
    original = deepcopy(example)
    serialized = json.dumps(example, ensure_ascii=False)
    path = tmp_path / "site.json"
    path.write_text(serialized, encoding="utf-8")
    assert validate_document(example) is example
    assert load_document(path) == original
    assert example == original
    assert path.read_text(encoding="utf-8") == serialized
    # The example intentionally places an arrow board outside its named zone
    # and a device line across zone boundaries.
    assert example["elements"][3]["position"]["station"] == 480


def test_bom_and_unicode(example, tmp_path):
    example["site"]["name"] = "Café 道路"
    path = tmp_path / "bom.json"
    path.write_text(json.dumps(example, ensure_ascii=False), encoding="utf-8-sig")
    assert load_document(path) == example


def test_optional_data_and_no_defaults(minimal):
    minimal["elements"] = []
    minimal["typical_application"].pop("lanes_closed")
    before = deepcopy(minimal)
    assert validate_document(minimal) == before
    assert "observations" not in minimal
    assert "predictions" not in minimal
    minimal.update(observations=[], temporal_context={}, predictions={})
    validate_document(minimal)
    minimal["predictions"] = {"by_zone": [{}], "recommendations": [{"action": "", "priority": "info"}]}
    validate_document(minimal)


@pytest.mark.parametrize("content", ["", " \n\t", "{", '{"a":}', '{} {}', '{} trailing', '\ufeff{}'])
def test_invalid_json(content, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    # A single initial BOM is valid encoding; this case lacks required fields.
    with pytest.raises(InputValidationError) as caught:
        load_document(path)
    diagnostic = caught.value.diagnostics[0]
    if content.startswith("\ufeff"):
        assert diagnostic.code == "schema.required"
    else:
        assert diagnostic.code == "invalid_json"
        assert diagnostic.path == ""
        assert diagnostic.line >= 1 and diagnostic.column >= 1


def test_invalid_encoding(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b'\xff\xfe{}')
    with pytest.raises(InputValidationError) as caught:
        load_document(path)
    assert caught.value.diagnostics[0].code == "invalid_encoding"


def test_missing_and_directory(tmp_path):
    for path in (tmp_path / "absent.json", tmp_path):
        with pytest.raises(InputValidationError) as caught:
            load_document(path)
        assert caught.value.diagnostics[0].code == "input_read"


def test_unreadable_file(monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("Access denied")
    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(InputValidationError) as caught:
        load_document("site.json")
    assert caught.value.diagnostics[0].code == "input_read"


def test_unexpected_io_propagates(monkeypatch):
    def failed(*args, **kwargs):
        raise OSError("Device unavailable")
    monkeypatch.setattr(Path, "read_text", failed)
    with pytest.raises(OSError, match="Device unavailable"):
        load_document("site.json")


@pytest.mark.parametrize("content,path", [
    ('{"site": {}, "site": {}}', "/site"),
    ('{"x":[{"a/b~c":1,"a/b~c":2}]}', "/x/0/a~1b~0c"),
    ('{"site":{"name":"a","na\\u006de":"b"}}', "/site/name"),
])
def test_duplicate_keys(content, path, tmp_path):
    source = tmp_path / "duplicate.json"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(InputValidationError) as caught:
        load_document(source)
    assert [(d.code, d.path) for d in caught.value.diagnostics] == [("duplicate_key", path)]


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e9999", "-1e9999"])
def test_nonfinite_json(number, example, tmp_path):
    text = json.dumps(example).replace('"posted_speed_mph": 45', f'"posted_speed_mph": {number}')
    source = tmp_path / "number.json"
    source.write_text(text, encoding="utf-8")
    with pytest.raises(InputValidationError) as caught:
        load_document(source)
    assert [(d.code, d.path) for d in caught.value.diagnostics] == [
        ("non_finite_number", "/typical_application/posted_speed_mph")
    ]


@pytest.mark.parametrize("sign", ["", "-"])
def test_integer_parsing_limit_has_structured_failure(sign, tmp_path):
    limit = sys.get_int_max_str_digits()
    if not limit:
        pytest.skip("Interpreter integer conversion limit is disabled")
    source = tmp_path / "large-integer.json"
    source.write_text(sign + "1" * (limit + 1), encoding="utf-8")
    with pytest.raises(InputValidationError) as caught:
        load_document(source)
    assert [(d.code, d.path) for d in caught.value.diagnostics] == [("invalid_json", "")]


@pytest.mark.parametrize("field", ["direction", "posted_speed_mph"])
def test_integer_conversion_limit_in_parsed_values(field, example):
    limit = sys.get_int_max_str_digits()
    if not limit:
        pytest.skip("Interpreter integer conversion limit is disabled")
    value = 10 ** limit
    with pytest.raises(ValueError):
        json.dumps(value)
    example["typical_application"][field] = value
    assert [(d.code, d.path) for d in failures(example)] == [
        ("non_json_value", f"/typical_application/{field}")
    ]
    assert example["typical_application"][field] is value


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), (1, 2), {1}, Decimal("1"), b"abc", object()])
def test_non_json_values(value, example):
    example["site"]["name"] = value
    diagnostics = failures(example)
    assert diagnostics[0].path == "/site/name"
    assert diagnostics[0].code in ("non_json_value", "non_finite_number")


def test_non_string_keys_cycles_and_pointer_escaping(example):
    example["site"][3] = "bad"
    example["site"]["x/~"] = (1,)
    example["site"]["cycle"] = example
    diagnostics = failures(example)
    assert {(d.path, d.code) for d in diagnostics} == {
        ("/site", "non_json_key"), ("/site/x~1~0", "non_json_value"),
        ("/site/cycle", "non_json_value"),
    }


@pytest.mark.parametrize("value", [None, [], "site", 42, True])
def test_non_object_root(value):
    assert failures(value)[0].code == "schema.type"


@pytest.mark.parametrize("field,value,code", [
    ("format_version", "2.0.0", "schema.const"),
    ("extra", 1, "schema.additionalProperties"),
    ("zones", [], "schema.minItems"),
    ("elements", {}, "schema.type"),
])
def test_schema_failures(field, value, code, example):
    example[field] = value
    assert code in {d.code for d in failures(example)}


@pytest.mark.parametrize("section,field,value", [
    ("site", "created_date", "2026-02-30"),
    ("site", "created_date", "2026-10-21T00:00:00Z"),
    ("temporal_context", "timestamp", "2026-10-21T25:00:00Z"),
    ("temporal_context", "timestamp", "2026-10-21T00:00:00"),
    ("predictions", "predicted_at", "yesterday"),
])
def test_formats(section, field, value, example):
    example[section][field] = value
    assert [(d.path, d.code) for d in failures(example)] == [(f"/{section}/{field}", "schema.format")]


@pytest.mark.parametrize("index,field", [(0, "mutcd_code"), (1, "taper_type"), (2, "device"), (3, "mode"), (4, "position")])
def test_known_variant_diagnostics(index, field, example):
    del example["elements"][index][field]
    diagnostics = failures(example)
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.code == "schema.required"
    assert diagnostic.path == f"/elements/{index}"
    assert field in diagnostic.message
    assert diagnostic.schema_path == f"/properties/elements/items/oneOf/{index}/required"


def test_wrong_variant_and_nested_paths(example):
    example["elements"][0]["position"]["side"] = "north"
    example["elements"][1]["type"] = "unknown"
    diagnostics = failures(example)
    assert {(d.path, d.code) for d in diagnostics} == {
        ("/elements/0/position/side", "schema.enum"), ("/elements/1", "schema.oneOf")
    }
    assert all(d.schema_path for d in diagnostics)


def test_aggregated_schema_failures_and_unchanged_input(example):
    example["site"]["units"] = "yards"
    example["elements"][0]["position"]["offset"] = "ten"
    del example["elements"][0]["mutcd_code"]
    example["predictions"]["by_zone"][0]["confidence"] = 2
    # Structural failure prevents integrity checks on otherwise invalid refs.
    example["observations"][0]["zone_id"] = "missing"
    before = deepcopy(example)
    diagnostics = failures(example)
    assert len(diagnostics) == 4
    assert {d.path for d in diagnostics} == {
        "/site/units", "/elements/0", "/elements/0/position/offset", "/predictions/by_zone/0/confidence"
    }
    assert list(diagnostics) == sorted(diagnostics, key=lambda d: (d.path, d.code, d.message))
    assert example == before
    assert diagnostics == failures(example)


@pytest.mark.parametrize("collection,id_key", [("zones", "zone_id"), ("elements", "element_id"), ("observations", "obs_id")])
def test_duplicate_ids(collection, id_key, example):
    example[collection][1][id_key] = example[collection][0][id_key]
    # Avoid introducing dangling refs while isolating duplicate checks.
    example.pop("predictions")
    example.pop("observations") if collection != "observations" else None
    for item in example["elements"]:
        item.pop("zone_id", None)
    diagnostics = failures(example)
    duplicates = [d for d in diagnostics if d.code == "duplicate_id"]
    assert len(duplicates) == 1
    assert duplicates[0].path == f"/{collection}/1/{id_key}"
    assert f"/{collection}/0/{id_key}" in duplicates[0].message


REFERENCE_LOCATIONS = [
    *(("elements", index, "zone_id") for index in range(5)),
    ("observations", 0, "zone_id"),
    ("predictions", "by_zone", 0, "zone_id"),
    ("predictions", "recommendations", 0, "zone_id"),
    ("predictions", "recommendations", 1, "element_id"),
]


@pytest.mark.parametrize("location", REFERENCE_LOCATIONS)
@pytest.mark.parametrize("value", ["missing", ""])
def test_all_reference_locations(location, value, example):
    target = example
    for part in location[:-1]:
        target = target[part]
    target[location[-1]] = value
    assert [(d.path, d.code) for d in failures(example)] == [
        ("/" + "/".join(map(str, location)), "unresolved_reference")
    ]


def test_integrity_aggregation_and_unchanged_input(example):
    example["elements"][1]["element_id"] = "E1"
    example["elements"][0]["zone_id"] = "missing"
    example["observations"][0]["zone_id"] = ""
    example["predictions"]["by_zone"][0]["zone_id"] = "missing"
    example["predictions"]["recommendations"][0].update(zone_id="", element_id="")
    example["typical_application"]["lanes_closed"] = 3
    before = deepcopy(example)
    diagnostics = failures(example)
    assert len(diagnostics) == 7
    assert {d.code for d in diagnostics} == {"duplicate_id", "unresolved_reference", "lanes_closed_exceeds_total"}
    assert example == before


def test_empty_ids_resolve_and_namespaces_are_independent(example):
    example["zones"][0]["zone_id"] = ""
    example["elements"][0]["element_id"] = ""
    example["observations"][0]["obs_id"] = ""
    for item in example["elements"] + example["observations"] + example["predictions"]["by_zone"] + example["predictions"]["recommendations"]:
        if item.get("zone_id") == "Z1":
            item["zone_id"] = ""
    example["predictions"]["recommendations"][0]["element_id"] = ""
    validate_document(example)


def test_no_geometry_constraints_coercion_or_sorting(example):
    example["zones"].reverse()
    example["zones"][0].update(start_station=999, end_station=-999)
    example["zones"][1].update(start_station=0, end_station=0)
    example["elements"].reverse()
    example["elements"][0]["position"].update(station=-123, offset=-4)
    example["typical_application"].update(lanes_total=2.0, lanes_closed=2.0)
    before = deepcopy(example)
    assert validate_document(example) is example
    assert example == before
    assert type(example["typical_application"]["lanes_total"]) is float


def test_schema_resolution_independent_of_cwd_and_network(example, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def blocked(*args, **kwargs):
        pytest.fail("Network access attempted")
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    assert validate_document(example) is example
    path = tmp_path / "site.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    assert load_document(path) == example


def test_missing_and_invalid_schema_propagate(example, tmp_path, monkeypatch):
    path = tmp_path / "schema.json"
    monkeypatch.setattr(ingestion, "_SCHEMA_PATH", path)
    with pytest.raises(FileNotFoundError):
        validate_document(example)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        validate_document(example)
    path.write_text('{"type": "bad-type"}', encoding="utf-8")
    with pytest.raises(SchemaError):
        validate_document(example)


def test_external_schema_reference_disabled(example, tmp_path, monkeypatch):
    path = tmp_path / "schema.json"
    path.write_text('{"$ref": "https://example.invalid/never-fetch.json"}', encoding="utf-8")
    monkeypatch.setattr(ingestion, "_SCHEMA_PATH", path)
    def blocked(*args, **kwargs):
        pytest.fail("Network access attempted")
    monkeypatch.setattr(socket, "socket", blocked)
    with pytest.raises(Unresolvable):
        validate_document(example)
