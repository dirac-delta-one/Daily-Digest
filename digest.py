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

from config import OPUS_MODEL, HAIKU_MODEL, DIGEST_SUBJECT_PREFIX, esc, safe_href
from claude_utils import parse_json_response, json_schema_output, wrapped_array_schema
import cost
from html_utils import extract_gmail_body
from substack import fetch_substack_articles
from sec_filings import fetch_recent_filings
from news import fetch_wsj_ft_articles
from market_data import fetch_market_data, build_market_table_html, format_market_data_for_prompt
from macro_data import fetch_macro_data, build_macro_table_html, format_macro_for_prompt
from memory import get_memory_context, update_memory
from alerts import evaluate_alerts, build_alerts_html
from earnings import fetch_earnings_calendar, build_earnings_html, format_earnings_for_prompt
from trace_data import fetch_trace_data, format_trace_for_prompt, build_trace_html
from pacer import fetch_pacer_docket, format_pacer_for_prompt, build_pacer_html, commit_seen
from ratings import fetch_rating_actions, format_ratings_for_prompt
from fund_tracking import fetch_fund_holdings, format_funds_for_prompt, build_funds_html
from thirteen_d import fetch_wiltw
from fed_research import fetch_research_articles, format_research_for_prompt
from treasury_auctions import fetch_treasury_auctions, format_auctions_for_prompt, build_auctions_table_html
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
# Recipients default to production (jared); override with the DIGEST_TO env var
# (e.g. set DIGEST_TO=acohen@acorninv.com on a test machine). midday.py and
# reply_monitor.py import this, so the override applies there too.
DIGEST_RECIPIENTS = [
    r.strip()
    for r in os.environ.get(
        "DIGEST_TO", "jtramontano@acorninv.com,acorn.research.bot@gmail.com"
    ).split(",")
    if r.strip()
]
CLAUDE_MODEL = OPUS_MODEL

# Paths (relative to this script)
SCRIPT_DIR = Path(__file__).parent
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"  # from Google Cloud Console
TOKEN_FILE = SCRIPT_DIR / "token.json"  # auto-generated after first login
DIGESTS_DIR = SCRIPT_DIR / "digests"  # saved daily digests for weekly summary


def _unattended():
    """True when running headless (DIGEST_UNATTENDED=1 in the server's env)."""
    return os.environ.get("DIGEST_UNATTENDED", "").strip().lower() in ("1", "true", "yes")


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

        # Check for PDF attachments
        pdfs = []
        parts = msg["payload"].get("parts", [])
        if parts:
            pdfs = get_pdf_attachments(service, msg_meta["id"], parts)

        # Extract full body text for archiving/RAG (not sent to Opus — too large)
        body_text = extract_gmail_body(msg["payload"], cap=50000)

        emails.append({
            "from": headers.get("From", "Unknown"),
            "subject": headers.get("Subject", "(no subject)"),
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

SECTIONS — If a section has no content, OMIT IT ENTIRELY and renumber the remaining \
sections sequentially (1, 2, 3...). Do not include empty sections or "none found" messages. \
Do not leave numbering gaps.

0. **TL;DR** — Exactly 3 bold bullets. Each bullet must be ONE LINE, under 20 words. \
No elaboration, no context, no full sentences. Raw signal only. Examples:
   • WTI $112 — Tuesday Hormuz ultimatum is the binary catalyst
   • 5-10yr TIPS: breakevens at 2.36% vs. PIMCO's 4.25% CPI estimate
   • Private credit redemption queue at 2 years, portfolio quality silently deteriorating

1. **Top Takeaways** — The 3-5 most important things from today's inbox. Lead with what's \
new, surprising, or actionable.

2. **Market & Macro** — Key macro themes, economic data, central bank commentary, \
rates/FX/commodities moves mentioned across sources. Reference the actual market data and \
FRED numbers provided — cite specific levels and changes.

3. **Equity Ideas & Calls** — Specific stock mentions, upgrades/downgrades, price target \
changes, earnings takeaways. Always include ticker symbols and any specific numbers \
(targets, multiples, estimates).

4. **Themes & Sector Trends** — Broader sector or thematic trends appearing across \
multiple sources.

5. **Contrarian / Surprising** — Anything that goes against consensus, is unexpected, \
or where two sources disagree with each other.

6. **Worth Reading in Full** — Flag 1-3 items. One line each: \
<a href="URL">Title</a> (Source) — why it's worth reading. \
Hyperlink the title to the source URL. No paragraph descriptions.

7. **Bloomberg** — If any emails are from bloomberg.net, group them here. \
Summarize each with headline and key data points. Keep tight.

8. **Recent SEC Filings** — Filing content is included for each filing. \
For 8-Ks, summarize the material event (what happened, key numbers, implications). \
For Form 4s, note who traded, how many shares, and at what price. \
For other forms, highlight the most important details. \
Organize by company. Include ticker, form type, date, and link to the filing.

9. **Rating Actions** — From the rating agency actions provided (Moody's, S&P, Fitch). \
One line each: entity (with ticker if known), the action (upgrade/downgrade/outlook change) \
and specifics (new rating, notches, rationale). Lead with downgrades and fallen angels — \
they carry the most credit signal. Tag the source at the end of each line.

Sections 10 (WSJ/FT Articles) and 11 (Fund Position Changes) \
are appended separately — do NOT generate those yourself.

Rules:
- Be specific. Include numbers, tickers, dates, and names — not vague summaries.
- If multiple sources discuss the same topic, synthesize them and note where they agree \
or disagree.
- Tag each claim with its source in parentheses at the end, e.g. "(Grant's)" or "(Greenmantle)". \
Be consistent — always at the end of the bullet, never woven into the sentence. \
Only cite real sources: publication names (Grant's, FT, Bloomberg), SEC filing types, \
agency names. NEVER cite "Cross-Digest Memory" or any internal system component as a source.
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

  <!-- TL;DR — always 3 bullets, bold, no header, each UNDER 20 WORDS -->
  <div style="background: #f7f5f0; border-left: 4px solid #1a1a1a; padding: 14px 18px; margin-bottom: 24px; font-size: 15px;">
    <p style="margin: 0 0 6px;"><strong>• {{one-line macro signal}}</strong></p>
    <p style="margin: 0 0 6px;"><strong>• {{one-line trade idea}}</strong></p>
    <p style="margin: 0;"><strong>• {{one-line risk}}</strong></p>
  </div>

  <!-- Sections use this exact pattern. Use these EXACT numbers. Omit sections with no content. -->
  <h2 style="font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 6px; margin: 28px 0 12px;">1. Top Takeaways</h2>
  <ul style="padding-left: 20px; margin: 0;">
    <li style="margin-bottom: 10px; font-size: 14px;">{{content}} <span style="color: #888;">(Source)</span></li>
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
  <!-- Sources: span with color #888, always at end of bullet -->
  <!-- Tickers: <strong>$TICK</strong> whenever a ticker appears -->
  <!-- Hyperlinks: <a href="URL" style="color: #1a5276;">linked text</a> -->

</div>

Follow this template exactly. Same fonts, same sizes, same spacing every single time.
"""


def _build_source_prompt(*, emails, substack_articles, sec_filings, market_data,
                         macro_data, memory_context, earnings, trace_data, pacer_entries,
                         rating_actions=None, fund_results=None,
                         wiltw=None,
                         research_articles=None, treasury_auctions=None,
                         cot_data=None, fed_bs=None, bank_failures=None):
    """Build the full source material text for the Opus prompt.

    Keyword-only (Phase 3.1): with 17 same-typed source arguments, positional
    calls were a misroute footgun — `*` forces every caller to name each source.
    """
    # Email metadata
    email_lines = []
    for i, e in enumerate(emails):
        pdf_note = ""
        if e["pdfs"]:
            names = ", ".join(p["filename"] for p in e["pdfs"])
            pdf_note = f"\n📎 PDF attachments (included below): {names}"

        email_lines.append(
            f"--- Email {i+1} ---\n"
            f"From: {e['from']}\n"
            f"Subject: {e['subject']}\n"
            f"Date: {e['date']}\n"
            f"Preview: {e['snippet']}"
            f"{pdf_note}"
        )

    pdf_count = sum(len(e["pdfs"]) for e in emails)
    pdf_note = ""
    if pdf_count > 0:
        pdf_note = (
            f" {pdf_count} PDF attachment(s) are included after the email list — "
            "extract and synthesize their key content."
        )

    substack_note = ""
    if substack_articles:
        substack_note = (
            f"\n\nAdditionally, {len(substack_articles)} paid Substack articles are included below. "
            "Treat these as primary research sources — summarize their key arguments, "
            "data points, and investment implications."
        )

    prompt = (
        f"Here are {len(emails)} emails from my inbox in the last {HOURS_LOOKBACK} hours."
        f"{pdf_note}{substack_note}\n\n"
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

    # Earnings calendar
    earnings_text = format_earnings_for_prompt(earnings)
    if earnings_text:
        prompt += "\n\n" + "=" * 40 + "\n" + earnings_text + "\n" + "=" * 40

    # Cross-digest memory
    if memory_context:
        prompt += "\n\n" + "=" * 40 + "\n" + memory_context + "\n" + "=" * 40

    # Substack articles
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
        prompt += "\n\n" + "=" * 40 + "\nSUBSTACK ARTICLES:\n" + "=" * 40 + "\n\n"
        prompt += "\n\n".join(substack_lines)

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

    # TRACE bond data
    trace_text = format_trace_for_prompt(trace_data)
    if trace_text:
        prompt += "\n\n" + "=" * 40 + "\n" + trace_text + "\n" + "=" * 40

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

    return prompt


def _strip_to_html(text):
    """Drop any model preamble before the first <div — the emailed HTML must
    start at the template (Opus occasionally prefixes a sentence of prose).
    Used by digest pass 2 and the weekly summary; midday has its own copy."""
    i = text.find("<div")
    return text[i:] if i > 0 else text


def summarize_with_claude(*, emails, substack_articles=None, sec_filings=None,
                          market_data=None, macro_data=None, earnings=None,
                          trace_data=None, pacer_entries=None,
                          rating_actions=None, fund_results=None,
                          wiltw=None,
                          research_articles=None, treasury_auctions=None,
                          cot_data=None, fed_bs=None, bank_failures=None):
    """Send all sources to Claude for digest generation (2-pass).

    Keyword-only (Phase 3.1) — see `_build_source_prompt` for the rationale.
    """
    client = anthropic.Anthropic()
    substack_articles = substack_articles or []
    sec_filings = sec_filings or []
    market_data = market_data or []
    macro_data = macro_data or []
    earnings = earnings or []
    trace_data = trace_data or []
    pacer_entries = pacer_entries or []
    rating_actions = rating_actions or []
    fund_results = fund_results or []
    research_articles = research_articles or []
    treasury_auctions = treasury_auctions or []
    cot_data = cot_data or []
    fed_bs = fed_bs or []
    bank_failures = bank_failures or []

    # Get cross-digest memory context
    memory_context = get_memory_context()

    # Build full source prompt
    prompt = _build_source_prompt(
        emails=emails,
        substack_articles=substack_articles,
        sec_filings=sec_filings,
        market_data=market_data,
        macro_data=macro_data,
        memory_context=memory_context,
        earnings=earnings,
        trace_data=trace_data,
        pacer_entries=pacer_entries,
        rating_actions=rating_actions,
        fund_results=fund_results,
        wiltw=wiltw,
        research_articles=research_articles,
        treasury_auctions=treasury_auctions,
        cot_data=cot_data,
        fed_bs=fed_bs,
        bank_failures=bank_failures,
    )

    # Build the content array for Claude's messages API
    content = [{"type": "text", "text": prompt}]

    # Add each PDF as a document block
    for e in emails:
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
    content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}

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

    draft = response.content[0].text

    # Log token usage
    p1_input = response.usage.input_tokens
    p1_output = response.usage.output_tokens
    print(f"  Pass 1 tokens: {p1_input:,} in + {p1_output:,} out")
    cost.record("digest pass 1", CLAUDE_MODEL, response.usage)

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
            "1. Identify any important items that were MISSED — specific data points, trade "
            "ideas, tickers, price targets, key arguments, or surprising findings that should "
            "have been included but weren't.\n"
            "2. Check for any ERRORS — wrong numbers, misattributed sources, or mischaracterized "
            "arguments.\n"
            "3. Check that every bullet has a source tag.\n"
            "4. Produce a FINAL ENHANCED VERSION of the digest that incorporates anything missed "
            "and fixes any errors. Keep the exact same HTML template and formatting.\n\n"
            "If the draft was already comprehensive, return it mostly unchanged — don't pad it "
            "with filler.\n\n"
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

    final = _strip_to_html(review_response.content[0].text)

    # Log total token usage
    p2_input = review_response.usage.input_tokens
    p2_output = review_response.usage.output_tokens
    print(f"  Pass 2 tokens: {p2_input:,} in + {p2_output:,} out")
    cost.record("digest pass 2", CLAUDE_MODEL, review_response.usage)

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

    return final, prompt  # Return prompt too for alert evaluation


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


def build_news_html(articles):
    """Generate the WSJ/FT section as pre-formatted HTML with real hyperlinks."""
    if not articles:
        return ""

    # Rank and trim to top 15
    articles = _rank_news_articles(articles, max_articles=15)

    html = (
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; '
        'padding-bottom: 6px; margin: 28px 0 12px;">10. WSJ/FT Articles</h2>\n'
        '<ul style="padding-left: 20px; margin: 0;">\n'
    )

    for a in articles:
        title = a.get("title", "")
        url = a.get("url", "")
        summary = a.get("summary", "")
        source = a.get("source", "")

        # Source color
        src_color = "#0274b6" if source == "WSJ" else "#f26f21"

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


def _assemble_digest_html(digest_html, alerts_html, market_html, macro_html,
                          earnings_html, news_html, trace_html, pacer_html,
                          funds_html="",
                          auctions_html="", fed_bs_html=""):
    """
    Assemble the final digest HTML by injecting pre-built sections
    into the Opus-generated digest.
    """
    # Find the opening div and header end to insert pre-built sections
    # Insert alerts + market + macro + earnings AFTER the header, BEFORE the TL;DR
    header_end = digest_html.find('</div>', digest_html.find('border-bottom: 3px double'))
    if header_end != -1:
        # Find the end of the header closing div
        header_end = digest_html.find('>', header_end) + 1

        pre_sections = ""
        if alerts_html:
            pre_sections += alerts_html
        if market_html:
            pre_sections += market_html
        if macro_html:
            pre_sections += macro_html
        if earnings_html:
            pre_sections += earnings_html
        if fed_bs_html:
            pre_sections += fed_bs_html
        if auctions_html:
            pre_sections += auctions_html

        if pre_sections:
            digest_html = digest_html[:header_end] + "\n" + pre_sections + digest_html[header_end:]

    # Append post-digest sections before the closing </div>
    post_sections = ""
    if news_html:
        post_sections += news_html
    if funds_html:
        post_sections += funds_html
    if trace_html:
        post_sections += trace_html
    if pacer_html:
        post_sections += pacer_html

    if post_sections and "</div>" in digest_html:
        last_div = digest_html.rfind("</div>")
        digest_html = digest_html[:last_div] + post_sections + digest_html[last_div:]

    return digest_html


def save_daily_digest(html, date=None):
    """Save the daily digest HTML to disk for weekly summary."""
    date = date or datetime.date.today()
    DIGESTS_DIR.mkdir(exist_ok=True)
    filepath = DIGESTS_DIR / f"{date.isoformat()}.html"
    filepath.write_text(html, encoding="utf-8")
    print(f"  Saved digest to {filepath}")


def _is_friday():
    """Check if today is Friday."""
    return datetime.date.today().weekday() == 4


def _week_monday(today=None):
    """Monday of the given (default: current) week."""
    today = today or datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _weekly_subject(monday=None):
    """'📊 Weekly Research Wrap — Week of Monday, July 6' (operator-specified
    wording, 2026-07-10). The 📊 weekly has never matched the reply bot's
    'Re: 📬 Daily Inbox Digest' query, and still doesn't."""
    monday = monday or _week_monday()
    return (f"\U0001f4ca Weekly Research Wrap — "
            f"Week of {monday.strftime('%A, %B')} {monday.day}")


def save_weekly_digest(html, date=None):
    """Save the weekly wrap to disk — before this, the sent email was the only
    copy (the 2026-07-10 first-run template check had to be done from the inbox)."""
    date = date or datetime.date.today()
    DIGESTS_DIR.mkdir(exist_ok=True)
    filepath = DIGESTS_DIR / f"weekly_{date.isoformat()}.html"
    filepath.write_text(html, encoding="utf-8")
    print(f"  Saved weekly summary to {filepath}")


def _get_week_digests():
    """Load this week's daily digests for the weekly summary."""
    if not DIGESTS_DIR.exists():
        return []

    monday = _week_monday()

    digests = []
    for i in range(5):  # Mon-Fri
        d = monday + datetime.timedelta(days=i)
        filepath = DIGESTS_DIR / f"{d.isoformat()}.html"
        if filepath.exists():
            digests.append({
                "date": d.isoformat(),
                "day": d.strftime("%A"),
                "html": filepath.read_text(encoding="utf-8"),
            })

    return digests


def generate_weekly_summary(digests):
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

    weekly = _strip_to_html(response.content[0].text)

    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    print(f"  Weekly summary tokens: {tokens_in:,} in + {tokens_out:,} out")
    cost.record("weekly summary", CLAUDE_MODEL, response.usage)

    return weekly


def _digest_subject():
    """Daily digest subject: '📬 Daily Inbox Digest — <Weekday, Month D>'.

    Built on config.DIGEST_SUBJECT_PREFIX — the exact string reply_monitor's
    Gmail query matches replies against, so the sender and the matcher can't
    drift apart.
    """
    day = datetime.date.today().day
    today = datetime.date.today().strftime(f"%A, %B {day}")
    return f"{DIGEST_SUBJECT_PREFIX} — {today}"


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

# S1: the 14 independent fetchers main() runs before the Claude passes, as a
# table instead of 14 near-identical try/except blocks. Each row:
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
    ("trace_data", "Fetching TRACE bond data...", "TRACE fetch",
     fetch_trace_data),
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

    # --- The 14 independent sources (S1 registry, fetched in parallel — E1) ---
    fetched = _fetch_all_sources()
    sec_filings = fetched["sec_filings"]
    news_articles = fetched["news_articles"]
    market_data = fetched["market_data"]
    macro_data = fetched["macro_data"]
    earnings = fetched["earnings"]
    trace_data = fetched["trace_data"]
    pacer_entries = fetched["pacer_entries"]
    rating_actions = fetched["rating_actions"]
    fund_results = fetched["fund_results"]
    research_articles = fetched["research_articles"]
    treasury_auctions = fetched["treasury_auctions"]
    cot_data = fetched["cot_data"]
    fed_bs = fetched["fed_bs"]
    bank_failures = fetched["bank_failures"]

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

    digest_html, source_text = summarize_with_claude(
        emails=emails,
        substack_articles=substack_articles,
        sec_filings=sec_filings,
        market_data=market_data,
        macro_data=macro_data,
        earnings=earnings,
        trace_data=trace_data,
        pacer_entries=pacer_entries,
        rating_actions=rating_actions,
        fund_results=fund_results,
        wiltw=wiltw,
        research_articles=research_articles,
        treasury_auctions=treasury_auctions,
        cot_data=cot_data,
        fed_bs=fed_bs,
        bank_failures=bank_failures,
    )

    # --- Custom Alerts ---
    print("Evaluating custom alerts...")
    try:
        triggered_alerts = evaluate_alerts(source_text)
    except Exception as e:
        print(f"Alert evaluation failed: {e} — continuing without.")
        triggered_alerts = []

    # --- Fed discount-window stress (numeric, from FRED H.4.1) ---
    # Deterministic threshold check on the actual discount-window level, merged
    # into the same alert box. Replaces the old LLM-evaluated "Fed stress signal"
    # rule (removed from alerts_config.json) so the threshold lives in exactly one
    # place: fed_balance_sheet.DISCOUNT_WINDOW_ALERT_MM / _SURGE_MM. Runs even if
    # the LLM alert eval above failed.
    try:
        for signal in check_fed_stress(fed_bs):
            triggered_alerts.append({
                "name": "Fed stress signal",
                "detail": signal,
                "source": "FRED H.4.1",
            })
    except Exception as e:
        print(f"Fed stress check failed: {e} — continuing without.")

    # --- Content monitor (O3): record per-source counts; flag a normally-
    # nonzero source stuck at zero (the silent-degradation mode the per-source
    # try/except deliberately swallows). Signals merge into the same alert box.
    try:
        counts = {
            "emails": len(emails),
            "substack": len(substack_articles),
            "wiltw": 1 if wiltw else 0,
            **{key: len(fetched[key]) for key in fetched},
        }
        for signal in record_and_check(counts):
            triggered_alerts.append({
                "name": "Source degradation",
                "detail": signal,
                "source": "content monitor",
            })
    except Exception as e:
        print(f"Content monitor failed: {e} — continuing.")

    # --- Build pre-formatted HTML sections ---
    alerts_html = build_alerts_html(triggered_alerts)
    market_html = build_market_table_html(market_data)
    macro_html = build_macro_table_html(macro_data)
    earnings_html = build_earnings_html(earnings)
    news_html = build_news_html(news_articles)
    trace_html = build_trace_html(trace_data)
    pacer_html = build_pacer_html(pacer_entries)
    # No ratings section is pre-built here — Opus writes the §9 "Rating Actions" section itself from
    # the rating data (see SYSTEM_PROMPT), unlike other sources which pre-render their section.
    funds_html = build_funds_html(fund_results)
    auctions_html = build_auctions_table_html(treasury_auctions)
    fed_bs_html = build_fed_bs_table_html(fed_bs)

    # --- Assemble final digest ---
    final_html = _assemble_digest_html(
        digest_html, alerts_html, market_html, macro_html,
        earnings_html, news_html, trace_html, pacer_html,
        funds_html,
        auctions_html, fed_bs_html,
    )

    # --- Save daily digest for weekly summary ---
    try:
        save_daily_digest(final_html)
    except Exception as e:
        print(f"Failed to save daily digest: {e}")

    # --- Send digest ---
    print("Sending digest email...")
    send_digest_email(service, final_html)

    # --- PACER seen-state (F1a-4): persist only now that the digest actually
    # sent — a crash anywhere earlier leaves the entries unseen for the next run.
    try:
        commit_seen()
    except Exception as e:
        print(f"PACER seen-state commit failed: {e} — continuing.")

    # --- Save timestamp for midday.py ---
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
    print("Indexing archive for search...")
    try:
        index_daily_content(today_str)
    except Exception as e:
        print(f"Indexing failed: {e} — continuing.")

    # --- Update cross-digest memory ---
    try:
        update_memory(final_html)
    except Exception as e:
        print(f"Memory update failed: {e} — continuing.")

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
                        subject=_weekly_subject(),
                    )
                    print("Weekly summary sent.")
            else:
                print(f"Only {len(week_digests)} digest(s) this week — skipping weekly summary.")
        except Exception as e:
            print(f"Weekly summary failed: {e}")

    # --- Per-run Claude cost (every call, not just the two Opus passes) ---
    cost_text, _ = cost.summary()
    print("Claude usage this run:")
    print(cost_text)

    print("Done.")


if __name__ == "__main__":
    main()
