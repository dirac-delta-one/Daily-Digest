#!/usr/bin/env python3
"""
Substack Scraper — API-based (no browser needed)

Uses Substack's internal API with a session cookie to fetch articles.
All publications (including custom domains) go through Substack's API,
so a single substack.sid cookie covers everything.

Login renewal is fully automated via magic link + Gmail API.
"""

import os
import re
import time
import datetime
import html
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests as req

# --- Configuration ---
SUBSTACK_EMAIL = os.environ.get("SUBSTACK_EMAIL", "")
HOURS_LOOKBACK = 24
MAX_ARTICLES_PER_PUB = 3
MAX_ARTICLE_CHARS = 8000

# ======================================================================
# LIST YOUR PAID SUBSTACK SUBSCRIPTIONS HERE
# ======================================================================
SUBSCRIPTIONS = [
    "https://www.junkbondinvestor.com/",
    "https://www.polymathinvestor.com/",
    "https://www.petition11.com/",
    "https://michaeljburry.substack.com/",
    "https://www.privatedebtnews.org/",
    "https://www.creditcrunch.blog/",
    "https://paulkrugman.substack.com/",
    "https://whatiscalledthinking.substack.com/",
    "https://aletteraday.substack.com/",
    "https://www.high-yield-landlord.com/",
    "https://www.yetanothervalueblog.com/",
]

# Persistence
SCRIPT_DIR = Path(__file__).parent
COOKIE_FILE = SCRIPT_DIR / "substack_cookie.txt"


# ======================================================================
# HTML → TEXT
# ======================================================================

class _HTMLStripper(HTMLParser):
    """Simple HTML tag stripper."""
    def __init__(self):
        super().__init__()
        self.result = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True
        if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "li", "blockquote"):
            self.result.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False
        if tag == "p":
            self.result.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.result.append(data)

    def get_text(self):
        return html.unescape("".join(self.result)).strip()


def _html_to_text(html_content):
    """Convert HTML to readable plain text."""
    if not html_content:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(html_content)
    text = stripper.get_text()
    # Collapse excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


# ======================================================================
# COOKIE / SESSION
# ======================================================================

def _get_session():
    """Create a requests session with the Substack cookie."""
    session = req.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    cookie_val = _load_cookie()
    if cookie_val:
        session.cookies.set("substack.sid", cookie_val, domain=".substack.com")

    return session


def _load_cookie():
    """Load saved cookie value."""
    if COOKIE_FILE.exists():
        return COOKIE_FILE.read_text().strip()
    return None


def _save_cookie(value):
    """Save cookie value to disk."""
    COOKIE_FILE.write_text(value)
    print("  Cookie saved.")


def _check_session(session):
    """Verify the session is authenticated."""
    try:
        r = session.get("https://substack.com/api/v1/reader/feed", timeout=10)
        if r.status_code == 200:
            return True
        if r.status_code in (401, 403):
            return False
    except Exception:
        pass
    return False


# ======================================================================
# AUTOMATED LOGIN VIA MAGIC LINK
# ======================================================================

def _request_magic_link(session):
    """Ask Substack to send a magic link email."""
    print("  Requesting magic link from Substack...")

    try:
        r = session.post(
            "https://substack.com/api/v1/login",
            json={"email": SUBSTACK_EMAIL, "for_pub": "", "redirect": "/"},
            timeout=15,
        )
        if r.status_code == 200:
            print("  Magic link email sent.")
            return True
        else:
            print(f"  Magic link request failed (HTTP {r.status_code})")
            return False
    except Exception as e:
        print(f"  Magic link request error: {e}")
        return False


def _find_magic_link_in_gmail(gmail_service, max_wait=60):
    """Search Gmail for the Substack magic link."""

    start = time.time()

    while time.time() - start < max_wait:
        results = gmail_service.users().messages().list(
            userId="me",
            q="from:no-reply@substack.com subject:sign newer_than:1h",
            maxResults=3,
        ).execute()

        for msg_meta in results.get("messages", []):
            msg = gmail_service.users().messages().get(
                userId="me", id=msg_meta["id"], format="full"
            ).execute()

            body = _extract_gmail_body(msg["payload"])

            # Find magic link URLs
            urls = re.findall(
                r'https://(?:email\.)?substack\.com/[^\s"<>\)]+',
                body
            )
            # Filter to login/redirect links
            login_urls = [u for u in urls if any(k in u for k in ("login", "token", "redirect", "/c/"))]

            if login_urls:
                print("  Found magic link in Gmail.")
                return login_urls[0]

        print(f"  Waiting for magic link... ({int(time.time() - start)}s)")
        time.sleep(5)

    return None


def _extract_gmail_body(payload):
    """Recursively extract text from Gmail message payload."""
    import base64
    body = ""
    if payload.get("body", {}).get("data"):
        body += base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        if part.get("body", {}).get("data"):
            body += base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        if part.get("parts"):
            body += _extract_gmail_body(part)
    return body


def _login_via_magic_link(session, gmail_service):
    """Full magic link login: request → find in Gmail → follow → save cookie."""
    if not SUBSTACK_EMAIL:
        print("  SUBSTACK_EMAIL not set — cannot auto-login.")
        return False

    if not gmail_service:
        print("  No Gmail service — cannot auto-login.")
        return False

    if not _request_magic_link(session):
        return False

    link = _find_magic_link_in_gmail(gmail_service)
    if not link:
        print("  Could not find magic link in Gmail.")
        return False

    print("  Following magic link...")
    try:
        session.get(link, allow_redirects=True, timeout=30)

        # Extract the new substack.sid cookie
        for cookie in session.cookies:
            if cookie.name == "substack.sid":
                _save_cookie(cookie.value)
                print("  Logged in via magic link!")
                return True

        print("  Magic link didn't set a session cookie.")
        return False

    except Exception as e:
        print(f"  Error following magic link: {e}")
        return False


# ======================================================================
# ARTICLE FETCHING
# ======================================================================

def _fetch_recent_posts(session, pub_url):
    """Fetch recent posts from a publication via API."""
    base = pub_url.rstrip("/")
    api_url = f"{base}/api/v1/archive?sort=new&limit={MAX_ARTICLES_PER_PUB * 2}"

    try:
        r = session.get(api_url, timeout=15)
        if r.status_code != 200:
            print(f"    API returned {r.status_code}")
            return []

        posts = r.json()
        if not isinstance(posts, list):
            return []

        return posts

    except Exception as e:
        print(f"    API error: {e}")
        return []


def _is_recent(post, hours=HOURS_LOOKBACK):
    """Check if a post was published within the lookback window."""
    date_str = post.get("post_date") or post.get("published_at") or ""
    if not date_str:
        return True

    try:
        # Substack dates are ISO format: "2026-04-03T14:30:00.000Z"
        parsed = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        return parsed >= cutoff
    except Exception:
        return True


def _get_article_text(session, post, pub_url):
    """Get full article text for a post. Tries API body_html, then fetches the post page."""
    # The archive API often includes body_html directly
    body_html = post.get("body_html", "")

    if body_html:
        text = _html_to_text(body_html)
        if len(text) > 200:
            if len(text) > MAX_ARTICLE_CHARS:
                text = text[:MAX_ARTICLE_CHARS] + "\n[...truncated]"
            return text

    # If body_html not in archive response, fetch the individual post
    slug = post.get("slug", "")
    if slug:
        base = pub_url.rstrip("/")
        post_api = f"{base}/api/v1/posts/{slug}"
        try:
            r = session.get(post_api, timeout=15)
            if r.status_code == 200:
                data = r.json()
                body_html = data.get("body_html", "")
                if body_html:
                    text = _html_to_text(body_html)
                    if len(text) > MAX_ARTICLE_CHARS:
                        text = text[:MAX_ARTICLE_CHARS] + "\n[...truncated]"
                    return text
        except Exception:
            pass

    # Check if it's paywalled
    if post.get("audience") == "only_paid":
        return "[Paid-only post — could not access full content. Check cookie/login.]"

    return post.get("description", "") or post.get("subtitle", "") or "[Could not extract article text]"


# ======================================================================
# MAIN
# ======================================================================

def fetch_substack_articles(gmail_service=None):
    """
    Fetch recent articles from all subscribed Substack publications.

    Args:
        gmail_service: Optional Gmail API service for auto-login via magic link.
    """
    if not SUBSCRIPTIONS:
        print("  No Substack subscriptions configured — skipping.")
        return []

    session = _get_session()

    # Check if we're authenticated
    if not _load_cookie():
        print("  No Substack cookie found.")
        if not _login_via_magic_link(session, gmail_service):
            print("  Cannot authenticate. Set cookie manually or provide Gmail service.")
            print("  Manual: save your substack.sid cookie value to substack_cookie.txt")
            return []
    elif not _check_session(session):
        print("  Substack session expired — renewing...")
        if not _login_via_magic_link(session, gmail_service):
            print("  Auto-renewal failed. Update substack_cookie.txt manually.")
            return []

    print("  Substack session active.")

    articles = []

    for pub_url in SUBSCRIPTIONS:
        pub_name = urlparse(pub_url).netloc
        print(f"\n  📚 {pub_name}")

        posts = _fetch_recent_posts(session, pub_url)
        recent = [p for p in posts if _is_recent(p)][:MAX_ARTICLES_PER_PUB]

        if not recent:
            print(f"    No new posts in the last {HOURS_LOOKBACK}h.")
            continue

        print(f"    {len(recent)} recent post(s)")

        for post in recent:
            title = post.get("title", "(untitled)")
            print(f"    📰 {title[:60]}...")

            text = _get_article_text(session, post, pub_url)
            author = post.get("publishedBylines", [{}])
            author_name = author[0].get("name", pub_name) if author else pub_name

            canonical = post.get("canonical_url", "")

            articles.append({
                "title": title,
                "author": author_name,
                "publication": pub_name,
                "url": canonical or f"{pub_url.rstrip('/')}/p/{post.get('slug', '')}",
                "text": text,
            })

    print(f"\n  Done — {len(articles)} Substack articles total.")
    return articles


if __name__ == "__main__":
    if not SUBSCRIPTIONS:
        print("Edit the SUBSCRIPTIONS list at the top of this file!")
    else:
        articles = fetch_substack_articles()
        for a in articles:
            print(f"\n{'='*60}")
            print(f"Title: {a['title']}")
            print(f"Author: {a['author']}")
            print(f"URL: {a['url']}")
            preview = a['text'][:300].replace('\n', ' ')
            print(f"Text: {preview}...")
