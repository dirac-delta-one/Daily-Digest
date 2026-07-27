#!/usr/bin/env python3
"""
J.P. Morgan Markets research access — PHASE 1 (session capture).

See JPM_SPEC.md for the full plan. `python jpm_research.py --login` runs a
HEADED login that AUTO-FILLS the username + password from env
(JPM_USERNAME / JPM_PASSWORD) — no manual credential typing — then saves the
authenticated `jpm_session.json` (Playwright storage_state) and dumps the
post-login landing DOM to ./jpm_recon/ so the Phase 2 scraper can be built
against the real authenticated site.

Two things are manual on the FIRST run only, then automated:
  - The MFA access code: auto-reading it needs JPM's code-email format, which
    this first run generates (it forwards to the bot inbox). Until then, the
    operator enters the code in the browser. Phase 1b adds the auto-reader
    (substack._find_login_code_in_gmail pattern) once we have a sample.
  - Selectors: recon only reached the username page, so the password/MFA field
    selectors are defensive guesses. If a field isn't found, the script PAUSES
    for the human rather than retrying (avoids hammering a live SSO → lockout).

Who runs it: the OPERATOR (or, once Phase 1b lands, the server's scheduled
task) — the script types the password itself; nobody logs in by hand.

NOT YET BUILT: Phase 1b auto-MFA · Phase 2 fetch_jpm_research() · Phase 3
digest wiring + access-code-email exclusion filter. Not imported by digest.py
yet (inert).
"""

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SESSION_FILE = SCRIPT_DIR / "jpm_session.json"  # gitignored, like thirteen_d_session.json

LOGIN_URL = os.environ.get("JPM_LINK") or "https://markets.jpmorgan.com/login"
_SSO_HOST = "nwas.jpmorgan.com"  # login redirects THROUGH here; off it = past auth

# Defensive selector candidates (recon reached only the username page; the rest
# are best-guesses refined after the first run). First match wins.
_USERNAME_SELECTORS = (
    "input[type='email']", "input[name*='user' i]", "input[name*='email' i]",
    "input[id*='user' i]", "input[id*='email' i]", "input[type='text']",
)
_PASSWORD_SELECTORS = (
    "input[type='password']", "input[name*='pass' i]", "input[id*='pass' i]",
)
_SUBMIT_SELECTORS = (
    "button[type='submit']", "button:has-text('Continue')", "button:has-text('Log')",
    "button:has-text('Sign')", "input[type='submit']",
)


def _has_session():
    return SESSION_FILE.exists()


def _looks_authenticated(final_url):
    """Phase-1 heuristic: authenticated if login sent us BACK to the markets
    host and off the SSO host. Tighten to a cookie check once the first run
    reveals JPM's auth cookie (cf. thirteen_d._looks_authenticated)."""
    u = (final_url or "").lower()
    return "markets.jpmorgan.com" in u and _SSO_HOST not in u


def _fill_first(page, selectors, value, what):
    """Fill the first matching field. Returns True on success; on miss, prints
    and returns False so the caller can pause for the human (never retries —
    a hammered SSO can lock the account)."""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(value)
                return True
        except Exception:
            continue
    print(f"  Could not locate the {what} field automatically "
          f"(tried {len(selectors)} selectors).")
    return False


def _click_first(page, selectors, what):
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                return True
        except Exception:
            continue
    print(f"  Could not locate the {what} button automatically.")
    return False


def _dump_landing(page):
    """Save the post-login DOM + screenshot to ./jpm_recon/ for scraper design."""
    out_dir = SCRIPT_DIR / "jpm_recon"
    out_dir.mkdir(exist_ok=True)
    try:
        (out_dir / "landing.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(out_dir / "landing.png"), full_page=True)
        print(f"  Landing page dumped to {out_dir}/ (landing.html + landing.png)")
    except Exception as e:
        print(f"  Could not dump landing page: {e}")


def do_login():
    """Headed login: auto-fill username+password from env; pause for the human
    on any selector miss or for the (first-run) MFA code; save the session only
    if it looks authenticated."""
    username = os.environ.get("JPM_USERNAME")
    password = os.environ.get("JPM_PASSWORD")
    if not username or not password:
        print("  JPM_USERNAME / JPM_PASSWORD not set in the environment — "
              "load env.bat first. Aborting.")
        return False

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return False

    print(f"  Opening J.P. Morgan Markets login ({LOGIN_URL})...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # Username → continue
        if _fill_first(page, _USERNAME_SELECTORS, username, "username"):
            _click_first(page, _SUBMIT_SELECTORS, "continue")
            page.wait_for_timeout(3000)

        # Password → submit (defensive: the password field may share the page
        # or appear after continue)
        if _fill_first(page, _PASSWORD_SELECTORS, password, "password"):
            _click_first(page, _SUBMIT_SELECTORS, "submit")
            page.wait_for_timeout(3000)

        # MFA + anything the auto-fill missed: hand to the human this first run.
        print("\n  Complete anything remaining in the browser — the MFA access")
        print("  code (it forwards to the bot inbox), plus any field the script")
        print("  couldn't fill. Then return here.")
        input("\n  >>> Press ENTER once you are fully logged in (keep the browser open)... ")

        final_url = page.url
        if not _looks_authenticated(final_url):
            print(f"  WARNING: still looks unauthenticated (url={final_url!r}).")
            if SESSION_FILE.exists():
                print("  Keeping the EXISTING session file untouched (refusing to clobber).")
            else:
                print("  No session saved. Re-run once the login completes.")
            browser.close()
            return False

        try:
            SESSION_FILE.write_text(json.dumps(context.storage_state(), indent=2),
                                    encoding="utf-8")
            print(f"  Session saved to {SESSION_FILE.name}.")
            _dump_landing(page)
        except Exception as e:
            print(f"  Could not save session: {e}")
            browser.close()
            return False

        browser.close()
        return True


if __name__ == "__main__":
    if "--login" in sys.argv:
        sys.exit(0 if do_login() else 1)
    print(__doc__)
    print(f"\nSession present: {_has_session()} ({SESSION_FILE})")
    print("Run `python jpm_research.py --login` to capture a session (Phase 1).")
