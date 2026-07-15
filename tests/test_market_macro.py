"""Phase 3.4 — pin the market/macro formatting + unit-conversion math."""

import market_data
import macro_data


def test_market_fmt_value():
    assert market_data._fmt_value("S&P 500", 5123.4, "dollar") == "$5,123"
    assert market_data._fmt_value("WTI Crude", 80.5, "dollar") == "$80.50"
    assert market_data._fmt_value("BTC", 65000.0, "dollar") == "$65,000"
    assert market_data._fmt_value("VIX", 14.23, "index") == "14.23"


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
