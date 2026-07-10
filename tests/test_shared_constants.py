"""Cleanup Stage 1.2 — pin the cross-module single-source constants.

The digest sender and the reply bot's Gmail matcher must agree on the subject
prefix byte-for-byte (silent drift = the bot stops seeing replies), and the
earnings watchlist must stay the SEC watchlist rather than a divergent copy.
"""

import datetime

import config
import digest
import earnings
import reply_monitor
import sec_filings


def _legacy_subject(prefix):
    """The pre-refactor subject format, built independently of digest.py."""
    day = datetime.date.today().day
    return f"{prefix} Daily Inbox Digest — {datetime.date.today().strftime(f'%A, %B {day}')}"


def test_subject_prefix_is_shared():
    # Both modules must reference the ONE constant (identity, not just equality)
    assert reply_monitor.DIGEST_SUBJECT_PREFIX is config.DIGEST_SUBJECT_PREFIX
    assert config.DIGEST_SUBJECT_PREFIX == "\U0001f4ec Daily Inbox Digest"


def test_daily_subject_byte_identical_to_legacy():
    assert digest._digest_subject() == _legacy_subject("\U0001f4ec")


def test_weekly_prefix_override_byte_identical_to_legacy():
    # The Friday call site passes the full "📊 Daily Inbox Digest" prefix now
    got = digest._digest_subject("\U0001f4ca Daily Inbox Digest")
    assert got == _legacy_subject("\U0001f4ca")


def test_earnings_watchlist_is_sec_watchlist():
    # Single source of truth: the same list object, not a drift-prone copy
    assert earnings.EARNINGS_WATCHLIST is sec_filings.WATCHLIST
