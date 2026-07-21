"""Alert-evaluation prompt building — the watchlist binding (2026-07-21).

`_build_alert_prompt` is exercised directly (no Claude call) so the binding of the
trigger word "watchlist" to the real sec_filings.WATCHLIST is unit-tested for free.
"""

import alerts


_CFG = [
    {"name": "Rating downgrade",
     "trigger": "Any downgrade of a watchlist company or a fallen angel",
     "priority": "high"},
    {"name": "Bank failure", "trigger": "Any FDIC bank failure", "priority": "high"},
]


def test_alert_prompt_injects_watchlist_when_provided():
    p = alerts._build_alert_prompt(_CFG, "some source text", watchlist=["ARCC", "MSTR", "CRWV"])
    assert "WATCHLIST DEFINITION" in p
    assert "ARCC, MSTR, CRWV" in p          # exact ticker list, comma-joined
    # triggers + source still present
    assert "Rating downgrade" in p and "Bank failure" in p
    assert "some source text" in p


def test_alert_prompt_omits_watchlist_clause_when_none():
    p = alerts._build_alert_prompt(_CFG, "src")            # legacy path, no list
    assert "WATCHLIST DEFINITION" not in p
    assert "Rating downgrade" in p                          # rest of the prompt intact


def test_alert_prompt_omits_watchlist_clause_when_empty():
    p = alerts._build_alert_prompt(_CFG, "src", watchlist=[])
    assert "WATCHLIST DEFINITION" not in p
