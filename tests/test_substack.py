"""_check_session — the probe must actually distinguish logged-in from
logged-out. The old /reader/feed probe returned 200 to anonymous requests, so
a dead cookie passed the check and magic-link renewal never fired (the
2026-07-13 dead-cookie incident). Pins the /user/profile/self probe semantics:
200 -> True, 401/403 -> False, network error -> False (which triggers the
renewal path in fetch_substack_articles)."""

import substack


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeSession:
    def __init__(self, status_code=None, exc=None):
        self.status_code = status_code
        self.exc = exc
        self.requested_urls = []

    def get(self, url, timeout=None):
        self.requested_urls.append(url)
        if self.exc:
            raise self.exc
        return _FakeResponse(self.status_code)


def test_check_session_authenticated():
    assert substack._check_session(_FakeSession(200)) is True


def test_check_session_dead_cookie_401():
    assert substack._check_session(_FakeSession(401)) is False


def test_check_session_403():
    assert substack._check_session(_FakeSession(403)) is False


def test_check_session_network_error():
    assert substack._check_session(_FakeSession(exc=OSError("boom"))) is False


def test_check_session_probes_profile_not_reader_feed():
    # The whole fix: /reader/feed answers 200 even logged out, so probing it
    # made the check vacuous. The probe must be an auth-gated endpoint.
    session = _FakeSession(200)
    substack._check_session(session)
    assert session.requested_urls == ["https://substack.com/api/v1/user/profile/self"]
