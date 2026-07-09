"""Efficiency O3 — pin the content monitor's recording and streak logic."""

import json

import pytest

import content_monitor as cm


@pytest.fixture
def counts_file(tmp_path):
    return tmp_path / "source_counts.json"


def _history(*runs):
    """Build history entries from {source: count} dicts."""
    return [{"date": f"2026-07-{i+1:02d}", "counts": dict(c)} for i, c in enumerate(runs)]


# --- record_counts ---

def test_record_appends_and_persists(counts_file):
    cm.record_counts({"substack": 5, "trace_data": 0}, path=counts_file)
    history = cm.record_counts({"substack": 4, "trace_data": 0}, path=counts_file)
    assert len(history) == 2
    assert history[-1]["counts"] == {"substack": 4, "trace_data": 0}
    on_disk = json.loads(counts_file.read_text(encoding="utf-8"))
    assert on_disk == history


def test_record_trims_to_keep_runs(counts_file):
    for i in range(cm.KEEP_RUNS + 10):
        history = cm.record_counts({"substack": i}, path=counts_file)
    assert len(history) == cm.KEEP_RUNS
    assert history[-1]["counts"]["substack"] == cm.KEEP_RUNS + 9


def test_record_corrupt_file_recovers(counts_file):
    counts_file.write_text("not json", encoding="utf-8")
    history = cm.record_counts({"substack": 5}, path=counts_file)
    assert len(history) == 1


# --- check_degradation ---

def test_degradation_fires_for_normally_nonzero_source():
    # 4 healthy runs, then 3 zeros -> signal
    history = _history(*[{"substack": 5}] * 4, *[{"substack": 0}] * 3)
    signals = cm.check_degradation(history)
    assert len(signals) == 1
    assert signals[0].startswith("substack: 0 items for 3 straight runs")


def test_no_signal_when_streak_broken():
    history = _history(*[{"substack": 5}] * 4,
                       {"substack": 0}, {"substack": 2}, {"substack": 0})
    assert cm.check_degradation(history) == []


def test_always_zero_source_never_fires():
    # TRACE is always 0 — nonzero share 0% < 50%, never "normally nonzero"
    history = _history(*[{"trace_data": 0}] * 10)
    assert cm.check_degradation(history) == []


def test_sporadic_source_below_share_never_fires():
    # nonzero in 1 of 4 earlier runs (25% < 50%) — e.g. quarterly 13F
    history = _history({"fund_results": 3}, {"fund_results": 0},
                       {"fund_results": 0}, {"fund_results": 0},
                       *[{"fund_results": 0}] * 3)
    assert cm.check_degradation(history) == []


def test_insufficient_history_no_signal():
    # 3 zeros but only 2 earlier runs (< MIN_HISTORY) — too new to judge
    history = _history(*[{"substack": 5}] * 2, *[{"substack": 0}] * 3)
    assert cm.check_degradation(history) == []


def test_missing_key_in_recent_run_skipped():
    # source absent from a recent run's counts -> can't confirm the streak
    history = _history(*[{"substack": 5, "wiltw": 1}] * 4,
                       {"substack": 0, "wiltw": 0},
                       {"substack": 0},              # wiltw missing here
                       {"substack": 0, "wiltw": 0})
    signals = cm.check_degradation(history)
    assert len(signals) == 1 and "substack" in signals[0]


def test_multiple_sources_fire_independently():
    history = _history(*[{"substack": 5, "wiltw": 1, "news_articles": 100}] * 5,
                       *[{"substack": 0, "wiltw": 0, "news_articles": 90}] * 3)
    signals = cm.check_degradation(history)
    assert len(signals) == 2
    assert any("substack" in s for s in signals)
    assert any("wiltw" in s for s in signals)


# --- record_and_check ---

def test_record_and_check_end_to_end(counts_file):
    for _ in range(4):
        assert cm.record_and_check({"substack": 5}, path=counts_file) == []
    cm.record_and_check({"substack": 0}, path=counts_file)
    cm.record_and_check({"substack": 0}, path=counts_file)
    signals = cm.record_and_check({"substack": 0}, path=counts_file)
    assert len(signals) == 1 and "substack" in signals[0]
