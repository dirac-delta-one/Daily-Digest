#!/usr/bin/env python3
"""
PACER Bankruptcy Monitor

Two modes:
  1. DISCOVERY — Monitor major bankruptcy court RSS feeds for new Chapter 11
     petitions. Surfaces new filings so you don't miss large bankruptcies.
  2. TRACKING — Once you add a case to TRACKED_CASES, monitor its docket
     for material entries (DIP motions, 363 sales, plans, bar dates, etc.).
"""

import json
import re
import time
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
from pathlib import Path

import anthropic

from config import esc, safe_href, SONNET_MODEL, USER_AGENT
from claude_utils import parse_json_response, json_schema_output, wrapped_array_schema
import cost

SCRIPT_DIR = Path(__file__).parent
SEEN_FILE = SCRIPT_DIR / "pacer_seen.json"

# ======================================================================
# DISCOVERY — Monitor courts for new Chapter 11 filings
# ======================================================================

# Major bankruptcy courts to watch (handle ~80% of large Ch.11 filings)
MONITORED_COURTS = [
    "deb",    # Delaware Bankruptcy
    "txsb",   # Southern District of Texas (Houston)
    "nysb",   # Southern District of New York
    "njb",    # New Jersey Bankruptcy
    "ilnb",   # Northern District of Illinois (Chicago)
    "vaeb",   # Eastern District of Virginia (Richmond)
    "flsb",   # Southern District of Florida
]

# Keywords that identify a new Chapter 11 petition in RSS items
NEW_FILING_KEYWORDS = [
    "chapter 11",
    "voluntary petition",
    "involuntary petition",
    "petition",
    "bk petition",
    "chapter 11 petition",
]

# ======================================================================
# TRACKING — Monitor specific cases for material docket entries
# ======================================================================

# (court_code, case_number, company_name)
# Add cases here once you discover them or want to track them
TRACKED_CASES = [
    # ("deb", "24-12345", "RAD Diversified REIT"),
]

# Material docket keywords to flag
MATERIAL_KEYWORDS = [
    "DIP", "debtor in possession", "363 sale", "plan of reorganization",
    "disclosure statement", "bar date", "claims objection", "relief from stay",
    "cash collateral", "adequate protection", "conversion to chapter 7",
    "appointment of trustee", "first day", "bidding procedures",
    "stalking horse", "credit bid", "final decree", "confirmation order",
    "exclusivity", "professional fees", "unsecured creditors committee",
]


# ======================================================================
# PERSISTENCE
# ======================================================================

def _load_seen():
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"discovery": {}, "tracking": {}}


def _save_seen(seen):
    SEEN_FILE.write_text(json.dumps(seen, indent=2, ensure_ascii=False), encoding="utf-8")


# ======================================================================
# RSS FETCHING
# ======================================================================

def _fetch_court_rss(court):
    """Fetch the court-wide RSS feed (all recent filings)."""
    url = f"https://ecf.{court}.uscourts.gov/cgi-bin/rss_outside.pl"

    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return ET.parse(resp)
    except Exception as e:
        print(f"    {court}: RSS fetch failed — {e}")
        return None


def _fetch_case_rss(court, case_number):
    """Fetch RSS feed filtered to a specific case."""
    # PACER case-specific RSS uses the case number as a search parameter
    encoded = urllib.request.quote(case_number)
    url = f"https://ecf.{court}.uscourts.gov/cgi-bin/rss_outside.pl?search={encoded}"

    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return ET.parse(resp)
    except Exception as e:
        print(f"    {court}/{case_number}: RSS fetch failed — {e}")
        return None


def _parse_items(tree):
    """Parse RSS items from an ElementTree."""
    if tree is None:
        return []
    root = tree.getroot()
    items = []
    for item in root.findall(".//item"):
        items.append({
            "title": item.findtext("title", "").strip(),
            "link": item.findtext("link", "").strip(),
            "description": item.findtext("description", "").strip(),
            "pub_date": item.findtext("pubDate", "").strip(),
        })
    return items


# ======================================================================
# DISCOVERY: Find new Chapter 11 filings
# ======================================================================

def _is_chapter_11_filing(title, description):
    """Check if an RSS item is a new Chapter 11 case (not just any docket entry)."""
    text = f"{title} {description}"

    # PACER RSS descriptions contain "Chapter: 11" for Ch.11 cases
    if not re.search(r'Chapter:\s*11', text):
        return False

    # Filter to entries that look like new case activity (petition, first-day, etc.)
    # rather than routine motions in existing Ch.11 cases.
    # New cases typically show: petition, certificate of mailing for 341 meeting,
    # order setting deadlines, first day declarations, etc.
    new_case_signals = [
        "petition", "voluntary", "involuntary",
        "certificate of mailing", "meeting of creditors",
        "order setting", "first day", "declaration",
        "corporate ownership statement", "list of creditors",
        "case opened", "new case",
    ]
    text_lower = text.lower()
    return any(sig in text_lower for sig in new_case_signals)


def _extract_case_info(title, description, link):
    """Extract case number and debtor name from PACER RSS item.

    PACER titles follow the pattern: "26-10710-mew JOANN Inc."
    where the case number is at the start, optionally followed by a judge suffix.
    """
    # Strip HTML tags from title/description
    clean_title = re.sub(r'<[^>]+>', '', title).strip()

    # Case number: digits-digits at the start of the title, with optional judge suffix
    case_match = re.match(r'(\d{2}-\d{4,6})(?:-\w+)?\s*(.*)', clean_title)
    if case_match:
        case_number = case_match.group(1)
        debtor = case_match.group(2).strip().rstrip(" -–—:")
    else:
        case_number = ""
        debtor = clean_title

    # Clean up debtor name: strip HTML, trailing punctuation, joint admin notes
    debtor = re.sub(r'<[^>]+>', '', debtor).strip()
    debtor = re.sub(r'\s*Jointly Administered under.*', '', debtor, flags=re.IGNORECASE).strip()
    debtor = debtor.strip(" -–—:.")

    # If debtor is empty or too short, try the description
    if len(debtor) < 3:
        debtor_match = re.search(r'(?:debtor|re|in re)[:\s]+([^,\n\[\(]+)', description, re.IGNORECASE)
        if debtor_match:
            debtor = re.sub(r'<[^>]+>', '', debtor_match.group(1)).strip()

    return case_number, debtor if debtor else "(unknown debtor)"


def _is_corporate_entity(name):
    """Filter out individual/personal bankruptcy filings. Keep corporate entities."""
    if not name or name == "(unknown debtor)":
        return False

    # Corporate suffixes — if present, definitely a company
    corp_patterns = [
        r'\b(LLC|L\.L\.C|Inc|Corp|Ltd|LP|L\.P|LLP|Co\b|Company|Holdings|Partners|'
        r'Group|Fund|Trust|REIT|Associates|Enterprises|International|Services|'
        r'Properties|Capital|Investments|Solutions|Technologies|Systems|Industries)\b',
    ]
    for pat in corp_patterns:
        if re.search(pat, name, re.IGNORECASE):
            return True

    # Personal name heuristics — "FirstName LastName" or "FirstName M. LastName"
    # Pattern: 2-3 capitalized words, possibly with middle initial
    personal = re.match(
        r'^[A-Z][a-z]+ (?:[A-Z]\.? )?[A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+ (?:[A-Z]\.? )?[A-Z][a-z]+)?$',
        name.strip()
    )
    if personal:
        return False

    # "d/b/a" usually means a business
    if "d/b/a" in name.lower() or "dba" in name.lower():
        return True

    # If the name has 4+ words, lean toward corporate
    if len(name.split()) >= 4:
        return True

    # Default: include (let the size filter handle it)
    return True


def _search_company_size(debtor_name):
    """Web search for the company to get context about its size."""
    # Use urllib to hit a search API — we'll use the WebSearch tool via
    # a simple Google search and pass results to Sonnet
    query = f"{debtor_name} company revenue assets size"

    req = urllib.request.Request(
        f"https://www.google.com/search?q={urllib.request.quote(query)}&num=5",
    )
    req.add_header("User-Agent", "Mozilla/5.0")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read(50000).decode("utf-8", errors="replace")
        # Extract visible text snippets
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        # Grab a relevant window
        return text[:3000]
    except Exception:
        return ""


def _filter_by_size(filings):
    """
    Use web search + Sonnet to filter filings to likely >$500M in assets.
    Batches all candidates into a single Sonnet call for efficiency.
    """
    if not filings:
        return []

    print(f"  Filtering {len(filings)} corporate Ch.11 filings by estimated size...")

    # Gather web search context for each debtor
    search_results = {}
    for f in filings:
        debtor = f["debtor"]
        if debtor in search_results:
            continue
        context = _search_company_size(debtor)
        search_results[debtor] = context
        time.sleep(0.3)  # rate limit searches

    # Build the Sonnet prompt with all candidates
    candidates = ""
    for i, f in enumerate(filings):
        debtor = f["debtor"]
        court = f["court"].upper()
        case_num = f["case_number"]
        context = search_results.get(debtor, "No search results found.")
        candidates += (
            f"\n--- Candidate {i} ---\n"
            f"Debtor: {debtor}\n"
            f"Court: {court}, Case: {case_num}\n"
            f"Web search context: {context[:500]}\n"
        )

    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1000,
            system=(
                "You are filtering Chapter 11 bankruptcy filings for a distressed credit investor. "
                "For each candidate, estimate whether the company likely has over $500 million "
                "in total assets or liabilities. Use the web search context provided, plus your "
                "general knowledge of the company.\n\n"
                "Consider: Is this a publicly traded company? A large private company? A PE-backed "
                "platform? A real estate portfolio? If there's not enough info to tell, lean toward "
                "EXCLUDE — the investor only wants to see large cases.\n\n"
                "Return a JSON object {\"indices\": [ ... ]} with the candidate indices (integers) "
                "that are likely >$500M. Example: {\"indices\": [0, 3, 7]}. If none qualify, "
                "return {\"indices\": []}. No explanation."
            ),
            output_config=json_schema_output(wrapped_array_schema("indices", "integer")),
            messages=[{"role": "user", "content": (
                f"Evaluate these {len(filings)} Chapter 11 filings. "
                f"Return the indices of those likely >$500M in assets/liabilities.\n"
                f"{candidates}"
            )}],
        )

        indices = parse_json_response(response.content[0].text)["indices"]

        kept = [filings[i] for i in indices if isinstance(i, int) and 0 <= i < len(filings)]

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        print(f"  Size filter: kept {len(kept)}/{len(filings)} "
              f"({tokens_in:,} in + {tokens_out:,} out)")
        cost.record("pacer size filter", SONNET_MODEL, response.usage)

        return kept

    except Exception as e:
        print(f"  Size filter failed ({e}) — keeping all corporate filings.")
        return filings


def discover_new_filings():
    """
    Monitor major bankruptcy court RSS feeds for new Chapter 11 petitions.

    Returns list of new filings found.
    """
    print(f"  Scanning {len(MONITORED_COURTS)} bankruptcy courts for new Ch.11 filings...")

    seen = _load_seen()
    disc_seen = seen.get("discovery", {})
    new_filings = []

    for court in MONITORED_COURTS:
        tree = _fetch_court_rss(court)
        items = _parse_items(tree)

        court_seen = set(disc_seen.get(court, []))
        court_new = 0

        for item in items:
            entry_id = item["link"] or item["title"]
            if entry_id in court_seen:
                continue

            if _is_chapter_11_filing(item["title"], item["description"]):
                case_number, debtor = _extract_case_info(
                    item["title"], item["description"], item["link"]
                )

                new_filings.append({
                    "court": court,
                    "case_number": case_number,
                    "debtor": debtor or "(name not parsed)",
                    "title": item["title"],
                    "description": item["description"][:300],
                    "link": item["link"],
                    "date": item["pub_date"],
                })
                court_new += 1
                print(f"    NEW Ch.11: {debtor or item['title'][:50]} ({court.upper()}, {case_number})")

            court_seen.add(entry_id)

        disc_seen[court] = list(court_seen)[-1000:]  # keep last 1000 per court

        if court_new == 0 and items:
            print(f"    {court.upper()}: {len(items)} entries, no new Ch.11 petitions")

        time.sleep(0.3)  # polite rate limiting

    seen["discovery"] = disc_seen
    _save_seen(seen)

    print(f"  Found {len(new_filings)} raw Chapter 11 filing(s).")

    if not new_filings:
        return []

    # Step 1: Filter out individuals, keep only corporate entities
    corporate = [f for f in new_filings if _is_corporate_entity(f["debtor"])]
    dropped = len(new_filings) - len(corporate)
    if dropped:
        print(f"  Filtered out {dropped} individual/personal filings, {len(corporate)} corporate remain.")

    if not corporate:
        return []

    # Step 2: Web search + Sonnet to estimate size, keep only likely >$500M
    large = _filter_by_size(corporate)

    print(f"  Final: {len(large)} large Ch.11 filing(s) (est. >$500M).")
    return large


# ======================================================================
# TRACKING: Monitor specific cases for material docket entries
# ======================================================================

def _is_material(text):
    """Check if a docket entry description contains material keywords."""
    text_lower = text.lower()
    return [kw for kw in MATERIAL_KEYWORDS if kw.lower() in text_lower]


def track_existing_cases():
    """
    Check PACER RSS feeds for new material docket entries in tracked cases.

    Returns list of new material entries.
    """
    if not TRACKED_CASES:
        return []

    print(f"  Checking dockets for {len(TRACKED_CASES)} tracked case(s)...")

    seen = _load_seen()
    track_seen = seen.get("tracking", {})
    new_entries = []

    for court, case_number, company in TRACKED_CASES:
        case_key = f"{court}/{case_number}"
        case_seen = set(track_seen.get(case_key, []))

        tree = _fetch_case_rss(court, case_number)
        items = _parse_items(tree)

        for item in items:
            entry_id = item["link"] or item["title"]
            if entry_id in case_seen:
                continue

            full_text = f"{item['title']} {item['description']}"
            matched = _is_material(full_text)

            if matched:
                new_entries.append({
                    "company": company,
                    "court": court,
                    "case_number": case_number,
                    "title": item["title"],
                    "description": item["description"][:300],
                    "link": item["link"],
                    "date": item["pub_date"],
                    "keywords": matched,
                })
                print(f"    {company}: {item['title'][:60]}... [{', '.join(matched)}]")

            case_seen.add(entry_id)

        track_seen[case_key] = list(case_seen)[-500:]
        time.sleep(0.3)

    seen["tracking"] = track_seen
    _save_seen(seen)

    print(f"  Found {len(new_entries)} new material docket entries.")
    return new_entries


# ======================================================================
# MAIN ENTRY POINT (called by digest.py)
# ======================================================================

def fetch_pacer_docket():
    """
    Run both discovery and tracking, return combined results.

    Returns list of entries (new filings + material docket activity).
    """
    all_entries = []

    # Discovery: new Chapter 11 filings across major courts
    try:
        new_filings = discover_new_filings()
        for f in new_filings:
            all_entries.append({
                "company": f["debtor"],
                "court": f["court"],
                "case_number": f["case_number"],
                "title": f"NEW CHAPTER 11: {f['title']}",
                "description": f["description"],
                "link": f["link"],
                "date": f["date"],
                "keywords": ["Chapter 11 petition"],
                "is_new_filing": True,
            })
    except Exception as e:
        print(f"  Discovery scan failed: {e}")

    # Tracking: material docket entries in tracked cases
    try:
        docket_entries = track_existing_cases()
        for e in docket_entries:
            e["is_new_filing"] = False
            all_entries.append(e)
    except Exception as e:
        print(f"  Docket tracking failed: {e}")

    return all_entries


# ======================================================================
# FORMATTING
# ======================================================================

def format_pacer_for_prompt(entries):
    if not entries:
        return ""

    lines = ["BANKRUPTCY COURT ACTIVITY:"]

    new_filings = [e for e in entries if e.get("is_new_filing")]
    docket_entries = [e for e in entries if not e.get("is_new_filing")]

    if new_filings:
        lines.append("\n  NEW CHAPTER 11 FILINGS:")
        for e in new_filings:
            lines.append(f"    {e['company']} — Case {e['case_number']} ({e['court'].upper()})")
            if e.get("description"):
                lines.append(f"      {e['description'][:200]}")

    if docket_entries:
        lines.append("\n  DOCKET ACTIVITY (tracked cases):")
        for e in docket_entries:
            lines.append(f"    {e['company']} (Case {e['case_number']}, {e['court'].upper()}):")
            lines.append(f"      {e['title']}")
            lines.append(f"      Flagged: {', '.join(e['keywords'])}")

    return "\n".join(lines)


def build_pacer_html(entries):
    if not entries:
        return ""

    new_filings = [e for e in entries if e.get("is_new_filing")]
    docket_entries = [e for e in entries if not e.get("is_new_filing")]

    html = (
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; '
        'padding-bottom: 6px; margin: 28px 0 12px;">Bankruptcy Court Activity</h2>\n'
    )

    # New Chapter 11 filings — prominent alert-style
    if new_filings:
        html += (
            '<div style="background: #fdf2f2; border-left: 4px solid #c0392b; '
            'padding: 10px 14px; margin-bottom: 16px;">\n'
            '<strong style="color: #c0392b;">New Chapter 11 Filing(s):</strong>\n'
            '<ul style="padding-left: 20px; margin: 6px 0 0;">\n'
        )
        for e in new_filings:
            court_label = e["court"].upper()
            case_num = e["case_number"]
            debtor = e["company"]
            link_html = ""
            if e.get("link"):
                link_html = (
                    f' <a href="{safe_href(e["link"])}" style="color: #1a5276; font-size: 12px;">'
                    f'[PACER]</a>'
                )

            desc = ""
            if e.get("description"):
                desc = (
                    f'<br><span style="color: #555; font-size: 12px;">'
                    f'{esc(e["description"][:200])}</span>'
                )

            html += (
                f'<li style="margin-bottom: 8px; font-size: 14px;">'
                f'<strong>{esc(debtor)}</strong> — {court_label} Case {esc(case_num)}{link_html}'
                f'{desc}</li>\n'
            )
        html += '</ul>\n</div>\n'

    # Tracked case docket activity
    if docket_entries:
        by_company = {}
        for e in docket_entries:
            by_company.setdefault(e["company"], []).append(e)

        html += '<ul style="padding-left: 20px; margin: 0;">\n'
        for company, cases in by_company.items():
            html += (
                f'<li style="margin-bottom: 12px; font-size: 14px;">'
                f'<strong>{esc(company)}</strong> (Case {esc(cases[0]["case_number"])})'
                f'<ul style="margin: 4px 0 0; padding-left: 16px;">'
            )
            for e in cases:
                kw_tags = ", ".join(e["keywords"])
                link_html = ""
                if e.get("link"):
                    link_html = (
                        f' <a href="{safe_href(e["link"])}" style="color: #1a5276; '
                        f'font-size: 12px;">[docket]</a>'
                    )
                html += (
                    f'<li style="margin-bottom: 6px; font-size: 13px;">'
                    f'{esc(e["title"])}{link_html}'
                    f'<br><span style="color: #888; font-size: 12px;">'
                    f'Flagged: {esc(kw_tags)}</span></li>'
                )
            html += '</ul></li>\n'
        html += '</ul>\n'

    return html


if __name__ == "__main__":
    print("=== Discovery: scanning for new Chapter 11 filings ===")
    new = discover_new_filings()
    if new:
        for f in new:
            print(f"  {f['debtor']} — {f['court'].upper()} Case {f['case_number']}")
    else:
        print("  No new filings found.")

    if TRACKED_CASES:
        print("\n=== Tracking: checking monitored cases ===")
        entries = track_existing_cases()
        if entries:
            for e in entries:
                print(f"  {e['company']}: {e['title'][:60]}")
        else:
            print("  No new material docket entries.")
