"""13D WILTW summary cache — a cache hit must skip the Playwright download + Opus call.

WILTW publishes weekly but the digest runs daily; the cache stops the same report
being re-downloaded and re-summarized (a ~$0.65 Opus call) Thursday->Wednesday.
"""

import datetime

import pytest

import thirteen_d


@pytest.fixture
def temp_cache(tmp_path, monkeypatch):
    """Point the cache at a throwaway file so tests don't touch the real one."""
    monkeypatch.setattr(thirteen_d, "WILTW_CACHE_FILE", tmp_path / "wiltw_cache.json")
    return tmp_path


def _most_recent_thursday():
    today = datetime.date.today()
    return today - datetime.timedelta(days=(today.weekday() - 3) % 7)


# --- cache round-trip ---

def test_save_load_roundtrip(temp_cache):
    result = {"title": "T", "date": "2026-06-25", "summary": "S", "url": "u"}
    thirteen_d._save_summary_cache("2026-06-25", result)
    assert thirteen_d._load_summary_cache() == {"2026-06-25": result}


def test_load_missing_returns_empty(temp_cache):
    assert thirteen_d._load_summary_cache() == {}


# --- fetch_wiltw cache behavior ---

def test_cache_hit_skips_download_and_opus(temp_cache, monkeypatch):
    report_date = _most_recent_thursday()  # within the 6-day window
    monkeypatch.setattr(thirteen_d, "_find_latest_thursday", lambda: report_date)

    cached = {
        "title": "WILTW", "date": report_date.isoformat(),
        "summary": "cached summary", "url": "https://client.13d.com/report",
    }
    thirteen_d._save_summary_cache(report_date.isoformat(), cached)

    # Reaching either of these means the cache didn't short-circuit — fail loudly.
    def _boom(*a, **k):
        raise AssertionError("cache hit must not download or summarize")
    monkeypatch.setattr(thirteen_d, "_download_pdf", _boom)
    monkeypatch.setattr(thirteen_d, "_summarize_pdf", _boom)

    assert thirteen_d.fetch_wiltw() == cached


def test_stale_report_returns_none(temp_cache, monkeypatch):
    # A report older than 6 days is skipped before any cache/download work.
    old_thursday = datetime.date.today() - datetime.timedelta(days=20)
    monkeypatch.setattr(thirteen_d, "_find_latest_thursday", lambda: old_thursday)
    assert thirteen_d.fetch_wiltw() is None


# --- _persist_pdf (Stage 2.2: all download paths archive consistently) ---

def test_persist_pdf_writes_to_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(thirteen_d, "SCRIPT_DIR", tmp_path)
    p = thirteen_d._persist_pdf(b"%PDF fake", report_date=datetime.date(2026, 7, 9))
    assert p.read_bytes() == b"%PDF fake"
    assert p.name == "WILTW_2026-07-09.pdf"
    assert p.parent.name == "pdfs"
    assert p.parent.parent.name == datetime.date.today().isoformat()
    # nothing littered outside the archive tree
    assert list(tmp_path.glob("*.pdf")) == []
