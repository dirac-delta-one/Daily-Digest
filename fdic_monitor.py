#!/usr/bin/env python3
"""
FDIC Failed Bank Monitor
Checks for recent bank failures via the FDIC API.
Rare events but critical to know about immediately.
"""

import json
import datetime
import urllib.request

FDIC_API = "https://banks.data.fdic.gov/api/failures?sort_by=FAILDATE&sort_order=DESC&limit=5"
LOOKBACK_DAYS = 30  # wider window since failures are rare


def _fetch_json(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "DailyDigest/1.0")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"    FDIC API error: {e}")
        return None


def _parse_fdic_date(date_str):
    """Parse FDIC date formats."""
    if not date_str:
        return None
    for fmt in ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def fetch_failed_banks():
    """Check for recent bank failures."""
    print("  Checking FDIC for bank failures...")

    data = _fetch_json(FDIC_API)
    if not data:
        print("    No FDIC data returned.")
        return []

    cutoff = datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)

    # The API response structure can vary — handle both formats
    records = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(records, dict) and "data" in records:
        records = records["data"]
    if not isinstance(records, list):
        print(f"    Unexpected FDIC response format.")
        return []

    failures = []
    for record in records:
        # Handle nested 'data' field
        rec = record.get("data", record) if isinstance(record, dict) else record

        fail_date_str = rec.get("FAILDATE", rec.get("faildate", ""))
        fail_date = _parse_fdic_date(fail_date_str)

        if fail_date and fail_date < cutoff:
            continue

        bank_name = rec.get("NAME", rec.get("name", ""))
        if not bank_name:
            continue

        total_assets = rec.get("TOTALASSETS", rec.get("totalassets", 0))
        total_deposits = rec.get("TOTALDEP", rec.get("totaldep", 0))

        # Convert from thousands if needed
        try:
            total_assets = float(total_assets) if total_assets else 0
            total_deposits = float(total_deposits) if total_deposits else 0
        except (ValueError, TypeError):
            total_assets = 0
            total_deposits = 0

        failures.append({
            "bank_name": bank_name,
            "city": rec.get("CITY", rec.get("city", "")),
            "state": rec.get("STNAME", rec.get("stname", "")),
            "cert": rec.get("CERT", rec.get("cert", "")),
            "acquiring_bank": rec.get("ACQUIRER", rec.get("acquirer", "")),
            "fail_date": str(fail_date) if fail_date else fail_date_str,
            "total_assets": total_assets,
            "total_deposits": total_deposits,
        })

    if failures:
        for f in failures:
            assets_str = f"${f['total_assets']/1000:.1f}B" if f['total_assets'] > 1000 else f"${f['total_assets']:.0f}M"
            print(f"    BANK FAILURE: {f['bank_name']} ({f['state']}) — {assets_str} assets — {f['fail_date']}")
    else:
        print("    No recent bank failures.")

    return failures


def format_fdic_for_prompt(failures):
    if not failures:
        return ""

    lines = ["FDIC BANK FAILURES (last 30 days):"]
    for f in failures:
        assets_str = f"${f['total_assets']/1000:.1f}B" if f['total_assets'] > 1000 else f"${f['total_assets']:.0f}M"
        lines.append(
            f"  {f['bank_name']} ({f['city']}, {f['state']}) — "
            f"Failed {f['fail_date']} — {assets_str} total assets"
        )
        if f.get("acquiring_bank"):
            lines.append(f"    Acquired by: {f['acquiring_bank']}")
    return "\n".join(lines)


if __name__ == "__main__":
    failures = fetch_failed_banks()
    if failures:
        print(format_fdic_for_prompt(failures))
    else:
        print("No recent bank failures.")
