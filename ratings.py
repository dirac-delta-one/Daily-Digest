#!/usr/bin/env python3
"""
Rating Agency Actions via RSS
Monitors Moody's, S&P, and Fitch rating actions using Google News RSS
as a reliable proxy (direct agency feeds are paywalled/broken).
"""

import datetime
import re

from feeds import fetch_feed, parse_date, is_recent
from config import esc, safe_href

HOURS_LOOKBACK = 24
USER_AGENT = "DailyDigest/1.0"

# Google News RSS searches for rating actions by agency
RATING_FEEDS = [
    (
        "https://news.google.com/rss/search?q=%22Moody%27s%22+"
        "%22downgrade%22+OR+%22upgrade%22+OR+%22outlook%22+OR+%22review%22+"
        "OR+%22affirm%22+OR+%22credit+watch%22&hl=en-US&gl=US&ceid=US:en",
        "Moody's",
    ),
    (
        "https://news.google.com/rss/search?q=%22S%26P+Global%22+"
        "%22downgrade%22+OR+%22upgrade%22+OR+%22outlook%22+OR+%22review%22+"
        "OR+%22affirm%22+OR+%22credit+watch%22&hl=en-US&gl=US&ceid=US:en",
        "S&P",
    ),
    (
        "https://news.google.com/rss/search?q=%22Fitch%22+"
        "%22downgrade%22+OR+%22upgrade%22+OR+%22outlook%22+OR+%22review%22+"
        "OR+%22affirm%22+OR+%22credit+watch%22+-%22fitch+slap%22"
        "&hl=en-US&gl=US&ceid=US:en",
        "Fitch",
    ),
]

# Keywords that indicate an actual rating action (vs general commentary)
ACTION_KEYWORDS = [
    "downgrade", "upgrade", "negative outlook", "positive outlook",
    "stable outlook", "credit watch", "watchlist", "review for downgrade",
    "review for upgrade", "affirm", "assign", "withdraw",
    "negative watch", "developing outlook", "junk", "speculative",
    "investment grade", "fallen angel", "rating action", "rates",
    "cuts rating", "raises rating", "lowers rating",
]


def _is_rating_action(title, description):
    """Check if the headline is about an actual rating action."""
    text = f"{title} {description}".lower()
    return any(kw in text for kw in ACTION_KEYWORDS)


def fetch_rating_actions(since_datetime=None):
    """
    Fetch recent rating actions from all agency RSS feeds.

    Args:
        since_datetime: Optional datetime to filter results after.

    Returns:
        List of rating action dicts.
    """
    print("  Fetching rating agency actions...")

    all_actions = []
    seen_titles = set()

    for feed_url, source in RATING_FEEDS:
        tree = fetch_feed(feed_url, USER_AGENT)
        if tree is None:
            continue

        root = tree.getroot()
        items = root.findall(".//item")

        count = 0
        for item in items:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            description = item.findtext("description", "").strip()
            pub_date = item.findtext("pubDate", "")

            if not title:
                continue

            # Dedup across feeds (same story from multiple sources)
            # Normalize title for dedup
            title_key = re.sub(r'\s+', ' ', title.lower().strip())
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            # Date filter
            if since_datetime:
                parsed = parse_date(pub_date)
                if parsed and parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=datetime.timezone.utc)
                if since_datetime.tzinfo is None:
                    since_datetime = since_datetime.replace(tzinfo=datetime.timezone.utc)
                if parsed and parsed < since_datetime:
                    continue
            elif not is_recent(pub_date, HOURS_LOOKBACK):
                continue

            # Must be an actual rating action
            if not _is_rating_action(title, description):
                continue

            # Clean HTML from description
            description = re.sub(r'<[^>]+>', '', description).strip()

            # Strip trailing " - Source Website" from Google News titles
            title = re.sub(r'\s*-\s*[A-Za-z][A-Za-z\s.]+$', '', title).strip()

            all_actions.append({
                "title": title,
                "url": link,
                "description": description[:300],
                "source": source,
                "date": pub_date,
            })
            count += 1

        print(f"    {source}: {count} rating action(s)")

    # Deduplicate by entity — if multiple articles cover the same rating action,
    # keep only the first one. Extract entity name and match fuzzy.
    deduped = []
    seen_entities = set()
    for a in all_actions:
        # Extract the entity being rated from the title
        # Patterns: "Moody's downgrades XYZ Corp..." or "...upgrades XYZ to..."
        entity_match = re.search(
            r"(?:downgrades?|upgrades?|affirms?|assigns?|reviews?|rates?|maintains?|outlook|cuts?|raises?|lowers?)\s+(.+?)(?:\s+to\s+|\s+at\s+|\s+from\s+|\s+rating|\s+credit|\s*$)",
            a["title"], re.IGNORECASE,
        )
        entity_key = entity_match.group(1).strip().lower() if entity_match else a["title"].lower()
        entity_key = re.sub(r'[^a-z0-9\s]', '', entity_key).strip()

        if entity_key in seen_entities:
            continue
        seen_entities.add(entity_key)
        deduped.append(a)

    if len(deduped) < len(all_actions):
        print(f"  Deduped: {len(all_actions)} -> {len(deduped)} unique rating actions.")

    print(f"  Total: {len(deduped)} rating actions.")
    return deduped


def format_ratings_for_prompt(actions):
    """Format rating actions as plain text for the Opus prompt."""
    if not actions:
        return ""

    lines = ["RATING AGENCY ACTIONS:"]
    for a in actions:
        lines.append(f"  [{a['source']}] {a['title']}")
        if a.get("url"):
            lines.append(f"    URL: {a['url']}")
        if a.get("description"):
            lines.append(f"    {a['description'][:200]}")

    return "\n".join(lines)


def build_ratings_html(actions):
    """Render rating actions as an HTML section."""
    if not actions:
        return ""

    items = ""
    for a in actions:
        source = a["source"]
        title = a["title"]
        url = a.get("url", "")
        desc = a.get("description", "")

        # Color by direction
        title_lower = title.lower()
        if any(w in title_lower for w in ("downgrade", "negative", "junk", "review for downgrade", "lowers", "cuts")):
            indicator = '<span style="color: #c0392b; font-weight: 700;">&#x25BC;</span> '
        elif any(w in title_lower for w in ("upgrade", "positive", "raises")):
            indicator = '<span style="color: #27ae60; font-weight: 700;">&#x25B2;</span> '
        else:
            indicator = ""

        if url:
            headline = (
                f'<a href="{safe_href(url)}" style="color: #1a5276; text-decoration: none; '
                f'border-bottom: 1px solid #ccc;">{esc(title)}</a>'
            )
        else:
            headline = esc(title)

        items += (
            f'<li style="margin-bottom: 10px; font-size: 14px;">'
            f'{indicator}{headline} '
            f'<span style="color: #888; font-size: 11px;">({esc(source)})</span>'
        )
        if desc:
            items += f'<br><span style="color: #555; font-size: 13px;">{esc(desc)}</span>'
        items += '</li>\n'

    html = (
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; '
        'padding-bottom: 6px; margin: 28px 0 12px;">9. Rating Actions</h2>\n'
        f'<ul style="padding-left: 20px; margin: 0;">\n{items}</ul>\n'
    )

    return html


if __name__ == "__main__":
    actions = fetch_rating_actions()
    if actions:
        for a in actions:
            print(f"  [{a['source']}] {a['title']}")
            if a.get("url"):
                print(f"    {a['url']}")
    else:
        print("No rating actions found.")
