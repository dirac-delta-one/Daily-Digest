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

# --- Reply-bot access tiers (TEAM_DIGEST_SPEC Stage 2) ---
# Substack content is personal to jared: full-access askers get Substack in
# reply answers (raw substack chunks, substack-memory storylines, the FULL
# digest as context); every other asker gets the team (Substack-free) view.
# Add an address here to grant full access. WHO GETS ANSWERED AT ALL is the
# config-driven union built by reply_monitor._reply_query (this set + the
# full/team recipient lists) — CLEANUP_SPEC 2.3.
# Trimmed 2026-07-14 (operator directives): jaredtramontano@gmail.com removed
# (kept unanswerable — it stays in FORWARDER_ADDRESSES below, which is
# attribution, not access); the bot removed (2026-06-29 slot-swap artifact —
# internal calls already get full access via asker=None, and the bot neither
# authors replies nor receives digests anymore).
FULL_ACCESS_SENDERS = {
    "jtramontano@acorninv.com",
}

# Set at Stage-5 team activation (ISO date string). Digest chunks dated BEFORE
# this are FULL digests with Substack woven into their prose, so team askers'
# retrieval excludes them. None = team never activated -> every digest chunk
# is a full digest -> all of them are excluded for team askers.
# ACTIVATED 2026-07-13 (pilot: acohen on DIGEST_TO_TEAM). Every run from this
# date generates + indexes the team digest — the server's env.bat must also
# carry DIGEST_TO_TEAM at deploy. A post-activation run WITHOUT DIGEST_TO_TEAM
# is treated as misconfigured (CLEANUP_SPEC 2.1): digest.main warns + alerts,
# search skips that day's digest chunks, and the shared memory is not updated
# — so a missing env var can no longer leak Substack to team askers.
# ESCAPE HATCH: if the team variant is ever DELIBERATELY retired, set this
# back to None — otherwise the guard keeps digest chunks un-indexed and the
# shared memory frozen forever (with only the daily alert as a clue).
TEAM_ACTIVATION_DATE = "2026-07-13"

# --- Forwarding (FORWARDING_FIX_SPEC) ---
# Addresses that forward research into the bot inbox. When the outer sender is
# one of these (or the subject is a FW:/Fwd:), digest.fetch_recent_emails parses
# the forwarded body for the ORIGINAL sender so the digest can attribute/group
# by the real source (Bloomberg etc.). Distinct from FULL_ACCESS_SENDERS (which
# includes the bot and governs reply-bot tiers) — this is only about forwards.
FORWARDER_ADDRESSES = {
    "jtramontano@acorninv.com",
    "jaredtramontano@gmail.com",
}

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
