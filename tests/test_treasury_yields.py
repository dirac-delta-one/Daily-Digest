"""Treasury.gov par-curve fetcher (SNAPSHOT_UPDATE §2.1) — offline parse and
series-shaping tests, plus the macro_data fallback seam and the lag-honest
footnotes (§1.6/§2.3)."""

import datetime

import macro_data
import market_data
import treasury_yields

_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
  <entry><content><m:properties>
    <d:NEW_DATE>2026-07-21T00:00:00</d:NEW_DATE>
    <d:BC_2YEAR>4.28</d:BC_2YEAR>
    <d:BC_10YEAR>4.63</d:BC_10YEAR>
    <d:BC_20YEAR>5.14</d:BC_20YEAR>
    <d:BC_30YEAR>5.13</d:BC_30YEAR>
  </m:properties></content></entry>
  <entry><content><m:properties>
    <d:NEW_DATE>2026-07-22T00:00:00</d:NEW_DATE>
    <d:BC_2YEAR>4.31</d:BC_2YEAR>
    <d:BC_10YEAR>4.67</d:BC_10YEAR>
    <d:BC_20YEAR>N/A</d:BC_20YEAR>
    <d:BC_30YEAR>5.15</d:BC_30YEAR>
  </m:properties></content></entry>
</feed>"""


def test_parse_curve_xml_maps_fields_and_skips_na():
    out = treasury_yields.parse_curve_xml(_XML, treasury_yields.NOMINAL_FIELDS)
    assert out["2026-07-21"]["DGS10"] == 4.63
    assert out["2026-07-22"]["DGS2"] == 4.31
    assert "DGS20" not in out["2026-07-22"]  # N/A skipped
    assert out["2026-07-21"]["DGS20"] == 5.14


def test_months_covering_spans_boundary():
    months = treasury_yields._months_covering(
        datetime.date(2026, 6, 10), datetime.date(2026, 7, 23))
    assert months == ["202606", "202607"]


def test_fetch_treasury_series_builds_series_and_breakeven(monkeypatch):
    real_xml = _XML.replace("BC_", "TC_")  # same shape, real-curve fields

    def fake_fetch(dataset, month):
        return _XML if "real" not in dataset else real_xml

    monkeypatch.setattr(treasury_yields, "_fetch_xml", fake_fetch)
    series = treasury_yields.fetch_treasury_series(datetime.date(2026, 7, 1))
    assert series["DGS10"].iloc[-1] == 4.67
    assert series["DGS10"].index[-1].date() == datetime.date(2026, 7, 22)
    # TC_10YEAR rides the renamed fixture -> DFII10; breakeven = nominal - real
    assert series["DFII10"].iloc[-1] == 4.67
    assert series["T10YIE"].iloc[-1] == 0.0
    # a later start_date drops the 07-21 observation
    series2 = treasury_yields.fetch_treasury_series(datetime.date(2026, 7, 22))
    assert len(series2["DGS10"]) == 1


# --- footnotes (SNAPSHOT_UPDATE §1.6 / §2.3) ---

def _row(label, date, source="FRED", section="rates", **kw):
    d = dict(series_id=label, label=label, unit="rate", section=section,
             metric="Yield", value=4.5, date=date, source=source,
             chg_1d=None, chg_1w=None, chg_1m=None)
    d.update(kw)
    return d


def test_as_of_label_majority_plus_outliers():
    frag = market_data.as_of_label(
        [("2Y UST", "2026-07-22"), ("10Y UST", "2026-07-22"),
         ("SOFR", "2026-07-21")])
    assert frag == "as of 2026-07-22; SOFR: 2026-07-21"
    assert market_data.as_of_label([]) == ""


def test_fred_table_footnote_honest_dates_and_sources():
    html = macro_data._build_fred_table(
        [_row("2Y UST", "2026-07-22", "U.S. Treasury"),
         _row("10Y UST", "2026-07-22", "U.S. Treasury"),
         _row("SOFR", "2026-07-21", "FRED")], "Rates Snapshot")
    assert "Source: U.S. Treasury · FRED" in html
    assert "as of 2026-07-22; SOFR: 2026-07-21" in html
    # the old max() behavior would have claimed 07-22 with no outlier note


def test_rates_note_is_source_aware():
    tsy = macro_data.build_rates_table_html(
        [_row("10Y UST", "2026-07-22", "U.S. Treasury")])
    assert "Treasury.gov daily par yield curves" in tsy
    assert "SOFR publishes the following morning" in tsy  # SOFR on FRED
    both = macro_data.build_rates_table_html(
        [_row("10Y UST", "2026-07-22", "U.S. Treasury"),
         _row("SOFR", "2026-07-22", "NY Fed")])
    assert "SOFR = NY Fed, prior business day's print" in both
    fallback = macro_data.build_rates_table_html(
        [_row("10Y UST", "2026-07-21", "FRED")])
    assert "two sessions old" in fallback


def test_fetch_sofr_series_parses_and_filters(monkeypatch):
    monkeypatch.setattr(treasury_yields, "_fetch_sofr_json", lambda n: {
        "refRates": [
            {"effectiveDate": "2026-07-22", "percentRate": 3.62},
            {"effectiveDate": "2026-07-21", "percentRate": 3.61},
            {"effectiveDate": "2026-06-01", "percentRate": 3.50},
        ]})
    s = treasury_yields.fetch_sofr_series(datetime.date(2026, 7, 1))
    assert len(s) == 2  # June obs filtered out
    assert s.iloc[-1] == 3.62
    assert s.index[-1].date() == datetime.date(2026, 7, 22)


def test_lag_marker_business_day_semantics():
    wed = datetime.date(2026, 7, 22)
    assert market_data.lag_marker("2026-07-22", today=wed) == ""      # same-day
    assert market_data.lag_marker("2026-07-21", today=wed) == "*"     # T-1
    assert market_data.lag_marker("2026-07-20", today=wed) == "**"    # T-2
    monday = date_mon = datetime.date(2026, 7, 20)
    assert market_data.lag_marker("2026-07-17", today=monday) == "*"  # Fri->Mon
    assert market_data.lag_marker("2026-07-16", today=date_mon) == "**"
    assert market_data.lag_marker("", today=wed) == ""                # missing
    assert market_data.lag_marker("garbage", today=wed) == ""         # unparseable


def test_lag_markers_render_with_legend():
    def yrow(label, as_of):
        return dict(label=label, value=1.0, unit="dollar", section="market",
                    metric="x", chg_1d=None, pct_1d=None, chg_1w=None,
                    pct_1w=None, chg_1m=None, pct_1m=None, as_of=as_of)

    today = datetime.date.today()
    prior = (today - datetime.timedelta(
        days=3 if today.weekday() == 0 else 1)).isoformat()
    html = market_data.build_market_table_html(
        [yrow("S&P 500", prior), yrow("BTC", today.isoformat())])
    assert "S&P 500*</td>" in html
    assert "BTC</td>" in html  # same-day: unmarked
    assert market_data.LAG_LEGEND.strip(" ·") in html
    # all-same-day table carries no legend
    clean = market_data.build_market_table_html([yrow("BTC", today.isoformat())])
    assert "two+ business days old" not in clean


def test_fred_rows_carry_lag_markers():
    today = datetime.date.today()
    two_back = today - datetime.timedelta(days=4)
    html = macro_data._build_fred_table(
        [_row("HY", two_back.isoformat(), "FRED", section="credit")],
        "Corporate Credit Snapshot")
    assert "HY**</td>" in html
    assert "two+ business days old" in html


def test_freshness_summary_splits_same_day_vs_prior():
    rows = [dict(label="BTC", as_of="2026-07-23"),
            dict(label="S&P 500", as_of="2026-07-22"),
            dict(label="WTI Crude", as_of="2026-07-23"),
            dict(label="NoDate")]
    line = market_data._freshness_summary(rows, today=datetime.date(2026, 7, 23))
    assert line == ("same-day bars: BTC, WTI Crude"
                    " | prior-session: S&P 500")


def test_yahoo_tables_carry_lag_notes():
    def yrow(label, as_of, section):
        return dict(label=label, value=1.0, unit="dollar", section=section,
                    metric="x", chg_1d=None, pct_1d=None, chg_1w=None,
                    pct_1w=None, chg_1m=None, pct_1m=None,
                    source="Yahoo", as_of=as_of)

    market = market_data.build_market_table_html(
        [yrow("S&P 500", "2026-07-22", "market"),
         yrow("BTC", "2026-07-23", "market")])
    assert "US-listed rows = previous close" in market
    assert "as of 2026-07-22; BTC: 2026-07-23" in market
    ai = market_data.build_ai_html([yrow("Nasdaq", "2026-07-22", "ai")])
    assert "SK Hynix = same-day Seoul close" in ai
    private = market_data.build_private_credit_html(
        [yrow("BKLN", "2026-07-22", "private")])
    assert "previous close" in private
