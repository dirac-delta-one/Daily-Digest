#!/usr/bin/env python3
"""
Shared Claude helpers. Currently just the JSON-response parser used by every
module that asks Claude for a JSON array/object and has to strip a ```json
code fence before json.loads() (Phase 2.2).
"""

import json


def parse_json_response(text):
    """Strip an optional ``` / ```json code fence from a Claude response and
    json.loads() the body.

    Mirrors the per-module logic that was duplicated across digest.py, octus.py,
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
