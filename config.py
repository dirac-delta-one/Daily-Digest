#!/usr/bin/env python3
"""
Shared configuration: Claude model IDs, Opus pricing, and small HTML-escaping
helpers. Centralizes values that were previously hardcoded across modules.
"""

import html

# --- Claude models ---
# Opus upgraded 4.6 -> 4.8 (same API surface, same $5/$25 pricing).
OPUS_MODEL = "claude-opus-4-8"
SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# --- Scraper contact ---
# Courtesy contact in the User-Agent for the public SEC EDGAR / PACER / FINRA
# scrapers (fair-access etiquette, not a credential). Used by sec_filings.py,
# pacer.py, trace_data.py, fund_tracking.py.
USER_AGENT = "DailyDigest/1.0 (acorn.research.bot@gmail.com)"

# --- Pricing ($ per million tokens) ---
OPUS_PRICE_IN = 5.0
OPUS_PRICE_OUT = 25.0
SONNET_PRICE_IN = 3.0
SONNET_PRICE_OUT = 15.0
HAIKU_PRICE_IN = 1.0
HAIKU_PRICE_OUT = 5.0


def esc(s):
    """HTML-escape a text value for safe interpolation into emailed HTML."""
    return html.escape(s or "", quote=True)


def safe_href(u):
    """Only http(s) URLs pass through (escaped); anything else becomes '#'."""
    u = u or ""
    return esc(u) if u.startswith(("http://", "https://")) else "#"
