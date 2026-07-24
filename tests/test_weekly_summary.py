"""Stage 2.4 — the weekly-wrap bundle: operator-specified subject, Monday math,
preamble strip (shared with digest pass 2), and save-to-disk."""

import datetime
from types import SimpleNamespace

import config
import digest


# --- _week_monday ---

def test_week_monday():
    assert digest._week_monday(datetime.date(2026, 7, 10)) == datetime.date(2026, 7, 6)  # Fri
    assert digest._week_monday(datetime.date(2026, 7, 6)) == datetime.date(2026, 7, 6)   # Mon
    assert digest._week_monday(datetime.date(2026, 7, 12)) == datetime.date(2026, 7, 6)  # Sun


# --- _weekly_subject (operator-specified wording, 2026-07-10) ---

def test_weekly_subject_format():
    subject = digest._weekly_subject(datetime.date(2026, 7, 6))
    assert subject == "\U0001f4ca Weekly Research Wrap — Week of Monday, July 6"


def test_weekly_subject_no_leading_zero_day():
    subject = digest._weekly_subject(datetime.date(2026, 8, 3))
    assert subject.endswith("Week of Monday, August 3")


def test_weekly_subject_never_matches_reply_query():
    # The reply bot matches "Re: 📬 Daily Inbox Digest" — the weekly must not collide
    subject = digest._weekly_subject(datetime.date(2026, 7, 6))
    assert not subject.startswith(config.DIGEST_SUBJECT_PREFIX)


# --- _strip_to_html (pass 2 + weekly share it) ---

def test_strip_to_html_drops_preamble():
    assert digest._strip_to_html("Here is the digest:\n<div>x</div>") == "<div>x</div>"


def test_strip_to_html_passthrough():
    assert digest._strip_to_html("<div>x</div>") == "<div>x</div>"
    assert digest._strip_to_html("no div at all") == "no div at all"


def test_strip_to_html_drops_trailing_changelog():
    # Regression for the 2026-07-21 team-digest leak: pass 2 appended a markdown
    # "Changes made:" changelog AFTER the final </div>, which rode into the sent
    # email as raw markdown. Note the changelog contains '>' ("Japan >$180B"),
    # so a naive cut-at-last-'>' would keep most of it — matching the last
    # closing tag is what makes this correct.
    html = (
        '<div style="font-family: Georgia;">'
        "<ul><li>US to hit Canada with 50% tariffs on wide range of goods (FT)</li></ul>\n"
        "</div>"
    )
    leaked = html + (
        "\n\n**Changes made:**\n"
        '- **Fixed error:** "Worth Reading" Greenmantle link pointed to the wrong URL.\n'
        "- **Added missed detail:** ... Japan >$180B repatriation from 13D; Barings +184bp yield.\n"
    )
    assert digest._strip_to_html(leaked) == html


def test_strip_to_html_keeps_non_div_closing_tag():
    # The weekly wrap shares this helper; guard that a template ending in a tag
    # other than </div> (with trailing chatter) is still returned intact.
    html = "<div><table><tr><td>wrap</td></tr></table></div>"
    assert digest._strip_to_html(html + "\n\nDone — hope that helps!") == html


# --- generate_weekly_summary call shape (fake client, no API) ---

def test_weekly_summary_streams_with_headroom(monkeypatch):
    # 2026-07-24 debut: BOTH weeklies hit the old 10k non-streaming cap at
    # exactly 10,000 out (Fable thinking bills as output) and the TEAM wrap
    # emailed truncated mid-bullet. Pin the streaming call + the raised cap.
    calls = []

    class _FakeStream:
        def __init__(self, kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="<div>weekly</div>")],
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                      cache_read_input_tokens=0,
                                      cache_creation_input_tokens=0),
            )

    class _FakeClient:
        def __init__(self):
            self.messages = SimpleNamespace(
                stream=lambda **kwargs: _FakeStream(kwargs))

    monkeypatch.setattr(digest.anthropic, "Anthropic", _FakeClient)
    out = digest.generate_weekly_summary(
        [{"day": "Monday", "date": "2026-07-20", "html": "<div>d</div>"}])
    assert out == "<div>weekly</div>"
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 32000


# --- save_weekly_digest ---

def test_save_weekly_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path / "digests")
    digest.save_weekly_digest("<div>weekly</div>", date=datetime.date(2026, 7, 10))
    saved = tmp_path / "digests" / "weekly_2026-07-10.html"
    assert saved.read_text(encoding="utf-8") == "<div>weekly</div>"


def test_weekly_filename_invisible_to_week_digest_loader(tmp_path, monkeypatch):
    # _get_week_digests loads exact "<iso-date>.html" names — a saved weekly
    # file must never be picked up as a daily digest input next Friday.
    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path / "digests")
    digest.save_weekly_digest("<div>weekly</div>")
    assert digest._get_week_digests() == []
