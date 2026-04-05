#!/usr/bin/env python3
"""
13F Fund Tracking
Monitors quarterly 13F-HR filings from major distressed/credit funds.
Detects new positions, exits, increases, and decreases.
"""

import json
import time
import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / "archive" / "13f_cache"

EDGAR_USER_AGENT = "DailyDigest/1.0 (jtramontano@acorninv.com)"

# Days to look back for new filings (check weekly for quarterly filings)
DAYS_LOOKBACK = 7

# Tracked funds: (CIK zero-padded to 10 digits, fund name)
TRACKED_FUNDS = [
    ("0001029160", "Oaktree Capital Management"),
    ("0001555283", "Apollo Global Management"),
    ("0001061768", "Baupost Group"),
    ("0001048445", "Elliott Investment Management"),
    ("0001336528", "Ares Management"),
    ("0001167557", "Cerberus Capital Management"),
    ("0001050470", "Canyon Capital Advisors"),
    ("0001279708", "Avenue Capital Group"),
    ("0001510981", "Monarch Alternative Capital"),
    ("0001345689", "Anchorage Capital Group"),
    ("0001649339", "Sculptor Capital Management"),
    ("0001535392", "Blackstone Credit"),
    ("0001350694", "KKR Credit Advisors"),
]


def _make_request(url):
    """Make an HTTP request to EDGAR."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", EDGAR_USER_AGENT)
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"    EDGAR request error: {e}")
        return None


def _get_latest_13f(cik):
    """Check EDGAR for the most recent 13F-HR filing from a CIK."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    raw = _make_request(url)
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    cutoff = (datetime.date.today() - datetime.timedelta(days=DAYS_LOOKBACK)).isoformat()

    for i, form in enumerate(forms):
        if form not in ("13F-HR", "13F-HR/A"):
            continue

        filing_date = dates[i] if i < len(dates) else ""
        if filing_date < cutoff:
            return None  # too old

        accession = accessions[i].replace("-", "") if i < len(accessions) else ""
        cik_stripped = cik.lstrip("0")

        return {
            "form": form,
            "date": filing_date,
            "accession": accessions[i] if i < len(accessions) else "",
            "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=13F-HR&dateb=&owner=include&count=5",
            "index_url": f"https://www.sec.gov/Archives/edgar/data/{cik_stripped}/{accession}/",
        }

    return None


def _find_infotable_url(index_url):
    """Find the information table XML file from a 13F filing index."""
    raw = _make_request(index_url)
    if not raw:
        return None

    # Look for the infotable XML file in the index
    import re

    # Try JSON index first
    json_index = index_url.rstrip("/") + "/index.json"
    raw_json = _make_request(json_index)
    if raw_json:
        try:
            idx = json.loads(raw_json)
            for item in idx.get("directory", {}).get("item", []):
                name = item.get("name", "").lower()
                if "infotable" in name and name.endswith(".xml"):
                    return index_url + item["name"]
        except Exception:
            pass

    # Fallback: parse the HTML index
    xml_files = re.findall(r'href="([^"]*(?:infotable|information)[^"]*\.xml)"', raw, re.IGNORECASE)
    if xml_files:
        url = xml_files[0]
        if not url.startswith("http"):
            url = index_url + url
        return url

    # Second fallback: any XML that's not the primary document
    xml_files = re.findall(r'href="([^"]*\.xml)"', raw, re.IGNORECASE)
    for xf in xml_files:
        if "primary" not in xf.lower():
            url = xf if xf.startswith("http") else index_url + xf
            return url

    return None


def _parse_infotable(xml_text):
    """Parse 13F information table XML into holdings list."""
    if not xml_text:
        return []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # 13F XML namespaces vary across filings
    namespaces = [
        "http://www.sec.gov/edgar/document/thirteenf/informationtable",
        "http://www.sec.gov/edgar/document/thirteenf",
    ]

    holdings = []

    for ns_uri in namespaces:
        ns = {"ns": ns_uri}
        entries = root.findall(".//ns:infoTable", ns)
        if not entries:
            continue

        for entry in entries:
            name = entry.findtext("ns:nameOfIssuer", "", ns).strip()
            cusip = entry.findtext("ns:cusip", "", ns).strip()

            value_str = entry.findtext("ns:value", "0", ns).strip()
            try:
                value = int(value_str) * 1000  # filed in thousands
            except ValueError:
                value = 0

            shares_str = entry.findtext(".//ns:sshPrnamt", "0", ns).strip()
            try:
                shares = int(shares_str)
            except ValueError:
                shares = 0

            share_type = entry.findtext(".//ns:sshPrnamtType", "", ns).strip()
            put_call = entry.findtext("ns:putCall", "", ns).strip()

            holdings.append({
                "name": name,
                "cusip": cusip,
                "value": value,
                "shares": shares,
                "share_type": share_type,
                "put_call": put_call,
            })

        if holdings:
            break  # found with this namespace

    # Fallback: try without namespace
    if not holdings:
        for entry in root.iter():
            if entry.tag.endswith("infoTable"):
                name = ""
                cusip = ""
                value = 0
                shares = 0
                for child in entry:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag == "nameOfIssuer":
                        name = (child.text or "").strip()
                    elif tag == "cusip":
                        cusip = (child.text or "").strip()
                    elif tag == "value":
                        try:
                            value = int(child.text or "0") * 1000
                        except ValueError:
                            pass
                    elif tag == "sshPrnamt":
                        try:
                            shares = int(child.text or "0")
                        except ValueError:
                            pass

                if name and cusip:
                    holdings.append({
                        "name": name,
                        "cusip": cusip,
                        "value": value,
                        "shares": shares,
                        "share_type": "",
                        "put_call": "",
                    })

    return holdings


def _load_cached_holdings(cik):
    """Load previously cached holdings for a fund."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cik}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_cached_holdings(cik, holdings):
    """Save current holdings, moving current to previous."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cik}.json"
    prev_file = CACHE_DIR / f"{cik}_prev.json"

    # Move current → previous
    if cache_file.exists():
        try:
            prev_file.write_text(cache_file.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass

    # Save new current
    cache_file.write_text(
        json.dumps(holdings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _compute_changes(current, previous):
    """Compare two sets of holdings to find position changes."""
    if not previous:
        return {"new": current[:10], "exited": [], "increased": [], "decreased": []}

    curr_by_cusip = {h["cusip"]: h for h in current}
    prev_by_cusip = {h["cusip"]: h for h in previous}

    new = [h for cusip, h in curr_by_cusip.items() if cusip not in prev_by_cusip]
    exited = [h for cusip, h in prev_by_cusip.items() if cusip not in curr_by_cusip]

    increased = []
    decreased = []
    for cusip, h in curr_by_cusip.items():
        if cusip in prev_by_cusip:
            prev = prev_by_cusip[cusip]
            share_change = h["shares"] - prev["shares"]
            if share_change > 0:
                h = dict(h)
                h["share_change"] = share_change
                h["pct_change"] = (share_change / prev["shares"] * 100) if prev["shares"] else 0
                increased.append(h)
            elif share_change < 0:
                h = dict(h)
                h["share_change"] = share_change
                h["pct_change"] = (share_change / prev["shares"] * 100) if prev["shares"] else 0
                decreased.append(h)

    new.sort(key=lambda x: x["value"], reverse=True)
    exited.sort(key=lambda x: x["value"], reverse=True)
    increased.sort(key=lambda x: abs(x.get("share_change", 0)), reverse=True)
    decreased.sort(key=lambda x: abs(x.get("share_change", 0)), reverse=True)

    return {
        "new": new[:10],
        "exited": exited[:10],
        "increased": increased[:10],
        "decreased": decreased[:10],
    }


def fetch_fund_holdings():
    """Check for new 13F filings from tracked funds. Returns list of fund results."""
    if not TRACKED_FUNDS:
        print("  No funds configured for 13F tracking — skipping.")
        return []

    print(f"  Checking 13F filings for {len(TRACKED_FUNDS)} funds...")

    results = []

    for cik, fund_name in TRACKED_FUNDS:
        filing = _get_latest_13f(cik)
        if not filing:
            continue

        print(f"    {fund_name}: new {filing['form']} filed {filing['date']}")

        # Find and fetch the infotable
        infotable_url = _find_infotable_url(filing["index_url"])
        if not infotable_url:
            print(f"      Could not find infotable XML")
            continue

        xml_text = _make_request(infotable_url)
        if not xml_text:
            continue

        holdings = _parse_infotable(xml_text)
        if not holdings:
            print(f"      No holdings parsed from infotable")
            continue

        print(f"      {len(holdings)} positions, ${sum(h['value'] for h in holdings):,.0f} total")

        # Compare to previous
        prev = _load_cached_holdings(cik)
        changes = _compute_changes(holdings, prev)

        # Cache current
        _save_cached_holdings(cik, holdings)

        results.append({
            "fund": fund_name,
            "cik": cik,
            "filing_date": filing["date"],
            "filing_url": filing["url"],
            "total_value": sum(h["value"] for h in holdings),
            "position_count": len(holdings),
            "changes": changes,
        })

        time.sleep(0.3)  # EDGAR rate limit

    print(f"  Found {len(results)} new 13F filing(s).")
    return results


def format_funds_for_prompt(results):
    """Format 13F data as plain text for the Opus prompt."""
    if not results:
        return ""

    lines = ["13F FUND FILINGS (NEW THIS PERIOD):"]

    for r in results:
        lines.append(f"\n--- {r['fund']} (filed {r['filing_date']}) ---")
        lines.append(f"  Filing: {r['filing_url']}")
        lines.append(f"  Total portfolio: ${r['total_value']:,.0f} across {r['position_count']} positions")

        changes = r["changes"]

        if changes["new"]:
            lines.append("\n  NEW POSITIONS:")
            for h in changes["new"][:5]:
                lines.append(f"    {h['name']} (CUSIP: {h['cusip']}): {h['shares']:,} shares, ${h['value']:,.0f}")

        if changes["exited"]:
            lines.append("\n  EXITED:")
            for h in changes["exited"][:5]:
                lines.append(f"    {h['name']}: {h['shares']:,} shares, was ${h['value']:,.0f}")

        if changes["increased"]:
            lines.append("\n  SIGNIFICANT INCREASES:")
            for h in changes["increased"][:5]:
                pct = h.get("pct_change", 0)
                chg = h.get("share_change", 0)
                lines.append(f"    {h['name']}: +{chg:,} shares ({pct:+.0f}%), now ${h['value']:,.0f}")

        if changes["decreased"]:
            lines.append("\n  SIGNIFICANT DECREASES:")
            for h in changes["decreased"][:5]:
                pct = h.get("pct_change", 0)
                chg = h.get("share_change", 0)
                lines.append(f"    {h['name']}: {chg:,} shares ({pct:+.0f}%), now ${h['value']:,.0f}")

    return "\n".join(lines)


def build_funds_html(results):
    """Render 13F data as an HTML section."""
    if not results:
        return ""

    html = (
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; '
        'padding-bottom: 6px; margin: 28px 0 12px;">11. Fund Position Changes (13F)</h2>\n'
    )

    for r in results:
        fund = r["fund"]
        date = r["filing_date"]
        total = r["total_value"]
        count = r["position_count"]
        url = r["filing_url"]
        changes = r["changes"]

        html += (
            f'<div style="margin-bottom: 20px;">\n'
            f'<h3 style="font-size: 15px; margin: 0 0 6px;">'
            f'<a href="{url}" style="color: #1a5276;">{fund}</a> '
            f'<span style="color: #888; font-size: 12px;">(filed {date})</span></h3>\n'
            f'<p style="font-size: 13px; color: #555; margin: 0 0 8px;">'
            f'${total:,.0f} across {count} positions</p>\n'
        )

        def _render_list(label, items, color="#1a1a1a"):
            if not items:
                return ""
            s = f'<p style="font-size: 13px; font-weight: 600; color: {color}; margin: 8px 0 4px;">{label}</p>\n'
            s += '<ul style="padding-left: 20px; margin: 0;">\n'
            for h in items[:5]:
                chg = h.get("share_change")
                pct = h.get("pct_change")
                chg_str = ""
                if chg is not None:
                    chg_str = f" ({chg:+,} shares, {pct:+.0f}%)"
                s += (
                    f'<li style="margin-bottom: 4px; font-size: 13px;">'
                    f'{h["name"]}: {h["shares"]:,} shares, ${h["value"]:,.0f}{chg_str}</li>\n'
                )
            s += '</ul>\n'
            return s

        html += _render_list("New Positions", changes["new"], "#27ae60")
        html += _render_list("Exited", changes["exited"], "#c0392b")
        html += _render_list("Increased", changes["increased"])
        html += _render_list("Decreased", changes["decreased"])

        html += '</div>\n'

    return html


if __name__ == "__main__":
    results = fetch_fund_holdings()
    if results:
        print(format_funds_for_prompt(results))
    else:
        print("No new 13F filings found in the last week.")
