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
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SESSION_FILE = SCRIPT_DIR / "jpm_session.json"  # gitignored, like thirteen_d_session.json
RECON_DIR = SCRIPT_DIR / "jpm_recon"

# Canonical login start. NOT JPM_LINK — the operator's JPM_LINK on 2026-07-27
# was https://share-login.jpmorgan.com/sessionExpire, a session-EXPIRED shim
# page (a button-to-continue, no username field) that broke auto-fill. The real
# login form lives at nwas.jpmorgan.com, reached via markets.jpmorgan.com/login.
# JPM_LINK's real purpose (research deep-link?) is TBD — see RESEARCH_URL.
LOGIN_URL = "https://markets.jpmorgan.com/login"
RESEARCH_URL = os.environ.get("JPM_LINK", "")  # post-login destination (Phase 2); confirm intent

# Hosts/paths that mean we are NOT past auth yet.
_UNAUTH_MARKERS = ("nwas.jpmorgan.com", "share-login.jpmorgan.com",
                   "sessionexpire", "/login", "logon", "/sso")

# --- MFA access code email (confirmed sample 2026-07-27) ---
# From: authe.noreply@jpmchase.com
# Subject: "Your Authentication Code from JPMorgan Chase"
# Body: "...Your Authentication Code is 81957340 and is available..." (8 digits,
# in the BODY not the subject; expires in 10 minutes). Also the string the
# Phase-3 digest exclusion filter keys on.
_JPM_CODE_SENDER = "authe.noreply@jpmchase.com"
_JPM_CODE_RE = re.compile(r"Authentication Code is\s*(\d{6,8})")

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
    """Phase-1 heuristic: authenticated if we're on a jpmorgan/jpmm host that
    is NOT one of the login/SSO/session-expire pages. Tighten to a cookie check
    once we identify JPM's auth cookie (cf. thirteen_d._looks_authenticated)."""
    u = (final_url or "").lower()
    on_jpm = "jpmorgan.com" in u or "jpmm.com" in u
    return on_jpm and not any(mark in u for mark in _UNAUTH_MARKERS)


def read_jpm_code(gmail_service, since_epoch=0, max_wait=120):
    """Poll the bot inbox for JPM's forwarded access code (confirmed format
    above) and return it. Freshness-gated on since_epoch so a stale code from
    an earlier attempt isn't reused (the Substack lesson). Reusable by the
    Phase-1b automated MFA step."""
    start = time.time()
    while time.time() - start < max_wait:
        res = gmail_service.users().messages().list(
            userId="me", q=f"from:{_JPM_CODE_SENDER} newer_than:1h", maxResults=5,
        ).execute()
        for meta in res.get("messages", []):
            msg = gmail_service.users().messages().get(
                userId="me", id=meta["id"], format="full").execute()
            if int(msg.get("internalDate", 0)) / 1000 < since_epoch:
                continue  # stale — arrived before this login attempt
            body = ""
            payload = msg.get("payload", {})
            stack = [payload]
            while stack:
                p = stack.pop()
                if p.get("body", {}).get("data"):
                    import base64
                    body += base64.urlsafe_b64decode(
                        p["body"]["data"]).decode("utf-8", "replace")
                stack.extend(p.get("parts", []) or [])
            m = _JPM_CODE_RE.search(re.sub(r"<[^>]+>", " ", body))
            if m:
                print("  Found JPM access code in the bot inbox.")
                return m.group(1)
        print(f"  Waiting for JPM access code... ({int(time.time() - start)}s)")
        time.sleep(5)
    return None


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


def _dump_recon(page, context, tag="landing"):
    """Save the current DOM + screenshot + cookies to ./jpm_recon/ — ALWAYS,
    even on an unauthenticated end state, so a 'failed' run still yields the
    page structure + cookie names I need to write reliable automation."""
    RECON_DIR.mkdir(exist_ok=True)
    try:
        (RECON_DIR / f"{tag}.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(RECON_DIR / f"{tag}.png"), full_page=True)
        state = context.storage_state()
        cookie_names = sorted({c.get("name", "") for c in state.get("cookies", [])})
        (RECON_DIR / f"{tag}_cookies.json").write_text(
            json.dumps(cookie_names, indent=1), encoding="utf-8")
        print(f"  Recon dumped to {RECON_DIR}/ ({tag}.html/.png, url={page.url!r})")
        print(f"  Cookie names present: {cookie_names}")
    except Exception as e:
        print(f"  Could not dump recon: {e}")


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

        # MFA + anything the auto-fill missed: hand to the human this run.
        print("\n  Complete anything remaining in the browser — the MFA access")
        print("  code (request it by EMAIL; it forwards to the bot inbox), plus")
        print("  any field the script couldn't fill. Then return here.")
        input("\n  >>> Press ENTER once you are fully logged in (keep the browser open)... ")

        # ALWAYS dump recon first — even a non-authenticated end state gives me
        # the DOM + cookie names to write reliable automation next time.
        _dump_recon(page, context, tag="landing")

        final_url = page.url
        authed = _looks_authenticated(final_url)
        if not authed:
            print(f"  NOTE: end URL doesn't look authenticated (url={final_url!r}).")

        # Bootstrap: with no existing session there's nothing to clobber, so
        # save whatever we have for inspection. Once a session exists, only
        # overwrite it with an authenticated one (13D's anti-clobber lesson).
        try:
            if authed or not SESSION_FILE.exists():
                SESSION_FILE.write_text(json.dumps(context.storage_state(), indent=2),
                                        encoding="utf-8")
                label = "authenticated" if authed else "PROVISIONAL (verify)"
                print(f"  Session saved to {SESSION_FILE.name} [{label}].")
            else:
                print("  Kept the EXISTING session file (refusing to clobber with "
                      "an unauthenticated state).")
        except Exception as e:
            print(f"  Could not save session: {e}")

        browser.close()
        return authed


if __name__ == "__main__":
    if "--login" in sys.argv:
        sys.exit(0 if do_login() else 1)
    print(__doc__)
    print(f"\nSession present: {_has_session()} ({SESSION_FILE})")
    print("Run `python jpm_research.py --login` to capture a session (Phase 1).")
