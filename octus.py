#!/usr/bin/env python3
"""
Octus (formerly Reorg) Intelligence Scraper + Primary Deal Tracker

Uses Playwright to scrape:
  1. Intel feed — articles, filtered to top 5 most relevant by Sonnet
  2. Primary deal tracker — new issue deals with yield >= 8% or price talk

Usage:
    python octus.py              # scrape both (login if needed)
    python octus.py --login      # force re-login
    python octus.py --debug      # visible browser, screenshot, dump HTML
    python octus.py --deals      # scrape deals only
    python octus.py --articles   # scrape articles only
"""

import json
import re
import sys
import time
import datetime
from pathlib import Path

import anthropic

SCRIPT_DIR = Path(__file__).parent
SESSION_FILE = SCRIPT_DIR / "octus_session.json"

HOURS_LOOKBACK = 24
MAX_ARTICLES_RAW = 15       # fetch up to 15, then Sonnet picks top 5
MAX_ARTICLES_FINAL = 5
MAX_ARTICLE_CHARS = 8000
YIELD_THRESHOLD = 8.0       # minimum yield % to include a deal

OCTUS_BASE = "https://app.octus.com"
OCTUS_INTEL = "https://app.octus.com/v3#/items/intel"
OCTUS_DEALS = "https://app.octus.com/v3#/primary-tracker/deals"

SONNET_MODEL = "claude-sonnet-4-6"


# ======================================================================
# SESSION / AUTH
# ======================================================================

def _save_session(context):
    state = context.storage_state()
    SESSION_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("  Session saved.")


def _has_session():
    return SESSION_FILE.exists()


def _do_manual_login(playwright):
    print("  Opening browser for manual Octus login...")
    print("  Log in to Octus in the browser window.")
    print("  DO NOT close the browser — come back here and press ENTER when done.")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(OCTUS_BASE, wait_until="domcontentloaded")

    input("\n  >>> Press ENTER after logging in (keep the browser open)... ")

    try:
        _save_session(context)
    except Exception as e:
        print(f"  Warning: could not save session: {e}")
    try:
        browser.close()
    except Exception:
        pass
    print("  Login complete.")


def _is_logged_in(page):
    url = page.url.lower()
    if "login" in url or "auth" in url or "signin" in url:
        return False
    try:
        if page.query_selector('input[type="password"]'):
            return False
    except Exception:
        pass
    return True


def _dismiss_overlays(page):
    for selector in [
        "button:has-text('Dismiss')", "button:has-text('Skip')",
        "button:has-text('Close')", "button:has-text('Got it')",
        "[class*='pendo-close']", "[class*='pendo'] button",
        "#onetrust-accept-btn-handler",
    ]:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(500)
        except Exception:
            continue
    try:
        page.evaluate("""
            document.querySelectorAll('[class*="basics-card"], [class*="pendo"], [class*="questions-button"]')
                .forEach(el => el.style.display = 'none');
        """)
    except Exception:
        pass


def _get_browser_and_page(playwright, force_login=False):
    """Get an authenticated browser page. Handles login/re-login."""
    if force_login or not _has_session():
        _do_manual_login(playwright)

    session_state = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=session_state)
    page = context.new_page()
    return browser, context, page


def _ensure_logged_in(playwright, browser, context, page, target_url):
    """Navigate to target_url, re-login if session expired. Returns new page."""
    page.goto(target_url, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)

    if _is_logged_in(page):
        return browser, context, page

    print("  Session expired — re-login required.")
    browser.close()
    _do_manual_login(playwright)

    session_state = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=session_state)
    page = context.new_page()
    page.goto(target_url, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)

    if not _is_logged_in(page):
        print("  Still not logged in. Aborting.")
        browser.close()
        return None, None, None

    return browser, context, page


def _parse_date_str(date_str):
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


# ======================================================================
# INTEL ARTICLES
# ======================================================================

def _scrape_articles(page):
    """Extract articles from the intel feed page. Returns raw list."""
    _dismiss_overlays(page)

    items = page.query_selector_all(".base-item-list-for-card--item")
    if not items:
        items = page.query_selector_all("[class*='item-list-for-card--item']")

    print(f"    Found {len(items)} feed items in DOM.")

    cutoff = datetime.datetime.now() - datetime.timedelta(hours=HOURS_LOOKBACK)
    articles = []

    for item_el in items:
        try:
            item_id = item_el.get_attribute("id") or ""
            date_str = item_el.get_attribute("date") or ""
            highlight = item_el.get_attribute("highlight") or ""
            company = item_el.get_attribute("master_company_name") or ""

            parsed_date = _parse_date_str(date_str)
            if parsed_date and parsed_date < cutoff:
                continue

            # Extract title from headline element
            title = ""
            try:
                headline_el = item_el.query_selector("[class*='headline'], [class*='title'], h3, h4, a")
                if headline_el:
                    title = headline_el.inner_text().strip()
            except Exception:
                pass
            if not title:
                try:
                    title = item_el.inner_text().strip().split("\n")[0].strip()
                except Exception:
                    pass
            if not title or len(title) < 10:
                title = highlight[:200].strip()

            preview = highlight
            if not title or len(title) < 5:
                continue

            title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            preview = preview.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&rsquo;", "'")

            if len(preview) > MAX_ARTICLE_CHARS:
                preview = preview[:MAX_ARTICLE_CHARS] + "\n[...truncated]"

            articles.append({
                "title": title,
                "author": "Octus",
                "url": f"https://app.octus.com/v3#/items/intel/{item_id}" if item_id else OCTUS_INTEL,
                "text": preview if preview else title,
                "date": date_str,
                "company": company,
            })
        except Exception as e:
            print(f"    Error parsing item: {e}")

    print(f"    Parsed {len(articles)} articles within lookback window.")
    return articles


def _rank_articles(articles):
    """Use Sonnet to pick the top 5 most relevant articles for a credit/distressed investor."""
    if len(articles) <= MAX_ARTICLES_FINAL:
        return articles

    print(f"  Ranking {len(articles)} Octus articles by relevance...")

    article_list = ""
    for i, a in enumerate(articles):
        article_list += f"{i}. [{a.get('company', '')}] {a['title']}\n"
        # Include first 150 chars of preview for context
        preview = a["text"][:150].replace("\n", " ")
        if preview:
            article_list += f"   {preview}\n"

    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=200,
            system=(
                "You are selecting the most relevant articles for a credit/distressed "
                "investment analyst. Prioritize: bankruptcy filings, restructuring updates, "
                "distressed credit analysis, rating downgrades, covenant issues, "
                "LME/distressed exchanges, DIP financing, Ch.11 developments, "
                "private credit analysis. Deprioritize: routine affirmations, "
                "minor outlook changes, general market commentary."
            ),
            messages=[{"role": "user", "content": (
                f"Pick the {MAX_ARTICLES_FINAL} most relevant from these {len(articles)} Octus articles. "
                f"Return ONLY a JSON array of index numbers.\n\n{article_list}"
            )}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        indices = json.loads(text)
        ranked = [articles[i] for i in indices if isinstance(i, int) and 0 <= i < len(articles)]

        print(f"  Ranked: kept {len(ranked)}/{len(articles)} articles "
              f"({response.usage.input_tokens:,} in + {response.usage.output_tokens:,} out)")
        return ranked if ranked else articles[:MAX_ARTICLES_FINAL]

    except Exception as e:
        print(f"  Ranking failed ({e}) — keeping first {MAX_ARTICLES_FINAL}.")
        return articles[:MAX_ARTICLES_FINAL]


# ======================================================================
# PRIMARY DEAL TRACKER
# ======================================================================

def _scrape_deals(page):
    """Scrape the primary deal tracker table for HY deals with yield >= 8%."""
    _dismiss_overlays(page)

    # The deals page is a table. Wait for it to render.
    page.wait_for_timeout(3000)

    # Try to find the table
    table = page.query_selector("table")
    if not table:
        print("    No deal table found on page.")
        # Dump what's there for debugging
        body_text = page.inner_text("body")[:500]
        print(f"    Page text: {body_text[:200]}")
        return []

    # Extract headers
    header_els = table.query_selector_all("thead th, thead td")
    headers = [h.inner_text().strip().lower() for h in header_els]
    print(f"    Table headers: {headers}")

    # Map header names to indices — flexible matching
    col_map = {}
    for i, h in enumerate(headers):
        h_lower = h.lower()
        if "issuer" in h_lower or "entity" in h_lower or "company" in h_lower or "borrower" in h_lower:
            col_map["entity"] = i
        elif "price talk" in h_lower and "coupon" in h_lower:
            col_map["price_talk_coupon"] = i
        elif "price talk" in h_lower and ("margin" in h_lower or "bps" in h_lower):
            col_map["price_talk_margin"] = i
        elif "price talk" in h_lower or "talk" in h_lower or "guidance" in h_lower:
            col_map.setdefault("price_talk", i)
        elif h_lower == "coupon" or (h_lower.startswith("coupon") and "talk" not in h_lower):
            col_map["coupon"] = i
        elif "yield" in h_lower or "ytw" in h_lower or "ytm" in h_lower:
            col_map["yield"] = i
        elif "rating" in h_lower:
            col_map.setdefault("rating", i)
        elif "bookrunner" in h_lower or "lead" in h_lower or "arranger" in h_lower:
            col_map["bookrunners"] = i
        elif "spread" in h_lower or "margin" in h_lower:
            col_map.setdefault("spread", i)
        elif "size" in h_lower or "amount" in h_lower:
            col_map["size"] = i
        elif "maturity" in h_lower:
            col_map["maturity"] = i
        elif "launch" in h_lower and "date" in h_lower:
            col_map["launch_date"] = i

    print(f"    Column mapping: {col_map}")

    # Extract rows
    rows = table.query_selector_all("tbody tr")
    print(f"    Found {len(rows)} deal rows.")

    deals = []
    for row in rows:
        cells = row.query_selector_all("td")
        if not cells:
            continue

        def _cell(name):
            idx = col_map.get(name)
            if idx is not None and idx < len(cells):
                return cells[idx].inner_text().strip()
            return ""

        entity = _cell("entity")
        coupon = _cell("coupon")
        yld = _cell("yield")
        rating = _cell("rating")
        bookrunners = _cell("bookrunners")
        spread = _cell("spread")
        size = _cell("size")
        maturity = _cell("maturity")
        launch_date = _cell("launch_date")

        # Merge price talk fields
        pt_margin = _cell("price_talk_margin")
        pt_coupon = _cell("price_talk_coupon")
        pt_generic = _cell("price_talk")
        price_talk_parts = [p for p in [pt_margin, pt_coupon, pt_generic] if p and p != "-"]
        price_talk = " / ".join(price_talk_parts) if price_talk_parts else ""

        if not entity:
            continue

        # Check yield threshold
        include = False

        # Parse yield — look for a number >= 8.0
        yld_nums = re.findall(r'(\d+\.?\d*)\s*%?', yld)
        for n in yld_nums:
            try:
                if float(n) >= YIELD_THRESHOLD:
                    include = True
                    break
            except ValueError:
                pass

        # Also check price talk for yield indicators
        if not include and price_talk:
            talk_nums = re.findall(r'(\d+\.?\d*)\s*%', price_talk)
            for n in talk_nums:
                try:
                    if float(n) >= YIELD_THRESHOLD:
                        include = True
                        break
                except ValueError:
                    pass

        # Also check spread — wide spreads (>400bps) are interesting
        if not include and spread:
            spread_nums = re.findall(r'(\d+)', spread)
            for n in spread_nums:
                try:
                    if int(n) >= 400:  # 400bps+ spread is roughly 8%+ yield
                        include = True
                        break
                except ValueError:
                    pass

        if not include:
            continue

        deals.append({
            "entity": entity,
            "coupon": coupon,
            "yield": yld,
            "price_talk": price_talk,
            "rating": rating,
            "bookrunners": bookrunners,
            "spread": spread,
            "size": size,
            "maturity": maturity,
            "launch_date": launch_date,
        })

    print(f"    {len(deals)} deals with yield >= {YIELD_THRESHOLD}% (or wide spread/price talk).")
    return deals


# ======================================================================
# FORMATTING
# ======================================================================

def format_octus_for_prompt(articles, deals):
    """Format Octus data as plain text for the Opus prompt."""
    parts = []

    if articles:
        lines = ["OCTUS INTELLIGENCE (top articles):"]
        for i, a in enumerate(articles):
            lines.append(
                f"\n--- Octus Article {i+1} ---\n"
                f"Title: {a['title']}\n"
                f"Company: {a.get('company', '')}\n"
                f"URL: {a.get('url', '')}\n\n"
                f"{a['text']}"
            )
        parts.append("\n".join(lines))

    # Deals are NOT passed to Opus — they're rendered as a pre-built HTML table only.
    # Passing them to Opus would cause a duplicate section.

    return "\n\n".join(parts)


def build_deals_table_html(deals):
    """Render deals as an HTML table for the digest."""
    if not deals:
        return ""

    rows = ""
    for d in deals:
        rows += (
            f'<tr>'
            f'<td style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee; font-weight: 600;">{d["entity"]}</td>'
            f'<td style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee; text-align: center;">{d.get("launch_date", "")}</td>'
            f'<td style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee; text-align: center;">{d.get("coupon", "")}</td>'
            f'<td style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee; text-align: center;">{d.get("yield", "")}</td>'
            f'<td style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee; text-align: center;">{d.get("price_talk", "")}</td>'
            f'<td style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee; text-align: center;">{d.get("rating", "")}</td>'
            f'<td style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee;">{", ".join(d.get("bookrunners", "").split(", ")[:3])}</td>'
            f'</tr>\n'
        )

    html = (
        '<div style="margin: 20px 0;">\n'
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 6px; '
        'margin: 28px 0 12px;">Primary Deals (Yield &ge; 8%)</h2>\n'
        '<table style="border-collapse: collapse; width: 100%; font-family: Georgia, serif;">\n'
        '<tr>'
        '<th style="padding: 4px 8px; font-size: 11px; color: #888; text-align: left; border-bottom: 2px solid #ccc;">Entity</th>'
        '<th style="padding: 4px 8px; font-size: 11px; color: #888; text-align: center; border-bottom: 2px solid #ccc;">Date</th>'
        '<th style="padding: 4px 8px; font-size: 11px; color: #888; text-align: center; border-bottom: 2px solid #ccc;">Coupon</th>'
        '<th style="padding: 4px 8px; font-size: 11px; color: #888; text-align: center; border-bottom: 2px solid #ccc;">Yield</th>'
        '<th style="padding: 4px 8px; font-size: 11px; color: #888; text-align: center; border-bottom: 2px solid #ccc;">Price Talk</th>'
        '<th style="padding: 4px 8px; font-size: 11px; color: #888; text-align: center; border-bottom: 2px solid #ccc;">Rating</th>'
        '<th style="padding: 4px 8px; font-size: 11px; color: #888; text-align: left; border-bottom: 2px solid #ccc;">Bookrunners</th>'
        '</tr>\n'
        f'{rows}'
        '</table>\n'
        '<p style="font-size: 10px; color: #aaa; margin: 4px 0 0;">Source: Octus Primary Deal Tracker</p>\n'
        '</div>\n'
    )

    return html


# ======================================================================
# MAIN ENTRY POINTS
# ======================================================================

def fetch_octus_articles():
    """Fetch and rank Octus intel articles. Called by digest.py."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed — skipping Octus articles.")
        return []

    with sync_playwright() as pw:
        browser, context, page = _get_browser_and_page(pw)
        browser, context, page = _ensure_logged_in(pw, browser, context, page, OCTUS_INTEL)
        if page is None:
            return []

        print("  Scraping Octus intel feed...")
        raw_articles = _scrape_articles(page)

        try:
            _save_session(context)
        except Exception:
            pass
        browser.close()

    if not raw_articles:
        return []

    # Rank to top 5 via Sonnet
    return _rank_articles(raw_articles)


def fetch_octus_deals():
    """Fetch HY deals from Octus primary tracker. Called by digest.py."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed — skipping Octus deals.")
        return []

    with sync_playwright() as pw:
        browser, context, page = _get_browser_and_page(pw)
        browser, context, page = _ensure_logged_in(pw, browser, context, page, OCTUS_DEALS)
        if page is None:
            return []

        print("  Scraping Octus primary deal tracker...")
        deals = _scrape_deals(page)

        try:
            _save_session(context)
        except Exception:
            pass
        browser.close()

    return deals


# ======================================================================
# CLI
# ======================================================================

if __name__ == "__main__":
    force_login = "--login" in sys.argv
    debug = "--debug" in sys.argv
    deals_only = "--deals" in sys.argv
    articles_only = "--articles" in sys.argv

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed.")
        print("Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    with sync_playwright() as pw:
        if force_login or not _has_session():
            _do_manual_login(pw)

        if debug:
            target = OCTUS_DEALS if deals_only else OCTUS_INTEL
            print(f"  DEBUG: loading {target} (visible)...")
            session_state = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context(storage_state=session_state)
            page = context.new_page()
            page.goto(target, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)

            suffix = "deals" if deals_only else "intel"
            page.screenshot(path=str(SCRIPT_DIR / f"octus_debug_{suffix}.png"), full_page=True)
            html = page.content()
            (SCRIPT_DIR / f"octus_debug_{suffix}.html").write_text(html, encoding="utf-8")
            print(f"  Screenshot: octus_debug_{suffix}.png")
            print(f"  HTML: octus_debug_{suffix}.html ({len(html):,} chars)")
            print(f"  URL: {page.url}")
            input("\n  >>> Press ENTER to close... ")
            browser.close()
            sys.exit(0)

        # --- Articles ---
        if not deals_only:
            browser, context, page = _get_browser_and_page(pw)
            browser, context, page = _ensure_logged_in(pw, browser, context, page, OCTUS_INTEL)
            if page:
                print("  Scraping Octus intel feed...")
                raw_articles = _scrape_articles(page)
                articles = _rank_articles(raw_articles) if raw_articles else []
                _save_session(context)
                browser.close()

                if articles:
                    print(f"\n=== TOP {len(articles)} OCTUS ARTICLES ===")
                    for a in articles:
                        print(f"\n  {a['title']}")
                        print(f"  Company: {a.get('company', '')} | Date: {a['date']}")
                        print(f"  URL: {a['url']}")
                        print(f"  Text: {a['text'][:200].replace(chr(10), ' ')}...")
                else:
                    print("\nNo articles scraped.")

        # --- Deals ---
        if not articles_only:
            browser, context, page = _get_browser_and_page(pw)
            browser, context, page = _ensure_logged_in(pw, browser, context, page, OCTUS_DEALS)
            if page:
                print("\n  Scraping Octus primary deal tracker...")
                deals = _scrape_deals(page)
                _save_session(context)
                browser.close()

                if deals:
                    print(f"\n=== {len(deals)} DEALS (YIELD >= {YIELD_THRESHOLD}%) ===")
                    for d in deals:
                        print(f"  {d['entity']}: coupon={d.get('coupon','?')} yield={d.get('yield','?')} "
                              f"talk={d.get('price_talk','?')} rating={d.get('rating','?')} "
                              f"bookrunners={d.get('bookrunners','?')[:50]}")
                else:
                    print("\nNo qualifying deals found.")
