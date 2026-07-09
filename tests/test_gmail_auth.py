"""Hardening — get_gmail_service must re-consent on a dead refresh token
(invalid_grant) instead of crashing (the failure seen with a copied token.json)."""

from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import RefreshError

import digest


def _creds(valid, *, refresh_raises=False):
    c = MagicMock()
    c.valid = valid
    c.expired = True
    c.refresh_token = "rt"
    c.to_json.return_value = "{}"
    if refresh_raises:
        c.refresh.side_effect = RefreshError("invalid_grant: Bad Request")
    else:
        def _ok(_req):
            c.valid = True
        c.refresh.side_effect = _ok
    return c


@pytest.fixture
def gmail_env(monkeypatch):
    """Patch digest's Google deps so get_gmail_service runs with no I/O or browser."""
    monkeypatch.delenv("DIGEST_UNATTENDED", raising=False)  # attended by default
    tok = MagicMock()
    tok.exists.return_value = True
    monkeypatch.setattr(digest, "TOKEN_FILE", tok)
    crd = MagicMock()
    crd.exists.return_value = True
    monkeypatch.setattr(digest, "CREDENTIALS_FILE", crd)
    monkeypatch.setattr(digest, "build", lambda *a, **k: "SERVICE")

    flow = MagicMock()
    flow.run_local_server.return_value = _creds(valid=True)
    iaf = MagicMock()
    iaf.from_client_secrets_file.return_value = flow
    monkeypatch.setattr(digest, "InstalledAppFlow", iaf)
    return monkeypatch, tok, flow


def test_dead_refresh_token_falls_back_to_consent(gmail_env):
    mp, tok, flow = gmail_env
    dead = _creds(valid=False, refresh_raises=True)
    mp.setattr(digest, "Credentials", MagicMock(from_authorized_user_file=lambda *a, **k: dead))

    svc = digest.get_gmail_service()  # must NOT raise RefreshError

    assert svc == "SERVICE"
    dead.refresh.assert_called_once()           # tried to refresh
    flow.run_local_server.assert_called_once()  # then fell back to a fresh consent
    tok.write_text.assert_called_once()         # and saved the new token


def test_good_refresh_skips_consent(gmail_env):
    mp, tok, flow = gmail_env
    good = _creds(valid=False)  # becomes valid after a successful refresh
    mp.setattr(digest, "Credentials", MagicMock(from_authorized_user_file=lambda *a, **k: good))

    svc = digest.get_gmail_service()

    assert svc == "SERVICE"
    good.refresh.assert_called_once()
    flow.run_local_server.assert_not_called()   # refresh worked; no browser consent
    tok.write_text.assert_called_once()


# --- F1a-1: unattended mode must fail fast, never open a browser consent ---

def test_unattended_dead_token_fails_fast(gmail_env):
    mp, tok, flow = gmail_env
    mp.setenv("DIGEST_UNATTENDED", "1")
    dead = _creds(valid=False, refresh_raises=True)
    mp.setattr(digest, "Credentials", MagicMock(from_authorized_user_file=lambda *a, **k: dead))

    with pytest.raises(SystemExit) as exc:
        digest.get_gmail_service()

    assert exc.value.code == 3                  # distinct exit -> wrapper fires run_alert
    flow.run_local_server.assert_not_called()   # the whole point: no headless hang
    tok.write_text.assert_not_called()


def test_unattended_good_refresh_unaffected(gmail_env):
    # Unattended mode only guards the CONSENT path — a healthy refresh works.
    mp, tok, flow = gmail_env
    mp.setenv("DIGEST_UNATTENDED", "1")
    good = _creds(valid=False)
    mp.setattr(digest, "Credentials", MagicMock(from_authorized_user_file=lambda *a, **k: good))

    assert digest.get_gmail_service() == "SERVICE"
    flow.run_local_server.assert_not_called()


def test_unattended_flag_parsing(monkeypatch):
    for val, expected in (("1", True), ("true", True), ("YES", True),
                          ("0", False), ("", False)):
        monkeypatch.setenv("DIGEST_UNATTENDED", val)
        assert digest._unattended() is expected, val
    monkeypatch.delenv("DIGEST_UNATTENDED")
    assert digest._unattended() is False
