"""Ticker-name glossary (ticker_names.py, 2026-07-22): learned/SEC name
merging, extraction, glossary determinism, and the validated collect→commit
staging discipline (no disk write between the TEAM and FULL generations)."""

import pytest

import digest
import ticker_names


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Every test gets an empty, throwaway cache file and clean module state."""
    monkeypatch.setattr(ticker_names, "CACHE_PATH", tmp_path / "ticker_names_cache.json")
    monkeypatch.setattr(ticker_names, "_cache", None)
    ticker_names._pending.clear()
    yield
    ticker_names._pending.clear()


def _seed(mapping):
    """Install a learned cache directly."""
    ticker_names._cache = dict(mapping)


# --- name merging / registry title cleanup ---

def test_titlecase_registry_name():
    assert ticker_names._titlecase_registry_name("ORACLE CORP") == "Oracle Corp"
    assert ticker_names._titlecase_registry_name("BRASKEM SA /ADR/") == "Braskem SA"
    assert ticker_names._titlecase_registry_name("APOLLO GLOBAL MANAGEMENT LLC") \
        == "Apollo Global Management LLC"


def test_known_names_learned_wins_over_sec():
    _seed({"ORCL": "Oracle"})
    names = ticker_names.known_names({"ORCL": "ORACLE CORP", "GTN": "GRAY MEDIA INC"})
    assert names["ORCL"] == "Oracle"          # learned beats registry
    assert names["GTN"] == "Gray Media Inc"   # registry title-cased
    # NON_TICKERS never enter via the registry side
    assert "AI" not in ticker_names.known_names({"AI": "C3.AI INC"})


# --- extraction ---

def test_extract_tickers_dollar_and_bare():
    _seed({"BRASKM": "Braskem"})
    text = "Run list: $HTZ 12⅝'29 and BRASKM 5⅞'50; $HY OAS wider; CRWV up."
    ticks = ticker_names.extract_tickers(text)
    assert "HTZ" in ticks                # $-prefixed always
    assert "BRASKM" in ticks             # bare, but a learned key
    assert "CRWV" not in ticks           # bare and NOT learned -> not matched
    assert "HY" not in ticks             # NON_TICKERS excluded even with $


# --- glossary build ---

def test_build_glossary_sorted_known_only_and_deterministic():
    _seed({"BRASKM": "Braskem"})
    sec = {"ORCL": "ORACLE CORP"}
    text = "$ORCL debt; BRASKM 5⅞'50; $ZZZUNKNOWN rumor"
    block, covered = ticker_names.build_glossary(text, sec_names=sec)
    assert "TICKER GLOSSARY" in block
    assert "$BRASKM = Braskem" in block and "$ORCL = Oracle Corp" in block
    assert "ZZZUNKNOWN" not in block            # no name -> no line
    assert covered == {"BRASKM", "ORCL"}
    assert block.index("$BRASKM") < block.index("$ORCL")  # sorted
    assert ticker_names.build_glossary(text, sec_names=sec)[0] == block  # deterministic


def test_build_glossary_exclude_and_empty():
    _seed({"BRASKM": "Braskem"})
    block, covered = ticker_names.build_glossary(
        "BRASKM 5⅞'50", exclude={"BRASKM"})
    assert block == "" and covered == set()
    assert ticker_names.build_glossary("no tickers here") == ("", set())


# --- collect / commit staging discipline ---

DIGEST_HTML = (
    '<li><strong>$FREMOR (Freedom Mortgage):</strong> new 5.5NC2.5 notes</li>'
    '<li><strong>$CRBG/$EQH (Corebridge/Equitable):</strong> merger proxy</li>'
    '<li><strong>$TEVA (Teva, rising-star timeline?):</strong> tariffs</li>'
    '<li><strong>$FAKE (Totally Invented Co):</strong> rumor</li>'
)
SOURCE_TEXT = "Stifel: Freedom Mortgage $500MM deal. Teva generic exposure."


def test_collect_validates_against_sources_and_commit_persists():
    staged = ticker_names.collect(DIGEST_HTML, SOURCE_TEXT)
    assert staged == 2
    # staged only — nothing on disk until commit()
    assert not ticker_names.CACHE_PATH.exists()
    assert ticker_names.commit() == 2
    cache = ticker_names._load_cache()
    assert cache["FREMOR"] == "Freedom Mortgage"
    assert cache["TEVA"] == "Teva"              # first comma segment only
    assert "FAKE" not in cache                  # name absent from sources
    assert "EQH" not in cache                   # slash names rejected
    assert ticker_names.commit() == 0           # pending drained


def test_collect_rejects_descriptive_parenthetical():
    # Observed on Fable 5 (2026-07-22): the model sometimes puts a lowercase
    # descriptive phrase in the name slot. The phrase IS in the sources, so the
    # source-text check passes — the proper-noun (leading-capital) guard is
    # what rejects it, or the cache learns a bogus "name".
    src = ("Sandoz is a potential USD issuer; Viatris is already crossover "
           "rated this quarter.")
    digest_html = (
        '<li><strong>$SDZSW (potential USD issuer):</strong> talk</li>'
        '<li><strong>$VTRS (already crossover):</strong> note</li>'
    )
    assert ticker_names.collect(digest_html, src) == 0
    ticker_names.commit()
    cache = ticker_names._load_cache()
    assert "SDZSW" not in cache and "VTRS" not in cache


def test_collect_learns_name_first_form():
    # "Name ($TICK)" — the reverse rendering ("Gray Media ($GTN)") must learn
    # too; an over-greedy word grab fails source validation instead of caching.
    staged = ticker_names.collect(
        "<li><strong>Broadcast:</strong> Gray Media ($GTN) buyback</li>",
        "8-K: Gray Media repurchased debt")
    assert staged == 1
    ticker_names.commit()
    assert ticker_names._load_cache()["GTN"] == "Gray Media"


def test_collect_skips_already_known_pairs():
    staged = ticker_names.collect(
        "<li><strong>$FREMOR (Freedom Mortgage):</strong> deal</li>",
        SOURCE_TEXT, known={"FREMOR": "Freedom Mortgage"})
    assert staged == 0


# --- digest integration: glossary lands in the shared prompt ---

def _prompt_kwargs(body):
    return dict(
        emails=[{"from": "Desk <d@example.com>", "subject": "run list",
                 "date": "Wed, 22 Jul 2026 07:00:00 -0400",
                 "snippet": body, "body": body, "pdfs": []}],
        sec_filings=[], market_data=[], macro_data=[], memory_context="",
        earnings=[], pacer_entries=[], rating_actions=[], fund_results=[],
        wiltw=None, research_articles=[], treasury_auctions=[], cot_data=[],
        fed_bs=[], bank_failures=[],
    )


def test_source_prompt_carries_glossary_and_stays_deterministic():
    _seed({"BRASKM": "Braskem"})
    kwargs = _prompt_kwargs("Movers: $BRASKM 5⅞'50 +1¾ to $44¼")
    prompt = digest._build_source_prompt(**kwargs)
    assert "TICKER GLOSSARY" in prompt
    assert "$BRASKM = Braskem" in prompt
    assert digest._build_source_prompt(**kwargs) == prompt


def test_source_prompt_no_glossary_when_nothing_known():
    kwargs = _prompt_kwargs("Movers: $ZZZUNKNOWN +1")
    assert "TICKER GLOSSARY" not in digest._build_source_prompt(**kwargs)
