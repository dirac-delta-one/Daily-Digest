#!/usr/bin/env python3
"""
Shared low-level network helpers for the source fetchers.

- `edgar_get` — the EDGAR HTTP GET (shared contact User-Agent + uniform error
  handling) previously duplicated in sec_filings.py and fund_tracking.py.
- `unverified_ssl_context` — the cert-verification-disabled SSL context the
  Treasury Fiscal Data and CFTC endpoints need (their chains don't validate
  against the default store), previously duplicated in treasury_auctions.py and
  cftc_cot.py.
"""

import ssl
import urllib.request
import urllib.error

from config import USER_AGENT


def edgar_get(url, timeout=15):
    """GET an EDGAR endpoint with the shared contact User-Agent.

    Returns the decoded response text, or None on any HTTP/network error.
    Callers parse the body themselves (JSON in sec_filings, JSON/XML in
    fund_tracking), so this returns raw text rather than parsed data.
    """
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"    EDGAR HTTP error {e.code} for {url}")
        return None
    except Exception as e:
        print(f"    EDGAR request error: {e}")
        return None


def unverified_ssl_context():
    """An SSL context that skips certificate verification.

    For the Treasury Fiscal Data and CFTC endpoints, whose certificate chains
    don't validate against the default trust store.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
