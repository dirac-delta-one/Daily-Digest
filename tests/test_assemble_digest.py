"""Stage 2.1 — pin _assemble_digest_html's insertion behavior.

This is the documented brittle coupling (HANDOFF §5): sections are injected by
string-matching the Opus-generated template HTML. These tests pin the CURRENT
behavior — the mechanism itself is §14.B-3.5a wait-and-see and stays unchanged.
"""

import digest


HEADER = ('<div style="border-bottom: 3px double #1a1a1a; padding-bottom: 12px; '
          'margin-bottom: 20px;"><h1>Daily Research Digest</h1></div>')
TLDR = '<div style="background: #f7f5f0;"><strong>tldr</strong></div>'
BODY = '<h2>1. Top Takeaways</h2><ul><li>item</li></ul>'
DIGEST = f'<div style="font-family: Georgia;">{HEADER}{TLDR}{BODY}</div>'


def _assemble(digest_html=DIGEST, **overrides):
    kw = dict(alerts_html="", market_html="", rates_html="", credit_html="",
              private_html="", ai_html="", earnings_html="",
              news_html="", pacer_html="", funds_html="", fed_bs_html="")
    kw.update(overrides)
    return digest._assemble_digest_html(digest_html, **kw)


def test_no_sections_returns_unchanged():
    assert _assemble() == DIGEST


def test_pre_sections_inserted_after_header_before_tldr():
    out = _assemble(alerts_html="<p>ALERTS</p>", market_html="<p>MARKET</p>",
                    rates_html="<p>RATES</p>", credit_html="<p>CREDIT</p>",
                    private_html="<p>PRIVATE</p>", ai_html="<p>AI</p>",
                    earnings_html="<p>EARN</p>", fed_bs_html="<p>FEDBS</p>")
    header_pos = out.find("Daily Research Digest")
    tldr_pos = out.find("tldr")
    for token in ("ALERTS", "MARKET", "RATES", "CREDIT", "PRIVATE",
                  "<p>AI</p>", "FEDBS", "EARN"):
        assert header_pos < out.find(token) < tldr_pos, token
    # pinned insertion order (2026-07-15 snapshot redesign): alerts, market,
    # rates, credit, private, AI, fed BS (bottom of snapshots), earnings
    assert (out.find("ALERTS") < out.find("MARKET") < out.find("RATES")
            < out.find("CREDIT") < out.find("PRIVATE") < out.find("<p>AI</p>")
            < out.find("FEDBS") < out.find("EARN"))


def test_post_sections_appended_before_final_close():
    out = _assemble(news_html="<p>NEWS</p>", funds_html="<p>FUNDS</p>",
                    pacer_html="<p>PACER</p>")
    body_pos = out.find("item")
    end_pos = out.rfind("</div>")
    for token in ("NEWS", "FUNDS", "PACER"):
        assert body_pos < out.find(token) < end_pos, token
    # pinned append order: news, funds, pacer
    assert out.find("NEWS") < out.find("FUNDS") < out.find("PACER")


def test_pre_and_post_combined():
    out = _assemble(alerts_html="<p>ALERTS</p>", news_html="<p>NEWS</p>")
    assert out.find("ALERTS") < out.find("tldr") < out.find("item") < out.find("NEWS")


def test_missing_header_anchor_degrades_gracefully():
    # A digest without the double-border header: pre-sections are skipped
    # (not crashed); post-sections still append.
    bare = f'<div>{TLDR}{BODY}</div>'
    out = _assemble(digest_html=bare, alerts_html="<p>ALERTS</p>",
                    news_html="<p>NEWS</p>")
    assert "ALERTS" not in out
    assert "NEWS" in out
