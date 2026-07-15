"""Substack-via-email boundary (2026-07-15).

Paid Substack newsletters also arrive as inbox email (e.g. PETITION from
petition@substack.com). They are jared-personal, so they must be treated as
Substack: kept out of the TEAM digest prompt (digest.summarize_with_claude
filters them from the shared/cached prefix) and tagged source_type="substack"
at index time so team-tier reply retrieval (exclude_source_types) drops them.
"""

import json

import config
import search


# --- config.is_substack_email ---

def test_is_substack_email_direct():
    assert config.is_substack_email("PETITION <petition@substack.com>")
    assert config.is_substack_email("Substack <no-reply@substack.com>")


def test_is_substack_email_subdomain():
    assert config.is_substack_email("x <newsletter@mail.substack.com>")


def test_is_substack_email_forwarded_effective_from():
    # Outer sender is a forwarder (jared); the recovered effective_from is the pub.
    assert config.is_substack_email(
        "Jared <jtramontano@acorninv.com>", "PETITION <petition@substack.com>"
    )


def test_is_substack_email_negatives():
    assert not config.is_substack_email("Bloomberg <noreply@bloomberg.net>")
    assert not config.is_substack_email("Broker Desk <desk@stifel.com>")
    assert not config.is_substack_email("", None)
    # A display-name mention without the domain must not trip it.
    assert not config.is_substack_email("Some Substack Fan <fan@example.com>")


# --- index-side tagging (search._chunks_for_date) ---

def _day_dir(tmp_path, monkeypatch, date="2026-07-15"):
    monkeypatch.setattr(search, "ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(search, "SCRIPT_DIR", tmp_path)
    day = tmp_path / "archive" / date
    day.mkdir(parents=True)
    return day


def test_substack_email_tagged_substack_type(tmp_path, monkeypatch):
    day = _day_dir(tmp_path, monkeypatch)
    sub_body = "Serta Simmons LME analysis and paid distressed-credit content. " * 20
    broker_body = "A forwarded broker note about new-issue flow and spreads. " * 20
    (day / "emails.json").write_text(json.dumps([
        {"from": "PETITION <petition@substack.com>",
         "effective_from": "PETITION <petition@substack.com>",
         "subject": "Serta Simmons: Another Failed LME. Part VII.", "body": sub_body},
        {"from": "Broker Desk <desk@stifel.com>",
         "effective_from": "Broker Desk <desk@stifel.com>",
         "subject": "New Issue Flash", "body": broker_body},
    ]), encoding="utf-8")

    email_chunks = [m for _c, m in search._chunks_for_date("2026-07-15")
                    if "_email_" in m["chunk_id"]]
    # The substack newsletter's chunks are tagged "substack" (dropped for team askers)...
    assert any(m["source_type"] == "substack" for m in email_chunks)
    # ...while the broker note stays a normal "email" chunk.
    assert any(m["source_type"] == "email" for m in email_chunks)


def test_forwarded_substack_email_tagged_substack(tmp_path, monkeypatch):
    day = _day_dir(tmp_path, monkeypatch)
    body = "Forwarded paid newsletter content worth indexing at length. " * 20
    (day / "emails.json").write_text(json.dumps([
        {"from": "Jared <jtramontano@acorninv.com>",
         "effective_from": "PETITION <petition@substack.com>",
         "subject": "Fwd: paid post", "body": body},
    ]), encoding="utf-8")

    email_chunks = [m for _c, m in search._chunks_for_date("2026-07-15")
                    if "_email_" in m["chunk_id"]]
    assert email_chunks and all(m["source_type"] == "substack" for m in email_chunks)
