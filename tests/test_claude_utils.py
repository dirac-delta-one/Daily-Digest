"""claude_utils — JSON parsing + structured-output schema helpers (A2)."""

import json

import pytest

import claude_utils as cu


# --- parse_json_response ---

def test_parse_json_plain():
    assert cu.parse_json_response('{"a": 1}') == {"a": 1}


def test_parse_json_fenced():
    assert cu.parse_json_response('```json\n{"results": []}\n```') == {"results": []}


def test_parse_json_array():
    assert cu.parse_json_response("[1, 2, 3]") == [1, 2, 3]


def test_parse_json_garbage_raises():
    with pytest.raises(json.JSONDecodeError):
        cu.parse_json_response("not json at all")


# --- json_schema_output ---

def test_json_schema_output_shape():
    schema = {"type": "object", "additionalProperties": False}
    assert cu.json_schema_output(schema) == {
        "format": {"type": "json_schema", "schema": schema}
    }


# --- wrapped_array_schema ---

def test_wrapped_array_schema_indices():
    s = cu.wrapped_array_schema("indices", "integer")
    assert s["type"] == "object"
    assert s["properties"]["indices"]["type"] == "array"
    assert s["properties"]["indices"]["items"] == {"type": "integer"}
    assert s["required"] == ["indices"]
    assert s["additionalProperties"] is False


def test_wrapped_array_schema_queries():
    s = cu.wrapped_array_schema("queries", "string")
    assert s["properties"]["queries"]["items"] == {"type": "string"}
    assert s["required"] == ["queries"]
