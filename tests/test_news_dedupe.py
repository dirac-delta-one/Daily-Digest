"""WSJ/FT appended-section dedupe (REDUCE_REPEATS Idea 13): _title_covered
heuristics and build_news_html's exclude_text filtering. build_news_html now
expects PRE-RANKED articles (ranking hoisted to main — F10 superseded).
Also the RSS-level URL dedup key (2026-07-24)."""

import digest
import news


def _article(title, url="https://example.com/a", source="WSJ"):
    return {"title": title, "url": url, "summary": "s", "source": source}


DIGEST_TEXT = (
    '<li><strong>$ORCL (Oracle):</strong> Oracle debt grew to $120bn; '
    'Gray Media repurchased $120MM of notes; Turkey carry trade math still '
    'works per Greenmantle analysis of lira funding costs.</li>'
)


# --- _title_covered heuristics ---

def test_covered_by_proper_noun_bigram():
    assert digest._title_covered("Gray Media Buys Back Debt", DIGEST_TEXT)


def test_covered_by_ticker():
    assert digest._title_covered("Cloud Wars: $ORCL Doubles Down", DIGEST_TEXT)


def test_covered_by_token_overlap():
    # >=60% of content tokens present: turkey/carry/trade/lira
    assert digest._title_covered(
        "Turkey Carry Trade Attracts Lira Bulls", DIGEST_TEXT)


def test_not_covered_distinct_story():
    assert not digest._title_covered(
        "Japan Wage Negotiations Surprise Economists", DIGEST_TEXT)


def test_generic_short_title_kept():
    # <3 content tokens -> too generic to judge -> keep (False)
    assert not digest._title_covered("Markets Rally", DIGEST_TEXT)


def test_no_exclude_text_keeps_everything():
    assert not digest._title_covered("Gray Media Buys Back Debt", "")


# --- build_news_html filtering ---

def test_build_news_html_drops_covered_headlines():
    articles = [
        _article("Gray Media Buys Back Debt"),          # covered -> dropped
        _article("Japan Wage Negotiations Surprise"),   # kept
    ]
    out = digest.build_news_html(articles, exclude_text=DIGEST_TEXT)
    assert "Japan Wage" in out
    assert "Gray Media" not in out


def test_build_news_html_all_covered_returns_empty():
    out = digest.build_news_html(
        [_article("Gray Media Buys Back Debt")], exclude_text=DIGEST_TEXT)
    assert out == ""


# --- RSS URL dedup key (2026-07-24: the same WSJ article arrived via two
# feeds differing only in the ?mod= tracking param and rendered twice) ---

def test_canonical_url_strips_query_and_fragment():
    a = "https://www.wsj.com/business/energy-oil/oil-prices-73df238a?mod=rss_markets_main"
    b = "https://www.wsj.com/business/energy-oil/oil-prices-73df238a?mod=pls_whats_news"
    assert news._canonical_url(a) == news._canonical_url(b)
    assert news._canonical_url("https://x.com/p#frag") == "https://x.com/p"
    # different paths stay distinct
    assert (news._canonical_url("https://x.com/p1?q=1")
            != news._canonical_url("https://x.com/p2?q=1"))


def test_build_news_html_without_exclude_renders_all():
    articles = [_article("Gray Media Buys Back Debt"),
                _article("Japan Wage Negotiations Surprise")]
    out = digest.build_news_html(articles)
    assert "Gray Media" in out and "Japan Wage" in out
    assert "WSJ/FT Articles" in out
