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
    "https://www.petition11.com/",
    "https://michaeljburry.substack.com/",
    "https://www.privatedebtnews.org/",
    "https://www.creditcrunch.blog/",
    "https://paulkrugman.substack.com/",
    "https://whatiscalledthinking.substack.com/",
    "https://aletteraday.substack.com/",
    "https://www.high-yield-landlord.com/",
    # No active sub — full text arrives via Substack's public per-post API;
    # keep until that breaks (operator decision 2026-07-13)
    "https://www.yetanothervalueblog.com/",
    # Paid subs found on the account but previously unfetched (2026-07-13 audit)
    "https://damnang2.substack.com/",
    "https://fixedincomebeacon.substack.com/",
    "https://www.paripassunewsletter.com/",  # API 403s (bot-blocked, like polymath) — degrades gracefully
    "https://paulomacro.substack.com/",
    "https://newsletter.semianalysis.com/",
    "https://www.techinvestments.io/",
    "https://contrarianunicus.substack.com/",
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
    """Verify the session is authenticated.

    Probes /user/profile/self: 200 only when logged in, 401 when the cookie is
    dead. The old probe (/reader/feed) returns 200 even to anonymous requests,
    so an expired cookie passed the check and auto-renewal never fired — the
    2026-07-13 dead-cookie incident went unnoticed for exactly that reason.
    """
    try:
        r = session.get("https://substack.com/api/v1/user/profile/self", timeout=10)
        if r.status_code == 200:
            return True
        if r.status_code in (401, 403):
            return False
    except Exception:
        pass
    return False


# ======================================================================
# AUTOMATED LOGIN VIA EMAIL OTP CODE
# ======================================================================
# Substack's passwordless flow (verified 2026-07-14): POST /api/v1/email-login
# emails a 6-digit verification CODE — the old /api/v1/login is password-only
# and now 400s "Please enter a longer password" — and the code is completed at
# /api/v1/email-otp-login/complete, which sets a fresh substack.sid. The code
# email goes to SUBSTACK_EMAIL (jared) and is auto-forwarded to the bot inbox;
# the forward preserves the original From, so the sender query still matches.
# All API + Gmail-read, no browser — so it self-heals unattended on the server.

_CODE_RE = re.compile(r"\b(\d{6})\b")


def _request_login_code(session):
    """Ask Substack to email a one-time login code (passwordless OTP)."""
    print("  Requesting Substack login code...")
    try:
        r = session.post(
            "https://substack.com/api/v1/email-login",
            json={"email": SUBSTACK_EMAIL, "captcha_response": None,
                  "for_pub": "", "redirect": "/"},
            timeout=15,
        )
        if r.status_code == 200:
            print("  Login code email sent.")
            return True
        print(f"  Login code request failed (HTTP {r.status_code}): {r.text[:120]}")
        return False
    except Exception as e:
        print(f"  Login code request error: {e}")
        return False


def _extract_otp_code(subject, body=""):
    """Return the 6-digit Substack OTP from a code email, or None.

    Trusts only genuine code emails (subject is 'NNNNNN is your Substack
    verification code'), so a stray 6-digit number in some other Substack email
    can't be mistaken for a login code. Prefers the subject, falls back to body.
    """
    subject = subject or ""
    if "verification code" not in subject.lower():
        return None
    m = _CODE_RE.search(subject) or _CODE_RE.search(body or "")
    return m.group(1) if m else None


def _find_login_code_in_gmail(gmail_service, since_epoch=0, max_wait=90):
    """Poll the bot inbox for Substack's OTP code email and return the code.

    Searches by SENDER only (the subject carries the code and has no 'sign'
    word, and the body has no link — so the old subject:sign + URL-follow
    approach never matched). Only accepts an email that arrived AFTER
    `since_epoch`: the inbox can hold several code emails within the hour (from
    earlier attempts), and handing /complete a STALE code returns "Invalid
    Code" — so freshness is required, not just newest-first.
    """
    start = time.time()
    while time.time() - start < max_wait:
        results = gmail_service.users().messages().list(
            userId="me",
            q="from:no-reply@substack.com newer_than:1h",
            maxResults=5,
        ).execute()

        for msg_meta in results.get("messages", []):
            msg = gmail_service.users().messages().get(
                userId="me", id=msg_meta["id"], format="full"
            ).execute()
            if int(msg.get("internalDate", 0)) / 1000 < since_epoch:
                continue  # stale — arrived before this login request
            headers = {h["name"].lower(): h["value"]
                       for h in msg["payload"].get("headers", [])}
            code = _extract_otp_code(headers.get("subject", ""),
                                     _extract_gmail_body(msg["payload"]))
            if code:
                print("  Found Substack login code in Gmail.")
                return code

        print(f"  Waiting for login code... ({int(time.time() - start)}s)")
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


def _complete_login(session, code):
    """Complete the OTP login and save the cookie ONLY if it genuinely
    authenticates.

    Substack sets an anonymous substack.sid on every session, so the mere
    presence of a cookie proves nothing (that false positive masked a broken
    flow). We require /complete to return 200 AND the session to pass the real
    /profile/self auth probe before saving — otherwise renewal fails loudly.
    """
    try:
        r = session.post(
            "https://substack.com/api/v1/email-otp-login/complete",
            json={"code": code, "email": SUBSTACK_EMAIL,
                  "redirect": "https://substack.com/"},
            timeout=30, allow_redirects=True,
        )
        if r.status_code != 200:
            print(f"  Login completion failed (HTTP {r.status_code}): {r.text[:120]}")
            return False
        if not _check_session(session):
            print("  Login completed but the session is not authenticated — not saving.")
            return False
        for cookie in session.cookies:
            if cookie.name == "substack.sid":
                _save_cookie(cookie.value)
                print("  Logged in via one-time code!")
                return True
        print("  Authenticated but no session cookie present.")
        return False
    except Exception as e:
        print(f"  Error completing login: {e}")
        return False


def _login_via_email_code(session, gmail_service):
    """Full passwordless renewal: request an OTP code → read it from the bot
    inbox (forwarded from jared) → complete the login → save the fresh cookie.
    All API + Gmail-read (no browser), so it self-heals unattended on the server."""
    if not SUBSTACK_EMAIL:
        print("  SUBSTACK_EMAIL not set — cannot auto-login.")
        return False
    if not gmail_service:
        print("  No Gmail service — cannot auto-login.")
        return False
    since = time.time() - 15  # only accept a code email newer than this request
    if not _request_login_code(session):
        return False
    code = _find_login_code_in_gmail(gmail_service, since_epoch=since)
    if not code:
        print("  Could not find a fresh Substack login code in Gmail.")
        return False
    return _complete_login(session, code)


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


def _cap_and_flag_preview(text, wordcount=None):
    """Cap article text at MAX_ARTICLE_CHARS and flag paywall previews.

    The API reports each post's TRUE wordcount; when the text we could access
    is far shorter (a free-tier sub, or a pub that stops serving full bodies),
    Opus would otherwise summarize the intro paragraphs with full-article
    confidence — the marker lets it hedge/tag the item and makes the gap
    visible in the email. The preview check runs BEFORE the cap so our own
    truncation of a long full article can't be mistaken for a paywall preview.
    """
    is_preview = bool(wordcount) and len(text.split()) < 0.5 * wordcount
    if len(text) > MAX_ARTICLE_CHARS:
        text = text[:MAX_ARTICLE_CHARS] + "\n[...truncated]"
    if is_preview:
        text += "\n[preview only — the remainder of this article is paywalled]"
    return text


def _get_article_text(session, post, pub_url):
    """Get full article text for a post. Tries API body_html, then fetches the post page."""
    # The archive API often includes body_html directly
    body_html = post.get("body_html", "")

    if body_html:
        text = _html_to_text(body_html)
        if len(text) > 200:
            return _cap_and_flag_preview(text, post.get("wordcount"))

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
                    return _cap_and_flag_preview(
                        text, data.get("wordcount") or post.get("wordcount"))
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
        if not _login_via_email_code(session, gmail_service):
            print("  Cannot authenticate. Set cookie manually or provide Gmail service.")
            print("  Manual: save your substack.sid cookie value to substack_cookie.txt")
            return []
    elif not _check_session(session):
        print("  Substack session expired — renewing...")
        if not _login_via_email_code(session, gmail_service):
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
