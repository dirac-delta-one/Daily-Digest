"""JPM_SPEC Phase 1 — the pure helpers, pinned after the 2026-07-29 attempt.

That run exposed two bugs with no Playwright involved: the entitled share
link was being stripped to a resource-less host root (the gateway answered
"Bad Request"), and a JPM-branded error page passed the authenticated
heuristic, saving a dead end as a session. Both are URL/string logic, so
they test offline — no browser, no network, no credentials.
"""

import jpm_research


# --- _login_root: preserve the resource identifier ---

def test_login_root_preserves_path_and_query():
    # share-login is resource-scoped (it sets a `resourceName` cookie); the
    # entitled link's path/query is the resource id and must survive.
    link = "https://share-login.jpmorgan.com/share?resourceName=RESEARCH123"
    assert jpm_research._login_root(link) == link
    assert jpm_research._login_root(
        "https://share-login.jpmorgan.com/r/abc123"
    ) == "https://share-login.jpmorgan.com/r/abc123"


def test_login_root_strips_only_the_dead_session_expire_path():
    # /sessionExpire was a transient page that later 404'd (2026-07-27).
    assert jpm_research._login_root(
        "https://share-login.jpmorgan.com/sessionExpire"
    ) == "https://share-login.jpmorgan.com/"


def test_login_root_defaults_and_scheme_completion():
    assert jpm_research._login_root("") == "https://share-login.jpmorgan.com/"
    assert jpm_research._login_root(None) == "https://share-login.jpmorgan.com/"
    assert jpm_research._login_root(
        "share-login.jpmorgan.com/x?y=1"
    ) == "https://share-login.jpmorgan.com/x?y=1"


# --- _looks_authenticated: no false positives on error/gateway pages ---

def test_looks_authenticated_rejects_branded_error_page():
    # The exact 2026-07-29 false positive: JPM-branded "Bad Request" on the
    # gateway host was saved as an authenticated session.
    assert jpm_research._looks_authenticated(
        "https://share-login.jpmorgan.com/", "Bad Request | J.P. Morgan ") is False
    # …and the gateway host is never the destination, whatever the title
    assert jpm_research._looks_authenticated(
        "https://share-login.jpmorgan.com/", "Research") is False


def test_looks_authenticated_rejects_login_and_sso_urls():
    for url in ("https://nwas.jpmorgan.com/auth",
                "https://markets.jpmorgan.com/login",
                "https://markets.jpmorgan.com/sessionExpire",
                "https://example.com/anything"):
        assert jpm_research._looks_authenticated(url) is False


def test_looks_authenticated_rejects_error_titles_on_good_hosts():
    assert jpm_research._looks_authenticated(
        "https://markets.jpmorgan.com/research", "Access Denied") is False
    assert jpm_research._looks_authenticated(
        "https://www.jpmm.com/research", "Sign in") is False


def test_looks_authenticated_accepts_real_content_page():
    assert jpm_research._looks_authenticated(
        "https://markets.jpmorgan.com/research/doc/123", "Global Markets Daily") is True
    assert jpm_research._looks_authenticated(
        "https://www.jpmm.com/#/research", None) is True


# --- MFA code extraction (confirmed live sample 2026-07-27) ---

def test_jpm_code_regex_matches_confirmed_body_format():
    body = ("Your Authentication Code is 81957340 and is available for the "
            "next 10 minutes.")
    assert jpm_research._JPM_CODE_RE.search(body).group(1) == "81957340"
    assert jpm_research._JPM_CODE_RE.search("no code here") is None
