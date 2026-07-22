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

JARED = "jtramontano@acorninv.com"
AVA = "acohen@acorninv.com"


# --- seeding ---

def test_load_alerts_seeds_defaults_when_missing():
    assert not ac.ALERTS_FILE.exists()
    alerts = ac.load_alerts(today=TODAY)
    assert ac.ALERTS_FILE.exists()
    # Part II: seeds ship pre-migrated — 7 alerts x 2 legacy owners
    assert len(alerts) == 14
    assert [a["name"] for a in alerts] == [a["name"] for a in ac.DEFAULT_ALERTS]
    assert {a["owner"] for a in alerts} == {JARED, AVA}
    # per-owner view: each owner sees exactly their 7
    assert len(ac.load_alerts(today=TODAY, owner=JARED)) == 7
    assert len(ac.load_alerts(today=TODAY, owner=AVA.upper())) == 7  # case-blind
    assert ac.load_alerts(today=TODAY, owner="apain@acorninv.com") == []


def test_legacy_ownerless_file_migrates_once():
    ac.ALERTS_FILE.write_text(json.dumps({"alerts": [
        {"name": "Timed", "trigger": "t", "priority": "low", "expires": None},
    ]}), encoding="utf-8")
    alerts = ac.load_alerts(today=TODAY)
    # duplicated per legacy owner, persisted
    assert [(a["name"], a["owner"]) for a in alerts] == [
        ("Timed", JARED), ("Timed", AVA)]
    on_disk = json.loads(ac.ALERTS_FILE.read_text(encoding="utf-8"))["alerts"]
    assert all("owner" in a for a in on_disk) and len(on_disk) == 2
    # idempotent: a second load doesn't duplicate again
    assert len(ac.load_alerts(today=TODAY)) == 2


def test_load_watchlist_seeds_defaults_when_missing():
    assert not ac.WATCHLIST_FILE.exists()
    tickers = ac.load_watchlist(today=TODAY)
    assert ac.WATCHLIST_FILE.exists()
    assert tickers == [e["ticker"] for e in ac.DEFAULT_WATCHLIST]
    assert "MSTR" in tickers and len(tickers) == 16


def test_corrupt_file_left_untouched_and_defaults_used():
    ac.ALERTS_FILE.write_text("{not json", encoding="utf-8")
    alerts = ac.load_alerts(today=TODAY)
    assert len(alerts) == 14  # in-memory defaults (pre-migrated)
    assert ac.ALERTS_FILE.read_text(encoding="utf-8") == "{not json"  # never overwritten


def test_corrupt_file_blocks_writes():
    ac.ALERTS_FILE.write_text("{not json", encoding="utf-8")
    results, changed = ac.apply_actions(
        [{"action": "add_alert", "name": "X", "trigger": "Y"}], "a@b.com", today=TODAY)
    assert not changed
    assert "unreadable" in results[0]
    assert ac.ALERTS_FILE.read_text(encoding="utf-8") == "{not json"


# --- expiry filtering ---

def _seed_alert(expires, owner=JARED):
    ac.ALERTS_FILE.write_text(json.dumps({"alerts": [
        {"name": "Timed", "trigger": "t", "priority": "low", "expires": expires,
         "owner": owner},
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
    # Part II shape: alert notices carry their owner; watchlist ones are shared
    alert_n = next(n for n in notices if '"Timed"' in n["notice"])
    assert alert_n["owner"] == JARED and YESTERDAY in alert_n["notice"]
    wl_n = next(n for n in notices if "BBB (Bravo Corp)" in n["notice"])
    assert wl_n["owner"] is None

    # pruned from the files; second call is silent
    assert json.loads(ac.ALERTS_FILE.read_text(encoding="utf-8"))["alerts"] == []
    remaining = json.loads(ac.WATCHLIST_FILE.read_text(encoding="utf-8"))["tickers"]
    assert [t["ticker"] for t in remaining] == ["CCC"]
    assert ac.consume_expired(today=TODAY) == []


def test_expiring_today_warns_without_removing():
    _seed_alert(TODAY)
    ac.WATCHLIST_FILE.write_text(json.dumps({"tickers": [
        {"ticker": "WOLF", "name": "Wolfspeed", "expires": TODAY},
        {"ticker": "CCC", "expires": FUTURE},
        {"ticker": "DDD", "expires": None},
    ]}), encoding="utf-8")

    warnings = ac.expiring_today(today=TODAY)
    assert len(warnings) == 2
    alert_w = next(w for w in warnings if '"Timed"' in w["notice"])
    assert alert_w["owner"] == JARED
    assert "ends after today's run" in alert_w["notice"]
    wl_w = next(w for w in warnings if "WOLF (Wolfspeed)" in w["notice"])
    assert wl_w["owner"] is None

    # read-only: nothing removed, item still active, consume finds nothing yet
    assert [a["name"] for a in ac.load_alerts(today=TODAY)] == ["Timed"]
    assert ac.consume_expired(today=TODAY) == []
    # and future/permanent entries never warn
    assert ac.expiring_today(today=YESTERDAY) == []


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
    ], AVA, today=TODAY)
    assert changed
    assert "Added alert" in results[0] and FUTURE in results[0]

    # owner-stamped and visible only in the asker's view
    assert "Argentina watch" in [a["name"] for a in ac.load_alerts(today=TODAY, owner=AVA)]
    assert "Argentina watch" not in [a["name"]
                                     for a in ac.load_alerts(today=TODAY, owner=JARED)]
    stored = [a for a in json.loads(ac.ALERTS_FILE.read_text(encoding="utf-8"))["alerts"]
              if a["name"] == "Argentina watch"][0]
    assert stored["added_by"] == AVA
    assert stored["owner"] == AVA
    assert stored["added_on"] == TODAY

    results, changed = ac.apply_actions(
        [{"action": "remove_alert", "name": "argentina watch"}],  # case-insensitive
        AVA, today=TODAY)
    assert changed and "Removed alert" in results[0]
    assert "Argentina watch" not in [a["name"] for a in ac.load_alerts(today=TODAY)]


def test_cannot_touch_another_owners_alert():
    ac.apply_actions([{"action": "add_alert", "name": "Ava only", "trigger": "x"}],
                     AVA, today=TODAY)
    # jared can't remove or re-expire ava's alert — and isn't told her names
    results, changed = ac.apply_actions(
        [{"action": "remove_alert", "name": "Ava only"},
         {"action": "update_expiry", "kind": "alert", "target": "Ava only",
          "expires": FUTURE}],
        JARED, today=TODAY)
    assert not changed
    assert all("No alert of yours" in r for r in results)
    assert all("Ava only" not in r.split("your active alerts:")[1] for r in results)
    assert "Ava only" in [a["name"] for a in ac.load_alerts(today=TODAY, owner=AVA)]


def test_add_alert_name_collision_gets_suffix_per_owner():
    add = {"action": "add_alert", "name": "Bank failure", "trigger": "x"}
    # jared already owns "Bank failure" -> suffix
    results, _ = ac.apply_actions([add], JARED, today=TODAY)
    assert '"Bank failure (2)"' in results[0]
    # a brand-new user owns nothing -> no collision, plain name
    results, _ = ac.apply_actions([dict(add)], "apain@acorninv.com", today=TODAY)
    assert '"Bank failure"' in results[0] and "(2)" not in results[0]


def test_add_alert_without_trigger_is_polite_noop():
    results, changed = ac.apply_actions(
        [{"action": "add_alert", "name": "X"}], "a@b.com", today=TODAY)
    assert not changed and "no trigger" in results[0]


def test_remove_alert_unknown_lists_own_active_names():
    results, changed = ac.apply_actions(
        [{"action": "remove_alert", "name": "Nonexistent"}], JARED, today=TODAY)
    assert not changed
    assert '"Nonexistent"' in results[0] and '"Large Chapter 11"' in results[0]
    # a user with no alerts sees "(none)", not someone else's names
    results, _ = ac.apply_actions(
        [{"action": "remove_alert", "name": "Nonexistent"}],
        "apain@acorninv.com", today=TODAY)
    assert "(none)" in results[0] and "Large Chapter 11" not in results[0]


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
    ], JARED, today=TODAY)
    assert changed
    assert f"expires {FUTURE}" in results[0] and f"expires {FUTURE}" in results[1]
    stored = json.loads(ac.ALERTS_FILE.read_text(encoding="utf-8"))["alerts"]
    jared_bf = [a for a in stored
                if a["name"] == "Bank failure" and a["owner"] == JARED][0]
    ava_bf = [a for a in stored
              if a["name"] == "Bank failure" and a["owner"] == AVA][0]
    assert jared_bf["expires"] == FUTURE      # jared's copy updated…
    assert ava_bf["expires"] is None          # …ava's untouched


def test_list_config_renders_own_alerts_and_shared_watchlist():
    results, changed = ac.apply_actions(
        [{"action": "list_config"}], JARED, today=TODAY)
    assert not changed
    joined = "\n".join(results)
    assert "Your alerts (7):" in joined
    assert '"Large Chapter 11"' in joined
    assert "Shared SEC watchlist (16):" in joined
    assert "PGY (Pagaya Technologies)" in joined
    # a user with no alerts still sees the shared watchlist
    results, _ = ac.apply_actions(
        [{"action": "list_config"}], "apain@acorninv.com", today=TODAY)
    joined = "\n".join(results)
    assert "Your alerts (0):" in joined
    assert "Shared SEC watchlist (16):" in joined


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


def test_parse_prompt_owner_grounding_excludes_other_owners():
    ac.apply_actions([{"action": "add_alert", "name": "Ava thing", "trigger": "x"}],
                     AVA, today=TODAY)
    prompt = ac._build_parse_prompt(
        "remove my chapter 11 alert",
        ac.load_alerts(today=TODAY, owner=JARED),
        ac.load_watchlist(today=TODAY), TODAY)
    assert '"Large Chapter 11"' in prompt   # jared's own alerts ground the parse
    assert "Ava thing" not in prompt        # ava's never leak into his prompt


def test_parse_prompt_empty_state():
    prompt = ac._build_parse_prompt("hello", [], [], TODAY)
    assert "- (none)" in prompt and "(none)" in prompt


# --- orphaned alerts (Part II) ---

def test_orphan_notices_fire_once_and_reset():
    ac.load_alerts(today=TODAY)  # seed (owners: jared + ava)
    everyone = [JARED, AVA]

    # both owners are recipients -> no orphans
    assert ac.orphan_notices(everyone, today=TODAY) == []

    # ava dropped -> ONE notice naming her, counting her alerts
    notices = ac.orphan_notices([JARED], today=TODAY)
    assert len(notices) == 1
    assert AVA in notices[0] and "7 alert(s)" in notices[0]
    # second run with the same recipients -> silent
    assert ac.orphan_notices([JARED], today=TODAY) == []

    # ava re-added -> meta clears; a later re-orphaning notices again
    assert ac.orphan_notices(everyone, today=TODAY) == []
    assert len(ac.orphan_notices([JARED], today=TODAY)) == 1


def test_orphan_check_ignores_expired_alerts():
    _seed_alert(YESTERDAY, owner=AVA)  # ava's only alert is already expired
    assert ac.orphan_notices([JARED], today=TODAY) == []


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
    expiry = [
        {"name": "Watch item expired",
         "detail": f"{item['notice']} Reply to this digest to renew.",
         "source": ""}
        for item in ac.consume_expired(today=TODAY)
    ]
    # expiry-only box: renders, no source tag, no separator (nothing above it)
    html = build_alerts_html([], expiry)
    assert "Watch item expired" in html
    assert "Reply to this digest to renew." in html
    assert "ALERTS" in html
    assert "alert commands" not in html
    assert "<hr" not in html


def test_alert_box_teaches_reply_commands():
    # the box footer advertises the reply channel…
    html = build_alerts_html([{"name": "X", "detail": "d", "source": "s"}])
    assert "manage your alerts" in html
    assert "what alerts are set up?" in html
    # …and with nothing to report, the hint renders STANDALONE (no red box)
    empty = build_alerts_html([], [])
    assert "manage your alerts" in empty
    assert "ALERTS" not in empty and "<div" not in empty


def test_expiry_notices_render_below_separator():
    content = [{"name": "HY spread blowout", "detail": "widened 31bps", "source": "FRED"}]
    expiry = [{"name": "Watch item expiring", "detail": "ends after today's run",
               "source": ""}]
    html = build_alerts_html(content, expiry)
    # one separator, content above it, expiry below it
    assert html.count("<hr") == 1
    assert html.index("HY spread blowout") < html.index("<hr") < html.index("Watch item expiring")
    # content alerts alone -> no separator; nothing at all -> no box (hint only)
    assert "<hr" not in build_alerts_html(content)
    assert "<div" not in build_alerts_html([], [])
