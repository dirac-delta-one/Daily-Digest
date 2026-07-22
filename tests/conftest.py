"""Shared fixtures — state isolation for the email-managed watch config.

The SEC watchlist and the alert definitions are user-mutable runtime state
since ALERT_COMMANDS_SPEC (2026-07-22): any digest recipient can add/remove
entries by replying to a digest. Tests must not depend on — or write — the
live state files: the entity-lexicon tests assume the canonical default
tickers (MSTR, MAIN, ...) are on the watchlist, and a stray write would
corrupt real config. This autouse fixture pins both for every test:

- alert_commands' state-file paths point into a per-test tmp dir (the
  seed-on-missing logic recreates pristine defaults there on first touch);
- sec_filings.WATCHLIST (bound at import time, BEFORE fixtures run) is reset
  in place to the default tickers — slice assignment, so the
  `earnings.EARNINGS_WATCHLIST is sec_filings.WATCHLIST` identity holds;
- search's lazily-built entity lexicon cache is cleared on both sides.
"""

import pytest

import alert_commands
import sec_filings
import search

_DEFAULT_TICKERS = [e["ticker"] for e in alert_commands.DEFAULT_WATCHLIST]


@pytest.fixture(autouse=True)
def _pin_watch_state(tmp_path, monkeypatch):
    monkeypatch.setattr(alert_commands, "ALERTS_FILE",
                        tmp_path / "alerts_config.json")
    monkeypatch.setattr(alert_commands, "WATCHLIST_FILE",
                        tmp_path / "watchlist.json")

    saved = list(sec_filings.WATCHLIST)
    sec_filings.WATCHLIST[:] = _DEFAULT_TICKERS
    search._entity_lexicon_cache = None
    yield
    sec_filings.WATCHLIST[:] = saved
    search._entity_lexicon_cache = None
