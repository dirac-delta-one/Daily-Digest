#!/usr/bin/env python3
"""
Shared Claude helpers:
- `parse_json_response` — strip an optional ```json fence and json.loads() (Phase 2.2).
- `json_schema_output` / `wrapped_array_schema` — structured-output (`output_config.format`)
  helpers so the model returns guaranteed-valid JSON matching a schema, no fence-stripping
  and no silent parse failures (A2). Confirmed supported on Opus 4.8 / Sonnet 4.6 / Haiku 4.5.
"""

import json


def json_schema_output(schema):
    """Build the `output_config` for a structured-output response.

    Usage: client.messages.create(..., output_config=json_schema_output(SCHEMA)).
    The response's first text block is then guaranteed valid JSON matching `schema`
    (parse with parse_json_response / json.loads — the fence branch never fires).
    """
    return {"format": {"type": "json_schema", "schema": schema}}


def wrapped_array_schema(key, item_type):
    """Schema for a top-level object with a single required array field.

    Structured outputs want a top-level object, so array-returning calls wrap their
    list under one `key` (e.g. "indices"/"queries") of `item_type` ("integer"/"string")
    and unwrap it after parsing: `parse_json_response(text)[key]`.
    """
    return {
        "type": "object",
        "properties": {key: {"type": "array", "items": {"type": item_type}}},
        "required": [key],
        "additionalProperties": False,
    }


def parse_json_response(text):
    """Strip an optional ``` / ```json code fence from a Claude response and
    json.loads() the body.

    Mirrors the per-module logic that was duplicated across digest.py,
    alerts.py, memory.py, pacer.py, and reply_monitor.py. Raises
    json.JSONDecodeError on unparseable content, so existing try/except blocks
    keep working unchanged.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        # Drop the opening fence line (``` or ```json), then a trailing fence.
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)
