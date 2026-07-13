"""Phase 3.1 — pin the keyword-only digest-core signatures and source routing.

`_build_source_prompt` takes 17 same-typed source arguments; the refactor made
them keyword-only so a caller can't silently route (say) ratings into the funds
slot. These tests pin both the keyword-only contract and that each source lands
in its own section.
"""

import pytest

import digest


def _kwargs():
    """Representative inputs with a distinct sentinel per source we can assert on."""
    return dict(
        emails=[{
            "from": "Broker Desk <desk@example.com>",
            "subject": "SENTINEL_EMAIL",
            "date": "Mon, 30 Jun 2026 09:00:00 -0400",
            "snippet": "email snippet",
            "pdfs": [],
        }],
        substack_articles=[{
            "title": "SENTINEL_SUBSTACK",
            "author": "Author",
            "url": "https://example.com/p/x",
            "text": "substack body",
        }],
        sec_filings=[{
            "ticker": "ABC",
            "company": "Acme Corp",
            "form_type": "8-K",
            "date": "2026-06-30",
            "url": "https://sec.example/abc",
            "description": "desc",
            "content": "SENTINEL_FILING body",
        }],
        market_data=[],
        macro_data=[],
        memory_context="SENTINEL_MEMORY context line",
        earnings=[],
        pacer_entries=[],
        rating_actions=[{
            "source": "Moody's",
            "title": "SENTINEL_RATING downgrades XYZ",
            "url": "https://example.com/r",
            "description": "rating desc",
        }],
        fund_results=[],
        wiltw={"title": "WILTW", "summary": "SENTINEL_WILTW summary"},
        research_articles=[],
        treasury_auctions=[],
        cot_data=[],
        fed_bs=[],
        bank_failures=[],
    )


# --- keyword-only contract ---

def test_build_source_prompt_rejects_positional():
    with pytest.raises(TypeError):
        digest._build_source_prompt([], [], [], [], [], "", [], [], [])


def test_summarize_with_claude_rejects_positional():
    # Argument binding fails before the body runs, so no anthropic client is
    # constructed and no API call is made.
    with pytest.raises(TypeError):
        digest.summarize_with_claude([], [])


# --- source routing: each sentinel lands in its own section ---

def test_each_source_routes_to_its_section():
    prompt = digest._build_source_prompt(**_kwargs())

    # Emails
    assert "SENTINEL_EMAIL" in prompt
    assert "Subject: SENTINEL_EMAIL" in prompt
    # Substack
    assert "SUBSTACK ARTICLES:" in prompt
    assert "SENTINEL_SUBSTACK" in prompt
    # SEC filings
    assert "SEC FILINGS:" in prompt
    assert "SENTINEL_FILING" in prompt
    # 13D WILTW
    assert "13D RESEARCH" in prompt
    assert "SENTINEL_WILTW" in prompt
    # Rating actions
    assert "RATING AGENCY ACTIONS:" in prompt
    assert "SENTINEL_RATING" in prompt
    # Cross-digest memory (passed through verbatim)
    assert "SENTINEL_MEMORY" in prompt


def test_build_source_prompt_is_deterministic():
    kwargs = _kwargs()
    assert digest._build_source_prompt(**kwargs) == digest._build_source_prompt(**kwargs)


def test_omitted_sources_produce_no_section():
    # With only emails supplied, none of the other section headers appear.
    kwargs = _kwargs()
    for k in ("substack_articles", "sec_filings", "rating_actions"):
        kwargs[k] = []
    kwargs["wiltw"] = None
    kwargs["memory_context"] = ""
    prompt = digest._build_source_prompt(**kwargs)

    assert "SUBSTACK ARTICLES:" not in prompt
    assert "SEC FILINGS:" not in prompt
    assert "RATING AGENCY ACTIONS:" not in prompt
    assert "13D RESEARCH" not in prompt
    # Email content still present
    assert "SENTINEL_EMAIL" in prompt
