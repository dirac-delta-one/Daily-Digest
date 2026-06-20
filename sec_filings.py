#!/usr/bin/env python3
"""
SEC EDGAR Filings Monitor
Fetches recent SEC filings for a whitelist of tickers/companies.

Uses the public EDGAR API — no authentication required.
SEC requires a User-Agent header with contact info.
"""

import json
import re
import datetime
import time
import urllib.request
import urllib.error
import html as html_module
from html_utils import HTMLStripper

# --- Configuration ---
HOURS_LOOKBACK = 24

# How much content to grab from each filing
CONTENT_CHARS_8K = 5000     # 8-Ks are the most important — grab more
CONTENT_CHARS_DEFAULT = 3000  # everything else

# Your contact info (SEC requires this in the User-Agent header)
EDGAR_USER_AGENT = "DailyDigest/1.0 (jtramontano@acorninv.com)"

# ======================================================================
# LIST YOUR TICKERS TO MONITOR HERE
# ======================================================================
WATCHLIST = [
    "PGY",   # Pagaya Technologies
    "CRWV",  # CoreWeave
    "WOLF",  # Wolfspeed
    "MSTR",  # MicroStrategy
    "TRTX",  # TPG RE Finance Trust
    "LADR",  # Ladder Capital
    "OSG",   # Overseas Shipholding Group
    "FSK",   # FS KKR Capital
    "OBDC",  # Blue Owl Capital (Owl Rock)
    "RWT",   # Redwood Trust
    "ABR",   # Arbor Realty Trust
    "GBDC",  # Golub Capital BDC
    "MAIN",  # Main Street Capital
    "TSLX",  # Sixth Street Specialty Lending
    "ARCC",  # Ares Capital
    "APLD",  # Applied Digital
]

# Filing types you care about (empty = all types)
# Common types: 10-K, 10-Q, 8-K, 4, SC 13D, SC 13G, S-1, DEF 14A, 13F-HR
FILING_TYPES_OF_INTEREST = [
    "10-K", "10-Q", "8-K", "4", "S-1", "S-3",
    "SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A",
    "DEF 14A", "13F-HR", "13F-HR/A",
]

# CIK cache
_cik_map = None


def _make_request(url):
    """Make an HTTP request to EDGAR with required headers."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", EDGAR_USER_AGENT)
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"    EDGAR HTTP error {e.code} for {url}")
        return None
    except Exception as e:
        print(f"    EDGAR request error: {e}")
        return None


def _fetch_filing_content(filing_url, form_type):
    """Fetch the actual filing document and extract text content."""
    if not filing_url:
        return ""

    # Skip non-HTML filings (PDFs, etc.)
    if filing_url.lower().endswith(('.pdf', '.jpg', '.png', '.gif')):
        return "[PDF filing — content not extracted]"

    req = urllib.request.Request(filing_url)
    req.add_header("User-Agent", EDGAR_USER_AGENT)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get("Content-Type", "")

            # Only process HTML/XML/text
            if not any(t in content_type.lower() for t in ("html", "xml", "text")):
                return "[Binary filing — content not extracted]"

            raw = resp.read(500_000)  # cap at 500KB to avoid huge filings
            html_text = raw.decode("utf-8", errors="replace")

    except Exception as e:
        return f"[Could not fetch filing: {e}]"

    # Strip HTML to get readable text
    stripper = HTMLStripper()
    try:
        stripper.feed(html_text)
        text = stripper.get_text()
    except Exception:
        # Fallback: regex strip
        text = re.sub(r'<[^>]+>', ' ', html_text)
        text = html_module.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()

    if not text or len(text) < 50:
        return "[Filing content appears empty]"

    # Skip boilerplate SEC header — real content usually starts after "ITEM"
    # for 8-Ks, or after the first few lines for other forms
    if form_type in ("8-K", "8-K/A"):
        # Try to find where the real content starts
        item_match = re.search(r'(?i)(ITEM\s+\d)', text)
        if item_match:
            text = text[item_match.start():]

    # Truncate based on form type
    max_chars = CONTENT_CHARS_8K if "8-K" in form_type else CONTENT_CHARS_DEFAULT
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[...truncated]"

    return text


def _load_cik_map():
    """Load the SEC's ticker → CIK mapping."""
    global _cik_map
    if _cik_map is not None:
        return _cik_map

    print("  Loading SEC ticker -> CIK mapping...")
    url = "https://www.sec.gov/files/company_tickers.json"
    data = _make_request(url)

    if not data:
        print("  WARNING: Could not load CIK mapping from SEC.")
        _cik_map = {}
        return _cik_map

    # Build a ticker → CIK dict
    _cik_map = {}
    for entry in data.values():
        ticker = entry.get("ticker", "").upper()
        cik = entry.get("cik_str", "")
        name = entry.get("title", "")
        if ticker and cik:
            _cik_map[ticker] = {
                "cik": str(cik).zfill(10),  # CIK must be zero-padded to 10 digits
                "name": name,
            }

    print(f"  Loaded {len(_cik_map)} ticker mappings.")
    return _cik_map


def _get_cik(ticker):
    """Look up a ticker's CIK number."""
    cik_map = _load_cik_map()
    ticker = ticker.upper().replace("-", ".")  # BRK-B → BRK.B in some SEC data

    # Try exact match
    if ticker in cik_map:
        return cik_map[ticker]

    # Try with hyphen/dot variations
    for variant in [ticker.replace(".", "-"), ticker.replace("-", ".")]:
        if variant in cik_map:
            return cik_map[variant]

    return None


def _fetch_filings_for_cik(cik_info, ticker, since_override=None):
    """Fetch recent filings for a single company."""
    cik = cik_info["cik"]
    company_name = cik_info["name"]

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = _make_request(url)

    if not data:
        return []

    recent = data.get("filings", {}).get("recent", {})
    if not recent:
        return []

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    descriptions = recent.get("primaryDocDescription", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    cutoff = since_override or (datetime.datetime.now() - datetime.timedelta(hours=HOURS_LOOKBACK))
    cutoff_date = cutoff.strftime("%Y-%m-%d")

    filings = []
    for i in range(len(forms)):
        filing_date = dates[i] if i < len(dates) else ""
        form_type = forms[i] if i < len(forms) else ""

        # Date filter
        if filing_date < cutoff_date:
            break  # filings are in reverse chronological order

        # Filing type filter
        if FILING_TYPES_OF_INTEREST and form_type not in FILING_TYPES_OF_INTEREST:
            continue

        accession = accession_numbers[i].replace("-", "") if i < len(accession_numbers) else ""
        doc = primary_docs[i] if i < len(primary_docs) else ""
        description = descriptions[i] if i < len(descriptions) else ""

        filing_url = ""
        if accession and doc:
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession}/{doc}"

        filings.append({
            "ticker": ticker,
            "company": company_name,
            "form_type": form_type,
            "date": filing_date,
            "description": description or form_type,
            "url": filing_url,
        })

    return filings


def fetch_recent_filings(since_datetime=None):
    """Main function: fetch recent SEC filings for all tickers in the watchlist.

    Args:
        since_datetime: Optional datetime — only return filings from after this time.
                        Falls back to HOURS_LOOKBACK if not provided.
    """
    if not WATCHLIST:
        print("  No EDGAR watchlist configured -- skipping SEC filings.")
        print("  Edit the WATCHLIST in sec_filings.py to add tickers.")
        return []

    all_filings = []

    print(f"  Checking EDGAR for filings from {len(WATCHLIST)} companies...")

    for ticker in WATCHLIST:
        cik_info = _get_cik(ticker)
        if not cik_info:
            print(f"    ⚠️  Could not find CIK for {ticker} — skipping.")
            continue

        filings = _fetch_filings_for_cik(cik_info, ticker, since_override=since_datetime)
        if filings:
            print(f"    📄 {ticker} ({cik_info['name']}): {len(filings)} recent filing(s)")
            all_filings.extend(filings)
        else:
            print(f"    {ticker}: no new filings")

        # SEC rate limit: 10 requests/sec — be polite
        time.sleep(0.2)

    print(f"  Found {len(all_filings)} filings. Fetching content...")

    for filing in all_filings:
        form = filing["form_type"]
        ticker = filing["ticker"]
        print(f"    📝 {ticker} {form}...", end=" ")

        content = _fetch_filing_content(filing["url"], form)
        filing["content"] = content

        # Show preview
        if content and not content.startswith("["):
            print(f"({len(content)} chars)")
        else:
            print(content[:60] if content else "(empty)")

        time.sleep(0.15)  # rate limit

    print(f"  Done — {len(all_filings)} filings with content.")
    return all_filings


if __name__ == "__main__":
    if not WATCHLIST:
        print("Edit the WATCHLIST at the top of this file first!")
        print('Example: WATCHLIST = ["AAPL", "MSFT", "GOOGL"]')
    else:
        filings = fetch_recent_filings()
        for f in filings:
            print(f"\n{'='*60}")
            print(f"  {f['date']} | {f['ticker']} | {f['form_type']} | {f['description']}")
            print(f"  {f['url']}")
            content = f.get('content', '')
            if content:
                preview = content[:300].replace('\n', ' ')
                print(f"  Content: {preview}...")
