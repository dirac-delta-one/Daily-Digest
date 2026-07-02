"""Phase 3.4 — pin behavior of search._chunk_text (chunking math).
Stage 1 (memory refactor) — pin _search_vectors subset search + rerank ordering.
Stage 2 — pin the BM25 tokenizer, RRF fusion math, and search-state cache invalidation.
Stage 3a — pin entity extraction and the combined date/entity id-filtering."""

import json

import numpy as np

import search


def test_chunk_text_empty():
    assert search._chunk_text("") == []


def test_chunk_text_too_short():
    assert search._chunk_text("short text") == []
    assert search._chunk_text("a" * 49) == []


def test_chunk_text_single_chunk():
    text = "x" * 100
    chunks = search._chunk_text(text)
    assert chunks == [text]


def test_chunk_text_multiple_overlapping():
    text = ("The quick brown fox jumps over the lazy dog. " * 60).strip()
    chunks = search._chunk_text(text)
    assert len(chunks) >= 3
    assert all(len(c) >= 50 for c in chunks)
    # each chunk stays near chunk_size (boundary look-ahead adds at most ~100)
    assert all(len(c) <= search.CHUNK_SIZE + 100 for c in chunks)


# --- _search_vectors (Stage-1 date-filter fix: subset search must be exact) ---

def _tiny_index():
    """4-dim IndexFlatIP with 4 known unit vectors — no embedding model needed."""
    import faiss
    vecs = np.array([
        [1.0, 0.0, 0.0, 0.0],   # id 0 — best match for query [1,0,0,0]
        [0.9, 0.1, 0.0, 0.0],   # id 1 — second best
        [0.0, 1.0, 0.0, 0.0],   # id 2 — orthogonal
        [0.5, 0.5, 0.0, 0.0],   # id 3 — middling
    ], dtype=np.float32)
    index = faiss.IndexFlatIP(4)
    index.add(vecs)
    return index


def test_search_vectors_global_matches_faiss_order():
    index = _tiny_index()
    q = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    scores, ids = search._search_vectors(index, q, 4)
    assert list(ids) == [0, 1, 3, 2]


def test_search_vectors_subset_only_returns_allowed():
    # Restrict to ids {2, 3}: the globally-best ids 0/1 must NOT appear,
    # and the allowed ids must come back exactly scored (dot product) and ordered.
    index = _tiny_index()
    q = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    scores, ids = search._search_vectors(index, q, 4, allowed_ids=[2, 3])
    assert list(ids) == [3, 2]
    assert scores[0] == np.float32(0.5)  # dot([0.5,0.5,0,0], q)
    assert scores[1] == np.float32(0.0)


def test_search_vectors_subset_respects_k():
    index = _tiny_index()
    q = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    _, ids = search._search_vectors(index, q, 1, allowed_ids=[0, 1, 3])
    assert list(ids) == [0]


# --- _rerank_candidates (Stage-1: order by cross-encoder score, top_k cut) ---

class _StubReranker:
    """Scores each pair by a lookup on the chunk text — no model download."""
    def __init__(self, score_by_text):
        self.score_by_text = score_by_text

    def predict(self, pairs, show_progress_bar=False):
        return [self.score_by_text[text] for _query, text in pairs]


def test_rerank_orders_by_cross_encoder_score(monkeypatch):
    candidates = [
        ({"text": "low"}, 0.99),    # best dense score, worst rerank score
        ({"text": "high"}, 0.10),
        ({"text": "mid"}, 0.50),
    ]
    stub = _StubReranker({"low": -5.0, "high": 7.5, "mid": 1.0})
    monkeypatch.setattr(search, "_get_reranker", lambda: stub)

    ranked = search._rerank_candidates("q", candidates, top_k=2)

    assert [m["text"] for m, _ in ranked] == ["high", "mid"]  # top_k=2 cut
    assert ranked[0][1] == 7.5  # scores are the cross-encoder's, not cosine


def test_rerank_empty_candidates(monkeypatch):
    # Must short-circuit without touching the reranker at all.
    def _boom():
        raise AssertionError("reranker must not load for empty candidates")
    monkeypatch.setattr(search, "_get_reranker", _boom)
    assert search._rerank_candidates("q", [], top_k=5) == []


# --- _tokenize (Stage 2: BM25 tokenizer must keep short tickers) ---

def test_tokenize_keeps_short_tickers():
    # 1-2 char tickers survive — the exact failure mode BM25 exists to fix
    assert "gm" in search._tokenize("GM bonds widened")
    assert "x" in search._tokenize("U.S. Steel (X) downgraded")


def test_tokenize_dollar_ticker_normalizes():
    # "$ABR" and "ABR" must match each other in BM25
    assert search._tokenize("$ABR spreads") == ["abr", "spreads"]
    assert search._tokenize("ABR spreads") == ["abr", "spreads"]


def test_tokenize_lowercases_and_splits():
    assert search._tokenize("HY OAS at 320bps") == ["hy", "oas", "at", "320bps"]
    assert search._tokenize("") == []
    assert search._tokenize(None) == []


# --- _rrf_fuse (Stage 2: fusion math) ---

def test_rrf_fuse_math():
    fused = search._rrf_fuse([["a", "b"], ["b", "c"]], k=60)
    assert fused["a"] == 1 / 61
    assert fused["b"] == 1 / 62 + 1 / 61   # rank 2 in list 1, rank 1 in list 2
    assert fused["c"] == 1 / 62


def test_rrf_fuse_both_lists_beats_single():
    # An id ranked mid-pack in BOTH lists outscores one ranked top in only one
    fused = search._rrf_fuse([["solo", "both"], ["both"]])
    assert fused["both"] > fused["solo"]


# --- _bm25_top_ids (Stage 2: exact-token retrieval, restriction, zero-score cut) ---

def _bm25_for(texts):
    from rank_bm25 import BM25Okapi
    return BM25Okapi([search._tokenize(t) for t in texts])


def test_bm25_top_ids_exact_token():
    bm25 = _bm25_for(["ABR spreads widened", "oil rallied", "yen fell"])
    assert search._bm25_top_ids(bm25, "$ABR", pool=3) == [0]  # zero-score chunks excluded


def test_bm25_top_ids_respects_allowed_ids():
    bm25 = _bm25_for(["ABR one", "ABR two", "oil"])
    assert search._bm25_top_ids(bm25, "ABR", pool=3, allowed_ids=[1, 2]) == [1]


# --- _get_search_state (Stage 2: cache hit + mtime/size invalidation) ---

def test_search_state_cache_and_invalidation(tmp_path, monkeypatch):
    import faiss

    index_file = tmp_path / "index.faiss"
    meta_file = tmp_path / "meta.json"

    def _write(texts):
        vecs = np.eye(len(texts), 4, dtype=np.float32)  # arbitrary distinct vectors
        idx = faiss.IndexFlatIP(4)
        idx.add(vecs)
        faiss.write_index(idx, str(index_file))
        meta_file.write_text(json.dumps([{"text": t, "date": "2026-06-30"} for t in texts]),
                             encoding="utf-8")

    monkeypatch.setattr(search, "INDEX_FILE", index_file)
    monkeypatch.setattr(search, "METADATA_FILE", meta_file)
    monkeypatch.setattr(search, "_search_state", None)

    _write(["alpha chunk text", "beta chunk text"])
    s1 = search._get_search_state()
    assert len(s1["metadata"]) == 2 and s1["bm25"] is not None

    # Unchanged files -> same cached object (no reload)
    assert search._get_search_state() is s1

    # Rewrite with different content -> signature changes -> fresh state
    _write(["alpha chunk text", "beta chunk text", "gamma chunk text"])
    s2 = search._get_search_state()
    assert s2 is not s1
    assert len(s2["metadata"]) == 3
    # the BM25 corpus was rebuilt too
    assert search._bm25_top_ids(s2["bm25"], "gamma", pool=3) == [2]


# --- _extract_entities (Stage 3a: watchlist + $TICK + tracked funds) ---

def test_extract_entities_watchlist_ticker():
    assert "MSTR" in search._extract_entities("MSTR announced a capital framework")


def test_extract_entities_dollar_ticker_off_watchlist():
    # $-prefixed symbols tag even when not on the watchlist (e.g. 13D names)
    tags = search._extract_entities("Almonty Industries ($ALM) on the tungsten squeeze")
    assert "ALM" in tags


def test_extract_entities_case_sensitive_tickers():
    # lowercase "main" (the word) must NOT tag the MAIN ticker
    assert "MAIN" not in search._extract_entities("the main driver of spreads")
    assert "MAIN" in search._extract_entities("MAIN reported NII of $1.02")


def test_extract_entities_fund_alias():
    tags = search._extract_entities("Oaktree added a new distressed position")
    assert "Oaktree Capital Management" in tags


def test_extract_entities_generic_fund_word_skipped():
    # "Avenue"/"Canyon" alone are too generic to tag the funds
    assert search._extract_entities("Fifth Avenue real estate") == []
    tags = search._extract_entities("Avenue Capital Group added notes")
    assert "Avenue Capital Group" in tags


def test_extract_entities_empty():
    assert search._extract_entities("") == []
    assert search._extract_entities(None) == []


# --- _filter_ids (Stage 3a: combined date/range/entity restriction) ---

_META = [
    {"date": "2026-06-29", "entities": ["MSTR"]},
    {"date": "2026-06-30", "entities": ["ABR", "Oaktree Capital Management"]},
    {"date": "2026-07-01", "entities": []},
    {"date": "2026-07-02"},  # no entities key at all (pre-retag chunk)
]


def test_filter_ids_none_when_no_filters():
    assert search._filter_ids(_META) is None


def test_filter_ids_date_prefix():
    assert search._filter_ids(_META, date_filter="2026-06") == [0, 1]


def test_filter_ids_date_range_inclusive():
    assert search._filter_ids(_META, date_from="2026-06-30", date_to="2026-07-01") == [1, 2]


def test_filter_ids_entity_normalized():
    # "$abr" matches the "ABR" tag ($- and case-insensitive)
    assert search._filter_ids(_META, entity_filter="$abr") == [1]
    assert search._filter_ids(_META, entity_filter="oaktree capital management") == [1]


def test_filter_ids_combined_and_missing_entities_key():
    # entity + range combine with AND; chunks without an entities key never match
    assert search._filter_ids(_META, entity_filter="MSTR", date_from="2026-06-30") == []
    assert search._filter_ids(_META, entity_filter="MSTR", date_to="2026-06-29") == [0]
