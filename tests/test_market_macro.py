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

def _fred_row(label, section, unit="rate", value=4.5, series_id="X", metric="Yield"):
    return {"label": label, "unit": unit, "section": section, "value": value,
            "series_id": series_id, "date": "2026-07-15", "metric": metric,
            "chg_1d": None, "chg_1w": None, "chg_1m": None}


def _yahoo_row(label, section, unit="dollar", value=50.0, ticker="TICK", metric="Price"):
    return {"label": label, "unit": unit, "section": section, "value": value,
            "source": f"Yahoo Finance: {ticker}", "as_of": "2026-07-15", "metric": metric,
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
    fred = [_fred_row("HY", "credit", "spread", 272.0, metric="Index OAS"),
            _fred_row("2Y UST", "rates")]
    yahoo = [_yahoo_row("IGLB (Long-Term IG)", "credit", ticker="IGLB",
                        metric="ETF price"),
             _yahoo_row("S&P 500", "market", ticker="^GSPC")]
    out = macro_data.build_credit_table_html(fred, yahoo)
    assert "Corporate Credit Snapshot" in out
    assert "Index OAS" in out         # metric column populated
    assert "IGLB (Long-Term IG)" in out and "ETF price" in out
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
    assert "Source: Yahoo Finance" in out   # minimal single-source footnote
    assert "FRED" in out                     # FRED noted as a co-source (no id list)
    assert "^GSPC" not in out                # raw tickers no longer enumerated
    assert "2Y UST<" not in out      # only the listed extras (DGS20), not DGS2
    assert "ishares.com" not in out  # no iShares extras -> no fund-reported note
    # without fred_data: no FRED co-source in the footnote
    plain = market_data.build_market_table_html(yahoo)
    assert "20Y UST" not in plain and "FRED" not in plain


def test_market_table_cites_ishares_mirror_rows():
    # 2026-07-22: the iShares Portfolio OAS mirror rows are ishares.com data,
    # not FRED — the footnote must carry the fund-reported note, and "FRED"
    # only when a real FRED extra (DGS20) is present. (Exercised with LQD;
    # HYG shares the identical mirror path.)
    yahoo = [_yahoo_row("S&P 500", "market", ticker="^GSPC")]
    ishares = [_fred_row("LQD (iBoxx IG)", "credit", unit="spread", value=83.0,
                         series_id="ISHARES:LQD", metric="Portfolio OAS")]
    fred = [_fred_row("20Y UST", "rates", value=5.09, series_id="DGS20")]

    both = market_data.build_market_table_html(yahoo, fred + ishares)
    assert "LQD (iBoxx IG)" in both and "83 bps" in both
    assert "FRED" in both
    assert "Portfolio OAS rows = fund-reported (ishares.com)" in both
    # sources before the as-of date, definition note trailing after it
    assert both.index("FRED") < both.index("as of") < both.index("ishares.com")

    # iShares-only extras (DGS20 failed): no spurious FRED co-source
    ishares_only = market_data.build_market_table_html(yahoo, ishares)
    assert "fund-reported (ishares.com)" in ishares_only
    assert "FRED" not in ishares_only


def test_change_cell_rounds_to_zero_renders_unch():
    # 2026-07-27: a change that rounds to zero at display precision must show a
    # grey "unch", not "+0"/"-0.0%" with an up/down color.
    import config

    # shared helper: no nonzero digit -> unch (grey), regardless of the color arg
    for zero_text in ("+0 bps", "-0 bps", "+0.0%", "-0.0%", "+$0.00 / -0.0%", "+0.00 / +0.0%"):
        out = config.change_cell_html(zero_text, "#27ae60")
        assert "unch" in out and "#999" in out
        assert "#27ae60" not in out and zero_text not in out
    # a real magnitude renders normally, signed + colored
    out = config.change_cell_html("+31 bps", "#c0392b")
    assert "+31 bps" in out and "#c0392b" in out and "unch" not in out

    # macro bps formatter: a sub-half-bp positive move rounds to "+0 bps" -> unch
    # (previously showed "+0 bps" in green because the raw sign was positive)
    assert "unch" in macro_data._fmt_change_cell(0.002, "rate", "10Y")   # 0.2 bps
    assert "unch" in macro_data._fmt_change_cell(0.0, "spread", "HY")     # exactly 0
    assert "+10 bps" in macro_data._fmt_change_cell(0.10, "rate", "10Y")  # real move stays

    # market formatter: tiny $/% that both round to zero -> unch; a real move stays
    assert "unch" in market_data._fmt_change_cell(0.003, 0.002, "index", "DXY")
    assert "unch" not in market_data._fmt_change_cell(-0.60, -3.1, "dollar", "ARCC")
    # missing data stays an em-dash, NOT "unch" (no-data vs ~zero)
    dash = market_data._fmt_change_cell(None, None, "dollar", "ARCC")
    assert "—" in dash and "unch" not in dash


def test_bkln_yield_accrual_cache(tmp_path, monkeypatch):
    # 2026-07-27: BKLN's 12M dist. yield has no Yahoo time series, so 1D/1W/1M
    # come from a local accrual cache keyed on run date (like ishares OAS).
    import json
    import datetime
    monkeypatch.setattr(market_data, "BKLN_YIELD_CACHE", tmp_path / "bkln.json")

    # First ever run: no history -> all None, but today's value is recorded.
    d1 = datetime.date(2026, 7, 24)
    assert market_data._bkln_yield_changes(6.56, today=d1) == (None, None, None)
    assert json.loads((tmp_path / "bkln.json").read_text())["2026-07-24"] == 6.56

    # Next run: 1D is now computable (pp difference); 1W/1M not yet accrued.
    d2 = datetime.date(2026, 7, 25)
    chg_1d, chg_1w, chg_1m = market_data._bkln_yield_changes(6.59, today=d2)
    assert round(chg_1d, 2) == 0.03 and chg_1w is None and chg_1m is None

    # The pp change renders in bps in the private-credit change cell.
    assert "+3 bps" in market_data._fmt_change_cell(0.03, None, "pct", "BKLN")
    # a sub-half-bp yield wobble still collapses to unch (shared rule)
    assert "unch" in market_data._fmt_change_cell(0.002, None, "pct", "BKLN")


def test_market_table_footnote_enumerates_extras_dates():
    # 2026-07-24: the as-of footnote only saw the section's Yahoo rows — the
    # mirrored 20Y UST/HYG extras' older dates were never enumerated (their
    # row-level * markers were honest, the date list wasn't).
    yahoo = [_yahoo_row("S&P 500", "market", ticker="^GSPC"),
             _yahoo_row("VIX", "market", unit="index", value=18.9,
                        ticker="^VIX", metric="Index")]
    fred = [_fred_row("20Y UST", "rates", value=5.09, series_id="DGS20")]
    fred[0]["date"] = "2026-07-14"
    out = market_data.build_market_table_html(yahoo, fred)
    assert "as of 2026-07-15" in out          # Yahoo majority date leads
    assert "20Y UST: 2026-07-14" in out       # mirror-row outlier enumerated


def test_market_prompt_carries_row_dates():
    # 2026-07-24: §1 called SK Hynix's 7/24 Seoul close "Thursday" — the
    # prompt rows carried no dates for the model to frame moves against.
    row = _yahoo_row("SK Hynix", "ai", unit="won", value=1759000.0,
                     ticker="000660.KS", metric="Share price (KRW)")
    out = market_data.format_market_data_for_prompt([row])
    assert "as of 2026-07-15" in out
    # rows without a date (e.g. the BKLN yield row) get no fragment
    row_undated = dict(row, as_of="")
    out2 = market_data.format_market_data_for_prompt([row_undated])
    assert "as of" not in out2


def test_market_prompt_survives_pct_none_changes():
    # 2026-07-29 crash: the BKLN 12M-yield row carries percentage-POINT
    # changes with pct_1d/1w/1m = None (deliberate — no "% of %"), and the
    # prompt formatter's unconditional `({pct:+.1f}%)` blew up the run the
    # first morning the accrual cache produced a 1D value. pct-unit changes
    # render in bps, matching the table cell.
    bkln = dict(_yahoo_row("BKLN", "private", unit="pct", value=6.59,
                           ticker="BKLN", metric="12M dist. yield"),
                as_of="", chg_1d=0.03, chg_1w=-0.12, chg_1m=None)
    out = market_data.format_market_data_for_prompt([bkln])
    assert "BKLN 12M dist. yield: 6.59%" in out
    assert "1D: +3 bps" in out
    assert "1W: -12 bps" in out
    assert "1M:" not in out                     # None chg still omitted

    # non-pct rows with a pct keep the old rendering exactly
    spx = dict(_yahoo_row("S&P 500", "market", ticker="^GSPC"),
               chg_1d=12.5, pct_1d=0.9)
    out2 = market_data.format_market_data_for_prompt([spx])
    assert "1D: +12.50 (+0.9%)" in out2

    # defensive: a non-pct row missing its pct renders the bare change
    odd = dict(_yahoo_row("VIX", "market", unit="index", value=18.9,
                          ticker="^VIX", metric="Index"), chg_1d=-0.42)
    out3 = market_data.format_market_data_for_prompt([odd])
    assert "1D: -0.42" in out3


def test_yahoo_section_tables_filter_by_section():
    data = [_yahoo_row("S&P 500", "market", ticker="^GSPC"),
            _yahoo_row("ARCC (Ares Capital)", "private", ticker="ARCC",
                       metric="Share price"),
            _yahoo_row("BKLN", "private", unit="pct", value=6.59,
                       ticker="BKLN", metric="12M dist. yield"),
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
