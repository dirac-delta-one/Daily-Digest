#!/usr/bin/env python3
"""
Email-managed alerts & watchlist (ALERT_COMMANDS_SPEC, 2026-07-22).

Users (any digest recipient) manage the thematic alerts and the SEC watchlist
by REPLYING to a digest email in plain English ("for the next two weeks watch
for X", "add CRWV to the watchlist", "what alerts are set up?"). The reply
monitor routes such replies here; the digest run reads the resulting state.

This module owns:
- the two state files (alerts_config.json, watchlist.json) — gitignored,
  seeded from the in-code defaults when missing, written atomically;
- the Sonnet classify/parse call that turns a reply email into structured
  actions (relative timelines resolved to absolute ISO dates at parse time);
- the deterministic apply + confirmation-rendering logic;
- expiry: entries stay active through their `expires` date inclusive; the
  first digest run after that gets a one-line notice (consume_expired) and
  the entry is gone.

Sits below alerts.py / sec_filings.py / reply_monitor.py / digest.py in the
import graph — imports nothing from them, so every consumer is cycle-free.
"""

import copy
import datetime
import json
import os
from pathlib import Path

import anthropic

from config import SONNET_MODEL, esc
from claude_utils import parse_json_response, json_schema_output
import cost

SCRIPT_DIR = Path(__file__).parent
ALERTS_FILE = SCRIPT_DIR / "alerts_config.json"
WATCHLIST_FILE = SCRIPT_DIR / "watchlist.json"

_SEED = {"added_by": "seed", "added_on": "2026-07-22", "expires": None}

# Part II (per-user alerts): every thematic alert has exactly ONE owner.
# The pre-Part-II alerts (ownerless) belong to these two — legacy entries
# found on disk are duplicated per owner by the §9 migration in
# _load_alerts_payload, and the seeds below ship already-migrated.
LEGACY_ALERT_OWNERS = ["jtramontano@acorninv.com", "acohen@acorninv.com"]

# The pre-spec alerts_config.json contents (git history: tracked until
# 2026-07-22). Seeded to disk when the file is missing — which includes the
# server's first pull after the file left git tracking (git deletes the
# working-tree copy on that pull; the seed makes the deletion lossless).
_BASE_ALERTS = [
    {"name": "Large Chapter 11",
     "trigger": "Any new Chapter 11 bankruptcy filing with over $500M in liabilities",
     "priority": "high"},
    {"name": "Insider selling",
     "trigger": "Any Form 4 showing insider selling over $1M in watchlist names",
     "priority": "high"},
    {"name": "HY spread blowout",
     "trigger": "HY OAS widens more than 25bps in a single day",
     "priority": "high"},
    {"name": "Fed surprise",
     "trigger": "Any unexpected Fed action or emergency meeting",
     "priority": "high"},
    {"name": "Distressed exchange",
     "trigger": "Any distressed exchange, liability management exercise, or "
                "cooperation agreement mentioned",
     "priority": "medium"},
    {"name": "Rating downgrade",
     "trigger": "Any downgrade of a watchlist company or any downgrade to "
                "junk/speculative grade (fallen angel)",
     "priority": "high"},
    {"name": "Bank failure",
     "trigger": "Any FDIC bank failure detected",
     "priority": "high"},
]

DEFAULT_ALERTS = [
    {**a, "owner": owner, **_SEED}
    for owner in LEGACY_ALERT_OWNERS
    for a in _BASE_ALERTS
]

# The pre-spec sec_filings.WATCHLIST (tickers + their comment names).
DEFAULT_WATCHLIST = [
    {"ticker": "PGY", "name": "Pagaya Technologies", **_SEED},
    {"ticker": "CRWV", "name": "CoreWeave", **_SEED},
    {"ticker": "WOLF", "name": "Wolfspeed", **_SEED},
    {"ticker": "MSTR", "name": "MicroStrategy", **_SEED},
    {"ticker": "TRTX", "name": "TPG RE Finance Trust", **_SEED},
    {"ticker": "LADR", "name": "Ladder Capital", **_SEED},
    {"ticker": "OSG", "name": "Overseas Shipholding Group", **_SEED},
    {"ticker": "FSK", "name": "FS KKR Capital", **_SEED},
    {"ticker": "OBDC", "name": "Blue Owl Capital (Owl Rock)", **_SEED},
    {"ticker": "RWT", "name": "Redwood Trust", **_SEED},
    {"ticker": "ABR", "name": "Arbor Realty Trust", **_SEED},
    {"ticker": "GBDC", "name": "Golub Capital BDC", **_SEED},
    {"ticker": "MAIN", "name": "Main Street Capital", **_SEED},
    {"ticker": "TSLX", "name": "Sixth Street Specialty Lending", **_SEED},
    {"ticker": "ARCC", "name": "Ares Capital", **_SEED},
    {"ticker": "APLD", "name": "Applied Digital", **_SEED},
]


# ======================================================================
# STATE FILES
# ======================================================================

def _today(today=None):
    return today or datetime.date.today().isoformat()


def _atomic_write(path, payload):
    """Write-temp-then-replace so the digest process never reads a torn file."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _default_alerts_payload():
    return {"alerts": copy.deepcopy(DEFAULT_ALERTS)}


def _default_watchlist_payload():
    return {"tickers": copy.deepcopy(DEFAULT_WATCHLIST)}


def _read_state(path, default_payload):
    """(payload, writable). Missing file -> seed defaults to disk. Corrupt
    file -> defaults in-memory + writable=False: NEVER overwrite a corrupt
    file (the O4 backup holds the last good copy; a reseed would silently
    discard user edits)."""
    if not path.exists():
        _atomic_write(path, default_payload)
        return copy.deepcopy(default_payload), True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("top level is not an object")
        return payload, True
    except Exception as e:
        print(f"  {path.name} unreadable ({e}) — using built-in defaults; "
              "file left untouched (restore from the O4 backup).")
        return copy.deepcopy(default_payload), False


def _is_active(entry, today):
    """Active through the expires date inclusive; no expires = permanent.
    ISO strings compare correctly as strings."""
    expires = entry.get("expires")
    return not expires or today <= expires


def _load_alerts_payload():
    """(payload, writable) with the Part-II §9 owner migration applied: legacy
    (ownerless) alert entries are duplicated per LEGACY_ALERT_OWNERS and the
    migrated payload persisted once. Idempotent — a migrated file never
    matches again; corrupt files stay in-memory (writable=False) as usual."""
    payload, writable = _read_state(ALERTS_FILE, _default_alerts_payload())
    alerts = payload.get("alerts", [])
    if any(isinstance(a, dict) and "owner" not in a for a in alerts):
        migrated = []
        for a in alerts:
            if not isinstance(a, dict) or a.get("owner"):
                migrated.append(a)
            else:
                migrated.extend({**a, "owner": owner} for owner in LEGACY_ALERT_OWNERS)
        payload["alerts"] = migrated
        if writable:
            _atomic_write(ALERTS_FILE, payload)
        print(f"  alerts_config.json migrated to per-owner alerts "
              f"({len(alerts)} -> {len(migrated)} entries).")
    return payload, writable


def load_alerts(today=None, owner=None):
    """Active alert dicts (expired filtered out) — what alerts.py evaluates.

    owner=<email> filters to that owner's alerts (case-insensitive) — the
    per-user view (Part II: alerts are personal; owner-only visibility).
    owner=None returns all owners' active alerts (internal/legacy use)."""
    today = _today(today)
    payload, _ = _load_alerts_payload()
    alerts = [a for a in payload.get("alerts", [])
              if isinstance(a, dict) and a.get("name") and _is_active(a, today)]
    if owner is not None:
        o = owner.lower()
        alerts = [a for a in alerts if (a.get("owner") or "").lower() == o]
    return alerts


def owners_with_alerts(today=None):
    """Lowercased owner emails holding >=1 active alert (the orphan check)."""
    today = _today(today)
    payload, _ = _load_alerts_payload()
    return {(a.get("owner") or "").lower()
            for a in payload.get("alerts", [])
            if isinstance(a, dict) and a.get("owner") and _is_active(a, today)}


def orphan_notices(current_recipients, today=None):
    """One-time ops-email lines for owners whose alerts are paused because
    they no longer receive the digest (Part II: evaluation covers current
    recipients only, so a departed owner's alerts silently stop running).
    Known orphans are tracked in the payload's `_meta` so each orphaning is
    noticed exactly once; an owner who becomes a recipient again is dropped
    from the list (a later re-orphaning notices again)."""
    today = _today(today)
    payload, writable = _load_alerts_payload()
    recipients = {(r or "").lower() for r in (current_recipients or [])}
    owners = {(a.get("owner") or "").lower()
              for a in payload.get("alerts", [])
              if isinstance(a, dict) and a.get("owner") and _is_active(a, today)}
    orphans = sorted(owners - recipients)

    meta = payload.get("_meta") or {}
    known = sorted((k or "").lower() for k in (meta.get("known_orphans") or []))
    new = [o for o in orphans if o not in known]

    if known != orphans and writable:
        payload["_meta"] = {**meta, "known_orphans": orphans}
        _atomic_write(ALERTS_FILE, payload)

    notices = []
    for o in new:
        n = sum(1 for a in payload.get("alerts", [])
                if isinstance(a, dict) and (a.get("owner") or "").lower() == o
                and _is_active(a, today))
        notices.append(f"{n} alert(s) owned by {o} are paused — {o} no longer "
                       "receives the digest. They resume if the address is "
                       "re-added, or can be deleted from alerts_config.json.")
    return notices


def load_watchlist(today=None):
    """Active tickers, uppercased, deduped, insertion order preserved — the
    list behind sec_filings.WATCHLIST (and through it earnings, the alert
    watchlist binding, and the search entity lexicon)."""
    today = _today(today)
    payload, _ = _read_state(WATCHLIST_FILE, _default_watchlist_payload())
    out, seen = [], set()
    for entry in payload.get("tickers", []):
        if not isinstance(entry, dict):
            continue
        ticker = (entry.get("ticker") or "").upper()
        if ticker and ticker not in seen and _is_active(entry, today):
            seen.add(ticker)
            out.append(ticker)
    return out


def watchlist_names():
    """{ticker: company name} for entries that carry a name (confirmation
    rendering; deliberately NOT wired into the ticker-glossary prompt path)."""
    payload, _ = _read_state(WATCHLIST_FILE, _default_watchlist_payload())
    return {e["ticker"].upper(): e["name"] for e in payload.get("tickers", [])
            if isinstance(e, dict) and e.get("ticker") and e.get("name")}


def _owner_of(entry):
    """Lowercased owner of an alert entry, or None (watchlist/shared)."""
    owner = (entry.get("owner") or "").lower()
    return owner or None


def expiring_today(today=None):
    """Advance warnings for entries whose LAST active day is today
    (today == expires) — read-only, nothing is removed: tomorrow's run drops
    the entry via consume_expired. Returns [{"owner": email|None, "notice":
    str}] (Part II): alert warnings carry their owner so the digest can route
    them to that recipient's box only; watchlist warnings are shared (None).
    The digest runs once a day, so each warning renders exactly once."""
    today = _today(today)
    warnings = []

    payload, _ = _load_alerts_payload()
    for a in payload.get("alerts", []):
        if a.get("expires") == today:
            warnings.append({
                "owner": _owner_of(a),
                "notice": f'Alert "{a.get("name", "?")}" ends after today\'s run '
                          f'(expires {today}).',
            })

    payload, _ = _read_state(WATCHLIST_FILE, _default_watchlist_payload())
    for t in payload.get("tickers", []):
        if t.get("expires") == today:
            name = f" ({t['name']})" if t.get("name") else ""
            warnings.append({
                "owner": None,
                "notice": f'Watchlist ticker {t.get("ticker", "?")}{name} ends after '
                          f'today\'s run (expires {today}).',
            })

    return warnings


def consume_expired(today=None):
    """Expiry notices for entries past their expiry, REMOVING them from the
    files — remove-on-read gives exactly-one-notice semantics with no
    'notified' flag. Same [{"owner": …, "notice": …}] shape as
    expiring_today. Called once per digest run; [] when nothing expired."""
    today = _today(today)
    notices = []

    payload, writable = _load_alerts_payload()
    if writable:
        keep = [a for a in payload.get("alerts", []) if _is_active(a, today)]
        dropped = [a for a in payload.get("alerts", []) if not _is_active(a, today)]
        if dropped:
            payload["alerts"] = keep
            _atomic_write(ALERTS_FILE, payload)
            for a in dropped:
                notices.append({
                    "owner": _owner_of(a),
                    "notice": f'Alert "{a.get("name", "?")}" expired '
                              f'{a.get("expires")} and was removed.',
                })

    payload, writable = _read_state(WATCHLIST_FILE, _default_watchlist_payload())
    if writable:
        keep = [t for t in payload.get("tickers", []) if _is_active(t, today)]
        dropped = [t for t in payload.get("tickers", []) if not _is_active(t, today)]
        if dropped:
            payload["tickers"] = keep
            _atomic_write(WATCHLIST_FILE, payload)
            for t in dropped:
                name = f" ({t['name']})" if t.get("name") else ""
                notices.append({
                    "owner": None,
                    "notice": f'Watchlist ticker {t.get("ticker", "?")}{name} expired '
                              f'{t.get("expires")} and was removed.',
                })

    return notices


# ======================================================================
# CLASSIFY / PARSE (the one Sonnet call per reply email)
# ======================================================================

_ACTION_NAMES = ["add_alert", "remove_alert", "update_expiry",
                 "add_ticker", "remove_ticker", "list_config"]

COMMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": _ACTION_NAMES},
                    "name": {"type": ["string", "null"]},
                    "trigger": {"type": ["string", "null"]},
                    "priority": {"type": ["string", "null"]},
                    "expires": {"type": ["string", "null"]},
                    "ticker": {"type": ["string", "null"]},
                    "kind": {"type": ["string", "null"]},
                    "target": {"type": ["string", "null"]},
                },
                "required": ["action", "name", "trigger", "priority",
                             "expires", "ticker", "kind", "target"],
                "additionalProperties": False,
            },
        },
        "question": {"type": ["string", "null"]},
        "clarification": {"type": ["string", "null"]},
    },
    "required": ["actions", "question", "clarification"],
    "additionalProperties": False,
}

PARSE_SYSTEM = (
    "You are the command interpreter for a research-digest email bot. Users reply "
    "to the daily digest either to ask questions about the research archive or to "
    "manage the bot's configuration: thematic ALERTS (plain-English triggers "
    "evaluated daily against research sources) and the SEC filing WATCHLIST "
    "(tickers whose filings and earnings are monitored).\n\n"
    "Classify the reply and extract any configuration commands.\n"
    "RULES:\n"
    "- Emit an action ONLY when the user clearly requests a configuration change, "
    "or asks to see the current configuration (-> list_config). Comments, thanks, "
    "opinions, and research questions are NOT commands.\n"
    "- A genuine research/archive question goes in \"question\" (null if none). A "
    "reply can contain both commands and a question.\n"
    "- Resolve every relative time expression (\"for the next two weeks\", \"until "
    "end of August\", \"through earnings on Aug 10\") to an absolute ISO date using "
    "TODAY's date. \"expires\" is the LAST day the item stays active. No time "
    "expression -> expires null (permanent).\n"
    "- add_alert: write \"trigger\" as a specific, self-contained condition "
    "suitable for daily evaluation against research sources; generate a short "
    "2-4 word \"name\" in the style of the existing alert names; \"priority\" is "
    "high/medium/low (null when unstated).\n"
    "- remove_alert (\"name\") / update_expiry (\"target\") / remove_ticker "
    "(\"ticker\"): the value MUST be copied EXACTLY from the current configuration "
    "below. If the request does not match exactly one existing entry, emit NO "
    "action for it and explain in \"clarification\", naming the candidates.\n"
    "- add_ticker: uppercase the ticker symbol; include the company name if the "
    "user gives one (else null).\n"
    "- update_expiry: \"kind\" is \"alert\" or \"ticker\"; expires null means make "
    "it permanent.\n"
    "- If the user clearly wanted a command but it cannot be parsed safely, emit "
    "no action and set \"clarification\".\n"
    "- Do NOT narrate outcomes or pre-judge redundancy — the apply step reports "
    "what actually happened. Emit the action even if it looks redundant (e.g. a "
    "ticker that is already on the watchlist); duplicates are handled downstream.\n"
    "Output only the JSON object."
)


def _build_parse_prompt(reply_text, alerts, tickers, today):
    """The user-turn content for classify_and_parse — extracted so grounding
    (today's date, exact alert names, tickers) is unit-testable for free."""
    alert_lines = "\n".join(
        f'- "{a["name"]}" (priority {a.get("priority", "medium")}, '
        f'{"expires " + a["expires"] if a.get("expires") else "permanent"})'
        for a in alerts
    ) or "- (none)"
    return (
        f"TODAY: {today}\n\n"
        f"THIS USER'S CURRENT ALERTS (exact names; alerts are personal — other users' "
        f"alerts are invisible here):\n{alert_lines}\n\n"
        f"CURRENT SHARED WATCHLIST TICKERS: {', '.join(tickers) or '(none)'}\n\n"
        f"REPLY EMAIL:\n{'=' * 40}\n{reply_text}\n{'=' * 40}\n"
    )


def classify_and_parse(reply_text, today=None, owner=None):
    """One Sonnet call: reply text -> {actions, question, clarification}.
    Raises on API failure — the reply monitor catches and falls through to
    the Q&A path, so a parse outage degrades to today's behavior.

    owner (Part II) = the asker's email: the CURRENT ALERTS grounding block
    lists only THEIR alerts (privacy + correct remove/extend grounding);
    None grounds on all alerts (internal/legacy use)."""
    today = _today(today)
    prompt = _build_parse_prompt(reply_text, load_alerts(today, owner=owner),
                                 load_watchlist(today), today)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=1500,
        system=PARSE_SYSTEM,
        output_config=json_schema_output(COMMAND_SCHEMA),
        messages=[{"role": "user", "content": prompt}],
    )
    cost.record("alert command-parse", SONNET_MODEL, response.usage)
    return parse_json_response(response.content[0].text)


# ======================================================================
# APPLY (deterministic — no Claude)
# ======================================================================

def _fmt_expiry(expires):
    return f"expires {expires}" if expires else "permanent"


def _unique_alert_name(name, existing_names):
    """Name collisions get a numbered suffix rather than overwriting."""
    if name.lower() not in existing_names:
        return name
    n = 2
    while f"{name} ({n})".lower() in existing_names:
        n += 1
    return f"{name} ({n})"


def apply_actions(actions, asker, today=None):
    """Apply parsed actions to the state files. Returns (results, changed):
    results = per-action outcome strings for the confirmation reply, changed =
    whether anything was written. Deterministic; every failure mode (unknown
    target, duplicate, unreadable file) becomes a polite outcome string.

    Part II owner scoping: thematic-alert actions see and touch ONLY the
    asker's alerts (add stamps owner=asker; remove/update/list match within
    the asker's set). Watchlist actions stay shared — anyone edits."""
    today = _today(today)
    asker_l = (asker or "").lower()
    results = []

    a_payload, a_writable = _load_alerts_payload()
    w_payload, w_writable = _read_state(WATCHLIST_FILE, _default_watchlist_payload())
    a_dirty = w_dirty = False

    def _own(entry):
        return (entry.get("owner") or "").lower() == asker_l

    def _own_alerts():
        return [a for a in a_payload.get("alerts", []) if _own(a)]

    def _active_own_alerts():
        return [a for a in _own_alerts() if _is_active(a, today)]

    def _active_tickers():
        return [t for t in w_payload.get("tickers", []) if _is_active(t, today)]

    def _alert_names():
        return ", ".join(f'"{a["name"]}"' for a in _active_own_alerts()) or "(none)"

    for act in actions or []:
        action = (act or {}).get("action")

        if action in ("add_alert", "remove_alert") and not a_writable:
            results.append("The alerts file is unreadable — no alert changes applied. "
                           "Restore alerts_config.json from the backup.")
            continue
        if action in ("add_ticker", "remove_ticker") and not w_writable:
            results.append("The watchlist file is unreadable — no watchlist changes "
                           "applied. Restore watchlist.json from the backup.")
            continue

        if action == "add_alert":
            trigger = (act.get("trigger") or "").strip()
            if not trigger:
                results.append("Couldn't add an alert — no trigger condition was given.")
                continue
            priority = (act.get("priority") or "medium").lower()
            if priority not in ("high", "medium", "low"):
                priority = "medium"
            existing = {a["name"].lower() for a in _own_alerts() if a.get("name")}
            name = _unique_alert_name((act.get("name") or "Custom alert").strip(), existing)
            a_payload.setdefault("alerts", []).append({
                "name": name, "trigger": trigger, "priority": priority,
                "expires": act.get("expires"), "owner": asker_l or "unknown",
                "added_by": asker or "unknown", "added_on": today,
            })
            a_dirty = True
            results.append(f'Added alert "{name}" — {trigger} '
                           f'(priority {priority}, {_fmt_expiry(act.get("expires"))}).')

        elif action == "remove_alert":
            name = (act.get("name") or "").strip().lower()
            match = [a for a in _own_alerts()
                     if (a.get("name") or "").lower() == name]
            if not match:
                results.append(f'No alert of yours named "{act.get("name")}" — your '
                               f'active alerts: {_alert_names()}.')
                continue
            a_payload["alerts"] = [a for a in a_payload["alerts"] if a not in match]
            a_dirty = True
            results.append(f'Removed alert "{match[0]["name"]}".')

        elif action == "update_expiry":
            target = (act.get("target") or "").strip()
            expires = act.get("expires")
            if act.get("kind") == "ticker":
                if not w_writable:
                    results.append("The watchlist file is unreadable — no changes applied.")
                    continue
                match = [t for t in w_payload.get("tickers", [])
                         if (t.get("ticker") or "").upper() == target.upper()]
                if not match:
                    results.append(f'No watchlist ticker "{target}" — current watchlist: '
                                   f'{", ".join(load_watchlist(today)) or "(empty)"}.')
                    continue
                match[0]["expires"] = expires
                w_dirty = True
                results.append(f'Updated {match[0]["ticker"]} on the watchlist — now '
                               f'{_fmt_expiry(expires)}.')
            else:
                if not a_writable:
                    results.append("The alerts file is unreadable — no changes applied.")
                    continue
                match = [a for a in _own_alerts()
                         if (a.get("name") or "").lower() == target.lower()]
                if not match:
                    results.append(f'No alert of yours named "{target}" — your '
                                   f'active alerts: {_alert_names()}.')
                    continue
                match[0]["expires"] = expires
                a_dirty = True
                results.append(f'Updated alert "{match[0]["name"]}" — now '
                               f'{_fmt_expiry(expires)}.')

        elif action == "add_ticker":
            ticker = (act.get("ticker") or "").strip().upper()
            if not ticker:
                results.append("Couldn't add a ticker — no symbol was given.")
                continue
            existing = [t for t in w_payload.get("tickers", [])
                        if (t.get("ticker") or "").upper() == ticker]
            if existing:
                if act.get("expires") != existing[0].get("expires"):
                    existing[0]["expires"] = act.get("expires")
                    w_dirty = True
                    results.append(f"{ticker} is already on the watchlist — updated to "
                                   f"{_fmt_expiry(act.get('expires'))}.")
                else:
                    results.append(f"{ticker} is already on the watchlist (no change).")
                continue
            w_payload.setdefault("tickers", []).append({
                "ticker": ticker, "name": act.get("name"),
                "expires": act.get("expires"), "added_by": asker or "unknown",
                "added_on": today,
            })
            w_dirty = True
            name_part = f' ({act["name"]})' if act.get("name") else ""
            results.append(f"Added {ticker}{name_part} to the SEC watchlist "
                           f"({_fmt_expiry(act.get('expires'))}). Takes effect on the "
                           "next digest run.")

        elif action == "remove_ticker":
            ticker = (act.get("ticker") or "").strip().upper()
            match = [t for t in w_payload.get("tickers", [])
                     if (t.get("ticker") or "").upper() == ticker]
            if not match:
                results.append(f'{ticker or "?"} is not on the watchlist — current '
                               f'watchlist: {", ".join(load_watchlist(today)) or "(empty)"}.')
                continue
            w_payload["tickers"] = [t for t in w_payload["tickers"] if t not in match]
            w_dirty = True
            results.append(f"Removed {ticker} from the SEC watchlist.")
            if not _active_tickers():
                results.append("Heads-up: the watchlist is now empty — SEC filings and "
                               "earnings coverage will be empty until a ticker is added.")

        elif action == "list_config":
            # Structured sections, not outcome strings (formatting, 2026-07-22):
            # each alert is just its trigger sentence — no count, no priority
            # tag (priority has no coded behavior; it's only an eval-prompt
            # hint), no name/dash prefix. Alerts group into expiry buckets
            # (expire tomorrow / expire later / permanent); empty buckets are
            # omitted. Watchlist renders as bullets.
            alerts = _active_own_alerts()
            if alerts:
                results.append({"header": "Your alerts"})
                tomorrow = (datetime.date.fromisoformat(today)
                            + datetime.timedelta(days=1)).isoformat()
                buckets = {"Expire tomorrow": [], "Expire later": [], "Permanent": []}
                for a in alerts:
                    line = a.get("trigger") or a.get("name", "?")
                    expires = a.get("expires")
                    if not expires:
                        buckets["Permanent"].append(line)
                    elif expires <= tomorrow:
                        buckets["Expire tomorrow"].append(f"{line} (until {expires})")
                    else:
                        buckets["Expire later"].append(f"{line} (until {expires})")
                for bucket, items in buckets.items():
                    if items:
                        results.append({"header": bucket, "sub": True, "items": items})
            else:
                results.append({"header": "Your alerts",
                                "text": 'None yet — reply e.g. "watch for X until '
                                        'Aug 15" to add one.'})
            ticker_bits = []
            for t in _active_tickers():
                bit = t.get("ticker", "?")
                if t.get("name"):
                    bit += f" ({t['name']})"
                if t.get("expires"):
                    bit += f" [until {t['expires']}]"
                ticker_bits.append(bit)
            if ticker_bits:
                results.append({"header": "Shared SEC watchlist", "items": ticker_bits})
            else:
                results.append({"header": "Shared SEC watchlist", "text": "(empty)"})

        else:
            results.append(f'Unrecognized command "{action}" — nothing applied.')

    changed = False
    if a_dirty:
        _atomic_write(ALERTS_FILE, a_payload)
        changed = True
    if w_dirty:
        _atomic_write(WATCHLIST_FILE, w_payload)
        changed = True
    return results, changed


# ======================================================================
# CONFIRMATION RENDERING
# ======================================================================

def build_confirmation_html(results):
    """Digest-styled confirmation reply body (same wrapper as answer_question),
    with a one-line footer teaching the feature.

    A result is either a plain string (one bullet — command outcomes) or a
    section dict from list_config: {"header": str} plus optional "items"
    (bulleted list), "text" (paragraph), and "sub": True (a smaller italic
    grouping label under the current section, e.g. the expiry buckets)."""
    blocks = []
    pending = []

    def _flush():
        if pending:
            lis = "".join(f'<li style="margin-bottom: 8px;">{esc(r)}</li>'
                          for r in pending)
            blocks.append(f'<ul style="padding-left: 20px; margin: 0 0 10px;">{lis}</ul>')
            pending.clear()

    for r in results or []:
        if isinstance(r, dict):
            _flush()
            if r.get("sub"):
                blocks.append(f'<p style="margin: 10px 0 4px; font-size: 13px; '
                              f'color: #555;"><em>{esc(r.get("header", ""))}</em></p>')
            else:
                # 18px top margin = the blank line separating a section from
                # the last bullet of the previous one (operator formatting)
                blocks.append(f'<p style="margin: 18px 0 6px;">'
                              f'<strong>{esc(r.get("header", ""))}</strong></p>')
            if r.get("items"):
                lis = "".join(f'<li style="margin-bottom: 6px;">{esc(i)}</li>'
                              for i in r["items"])
                blocks.append(f'<ul style="padding-left: 20px; margin: 0;">{lis}</ul>')
            if r.get("text"):
                blocks.append(f'<p style="margin: 0; color: #444;">{esc(r["text"])}</p>')
        else:
            pending.append(r)
    _flush()
    if not blocks:
        blocks.append('<ul style="padding-left: 20px; margin: 0;">'
                      '<li style="margin-bottom: 8px;">Nothing to do.</li></ul>')

    body = "\n".join(blocks)
    return (
        '<div style="font-family: Georgia, serif; max-width: 680px; margin: 0 auto; '
        'color: #1a1a1a; line-height: 1.6; font-size: 14px;">\n'
        '<p style="margin: 0 0 10px;"><strong>Alert &amp; watchlist settings</strong></p>\n'
        f'{body}\n'
        '<hr style="margin: 20px 0; border: none; border-top: 1px solid #ccc;">\n'
        '<p style="font-size: 11px; color: #888;">Manage alerts by replying to any digest — '
        'e.g. &quot;watch for X until Aug 15&quot;, &quot;add CRWV to the watchlist&quot;, '
        '&quot;stop watching MSTR&quot;, &quot;what alerts are set up?&quot;. '
        'Alerts are personal to you; the SEC watchlist is shared with the whole team.</p>\n'
        '</div>'
    )


if __name__ == "__main__":
    print(f"Active alerts ({ALERTS_FILE}):")
    for a in load_alerts():
        print(f'  [{a.get("owner", "?")}] [{a.get("priority", "?")}] {a["name"]}: '
              f'{a.get("trigger", "")} ({_fmt_expiry(a.get("expires"))})')
    print(f"\nActive watchlist ({WATCHLIST_FILE}):")
    print(f'  {", ".join(load_watchlist()) or "(empty)"}')
