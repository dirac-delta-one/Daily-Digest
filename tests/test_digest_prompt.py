"""Phase 3.1 — pin the keyword-only digest-core signatures and source routing.

`_build_source_prompt` takes 17 same-typed source arguments; the refactor made
them keyword-only so a caller can't silently route (say) ratings into the funds
slot. These tests pin both the keyword-only contract and that each source lands
in its own section.
"""

import pytest

import digest


SUBSTACK_ARTICLES = [{
    "title": "SENTINEL_SUBSTACK",
    "author": "Author",
    "url": "https://example.com/p/x",
    "text": "substack body",
}]


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


def test_source_prompt_never_contains_substack():
    # TEAM_DIGEST_SPEC: the base prompt is the TEAM-shareable view — Substack
    # lives only in the trailing _build_substack_block, so the team prompt is a
    # strict prefix of the full prompt (and can never leak jared's subs).
    prompt = digest._build_source_prompt(**_kwargs())
    assert "SUBSTACK" not in prompt.upper()


def test_build_source_prompt_is_deterministic():
    kwargs = _kwargs()
    assert digest._build_source_prompt(**kwargs) == digest._build_source_prompt(**kwargs)


# --- response text extraction (Fable 5 thinking-block compatibility) ---

class _Block:
    def __init__(self, type, text=None):
        self.type = type
        if text is not None:
            self.text = text


class _Resp:
    def __init__(self, blocks):
        self.content = blocks


def test_response_text_skips_thinking_block():
    # Fable 5 returns a ThinkingBlock first; the visible answer is a later text
    # block. content[0].text would have grabbed the thinking (or raised).
    resp = _Resp([_Block("thinking"), _Block("text", "<div>digest</div>")])
    assert digest._response_text(resp) == "<div>digest</div>"


def test_response_text_plain_opus_single_block():
    resp = _Resp([_Block("text", "<div>digest</div>")])
    assert digest._response_text(resp) == "<div>digest</div>"


def test_omitted_sources_produce_no_section():
    # With only emails supplied, none of the other section headers appear.
    kwargs = _kwargs()
    for k in ("sec_filings", "rating_actions"):
        kwargs[k] = []
    kwargs["wiltw"] = None
    kwargs["memory_context"] = ""
    prompt = digest._build_source_prompt(**kwargs)

    assert "SEC FILINGS:" not in prompt
    assert "RATING AGENCY ACTIONS:" not in prompt
    assert "13D RESEARCH" not in prompt
    # Email content still present
    assert "SENTINEL_EMAIL" in prompt


# --- _build_substack_block (TEAM_DIGEST_SPEC: the full variant's tail) ---

def test_substack_block_contains_articles():
    block = digest._build_substack_block(SUBSTACK_ARTICLES)
    assert "SUBSTACK ARTICLES:" in block
    assert "SENTINEL_SUBSTACK" in block
    assert "primary research sources" in block


def test_substack_block_includes_memory_context():
    block = digest._build_substack_block(
        SUBSTACK_ARTICLES, substack_memory_context="SENTINEL_SUBMEM context")
    assert "SENTINEL_SUBMEM" in block
    # memory context precedes the articles (yesterday's storylines frame today's)
    assert block.find("SENTINEL_SUBMEM") < block.find("SENTINEL_SUBSTACK")


def test_substack_block_empty_when_nothing():
    assert digest._build_substack_block([]) == ""
    assert digest._build_substack_block([], substack_memory_context="") == ""


def test_substack_block_memory_only():
    block = digest._build_substack_block([], substack_memory_context="SENTINEL_SUBMEM")
    assert "SENTINEL_SUBMEM" in block
    assert "SUBSTACK ARTICLES:" not in block
