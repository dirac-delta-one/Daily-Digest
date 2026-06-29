#!/usr/bin/env python3
"""
FINRA TRACE Bond Data
Pulls recent corporate bond trades for watchlist issuers from FINRA's TRACE system.
Uses the public FINRA TRACE API (via Morningstar's bond center).
"""

import json
import datetime
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CACHE_FILE = SCRIPT_DIR / "trace_cache.json"

USER_AGENT = "DailyDigest/1.0 (acorn.research.bot@gmail.com)"

# Map issuer tickers to their common bond identifiers
# Add CUSIPs or issuer names as needed
TRACE_WATCHLIST = [
    # (ticker, issuer_name_search_term)
    ("PGY", "Pagaya"),
    ("CRWV", "CoreWeave"),
]

# FINRA TRACE API endpoints
TRACE_SEARCH_URL = "https://finra-markets.morningstar.com/BondCenter/BondTradeActivitySearchResult.jsp"


def _make_request(url, params=None):
    """Make an HTTP request with proper headers."""
    if params:
        query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{query}"

    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"    TRACE request error: {e}")
        return None


def _load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(data):
    CACHE_FILE.write_text(json.dumps(data, indent=2))


def fetch_trace_data():
    """
    Fetch recent TRACE bond trades for watchlist issuers.

    Uses FINRA's public bond search. Note: the public API has limitations;
    for production use, consider FINRA's TRACE data API with registration.

    Returns list of bond trade summaries.
    """
    import urllib.parse

    if not TRACE_WATCHLIST:
        print("  No TRACE watchlist configured — skipping.")
        return []

    print(f"  Fetching TRACE data for {len(TRACE_WATCHLIST)} issuers...")

    results = []
    cache = _load_cache()

    for ticker, issuer_name in TRACE_WATCHLIST:
        try:
            # Use FINRA's bond search endpoint
            params = {
                "ticker": ticker,
                "startdate": (datetime.date.today() - datetime.timedelta(days=5)).strftime("%m/%d/%Y"),
                "enddate": datetime.date.today().strftime("%m/%d/%Y"),
            }

            url = "https://finra-markets.morningstar.com/BondCenter/BondTradeActivitySearchResult.jsp"
            query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
            full_url = f"{url}?{query}"

            req = urllib.request.Request(full_url)
            req.add_header("User-Agent", USER_AGENT)

            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
            except Exception as e:
                print(f"    {ticker}: TRACE fetch failed — {e}")
                continue

            # Try to parse as JSON
            try:
                data = json.loads(raw)
                if isinstance(data, dict) and "rows" in data:
                    for row in data["rows"][:5]:  # Top 5 most recent
                        results.append({
                            "ticker": ticker,
                            "issuer": issuer_name,
                            "cusip": row.get("cusip", ""),
                            "coupon": row.get("coupon", ""),
                            "maturity": row.get("maturityDate", ""),
                            "price": row.get("lastSalePrice", ""),
                            "yield": row.get("lastSaleYield", ""),
                            "volume": row.get("totalVolume", ""),
                            "trade_date": row.get("tradeDate", ""),
                        })
                        print(f"    {ticker}: found bond trade data")
            except json.JSONDecodeError:
                # HTML response — try basic parsing
                # The public endpoint may return HTML instead of JSON
                if "No results found" in raw or "no records" in raw.lower():
                    print(f"    {ticker}: no TRACE data found")
                else:
                    print(f"    {ticker}: TRACE returned non-JSON response (may need API registration)")

        except Exception as e:
            print(f"    {ticker}: TRACE error — {e}")

    # Update cache
    if results:
        cache["last_fetch"] = str(datetime.date.today())
        cache["data"] = results
        _save_cache(cache)

    print(f"  Got {len(results)} TRACE bond records.")
    return results


def format_trace_for_prompt(data):
    """Format TRACE data as plain text for the Opus prompt."""
    if not data:
        return ""

    lines = ["FINRA TRACE BOND DATA (recent trades):"]
    for d in data:
        parts = [f"${d['ticker']}"]
        if d.get("coupon"):
            parts.append(f"{d['coupon']}%")
        if d.get("maturity"):
            parts.append(f"due {d['maturity']}")
        if d.get("price"):
            parts.append(f"last: {d['price']}")
        if d.get("yield"):
            parts.append(f"yield: {d['yield']}%")
        if d.get("volume"):
            parts.append(f"vol: {d['volume']}")
        lines.append(f"  {' | '.join(parts)}")

    return "\n".join(lines)


def build_trace_html(data):
    """Render TRACE data as an HTML section."""
    if not data:
        return ""

    rows = ""
    for d in data:
        desc = f"{d.get('coupon', '?')}% due {d.get('maturity', '?')}"
        price = d.get("price", "—")
        yld = d.get("yield", "—")
        vol = d.get("volume", "—")

        rows += (
            f'<li style="margin-bottom: 8px; font-size: 14px;">'
            f'<strong>${d["ticker"]}</strong> {desc}: '
            f'last traded at {price}'
        )
        if yld and yld != "—":
            rows += f', yield {yld}%'
        if vol and vol != "—":
            rows += f', ${vol} volume'
        rows += '</li>\n'

    html = (
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; '
        'padding-bottom: 6px; margin: 28px 0 12px;">FINRA TRACE Bond Activity</h2>\n'
        f'<ul style="padding-left: 20px; margin: 0;">\n{rows}</ul>\n'
    )

    return html


if __name__ == "__main__":
    data = fetch_trace_data()
    if data:
        print(format_trace_for_prompt(data))
    else:
        print("No TRACE data fetched.")
