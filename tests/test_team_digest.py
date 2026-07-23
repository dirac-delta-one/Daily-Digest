"""TEAM_DIGEST_SPEC — recipient split, variant save/load, and the 2-pass
content structure (team prompt = strict cache prefix of the full prompt).
All offline: fake Anthropic client, tmp dirs, no network."""

import base64
import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import digest
import reply_monitor


# --- Stage 1: recipient split ---

def test_recipients_from_env_parses(monkeypatch):
    monkeypatch.setenv("X_RECIP", " a@x.com , b@y.com ,")
    assert digest._recipients_from_env("X_RECIP", "d@z.com") == ["a@x.com", "b@y.com"]


def test_recipients_from_env_default(monkeypatch):
    monkeypatch.delenv("X_RECIP", raising=False)
    assert digest._recipients_from_env("X_RECIP", "d@z.com") == ["d@z.com"]


def test_team_recipients_default_empty(monkeypatch):
    monkeypatch.delenv("DIGEST_TO_TEAM", raising=False)
    assert digest._recipients_from_env("DIGEST_TO_TEAM", "") == []


# --- Stage 4: variant save/load ---

def test_save_daily_digest_team_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path / "digests")
    d = datetime.date(2026, 7, 13)
    digest.save_daily_digest("<div>full</div>", date=d)
    digest.save_daily_digest("<div>team</div>", date=d, team=True)
    assert (tmp_path / "digests" / "2026-07-13.html").read_text(encoding="utf-8") == "<div>full</div>"
    assert (tmp_path / "digests" / "2026-07-13_team.html").read_text(encoding="utf-8") == "<div>team</div>"


def test_get_week_digests_variant_separation(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path / "digests")
    monday = digest._week_monday()
    digest.save_daily_digest("<div>full</div>", date=monday)
    digest.save_daily_digest("<div>team</div>", date=monday, team=True)
    full = digest._get_week_digests()
    team = digest._get_week_digests(team=True)
    assert [d["html"] for d in full] == ["<div>full</div>"]
    assert [d["html"] for d in team] == ["<div>team</div>"]


def test_save_weekly_digest_team_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path / "digests")
    d = datetime.date(2026, 7, 17)
    digest.save_weekly_digest("<div>w</div>", date=d, team=True)
    assert (tmp_path / "digests" / "weekly_2026-07-17_team.html").exists()
    # weekly files (either variant) are invisible to the daily loaders
    assert digest._get_week_digests() == []
    assert digest._get_week_digests(team=True) == []


# --- Stage 4: 2-pass content structure (fake client, no API) ---

def _fake_response():
    return SimpleNamespace(
        content=[SimpleNamespace(text="<div>digest</div>")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                              cache_read_input_tokens=0,
                              cache_creation_input_tokens=0),
    )


def _capture_calls(monkeypatch):
    calls = []

    class _FakeStream:
        # digest passes use client.messages.stream(...) since the 2026-07-23
        # max_tokens raise (SDK long-request requirement); same kwargs shape.
        def __init__(self, kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return _fake_response()

    class _FakeClient:
        def __init__(self):
            self.messages = SimpleNamespace(
                create=self._create,
                stream=lambda **kwargs: _FakeStream(kwargs))

        def _create(self, **kwargs):
            calls.append(kwargs)
            return _fake_response()

    monkeypatch.setattr(digest.anthropic, "Anthropic", _FakeClient)
    monkeypatch.setattr(digest, "get_memory_context", lambda: "SHARED_MEMCTX")
    return calls


_EMAILS = [{"from": "a@b.c", "subject": "s", "date": "", "snippet": "x", "pdfs": []}]
_SUBSTACK = [{"title": "SENTINEL_SUBSTACK", "author": "A",
              "url": "https://x.substack.com/p/y", "text": "body"}]


def test_full_variant_substack_in_trailing_cached_block(monkeypatch):
    calls = _capture_calls(monkeypatch)
    final, source = digest.summarize_with_claude(
        emails=_EMAILS, substack_articles=_SUBSTACK,
        substack_memory_context="SENTINEL_SUBMEM")

    assert len(calls) == 2  # two passes
    content = calls[0]["messages"][0]["content"]
    # [prompt(bp)][substack tail(bp)][pass-1 instruction]
    assert len(content) == 3
    assert "SUBSTACK ARTICLES:" not in content[0]["text"]  # shared prefix is team-safe
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert "SENTINEL_SUBSTACK" in content[1]["text"]
    assert "SENTINEL_SUBMEM" in content[1]["text"]
    assert content[1]["cache_control"] == {"type": "ephemeral"}
    # alert-eval source includes the substack tail (full variant's view)
    assert "SENTINEL_SUBSTACK" in source


def test_team_variant_has_no_substack_anywhere(monkeypatch):
    calls = _capture_calls(monkeypatch)
    final, source = digest.summarize_with_claude(
        emails=_EMAILS, substack_articles=[], cost_label=" (team)")

    content = calls[0]["messages"][0]["content"]
    assert len(content) == 2  # [prompt(bp)][instruction] — no tail block
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert "SUBSTACK" not in source.upper()


def test_team_prompt_is_strict_prefix_of_full(monkeypatch):
    calls = _capture_calls(monkeypatch)
    digest.summarize_with_claude(emails=_EMAILS, substack_articles=[])
    digest.summarize_with_claude(emails=_EMAILS, substack_articles=_SUBSTACK)
    team_prefix = calls[0]["messages"][0]["content"][0]["text"]
    full_prefix = calls[2]["messages"][0]["content"][0]["text"]
    # byte-identical shared prefix -> the variants share the prompt cache
    assert team_prefix == full_prefix


# --- Stage 2: asker-only reply addressing ---

def _sent_raw(service):
    body = service.users.return_value.messages.return_value.send.call_args.kwargs["body"]
    return base64.urlsafe_b64decode(body["raw"]).decode("utf-8", errors="replace")


def test_send_reply_addresses_asker_only():
    service = MagicMock()
    reply_monitor.send_reply(service, "tid", "mid", "Re: x", "<div>a</div>",
                             to_addr="asker@example.com")
    raw = _sent_raw(service)
    assert "to: asker@example.com" in raw.lower()
    for r in reply_monitor.DIGEST_RECIPIENTS:
        if r.lower() != "asker@example.com":
            assert r.lower() not in raw.lower().split("\n\n")[0]


def test_send_reply_default_falls_back_to_full_list():
    service = MagicMock()
    reply_monitor.send_reply(service, "tid", "mid", "Re: x", "<div>a</div>")
    raw = _sent_raw(service)
    for r in reply_monitor.DIGEST_RECIPIENTS:
        assert r.lower() in raw.lower()


# --- Full-variant alert window keeps Substack visible (spec §1) ---

def test_alert_source_carves_window_for_substack(monkeypatch):
    # alerts.py evaluates only the first ~50k chars; a huge shared prompt must
    # not push the trailing substack block out of the alert window.
    _capture_calls(monkeypatch)
    big_emails = [{"from": "a@b.c", "subject": "s", "date": "",
                   "snippet": "x" * 60000, "pdfs": []}]
    _final, source = digest.summarize_with_claude(
        emails=big_emails, substack_articles=_SUBSTACK)
    assert "SENTINEL_SUBSTACK" in source
    assert len(source) <= 51000  # 35k shared + 15k substack + markers
    assert "truncated for alert evaluation" in source
