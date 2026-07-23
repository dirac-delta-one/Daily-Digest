#!/usr/bin/env python3
"""
iShares fund-reported Portfolio OAS for the IG bond ETFs in the Corporate
Credit Snapshot (jared 2026-07-16: wanted G-spread for IGLB/IGIB — no free
source exists for ETF G-spreads, so this fetches the Option Adjusted Spread
each fund publishes on its own ishares.com product page instead).

The page embeds portfolio characteristics as HTML-escaped JSON; the OAS block
looks like (unescaped):
    "label":"Option Adjusted Spread","formattedValue":"94.54 bps",...
    "formattedAsOfDate":"Jul 15, 2026","name":"optionAdjustedSpread"

The site shows only the CURRENT value, so 1D/1W/1M changes come from a local
history cache (`ishares_oas_cache.json`) that accrues one observation per
site as-of date: 1D appears from the 2nd distinct day, 1W after a week, 1M
after a month. Rows are macro_data-shaped (unit "spread", value in bps,
section "credit") so the credit table renders them like the FRED OAS rows.
"""

import datetime
import html
import json
import re
import urllib.request
from pathlib import Path

from config import FEED_USER_AGENT

CACHE_PATH = Path(__file__).parent / "ishares_oas_cache.json"
CACHE_KEEP_DAYS = 60

# ticker -> (product page URL, row label)
# HYG/LQD added 2026-07-16 (operator: both the credit table AND a Market
# Snapshot mirror — see digest.py / market_data.MARKET_FRED_EXTRAS).
FUNDS = {
    "HYG":  ("https://www.ishares.com/us/products/239565/"
             "ishares-iboxx-high-yield-corporate-bond-etf",
             "HYG (iBoxx HY)"),
    "LQD":  ("https://www.ishares.com/us/products/239566/"
             "ishares-iboxx-investment-grade-corporate-bond-etf",
             "LQD (iBoxx IG)"),
    "IGLB": ("https://www.ishares.com/us/products/239423/"
             "ishares-10-year-credit-bond-etf",
             "IGLB (Long-Term IG)"),
    "IGIB": ("https://www.ishares.com/us/products/239463/"
             "ishares-intermediate-credit-bond-etf",
             "IGIB (Intermediate IG)"),
}

# Matches the unescaped characteristics JSON; non-greedy window keeps the
# value, its as-of date, and the field name bound to the same block.
_OAS_RE = re.compile(
    r'"label":"Option Adjusted Spread","formattedValue":"([\d.]+)\s*bps"'
    r'.*?"formattedAsOfDate":"([^"]+)"\s*,\s*"name":"optionAdjustedSpread"',
    re.DOTALL,
)


def _parse_oas(page_html):
    """(oas_bps: float, as_of: 'YYYY-MM-DD') from a product page, or None."""
    m = _OAS_RE.search(html.unescape(page_html))
    if not m:
        return None
    oas = float(m.group(1))
    try:
        as_of = datetime.datetime.strptime(m.group(2).strip(), "%b %d, %Y").date().isoformat()
    except ValueError:
        as_of = datetime.date.today().isoformat()
    return oas, as_of


def _load_cache():
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache):
    try:
        CACHE_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"  iShares OAS cache write failed: {e}")


def _changes_from_history(history, as_of, value):
    """(chg_1d, chg_1w, chg_1m) in bps vs the accrued history — the newest
    PRIOR observation for 1D, the closest at/before -7d / -30d for 1W/1M.
    None where history hasn't accrued yet (the site has no time series)."""
    ref = datetime.date.fromisoformat(as_of)
    dated = sorted((datetime.date.fromisoformat(d), v)
                   for d, v in history.items()
                   if d < as_of)
    if not dated:
        return None, None, None

    chg_1d = value - dated[-1][1]

    def _at_or_before(target):
        prior = [v for d, v in dated if d <= target]
        return (value - prior[-1]) if prior else None

    return (round(chg_1d, 2),
            _at_or_before(ref - datetime.timedelta(days=7)),
            _at_or_before(ref - datetime.timedelta(days=30)))


def fetch_ishares_oas():
    """Fetch fund-reported OAS rows for the credit snapshot (macro-shaped)."""
    print("  Fetching iShares fund-reported OAS...")
    cache = _load_cache()
    results = []

    for ticker, (url, label) in FUNDS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": FEED_USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                parsed = _parse_oas(resp.read().decode("utf-8", errors="replace"))
            if not parsed:
                print(f"    {ticker}: OAS field not found on the page — skipped.")
                continue
            oas, as_of = parsed

            history = cache.setdefault(ticker, {})
            chg_1d, chg_1w, chg_1m = _changes_from_history(history, as_of, oas)
            history[as_of] = oas

            results.append({
                "series_id": f"ISHARES:{ticker}",
                "label": label,
                "unit": "spread",       # value already in bps (macro-style row)
                "section": "credit",
                "metric": "Portfolio OAS",
                "value": oas,
                "date": as_of,
                "source": "ishares.com",
                "chg_1d": chg_1d,
                "chg_1w": chg_1w,
                "chg_1m": chg_1m,
            })
        except Exception as e:
            print(f"    {ticker}: iShares fetch failed ({e}) — skipped.")

    # Prune history beyond the keep window
    floor = (datetime.date.today() - datetime.timedelta(days=CACHE_KEEP_DAYS)).isoformat()
    for ticker in list(cache):
        cache[ticker] = {d: v for d, v in cache[ticker].items() if d >= floor}
    _save_cache(cache)

    print(f"  Got {len(results)} iShares OAS reading(s).")
    return results


def format_ishares_for_prompt(rows):
    if not rows:
        return ""
    lines = ["ISHARES FUND-REPORTED PORTFOLIO OAS (from ishares.com, bps over Treasuries):"]
    for r in rows:
        parts = [f"{r['label']} Portfolio OAS: {r['value']:.0f} bps (as of {r['date']})"]
        for key, tag in (("chg_1d", "1D"), ("chg_1w", "1W"), ("chg_1m", "1M")):
            if r.get(key) is not None:
                parts.append(f"{tag}: {r[key]:+.0f} bps")
        lines.append("  " + " | ".join(parts))
    return "\n".join(lines)


if __name__ == "__main__":
    data = fetch_ishares_oas()
    if data:
        print(format_ishares_for_prompt(data))
    else:
        print("No iShares OAS data fetched.")
