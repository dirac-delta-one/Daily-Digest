#!/usr/bin/env python3
"""
Central Bank & Research Blog Monitor
Fetches recent posts from NY Fed, FRED Blog, Brookings, and BIS (via Google News).
Filters by relevance keywords for credit/macro analysis.
"""

import re
import xml.etree.ElementTree as ET
import urllib.request

from feeds import is_recent

HOURS_LOOKBACK = 24
USER_AGENT = "DailyDigest/1.0"

RESEARCH_FEEDS = [
    ("https://libertystreeteconomics.newyorkfed.org/feed/", "NY Fed (Liberty Street)"),
    ("https://fredblog.stlouisfed.org/feed/", "FRED Blog"),
    # Brookings feed returns HTML (broken) — use Google News
    (
        "https://news.google.com/rss/search?q=site:brookings.edu+"
        "%22credit%22+OR+%22fiscal%22+OR+%22monetary%22+OR+%22debt%22+OR+%22fed%22"
        "&hl=en-US&gl=US&ceid=US:en",
        "Brookings",
    ),
    # BIS RSS is dead — use Google News
    (
        "https://news.google.com/rss/search?q=site:bis.org+"
        "%22credit%22+OR+%22financial+stability%22+OR+%22non-bank%22"
        "&hl=en-US&gl=US&ceid=US:en",
        "BIS",
    ),
]

RELEVANCE_KEYWORDS = [
    "credit", "lending", "default", "leverage", "debt", "bond",
    "yield", "spread", "rate", "inflation", "recession", "gdp",
    "financial stability", "non-bank", "nbfi", "shadow bank",
    "private credit", "clo", "securitization", "liquidity",
    "treasury", "fiscal", "monetary", "fed ", "fomc",
    "bank", "capital", "stress", "risk", "systemic",
    "oil", "commodity", "energy", "housing", "labor",
    "swap", "repo", "money market",
]


def _fetch_feed(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            # Strip any invalid XML entities that cause parse errors
            raw = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)\w+;', '', raw)
            return ET.fromstring(raw)
    except Exception as e:
        print(f"    Feed error: {e}")
        return None


def _is_relevant(title, description):
    text = f"{title} {description}".lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)


def fetch_research_articles():
    """Fetch relevant recent posts from central bank / research blogs."""
    print("  Fetching central bank research blogs...")

    all_articles = []
    seen = set()

    for feed_url, source in RESEARCH_FEEDS:
        root = _fetch_feed(feed_url)
        if root is None:
            continue

        # Handle RSS and Atom
        items = root.findall(".//item")
        if not items:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//atom:entry", ns)
        if not items:
            # Try without namespace prefix
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        count = 0
        for item in items:
            title = (item.findtext("title") or
                     item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not link:
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
                if link_el is not None:
                    link = link_el.get("href", "")
            description = (item.findtext("description") or
                          item.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()
            pub_date = (item.findtext("pubDate") or
                       item.findtext("{http://www.w3.org/2005/Atom}published") or "")

            if not title:
                continue

            # Dedup
            key = title.lower()[:60]
            if key in seen:
                continue
            seen.add(key)

            if not is_recent(pub_date, HOURS_LOOKBACK):
                continue

            # Strip Google News source suffix
            title = re.sub(r'\s*-\s*[A-Za-z][A-Za-z\s.]+$', '', title).strip()

            # Clean HTML from description
            description = re.sub(r'<[^>]+>', '', description).strip()

            if not _is_relevant(title, description):
                continue

            all_articles.append({
                "title": title,
                "url": link,
                "summary": description[:300],
                "source": source,
                "date": pub_date,
            })
            count += 1

        print(f"    {source}: {count} relevant article(s)")

    print(f"  Total: {len(all_articles)} research articles.")
    return all_articles


def format_research_for_prompt(articles):
    if not articles:
        return ""
    lines = ["CENTRAL BANK / RESEARCH BLOG POSTS:"]
    for a in articles:
        lines.append(f"  [{a['source']}] {a['title']}")
        if a.get("url"):
            lines.append(f"    URL: {a['url']}")
        if a.get("summary"):
            lines.append(f"    {a['summary'][:200]}")
    return "\n".join(lines)


if __name__ == "__main__":
    articles = fetch_research_articles()
    for a in articles:
        print(f"  [{a['source']}] {a['title']}")
        if a.get("url"):
            print(f"    {a['url']}")
