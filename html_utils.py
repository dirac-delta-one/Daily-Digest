#!/usr/bin/env python3
"""
Shared HTML / Gmail text-extraction helpers (Phase 3.2).

Consolidates the byte-identical `_HTMLStripper` used by search.py and
sec_filings.py, plus the near-identical Gmail body extractors from digest.py
(capped at 50K) and reply_monitor.py (uncapped). substack.py's stripper and its
magic-link body extractor are intentionally divergent (different tag handling /
no text-vs-html split) and are NOT folded in here.
"""

import base64
import re
import html as html_module
from html.parser import HTMLParser


class HTMLStripper(HTMLParser):
    """Strip HTML tags to readable text (shared by search.py + sec_filings.py)."""

    def __init__(self):
        super().__init__()
        self.result = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "head"):
            self._skip = True
        if tag in ("p", "br", "div", "tr", "h1", "h2", "h3", "h4", "li", "td"):
            self.result.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "head"):
            self._skip = False
        if tag in ("p", "tr", "table"):
            self.result.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.result.append(data)

    def get_text(self):
        text = html_module.unescape("".join(self.result))
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def strip_html(text):
    """Strip HTML to text via HTMLStripper, with a regex fallback (from search.py)."""
    if not text:
        return ""
    stripper = HTMLStripper()
    try:
        stripper.feed(text)
        return stripper.get_text()
    except Exception:
        return re.sub(r'<[^>]+>', ' ', text)


def extract_gmail_body(payload, cap=None):
    """Recursively extract plain-text body from a Gmail message payload.

    Prefers text/plain; falls back to regex-stripped text/html. `cap` truncates
    the result at each recursion level — digest.py passes 50000, reply_monitor.py
    passes None — matching the prior per-call behavior exactly.
    """
    body = ""
    mime_type = payload.get("mimeType", "")

    if payload.get("body", {}).get("data"):
        decoded = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        if "plain" in mime_type:
            body += decoded
        elif "html" in mime_type and not body:
            body += re.sub(r'<[^>]+>', ' ', decoded)

    for part in payload.get("parts", []):
        part_body = extract_gmail_body(part, cap=cap)
        if part_body:
            body += part_body

    return body[:cap] if cap else body
