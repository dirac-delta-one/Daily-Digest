#!/usr/bin/env python3
"""
Daily Gmail Digest
Reads recent emails from Gmail and Substack subscriptions, summarizes them
with Claude (including PDF attachments), and sends a digest email.

PDFs are sent directly to Claude's vision/document API — no text extraction needed.
This handles scanned PDFs, image-heavy reports, etc.
"""

import os
import io
import re
import sys
import base64
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.mime.text import MIMEText
from pathlib import Path

import anthropic
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import (
    FABLE_MODEL, HAIKU_MODEL, DIGEST_SUBJECT_PREFIX, TEAM_ACTIVATION_DATE,
    FORWARDER_ADDRESSES, esc, safe_href, unattended, is_self_artifact,
    is_substack_email,
)
from config import BOT_ADDRESS  # noqa: F401  (re-exported for tests/callers)
from claude_utils import parse_json_response, json_schema_output, wrapped_array_schema
import cost
from html_utils import extract_gmail_body, parse_forwarded_from, strip_forward_header
from substack import fetch_substack_articles
from sec_filings import fetch_recent_filings, company_names, WATCHLIST
import repetition
import ticker_names
from news import fetch_wsj_ft_articles
from market_data import (
    fetch_market_data, build_market_table_html, build_private_credit_html,
    build_ai_html, format_market_data_for_prompt,
)
from macro_data import (
    fetch_macro_data, build_rates_table_html, build_credit_table_html,
    format_macro_for_prompt,
)
from ishares_data import fetch_ishares_oas, format_ishares_for_prompt
from memory import (
    get_memory_context, update_memory,
    get_substack_memory_context, update_substack_memory,
)
from alerts import evaluate_alerts, build_alerts_html
from earnings import fetch_earnings_calendar, build_earnings_html, format_earnings_for_prompt
from pacer import fetch_pacer_docket, format_pacer_for_prompt, build_pacer_html, commit_seen
from ratings import fetch_rating_actions, format_ratings_for_prompt
from fund_tracking import fetch_fund_holdings, format_funds_for_prompt, build_funds_html
from thirteen_d import fetch_wiltw
from fed_research import fetch_research_articles, format_research_for_prompt
from treasury_auctions import fetch_treasury_auctions, format_auctions_for_prompt
from cftc_cot import fetch_cot_data, format_cot_for_prompt
from fed_balance_sheet import (
    fetch_fed_balance_sheet, format_fed_bs_for_prompt, build_fed_bs_table_html, check_fed_stress,
)
from fdic_monitor import fetch_failed_banks, format_fdic_for_prompt
from archive import archive_daily_content
from content_monitor import record_and_check
from search import index_daily_content

# --- Configuration ---
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
# Parse --email_time=N from command line, default 24
HOURS_LOOKBACK = 24
for _arg in sys.argv[1:]:
    if _arg.startswith("--email_time="):
        try:
            HOURS_LOOKBACK = int(_arg.split("=", 1)[1])
        except ValueError:
            pass
MAX_EMAILS = 50  # max emails to include in digest
MAX_PDF_SIZE_MB = 5  # skip PDFs larger than this (to control token usage)

# Email body extract fed to Opus (FORWARDING_FIX_SPEC Stage 2). Replaces the
# ~200-char snippet so forwarded content (Bloomberg roundups, text broker notes)
# is actually readable at digest time. Text-bearing emails get the full slice;
# PDF-carried emails stay lean (their content is the attached document); a
# per-run total budget bounds heavy inbox days (forwarded text emails funded first).
EMAIL_BODY_PROMPT_CHARS = 4000
EMAIL_BODY_PDF_CHARS = 500
EMAIL_BODY_TOTAL_CHARS = 40000
def _recipients_from_env(var, default):
    """Comma-split, whitespace-stripped recipient list from an env var."""
    return [r.strip() for r in os.environ.get(var, default).split(",") if r.strip()]


# Recipients default to production (jared); override with the DIGEST_TO env var
# (e.g. set DIGEST_TO=acohen@acorninv.com on a test machine). reply_monitor.py
# imports this, so the override applies there too. This is the
# FULL variant's audience (Substack included) — TEAM_DIGEST_SPEC Stage 1.
# Receiving-side policy (operator, 2026-07-14): recipients are @acorninv.com
# addresses ONLY. The bot was removed as its own recipient (CLEANUP_SPEC 2.5):
# the self-send put every digest/alert into the very inbox the digest READS as
# a source (in:inbox, last 24h) — a latent ingestion loop that would have
# first fired at server deploy. _is_self_artifact below is the code-side
# backstop should a self-send ever be reintroduced.
_DEFAULT_RECIPIENTS = "jtramontano@acorninv.com"
DIGEST_RECIPIENTS = _recipients_from_env("DIGEST_TO", _DEFAULT_RECIPIENTS)

# The Substack-free TEAM variant's audience (TEAM_DIGEST_SPEC). Default EMPTY:
# team generation is skipped entirely until a recipient is added (the Stage-5
# activation checklist), so the second 2-pass run costs nothing today.
TEAM_RECIPIENTS = _recipients_from_env("DIGEST_TO_TEAM", "")

# Prefixed onto the FULL variant's subjects (daily + weekly) so the Substack-
# inclusive digest jared receives is visually distinguishable from the team
# variant, which keeps the plain subject. The reply-bot Gmail query matches on
# DIGEST_SUBJECT_PREFIX (a separate subject: term from the "Re:" anchor), so this
# leading marker does NOT break reply matching — see reply_monitor.check_for_replies.
FULL_SUBJECT_MARKER = "[FULL] "
# Digest generation model. Switched OPUS_MODEL -> FABLE_MODEL 2026-07-22 to
# evaluate the Mythos-class model on the 2-pass digest + weekly summary.
# Alerts/13D/reply bot stay on OPUS_MODEL (unchanged), so this is the only
# moving variable. Import OPUS_MODEL and set this back to it to roll back.
CLAUDE_MODEL = FABLE_MODEL

# BOT_ADDRESS + the self-mail detector moved to config.py (2026-07-15) so the
# INDEXER can share them (search.py can't import digest — circular). The
# private alias keeps the existing callers and tests unchanged.
_is_self_artifact = is_self_artifact

# Paths (relative to this script)
SCRIPT_DIR = Path(__file__).parent
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"  # from Google Cloud Console
TOKEN_FILE = SCRIPT_DIR / "token.json"  # auto-generated after first login
DIGESTS_DIR = SCRIPT_DIR / "digests"  # saved daily digests for weekly summary


def _unattended():
    """True when running headless — delegates to config.unattended() (shared
    with thirteen_d's login guard since Stage 2.5)."""
    return unattended()


def get_gmail_service():
    """Authenticate and return a Gmail API service object.

    Unattended mode (F1a-1): with DIGEST_UNATTENDED set, a dead/expired token
    FAILS FAST (SystemExit 3) instead of falling through to the interactive
    browser consent — on a headless server `flow.run_local_server()` blocks
    forever, so the run never exits and even the wrapper's nonzero-exit alert
    can't fire (observed live 2026-07-07). The fast failure lets the wrapper
    fire `run_alert` and leaves re-consent as a deliberate manual step.
    """
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                # Refresh token expired/revoked (invalid_grant) — don't crash;
                # fall through to a fresh browser consent below.
                print(f"  Gmail refresh token rejected ({e}). Re-authorizing via browser consent...")
                creds = None

        if not creds or not creds.valid:
            if _unattended():
                print("ERROR: Gmail token invalid/expired and DIGEST_UNATTENDED is set — "
                      "refusing to open an interactive browser consent (it would hang a "
                      "headless run forever). Re-consent manually on this machine, then re-run.")
                raise SystemExit(3)
            if not CREDENTIALS_FILE.exists():
                print(f"ERROR: {CREDENTIALS_FILE} not found.")
                print("Download it from Google Cloud Console → APIs & Services → Credentials.")
                raise SystemExit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_pdf_attachments(service, msg_id, parts):
    """Recursively find and download PDF attachments from message parts."""
    pdfs = []

    for part in parts:
        filename = part.get("filename", "")
        mime_type = part.get("mimeType", "")

        # Recurse into multipart containers
        if part.get("parts"):
            pdfs.extend(get_pdf_attachments(service, msg_id, part["parts"]))

        # Check if this part is a PDF
        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            attachment_id = part.get("body", {}).get("attachmentId")
            if not attachment_id:
                continue

            att = service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=attachment_id
            ).execute()

            # Gmail returns URL-safe base64; convert to standard base64 for Claude
            pdf_data_urlsafe = att["data"]
            pdf_bytes = base64.urlsafe_b64decode(pdf_data_urlsafe)

            # Skip oversized PDFs
            size_mb = len(pdf_bytes) / (1024 * 1024)
            if size_mb > MAX_PDF_SIZE_MB:
                print(f"    ⏭️  Skipping {filename} ({size_mb:.1f}MB > {MAX_PDF_SIZE_MB}MB limit)")
                continue

            # Re-encode as standard base64 for Claude API
            pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

            pdfs.append({
                "filename": filename or "attachment.pdf",
                "base64": pdf_b64,
            })
            print(f"    📎 Downloaded PDF: {filename} ({size_mb:.1f}MB)")

    return pdfs


def fetch_recent_emails(service, hours=HOURS_LOOKBACK, max_results=MAX_EMAILS):
    """Fetch emails from the last N hours, including PDF attachments."""
    after = datetime.datetime.now() - datetime.timedelta(hours=hours)
    query = f"after:{int(after.timestamp())} in:inbox"

    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        return []

    emails = []
    for msg_meta in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_meta["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        snippet = msg.get("snippet", "")

        outer_from = headers.get("From", "Unknown")
        subject = headers.get("Subject", "(no subject)")

        # Never ingest the system's own output (or replies to it) as source
        # material — CLEANUP_SPEC 2.5.
        if _is_self_artifact(outer_from, subject):
            print(f"    Skipping self/digest artifact: {subject[:60]}")
            continue

        # Check for PDF attachments
        pdfs = []
        parts = msg["payload"].get("parts", [])
        if parts:
            pdfs = get_pdf_attachments(service, msg_meta["id"], parts)

        # Extract full body text for archiving/RAG (not sent to Opus — too large)
        body_text = extract_gmail_body(msg["payload"], cap=50000)

        # Forwarding (FORWARDING_FIX_SPEC Stage 1): when jared forwards research
        # in, the outer From is jared — recover the ORIGINAL sender from the
        # forwarded body so the digest can attribute/group by the real source.
        # Only attempt on likely forwards (known forwarder OR FW:/Fwd: subject);
        # a miss falls back to the outer sender.
        effective_from = outer_from
        is_forward = subject.lower().startswith(("fw:", "fwd:")) or any(
            addr in outer_from.lower() for addr in FORWARDER_ADDRESSES
        )
        if is_forward:
            parsed = parse_forwarded_from(body_text)
            if parsed:
                display, email = parsed
                effective_from = f"{display} <{email}>" if display != email else email

        emails.append({
            "from": outer_from,
            "effective_from": effective_from,
            "subject": subject,
            "date": headers.get("Date", ""),
            "snippet": snippet,
            "body": body_text,
            "pdfs": pdfs,
        })

    return emails


SYSTEM_PROMPT = """\
You are creating a daily research digest for a professional credit/distressed investment analyst.

Your job is to take the day's inbox — research reports, newsletters, market commentary, \
investment ideas — and produce a sharp, useful briefing.

Before writing, plan: list the day's distinct stories and assign each to exactly ONE \
home section. Write from that allocation — the plan is for your reasoning only; never \
include it in the output.

SECTIONS — If a section has no content, OMIT IT ENTIRELY and renumber the remaining \
sections sequentially (1, 2, 3...). Do not include empty sections or "none found" messages. \
Do not leave numbering gaps.

1. **Top Takeaways** — The 3-5 most important things from today's inbox. Lead with what's \
new, surprising, or actionable. This is the digest's opening section — there is NO TL;DR / \
summary box above it; do not generate one.

2. **Market & Macro** — Key macro themes, economic data, central bank commentary, \
rates/FX/commodities moves mentioned across sources. Cite specific levels and changes from \
the market/FRED data provided ONLY in support of a story or interpretation drawn from the \
sources. The reader sees that raw data in snapshot tables directly above your digest, so a \
bullet that merely restates a level or move (e.g. "10Y at 4.25%, down 3 bps on the week") \
with no added analysis is FORBIDDEN — drop it. If nothing qualifies, omit the section.

3. **Equity Ideas & Calls** — Specific stock mentions, upgrades/downgrades, price target \
changes, earnings takeaways. Always include ticker symbols and any specific numbers \
(targets, multiples, estimates).

4. **Themes & Sector Trends** — Broader sector or thematic trends appearing across \
multiple sources.

5. **Contrarian / Surprising** — Anything that goes against consensus, is unexpected, \
or where two sources disagree with each other.

6. **Worth Reading in Full** — Flag 1-3 items. One line each: \
<strong>Topic:</strong> <a href="URL">Title</a> (Source) — why it's worth reading. \
Hyperlink the title to the source URL. No paragraph descriptions.

7. **Bloomberg** — If any emails are from bloomberg.net, group them here. \
Summarize each with headline and key data points. Keep tight. Only items NOT already \
covered in sections 1-6 — if a Bloomberg item earned a spot in an earlier section, it \
lives there and must not be restated here. Omit this section if nothing is left.

8. **Recent SEC Filings** — Filing content is included for each filing. \
For 8-Ks, summarize the material event (what happened, key numbers, implications). \
For Form 4s, note who traded, how many shares, and at what price. \
For other forms, highlight the most important details. \
Organize by company. Include ticker, form type, date, and link to the filing.

9. **Rating Actions** — From the rating agency actions provided (Moody's, S&P, Fitch). \
One line each: entity (with ticker if known), the action (upgrade/downgrade/outlook change) \
and specifics (new rating, notches, rationale). Lead with downgrades and fallen angels — \
they carry the most credit signal. Tag the source at the end of each line.

The "WSJ/FT Articles", "Fund Position Changes", and "Bankruptcy Court Activity" \
sections are appended separately AFTER your digest as UNNUMBERED sections — do NOT \
generate, number, or reserve numbers for them. Number ONLY your own sections above, \
sequentially (1, 2, 3, …), omitting any that are empty — however many you produce, \
there is nothing to collide with below. The PACER docket entries below are provided \
only so you can cross-reference them where relevant (e.g. Takeaways/Themes); do NOT \
write a standalone bankruptcy or court-activity section.

Rules:
- Be specific. Include numbers, tickers, dates, and names — not vague summaries.
- LEAD WORD: every bullet in every numbered section (1-9) starts with a single bolded \
topic word followed by a colon — <strong>Oil:</strong>, <strong>Turkey:</strong>, \
<strong>Homebuilders:</strong> — chosen so the reader knows the bullet's subject at a \
glance. When a bullet is about one issuer, the ticker or entity name is the right lead, \
written in the FULL ticker form — <strong>$NVDA (NVIDIA):</strong> — NEVER a bare \
ticker lead like "COF:"; in Worth Reading the lead word comes before the \
linked title; in SEC Filings and Rating Actions the company/entity is the natural lead. \
A two-word lead is allowed only when one word would be ambiguous \
(<strong>Turkey CDS:</strong>).
- Tickers are ALWAYS written $-prefixed — $COF, never a bare "COF" — wherever they \
appear. Bold a ticker ONLY when it is the bullet's lead word \
(<strong>$COF (Capital One):</strong>); everywhere else in a bullet's body the ticker \
stays unbolded ($COF). When a company is discussed, keep its ticker visible: do not \
replace a ticker from the sources with the name alone.
- Every ticker you cite is followed by the issuer's name in parentheses — \
$SPCX (SpaceX) — whenever that name appears in the source material \
(a TICKER GLOSSARY block of verified names may be provided among the sources; it \
counts as source material for this rule). Do not expand a ticker into a company name \
that does NOT appear in the source material or the glossary: if you are unsure of the \
issuer, cite the bare ticker (e.g. "$TCBK") rather than guessing. Skip the \
parenthetical where the name is already immediately adjacent \
(e.g. "SpaceX ($SPCX)" needs no second copy of the name).
- If multiple sources discuss the same topic, synthesize them and note where they agree \
or disagree.
- SECTIONS ARE EXCLUSIVE, IN ORDER. Work top-down: once a story has appeared in any \
section, later sections may not re-tell it. When a story qualifies for several sections, \
it lives in the EARLIEST qualifying section. If a later section has a genuinely NEW \
angle on it, give ONLY the new angle in one clause with a cross-reference pointer — \
never restate the numbers or re-tell the story.
- CROSS-REFERENCES: when a bullet must touch a story covered elsewhere, point to its \
home section instead of restating it: "…the new angle here <em>(→ §1)</em>." Number \
references against YOUR final output's numbering (after omitting empty sections), and \
only point at your own numbered sections.
- Tag each claim with its source in parentheses at the end, e.g. "(Grant's)" or "(Greenmantle)". \
Be consistent — always at the end of the bullet, never woven into the sentence. \
Only cite real sources: publication names (Grant's, FT, Bloomberg), SEC filing types, \
agency names. NEVER cite "Cross-Digest Memory" or any internal system component as a source, \
and NEVER append "memory" (or any system-layer word) to a source tag — write "(Greenmantle)", \
never "(Greenmantle memory)".
- Skip promotional content, subscription upsells, and anything with no analytical substance.
- Keep it scannable — short bullets, no filler.
- If cross-digest memory is provided, use it to add context about evolving stories \
(e.g., "tracking since Mar 28: redemptions now at 40.7%, up from 32% last week"). \
Cite the original source of the data, not the memory system itself.

FORMAT: Output valid HTML using EXACTLY this structure. Do not deviate from this template. \
Use inline styles only (no <style> blocks). Every digest must look identical in structure.

<div style="font-family: Georgia, 'Times New Roman', serif; max-width: 680px; margin: 0 auto; color: #1a1a1a; line-height: 1.6;">

  <!-- Header -->
  <div style="border-bottom: 3px double #1a1a1a; padding-bottom: 12px; margin-bottom: 20px;">
    <h1 style="font-size: 28px; margin: 0;">Daily Research Digest</h1>
    <p style="font-size: 13px; color: #666; margin: 4px 0 0;">{{DATE}} · Prepared by Claude</p>
  </div>

  <!-- No TL;DR / summary box. The digest opens directly with section 1. -->
  <!-- Sections use this exact pattern. Use these EXACT numbers. Omit sections with no content. -->
  <h2 style="font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 6px; margin: 28px 0 12px;">1. Top Takeaways</h2>
  <ul style="padding-left: 20px; margin: 0;">
    <li style="margin-bottom: 10px; font-size: 14px;"><strong>{{Topic}}:</strong> {{content}} <span style="color: #888;">(Source)</span></li>
  </ul>

  <!-- Section 2: Market & Macro -->
  <!-- Section 3: Equity Ideas & Calls -->
  <!-- Section 4: Themes & Sector Trends -->
  <!-- Section 5: Contrarian / Surprising -->
  <!-- Section 6: Worth Reading in Full — hyperlink titles to source URLs -->
  <!-- Section 7: Bloomberg — only if bloomberg.net emails exist -->
  <!-- Section 8: Recent SEC Filings — only if filings exist -->
  <!-- Section 9: Rating Actions — only if rating agency actions exist -->

  <!-- Styling rules for all sections: -->
  <!-- Section headers: h2, 18px, border-bottom, numbered as above -->
  <!-- Content: ul/li for bullets, 14px, 10px margin-bottom -->
  <!-- Every bullet opens with its bolded lead word: <strong>Topic:</strong> -->
  <!-- Sources: span with color #888, always at end of bullet -->
  <!-- Tickers: $TICK (Company Name) whenever a ticker appears; bold only as a lead word -->
  <!-- Cross-refs: <em>(→ §N)</em> when touching a story whose home is another section -->
  <!-- Hyperlinks: <a href="URL" style="color: #1a5276;">linked text</a> -->

</div>

Follow this template exactly. Same fonts, same sizes, same spacing every single time.
"""


def _looks_like_promo(e):
    """Very conservative 'clearly spam/promo' guard (FORWARDING_FIX_SPEC decision
    4). Trips only on obvious marketing junk (>=3 promo markers), so a real
    forwarded note or subscribed newsletter is never demoted. A promo email is
    NOT dropped — it just keeps its short snippet instead of a full body extract."""
    text = f"{e.get('subject', '')} {e.get('snippet', '')}".lower()
    markers = (
        "unsubscribe", "view in browser", "view this email in your browser",
        "manage preferences", "manage your subscription", "special offer",
        "limited time", "shop now", "% off", "promo code",
    )
    return sum(m in text for m in markers) >= 3


def _email_body_for_prompt(e, cap):
    """Body slice shown to Opus for one email (FORWARDING_FIX_SPEC Stage 2):
    forwarded-header stripped, capped at `cap` chars. Falls back to the snippet
    when there is no body or no budget (cap <= 0)."""
    if cap <= 0:
        return e.get("snippet", "")
    body = (e.get("body") or "").strip()
    if not body:
        return e.get("snippet", "")
    body = strip_forward_header(body)
    if len(body) > cap:
        body = body[:cap].rstrip() + " […]"
    return body


def _build_source_prompt(*, emails, sec_filings, market_data,
                         macro_data, memory_context, earnings, pacer_entries,
                         rating_actions=None, fund_results=None,
                         wiltw=None,
                         research_articles=None, treasury_auctions=None,
                         cot_data=None, fed_bs=None, bank_failures=None,
                         ishares_oas=None):
    """Build the TEAM-shareable source material text for the Opus prompt.

    Keyword-only (Phase 3.1): with 15 same-typed source arguments, positional
    calls were a misroute footgun — `*` forces every caller to name each source.

    Substack is NOT here (TEAM_DIGEST_SPEC): it is personal to jared, so it
    lives in `_build_substack_block`, appended as a TRAILING block for the
    full variant only — which also makes this prompt a strict prefix of the
    full prompt, so the two variants share the prompt cache.
    """
    # Email body-extract budget (Stage 2): text-bearing emails get the full
    # slice, PDF-carried emails stay lean (content is the attachment), promo
    # keeps only its snippet. When the total budget is tight, forwarded text
    # emails are funded first.
    def _cap_for(e):
        if _looks_like_promo(e):
            return 0
        return EMAIL_BODY_PDF_CHARS if e.get("pdfs") else EMAIL_BODY_PROMPT_CHARS

    def _priority(k):
        e = emails[k]
        is_fwd = e.get("effective_from", e.get("from")) != e.get("from")
        return (bool(e.get("pdfs")), not is_fwd)  # non-PDF forwards first

    remaining = EMAIL_BODY_TOTAL_CHARS
    budget = {}
    for k in sorted(range(len(emails)), key=_priority):
        give = max(0, min(_cap_for(emails[k]), remaining))
        budget[k] = give
        remaining -= give

    # Email metadata
    email_lines = []
    for i, e in enumerate(emails):
        pdf_note = ""
        if e.get("pdfs"):
            names = ", ".join(p["filename"] for p in e["pdfs"])
            pdf_note = f"\n📎 PDF attachments (included below): {names}"

        outer = e.get("from", "Unknown")
        eff = e.get("effective_from", outer)
        from_line = (
            f"From: {eff}  (forwarded by {outer})" if eff and eff != outer
            else f"From: {outer}"
        )
        content = _email_body_for_prompt(e, budget[i])

        email_lines.append(
            f"--- Email {i+1} ---\n"
            f"{from_line}\n"
            f"Subject: {e['subject']}\n"
            f"Date: {e['date']}\n"
            f"Content: {content}"
            f"{pdf_note}"
        )

    pdf_count = sum(len(e["pdfs"]) for e in emails)
    pdf_note = ""
    if pdf_count > 0:
        pdf_note = (
            f" {pdf_count} PDF attachment(s) are included after the email list — "
            "extract and synthesize their key content."
        )

    prompt = (
        f"Here are {len(emails)} emails from my inbox in the last {HOURS_LOOKBACK} hours."
        f"{pdf_note}\n\n"
        + "\n\n".join(email_lines)
    )

    # Market data
    market_text = format_market_data_for_prompt(market_data)
    if market_text:
        prompt += "\n\n" + "=" * 40 + "\n" + market_text + "\n" + "=" * 40

    # Macro data
    macro_text = format_macro_for_prompt(macro_data)
    if macro_text:
        prompt += "\n\n" + "=" * 40 + "\n" + macro_text + "\n" + "=" * 40

    # iShares fund-reported OAS (IGLB/IGIB — credit snapshot rows)
    if ishares_oas:
        ishares_text = format_ishares_for_prompt(ishares_oas)
        if ishares_text:
            prompt += "\n\n" + "=" * 40 + "\n" + ishares_text + "\n" + "=" * 40

    # Earnings calendar
    earnings_text = format_earnings_for_prompt(earnings)
    if earnings_text:
        prompt += "\n\n" + "=" * 40 + "\n" + earnings_text + "\n" + "=" * 40

    # Cross-digest memory
    if memory_context:
        prompt += "\n\n" + "=" * 40 + "\n" + memory_context + "\n" + "=" * 40

    # 13D Research WILTW (Opus-summarized PDF)
    if wiltw and wiltw.get("summary"):
        prompt += (
            "\n\n" + "=" * 40
            + f"\n13D RESEARCH — {wiltw['title']}:\n"
            + "=" * 40 + "\n"
            + wiltw["summary"]
        )

    # SEC filings
    if sec_filings:
        filing_lines = []
        for f in sec_filings:
            line = (
                f"--- Filing: {f['ticker']} ({f['company']}) ---\n"
                f"Form: {f['form_type']} | Date: {f['date']}\n"
                f"URL: {f['url']}\n"
                f"Description: {f['description']}"
            )
            filing_content = f.get("content", "")
            if filing_content and not filing_content.startswith("["):
                line += f"\n\nFiling Content:\n{filing_content}"

            filing_lines.append(line)

        prompt += "\n\n" + "=" * 40 + "\nSEC FILINGS:\n" + "=" * 40 + "\n\n"
        prompt += "\n\n".join(filing_lines)

    # PACER docket entries
    pacer_text = format_pacer_for_prompt(pacer_entries)
    if pacer_text:
        prompt += "\n\n" + "=" * 40 + "\n" + pacer_text + "\n" + "=" * 40

    # Rating agency actions
    if rating_actions:
        ratings_text = format_ratings_for_prompt(rating_actions)
        if ratings_text:
            prompt += "\n\n" + "=" * 40 + "\n" + ratings_text + "\n" + "=" * 40

    # 13F fund filings
    if fund_results:
        funds_text = format_funds_for_prompt(fund_results)
        if funds_text:
            prompt += "\n\n" + "=" * 40 + "\n" + funds_text + "\n" + "=" * 40

    # Central bank research
    if research_articles:
        research_text = format_research_for_prompt(research_articles)
        if research_text:
            prompt += "\n\n" + "=" * 40 + "\n" + research_text + "\n" + "=" * 40

    # Treasury auctions
    if treasury_auctions:
        auctions_text = format_auctions_for_prompt(treasury_auctions)
        if auctions_text:
            prompt += "\n\n" + "=" * 40 + "\n" + auctions_text + "\n" + "=" * 40

    # CFTC COT
    if cot_data:
        cot_text = format_cot_for_prompt(cot_data)
        if cot_text:
            prompt += "\n\n" + "=" * 40 + "\n" + cot_text + "\n" + "=" * 40

    # Fed balance sheet
    if fed_bs:
        fed_text = format_fed_bs_for_prompt(fed_bs)
        if fed_text:
            prompt += "\n\n" + "=" * 40 + "\n" + fed_text + "\n" + "=" * 40

    # FDIC bank failures
    if bank_failures:
        fdic_text = format_fdic_for_prompt(bank_failures)
        if fdic_text:
            prompt += "\n\n" + "=" * 40 + "\n" + fdic_text + "\n" + "=" * 40

    # Ticker glossary (ticker_names.py, 2026-07-22): verified issuer names for
    # the tickers in the text above, so the "$TICK (Name)" rule can fire
    # without violating the no-guessing rule. Built from the assembled prompt
    # itself, so it is a pure function of the shared sources + the (frozen-
    # during-run) name cache — both variants produce byte-identical blocks and
    # the TEAM prefix stays cache-shareable.
    glossary, _ = ticker_names.build_glossary(prompt, sec_names=company_names())
    if glossary:
        prompt += "\n\n" + "=" * 40 + "\n" + glossary + "\n" + "=" * 40

    return prompt


def _build_substack_block(substack_articles, substack_memory_context=None):
    """Trailing prompt block for the FULL variant only (TEAM_DIGEST_SPEC §1):
    the Substack articles + the substack-memory context.

    Kept OUT of _build_source_prompt so the team prompt is a strict prefix of
    the full prompt — both extras must sit here in the tail, after the shared
    cache breakpoint, or the prefix diverges and the variants stop sharing
    the prompt cache. Returns "" when there is nothing to add.
    """
    parts = []

    if substack_memory_context:
        parts.append("=" * 40 + "\n" + substack_memory_context + "\n" + "=" * 40)

    if substack_articles:
        substack_lines = []
        for i, a in enumerate(substack_articles):
            substack_lines.append(
                f"--- Substack Article {i+1} ---\n"
                f"Title: {a['title']}\n"
                f"Author: {a['author']}\n"
                f"URL: {a['url']}\n\n"
                f"{a['text']}"
            )
        parts.append(
            f"Additionally, {len(substack_articles)} paid Substack articles follow. "
            "Treat these as primary research sources — summarize their key arguments, "
            "data points, and investment implications.\n\n"
            + "=" * 40 + "\nSUBSTACK ARTICLES:\n" + "=" * 40 + "\n\n"
            + "\n\n".join(substack_lines)
        )

    return "\n\n".join(parts)


def _response_text(response):
    """The concatenated text of a Messages response, skipping non-text blocks.

    Fable 5 (claude-fable-5) returns extended-thinking by default, so
    content[0] is a ThinkingBlock and the visible answer is a LATER text block
    — the old `content[0].text` raised AttributeError under Fable (2026-07-22).
    Selecting text blocks by type is model-agnostic: on Opus (no thinking
    block) it still returns the single text block unchanged."""
    return "".join(
        b.text for b in response.content if getattr(b, "type", None) == "text"
    )


def _strip_to_html(text):
    """Isolate the emailed digest HTML from any model chatter around it.

    Opus occasionally wraps the digest in prose in two places:
    - a sentence of preamble BEFORE the opening <div, and
    - (pass 2, nondeterministically) a markdown "Changes made:" changelog AFTER
      the final </div> narrating the edits it made — this leaked into the sent
      2026-07-21 team digest (WORKLOG 2026-07-21).

    The email must be exactly the template: start at the first <div and end at
    the last HTML closing tag, dropping any trailing chatter. A naive "cut at
    the last '>'" is unsafe — changelog prose can contain '>' (e.g. the real
    leak's "Japan >$180B repatriation"); matching the last closing tag avoids
    that. Used by digest pass 2 and the weekly summary."""
    start = text.find("<div")
    if start < 0:
        return text
    html = text[start:]
    closings = list(re.finditer(r"</[a-zA-Z][a-zA-Z0-9]*>", html))
    return html[:closings[-1].end()] if closings else html


def summarize_with_claude(*, emails, substack_articles=None, sec_filings=None,
                          market_data=None, macro_data=None, earnings=None,
                          pacer_entries=None,
                          rating_actions=None, fund_results=None,
                          wiltw=None,
                          research_articles=None, treasury_auctions=None,
                          cot_data=None, fed_bs=None, bank_failures=None,
                          ishares_oas=None,
                          substack_memory_context=None, cost_label=""):
    """Send all sources to Claude for digest generation (2-pass).

    Keyword-only (Phase 3.1) — see `_build_source_prompt` for the rationale.

    TEAM_DIGEST_SPEC: the team variant passes substack_articles=[] (and no
    substack_memory_context); the full variant passes both, which land in a
    trailing content block AFTER the shared cache breakpoint — so when both
    variants run (team first), the full run reads the team run's cached
    prefix and pays only for the substack tail. `cost_label` distinguishes
    the variants in the per-run cost summary (e.g. " (team)").
    """
    client = anthropic.Anthropic()
    substack_articles = substack_articles or []
    sec_filings = sec_filings or []
    market_data = market_data or []
    macro_data = macro_data or []
    earnings = earnings or []
    pacer_entries = pacer_entries or []
    rating_actions = rating_actions or []
    fund_results = fund_results or []
    research_articles = research_articles or []
    treasury_auctions = treasury_auctions or []
    cot_data = cot_data or []
    fed_bs = fed_bs or []
    bank_failures = bank_failures or []
    ishares_oas = ishares_oas or []

    # Substack-via-email boundary (2026-07-15): paid Substack newsletters also
    # arrive as inbox email (e.g. PETITION from petition@substack.com). They are
    # Substack content — jared-personal — so they must NOT enter the shared/team
    # prompt prefix. Drop them here; because BOTH variants filter identically the
    # cached prefix stays byte-identical, and the FULL variant still gets Substack
    # via the scraped substack_block. (Their index chunks are tagged "substack" in
    # search._chunks_for_date.)
    shared_emails = [
        e for e in emails
        if not is_substack_email(e.get("effective_from"), e.get("from"))
    ]
    n_sub_email = len(emails) - len(shared_emails)
    if n_sub_email:
        print(f"  Excluded {n_sub_email} Substack-origin email(s) from the digest "
              "prompt (jared-personal; FULL still gets Substack via the scraper).")

    # Get cross-digest memory context (the shared/team store — both variants)
    memory_context = get_memory_context()

    # Build the team-shareable source prompt (no Substack — see the builder)
    prompt = _build_source_prompt(
        emails=shared_emails,
        sec_filings=sec_filings,
        market_data=market_data,
        macro_data=macro_data,
        memory_context=memory_context,
        earnings=earnings,
        pacer_entries=pacer_entries,
        rating_actions=rating_actions,
        fund_results=fund_results,
        wiltw=wiltw,
        research_articles=research_articles,
        treasury_auctions=treasury_auctions,
        cot_data=cot_data,
        fed_bs=fed_bs,
        bank_failures=bank_failures,
        ishares_oas=ishares_oas,
    )

    # Build the content array for Claude's messages API
    content = [{"type": "text", "text": prompt}]

    # Add each PDF as a document block (shared_emails only — a Substack-origin
    # email's attachments follow the same jared-personal boundary as its body)
    for e in shared_emails:
        for pdf in e["pdfs"]:
            content.append({
                "type": "text",
                "text": f"\n📎 PDF attachment from: {e['from']} — Subject: {e['subject']} — File: {pdf['filename']}"
            })
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf["base64"],
                },
            })

    # Prompt caching (Step 3): the source material (text + PDFs) is identical across
    # both passes, so mark the last shared block as a cache breakpoint. Both passes use
    # the SAME system prompt and put their per-pass instruction AFTER this cached prefix,
    # so pass 1 writes the cache and pass 2 reads it (~0.1x) instead of re-paying full
    # price to re-send the sources+PDFs. The passes run seconds apart, well within the
    # 5-minute cache TTL. Validated output-equivalent + cache-engaging 2026-07-01 (see
    # WORKLOG) — caching is transparent to the model (identical tokens either way).
    # TEAM_DIGEST_SPEC: this breakpoint also marks the team/full SHARED prefix.
    content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}

    # Substack tail (full variant only): articles + substack-memory context,
    # with its own breakpoint so the full run's two passes share it too.
    substack_block = _build_substack_block(substack_articles, substack_memory_context)
    if substack_block:
        # Supplemental glossary for tickers appearing only in the Substack
        # tail (the shared-prefix glossary can't carry them without forking
        # the TEAM/FULL cache prefix — so they ride here, full-variant only).
        supp_glossary, _ = ticker_names.build_glossary(
            substack_block, sec_names=company_names(),
            exclude=ticker_names.extract_tickers(prompt))
        if supp_glossary:
            substack_block += "\n\n" + "=" * 40 + "\n" + supp_glossary + "\n" + "=" * 40
        content.append({
            "type": "text",
            "text": "\n" + substack_block,
            "cache_control": {"type": "ephemeral"},
        })

    # ---- PASS 1: Generate initial digest ----
    print("  Pass 1: Generating initial digest...")

    pass1_content = content + [{
        "type": "text",
        "text": (
            "Using the source material above, generate today's daily research digest now, "
            "following the template and rules in the system prompt exactly."
        ),
    }]
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=20000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": pass1_content}],
    )

    draft = _response_text(response)

    # Log token usage
    p1_input = response.usage.input_tokens
    p1_output = response.usage.output_tokens
    print(f"  Pass 1 tokens: {p1_input:,} in + {p1_output:,} out")
    cost.record(f"digest pass 1{cost_label}", CLAUDE_MODEL, response.usage)

    # ---- PASS 2: Review and enhance ----
    # Same system + same cached source prefix as pass 1; the review instruction (with the
    # draft) goes in the trailing block so the cached prefix stays byte-identical.
    print("  Pass 2: Reviewing for missed content...")

    pass2_content = content + [{
        "type": "text",
        "text": (
            "Above is all of today's original source material.\n\n"
            "Below is a DRAFT DIGEST you produced from it. Review the draft against the "
            "source material above:\n"
            "1. DEDUPLICATE — this is the primary review goal. Method: list every ticker and "
            "every specific figure (price, spread, %, target, $ amount) that appears in more "
            "than one section of the draft. For each, choose the home section (the earliest "
            "qualifying one), keep the full detail there, and in every other section either "
            "delete the mention or reduce it to a one-clause new angle with a <em>(→ §N)</em> "
            "pointer. Verify every (→ §N) points at a section that exists in the final "
            "numbering. Also confirm there is NO TL;DR / summary box before section 1 — if "
            "the draft opens with one, delete it so the digest starts at section 1.\n"
            "2. Identify any important items that were MISSED — specific data points, trade "
            "ideas, tickers, price targets, key arguments, or surprising findings that should "
            "have been included but weren't.\n"
            "3. Check for any ERRORS — wrong numbers, misattributed sources, or mischaracterized "
            "arguments.\n"
            "4. Check that every bullet has a source tag.\n"
            "5. Check the FORMAT rules: every bullet starts with its bolded lead word + colon "
            "(<strong>Topic:</strong>); every ticker is $-prefixed everywhere it appears but "
            "bolded ONLY as a bullet's lead word — a single-issuer bullet leads with the full "
            "form (<strong>$COF (Capital One):</strong>, never a bare \"COF:\") while "
            "mid-bullet tickers stay unbolded; every cited "
            "ticker carries the issuer name in parentheses when the name is in the sources "
            "(or immediately adjacent prose); Market & Macro contains no bullet that merely "
            "restates a snapshot-table level or move without added analysis (delete any such "
            "bullet).\n"
            "6. Produce a FINAL ENHANCED VERSION of the digest that incorporates anything missed "
            "and fixes any errors, repetition, and format violations. Keep the exact same HTML "
            "template and formatting.\n\n"
            "If the draft was already comprehensive, return it mostly unchanged — don't pad it "
            "with filler.\n\n"
            "Output ONLY the final digest HTML itself — begin at the opening <div> and end at "
            "the final </div>. Do NOT append any preamble, sign-off, commentary, or summary/"
            "changelog of the changes you made.\n\n"
            "DRAFT DIGEST:\n"
            "═══════════════════════════════════════\n"
            f"{draft}\n"
            "═══════════════════════════════════════\n"
        ),
    }]
    review_response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=20000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": pass2_content}],
    )

    final = _strip_to_html(_response_text(review_response))

    # Stage "$TICK (Name)" pairs this digest rendered for the learned name
    # cache — validated against the FULL prompt text (not the truncated alert
    # window below). Staging only: the disk write is main()'s single commit()
    # after BOTH variants, so the team/full shared cache prefix can't fork
    # mid-run (see ticker_names module docstring).
    try:
        ticker_names.collect(final, prompt + "\n" + substack_block,
                             known=ticker_names.known_names(company_names()))
    except Exception as e:
        print(f"  Ticker-name collection failed: {e} — continuing.")

    # Log total token usage
    p2_input = review_response.usage.input_tokens
    p2_output = review_response.usage.output_tokens
    print(f"  Pass 2 tokens: {p2_input:,} in + {p2_output:,} out")
    cost.record(f"digest pass 2{cost_label}", CLAUDE_MODEL, review_response.usage)

    # Cost (cache-aware): usage.input_tokens excludes cached tokens, so price via
    # cost.cost_of, which bills cache reads at 0.1x and writes at 1.25x.
    def _cache_tokens(usage):
        return (getattr(usage, "cache_read_input_tokens", 0) or 0,
                getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cr1, cw1 = _cache_tokens(response.usage)
    cr2, cw2 = _cache_tokens(review_response.usage)
    total_cost = (cost.cost_of(CLAUDE_MODEL, p1_input, p1_output, cr1, cw1)
                  + cost.cost_of(CLAUDE_MODEL, p2_input, p2_output, cr2, cw2))

    print(f"  Cache: pass 1 wrote {cw1:,} tok; pass 2 read {cr2:,} tok from cache")
    print(f"  Estimated 2-pass cost: ${total_cost:.2f}")

    # Source text for alert evaluation — the variant's view (the team variant
    # has no substack block, so its alerts can never cite Substack). alerts.py
    # evaluates only the first ~50k chars; with the substack block now at the
    # TAIL it would rarely make that window, silently blinding the FULL alert
    # box to Substack (e.g. PETITION flagging a distressed exchange). Carve
    # the window instead: most of it for the shared sources, a guaranteed
    # slice for Substack.
    if substack_block:
        head = prompt[:35000]
        if len(prompt) > 35000:
            head += "\n\n[...remaining shared sources truncated for alert evaluation...]"
        source_text = head + "\n\n" + substack_block[:15000]
    else:
        source_text = prompt
    return final, source_text


def _rank_news_articles(articles, max_articles=15):
    """Use Claude to force-rank articles by relevance for a credit/distressed investor."""
    if len(articles) <= max_articles:
        return articles

    print(f"  Ranking {len(articles)} WSJ/FT articles by relevance...")

    # Build a numbered list of titles + summaries for ranking
    article_list = ""
    for i, a in enumerate(articles):
        title = a.get("title", "")
        summary = a.get("summary", "")[:150]
        source = a.get("source", "")
        article_list += f"{i}. [{source}] {title}"
        if summary:
            article_list += f" — {summary}"
        article_list += "\n"

    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=500,
            system=(
                f"You are selecting the {max_articles} most relevant news articles for a "
                "credit/distressed investment analyst. Be RUTHLESS — only keep articles "
                "directly relevant to: credit markets, bankruptcies, restructuring, "
                "leveraged finance, specialty finance, special situations, distressed credit, "
                "macro/rates, energy/commodities, geopolitical risk "
                "affecting markets, central bank policy, sovereign debt, or regulatory "
                "changes that impact credit.\n\n"
                "EXCLUDE: truck electrification, car finance schemes, fintech apps, "
                "weight-loss drugs, tech product launches, lifestyle, sports, "
                "entertainment, and anything without a direct credit/macro angle."
            ),
            output_config=json_schema_output(wrapped_array_schema("indices", "integer")),
            messages=[{"role": "user", "content": (
                f"Below are {len(articles)} articles. Return the index numbers of "
                f"the top {max_articles} most relevant, in order of relevance, as a JSON "
                f'object {{"indices": [ ... ]}}, nothing else.\n\n{article_list}'
            )}],
        )

        indices = parse_json_response(response.content[0].text)["indices"]
        ranked = []
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(articles):
                ranked.append(articles[idx])

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        print(f"  Ranked: kept {len(ranked)}/{len(articles)} articles "
              f"({tokens_in:,} in + {tokens_out:,} out)")
        cost.record("news ranking", HAIKU_MODEL, response.usage)

        return ranked if ranked else articles[:max_articles]

    except Exception as e:
        print(f"  Ranking failed ({e}) — keeping first {max_articles}.")
        return articles[:max_articles]


# Title tokens too generic to indicate story identity (REDUCE_REPEATS Idea 13).
_TITLE_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "after", "over", "amid", "says", "said", "into", "more", "than", "what",
    "when", "where", "their", "they", "been", "were", "would", "could",
    "should", "about", "market", "markets", "stocks", "shares", "investors",
    "billion", "million", "percent", "report", "reports", "year", "years",
    "week", "wall", "street",
}


def _title_covered(title, digest_text):
    """True when the digest text already covers this headline's story
    (REDUCE_REPEATS Idea 13). Deterministic, strict bar — a false drop hides a
    headline from the reader; a false keep is just the old status quo.

    Signals, any of which trips coverage:
    - a $TICK from the title appears in the digest;
    - a distinctive proper-noun bigram (two consecutive Capitalized words,
      e.g. "Gray Media") appears in the digest;
    - >=60% of the title's content tokens (len>=4, non-stopword; at least 3
      of them, else the title is too generic to judge) appear in the digest.
    """
    if not title or not digest_text:
        return False
    text_lower = digest_text.lower()

    for tick in re.findall(r"\$[A-Z][A-Z0-9.]{1,7}\b", title):
        if tick.lower() in text_lower:
            return True

    for m in re.finditer(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b", title):
        bigram = f"{m.group(1)} {m.group(2)}".lower()
        if bigram in text_lower and not all(
                w in _TITLE_STOPWORDS for w in bigram.split()):
            return True

    tokens = [t for t in re.findall(r"[a-z']{4,}", title.lower())
              if t not in _TITLE_STOPWORDS]
    if len(tokens) >= 3:
        hits = sum(1 for t in tokens if t in text_lower)
        if hits / len(tokens) >= 0.6:
            return True
    return False


def build_news_html(articles, exclude_text=""):
    """Generate the WSJ/FT section as pre-formatted HTML with real hyperlinks.

    Expects PRE-RANKED articles — the Haiku ranking was hoisted to main() so
    it runs once while this renders per variant (REDUCE_REPEATS Idea 13;
    supersedes the F10 decline — ranking stays in digest.py's paid path,
    never in the free news.py path). `exclude_text` is that variant's
    Opus-written digest HTML: headlines whose story the digest already covers
    are dropped, closing the blind spot where the model can't dedup against a
    section appended after generation."""
    if not articles:
        return ""

    if exclude_text:
        kept = [a for a in articles
                if not _title_covered(a.get("title", ""), exclude_text)]
        dropped = len(articles) - len(kept)
        if dropped:
            print(f"  WSJ/FT: dropped {dropped} of {len(articles)} ranked "
                  "headline(s) already covered in the digest.")
        articles = kept
        if not articles:
            return ""

    html = (
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; '
        'padding-bottom: 6px; margin: 28px 0 12px;">WSJ/FT Articles</h2>\n'
        '<ul style="padding-left: 20px; margin: 0;">\n'
    )

    for a in articles:
        title = a.get("title", "")
        url = a.get("url", "")
        summary = a.get("summary", "")
        source = a.get("source", "")

        # Source color (WSJ red so the tag doesn't blend into the blue link color)
        src_color = "#c00000" if source == "WSJ" else "#f26f21"

        if url:
            headline = (
                f'<a href="{safe_href(url)}" style="color: #1a5276; text-decoration: none; '
                f'border-bottom: 1px solid #ccc;">{esc(title)}</a>'
            )
        else:
            headline = esc(title)

        html += (
            f'<li style="margin-bottom: 10px; font-size: 14px;">'
            f'{headline} '
            f'<span style="color: {src_color}; font-weight: 700; font-size: 11px;">'
            f'({esc(source)})</span>'
        )

        if summary:
            html += f'<br><span style="color: #555; font-size: 13px;">{esc(summary)}</span>'

        html += '</li>\n'

    html += '</ul>\n'

    return html


def _assemble_digest_html(digest_html, alerts_html, market_html, rates_html,
                          credit_html, private_html, ai_html,
                          earnings_html, news_html, pacer_html,
                          funds_html="", fed_bs_html=""):
    """
    Assemble the final digest HTML by injecting pre-built sections
    into the Opus-generated digest.

    Snapshot order (jared's 2026-07-15 redesign): Market, Rates, Corporate
    Credit, Private Credit, AI, then Fed Balance Sheet at the bottom of the
    snapshots; the earnings calendar follows them.
    """
    # Find the opening div and header end to insert pre-built sections
    # Insert alerts + the snapshot tables + earnings AFTER the header, before
    # section 1 (the TL;DR box that used to sit here was removed 2026-07-22)
    header_end = digest_html.find('</div>', digest_html.find('border-bottom: 3px double'))
    if header_end != -1:
        # Find the end of the header closing div
        header_end = digest_html.find('>', header_end) + 1

        pre_sections = ""
        if alerts_html:
            pre_sections += alerts_html
        if market_html:
            pre_sections += market_html
        if rates_html:
            pre_sections += rates_html
        if credit_html:
            pre_sections += credit_html
        if private_html:
            pre_sections += private_html
        if ai_html:
            pre_sections += ai_html
        if fed_bs_html:
            pre_sections += fed_bs_html
        if earnings_html:
            pre_sections += earnings_html

        if pre_sections:
            digest_html = digest_html[:header_end] + "\n" + pre_sections + digest_html[header_end:]

    # Append post-digest sections before the closing </div>
    post_sections = ""
    if news_html:
        post_sections += news_html
    if funds_html:
        post_sections += funds_html
    if pacer_html:
        post_sections += pacer_html

    if post_sections and "</div>" in digest_html:
        last_div = digest_html.rfind("</div>")
        digest_html = digest_html[:last_div] + post_sections + digest_html[last_div:]

    return digest_html


def save_daily_digest(html, date=None, team=False):
    """Save the daily digest HTML to disk for weekly summary.

    team=True saves the Substack-free variant alongside (TEAM_DIGEST_SPEC) —
    each variant's weekly wrap synthesizes its own dailies."""
    date = date or datetime.date.today()
    DIGESTS_DIR.mkdir(exist_ok=True)
    suffix = "_team" if team else ""
    filepath = DIGESTS_DIR / f"{date.isoformat()}{suffix}.html"
    filepath.write_text(html, encoding="utf-8")
    print(f"  Saved digest to {filepath}")


def _is_friday():
    """Check if today is Friday."""
    return datetime.date.today().weekday() == 4


def _week_monday(today=None):
    """Monday of the given (default: current) week."""
    today = today or datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _weekly_subject(monday=None, full=False):
    """'📊 Weekly Research Wrap — Week of Monday, July 6' (operator-specified
    wording, 2026-07-10). The 📊 weekly has never matched the reply bot's
    'Re: 📬 Daily Inbox Digest' query, and still doesn't. full=True prepends
    FULL_SUBJECT_MARKER for jared's variant; the team weekly keeps it plain."""
    monday = monday or _week_monday()
    subject = (f"\U0001f4ca Weekly Research Wrap — "
               f"Week of {monday.strftime('%A, %B')} {monday.day}")
    return f"{FULL_SUBJECT_MARKER}{subject}" if full else subject


def save_weekly_digest(html, date=None, team=False):
    """Save the weekly wrap to disk — before this, the sent email was the only
    copy (the 2026-07-10 first-run template check had to be done from the inbox)."""
    date = date or datetime.date.today()
    DIGESTS_DIR.mkdir(exist_ok=True)
    suffix = "_team" if team else ""
    filepath = DIGESTS_DIR / f"weekly_{date.isoformat()}{suffix}.html"
    filepath.write_text(html, encoding="utf-8")
    print(f"  Saved weekly summary to {filepath}")


def _get_week_digests(team=False):
    """Load this week's daily digests for the weekly summary.

    team=True loads the Substack-free variant's dailies — the team wrap must
    be synthesized only from inputs that never contained Substack."""
    if not DIGESTS_DIR.exists():
        return []

    monday = _week_monday()
    suffix = "_team" if team else ""

    digests = []
    for i in range(5):  # Mon-Fri
        d = monday + datetime.timedelta(days=i)
        filepath = DIGESTS_DIR / f"{d.isoformat()}{suffix}.html"
        if filepath.exists():
            digests.append({
                "date": d.isoformat(),
                "day": d.strftime("%A"),
                "html": filepath.read_text(encoding="utf-8"),
            })

    return digests


def generate_weekly_summary(digests, cost_label=""):
    """Generate a weekly summary by synthesizing the week's daily digests with Opus."""
    if not digests:
        return ""

    print(f"  Generating weekly summary from {len(digests)} daily digests...")

    client = anthropic.Anthropic()

    digest_text = ""
    for d in digests:
        digest_text += f"\n{'='*60}\n{d['day']} ({d['date']})\n{'='*60}\n{d['html']}\n"

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=10000,
        system=(
            "You are a senior investment analyst reviewing a week of daily research digests. "
            "Synthesize the key themes, how narratives evolved over the week, what resolved "
            "vs. what remains unresolved, and any emerging patterns to watch next week. "
            "Output HTML using the same Georgia/serif template style as the daily digests."
        ),
        messages=[{"role": "user", "content": (
            "Here are this week's daily research digests. Produce a Weekly Wrap section with:\n"
            "1. Key themes and how they evolved (Mon→Fri)\n"
            "2. What resolved this week\n"
            "3. What's still developing\n"
            "4. Next week's watchlist (catalysts, dates, risks)\n\n"
            "Use the same HTML template styling (Georgia, inline styles, 680px).\n\n"
            f"{digest_text}"
        )}],
    )

    weekly = _strip_to_html(_response_text(response))

    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    print(f"  Weekly summary tokens: {tokens_in:,} in + {tokens_out:,} out")
    cost.record(f"weekly summary{cost_label}", CLAUDE_MODEL, response.usage)

    return weekly


def _digest_subject(full=False):
    """Daily digest subject: '📬 Daily Inbox Digest — <Weekday, Month D>'.

    Built on config.DIGEST_SUBJECT_PREFIX — the exact string reply_monitor's
    Gmail query matches replies against, so the sender and the matcher can't
    drift apart. full=True prepends FULL_SUBJECT_MARKER for jared's Substack-
    inclusive variant (the marker sits before the prefix, which reply matching
    tolerates); the team variant passes full=False and keeps the plain subject.
    """
    day = datetime.date.today().day
    today = datetime.date.today().strftime(f"%A, %B {day}")
    subject = f"{DIGEST_SUBJECT_PREFIX} — {today}"
    return f"{FULL_SUBJECT_MARKER}{subject}" if full else subject


def send_digest_email(service, html_body, recipients=DIGEST_RECIPIENTS, subject=None):
    """Send a digest email via Gmail, with retry for transient SSL errors.

    `subject` overrides the daily default (the weekly wrap passes its own)."""
    day = datetime.date.today().day
    today = datetime.date.today().strftime(f"%A, %B {day}")

    message = MIMEText(html_body, "html")
    message["to"] = ", ".join(recipients)
    message["subject"] = subject or _digest_subject()

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    for attempt in range(3):
        try:
            service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            print(f"Digest sent successfully for {today} to {', '.join(recipients)}")
            return
        except Exception as e:
            if attempt < 2 and ("EOF" in str(e) or "SSL" in str(e) or "BrokenPipe" in str(e)):
                wait = 2 ** attempt
                print(f"  Send attempt {attempt + 1} failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
                # Rebuild the service to get a fresh connection
                service = get_gmail_service()
            else:
                raise


# ======================================================================
# SOURCE REGISTRY + PARALLEL FETCH (efficiency S1 + E1, 2026-07-09)
# ======================================================================

# S1: the 13 independent fetchers main() runs before the Claude passes, as a
# table instead of 13 near-identical try/except blocks. Each row:
# (result key, progress line, failure label, zero-arg callable). Any source
# failing yields [] and the run continues — the same per-source isolation the
# old blocks provided. Gmail, Substack, and 13D are deliberately NOT here:
# Gmail is the auth root, Substack reuses the Gmail service (magic-link
# renewal), and 13D drives Playwright — all three stay serial in main().
SOURCE_FETCHERS = [
    ("sec_filings", "Checking SEC EDGAR filings...", "EDGAR fetch",
     fetch_recent_filings),
    ("news_articles", "Fetching WSJ/FT headlines...", "WSJ/FT fetch",
     fetch_wsj_ft_articles),
    ("market_data", "Fetching market data...", "Market data fetch",
     fetch_market_data),
    ("macro_data", "Fetching FRED macro data...", "Macro data fetch",
     fetch_macro_data),
    ("earnings", "Checking earnings calendar...", "Earnings calendar",
     fetch_earnings_calendar),
    ("pacer_entries", "Checking PACER dockets...", "PACER fetch",
     fetch_pacer_docket),
    ("rating_actions", "Fetching rating actions...", "Rating actions",
     fetch_rating_actions),
    ("fund_results", "Checking 13F fund filings...", "13F tracking",
     fetch_fund_holdings),
    ("research_articles", "Fetching central bank research...", "Research blogs",
     fetch_research_articles),
    ("treasury_auctions", "Fetching Treasury auctions...", "Treasury auctions",
     fetch_treasury_auctions),
    ("cot_data", "Checking CFTC positioning...", "CFTC COT",
     fetch_cot_data),
    ("fed_bs", "Fetching Fed balance sheet...", "Fed balance sheet",
     fetch_fed_balance_sheet),
    ("bank_failures", "Checking FDIC for bank failures...", "FDIC check",
     fetch_failed_banks),
    ("ishares_oas", "Fetching iShares fund OAS...", "iShares OAS",
     fetch_ishares_oas),
]

MAX_FETCH_WORKERS = 6


class _ThreadLocalStdout:
    """stdout proxy that routes each worker thread's prints to its own buffer.

    The fetcher modules print() progress liberally; running them in a pool
    would interleave those lines into log soup. Workers register a per-thread
    buffer; unregistered threads (the main thread) pass through to the real
    stdout. contextlib.redirect_stdout can't do this — it swaps the ONE global
    sys.stdout, so it isn't thread-safe.
    """

    def __init__(self, default):
        import threading
        self._default = default
        self._local = threading.local()

    def register(self, buffer):
        self._local.buffer = buffer

    def unregister(self):
        self._local.buffer = None

    def write(self, s):
        buf = getattr(self._local, "buffer", None)
        return (buf if buf is not None else self._default).write(s)

    def flush(self):
        buf = getattr(self._local, "buffer", None)
        (buf if buf is not None else self._default).flush()


def _fetch_all_sources(registry=None, max_workers=MAX_FETCH_WORKERS):
    """Run the registry fetchers in parallel (E1). Returns {key: result}.

    The pure-HTTP sources are independent, so the ~5-8 min serial fetch phase
    collapses to roughly the slowest source. Each source's output is buffered
    and printed as one coherent block when it completes (completion order);
    per-source rate-limit sleeps stay correct inside their own threads. A
    failed source prints its old failure line and yields [] — isolation
    unchanged from the serial version.
    """
    registry = SOURCE_FETCHERS if registry is None else registry
    results = {}
    proxy = _ThreadLocalStdout(sys.stdout)
    real_stdout = sys.stdout
    started = time.time()

    def _run(entry):
        key, _start_msg, fail_label, fetch = entry
        buffer = io.StringIO()
        proxy.register(buffer)
        try:
            result = fetch()
        except Exception as e:
            print(f"{fail_label} failed: {e} — continuing without.")
            result = []
        finally:
            proxy.unregister()
        return key, result, buffer.getvalue()

    labels = {entry[0]: entry[1] for entry in registry}
    sys.stdout = proxy
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_run, entry) for entry in registry]
            for future in as_completed(futures):
                key, result, output = future.result()
                results[key] = result
                real_stdout.write(labels[key] + "\n")
                if output:
                    real_stdout.write(output if output.endswith("\n") else output + "\n")
    finally:
        sys.stdout = real_stdout

    print(f"Fetch phase: {time.time() - started:.0f}s "
          f"({len(registry)} sources, {max_workers} workers)")
    return results


def main():
    print(f"[{datetime.datetime.now()}] Starting daily digest...")

    # --- Gmail ---
    service = get_gmail_service()
    emails = fetch_recent_emails(service)
    pdf_count = sum(len(e["pdfs"]) for e in emails)
    print(f"Found {len(emails)} emails ({pdf_count} PDF attachments).")

    # --- Substack ---
    print("Fetching Substack articles...")
    try:
        substack_articles = fetch_substack_articles(gmail_service=service)
    except Exception as e:
        print(f"Substack scraping failed: {e} — continuing without.")
        substack_articles = []

    # --- 13D WILTW ---
    print("Checking 13D WILTW...")
    try:
        wiltw = fetch_wiltw()
    except Exception as e:
        print(f"13D WILTW failed: {e} — continuing without.")
        wiltw = None

    # --- The 13 independent sources (S1 registry, fetched in parallel — E1) ---
    fetched = _fetch_all_sources()
    sec_filings = fetched["sec_filings"]
    news_articles = fetched["news_articles"]
    market_data = fetched["market_data"]
    macro_data = fetched["macro_data"]
    earnings = fetched["earnings"]
    pacer_entries = fetched["pacer_entries"]
    rating_actions = fetched["rating_actions"]
    fund_results = fetched["fund_results"]
    research_articles = fetched["research_articles"]
    treasury_auctions = fetched["treasury_auctions"]
    cot_data = fetched["cot_data"]
    fed_bs = fetched["fed_bs"]
    bank_failures = fetched["bank_failures"]
    ishares_oas = fetched["ishares_oas"]

    # --- Check if anything to digest ---
    if not emails and not substack_articles and not sec_filings and not news_articles:
        print("No emails, articles, filings, or news found. Skipping digest.")
        return

    # --- Summarize with Claude ---
    source_count = (f"{len(emails)} emails, {len(substack_articles)} Substack, "
                    f"{len(sec_filings)} SEC filings, {len(news_articles)} WSJ/FT articles, "
                    f"{len(market_data)} market data points, {len(macro_data)} FRED series, "
                    f"{len(rating_actions)} rating actions, {len(fund_results)} 13F filings")
    print(f"Summarizing with Claude ({source_count})...")

    # TEAM_DIGEST_SPEC: Substack is personal to jared, so when TEAM_RECIPIENTS
    # is non-empty a second, Substack-free variant is generated FIRST — its
    # prompt is the shared cache prefix, so the full run that follows reads it
    # and pays only for the substack tail. With the list empty (today), only
    # the full variant runs, exactly as before.
    team_active = bool(TEAM_RECIPIENTS)

    # Post-activation misconfiguration guard (CLEANUP_SPEC 2.1): activation is
    # recorded in config but DIGEST_TO_TEAM is missing from the environment —
    # only the FULL digest generates, and indexing it / feeding memory from it
    # would leak Substack to team askers. This run warns loudly (below), puts
    # an alert in the digest's alert box, skips the memory update, and
    # search._chunks_for_date skips the day's digest chunks. Deliberate
    # retirement of the team variant must unset TEAM_ACTIVATION_DATE (config.py).
    team_misconfigured = (
        bool(TEAM_ACTIVATION_DATE)
        and datetime.date.today().isoformat() >= TEAM_ACTIVATION_DATE
        and not team_active
    )
    if team_misconfigured:
        print("  WARNING: config.TEAM_ACTIVATION_DATE is set but DIGEST_TO_TEAM is "
              "empty — team variant NOT generated. This run's digest chunks will "
              "not be indexed and the shared memory will not be updated "
              "(Substack-leak guard).")

    # Substack-memory context (yesterday's store) for the FULL prompt only
    substack_memory_context = ""
    try:
        substack_memory_context = get_substack_memory_context()
    except Exception as e:
        print(f"Substack memory context failed: {e} — continuing without.")

    shared_kwargs = dict(
        emails=emails,
        sec_filings=sec_filings,
        market_data=market_data,
        macro_data=macro_data,
        earnings=earnings,
        pacer_entries=pacer_entries,
        rating_actions=rating_actions,
        fund_results=fund_results,
        wiltw=wiltw,
        research_articles=research_articles,
        treasury_auctions=treasury_auctions,
        cot_data=cot_data,
        fed_bs=fed_bs,
        bank_failures=bank_failures,
        ishares_oas=ishares_oas,
    )

    team_digest_html = team_source_text = None
    if team_active:
        if not TEAM_ACTIVATION_DATE:
            # The 7/13 validation A/B proved this leaks: pre-cleanse memory.json
            # carries substack-derived storylines that surface in the team digest.
            print("  WARNING: TEAM_RECIPIENTS set but config.TEAM_ACTIVATION_DATE "
                  "is None — run the TEAM_DIGEST_SPEC Stage-5 activation checklist "
                  "(memory cleanse!) or the shared memory can leak Substack "
                  "storylines into the team digest.")
        print("  TEAM variant (Substack-free)...")
        team_digest_html, team_source_text = summarize_with_claude(
            substack_articles=[], cost_label=" (team)", **shared_kwargs)

    digest_html, source_text = summarize_with_claude(
        substack_articles=substack_articles,
        substack_memory_context=substack_memory_context,
        **shared_kwargs)

    # Both variants have generated — now (and only now) the staged ticker-name
    # pairs may hit disk without forking the shared prompt-cache prefix.
    try:
        n_learned = ticker_names.commit()
        if n_learned:
            print(f"  Ticker-name cache: learned {n_learned} new pairing(s).")
    except Exception as e:
        print(f"Ticker-name cache commit failed: {e} — continuing.")

    # --- Custom Alerts (per variant — the team box is evaluated on the team
    # source text, so it can never cite a Substack pub) ---
    print("Evaluating custom alerts...")
    try:
        triggered_alerts = evaluate_alerts(source_text, watchlist=WATCHLIST)
    except Exception as e:
        print(f"Alert evaluation failed: {e} — continuing without.")
        triggered_alerts = []

    team_alerts = []
    if team_active:
        print("Evaluating custom alerts (team source)...")
        try:
            team_alerts = evaluate_alerts(team_source_text, watchlist=WATCHLIST)
        except Exception as e:
            print(f"Team alert evaluation failed: {e} — continuing without.")

    # --- Deterministic signals (appended to BOTH variants' alert boxes) ---
    deterministic_alerts = []

    # Team config guard (CLEANUP_SPEC 2.1): make the misconfiguration visible
    # in the sent email itself, not just the log nobody reads unattended.
    if team_misconfigured:
        deterministic_alerts.append({
            "name": "Team config missing",
            "detail": ("DIGEST_TO_TEAM is unset but team activation is recorded "
                       "(config.TEAM_ACTIVATION_DATE) — only the FULL digest was "
                       "generated; its chunks were NOT indexed and the shared "
                       "memory was NOT updated. Set DIGEST_TO_TEAM in env.bat, or "
                       "unset TEAM_ACTIVATION_DATE if the team variant is retired."),
            "source": "config guard",
        })

    # Fed discount-window stress (numeric, from FRED H.4.1): threshold check on
    # the actual discount-window level. Replaces the old LLM-evaluated "Fed
    # stress signal" rule (removed from alerts_config.json) so the threshold
    # lives in exactly one place: fed_balance_sheet.DISCOUNT_WINDOW_ALERT_MM /
    # _SURGE_MM. Runs even if the LLM alert eval above failed.
    try:
        for signal in check_fed_stress(fed_bs):
            deterministic_alerts.append({
                "name": "Fed stress signal",
                "detail": signal,
                "source": "FRED H.4.1",
            })
    except Exception as e:
        print(f"Fed stress check failed: {e} — continuing without.")

    # Content monitor (O3): record per-source counts; flag a normally-nonzero
    # source stuck at zero (the silent-degradation mode the per-source
    # try/except deliberately swallows). Recorded ONCE per run.
    try:
        counts = {
            "emails": len(emails),
            "substack": len(substack_articles),
            # Articles we actually got FULL text for (CLEANUP_SPEC 4.2): the
            # custom-domain pubs never receive the auth cookie and depend on
            # Substack's unauthenticated per-post API — if that closes, total
            # count stays healthy while full-text collapses. A fulltext
            # zero-streak then fires the existing O3 rule.
            "substack_fulltext": sum(
                1 for a in substack_articles
                if "[preview only" not in (a.get("text") or "")
                and "[Paid-only post" not in (a.get("text") or "")
            ),
            "wiltw": 1 if wiltw else 0,
            **{key: len(fetched[key]) for key in fetched},
        }
        for signal in record_and_check(counts):
            deterministic_alerts.append({
                "name": "Source degradation",
                "detail": signal,
                "source": "content monitor",
            })
    except Exception as e:
        print(f"Content monitor failed: {e} — continuing.")

    triggered_alerts.extend(deterministic_alerts)
    team_alerts.extend(deterministic_alerts)

    # --- Build pre-formatted HTML sections (shared by both variants) ---
    alerts_html = build_alerts_html(triggered_alerts)
    team_alerts_html = build_alerts_html(team_alerts)
    # mirror rows: 20Y UST (FRED) + HYG/LQD OAS (iShares) into Market Snapshot
    market_html = build_market_table_html(market_data, macro_data + ishares_oas)
    rates_html = build_rates_table_html(macro_data)
    # iShares fund-reported OAS rows render after the FRED index OAS rows
    credit_html = build_credit_table_html(macro_data + ishares_oas, market_data)
    private_html = build_private_credit_html(market_data)
    ai_html = build_ai_html(market_data)
    earnings_html = build_earnings_html(earnings)
    # Rank once (Haiku), render per variant with that variant's digest text as
    # the dedupe filter (REDUCE_REPEATS Idea 13) — each variant's appended
    # news list drops headlines its own digest already covers.
    ranked_news = _rank_news_articles(news_articles) if news_articles else []
    news_html = build_news_html(ranked_news, exclude_text=digest_html)
    team_news_html = (build_news_html(ranked_news, exclude_text=team_digest_html)
                      if team_active else "")
    pacer_html = build_pacer_html(pacer_entries)
    # No ratings section is pre-built here — Opus writes the §9 "Rating Actions" section itself from
    # the rating data (see SYSTEM_PROMPT), unlike other sources which pre-render their section.
    # No macro/auctions table either (2026-07-15 snapshot redesign) — both still feed the prompt.
    funds_html = build_funds_html(fund_results)
    fed_bs_html = build_fed_bs_table_html(fed_bs)

    # --- Assemble final digest(s) ---
    final_html = _assemble_digest_html(
        digest_html, alerts_html, market_html, rates_html,
        credit_html, private_html, ai_html,
        earnings_html, news_html, pacer_html,
        funds_html, fed_bs_html,
    )
    team_final_html = None
    if team_active:
        team_final_html = _assemble_digest_html(
            team_digest_html, team_alerts_html, market_html, rates_html,
            credit_html, private_html, ai_html,
            earnings_html, team_news_html, pacer_html,
            funds_html, fed_bs_html,
        )

    # Repetition metric (REDUCE_REPEATS Idea 12): deterministic, $0, never
    # raises. Scores the assembled HTML — the same surface save_daily_digest
    # persists, so live scores and any digests/ backfill are comparable.
    repetition.record_score("full", final_html)
    if team_final_html:
        repetition.record_score("team", team_final_html)

    # --- Save daily digest(s) for weekly summary (each non-fatal on its own) ---
    try:
        save_daily_digest(final_html)
    except Exception as e:
        print(f"Failed to save daily digest: {e}")
    if team_final_html:
        try:
            save_daily_digest(team_final_html, team=True)
        except Exception as e:
            print(f"Failed to save team daily digest: {e}")

    # --- Send digest(s) ---
    print("Sending digest email...")
    send_digest_email(service, final_html, subject=_digest_subject(full=True))
    if team_final_html:
        print("Sending TEAM digest email...")
        send_digest_email(service, team_final_html, recipients=TEAM_RECIPIENTS)

    # --- PACER seen-state (F1a-4): persist only now that the digest(s) actually
    # sent — a crash anywhere earlier leaves the entries unseen for the next run.
    try:
        commit_seen()
    except Exception as e:
        print(f"PACER seen-state commit failed: {e} — continuing.")

    # --- Completion marker: the O2 watchdog (run_alert --check-completed) reads
    # archive/<today>/digest_sent_at.txt to tell a hung/missing run from a done one ---
    try:
        today_dir = DIGESTS_DIR.parent / "archive" / datetime.date.today().isoformat()
        today_dir.mkdir(parents=True, exist_ok=True)
        (today_dir / "digest_sent_at.txt").write_text(
            datetime.datetime.now().isoformat(), encoding="utf-8"
        )
    except Exception:
        pass

    # --- Archive all raw content ---
    print("Archiving content...")
    try:
        today_str = datetime.date.today().isoformat()
        archive_daily_content(
            date=today_str,
            digest_html=final_html,
            digest_team_html=team_final_html or "",
            emails=emails,
            substack_articles=substack_articles,
            sec_filings=sec_filings,
            news_articles=news_articles,
            market_data=market_data,
            macro_data=macro_data,
            rating_actions=rating_actions,
            pacer_entries=pacer_entries,
            fund_results=fund_results,
            wiltw=wiltw,
        )
    except Exception as e:
        print(f"Archiving failed: {e} — continuing.")

    # --- Index into vector search ---
    # (search prefers digest_team.html for the digest chunks when it exists —
    # full-digest prose embeds Substack analysis; see search._chunks_for_date)
    print("Indexing archive for search...")
    try:
        index_daily_content(today_str)
    except Exception as e:
        print(f"Indexing failed: {e} — continuing.")

    # --- Update cross-digest memory (the shared store must stay Substack-free
    # once the team variant exists, so it learns from the team digest then) ---
    if team_misconfigured:
        print("Memory update skipped — post-activation run without a team digest "
              "(the full digest would re-contaminate the cleansed store).")
    else:
        try:
            update_memory(team_final_html if team_final_html else final_html)
        except Exception as e:
            print(f"Memory update failed: {e} — continuing.")

    # --- Update substack memory (Stage 3 — jared-personal storylines) ---
    try:
        update_substack_memory(substack_articles)
    except Exception as e:
        print(f"Substack memory update failed: {e} — continuing.")

    # --- Weekly Summary (Friday only) ---
    if _is_friday():
        print("It's Friday — generating weekly summary...")
        try:
            week_digests = _get_week_digests()
            if len(week_digests) >= 2:  # Need at least 2 days for a meaningful summary
                weekly_html = generate_weekly_summary(week_digests)
                if weekly_html:
                    try:
                        save_weekly_digest(weekly_html)
                    except Exception as e:
                        print(f"Failed to save weekly summary: {e}")
                    send_digest_email(
                        service, weekly_html,
                        subject=_weekly_subject(full=True),
                    )
                    print("Weekly summary sent.")
            else:
                print(f"Only {len(week_digests)} digest(s) this week — skipping weekly summary.")
        except Exception as e:
            print(f"Weekly summary failed: {e}")

        # TEAM weekly wrap (TEAM_DIGEST_SPEC): synthesized only from the team
        # dailies, so it can't contain Substack; the first partial week after
        # activation self-skips on the >=2 check.
        if team_active:
            try:
                team_week = _get_week_digests(team=True)
                if len(team_week) >= 2:
                    team_weekly = generate_weekly_summary(team_week, cost_label=" (team)")
                    if team_weekly:
                        try:
                            save_weekly_digest(team_weekly, team=True)
                        except Exception as e:
                            print(f"Failed to save team weekly summary: {e}")
                        send_digest_email(
                            service, team_weekly,
                            recipients=TEAM_RECIPIENTS,
                            subject=_weekly_subject(),
                        )
                        print("Team weekly summary sent.")
                else:
                    print(f"Only {len(team_week)} team digest(s) this week — "
                          "skipping team weekly summary.")
            except Exception as e:
                print(f"Team weekly summary failed: {e}")

    # --- Per-run Claude cost (every call, not just the two Opus passes) ---
    cost_text, _ = cost.summary()
    print("Claude usage this run:")
    print(cost_text)

    print("Done.")


if __name__ == "__main__":
    main()
