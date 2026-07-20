"""iShares fund-reported OAS (ishares_data.py) — parse, history math, rows.

All offline: fixture HTML only, no network."""

import ishares_data


# The characteristics blob as it appears in the page source (HTML-escaped
# JSON) — trimmed to the fields the parser binds on.
_PAGE = (
    "<html><body><script>var x = {&quot;label&quot;:&quot;Option Adjusted "
    "Spread&quot;,&quot;formattedValue&quot;:&quot;94.54 bps&quot;,"
    "&quot;sortOrder&quot;:140,&quot;infoBubble&quot;:&quot;The weighted "
    "average incremental yield...&quot;,&quot;formattedAsOfDate&quot;:&quot;"
    "Jul 15, 2026&quot;,&quot;name&quot;:&quot;optionAdjustedSpread&quot;}"
    "</script></body></html>"
)


def test_parse_oas_from_escaped_page():
    assert ishares_data._parse_oas(_PAGE) == (94.54, "2026-07-15")


def test_parse_oas_missing_field():
    assert ishares_data._parse_oas("<html>no characteristics here</html>") is None


def test_parse_oas_bad_date_falls_back_to_today():
    page = _PAGE.replace("Jul 15, 2026", "not a date")
    oas, as_of = ishares_data._parse_oas(page)
    assert oas == 94.54
    assert len(as_of) == 10  # today's ISO date — value survives a date change


def test_changes_from_history():
    history = {
        "2026-06-15": 90.0,   # ~1 month before
        "2026-07-08": 93.0,   # ~1 week before
        "2026-07-14": 94.0,   # previous day
    }
    chg_1d, chg_1w, chg_1m = ishares_data._changes_from_history(
        history, "2026-07-15", 94.54)
    assert chg_1d == 0.54            # vs 94.0
    assert chg_1w == 94.54 - 93.0    # closest at/before -7d
    assert chg_1m == 94.54 - 90.0    # closest at/before -30d


def test_changes_empty_history():
    assert ishares_data._changes_from_history({}, "2026-07-15", 94.54) == (
        None, None, None)


def test_changes_ignore_same_day_and_future():
    # a same-day rerun must not treat its own earlier reading as "yesterday"
    history = {"2026-07-15": 94.54}
    assert ishares_data._changes_from_history(history, "2026-07-15", 94.54) == (
        None, None, None)


def test_fetch_builds_credit_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(ishares_data, "CACHE_PATH", tmp_path / "cache.json")

    class _Resp:
        def read(self):
            return _PAGE.encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ishares_data.urllib.request, "urlopen",
                        lambda req, timeout=0: _Resp())
    rows = ishares_data.fetch_ishares_oas()
    assert len(rows) == len(ishares_data.FUNDS)  # HYG + LQD + IGLB + IGIB
    for row in rows:
        assert row["section"] == "credit"
        assert row["unit"] == "spread"
        assert row["metric"] == "Portfolio OAS"
        assert row["value"] == 94.54
        assert row["series_id"].startswith("ISHARES:")
    # history persisted for tomorrow's 1D change
    assert (tmp_path / "cache.json").exists()
    # prompt text names the funds and the value
    text = ishares_data.format_ishares_for_prompt(rows)
    assert "IGLB (Long-Term IG) Portfolio OAS: 95 bps" in text


def test_fetch_failure_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(ishares_data, "CACHE_PATH", tmp_path / "cache.json")

    def _boom(req, timeout=0):
        raise OSError("blocked")

    monkeypatch.setattr(ishares_data.urllib.request, "urlopen", _boom)
    assert ishares_data.fetch_ishares_oas() == []
