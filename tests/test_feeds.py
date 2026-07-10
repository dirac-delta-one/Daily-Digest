"""Stage 2.1 — pin feeds.py's date parsing + recency window (previously untested;
the WORKLOG Phase-2.3 'unit tests' were session-ad-hoc and never committed)."""

import datetime
from email.utils import format_datetime

import feeds


def _rfc2822(dt):
    return format_datetime(dt)


# --- parse_date ---

def test_parse_date_rfc2822():
    dt = datetime.datetime(2026, 7, 10, 8, 0, 0,
                           tzinfo=datetime.timezone(datetime.timedelta(hours=-4)))
    assert feeds.parse_date(_rfc2822(dt)) == dt


def test_parse_date_iso_with_z():
    parsed = feeds.parse_date("2026-07-10T12:30:00.000Z")
    assert parsed == datetime.datetime(2026, 7, 10, 12, 30,
                                       tzinfo=datetime.timezone.utc)


def test_parse_date_garbage_and_empty():
    assert feeds.parse_date("not a date") is None
    assert feeds.parse_date("") is None
    assert feeds.parse_date(None) is None


# --- is_recent ---

def test_is_recent_inside_window():
    now = datetime.datetime.now(datetime.timezone.utc)
    assert feeds.is_recent(_rfc2822(now - datetime.timedelta(hours=1)), hours=24) is True


def test_is_recent_outside_window():
    now = datetime.datetime.now(datetime.timezone.utc)
    assert feeds.is_recent(_rfc2822(now - datetime.timedelta(hours=48)), hours=24) is False


def test_is_recent_naive_date_treated_as_utc():
    # RFC 2822 without a timezone parses naive; is_recent must assume UTC, not crash
    naive = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(hours=1)).strftime("%a, %d %b %Y %H:%M:%S")
    assert feeds.is_recent(naive, hours=24) is True


def test_is_recent_unparseable_over_includes():
    # HANDOFF §6: unparseable dates deliberately over-include (Opus curates downstream)
    assert feeds.is_recent("garbage", hours=24) is True
    assert feeds.is_recent("", hours=24) is True
