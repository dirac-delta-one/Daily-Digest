#!/usr/bin/env python3
"""
WSJ / FT News via RSS
Pulls headlines from public RSS feeds — no API calls, no web search,
no login required. Just structured XML with real URLs and descriptions.

Opus handles the filtering for credit/distressed relevance in the digest.
"""

import datetime

from feeds import fetch_feed, parse_date, is_recent

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


def _canonical_url(link):
    """Dedup key for an article URL: path only, query/fragment stripped.
    WSJ syndicates the same article to multiple feeds differing only in a
    ?mod= tracking param (two 'Oil Prices Roar Back' rows, 2026-07-24)."""
    return link.split("#", 1)[0].split("?", 1)[0]


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
        tree = fetch_feed(feed_url)
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

            # Deduplicate (tracking params ignored — see _canonical_url)
            canonical = _canonical_url(link)
            if canonical in seen_urls:
                continue
            seen_urls.add(canonical)

            # Date filter
            if since_datetime:
                parsed = parse_date(pub_date)
                if parsed:
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
                    since_aware = since_datetime
                    if since_aware.tzinfo is None:
                        since_aware = since_aware.replace(tzinfo=datetime.timezone.utc)
                    if parsed < since_aware:
                        continue
            elif not is_recent(pub_date, HOURS_LOOKBACK):
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
