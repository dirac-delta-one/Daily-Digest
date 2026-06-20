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
