#!/usr/bin/env python3
"""
J.P. Morgan Markets research access — PHASE 1 (session capture only).

See JPM_SPEC.md for the full plan. This first cut does ONLY the safe,
human-run login that the rest is built on — modeled on thirteen_d.py's
`_do_manual_login`:

    python jpm_research.py --login

opens a HEADED browser to the JPM login, the operator logs in as jared
(types the password + enters the forwarded MFA access code themselves —
Claude never types the password), then this saves the authenticated
`jpm_session.json` (Playwright storage_state) and dumps the post-login
landing page's structure to the scratchpad so the Phase 2 scraper can be
designed against the real authenticated DOM.

NOT YET BUILT (need the Phase 1 run first — see JPM_SPEC.md):
  - Phase 1b: automated login (env creds + auto-read forwarded code via
    substack._find_login_code_in_gmail). Written once we've seen the real
    password/MFA pages + the code-email format from this run.
  - Phase 2: fetch_jpm_research() scraper.
  - Phase 3: digest wiring + the access-code-email exclusion filter.

This module is intentionally NOT imported by digest.py yet — it is inert
until Phase 3 wires it in.
"""

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SESSION_FILE = SCRIPT_DIR / "jpm_session.json"  # gitignored, like thirteen_d_session.json

# Login entry point. JPM_LINK (env) wins if set; else the known login URL.
LOGIN_URL = os.environ.get("JPM_LINK") or "https://markets.jpmorgan.com/login"

# The SSO host the login redirects THROUGH. While the final URL is still on
# this host we are NOT past auth, so we must not save the session (mirrors
# 13D's anti-clobber guard — never overwrite a good session with an
# unauthenticated one). The authenticated-cookie name is unknown until the
# Phase 1 run; once identified, tighten this into a cookie check like
# thirteen_d._looks_authenticated. TODO(Phase 1b): set _AUTH_COOKIE_NAMES.
_SSO_HOST = "nwas.jpmorgan.com"


def _has_session():
    return SESSION_FILE.exists()


def _looks_authenticated(final_url):
    """Phase-1 heuristic: we're authenticated if login sent us BACK to the
    markets host and off the SSO host. Replace with a cookie-name check once
    the Phase 1 run reveals JPM's auth cookie (see the _SSO_HOST note)."""
    u = (final_url or "").lower()
    return "markets.jpmorgan.com" in u and _SSO_HOST not in u


def _dump_landing(page):
    """Save the post-login landing DOM + a screenshot to the scratchpad so the
    Phase 2 scraper can be designed against the real authenticated site."""
    out_dir = SCRIPT_DIR / "jpm_recon"
    out_dir.mkdir(exist_ok=True)
    try:
        (out_dir / "landing.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(out_dir / "landing.png"), full_page=True)
        print(f"  Landing page dumped to {out_dir}/ (landing.html + landing.png)")
    except Exception as e:
        print(f"  Could not dump landing page: {e}")


def do_manual_login():
    """Headed, human-run login. Claude does NOT type the password — the
    operator does. Saves the session only if it looks authenticated."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return False

    print("  Opening a browser for J.P. Morgan Markets login...")
    print(f"  Log in at {LOGIN_URL} as jared — enter the username, password, and the")
    print("  access code (it forwards to the bot inbox). Then return here and press ENTER.")
    print("  DO NOT close the browser.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        input("\n  >>> Press ENTER after you are fully logged in (keep the browser open)... ")

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
            state = context.storage_state()
            SESSION_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
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
        ok = do_manual_login()
        sys.exit(0 if ok else 1)
    print(__doc__)
    print(f"\nSession present: {_has_session()} ({SESSION_FILE})")
    print("Run `python jpm_research.py --login` to capture a session (Phase 1).")
