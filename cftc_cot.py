#!/usr/bin/env python3
"""
CFTC Commitments of Traders
Parses the weekly CFTC futures positioning report.
Published Fridays at 3:30 PM for positions as of Tuesday.
Best shown on Mondays in the digest.
"""

import json
import datetime
import urllib.request
from pathlib import Path

from net_utils import unverified_ssl_context
from config import FEED_USER_AGENT

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / "archive" / "cot_cache"

# CFTC data URLs
COT_FUTURES_URL = "https://www.cftc.gov/dea/newcot/deafut.txt"
COT_FINANCIAL_URL = "https://www.cftc.gov/dea/newcot/FinFutWk.txt"

# SSL context for CFTC (cert chain doesn't validate against the default store)
_SSL_CTX = unverified_ssl_context()

# Contracts to track: (name, cftc_code, source_file)
# "futures" = deafut.txt, "financial" = FinFutWk.txt
TRACKED_CONTRACTS = [
    ("WTI Crude", "067651", "futures"),
    ("Gold", "088691", "futures"),
    ("Silver", "084691", "futures"),
    ("Natural Gas", "023651", "futures"),
    ("10Y Treasury", "043602", "financial"),
    ("2Y Treasury", "042601", "financial"),
    ("30Y Treasury", "020601", "financial"),
    ("S&P 500", "13874+", "financial"),
    ("VIX", "1170E1", "financial"),
    ("US Dollar Index", "098662", "futures"),
]


def _fetch_cot(url):
    """Fetch a CFTC text file."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", FEED_USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    CFTC fetch error: {e}")
        return None


def _parse_cot_line(line):
    """Parse a single CFTC fixed-width/CSV line into fields.

    Legacy format is comma-separated with some fields quoted.
    Key column positions (0-indexed):
      0: contract name (quoted)
      1: date code (YYMMDD)
      2: report date (YYYY-MM-DD)
      3: CFTC contract code
      4: exchange
      7: open interest
      8: noncomm long
      9: noncomm short
      10: noncomm spreading
      11: comm long
      12: comm short
      ...later columns have changes from prior week
    """
    # Split by comma, handle quoted fields
    fields = []
    in_quote = False
    current = ""
    for ch in line:
        if ch == '"':
            in_quote = not in_quote
        elif ch == ',' and not in_quote:
            fields.append(current.strip())
            current = ""
        else:
            current += ch
    fields.append(current.strip())

    if len(fields) < 15:
        return None

    def _int(idx):
        try:
            return int(fields[idx].strip())
        except (ValueError, IndexError):
            return 0

    return {
        "name": fields[0].strip('" '),
        "report_date": fields[2].strip(),
        "cftc_code": fields[3].strip(),
        "open_interest": _int(7),
        "noncomm_long": _int(8),
        "noncomm_short": _int(9),
        "noncomm_spreading": _int(10),
        "comm_long": _int(11),
        "comm_short": _int(12),
    }


def _find_contract(raw_text, cftc_code):
    """Find a specific contract in the CFTC text by code.

    An exact parsed-code match anywhere in the file wins; a loose (substring)
    hit is kept only as a fallback when NO line parses to the exact code. The
    old version returned the first substring hit immediately — the code
    appearing inside another line's numeric field could hand back the wrong
    contract's row — which also made its exact-match check unreachable.
    """
    fallback = None
    for line in raw_text.split("\n"):
        if cftc_code in line:
            parsed = _parse_cot_line(line)
            if parsed is None:
                continue
            if parsed["cftc_code"].strip() == cftc_code.strip():
                return parsed
            if fallback is None:
                fallback = parsed
    return fallback


def _load_prior_week(current_report_date=None):
    """Load the newest cached week STRICTLY OLDER than the current report.

    Cache files are named <report_date>.json. The old version took the newest
    file regardless — on the 2nd/3rd run within the same report week that file
    IS the current report, so every WoW change computed as 0 instead of the
    true week-over-week move. A cache holding only the same date returns {}
    (WoW renders honestly as n/a)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_files = sorted(CACHE_DIR.glob("*.json"), reverse=True)
    if current_report_date:
        cache_files = [f for f in cache_files if f.stem < current_report_date]
    if cache_files:
        try:
            return json.loads(cache_files[0].read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_current_week(positions):
    """Cache current week's data."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    report_date = positions[0]["report_date"] if positions else datetime.date.today().isoformat()
    cache_file = CACHE_DIR / f"{report_date}.json"
    data = {p["contract"]: p for p in positions}
    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def fetch_cot_data():
    """Fetch and parse latest CFTC Commitments of Traders report."""
    # Only show on Monday-Wednesday (data released Friday, stale by Thursday)
    today = datetime.date.today()
    if today.weekday() > 2:  # Thu=3, Fri=4, Sat=5, Sun=6
        print("  CFTC COT: skipping (data best shown Mon-Wed).")
        return []

    print("  Fetching CFTC Commitments of Traders...")

    # Fetch both files
    futures_raw = _fetch_cot(COT_FUTURES_URL)
    financial_raw = _fetch_cot(COT_FINANCIAL_URL)

    if not futures_raw and not financial_raw:
        print("    Could not fetch CFTC data.")
        return []

    rows = []
    for contract_name, cftc_code, source in TRACKED_CONTRACTS:
        raw = futures_raw if source == "futures" else financial_raw
        if not raw:
            continue
        row = _find_contract(raw, cftc_code)
        if not row:
            continue
        rows.append((contract_name, row))

    # WoW baseline: the newest cached report OLDER than this one (a same-week
    # rerun otherwise compares the report to itself -> all-zero changes).
    current_report_date = rows[0][1]["report_date"] if rows else None
    prior = _load_prior_week(current_report_date)
    positions = []

    for contract_name, row in rows:
        spec_net = row["noncomm_long"] - row["noncomm_short"]

        # Prior week comparison
        prior_data = prior.get(contract_name, {})
        prior_net = prior_data.get("spec_net")
        wow_change = (spec_net - prior_net) if prior_net is not None else None

        positions.append({
            "contract": contract_name,
            "report_date": row["report_date"],
            "spec_long": row["noncomm_long"],
            "spec_short": row["noncomm_short"],
            "spec_net": spec_net,
            "spec_net_change": wow_change,
            "comm_long": row["comm_long"],
            "comm_short": row["comm_short"],
            "comm_net": row["comm_long"] - row["comm_short"],
            "open_interest": row["open_interest"],
        })

        print(f"    {contract_name}: spec net {spec_net:+,}"
              f"{f' (wow {wow_change:+,})' if wow_change is not None else ''}")

    if positions:
        _save_current_week(positions)

    print(f"  Parsed {len(positions)} contracts.")
    return positions


def format_cot_for_prompt(positions):
    if not positions:
        return ""

    report_date = positions[0].get("report_date", "")
    lines = [f"CFTC COMMITMENTS OF TRADERS (as of {report_date}):"]
    lines.append(f"  {'Contract':<20s} {'Spec Net':>12s} {'Chg (WoW)':>12s}")

    for p in positions:
        net = f"{p['spec_net']:+,}"
        chg = f"{p['spec_net_change']:+,}" if p["spec_net_change"] is not None else "n/a"
        lines.append(f"  {p['contract']:<20s} {net:>12s} {chg:>12s}")

    return "\n".join(lines)


if __name__ == "__main__":
    positions = fetch_cot_data()
    if positions:
        print("\n" + format_cot_for_prompt(positions))
    else:
        print("No COT data (may be wrong day of week).")
