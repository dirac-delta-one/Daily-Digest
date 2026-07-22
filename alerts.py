#!/usr/bin/env python3
"""
Custom Plain-English Alerts
Evaluates user-defined triggers against each day's source content using Opus.
"""

import json

import anthropic

import alert_commands
from config import OPUS_MODEL, esc
from claude_utils import parse_json_response, json_schema_output
import cost

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
    """Active alert definitions — delegated to alert_commands, which owns
    alerts_config.json (email-managed state since ALERT_COMMANDS_SPEC:
    seeding, expiry filtering, and all writes live there)."""
    try:
        return alert_commands.load_alerts()
    except Exception as e:
        print(f"  Error loading alerts config: {e}")
        return []


def _build_alert_prompt(alerts, source_text, watchlist=None):
    """Assemble the alert-evaluation prompt. Extracted from evaluate_alerts so the
    watchlist binding below is unit-testable without a Claude call."""
    # Alert definitions — name and trigger clearly separated
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

    # Bind the fuzzy word "watchlist" in a trigger to the REAL ticker universe
    # (sec_filings.WATCHLIST, passed in by the caller). Without this the model
    # inferred "watchlist names" on its own; with it, the alerts and the
    # SEC/earnings fetchers key off the same single list. Triggers that never
    # say "watchlist" (Large Chapter 11, HY spread blowout, …) are unaffected.
    watchlist_clause = ""
    if watchlist:
        watchlist_clause = (
            "WATCHLIST DEFINITION — wherever a trigger says \"watchlist\" (e.g. "
            "\"watchlist names\", \"a watchlist company\"), it means ONLY these tickers "
            "and their issuers:\n"
            f"{', '.join(watchlist)}\n"
            "Do NOT treat any other company as on the watchlist.\n\n"
        )

    return (
        "Evaluate each alert trigger below against today's source material.\n\n"
        "ALERTS TO EVALUATE:\n"
        f"{alert_defs}"
        f"{watchlist_clause}"
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


def evaluate_alerts(source_text, watchlist=None, alerts=None):
    """
    Evaluate alert definitions against today's source material.

    Args:
        source_text: The full source material text sent to Opus for the digest.
        watchlist: optional list of tickers the word "watchlist" in a trigger
            resolves to (digest.py passes `sec_filings.WATCHLIST`). None leaves
            "watchlist" to the model's own interpretation (legacy behavior).
        alerts: optional explicit alert-dict list (evaluate_owner_alerts passes
            its deduped eval units). None loads every active alert (standalone
            __main__ / legacy behavior).

    Returns:
        List of triggered alerts with details.
    """
    if alerts is None:
        alerts = _load_alerts_config()
    if not alerts:
        print("  No alerts configured — skipping.")
        return []

    print(f"  Evaluating {len(alerts)} custom alerts...")

    client = anthropic.Anthropic()
    prompt = _build_alert_prompt(alerts, source_text, watchlist)

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


def evaluate_owner_alerts(source_text, owner_alerts, watchlist=None):
    """Per-user thematic alerts (ALERT_COMMANDS_SPEC Part II): evaluate every
    owner's alerts in ONE Claude call and fan results back out per owner —
    cost stays flat as users onboard.

    Args:
        owner_alerts: {owner_email: [alert dicts]} — typically
            {r: alert_commands.load_alerts(owner=r) for r in recipients}.
    Returns:
        {owner: [triggered results]} with each result carrying the owner's own
        alert name. Owners with no alerts get an empty list; an empty union
        makes NO Claude call.

    Mechanics: identical (name, trigger) pairs across owners collapse into one
    eval unit (the migrated 7×2 defaults collapse back to 7); same-name units
    with DIFFERENT triggers get a disambiguated eval name ("Bank failure ~2")
    so the model's name-keyed results can't merge them — the fan-out restores
    each owner's real name.
    """
    units = []          # deduped alert dicts handed to evaluate_alerts
    unit_members = []   # parallel: [(owner, real_name), ...] per unit
    by_key = {}         # (name_lower, trigger) -> unit index
    name_counts = {}    # name_lower -> units so far with this name

    for owner, alerts in owner_alerts.items():
        for a in alerts or []:
            name = a.get("name") or ""
            key = (name.lower(), a.get("trigger") or "")
            if key in by_key:
                unit_members[by_key[key]].append((owner, name))
                continue
            n = name_counts.get(key[0], 0) + 1
            name_counts[key[0]] = n
            eval_name = name if n == 1 else f"{name} ~{n}"
            by_key[key] = len(units)
            units.append({"name": eval_name, "trigger": a.get("trigger", ""),
                          "priority": a.get("priority", "medium")})
            unit_members.append([(owner, name)])

    if not units:
        return {owner: [] for owner in owner_alerts}

    print(f"  {sum(len(v or []) for v in owner_alerts.values())} owned alert(s) "
          f"across {len(owner_alerts)} recipient(s) -> {len(units)} eval unit(s).")
    triggered = evaluate_alerts(source_text, watchlist=watchlist, alerts=units)

    unit_index = {u["name"]: i for i, u in enumerate(units)}
    out = {owner: [] for owner in owner_alerts}
    for t in triggered:
        idx = unit_index.get(t.get("name"))
        if idx is None:
            continue
        for owner, real_name in unit_members[idx]:
            out[owner].append({**t, "name": real_name})
    return out


def _alert_items_html(alerts):
    """The <li> rows for one group of alert dicts (shared by both box sections)."""
    items = ""
    for alert in alerts:
        name = alert.get("name", "Alert")
        detail = alert.get("detail", "")
        source = alert.get("source", "")

        source_tag = f' <span style="color: #888;">({esc(source)})</span>' if source else ""

        items += (
            f'<li style="margin-bottom: 8px; font-size: 14px;">'
            f'<strong>{esc(name)}:</strong> {esc(detail)}{source_tag}'
            f'</li>\n'
        )
    return items


# The reply-channel teaching line (ALERT_COMMANDS_SPEC discoverability,
# 2026-07-22): closes every rendered alert box, and stands alone at the top of
# the digest when there is no box that day \u2014 every recipient gets the hint
# daily either way.
_REPLY_FOOTER_TEXT = (
    'Reply to this digest to ask questions or manage your alerts &amp; the shared '
    'SEC watchlist \u2014 e.g. &quot;watch for X until Aug 15&quot;, &quot;add CRWV to '
    'the watchlist&quot;, &quot;what alerts are set up?&quot;.'
)


def build_alerts_html(triggered_alerts, expiry_alerts=None):
    """Render triggered alerts as a prominent HTML box.

    expiry_alerts \u2014 the watch-item expiring/expired lifecycle notices
    (ALERT_COMMANDS_SPEC) \u2014 render inside the same box but BELOW a thin
    separator, so renewal housekeeping reads apart from the actual
    market/content alerts (operator formatting request 2026-07-22).

    With nothing to report there is NO red box \u2014 just the standalone
    reply-channel hint line where the box would sit."""
    expiry_alerts = expiry_alerts or []
    if not triggered_alerts and not expiry_alerts:
        return (f'<p style="font-size: 11px; color: #888; margin: 0 0 24px;">'
                f'{_REPLY_FOOTER_TEXT}</p>\n')

    body = ""
    if triggered_alerts:
        body += (f'<ul style="padding-left: 20px; margin: 0;">\n'
                 f'{_alert_items_html(triggered_alerts)}</ul>\n')
    if expiry_alerts:
        if triggered_alerts:
            body += ('<hr style="margin: 12px 0; border: none; '
                     'border-top: 1px solid #e0b9b3;">\n')
        body += (f'<ul style="padding-left: 20px; margin: 0;">\n'
                 f'{_alert_items_html(expiry_alerts)}</ul>\n')

    html = (
        '<div style="background: #fdf2f2; border: 2px solid #c0392b; border-radius: 6px; '
        'padding: 16px 20px; margin-bottom: 24px;">\n'
        '<h2 style="font-size: 18px; color: #c0392b; margin: 0 0 10px;">'
        '\u26a0\ufe0f ALERTS</h2>\n'
        f'{body}'
        f'<p style="font-size: 11px; color: #888; margin: 10px 0 0;">'
        f'{_REPLY_FOOTER_TEXT}</p>\n'
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
        print("No alerts configured. Add one by replying to a digest "
              "(or create alerts_config.json).")
