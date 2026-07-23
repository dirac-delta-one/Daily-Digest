#!/usr/bin/env python3
"""
Cliffwater BDC Index (CWBDC) — the Private Credit Snapshot's BDC-index row
(SNAPSHOT_UPDATE §4 row 3; jared approved the Cliffwater substitution
2026-07-23 — the S&P BDC index he originally named, SPBDCUP, has no free
source; CWBDC is a different, cap-weighted index of listed BDCs and is
labeled as Cliffwater in the table, never as S&P).

Source: bdcs.com's own chart data file (/docs/bdcs/ChartData.json — the same
static JSON the site's charts load; full daily history back to 2004,
published T-1, no key or registration). The file also carries CWBDC_Yield
and PremDis (premium/discount to NAV) should more rows ever be wanted.

Returns a market_data-shaped row so it renders in the Private Credit table
and rides the digest prompt with the other market rows. Empty list on any
failure (try/except-everywhere convention; the O3 monitor flags a
zero-streak if the file moves)."""

import datetime
import json
import urllib.request

from net_utils import unverified_ssl_context
from config import FEED_USER_AGENT

DATA_URL = "https://www.bdcs.com/docs/bdcs/ChartData.json"
_SSL_CTX = unverified_ssl_context()


def _fetch_chart_json():
    req = urllib.request.Request(DATA_URL)
    req.add_header("User-Agent", FEED_USER_AGENT)
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_cliffwater_bdc():
    """[row] for the Cliffwater BDC total-return index, or [] on failure."""
    print("  Fetching Cliffwater BDC index...")
    try:
        data = _fetch_chart_json()
        pts = [(d, float(v)) for d, v in zip(data.get("x") or [],
                                             data.get("CWBDC") or [])
               if d and v is not None]
        if not pts:
            print("    No CWBDC observations — skipped.")
            return []
    except Exception as e:
        print(f"    Cliffwater fetch failed ({e}) — skipped.")
        return []

    pts.sort()
    as_of, current = pts[-1]

    def _at_or_before(target_iso):
        prior = [v for d, v in pts if d <= target_iso]
        return prior[-1] if prior else None

    ref = datetime.date.fromisoformat(as_of)
    prev_1d = pts[-2][1] if len(pts) >= 2 else None
    prev_1w = _at_or_before((ref - datetime.timedelta(days=7)).isoformat())
    prev_1m = _at_or_before((ref - datetime.timedelta(days=30)).isoformat())

    def _calc(prev):
        if prev is None or prev == 0:
            return None, None
        return current - prev, (current - prev) / abs(prev) * 100

    chg_1d, pct_1d = _calc(prev_1d)
    chg_1w, pct_1w = _calc(prev_1w)
    chg_1m, pct_1m = _calc(prev_1m)

    print(f"    CWBDC {current:,.2f} as of {as_of}.")
    return [{
        "label": "Cliffwater BDC Index",
        "value": current,
        "unit": "index",
        "section": "private",
        "metric": "Total return index",
        "chg_1d": chg_1d, "pct_1d": pct_1d,
        "chg_1w": chg_1w, "pct_1w": pct_1w,
        "chg_1m": chg_1m, "pct_1m": pct_1m,
        "source": "Cliffwater (bdcs.com)",
        "as_of": as_of,
    }]


if __name__ == "__main__":
    for row in fetch_cliffwater_bdc():
        print(row)
