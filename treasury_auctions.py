#!/usr/bin/env python3
"""
Treasury Auction Results
Fetches recent auction results from Treasury Fiscal Data API.
Shows bid-to-cover, yield, tail, and bidder breakdown.
"""

import json
import datetime
import urllib.request

from net_utils import unverified_ssl_context
from config import FEED_USER_AGENT

HOURS_LOOKBACK = 24

API_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
    "v1/accounting/od/auctions_query"
    "?sort=-auction_date"
    "&page[size]=25"
    "&filter=auction_date:gte:{start_date},high_investment_rate:gt:0"
)

# SSL context for Treasury (cert chain doesn't validate against the default store)
_SSL_CTX = unverified_ssl_context()


def _fetch_json(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", FEED_USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"    Treasury API error: {e}")
        return None


def fetch_treasury_auctions():
    """Fetch recent Treasury auction results."""
    print("  Fetching Treasury auction results...")

    start = (datetime.datetime.now() - datetime.timedelta(hours=HOURS_LOOKBACK)).strftime("%Y-%m-%d")
    url = API_URL.format(start_date=start)

    data = _fetch_json(url)
    if not data or not data.get("data"):
        print("    No auction data returned.")
        return []

    auctions = []
    for rec in data["data"]:
        high_yield = rec.get("high_investment_rate", "")
        if not high_yield:
            continue  # skip unresolved auctions

        # Parse numbers safely
        def _num(val):
            try:
                return float(val) if val else None
            except (ValueError, TypeError):
                return None

        high = _num(high_yield)
        median = _num(rec.get("avg_med_investment_rate"))
        btc = _num(rec.get("bid_to_cover_ratio"))
        total_accepted = _num(rec.get("total_accepted"))
        total_tendered = _num(rec.get("total_tendered"))
        indirect = _num(rec.get("indirect_bidder_accepted"))
        direct = _num(rec.get("direct_bidder_accepted"))
        primary = _num(rec.get("primary_dealer_accepted"))

        # Compute percentages if we have the raw numbers
        indirect_pct = None
        direct_pct = None
        primary_pct = None
        if total_accepted and total_accepted > 0:
            if indirect:
                indirect_pct = (indirect / total_accepted) * 100
            if direct:
                direct_pct = (direct / total_accepted) * 100
            if primary:
                primary_pct = (primary / total_accepted) * 100

        # Compute tail
        tail = None
        if high is not None and median is not None:
            tail = round((high - median) * 100, 1)  # in bps

        # Compute BTC from raw if not provided
        if btc is None and total_accepted and total_tendered and total_accepted > 0:
            btc = round(total_tendered / total_accepted, 2)

        auctions.append({
            "security_type": rec.get("security_type", ""),
            "security_term": rec.get("original_security_term", rec.get("security_term", "")),
            "auction_date": rec.get("auction_date", ""),
            "high_yield": high,
            "median_yield": median,
            "tail_bps": tail,
            "bid_to_cover": btc,
            "indirect_pct": indirect_pct,
            "direct_pct": direct_pct,
            "primary_dealer_pct": primary_pct,
            "total_accepted_mm": round(total_accepted / 1_000_000, 0) if total_accepted else None,
        })

    # Deduplicate by auction_date + security_term (API can return duplicates)
    seen = set()
    deduped = []
    for a in auctions:
        key = f"{a['auction_date']}_{a['security_term']}"
        if key not in seen:
            seen.add(key)
            deduped.append(a)

    # Filter to interesting auctions (Notes, Bonds, TIPS — skip Bills)
    notes_bonds = [a for a in deduped if a["security_type"] in ("Note", "Bond", "TIPS", "FRN")]
    bills = [a for a in deduped if a["security_type"] == "Bill"]

    # Show notes/bonds first, then up to 3 bills
    result = notes_bonds + bills[:3]

    print(f"  Found {len(result)} recent auctions ({len(notes_bonds)} notes/bonds, {len(bills)} bills).")
    return result


def format_auctions_for_prompt(auctions):
    if not auctions:
        return ""

    lines = [f"TREASURY AUCTIONS (last {HOURS_LOOKBACK}h):"]
    for a in auctions:
        term = a["security_term"]
        atype = a["security_type"]
        date = a["auction_date"]
        yld = a["high_yield"]
        btc = a["bid_to_cover"]
        tail = a["tail_bps"]

        yld_str = f"{yld:.3f}% yield" if yld is not None else "yield n/a"
        line = f"  {term} {atype} ({date}): {yld_str}"
        if btc:
            line += f", bid-to-cover {btc:.2f}x"
        if tail is not None:
            line += f", tail {tail:+.1f}bps"
        lines.append(line)

        parts = []
        if a["indirect_pct"] is not None:
            parts.append(f"Indirect: {a['indirect_pct']:.1f}%")
        if a["direct_pct"] is not None:
            parts.append(f"Direct: {a['direct_pct']:.1f}%")
        if a["primary_dealer_pct"] is not None:
            parts.append(f"Primary Dealers: {a['primary_dealer_pct']:.1f}%")
        if parts:
            lines.append(f"    {', '.join(parts)}")

    return "\n".join(lines)


# build_auctions_table_html removed 2026-07-15 (jared's snapshot redesign):
# the Treasury Auctions table no longer renders in the digest. The auction
# data still feeds the Opus prompt via format_auctions_for_prompt above.


if __name__ == "__main__":
    auctions = fetch_treasury_auctions()
    if auctions:
        print(format_auctions_for_prompt(auctions))
    else:
        print("No recent auctions.")
