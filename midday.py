#!/usr/bin/env python3
"""
Midday Breaking Alert
Runs at ~1 PM ET. Checks for new material since the morning digest.
ONLY sends an email if something genuinely important happened.
Most days it sends nothing.

Usage:
    python midday.py           # run the midday check
    python midday.py --force   # send alert even if not material (for testing)
"""

import base64
import datetime
import sys
from email.mime.text import MIMEText
from pathlib import Path

import anthropic

from digest import get_gmail_service, DIGEST_RECIPIENTS
from news import fetch_wsj_ft_articles
from sec_filings import fetch_recent_filings
from ratings import fetch_rating_actions
import cost

SCRIPT_DIR = Path(__file__).parent
ARCHIVE_DIR = SCRIPT_DIR / "archive"

SONNET_MODEL = "claude-sonnet-4-6"

MATERIALITY_PROMPT = """\
You are evaluating whether any of the following new content warrants an
intraday alert to a credit/distressed investment analyst.

ONLY trigger an alert if you find:
- A new Chapter 11 bankruptcy filing (especially >$500M)
- A significant rating action (downgrade, especially to junk)
- A surprise Fed action or emergency statement
- HY or IG spreads moving >15bps intraday
- A major geopolitical escalation affecting markets
- A material 8-K from a watchlist company (CEO departure, covenant breach, M&A)
- A significant market move (S&P down >2%, oil move >5%)
- Breaking news that would materially affect credit markets

If NONE of these apply, respond with exactly: NO_ALERT

If any apply, respond with TWO things separated by a line of equals signs:
1. A short subject line description (under 60 chars, no quotes)
2. A short HTML alert body using the same digest template styling (Georgia, 680px,
   inline styles). Keep it to 3-5 bullets max. Include source tags.

Example format:
Moody's downgrades XYZ Corp to junk
========================================
<div style="font-family: Georgia, serif; max-width: 680px; ...">
<ul>...alert content...</ul>
</div>
"""


def _load_morning_timestamp():
    """Load the timestamp of when the morning digest was sent."""
    today = datetime.date.today().isoformat()
    ts_file = ARCHIVE_DIR / today / "digest_sent_at.txt"

    if ts_file.exists():
        try:
            ts_str = ts_file.read_text().strip()
            return datetime.datetime.fromisoformat(ts_str)
        except Exception:
            pass

    # Fallback: assume morning digest ran at 8 AM today
    today_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(8, 0))
    return today_dt


def _fetch_new_emails(service, cutoff):
    """Fetch emails received after the morning digest cutoff."""
    after_ts = int(cutoff.timestamp())
    query = f"after:{after_ts} in:inbox"

    try:
        results = service.users().messages().list(
            userId="me", q=query, maxResults=30,
        ).execute()
    except Exception as e:
        print(f"  Gmail fetch error: {e}")
        return []

    messages = results.get("messages", [])
    if not messages:
        return []

    emails = []
    for msg_meta in messages:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_meta["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            snippet = msg.get("snippet", "")

            emails.append({
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", ""),
                "snippet": snippet,
            })
        except Exception:
            continue

    return emails


def evaluate_materiality(emails, articles, filings, rating_actions):
    """Ask Sonnet to evaluate whether new content is material."""
    # Build source text
    parts = []

    if emails:
        lines = [f"--- Email: {e['subject']} (from {e['from']})\n{e['snippet']}" for e in emails]
        parts.append(f"NEW EMAILS ({len(emails)}):\n" + "\n\n".join(lines))

    if articles:
        lines = [f"--- [{a['source']}] {a['title']}\n{a.get('summary', '')}" for a in articles]
        parts.append(f"NEW WSJ/FT ARTICLES ({len(articles)}):\n" + "\n\n".join(lines))

    if filings:
        lines = []
        for f in filings:
            line = f"--- {f['ticker']} ({f['company']}): {f['form_type']} filed {f['date']}"
            content = f.get("content", "")
            if content and not content.startswith("["):
                line += f"\n{content[:500]}"
            lines.append(line)
        parts.append(f"NEW SEC FILINGS ({len(filings)}):\n" + "\n\n".join(lines))

    if rating_actions:
        lines = [f"--- [{a['source']}] {a['title']}\n{a.get('description', '')}" for a in rating_actions]
        parts.append(f"RATING ACTIONS ({len(rating_actions)}):\n" + "\n\n".join(lines))

    source_text = "\n\n" + "=" * 40 + "\n\n".join(parts)

    client = anthropic.Anthropic()

    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=2000,
        system=MATERIALITY_PROMPT,
        messages=[{"role": "user", "content": source_text}],
    )

    result = response.content[0].text.strip()

    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    print(f"  Materiality check: {tokens_in:,} in + {tokens_out:,} out")
    cost.record("midday materiality", SONNET_MODEL, response.usage)

    return result


def send_alert_email(service, subject_desc, alert_html):
    """Send the midday alert email."""
    message = MIMEText(alert_html, "html")
    message["to"] = ", ".join(DIGEST_RECIPIENTS)
    message["subject"] = f"\U0001f6a8 Midday Alert — {subject_desc}"

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()

    print(f"  Alert sent: {subject_desc}")

    # Archive
    today_dir = ARCHIVE_DIR / datetime.date.today().isoformat()
    today_dir.mkdir(parents=True, exist_ok=True)
    (today_dir / "midday_alert.html").write_text(alert_html, encoding="utf-8")


def main():
    force = "--force" in sys.argv

    print(f"[{datetime.datetime.now()}] Midday alert check...")

    cutoff = _load_morning_timestamp()
    print(f"  Morning digest cutoff: {cutoff}")

    service = get_gmail_service()

    # Fetch new content since morning
    print("  Checking for new emails...")
    new_emails = _fetch_new_emails(service, cutoff)
    print(f"  {len(new_emails)} new emails since morning.")

    print("  Checking WSJ/FT RSS...")
    try:
        new_articles = fetch_wsj_ft_articles(since_datetime=cutoff)
    except Exception as e:
        print(f"  RSS failed: {e}")
        new_articles = []
    print(f"  {len(new_articles)} new articles.")

    print("  Checking EDGAR...")
    try:
        new_filings = fetch_recent_filings(since_datetime=cutoff)
    except Exception as e:
        print(f"  EDGAR failed: {e}")
        new_filings = []
    print(f"  {len(new_filings)} new filings.")

    print("  Checking rating actions...")
    try:
        new_ratings = fetch_rating_actions(since_datetime=cutoff)
    except Exception as e:
        print(f"  Ratings failed: {e}")
        new_ratings = []
    print(f"  {len(new_ratings)} rating actions.")

    total = len(new_emails) + len(new_articles) + len(new_filings) + len(new_ratings)
    if total == 0 and not force:
        print("  No new content since morning. Exiting.")
        return

    print(f"  Evaluating materiality ({total} items)...")
    result = evaluate_materiality(new_emails, new_articles, new_filings, new_ratings)
    cost_text, _ = cost.summary()
    print(cost_text)

    if result.strip() == "NO_ALERT" and not force:
        print("  Nothing material. No alert sent.")
        return

    # Parse the result: first line = subject, rest = HTML (after separator)
    if "=" * 10 in result:
        parts = result.split("=" * 10, 1)
        subject_desc = parts[0].strip().split("\n")[-1].strip()
        alert_html = parts[1].strip() if len(parts) > 1 else result
    else:
        subject_desc = result[:60].replace("\n", " ")
        alert_html = result

    # Strip any preamble before HTML
    html_start = alert_html.find("<div")
    if html_start > 0:
        alert_html = alert_html[html_start:]

    print(f"  ALERT: {subject_desc}")
    send_alert_email(service, subject_desc, alert_html)

    print("Done.")


if __name__ == "__main__":
    main()
