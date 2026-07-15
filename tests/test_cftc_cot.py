"""Stage 2.2/2.3 — cftc_cot: exact-code contract matching (a substring hit in
another line's numeric field could return the wrong contract's row) and, from
Stage 2.3, the prior-WEEK cache selection for WoW changes."""

import json

import pytest

import cftc_cot


def _line(name, code, oi=100, nl=10, ns=5):
    """One legacy-format CFTC CSV line with the columns _parse_cot_line reads."""
    fields = [f'"{name}"', "260707", "2026-07-07", code, "NYME", "x", "x",
              str(oi), str(nl), str(ns), "0", "11", "12", "0", "0", "0"]
    return ",".join(fields)


# --- _find_contract (exact match must beat an earlier substring hit) ---

def test_exact_code_beats_earlier_substring_hit():
    # "020601" appears inside the wrong line's open-interest figure (1020601)
    raw = "\n".join([_line("WRONG CONTRACT", "999999", oi=1020601),
                     _line("RIGHT CONTRACT", "020601")])
    row = cftc_cot._find_contract(raw, "020601")
    assert row["name"] == "RIGHT CONTRACT"
    assert row["cftc_code"] == "020601"


def test_loose_fallback_kept_when_no_exact_match():
    raw = _line("ONLY SUBSTRING", "999999", oi=1020601)
    row = cftc_cot._find_contract(raw, "020601")
    assert row["name"] == "ONLY SUBSTRING"


def test_absent_code_returns_none():
    assert cftc_cot._find_contract(_line("A", "111111"), "020601") is None


def test_parse_cot_line_fields():
    row = cftc_cot._parse_cot_line(_line("WTI CRUDE", "067651", oi=500, nl=40, ns=15))
    assert row["name"] == "WTI CRUDE"
    assert row["cftc_code"] == "067651"
    assert row["open_interest"] == 500
    assert row["noncomm_long"] == 40
    assert row["noncomm_short"] == 15
    assert row["comm_long"] == 11
    assert row["comm_short"] == 12


# --- _load_prior_week (Stage 2.3: prior WEEK, not prior file) ---

@pytest.fixture
def cot_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cftc_cot, "CACHE_DIR", tmp_path / "cot_cache")
    return tmp_path / "cot_cache"


def _write_cache(cache_dir, date, spec_net):
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{date}.json").write_text(
        json.dumps({"WTI Crude": {"contract": "WTI Crude", "spec_net": spec_net}}),
        encoding="utf-8")


def test_prior_week_skips_same_report_date(cot_cache):
    # Monday's run cached 2026-07-07; a Tuesday rerun must compare against the
    # TRUE prior week (2026-06-30), not the report itself (WoW was reading 0)
    _write_cache(cot_cache, "2026-06-30", 100)
    _write_cache(cot_cache, "2026-07-07", 500)
    prior = cftc_cot._load_prior_week("2026-07-07")
    assert prior["WTI Crude"]["spec_net"] == 100


def test_prior_week_empty_when_only_same_date(cot_cache):
    _write_cache(cot_cache, "2026-07-07", 500)
    assert cftc_cot._load_prior_week("2026-07-07") == {}


def test_prior_week_empty_cache(cot_cache):
    assert cftc_cot._load_prior_week("2026-07-07") == {}


def test_prior_week_no_date_takes_newest(cot_cache):
    # no-arg behavior (no current report parsed) keeps the legacy newest-file pick
    _write_cache(cot_cache, "2026-06-30", 100)
    _write_cache(cot_cache, "2026-07-07", 500)
    assert cftc_cot._load_prior_week()["WTI Crude"]["spec_net"] == 500
