"""Phase 3.4 — pin behavior of search._chunk_text (chunking math).
Stage 1 (memory refactor) — pin _search_vectors subset search + rerank ordering."""

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
