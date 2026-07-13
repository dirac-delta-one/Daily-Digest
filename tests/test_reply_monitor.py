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
    assert reply_monitor._is_full_access("JAREDTRAMONTANO@GMAIL.COM") is True
    assert reply_monitor._is_full_access("acohen@acorninv.com") is False
    assert reply_monitor._is_full_access("stranger@example.com") is False


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
