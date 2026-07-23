"""Cross-day awareness (2026-07-23, jared: "it isn't really a DAILY digest"):
PACER freshness filter, previous-run discovery, the weekend-aware lookback
retune, and the previous-digest prompt block."""

import datetime

import pytest

import digest
import pacer
import substack


# --- pacer._fresh_filing ---

_NOW = datetime.datetime(2026, 7, 23, 12, 0, tzinfo=datetime.timezone.utc)


def _rfc822(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def test_fresh_filing_current_case_recent_pubdate():
    assert pacer._fresh_filing(
        _rfc822(_NOW - datetime.timedelta(hours=3)), "26-90716", now=_NOW)


def test_old_case_year_dropped_even_with_fresh_entry():
    # The LL Flooring class: 2024 case, brand-new amended-petition entry.
    assert not pacer._fresh_filing(
        _rfc822(_NOW - datetime.timedelta(hours=1)), "24-11680", now=_NOW)
    assert not pacer._fresh_filing(
        _rfc822(_NOW - datetime.timedelta(hours=1)), "25-90607", now=_NOW)


def test_stale_pubdate_dropped(monkeypatch):
    monkeypatch.setattr(pacer, "LOOKBACK_HOURS", 24)
    assert not pacer._fresh_filing(
        _rfc822(_NOW - datetime.timedelta(hours=40)), "26-90716", now=_NOW)


def test_lookback_widening_admits_weekend_entry(monkeypatch):
    # Monday run with a 72h window keeps a Saturday filing.
    monkeypatch.setattr(pacer, "LOOKBACK_HOURS", 72)
    assert pacer._fresh_filing(
        _rfc822(_NOW - datetime.timedelta(hours=60)), "26-90716", now=_NOW)


def test_january_grace_accepts_prior_year_case():
    jan = datetime.datetime(2027, 1, 2, 12, 0, tzinfo=datetime.timezone.utc)
    assert pacer._fresh_filing(
        _rfc822(jan - datetime.timedelta(hours=5)), "26-99999", now=jan)
    # ...but not in February.
    feb = datetime.datetime(2027, 2, 2, 12, 0, tzinfo=datetime.timezone.utc)
    assert not pacer._fresh_filing(
        _rfc822(feb - datetime.timedelta(hours=5)), "26-99999", now=feb)


def test_unparseable_values_over_include():
    # Codebase convention: unparseable dates/case numbers pass through
    # (the seen-state still dedups).
    assert pacer._fresh_filing("not a date", None, now=_NOW)
    assert pacer._fresh_filing("", "(name not parsed)", now=_NOW)


# --- digest._previous_run_date ---

def test_previous_run_date_from_digests_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path)
    (tmp_path / "2026-07-18.html").write_text("x", encoding="utf-8")
    (tmp_path / "2026-07-17_team.html").write_text("x", encoding="utf-8")
    (tmp_path / "weekly_2026-07-17.html").write_text("x", encoding="utf-8")
    today = datetime.date(2026, 7, 21)  # Tuesday after a Saturday file
    assert digest._previous_run_date(today) == datetime.date(2026, 7, 18)


def test_previous_run_date_weekday_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path / "missing")
    monday = datetime.date(2026, 7, 20)
    assert digest._previous_run_date(monday) == datetime.date(2026, 7, 17)  # Friday
    wednesday = datetime.date(2026, 7, 22)
    assert digest._previous_run_date(wednesday) == datetime.date(2026, 7, 21)


# --- digest._set_lookback_hours ---

def test_set_lookback_hours_reaches_all_sources(monkeypatch):
    saved = [(m, m.HOURS_LOOKBACK) for m in
             (digest._news_mod, digest._ratings_mod, digest._sec_filings_mod,
              digest._treasury_mod, digest._fed_research_mod,
              digest._substack_mod)]
    saved_pacer = pacer.LOOKBACK_HOURS
    try:
        digest._set_lookback_hours(72)
        for mod, _ in saved:
            assert mod.HOURS_LOOKBACK == 72
        assert pacer.LOOKBACK_HOURS == 72
        # substack reads it at call time (the def-time default-arg trap
        # was fixed): a 60h-old post is admitted under the 72h window.
        old = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(hours=60)).isoformat()
        assert substack._is_recent({"post_date": old})
        digest._set_lookback_hours(24)
        assert not substack._is_recent({"post_date": old})
    finally:
        for mod, val in saved:
            mod.HOURS_LOOKBACK = val
        pacer.LOOKBACK_HOURS = saved_pacer


# --- digest._previous_digest_block ---

_DIGEST_HTML = (
    '<div><h2 style="x">1. Top Takeaways</h2>'
    "<li><strong>Oil:</strong> Brent cleared $98 (WSJ)</li>"
    '<h2 style="x">2. Market &amp; Macro</h2>'
    "<li><strong>Bonds:</strong> 10Y at 4.63% (FT)</li></div>"
)


def test_previous_digest_block_prefers_team_file(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path)
    (tmp_path / "2026-07-22.html").write_text(
        _DIGEST_HTML.replace("Oil", "FULLONLY"), encoding="utf-8")
    (tmp_path / "2026-07-22_team.html").write_text(_DIGEST_HTML, encoding="utf-8")
    block = digest._previous_digest_block(datetime.date(2026, 7, 23))
    assert "PREVIOUS DIGEST — Wednesday, 2026-07-22" in block
    assert "Brent cleared $98" in block
    assert "FULLONLY" not in block  # team file wins (Substack-free prefix)
    assert "ALREADY REPORTED" in block


def test_previous_digest_block_empty_when_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path)
    assert digest._previous_digest_block(datetime.date(2026, 7, 23)) == ""


def test_previous_digest_block_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path)
    big = ('<div><h2 style="x">1. Top Takeaways</h2>'
           + "<li>word " * 30_000 + "</li></div>")
    (tmp_path / "2026-07-22_team.html").write_text(big, encoding="utf-8")
    block = digest._previous_digest_block(datetime.date(2026, 7, 23))
    assert len(block) <= digest._PREV_DIGEST_CAP + 100
    assert "truncated" in block


# --- prompt plumbing ---

def test_previous_context_lands_in_shared_prompt(monkeypatch):
    from types import SimpleNamespace
    calls = []

    class _FakeStream:
        def __init__(self, kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return SimpleNamespace(
                content=[SimpleNamespace(text="<div>d</div>")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                                      cache_read_input_tokens=0,
                                      cache_creation_input_tokens=0))

    class _FakeClient:
        def __init__(self):
            self.messages = SimpleNamespace(
                stream=lambda **kw: _FakeStream(kw),
                create=lambda **kw: pytest.fail("digest passes should stream"))

    monkeypatch.setattr(digest.anthropic, "Anthropic", _FakeClient)
    monkeypatch.setattr(digest, "get_memory_context", lambda: "")
    _final, source_text = digest.summarize_with_claude(
        emails=[], previous_digest_context="PREVIOUS DIGEST — SENTINEL")
    blocks = [b["text"] for b in calls[0]["messages"][0]["content"]
              if b.get("type") == "text"]
    # the context rides as its own shared-prefix block...
    assert any("PREVIOUS DIGEST — SENTINEL" in t for t in blocks[1:])
    # ...NOT inside the prompt block, which feeds alert evaluation —
    # yesterday's digest text must never re-trigger alerts.
    assert "SENTINEL" not in blocks[0]
    assert "SENTINEL" not in source_text
    # both passes share the identical prefix blocks (cache contract)
    blocks_p2 = [b["text"] for b in calls[1]["messages"][0]["content"]
                 if b.get("type") == "text"]
    assert blocks_p2[:len(blocks)-1] == blocks[:-1]  # all but the per-pass instruction
