"""Phase 3.4 — pin behavior of search._chunk_text (chunking math)."""

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
