"""Phase 3.2 — pin the consolidated HTML stripper + Gmail body extractor."""

import base64

import html_utils


def _b64(s):
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")


# --- strip_html / HTMLStripper ---

def test_strip_html_basic_and_script_skip():
    assert html_utils.strip_html("<p>Hello <b>world</b></p><script>x=1</script>") == "Hello world"


def test_strip_html_unescapes_entities():
    assert html_utils.strip_html("<p>A &amp; B</p>") == "A & B"


def test_strip_html_skips_head():
    assert html_utils.strip_html("<head><title>T</title></head><p>Body</p>") == "Body"


def test_strip_html_table_newlines():
    assert html_utils.strip_html("<table><tr><td>a</td><td>b</td></tr></table>") == "a\nb"


def test_strip_html_empty_and_none():
    assert html_utils.strip_html("") == ""
    assert html_utils.strip_html(None) == ""


# --- extract_gmail_body ---

def test_extract_gmail_plain():
    payload = {"mimeType": "text/plain", "body": {"data": _b64("Hello there")}}
    assert html_utils.extract_gmail_body(payload) == "Hello there"


def test_extract_gmail_html_fallback():
    payload = {"mimeType": "text/html", "body": {"data": _b64("<p>Hi</p>")}}
    # html path does a raw regex strip (no whitespace collapse), matching prior behavior
    assert html_utils.extract_gmail_body(payload) == " Hi "


def test_extract_gmail_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64("Plain text")}},
            {"mimeType": "text/html", "body": {"data": _b64("<p>html</p>")}},
        ],
    }
    assert html_utils.extract_gmail_body(payload) == "Plain text html "


def test_extract_gmail_cap():
    payload = {"mimeType": "text/plain", "body": {"data": _b64("A" * 100)}}
    assert html_utils.extract_gmail_body(payload, cap=50) == "A" * 50
    assert html_utils.extract_gmail_body(payload) == "A" * 100  # uncapped by default
