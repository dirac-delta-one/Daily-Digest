"""Stage 0 (memory refactor) — pin the eval harness's golden-match semantics.

tools/ is not a package, so the harness is loaded by file path. Importing it is
cheap: search's embedding model only loads lazily inside search(), which these
tests never call.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "eval_retrieval",
    Path(__file__).resolve().parents[1] / "tools" / "eval_retrieval.py",
)
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


META = {
    "source_type": "wiltw",
    "source_name": "13D Research: What I Learned This Week",
    "text": "Tungsten plays: Almonty Industries (ALM, $16.46) on the squeeze.",
}


# --- _matches: every specified field must hold ---

def test_matches_all_fields():
    assert ev._matches(META, {
        "source_type": "wiltw",
        "source_name_contains": "13d research",
        "text_contains_any": ["Almonty", "nope"],
    }) is True


def test_matches_wrong_source_type():
    assert ev._matches(META, {"source_type": "pdf"}) is False


def test_matches_source_name_case_insensitive():
    assert ev._matches(META, {"source_name_contains": "WHAT I LEARNED"}) is True
    assert ev._matches(META, {"source_name_contains": "grants"}) is False


def test_matches_text_any_semantics():
    assert ev._matches(META, {"text_contains_any": ["missing", "tungsten"]}) is True
    assert ev._matches(META, {"text_contains_any": ["missing", "absent"]}) is False


def test_matches_empty_expect_matches_everything():
    assert ev._matches(META, {}) is True


# --- _first_match_rank: 1-based rank of first hit across alternatives ---

def test_first_match_rank_basic():
    results = [
        ({"source_type": "news", "source_name": "WSJ", "text": "oil"}, 0.9),
        (META, 0.8),
    ]
    expects = [{"source_type": "wiltw"}]
    assert ev._first_match_rank(results, expects) == 2


def test_first_match_rank_any_alternative():
    results = [({"source_type": "pdf", "source_name": "Wiltw 2026-06-25", "text": "Almonty"}, 0.9)]
    expects = [
        {"source_type": "wiltw", "text_contains_any": ["Almonty"]},
        {"source_type": "pdf", "source_name_contains": "wiltw", "text_contains_any": ["Almonty"]},
    ]
    assert ev._first_match_rank(results, expects) == 1


def test_first_match_rank_miss_returns_none():
    results = [({"source_type": "news", "source_name": "WSJ", "text": "oil"}, 0.9)]
    assert ev._first_match_rank(results, [{"source_type": "wiltw"}]) is None
