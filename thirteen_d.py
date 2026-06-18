#!/usr/bin/env python3
"""
13D Research "What I Learned This Week" (WILTW) Scraper

Published Thursdays. Downloads the PDF from a predictable URL pattern,
sends it to Opus for summarization, and returns the summary for the digest.

URL pattern: https://client.13d.com/report.php?id=WILTW_YYYY-MM-DD

Usage:
    python thirteen_d.py              # fetch latest WILTW
    python thirteen_d.py --login      # force re-login
"""

import base64
import json
import sys
import datetime
from pathlib import Path

import anthropic

from config import OPUS_MODEL

SCRIPT_DIR = Path(__file__).parent
SESSION_FILE = SCRIPT_DIR / "thirteen_d_session.json"

WILTW_BASE = "https://client.13d.com/report.php?id=WILTW_"
LOGIN_URL = "https://client.13d.com/login.php"
CLAUDE_MODEL = OPUS_MODEL


def _save_session(context):
    state = context.storage_state()
    SESSION_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("  Session saved.")


def _has_session():
    return SESSION_FILE.exists()


def _do_manual_login(playwright):
    print("  Opening browser for 13D Research login...")
    print("  Log in at client.13d.com, then press ENTER here.")
    print("  DO NOT close the browser.")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(LOGIN_URL, wait_until="domcontentloaded")

    input("\n  >>> Press ENTER after logging in (keep browser open)... ")

    try:
        _save_session(context)
    except Exception as e:
        print(f"  Warning: could not save session: {e}")
    try:
        browser.close()
    except Exception:
        pass
    print("  Login complete.")


def _find_latest_thursday():
    """Find the most recent Thursday (WILTW publish day)."""
    today = datetime.date.today()
    # weekday(): Mon=0, Thu=3
    days_since_thursday = (today.weekday() - 3) % 7
    return today - datetime.timedelta(days=days_since_thursday)


def _get_report_url(report_date=None):
    """Build the WILTW report URL for a given date."""
    if report_date is None:
        report_date = _find_latest_thursday()
    return f"{WILTW_BASE}{report_date.isoformat()}"


def _download_pdf(playwright, report_url, force_login=False):
    """Navigate to the report page and download the PDF. Returns PDF bytes or None."""

    if force_login or not _has_session():
        _do_manual_login(playwright)

    print("  Loading session...")
    session_state = json.loads(SESSION_FILE.read_text(encoding="utf-8"))

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=session_state)
    page = context.new_page()

    print(f"  Navigating to {report_url}")
    page.goto(report_url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # Check if we got redirected to login
    if "login" in page.url.lower():
        print("  Session expired — re-login required.")
        browser.close()
        _do_manual_login(playwright)

        session_state = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=session_state)
        page = context.new_page()
        page.goto(report_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        if "login" in page.url.lower():
            print("  Still not logged in. Aborting.")
            browser.close()
            return None

    # Check if the report exists (page might show an error for wrong dates)
    body_text = page.inner_text("body")
    if any(msg in body_text.lower() for msg in ["not found", "no report", "404", "does not exist"]):
        print(f"  Report not found at {report_url}")
        browser.close()
        return None

    # Find the PDF download button/link
    pdf_link = None
    for selector in [
        "a:has-text('Download')",
        "a:has-text('download')",
        "a:has-text('PDF')",
        "a:has-text('pdf')",
        "a[href*='.pdf']",
        "a[href*='download']",
        "button:has-text('Download')",
    ]:
        try:
            el = page.query_selector(selector)
            if el:
                href = el.get_attribute("href") or ""
                if href:
                    if not href.startswith("http"):
                        href = "https://client.13d.com/" + href.lstrip("/")
                    pdf_link = href
                    break
                # If it's a button that triggers a download, click it
                with page.expect_download(timeout=15000) as download_info:
                    el.click()
                download = download_info.value
                pdf_path = SCRIPT_DIR / f"wiltw_{_find_latest_thursday().isoformat()}.pdf"
                download.save_as(str(pdf_path))
                print(f"  Downloaded PDF via button click: {pdf_path}")
                pdf_bytes = pdf_path.read_bytes()
                browser.close()
                return pdf_bytes
        except Exception:
            continue

    if pdf_link:
        print(f"  Found PDF link: {pdf_link}")
        # Download via a new page request to keep cookies
        try:
            resp = page.request.get(pdf_link)
            if resp.ok:
                pdf_bytes = resp.body()
                print(f"  Downloaded PDF: {len(pdf_bytes):,} bytes")

                # Save a copy
                pdf_path = SCRIPT_DIR / "archive" / datetime.date.today().isoformat() / "pdfs"
                pdf_path.mkdir(parents=True, exist_ok=True)
                (pdf_path / f"WILTW_{_find_latest_thursday().isoformat()}.pdf").write_bytes(pdf_bytes)

                _save_session(context)
                browser.close()
                return pdf_bytes
            else:
                print(f"  PDF download failed: HTTP {resp.status}")
        except Exception as e:
            print(f"  PDF download error: {e}")

    # Fallback: try to intercept download from clicking
    print("  Trying button click download fallback...")
    for selector in [
        "a:has-text('Download')", "a:has-text('PDF')",
        "button:has-text('Download')", "button:has-text('PDF')",
    ]:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                with page.expect_download(timeout=15000) as download_info:
                    el.click()
                download = download_info.value
                pdf_path = SCRIPT_DIR / "wiltw_temp.pdf"
                download.save_as(str(pdf_path))
                pdf_bytes = pdf_path.read_bytes()
                pdf_path.unlink()  # clean up temp
                print(f"  Downloaded PDF via click: {len(pdf_bytes):,} bytes")

                _save_session(context)
                browser.close()
                return pdf_bytes
        except Exception:
            continue

    print("  Could not find or download the PDF.")
    _save_session(context)
    browser.close()
    return None


def _summarize_pdf(pdf_bytes):
    """Send the WILTW PDF to Opus for summarization."""
    print("  Summarizing WILTW with Opus...")

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    # Check size — skip if over 25MB
    size_mb = len(pdf_bytes) / (1024 * 1024)
    if size_mb > 25:
        print(f"  PDF too large ({size_mb:.1f}MB) — skipping.")
        return None

    client = anthropic.Anthropic()

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=5000,
        system=(
            "You are summarizing 13D Research's 'What I Learned This Week' (WILTW) report "
            "for a credit/distressed investment analyst. Extract:\n"
            "- The key macro thesis and any shifts from prior weeks\n"
            "- Specific trade ideas, asset class views, or positioning recommendations\n"
            "- Any credit/distressed-relevant insights (spreads, defaults, restructuring)\n"
            "- Geopolitical or policy developments with market implications\n"
            "- Surprising data points or contrarian views\n\n"
            "Be specific — include numbers, names, and dates. Keep it to 500-800 words. "
            "Tag key claims so the digest can attribute them to '(13D Research)'."
        ),
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {
                    "type": "text",
                    "text": "Summarize this WILTW report for a credit/distressed analyst digest.",
                },
            ],
        }],
    )

    summary = response.content[0].text

    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    print(f"  WILTW summary: {tokens_in:,} in + {tokens_out:,} out")
    print(f"  Summary length: {len(summary):,} chars")

    return summary


def fetch_wiltw():
    """
    Main entry point. Downloads the latest WILTW PDF and returns an Opus summary.

    Returns:
        dict with {"title", "date", "summary", "url"} or None if unavailable.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed — skipping 13D WILTW.")
        return None

    report_date = _find_latest_thursday()
    report_url = _get_report_url(report_date)

    # Only fetch if it's Thursday or later in the week (report drops Thursday)
    days_since = (datetime.date.today() - report_date).days
    if days_since > 6:
        print(f"  Latest WILTW ({report_date}) is over 6 days old — skipping.")
        return None

    print(f"  Latest WILTW date: {report_date} ({days_since} days ago)")

    with sync_playwright() as pw:
        pdf_bytes = _download_pdf(pw, report_url)

    if not pdf_bytes:
        return None

    summary = _summarize_pdf(pdf_bytes)
    if not summary:
        return None

    return {
        "title": f"What I Learned This Week — {report_date.strftime('%B %d, %Y')}",
        "date": report_date.isoformat(),
        "summary": summary,
        "url": report_url,
    }


if __name__ == "__main__":
    force_login = "--login" in sys.argv

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed.")
        print("Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    if force_login or not _has_session():
        with sync_playwright() as pw:
            _do_manual_login(pw)

    result = fetch_wiltw()
    if result:
        print(f"\n{'='*60}")
        print(f"Title: {result['title']}")
        print(f"Date: {result['date']}")
        print(f"URL: {result['url']}")
        print(f"\nSummary:\n{result['summary']}")
    else:
        print("\nNo WILTW report available.")
