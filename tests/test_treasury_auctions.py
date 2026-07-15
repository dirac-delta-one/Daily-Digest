"""Stage 2.2 — treasury_auctions prompt formatting: honest lookback label +
None-yield guard (a non-numeric high_investment_rate parsed to None and crashed
the f-string, silently losing the whole section via the registry try/except)."""

import treasury_auctions as ta


def _auction(**over):
    a = {"security_type": "Note", "security_term": "10-Year",
         "auction_date": "2026-07-09", "high_yield": 4.5, "median_yield": 4.45,
         "tail_bps": 5.0, "bid_to_cover": 2.5, "indirect_pct": 60.0,
         "direct_pct": 20.0, "primary_dealer_pct": 20.0,
         "total_accepted_mm": 40000}
    a.update(over)
    return a


def test_prompt_header_reflects_actual_lookback():
    out = ta.format_auctions_for_prompt([_auction()])
    assert f"last {ta.HOURS_LOOKBACK}h" in out


def test_prompt_formats_normal_yield():
    out = ta.format_auctions_for_prompt([_auction()])
    assert "4.500% yield" in out
    assert "bid-to-cover 2.50x" in out
    assert "tail +5.0bps" in out


def test_prompt_survives_none_yield():
    out = ta.format_auctions_for_prompt([_auction(high_yield=None, tail_bps=None)])
    assert "yield n/a" in out
