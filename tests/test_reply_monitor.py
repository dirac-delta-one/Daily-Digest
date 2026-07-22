"""Phase 3.4 — pin behavior of reply_monitor's pure extractors."""

import datetime

import reply_monitor


# --- _extract_question ---

def test_extract_question_strips_quote():
    body = "What is the HY OAS today?\n\nOn Mon, Jun 9, 2026 someone wrote:\n> old digest text"
    assert reply_monitor._extract_question(body) == "What is the HY OAS today?"


def test_extract_question_stops_at_signature():
    body = "Thanks for this.\n--\nSent from my iPhone"
    assert reply_monitor._extract_question(body) == "Thanks for this."


def test_extract_question_multiline():
    body = "First question?\nSecond question?\n\n> quoted"
    assert reply_monitor._extract_question(body) == "First question?\nSecond question?"


def test_extract_question_skips_leading_blanks():
    body = "\n\nActual question\n> quote"
    assert reply_monitor._extract_question(body) == "Actual question"


# --- _extract_digest_date (subject-parse path; no Gmail service needed) ---

def _expected_for_month_day(month, day):
    """Mirror the function's year-boundary logic so the test is year-robust."""
    today = datetime.date.today()
    cand = datetime.date(today.year, month, day)
    if cand > today:
        cand = datetime.date(today.year - 1, month, day)
    return cand.isoformat()


def test_extract_digest_date_from_subject():
    subject = "Re: Daily Inbox Digest — Friday, April 4"
    assert reply_monitor._extract_digest_date(subject, None, None) == _expected_for_month_day(4, 4)


def test_extract_digest_date_no_match_returns_none():
    # No trailing "Month DD" and service is None, so the thread fallback can't run.
    assert reply_monitor._extract_digest_date("Re: random subject", None, None) is None


# --- _extract_query_filters (Stage 4: regex query understanding) ---

def test_query_filters_iso_date_range():
    _, df, dt = reply_monitor._extract_query_filters(
        "What happened between 2026-07-06 and 2026-07-08?")
    assert (df, dt) == ("2026-07-06", "2026-07-08")


def test_query_filters_single_iso_date():
    _, df, dt = reply_monitor._extract_query_filters("What did the 2026-06-30 digest cover?")
    assert (df, dt) == ("2026-06-30", "2026-06-30")


def test_query_filters_entity_dollar_tick():
    ents, df, dt = reply_monitor._extract_query_filters("What is the latest on $ABR?")
    assert "ABR" in ents
    assert (df, dt) == (None, None)


def test_query_filters_watchlist_and_fund():
    ents, _, _ = reply_monitor._extract_query_filters(
        "What did FSK file about a purchase agreement with Oaktree?")
    assert "FSK" in ents
    assert "Oaktree Capital Management" in ents


def test_query_filters_month_day():
    _, df, dt = reply_monitor._extract_query_filters("What was in the July 7 digest?")
    assert df == dt == _expected_for_month_day(7, 7)


def test_query_filters_this_week_anchored_to_digest():
    # 2026-07-09 is a Thursday (weekday 3) -> Monday 2026-07-06 .. anchor
    ents, df, dt = reply_monitor._extract_query_filters(
        "How did the MSTR story evolve this week?", digest_date="2026-07-09")
    assert "MSTR" in ents
    assert (df, dt) == ("2026-07-06", "2026-07-09")


def test_query_filters_last_week_anchored_to_digest():
    _, df, dt = reply_monitor._extract_query_filters(
        "What happened last week?", digest_date="2026-07-09")
    assert (df, dt) == ("2026-06-29", "2026-07-05")


def test_query_filters_nothing_recognized():
    ents, df, dt = reply_monitor._extract_query_filters(
        "What is the state of private credit?")
    assert ents == []
    assert (df, dt) == (None, None)


def test_query_filters_bare_may_not_a_date():
    # "may" as a verb must not trigger the month regex (needs a trailing day number)
    _, df, dt = reply_monitor._extract_query_filters("How may spreads react to this?")
    assert (df, dt) == (None, None)


# --- Access tiers (TEAM_DIGEST_SPEC Stage 2) ---

def test_sender_email_parses_display_name():
    assert reply_monitor._sender_email("Jared T <JTramontano@acorninv.com>") == \
        "jtramontano@acorninv.com"
    assert reply_monitor._sender_email("plain@x.com") == "plain@x.com"
    assert reply_monitor._sender_email("") == ""
    assert reply_monitor._sender_email(None) == ""


def test_is_full_access_tiers():
    assert reply_monitor._is_full_access(None) is True          # internal/tool calls
    assert reply_monitor._is_full_access("jtramontano@acorninv.com") is True
    # 2026-07-14 directives (CLEANUP_SPEC 2.3): jared's personal gmail is
    # unanswerable by choice, and the bot's slot was a 2026-06-29 swap artifact
    # — both are team-tier now (and neither is in the answerable query).
    assert reply_monitor._is_full_access("JAREDTRAMONTANO@GMAIL.COM") is False
    assert reply_monitor._is_full_access("acorn.research.bot@gmail.com") is False
    assert reply_monitor._is_full_access("acohen@acorninv.com") is False
    assert reply_monitor._is_full_access("stranger@example.com") is False


# --- _reply_query (CLEANUP_SPEC 2.3: allow-list derived from config) ---

def test_reply_query_is_config_driven(monkeypatch):
    monkeypatch.setattr(reply_monitor, "DIGEST_RECIPIENTS", ["jtramontano@acorninv.com"])
    monkeypatch.setattr(reply_monitor, "TEAM_RECIPIENTS", ["newteam@acorninv.com"])
    q = reply_monitor._reply_query()
    # everyone who receives a digest is answerable — incl. a NEW team member
    assert "from:newteam@acorninv.com" in q
    assert "from:jtramontano@acorninv.com" in q
    # the structural terms survive: Re: + prefix (two separate subject terms)
    assert 'subject:"Re:"' in q
    assert reply_monitor.DIGEST_SUBJECT_PREFIX in q
    assert "is:unread" in q


def test_reply_query_excludes_removed_addresses(monkeypatch):
    monkeypatch.setattr(reply_monitor, "DIGEST_RECIPIENTS", ["jtramontano@acorninv.com"])
    monkeypatch.setattr(reply_monitor, "TEAM_RECIPIENTS", ["acohen@acorninv.com"])
    q = reply_monitor._reply_query()
    assert "jaredtramontano@gmail.com" not in q     # operator directive
    assert "acorn.research.bot@gmail.com" not in q  # slot-swap artifact
    assert "from:acohen@acorninv.com" in q          # via the team list


def test_team_exclusions_without_activation(monkeypatch):
    monkeypatch.setattr(reply_monitor, "TEAM_ACTIVATION_DATE", None)
    excl = reply_monitor._team_search_exclusions()
    assert excl["exclude_source_types"] == ("substack",)
    assert excl["exclude_digest_before"] == "9999-12-31"   # every digest is a full one


def test_team_exclusions_with_activation(monkeypatch):
    monkeypatch.setattr(reply_monitor, "TEAM_ACTIVATION_DATE", "2026-08-01")
    excl = reply_monitor._team_search_exclusions()
    assert excl["exclude_digest_before"] == "2026-08-01"


def test_story_mentions_substack_heuristic():
    assert reply_monitor._story_mentions_substack(
        {"sources": ["PETITION", "FT"]}) is True          # petition11.com
    assert reply_monitor._story_mentions_substack(
        {"sources": ["Junk Bond Investor"]}) is True      # junkbondinvestor.com
    assert reply_monitor._story_mentions_substack(
        {"sources": ["Krugman Substack"]}) is True        # word-level + keyword
    assert reply_monitor._story_mentions_substack(
        {"sources": ["Burry Substack"]}) is True          # michaeljburry
    assert reply_monitor._story_mentions_substack(
        {"sources": ["Yet Another Value Blog"]}) is True  # yetanothervalueblog.com
    assert reply_monitor._story_mentions_substack(
        {"sources": ["FT", "Moody's", "Bloomberg"]}) is False
    assert reply_monitor._story_mentions_substack(
        {"sources": ["13D Research", "Greenmantle", "Yahoo Finance"]}) is False
    assert reply_monitor._story_mentions_substack({"sources": []}) is False
    assert reply_monitor._story_mentions_substack({}) is False


def test_load_digest_for_date_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(reply_monitor, "ARCHIVE_DIR", tmp_path)
    day = tmp_path / "2026-07-13"
    day.mkdir()
    (day / "digest.html").write_text("<div>FULL</div>", encoding="utf-8")
    (day / "digest_team.html").write_text("<div>TEAM</div>", encoding="utf-8")
    assert reply_monitor._load_digest_for_date("2026-07-13") == "<div>FULL</div>"
    assert reply_monitor._load_digest_for_date("2026-07-13", team=True) == "<div>TEAM</div>"


def test_load_digest_for_date_team_missing_returns_none(tmp_path, monkeypatch):
    # Pre-activation: no team file exists -> team askers get NO digest context
    # (rather than leaking the full one)
    monkeypatch.setattr(reply_monitor, "ARCHIVE_DIR", tmp_path)
    day = tmp_path / "2026-07-13"
    day.mkdir()
    (day / "digest.html").write_text("<div>FULL</div>", encoding="utf-8")
    assert reply_monitor._load_digest_for_date("2026-07-13", team=True) is None


# --- _handle_command (ALERT_COMMANDS_SPEC routing; classify/apply mocked) ---

def _parsed(actions=None, question=None, clarification=None):
    return {"actions": actions or [], "question": question,
            "clarification": clarification}


def test_handle_command_actions_only(monkeypatch):
    import alert_commands
    monkeypatch.setattr(alert_commands, "classify_and_parse",
                        lambda text: _parsed(actions=[{"action": "list_config"}]))
    seen = {}

    def fake_apply(actions, asker, today=None):
        seen["actions"], seen["asker"] = actions, asker
        return ["Removed MSTR from the SEC watchlist."], True

    monkeypatch.setattr(alert_commands, "apply_actions", fake_apply)
    html, leftover = reply_monitor._handle_command("stop watching MSTR",
                                                   "apain@acorninv.com")
    assert leftover is None
    assert "Removed MSTR" in html
    assert seen["asker"] == "apain@acorninv.com"  # requester attribution flows through


def test_handle_command_with_rideralong_question(monkeypatch):
    import alert_commands
    monkeypatch.setattr(
        alert_commands, "classify_and_parse",
        lambda text: _parsed(actions=[{"action": "add_ticker", "ticker": "WYNN"}],
                             question="what did Grant's say about Wynn?"))
    monkeypatch.setattr(alert_commands, "apply_actions",
                        lambda a, asker, today=None: (["Added WYNN."], True))
    html, leftover = reply_monitor._handle_command("add WYNN, and what did Grant's say?",
                                                   "a@acorninv.com")
    assert "Added WYNN." in html
    assert leftover == "what did Grant's say about Wynn?"


def test_handle_command_clarification_only(monkeypatch):
    import alert_commands
    applied = []
    monkeypatch.setattr(alert_commands, "classify_and_parse",
                        lambda text: _parsed(clarification="Two alerts mention banks."))
    monkeypatch.setattr(alert_commands, "apply_actions",
                        lambda *a, **k: applied.append(a) or ([], False))
    html, leftover = reply_monitor._handle_command("remove the bank alert",
                                                   "a@acorninv.com")
    assert "Two alerts mention banks." in html
    assert leftover is None
    assert applied == []  # nothing applied on an ambiguous command


def test_handle_command_not_a_command_returns_none(monkeypatch):
    import alert_commands
    monkeypatch.setattr(alert_commands, "classify_and_parse",
                        lambda text: _parsed(question="how did HY trade?"))
    assert reply_monitor._handle_command("how did HY trade?", "a@acorninv.com") is None


def test_handle_command_parse_failure_falls_through(monkeypatch):
    import alert_commands

    def boom(text):
        raise RuntimeError("api down")

    monkeypatch.setattr(alert_commands, "classify_and_parse", boom)
    assert reply_monitor._handle_command("add WYNN", "a@acorninv.com") is None


def test_handle_command_partial_parse_keeps_clarification(monkeypatch):
    import alert_commands
    monkeypatch.setattr(
        alert_commands, "classify_and_parse",
        lambda text: _parsed(actions=[{"action": "add_ticker", "ticker": "WYNN"}],
                             clarification="Two alerts mention banks — which one?"))
    monkeypatch.setattr(alert_commands, "apply_actions",
                        lambda a, asker, today=None: (["Added WYNN."], True))
    html, leftover = reply_monitor._handle_command("add WYNN and drop the bank alert",
                                                   "a@acorninv.com")
    assert "Added WYNN." in html
    assert "which one?" in html  # the ambiguous half isn't silently dropped
    assert leftover is None
