#!/usr/bin/env python3
"""
WSJ / FT News via RSS
Pulls headlines from public RSS feeds — no API calls, no web search,
no login required. Just structured XML with real URLs and descriptions.

Opus handles the filtering for credit/distressed relevance in the digest.
"""

import datetime
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
from email.utils import parsedate_to_datetime

# --- Configuration ---
# Add or remove feeds as needed. Each entry: (url, source_label)
RSS_FEEDS = [
    # WSJ (via Dow Jones content feed — old feeds.a.dj.com URLs are dead since Jan 2025)
    ("https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "WSJ"),
    ("https://feeds.content.dowjones.io/public/rss/RSSWorldNews", "WSJ"),
    ("https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness", "WSJ"),
    # FT
    ("https://www.ft.com/markets?format=rss", "FT"),
    ("https://www.ft.com/companies?format=rss", "FT"),
    ("https://www.ft.com/world?format=rss", "FT"),
    ("https://www.ft.com/global-economy?format=rss", "FT"),
]

HOURS_LOOKBACK = 24
USER_AGENT = "DailyDigest/1.0"


def _fetch_feed(url):
    """Fetch and parse a single RSS feed."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return ET.parse(resp)
    except Exception as e:
        print(f"    Failed to fetch {url}: {e}")
        return None


def _parse_date(date_str):
    """Try to parse an RSS date string into a datetime."""
    if not date_str:
        return None

    # Try RFC 2822 format (standard RSS)
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass

    # Try ISO format
    try:
        return datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        pass

    return None


def _is_recent(date_str, hours=HOURS_LOOKBACK):
    """Check if a date string is within the lookback window."""
    parsed = _parse_date(date_str)
    if not parsed:
        return True  # include if we can't parse

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=hours)

    # Make offset-aware if needed
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)

    return parsed >= cutoff


def _clean_html(text):
    """Strip basic HTML tags from description text."""
    if not text:
        return ""
    import re
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
    return text.strip()


def fetch_wsj_ft_articles(since_datetime=None):
    """Fetch recent articles from WSJ and FT RSS feeds.

    Args:
        since_datetime: Optional datetime — only return articles published after this time.
    """
    print("  Fetching WSJ/FT RSS feeds...")

    all_articles = []
    seen_urls = set()

    for feed_url, source in RSS_FEEDS:
        tree = _fetch_feed(feed_url)
        if tree is None:
            continue

        root = tree.getroot()

        # Handle both RSS and Atom feeds
        # RSS: channel/item
        items = root.findall('.//item')

        # Atom fallback: entry (with namespace)
        if not items:
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            items = root.findall('.//atom:entry', ns)

        count = 0
        for item in items:
            # RSS format
            title = item.findtext('title', '').strip()
            link = item.findtext('link', '').strip()
            description = item.findtext('description', '').strip()
            pub_date = item.findtext('pubDate', '') or item.findtext('published', '')

            # Atom format fallback
            if not title:
                title = item.findtext('{http://www.w3.org/2005/Atom}title', '').strip()
            if not link:
                link_el = item.find('{http://www.w3.org/2005/Atom}link')
                if link_el is not None:
                    link = link_el.get('href', '')
            if not description:
                description = item.findtext('{http://www.w3.org/2005/Atom}summary', '').strip()

            if not title or not link:
                continue

            # Deduplicate
            if link in seen_urls:
                continue
            seen_urls.add(link)

            # Date filter
            if since_datetime:
                parsed = _parse_date(pub_date)
                if parsed:
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
                    since_aware = since_datetime
                    if since_aware.tzinfo is None:
                        since_aware = since_aware.replace(tzinfo=datetime.timezone.utc)
                    if parsed < since_aware:
                        continue
            elif not _is_recent(pub_date):
                continue

            description = _clean_html(description)

            all_articles.append({
                "title": title,
                "url": link,
                "summary": description[:300] if description else "",
                "source": source,
                "date": pub_date,
            })
            count += 1

        feed_name = feed_url.split("/")[-1].split("?")[0]
        print(f"    {source} {feed_name}: {count} recent articles")

    print(f"  Total: {len(all_articles)} WSJ/FT articles from RSS.")
    return all_articles


if __name__ == "__main__":
    articles = fetch_wsj_ft_articles()
    if not articles:
        print("\nNo articles found.")
    else:
        # Group by source
        for source in ["WSJ", "FT"]:
            src_articles = [a for a in articles if a["source"] == source]
            if src_articles:
                print(f"\n{'='*60}")
                print(f"  {source} — {len(src_articles)} articles")
                print(f"{'='*60}")
                for a in src_articles[:10]:
                    print(f"\n  {a['title']}")
                    print(f"  {a['url']}")
                    if a['summary']:
                        print(f"  {a['summary'][:120]}...")
