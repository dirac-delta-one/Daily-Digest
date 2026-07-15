#!/usr/bin/env python3
"""
Shared RSS feed helpers used by news.py and ratings.py (Phase 2.3).

pacer.py and fed_research.py have genuinely different feed shapes (PACER RSS
parsing; fed_research strips invalid XML entities before ET.fromstring), so they
are intentionally NOT folded in here.
"""

import datetime
import xml.etree.ElementTree as ET
import urllib.request
from email.utils import parsedate_to_datetime

from config import FEED_USER_AGENT


def fetch_feed(url, user_agent=FEED_USER_AGENT, timeout=15):
    """Fetch and parse a single RSS feed. Returns an ElementTree or None."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", user_agent)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return ET.parse(resp)
    except Exception as e:
        print(f"    Feed fetch error ({url}): {e}")
        return None


def parse_date(date_str):
    """Parse an RSS date string (RFC 2822 or ISO) into a datetime, or None."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    try:
        return datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


def is_recent(date_str, hours=24):
    """True if date_str is within the last `hours`, or unparseable (over-include)."""
    parsed = parse_date(date_str)
    if not parsed:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=hours)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed >= cutoff
