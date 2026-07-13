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
    # The default (team / no-marker) subject is unchanged from the legacy format.
    assert digest._digest_subject() == _legacy_subject("\U0001f4ec")


def test_full_marker_prepended_only_when_full():
    # FULL variant (jared) carries the marker; team variant does not.
    plain = digest._digest_subject()
    full = digest._digest_subject(full=True)
    assert full == f"{digest.FULL_SUBJECT_MARKER}{plain}"
    assert full.startswith("[FULL] ")
    # The prefix phrase the reply query matches still appears verbatim, so the
    # marker can't break reply matching (query ANDs "Re:" + the prefix phrase).
    assert config.DIGEST_SUBJECT_PREFIX in full


def test_full_marker_on_weekly_subject():
    monday = datetime.date(2026, 7, 6)
    plain = digest._weekly_subject(monday)
    full = digest._weekly_subject(monday, full=True)
    assert full == f"{digest.FULL_SUBJECT_MARKER}{plain}"
    assert full.startswith("[FULL] ")


def test_earnings_watchlist_is_sec_watchlist():
    # Single source of truth: the same list object, not a drift-prone copy
    assert earnings.EARNINGS_WATCHLIST is sec_filings.WATCHLIST
