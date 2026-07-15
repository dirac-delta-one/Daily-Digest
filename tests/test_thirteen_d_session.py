"""13D session-save guard (2026-07-15 hardening).

`_save_session` must refuse to overwrite a valid session with an unauthenticated
one — the clobber that killed WILTW when a stray ENTER at the login prompt saved
an anonymous (visitrack-only) browser context over Jared's logged-in session.
"""

import json

import thirteen_d


class _FakeContext:
    """Stands in for a Playwright BrowserContext — only storage_state() is used."""

    def __init__(self, state):
        self._state = state

    def storage_state(self):
        return self._state


_AUTH = {
    "cookies": [
        {"name": "visitrack", "value": "abc", "domain": ".13d.com"},
        {"name": "user", "value": "SECRET-TOKEN", "domain": ".13d.com"},
    ]
}
_ANON = {"cookies": [{"name": "visitrack", "value": "abc", "domain": ".13d.com"}]}


# --- _looks_authenticated ---

def test_looks_authenticated_true():
    assert thirteen_d._looks_authenticated(_AUTH) is True


def test_looks_authenticated_false_anonymous():
    assert thirteen_d._looks_authenticated(_ANON) is False


def test_looks_authenticated_false_empty_user():
    state = {"cookies": [{"name": "user", "value": "  ", "domain": ".13d.com"}]}
    assert thirteen_d._looks_authenticated(state) is False


def test_looks_authenticated_handles_none():
    assert thirteen_d._looks_authenticated(None) is False


# --- _save_session guard ---

def test_save_refuses_anonymous_and_keeps_existing(tmp_path, monkeypatch):
    sess = tmp_path / "thirteen_d_session.json"
    good = json.dumps(_AUTH, indent=2)
    sess.write_text(good, encoding="utf-8")
    monkeypatch.setattr(thirteen_d, "SESSION_FILE", sess)

    saved = thirteen_d._save_session(_FakeContext(_ANON))

    assert saved is False
    # the valid session must be byte-for-byte untouched
    assert sess.read_text(encoding="utf-8") == good


def test_save_refuses_anonymous_when_no_file(tmp_path, monkeypatch):
    sess = tmp_path / "thirteen_d_session.json"  # does not exist
    monkeypatch.setattr(thirteen_d, "SESSION_FILE", sess)

    saved = thirteen_d._save_session(_FakeContext(_ANON))

    assert saved is False
    assert not sess.exists()  # no dead anonymous session left behind


def test_save_writes_authenticated(tmp_path, monkeypatch):
    sess = tmp_path / "thirteen_d_session.json"
    monkeypatch.setattr(thirteen_d, "SESSION_FILE", sess)

    saved = thirteen_d._save_session(_FakeContext(_AUTH))

    assert saved is True
    written = json.loads(sess.read_text(encoding="utf-8"))
    assert any(c["name"] == "user" for c in written["cookies"])
