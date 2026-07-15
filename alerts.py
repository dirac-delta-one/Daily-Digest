#!/usr/bin/env python3
"""
Custom Plain-English Alerts
Evaluates user-defined triggers against each day's source content using Opus.
"""

import json
from pathlib import Path

import anthropic

from config import OPUS_MODEL, esc
from claude_utils import parse_json_response, json_schema_output
import cost

SCRIPT_DIR = Path(__file__).parent
ALERTS_CONFIG_FILE = SCRIPT_DIR / "alerts_config.json"
CLAUDE_MODEL = OPUS_MODEL

# Structured-output schema (A2): a top-level object with a "results" array, so the
# model can't return malformed JSON that silently drops the whole alert pass.
ALERTS_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "triggered": {"type": "boolean"},
                    "detail": {"type": ["string", "null"]},
                    "source": {"type": ["string", "null"]},
                },
                "required": ["name", "triggered", "detail", "source"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def _load_alerts_config():
    """Load alert definitions from config file."""
    if not ALERTS_CONFIG_FILE.exists():
        return []
    try:
        data = json.loads(ALERTS_CONFIG_FILE.read_text(encoding="utf-8"))
        return data.get("alerts", [])
    except Exception as e:
        print(f"  Error loading alerts config: {e}")
        return []


def evaluate_alerts(source_text):
    """
    Evaluate all configured alerts against today's source material.

    Args:
        source_text: The full source material text sent to Opus for the digest.

    Returns:
        List of triggered alerts with details.
    """
    alerts = _load_alerts_config()
    if not alerts:
        print("  No alerts configured — skipping.")
        return []

    print(f"  Evaluating {len(alerts)} custom alerts...")

    # Build alert definitions for the prompt — keep name and trigger clearly separated
    alert_defs = ""
    name_list = []
    for i, a in enumerate(alerts, 1):
        name = a["name"]
        name_list.append(name)
        alert_defs += (
            f"{i}. NAME: \"{name}\"\n"
            f"   TRIGGER: {a['trigger']}\n"
            f"   PRIORITY: {a.get('priority', 'medium').upper()}\n\n"
        )

    client = anthropic.Anthropic()

    prompt = (
        "Evaluate each alert trigger below against today's source material.\n\n"
        "ALERTS TO EVALUATE:\n"
        f"{alert_defs}"
        "For each alert, add one entry to a \"results\" array. Each entry:\n"
        '{"name": "<exact NAME string from above>", "triggered": true/false, '
        '"detail": "1-2 sentence description of what triggered it (or null)", '
        '"source": "the real source name, e.g. Grant\'s, FT, Bloomberg (or null)"}\n\n'
        "IMPORTANT:\n"
        "- The \"name\" field must be the EXACT short name from above (e.g. \"Large Chapter 11\"), "
        "NOT the trigger description.\n"
        f"- Valid names are: {name_list}\n"
        "- The \"source\" must be a real publication/agency name, never \"Cross-Digest Memory\" "
        "or any internal system component.\n\n"
        "Return a JSON object with a \"results\" array. No markdown, no explanation.\n\n"
        f"SOURCE MATERIAL:\n{'='*40}\n{source_text[:50000]}\n{'='*40}\n"
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            system=(
                "You are an alert evaluation engine. Check each trigger against "
                "the source material. Be conservative — only mark TRIGGERED if there "
                "is clear, specific evidence in the source material. Output only JSON."
            ),
            output_config=json_schema_output(ALERTS_SCHEMA),
            messages=[{"role": "user", "content": prompt}],
        )

        results = parse_json_response(response.content[0].text)["results"]

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        print(f"  Alerts pass tokens: {tokens_in:,} in + {tokens_out:,} out")
        cost.record("alert eval", CLAUDE_MODEL, response.usage)

        triggered = [r for r in results if r.get("triggered")]
        print(f"  {len(triggered)} alert(s) triggered out of {len(alerts)}.")
        return triggered

    except json.JSONDecodeError as e:
        print(f"  Alert evaluation failed (invalid JSON): {e}")
        return []
    except Exception as e:
        print(f"  Alert evaluation failed: {e}")
        return []


def build_alerts_html(triggered_alerts):
    """Render triggered alerts as a prominent HTML box."""
    if not triggered_alerts:
        return ""

    items = ""
    for alert in triggered_alerts:
        name = alert.get("name", "Alert")
        detail = alert.get("detail", "")
        source = alert.get("source", "")

        source_tag = f' <span style="color: #888;">({esc(source)})</span>' if source else ""

        items += (
            f'<li style="margin-bottom: 8px; font-size: 14px;">'
            f'<strong>{esc(name)}:</strong> {esc(detail)}{source_tag}'
            f'</li>\n'
        )

    html = (
        '<div style="background: #fdf2f2; border: 2px solid #c0392b; border-radius: 6px; '
        'padding: 16px 20px; margin-bottom: 24px;">\n'
        '<h2 style="font-size: 18px; color: #c0392b; margin: 0 0 10px;">'
        '\u26a0\ufe0f ALERTS</h2>\n'
        f'<ul style="padding-left: 20px; margin: 0;">\n{items}</ul>\n'
        '</div>\n'
    )

    return html


if __name__ == "__main__":
    alerts = _load_alerts_config()
    if alerts:
        print(f"Loaded {len(alerts)} alert definitions:")
        for a in alerts:
            print(f"  [{a.get('priority', '?')}] {a['name']}: {a['trigger']}")
    else:
        print("No alerts configured. Create alerts_config.json.")
