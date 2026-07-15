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


def parse_forwarded_from(body_text, window=3000):
    """Best-effort: pull the ORIGINAL sender out of a forwarded email's body.

    Forwarded emails (Outlook "FW:", Gmail "Fwd:") embed the original message's
    header block — `From: … / Sent:|Date: / To: / Subject:` — inside the body.
    The outer Gmail `From:` header is just the forwarder (jared), so this recovers
    the real source (e.g. Bloomberg) for attribution/grouping in the digest and
    the search index.

    Returns `(display_name, email)` for the first plausible forward-header
    `From:` in the first `window` chars, or `None` when nothing forward-shaped is
    found (callers fall back to the outer sender — never worse than before).

    Conservative by design: the matched `From:` must sit next to at least one
    other header label (Sent/Date/To/Cc/Subject) so a stray "From:" in prose or a
    quoted signature doesn't get mistaken for a forward header. Works whether the
    body is newline-separated (text/plain) or space-collapsed (stripped HTML).
    """
    if not body_text:
        return None
    head = body_text[:window]
    # Capture the From: value up to a newline OR the next header label (handles
    # the space-collapsed HTML case where there are no line breaks).
    m = re.search(
        r"From:\s*(.+?)(?:\r?\n|(?=\b(?:Sent|Date|To|Cc|Subject):))",
        head, re.IGNORECASE,
    )
    if not m:
        return None
    raw = m.group(1).strip()
    em = re.search(r"[\w.+-]+@[\w.-]+\.\w{2,}", raw)
    if not em:
        return None
    # Confirm a real forward-header block: another header label near the From:.
    ctx = head[m.start():m.start() + 500]
    if not re.search(r"\b(?:Sent|Date|To|Cc|Subject):", ctx, re.IGNORECASE):
        return None
    email = em.group(0)
    display = re.sub(r"<[^>]*>", "", raw).replace('"', "").strip().strip(",").strip()
    if not display or "@" in display:
        display = email
    return (display, email)


_FWD_HEADER_LINE_RE = re.compile(
    r"^\s*(?:From|Sent|Date|To|Cc|Bcc|Reply-To|Subject|Importance):",
    re.IGNORECASE,
)


def strip_forward_header(text):
    """Drop the leading forwarded-header block from a body (FORWARDING_FIX_SPEC
    Stage 2), so a capped body extract spends its budget on real content rather
    than routing boilerplate.

    Removes the Gmail "---------- Forwarded message ----------" marker and the run
    of header lines (From/Sent/Date/To/Cc/Bcc/Reply-To/Subject/Importance) at the
    top, stopping at the first real content line. Returns the original text if
    stripping would leave nothing (e.g. space-collapsed HTML with no line breaks).
    """
    if not text:
        return ""
    out = []
    skipping = True
    for ln in text.splitlines():
        if skipping:
            s = ln.strip()
            if not s:
                continue
            if s.startswith("---") and "forward" in s.lower():
                continue
            if _FWD_HEADER_LINE_RE.match(ln):
                continue
            skipping = False
        out.append(ln)
    result = "\n".join(out).strip()
    return result or text.strip()


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
