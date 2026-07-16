"""Phase 3.4 — pin the market/macro formatting + unit-conversion math.
Extended 2026-07-15 for the snapshot redesign (sectioned tables, derived
rates rows, KRW/pct units)."""

import market_data
import macro_data


def test_market_fmt_value():
    assert market_data._fmt_value("S&P 500", 5123.4, "dollar") == "$5,123"
    assert market_data._fmt_value("WTI Crude", 80.5, "dollar") == "$80.50"
    assert market_data._fmt_value("BTC", 65000.0, "dollar") == "$65,000"
    assert market_data._fmt_value("VIX", 14.23, "index") == "14.23"
    # 2026-07-15: indices get thousands separators (Nasdaq/Russell scale)
    assert market_data._fmt_value("Nasdaq Composite", 26269.23, "index") == "26,269.23"
    assert market_data._fmt_value("SK Hynix (KRW)", 1913000.0, "won") == "₩1,913,000"
    assert market_data._fmt_value("BKLN Trailing Yield", 6.59, "pct") == "6.59%"


def test_macro_fmt_val_units():
    assert macro_data._fmt_val("HY OAS", 320.0, "spread") == "320 bps"
    assert macro_data._fmt_val("10Y UST", 4.25, "rate") == "4.25%"
    assert macro_data._fmt_val("Initial Jobless Claims", 219000.0, "count") == "219,000"
    assert macro_data._fmt_val("CPI (monthly)", 314.2, "cpi") == "314.2"


def test_macro_change_bps_conversion():
    # rate changes are decimals; the prompt formatter converts them to bps (x100)
    data = [{
        "label": "10Y UST", "unit": "rate", "value": 4.25, "series_id": "DGS10",
        "date": "2026-06-18", "chg_1d": 0.10, "chg_1w": None, "chg_1m": -0.25,
    }]
    out = macro_data.format_macro_for_prompt(data)
    assert "10Y UST: 4.25%" in out
    assert "1D: +10 bps" in out
    assert "1W: n/a" in out
    assert "1M: -25 bps" in out


# --- 2026-07-15 snapshot redesign ---

def _fred_row(label, section, unit="rate", value=4.5, series_id="X"):
    return {"label": label, "unit": unit, "section": section, "value": value,
            "series_id": series_id, "date": "2026-07-15",
            "chg_1d": None, "chg_1w": None, "chg_1m": None}


def _yahoo_row(label, section, unit="dollar", value=50.0, ticker="TICK"):
    return {"label": label, "unit": unit, "section": section, "value": value,
            "source": f"Yahoo Finance: {ticker}", "as_of": "2026-07-15",
            "chg_1d": None, "pct_1d": None, "chg_1w": None, "pct_1w": None,
            "chg_1m": None, "pct_1m": None}


def test_derived_row_spread_and_breakeven():
    a = {"current": 5.09, "prev_1d": 5.03, "prev_1w": None, "prev_1m": 4.99,
         "date": "2026-07-14"}
    b = {"current": 4.18, "prev_1d": 4.13, "prev_1w": 4.10, "prev_1m": 4.00,
         "date": "2026-07-14"}
    # spread: values and changes in bps
    row = macro_data._derived_row("2s20s Spread", a, b, unit="spread",
                                  section="rates", series_id="DERIVED:T")
    assert row["value"] == 91.0            # (5.09-4.18)*100
    assert row["chg_1d"] == 1.0            # 91 - 90
    assert row["chg_1w"] is None           # a has no 1W value
    assert row["chg_1m"] == -8.0           # 91 - 99
    # breakeven: value in %, changes as decimal diffs
    row = macro_data._derived_row("30Y Breakeven", a, b, unit="breakeven",
                                  section="rates", series_id="DERIVED:T")
    assert row["value"] == 0.91
    assert abs(row["chg_1d"] - 0.01) < 1e-9
    # missing input series -> no row
    assert macro_data._derived_row("X", None, b, unit="spread",
                                   section="rates", series_id="D") is None


def test_rates_table_renders_only_rates_rows():
    data = [_fred_row("2Y UST", "rates"), _fred_row("HY OAS", "credit", "spread", 272.0),
            _fred_row("CPI (monthly)", "prompt", "cpi", 332.6)]
    out = macro_data.build_rates_table_html(data)
    assert "Rates Snapshot" in out
    assert "2Y UST" in out
    assert "HY OAS" not in out
    assert "CPI" not in out


def test_credit_table_merges_fred_and_yahoo_rows():
    fred = [_fred_row("HY OAS", "credit", "spread", 272.0),
            _fred_row("2Y UST", "rates")]
    yahoo = [_yahoo_row("IGLB (Long-Term IG)", "credit", ticker="IGLB"),
             _yahoo_row("S&P 500", "market", ticker="^GSPC")]
    out = macro_data.build_credit_table_html(fred, yahoo)
    assert "Corporate Credit Snapshot" in out
    assert "HY OAS" in out
    assert "IGLB (Long-Term IG)" in out
    assert "ICE BofA" in out          # OAS provenance footnote
    assert "2Y UST" not in out        # rates row excluded
    assert "S&P 500" not in out       # non-credit Yahoo row excluded


def test_market_table_embeds_fred_extras():
    # jared 2026-07-16: 20Y UST appears in Market Snapshot AND Rates Snapshot
    yahoo = [_yahoo_row("S&P 500", "market", ticker="^GSPC")]
    fred = [_fred_row("20Y UST", "rates", value=5.09, series_id="DGS20"),
            _fred_row("2Y UST", "rates", series_id="DGS2")]
    out = market_data.build_market_table_html(yahoo, fred)
    assert "20Y UST" in out and "5.09%" in out
    assert "DGS20" in out            # FRED provenance in the footnote
    assert "2Y UST" not in out       # only the listed extras, not all rates
    # without fred_data the table is unchanged (no FRED row, no FRED footnote)
    plain = market_data.build_market_table_html(yahoo)
    assert "20Y UST" not in plain and "FRED" not in plain


def test_yahoo_section_tables_filter_by_section():
    data = [_yahoo_row("S&P 500", "market", ticker="^GSPC"),
            _yahoo_row("ARCC (Ares Capital)", "private", ticker="ARCC"),
            _yahoo_row("BKLN Trailing Yield", "private", unit="pct", value=6.59,
                       ticker="BKLN"),
            _yahoo_row("CoreWeave", "ai", ticker="CRWV")]
    market = market_data.build_market_table_html(data)
    private = market_data.build_private_credit_html(data)
    ai = market_data.build_ai_html(data)
    assert "Market Snapshot" in market and "ARCC" not in market
    assert "Private Credit Snapshot" in private
    assert "ARCC (Ares Capital)" in private and "6.59%" in private
    assert "CoreWeave" not in private
    assert "AI Snapshot" in ai and "CoreWeave" in ai
    # a section with no rows renders nothing at all
    assert market_data.build_ai_html([_yahoo_row("S&P 500", "market")]) == ""
