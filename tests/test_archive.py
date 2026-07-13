"""Stage 2.1 — pin archive_daily_content's PDF handling + JSON shapes
(previously untested): hostile filenames sanitized, PDF bytes saved, base64
stripped from the archived emails.json, wiltw snapshot written."""

import base64
import json

import pytest

import archive


@pytest.fixture
def tmp_archive(tmp_path, monkeypatch):
    """Isolate both the archive dir and SCRIPT_DIR (memory.json snapshot)."""
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(archive, "SCRIPT_DIR", tmp_path)
    return tmp_path / "archive"


def test_pdf_saved_sanitized_and_base64_stripped(tmp_archive):
    pdf_bytes = b"%PDF-1.4 fake pdf body"
    emails = [{
        "from": "Desk <d@example.com>", "subject": "note", "date": "",
        "snippet": "s", "body": "b",
        "pdfs": [{"filename": "My Report: Q2 <final>.pdf",
                  "base64": base64.standard_b64encode(pdf_bytes).decode()}],
    }]
    returned = archive.archive_daily_content(
        date="2026-07-10", digest_html="<div>d</div>", emails=emails)
    day_dir = tmp_archive / "2026-07-10"

    # PDF written with a sanitized name (no ':', '<', '>'), bytes intact
    saved = list((day_dir / "pdfs").glob("*.pdf"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == pdf_bytes
    assert all(c.isalnum() or c in ".-_ " for c in saved[0].name)

    # emails.json records the filename and carries NO base64 payload
    emails_json = json.loads((day_dir / "emails.json").read_text(encoding="utf-8"))
    assert emails_json[0]["pdf_filenames"] == [saved[0].name]
    assert "pdfs" not in emails_json[0]
    assert "base64" not in json.dumps(emails_json)

    assert (day_dir / "digest.html").read_text(encoding="utf-8") == "<div>d</div>"
    assert returned == str(day_dir)


def test_wiltw_snapshot_and_empty_sources(tmp_archive):
    archive.archive_daily_content(date="2026-07-10",
                                  wiltw={"title": "T", "summary": "S"})
    day_dir = tmp_archive / "2026-07-10"
    assert json.loads((day_dir / "wiltw.json").read_text(encoding="utf-8"))["title"] == "T"
    # omitted sources still archive as valid empty lists (the indexer reads these)
    for name in ("emails.json", "news.json", "filings.json", "substacks.json"):
        assert json.loads((day_dir / name).read_text(encoding="utf-8")) == []


def test_team_digest_archived_when_provided(tmp_archive):
    archive.archive_daily_content(date="2026-07-13", digest_html="<div>full</div>",
                                  digest_team_html="<div>team</div>")
    day_dir = tmp_archive / "2026-07-13"
    assert (day_dir / "digest.html").read_text(encoding="utf-8") == "<div>full</div>"
    assert (day_dir / "digest_team.html").read_text(encoding="utf-8") == "<div>team</div>"


def test_no_team_file_when_not_provided(tmp_archive):
    archive.archive_daily_content(date="2026-07-13", digest_html="<div>full</div>")
    assert not (tmp_archive / "2026-07-13" / "digest_team.html").exists()


def test_unreadable_pdf_base64_does_not_crash(tmp_archive):
    emails = [{"from": "x", "subject": "s", "date": "", "snippet": "", "body": "",
               "pdfs": [{"filename": "bad.pdf", "base64": "!!!not-base64!!!"}]}]
    archive.archive_daily_content(date="2026-07-10", emails=emails)
    day_dir = tmp_archive / "2026-07-10"
    emails_json = json.loads((day_dir / "emails.json").read_text(encoding="utf-8"))
    assert emails_json[0]["pdf_filenames"] == []  # failed save recorded as absent
