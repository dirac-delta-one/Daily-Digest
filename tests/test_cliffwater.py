"""Cliffwater BDC index row (SNAPSHOT_UPDATE §4 row 3, jared-approved
2026-07-23): fetch/change math and Private Credit table rendering."""

import datetime

import cliffwater_data
import market_data

_CHART = {
    "x": ["2026-06-20", "2026-07-15", "2026-07-21", "2026-07-22"],
    "CWBDC": [4199.80, 4425.23, 4390.27, 4343.77],
    "CWBDC_Yield": [11.2, 11.4, 11.56, 11.68],  # present but unused
}


def test_fetch_builds_row_with_changes(monkeypatch):
    monkeypatch.setattr(cliffwater_data, "_fetch_chart_json", lambda: _CHART)
    rows = cliffwater_data.fetch_cliffwater_bdc()
    assert len(rows) == 1
    r = rows[0]
    assert r["label"] == "Cliffwater BDC Index"
    assert r["section"] == "private" and r["unit"] == "index"
    assert r["as_of"] == "2026-07-22"
    assert r["value"] == 4343.77
    assert round(r["chg_1d"], 2) == round(4343.77 - 4390.27, 2)
    assert round(r["chg_1w"], 2) == round(4343.77 - 4425.23, 2)  # <= 07-15
    assert round(r["chg_1m"], 2) == round(4343.77 - 4199.80, 2)  # <= 06-22
    assert r["source"].startswith("Cliffwater")


def test_fetch_failure_returns_empty(monkeypatch):
    def boom():
        raise OSError("site down")
    monkeypatch.setattr(cliffwater_data, "_fetch_chart_json", boom)
    assert cliffwater_data.fetch_cliffwater_bdc() == []
    monkeypatch.setattr(cliffwater_data, "_fetch_chart_json", lambda: {})
    assert cliffwater_data.fetch_cliffwater_bdc() == []


def test_private_table_renders_cliffwater_row(monkeypatch):
    monkeypatch.setattr(cliffwater_data, "_fetch_chart_json", lambda: _CHART)
    row = cliffwater_data.fetch_cliffwater_bdc()[0]
    html = market_data.build_private_credit_html([row])
    assert "Cliffwater BDC Index" in html
    assert "4,343.77" in html  # unit "index" formatting
    assert "Cliffwater (bdcs.com)" in html  # footnote attribution
    assert "as of 2026-07-22" in html
    # without the row, no attribution
    plain = market_data.build_private_credit_html([])
    assert plain == "" or "Cliffwater" not in plain


def test_single_observation_has_no_changes(monkeypatch):
    monkeypatch.setattr(cliffwater_data, "_fetch_chart_json",
                        lambda: {"x": ["2026-07-22"], "CWBDC": [4343.77]})
    r = cliffwater_data.fetch_cliffwater_bdc()[0]
    assert r["chg_1d"] is None and r["chg_1w"] is None


def test_month_lookup_uses_calendar_days():
    # guard the date math against drift: 30 days before 07-22 is 06-22,
    # so the 06-20 point is the at-or-before match
    ref = datetime.date(2026, 7, 22) - datetime.timedelta(days=30)
    assert ref.isoformat() == "2026-06-22"
