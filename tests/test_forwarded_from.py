"""FORWARDING_FIX_SPEC Stage 1 — pin html_utils.parse_forwarded_from.

Recovers the ORIGINAL sender from a forwarded email body (Outlook / Gmail
formats, newline- or space-separated), and stays conservative: a direct email
or a stray "From:" in prose must NOT be misread as a forward header.
"""

from html_utils import parse_forwarded_from


def test_outlook_forward():
    body = (
        "FYI — see below.\n\n"
        "From: Bloomberg <noreply@bloomberg.net>\n"
        "Sent: Monday, July 13, 2026 1:30 PM\n"
        "To: Jared Tramontano\n"
        "Subject: Today's News\n\n"
        "Stocks fell as..."
    )
    assert parse_forwarded_from(body) == ("Bloomberg", "noreply@bloomberg.net")


def test_gmail_forward():
    body = (
        "---------- Forwarded message ---------\n"
        "From: Stifel Research <research@stifel.com>\n"
        "Date: Mon, Jul 13, 2026 at 8:00 AM\n"
        "Subject: New Issue Flash\n"
        "To: <jaredtramontano@gmail.com>\n\n"
        "New HY deal priced..."
    )
    assert parse_forwarded_from(body) == ("Stifel Research", "research@stifel.com")


def test_space_collapsed_html_forward():
    # extract_gmail_body's HTML fallback replaces tags with spaces (no newlines);
    # the lookahead to the next header label must still bound the From: value.
    body = (
        "From: Bloomberg <noreply@bloomberg.net> Sent: Monday To: Jared "
        "Subject: Today's News Stocks fell..."
    )
    assert parse_forwarded_from(body) == ("Bloomberg", "noreply@bloomberg.net")


def test_bare_email_no_display_name():
    body = (
        "From: research@kbw.com\n"
        "Sent: Monday\n"
        "Subject: KBW Daily\n\n"
        "..."
    )
    assert parse_forwarded_from(body) == ("research@kbw.com", "research@kbw.com")


def test_direct_email_returns_none():
    # No forwarded header block at all.
    assert parse_forwarded_from("Hi — quick question about the digest. Thanks!") is None


def test_prose_from_not_misdetected():
    # "From:" appears but with no neighbouring header label -> not a forward.
    body = "Quoting the memo: 'From: the desk of the CIO' — an interesting phrase, no email here."
    assert parse_forwarded_from(body) is None


def test_quoted_from_without_context_ignored():
    # An email address is present but with no Sent/Date/To/Subject nearby.
    body = "Reach me at analyst@example.com. From: my perspective the trade is crowded."
    assert parse_forwarded_from(body) is None


def test_empty_body():
    assert parse_forwarded_from("") is None
    assert parse_forwarded_from(None) is None


def test_first_from_wins():
    # The forwarded block's original sender is the first From: — not a deeper
    # nested quote further down.
    body = (
        "From: Barclays <notes@barclays.com>\n"
        "Sent: Monday\nSubject: Special Sits\n\n"
        "From: someone-else <x@nested.com>\nSent: earlier\n"
    )
    assert parse_forwarded_from(body) == ("Barclays", "notes@barclays.com")
