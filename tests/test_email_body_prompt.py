"""FORWARDING_FIX_SPEC Stage 2 — capped body extract into the digest prompt."""

import digest
from html_utils import strip_forward_header


def _email(**kw):
    base = {"from": "Broker <d@x.com>", "subject": "s", "date": "d",
            "snippet": "SNIP", "body": "", "pdfs": []}
    base.update(kw)
    return base


def _prompt_kwargs(emails):
    return dict(
        emails=emails, sec_filings=[], market_data=[], macro_data=[],
        memory_context="", earnings=[], pacer_entries=[], rating_actions=[],
        fund_results=[], wiltw=None, research_articles=[], treasury_auctions=[],
        cot_data=[], fed_bs=[], bank_failures=[],
    )


# --- strip_forward_header ---

def test_strip_outlook_header():
    text = ("From: Bloomberg <n@bloomberg.net>\nSent: Monday\nTo: Jared\n"
            "Subject: News\n\nStocks fell on oil.")
    assert strip_forward_header(text) == "Stocks fell on oil."


def test_strip_gmail_marker_and_header():
    text = ("---------- Forwarded message ---------\nFrom: X <x@y.com>\n"
            "Date: Mon\nSubject: Hi\n\nReal content here.")
    assert strip_forward_header(text) == "Real content here."


def test_strip_returns_original_if_all_header():
    text = "From: x@y.com\nSubject: Hi"
    assert strip_forward_header(text) == text.strip()


def test_strip_no_header_untouched():
    assert strip_forward_header("Just body text.") == "Just body text."


# --- _email_body_for_prompt ---

def test_body_extract_replaces_snippet():
    e = _email(body="Full body content that is long.", snippet="SNIP")
    out = digest._email_body_for_prompt(e, 4000)
    assert "Full body content" in out and out != "SNIP"


def test_body_extract_capped():
    e = _email(body="X" * 9000)
    out = digest._email_body_for_prompt(e, 4000)
    assert len(out) <= 4010 and out.endswith("[…]")


def test_body_extract_strips_forward_header():
    e = _email(body="From: Bloomberg <n@bloomberg.net>\nSent: Mon\nSubject: N\n\nOil up.")
    assert digest._email_body_for_prompt(e, 4000) == "Oil up."


def test_body_extract_snippet_fallback_no_body():
    e = _email(body="", snippet="only snippet")
    assert digest._email_body_for_prompt(e, 4000) == "only snippet"


def test_body_extract_zero_budget_uses_snippet():
    e = _email(body="lots of body", snippet="SNIP")
    assert digest._email_body_for_prompt(e, 0) == "SNIP"


# --- _looks_like_promo (conservative: >= 3 markers) ---

def test_promo_needs_three_markers():
    spam = _email(subject="Special offer!",
                  snippet="unsubscribe / view in browser / promo code")
    assert digest._looks_like_promo(spam) is True


def test_newsletter_with_two_markers_not_promo():
    nl = _email(subject="FT Markets", snippet="Markets fell. unsubscribe | view in browser")
    assert digest._looks_like_promo(nl) is False


# --- budget allocation via _build_source_prompt ---

def test_pdf_email_stays_lean():
    long_body = "PDFBODY " * 2000  # ~16k chars
    e = _email(body=long_body, pdfs=[{"filename": "note.pdf"}])
    prompt = digest._build_source_prompt(**_prompt_kwargs([e]))
    # only the lean ~500-char cap should appear, not all 2000 repeats
    assert prompt.count("PDFBODY") < 100


def test_text_forward_gets_full_body_and_attribution():
    body = "FORWARDCONTENT " * 100  # 1500 chars, under the 4000 cap
    e = _email(body=body, **{"from": "Jared <jtramontano@acorninv.com>",
                             "effective_from": "Bloomberg <n@bloomberg.net>"})
    prompt = digest._build_source_prompt(**_prompt_kwargs([e]))
    assert "FORWARDCONTENT" in prompt and "forwarded by" in prompt


def test_promo_email_demoted_to_snippet_in_prompt():
    e = _email(subject="Special offer", snippet="deal",
               body="BUYNOW " * 500,
               **{"from": "promo@spam.com"})
    # 3 markers so it's flagged; wait — ensure markers present:
    e["snippet"] = "unsubscribe view in browser promo code deal"
    prompt = digest._build_source_prompt(**_prompt_kwargs([e]))
    assert "BUYNOW" not in prompt
