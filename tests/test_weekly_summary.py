"""Stage 2.4 — the weekly-wrap bundle: operator-specified subject, Monday math,
preamble strip (shared with digest pass 2), and save-to-disk."""

import datetime

import config
import digest


# --- _week_monday ---

def test_week_monday():
    assert digest._week_monday(datetime.date(2026, 7, 10)) == datetime.date(2026, 7, 6)  # Fri
    assert digest._week_monday(datetime.date(2026, 7, 6)) == datetime.date(2026, 7, 6)   # Mon
    assert digest._week_monday(datetime.date(2026, 7, 12)) == datetime.date(2026, 7, 6)  # Sun


# --- _weekly_subject (operator-specified wording, 2026-07-10) ---

def test_weekly_subject_format():
    subject = digest._weekly_subject(datetime.date(2026, 7, 6))
    assert subject == "\U0001f4ca Weekly Research Wrap — Week of Monday, July 6"


def test_weekly_subject_no_leading_zero_day():
    subject = digest._weekly_subject(datetime.date(2026, 8, 3))
    assert subject.endswith("Week of Monday, August 3")


def test_weekly_subject_never_matches_reply_query():
    # The reply bot matches "Re: 📬 Daily Inbox Digest" — the weekly must not collide
    subject = digest._weekly_subject(datetime.date(2026, 7, 6))
    assert not subject.startswith(config.DIGEST_SUBJECT_PREFIX)


# --- _strip_to_html (pass 2 + weekly share it) ---

def test_strip_to_html_drops_preamble():
    assert digest._strip_to_html("Here is the digest:\n<div>x</div>") == "<div>x</div>"


def test_strip_to_html_passthrough():
    assert digest._strip_to_html("<div>x</div>") == "<div>x</div>"
    assert digest._strip_to_html("no div at all") == "no div at all"


# --- save_weekly_digest ---

def test_save_weekly_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path / "digests")
    digest.save_weekly_digest("<div>weekly</div>", date=datetime.date(2026, 7, 10))
    saved = tmp_path / "digests" / "weekly_2026-07-10.html"
    assert saved.read_text(encoding="utf-8") == "<div>weekly</div>"


def test_weekly_filename_invisible_to_week_digest_loader(tmp_path, monkeypatch):
    # _get_week_digests loads exact "<iso-date>.html" names — a saved weekly
    # file must never be picked up as a daily digest input next Friday.
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path / "digests")
    digest.save_weekly_digest("<div>weekly</div>")
    assert digest._get_week_digests() == []
