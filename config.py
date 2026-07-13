#!/usr/bin/env python3
"""
Shared configuration: Claude model IDs, Opus pricing, and small HTML-escaping
helpers. Centralizes values that were previously hardcoded across modules.
"""

import html
import os

# --- Claude models ---
# Opus upgraded 4.6 -> 4.8 (same API surface, same $5/$25 pricing).
OPUS_MODEL = "claude-opus-4-8"
SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# --- User-Agent strings ---
# Courtesy contact in the User-Agent for the SEC EDGAR / PACER scrapers
# (fair-access etiquette, not a credential). Used by sec_filings.py, pacer.py,
# fund_tracking.py, net_utils.py.
USER_AGENT = "DailyDigest/1.0 (acorn.research.bot@gmail.com)"
# Plain UA for public RSS / open data-feed fetchers that don't need a contact:
# feeds.py (news + ratings), fed_research.py, cftc_cot.py, fdic_monitor.py,
# treasury_auctions.py.
FEED_USER_AGENT = "DailyDigest/1.0"

# --- Email subject ---
# The daily digest subject prefix. reply_monitor's Gmail query finds replies by
# matching this EXACT string ("Re: 📬 Daily Inbox Digest"), so the sender
# (digest.send_digest_email) and the matcher share this one constant — a subject
# edit in only one place can no longer silently break reply matching.
DIGEST_SUBJECT_PREFIX = "\U0001f4ec Daily Inbox Digest"

# --- Pricing ($ per million tokens) ---
OPUS_PRICE_IN = 5.0
OPUS_PRICE_OUT = 25.0
SONNET_PRICE_IN = 3.0
SONNET_PRICE_OUT = 15.0
HAIKU_PRICE_IN = 1.0
HAIKU_PRICE_OUT = 5.0


def unattended():
    """True when running headless (DIGEST_UNATTENDED=1, set machine-wide on the
    server by setup_tasks.ps1). Guards every interactive fallback that would
    hang a headless run: Gmail's browser consent (digest.get_gmail_service,
    F1a-1) and 13D's manual login (thirteen_d, R8)."""
    return os.environ.get("DIGEST_UNATTENDED", "").strip().lower() in ("1", "true", "yes")


def esc(s):
    """HTML-escape a text value for safe interpolation into emailed HTML."""
    return html.escape(s or "", quote=True)


def safe_href(u):
    """Only http(s) URLs pass through (escaped); anything else becomes '#'."""
    u = u or ""
    return esc(u) if u.startswith(("http://", "https://")) else "#"
