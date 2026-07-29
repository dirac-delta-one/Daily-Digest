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
from config import REPO_ROOT

SCRIPT_DIR = REPO_ROOT
SESSION_FILE = SCRIPT_DIR / "jpm_session.json"  # gitignored, like thirteen_d_session.json
RECON_DIR = SCRIPT_DIR / "jpm_recon"

# Login start = jared's entitled share-login gateway. Two 2026-07-27 lessons:
# (1) The durable entry is the ROOT https://share-login.jpmorgan.com/ — the
#     /sessionExpire path once captured in JPM_LINK was a transient
#     session-expired page and later 404'd, so any path on the link is
#     stripped down to the host root here.
# (2) Do NOT go around the gateway via markets.jpmorgan.com/login — it
#     authenticates but dead-ends at "You do not have appropriate entitlement
#     to access this resource" (jared is entitled to the shared resource
#     only, not the full markets platform).
# ⚠ JPM rate-limits/BLOCKS an IP after repeated auth attempts (operator hit
# this 2026-07-27 after ~3 tries). Automation must stay SINGLE-ATTEMPT per
# run — never loop or retry a failed login; on failure, stop and wait
# (hours). The server has its own IP and budget.
def _login_root(link):
    """Resolve JPM_LINK to the URL to open — pass it through VERBATIM (adding
    only a missing scheme).

    History: the 7/27 code stripped everything to the host root because
    /sessionExpire had 404'd; 7/29 showed the gateway is resource-scoped (the
    bare root returns a branded "Bad Request" whose cookies include
    `resourceName`), so stripping guaranteed failure. Any transformation here
    just second-guesses the operator's link — the runtime error-page
    short-circuit in do_login() is the real guard against a dead URL."""
    link = (link or "").strip()
    if not link:
        return "https://share-login.jpmorgan.com/"
    return link if "://" in link else "https://" + link


LOGIN_URL = _login_root(os.environ.get("JPM_LINK"))

# Hosts/paths that mean we are NOT past auth / not yet at content.
_UNAUTH_MARKERS = ("nwas.jpmorgan.com", "sessionexpire", "logon", "/sso", "/login",
                   "share-login.jpmorgan.com")  # the gateway itself is never the destination

# The share-login landing shows a button BEFORE the username form — click it
# first if no username field is present yet.
_LANDING_BUTTON_SELECTORS = (
    "button:has-text('Log in')", "button:has-text('Login')",
    "button:has-text('Sign in')", "button:has-text('Continue')",
    "button:has-text('Proceed')", "a:has-text('Log in')",
    "a:has-text('Login')", "a:has-text('Sign in')", "a[href*='login' i]",
)

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


def _launch_browser(pw, headless=False):
    """Prefer the machine's installed Chrome/Edge (Playwright `channel`) over
    the bundled Chromium: on 2026-07-29 share-login.jpmorgan.com answered the
    bundled build's page LOAD with 400 Bad Request while the same URL rendered
    fine in the desktop browser — the gateway appears to reject the bundled
    build outright. Driving the real browser is a plain configuration choice;
    deliberately NO automation-hiding flags — if JPM refuses openly-automated
    clients too, that's an approach-level decision (entitled feed/API, or
    human-in-the-loop), not something to evade."""
    for channel in ("chrome", "msedge"):
        try:
            browser = pw.chromium.launch(headless=headless, channel=channel)
            print(f"  Browser: installed {channel} (channel).")
            return browser
        except Exception:
            continue
    print("  Browser: bundled Chromium (no installed Chrome/Edge found).")
    return pw.chromium.launch(headless=headless)


def _has_session():
    return SESSION_FILE.exists()


_ERROR_PAGE_TITLES = ("bad request", "error", "forbidden", "access denied",
                      "not found", "sign in", "log in", "logon")


def _looks_authenticated(final_url, page_title=None):
    """Phase-1 heuristic: authenticated if we're on a jpmorgan/jpmm host that
    is NOT a login/SSO/session-expire/error page. Tighten to a cookie check
    once we identify JPM's auth cookie (cf. thirteen_d._looks_authenticated).

    2026-07-29: URL alone gave a FALSE POSITIVE — a JPM-branded "Bad Request"
    page on share-login.jpmorgan.com/ passed (the host contains "jpmorgan.com"
    and "-login." doesn't match the "/login" marker), so a dead end was saved
    as an "authenticated" session, clobbering the prior file. Now the gateway
    host itself counts as unauthenticated and the page TITLE is checked."""
    u = (final_url or "").lower()
    on_jpm = "jpmorgan.com" in u or "jpmm.com" in u
    if not on_jpm or any(mark in u for mark in _UNAUTH_MARKERS):
        return False
    title = (page_title or "").lower()
    return not any(bad in title for bad in _ERROR_PAGE_TITLES)


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


def _has_field(page, selectors):
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except Exception:
            continue
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
        browser = _launch_browser(pw, headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # Error-page short-circuit (2026-07-29): the gateway answers a
        # resource-less URL with a JPM-branded "Bad Request". Say so up front
        # instead of walking the operator through selector misses and an
        # ENTER prompt that can't lead anywhere.
        try:
            title = page.title()
        except Exception:
            title = ""
        if any(bad in (title or "").lower() for bad in _ERROR_PAGE_TITLES[:5]):
            print(f"\n  ⚠ The gateway returned an error page (title: {title!r}).")
            print("  This is NOT a credential problem — no login was attempted,")
            print("  so no auth attempt was spent. The share-login gateway is")
            print("  resource-scoped: JPM_LINK must be the FULL entitled share")
            print("  link (path + query, e.g. ...?resourceName=...), not the")
            print("  bare host. Get the original link from jared's JPM email/")
            print("  bookmark, put it in env.bat as JPM_LINK, and retry once.")
            _dump_recon(page, context, tag="error")
            browser.close()
            return False

        # share-login landing: a button precedes the username form. If no
        # username field is visible yet, click the landing button first.
        if not _has_field(page, _USERNAME_SELECTORS):
            print("  No username field yet — clicking the landing button...")
            if _click_first(page, _LANDING_BUTTON_SELECTORS, "landing/continue"):
                page.wait_for_timeout(3500)

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
        try:
            final_title = page.title()
        except Exception:
            final_title = ""
        authed = _looks_authenticated(final_url, final_title)
        if not authed:
            print(f"  NOTE: end state doesn't look authenticated "
                  f"(url={final_url!r}, title={final_title!r}).")

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
