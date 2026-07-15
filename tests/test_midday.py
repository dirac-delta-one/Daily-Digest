"""Cleanup Stage 1.2 — pin midday's materiality-result parsing.

The recipient-combining pin lives in test_team_digest.py; this covers the
previously untested string handling in _parse_alert_result (extracted from
main() for testability, behavior unchanged).
"""

import midday


SEP = "=" * 40  # the MATERIALITY_PROMPT example uses a 40-char separator


def test_separator_with_preamble_lines():
    result = f"Some preamble sentence.\nMoody's downgrades XYZ to junk\n{SEP}\n<div>body</div>"
    subject, html = midday._parse_alert_result(result)
    # subject = LAST line before the separator, not the preamble
    assert subject == "Moody's downgrades XYZ to junk"
    assert html == "<div>body</div>"


def test_separator_leftover_equals_stripped():
    # split on the FIRST 10 '=' leaves the remaining 30 in front of the HTML;
    # the strip-to-<div pass must remove them
    result = f"Subject line\n{SEP}\n<div>body</div>"
    _, html = midday._parse_alert_result(result)
    assert html.startswith("<div>")


def test_no_separator_fallback():
    result = "A short alert without any separator\nsecond line " + "x" * 80
    subject, html = midday._parse_alert_result(result)
    assert subject == result[:60].replace("\n", " ")
    assert html.startswith("A short alert")  # no <div → unchanged


def test_html_at_start_unchanged():
    # html part already starting at <div (post-strip) passes through untouched
    subject, html = midday._parse_alert_result("S\n" + SEP + "\n<div>x</div>")
    assert subject == "S"
    assert html == "<div>x</div>"


def test_no_alert_passthrough():
    # main() checks for NO_ALERT before parsing; pinned anyway so the helper's
    # fallback path is safe if that ordering ever changes
    subject, html = midday._parse_alert_result("NO_ALERT")
    assert subject == "NO_ALERT"
    assert html == "NO_ALERT"


def test_no_div_body_keeps_leftover_separator():
    # Pre-existing behavior, pinned as-is: without a <div to anchor on, the
    # 30 leftover '=' from splitting a 40-char separator on its first 10 stay
    # in front of the body (harmless — the prompt mandates a <div body).
    subject, html = midday._parse_alert_result(f"Subj\n{SEP}\nplain text body")
    assert subject == "Subj"
    assert html == "=" * 30 + "\nplain text body"
