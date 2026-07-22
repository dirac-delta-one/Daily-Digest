"""Email-managed alerts & watchlist (ALERT_COMMANDS_SPEC, 2026-07-22).

Everything here is deterministic and offline: state-file seeding/expiry,
apply_actions outcomes, the parse-prompt grounding, and the digest wiring
in miniature. The one Claude seam (classify_and_parse) is exercised only
via _build_parse_prompt. The conftest autouse fixture already points
alert_commands.ALERTS_FILE / WATCHLIST_FILE into a per-test tmp dir.
"""

import json

import alert_commands as ac
from alerts import build_alerts_html


TODAY = "2026-07-22"
YESTERDAY = "2026-07-21"
FUTURE = "2026-08-05"


# --- seeding ---

def test_load_alerts_seeds_defaults_when_missing():
    assert not ac.ALERTS_FILE.exists()
    alerts = ac.load_alerts(today=TODAY)
    assert ac.ALERTS_FILE.exists()
    assert [a["name"] for a in alerts] == [a["name"] for a in ac.DEFAULT_ALERTS]
    assert len(alerts) == 7


def test_load_watchlist_seeds_defaults_when_missing():
    assert not ac.WATCHLIST_FILE.exists()
    tickers = ac.load_watchlist(today=TODAY)
    assert ac.WATCHLIST_FILE.exists()
    assert tickers == [e["ticker"] for e in ac.DEFAULT_WATCHLIST]
    assert "MSTR" in tickers and len(tickers) == 16


def test_corrupt_file_left_untouched_and_defaults_used():
    ac.ALERTS_FILE.write_text("{not json", encoding="utf-8")
    alerts = ac.load_alerts(today=TODAY)
    assert len(alerts) == 7  # in-memory defaults
    assert ac.ALERTS_FILE.read_text(encoding="utf-8") == "{not json"  # never overwritten


def test_corrupt_file_blocks_writes():
    ac.ALERTS_FILE.write_text("{not json", encoding="utf-8")
    results, changed = ac.apply_actions(
        [{"action": "add_alert", "name": "X", "trigger": "Y"}], "a@b.com", today=TODAY)
    assert not changed
    assert "unreadable" in results[0]
    assert ac.ALERTS_FILE.read_text(encoding="utf-8") == "{not json"


# --- expiry filtering ---

def _seed_alert(expires):
    ac.ALERTS_FILE.write_text(json.dumps({"alerts": [
        {"name": "Timed", "trigger": "t", "priority": "low", "expires": expires},
    ]}), encoding="utf-8")


def test_expired_yesterday_is_inactive():
    _seed_alert(YESTERDAY)
    assert ac.load_alerts(today=TODAY) == []


def test_expiring_today_is_still_active():
    _seed_alert(TODAY)
    assert [a["name"] for a in ac.load_alerts(today=TODAY)] == ["Timed"]


def test_watchlist_expiry_and_dedupe():
    ac.WATCHLIST_FILE.write_text(json.dumps({"tickers": [
        {"ticker": "aaa", "expires": None},
        {"ticker": "AAA", "expires": None},          # dupe after uppercasing
        {"ticker": "BBB", "expires": YESTERDAY},     # expired
        {"ticker": "CCC", "expires": FUTURE},
    ]}), encoding="utf-8")
    assert ac.load_watchlist(today=TODAY) == ["AAA", "CCC"]


# --- consume_expired (notice-once semantics) ---

def test_consume_expired_notices_once_and_prunes():
    _seed_alert(YESTERDAY)
    ac.WATCHLIST_FILE.write_text(json.dumps({"tickers": [
        {"ticker": "BBB", "name": "Bravo Corp", "expires": YESTERDAY},
        {"ticker": "CCC", "expires": None},
    ]}), encoding="utf-8")

    notices = ac.consume_expired(today=TODAY)
    assert len(notices) == 2
    assert any('"Timed"' in n and YESTERDAY in n for n in notices)
    assert any("BBB (Bravo Corp)" in n for n in notices)

    # pruned from the files; second call is silent
    assert json.loads(ac.ALERTS_FILE.read_text(encoding="utf-8"))["alerts"] == []
    remaining = json.loads(ac.WATCHLIST_FILE.read_text(encoding="utf-8"))["tickers"]
    assert [t["ticker"] for t in remaining] == ["CCC"]
    assert ac.consume_expired(today=TODAY) == []


def test_consume_expired_nothing_expired_touches_nothing():
    _seed_alert(FUTURE)
    before = ac.ALERTS_FILE.read_text(encoding="utf-8")
    assert ac.consume_expired(today=TODAY) == []
    assert ac.ALERTS_FILE.read_text(encoding="utf-8") == before


# --- apply_actions ---

def test_add_and_remove_alert_roundtrip():
    results, changed = ac.apply_actions([
        {"action": "add_alert", "name": "Argentina watch",
         "trigger": "Any news on Argentina sovereign debt",
         "priority": "high", "expires": FUTURE},
    ], "acohen@acorninv.com", today=TODAY)
    assert changed
    assert "Added alert" in results[0] and FUTURE in results[0]

    names = [a["name"] for a in ac.load_alerts(today=TODAY)]
    assert "Argentina watch" in names
    stored = [a for a in json.loads(ac.ALERTS_FILE.read_text(encoding="utf-8"))["alerts"]
              if a["name"] == "Argentina watch"][0]
    assert stored["added_by"] == "acohen@acorninv.com"
    assert stored["added_on"] == TODAY

    results, changed = ac.apply_actions(
        [{"action": "remove_alert", "name": "argentina watch"}],  # case-insensitive
        "acohen@acorninv.com", today=TODAY)
    assert changed and "Removed alert" in results[0]
    assert "Argentina watch" not in [a["name"] for a in ac.load_alerts(today=TODAY)]


def test_add_alert_name_collision_gets_suffix():
    add = {"action": "add_alert", "name": "Bank failure", "trigger": "x"}
    results, _ = ac.apply_actions([add], "a@b.com", today=TODAY)
    assert '"Bank failure (2)"' in results[0]


def test_add_alert_without_trigger_is_polite_noop():
    results, changed = ac.apply_actions(
        [{"action": "add_alert", "name": "X"}], "a@b.com", today=TODAY)
    assert not changed and "no trigger" in results[0]


def test_remove_alert_unknown_lists_active_names():
    results, changed = ac.apply_actions(
        [{"action": "remove_alert", "name": "Nonexistent"}], "a@b.com", today=TODAY)
    assert not changed
    assert '"Nonexistent"' in results[0] and '"Large Chapter 11"' in results[0]


def test_add_ticker_and_duplicate():
    results, changed = ac.apply_actions(
        [{"action": "add_ticker", "ticker": "wynn", "name": "Wynn Resorts",
          "expires": FUTURE}], "a@b.com", today=TODAY)
    assert changed
    assert "Added WYNN (Wynn Resorts)" in results[0]
    assert "WYNN" in ac.load_watchlist(today=TODAY)

    # same expiry again -> no change; new expiry -> renewal
    results, changed = ac.apply_actions(
        [{"action": "add_ticker", "ticker": "WYNN", "expires": FUTURE}],
        "a@b.com", today=TODAY)
    assert not changed and "already on the watchlist" in results[0]
    results, changed = ac.apply_actions(
        [{"action": "add_ticker", "ticker": "WYNN", "expires": None}],
        "a@b.com", today=TODAY)
    assert changed and "updated to permanent" in results[0]


def test_remove_ticker_and_empty_watchlist_headsup():
    ac.WATCHLIST_FILE.write_text(json.dumps({"tickers": [
        {"ticker": "ONLY", "expires": None},
    ]}), encoding="utf-8")
    results, changed = ac.apply_actions(
        [{"action": "remove_ticker", "ticker": "ONLY"}], "a@b.com", today=TODAY)
    assert changed
    assert "Removed ONLY" in results[0]
    assert any("watchlist is now empty" in r for r in results)


def test_remove_ticker_unknown():
    results, changed = ac.apply_actions(
        [{"action": "remove_ticker", "ticker": "ZZZZ"}], "a@b.com", today=TODAY)
    assert not changed and "not on the watchlist" in results[0]


def test_update_expiry_alert_and_ticker():
    results, changed = ac.apply_actions([
        {"action": "update_expiry", "kind": "alert", "target": "Bank failure",
         "expires": FUTURE},
        {"action": "update_expiry", "kind": "ticker", "target": "MSTR",
         "expires": FUTURE},
    ], "a@b.com", today=TODAY)
    assert changed
    assert f"expires {FUTURE}" in results[0] and f"expires {FUTURE}" in results[1]
    stored = json.loads(ac.ALERTS_FILE.read_text(encoding="utf-8"))["alerts"]
    assert [a for a in stored if a["name"] == "Bank failure"][0]["expires"] == FUTURE


def test_list_config_renders_current_state():
    results, changed = ac.apply_actions(
        [{"action": "list_config"}], "a@b.com", today=TODAY)
    assert not changed
    joined = "\n".join(results)
    assert "Active alerts (7):" in joined
    assert '"Large Chapter 11"' in joined
    assert "SEC watchlist (16):" in joined
    assert "PGY (Pagaya Technologies)" in joined


def test_no_tmp_files_left_behind():
    ac.apply_actions([{"action": "add_ticker", "ticker": "NEW"}], "a@b.com", today=TODAY)
    leftovers = list(ac.WATCHLIST_FILE.parent.glob("*.tmp"))
    assert leftovers == []


# --- parse-prompt grounding (the Claude seam, tested without Claude) ---

def test_parse_prompt_grounds_on_state_and_date():
    ac.load_alerts(today=TODAY)  # seed
    prompt = ac._build_parse_prompt(
        "stop watching MSTR", ac.load_alerts(today=TODAY),
        ac.load_watchlist(today=TODAY), TODAY)
    assert f"TODAY: {TODAY}" in prompt
    assert '"Large Chapter 11"' in prompt          # exact alert names for grounding
    assert "MSTR" in prompt                        # current tickers
    assert "stop watching MSTR" in prompt          # the reply text itself


def test_parse_prompt_empty_state():
    prompt = ac._build_parse_prompt("hello", [], [], TODAY)
    assert "- (none)" in prompt and "(none)" in prompt


# --- confirmation HTML ---

def test_confirmation_html_escapes_and_teaches():
    html = ac.build_confirmation_html(['Added alert "<script>" — x (priority high, permanent).'])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Manage alerts by replying" in html


# --- digest wiring in miniature (mirrors test_fed_stress) ---

def test_expiry_notice_renders_in_alert_box():
    _seed_alert(YESTERDAY)
    ac.WATCHLIST_FILE.write_text(json.dumps({"tickers": []}), encoding="utf-8")
    deterministic = [
        {"name": "Watch item expired", "detail": f"{n} Reply to this digest to renew.",
         "source": "alert commands"}
        for n in ac.consume_expired(today=TODAY)
    ]
    html = build_alerts_html(deterministic)
    assert "Watch item expired" in html
    assert "Reply to this digest to renew." in html
    assert "ALERTS" in html
