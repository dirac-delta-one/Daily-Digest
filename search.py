#!/usr/bin/env python3
"""
Vector Search over the Daily Digest Archive

Uses sentence-transformers for local embeddings and FAISS for similarity search.
Chunks all archived content (PDFs, Substack, filings, emails, news, digests)
and builds an incrementally-updated vector index.

Usage:
    python search.py "what did Grant's say about TIPS?"
    python search.py "Cliffwater NAV" --date 2026-04
    python search.py --rebuild
"""

import json
import re
import sys
from pathlib import Path

import numpy as np

from html_utils import strip_html

SCRIPT_DIR = Path(__file__).parent
ARCHIVE_DIR = SCRIPT_DIR / "archive"
INDEX_FILE = ARCHIVE_DIR / "index.faiss"
METADATA_FILE = ARCHIVE_DIR / "chunk_metadata.json"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Stage-1 reranker (MEMORY_REFACTOR_SPEC): cross-encoder that re-scores
# (query, chunk) pairs from the dense candidate pool. ~90MB one-time download,
# CPU-fine. Param-gated via search(rerank=True) — the reply bot opts in.
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

CHUNK_SIZE = 800       # chars (~150-200 tokens) — larger for better context
CHUNK_OVERLAP = 150    # more overlap to avoid splitting key details across chunks


# ======================================================================
# CHUNKING
# ======================================================================

def _chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks."""
    if not text or len(text.strip()) < 50:
        return []

    text = text.strip()
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size

        # Try to break at a paragraph or sentence boundary
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind("\n\n", start + chunk_size // 2, end + 100)
            if para_break > start:
                end = para_break
            else:
                # Look for sentence break
                sent_break = text.rfind(". ", start + chunk_size // 2, end + 50)
                if sent_break > start:
                    end = sent_break + 1

        chunk = text[start:end].strip()
        if len(chunk) >= 50:  # skip tiny chunks
            chunks.append(chunk)

        start = max(start + 1, end - overlap)  # ensure forward progress

    return chunks


def _clean_pdf_text(text):
    """Clean up PDF extraction artifacts for better indexing."""
    # Rejoin hyphenated line breaks: "subscrip-\ntion" → "subscription"
    text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
    # Rejoin words split across lines (lowercase letter, newline, lowercase letter)
    text = re.sub(r'([a-z])\s*\n\s*([a-z])', r'\1 \2', text)
    # Collapse multiple spaces
    text = re.sub(r'[ \t]+', ' ', text)
    # Collapse multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Fix common OCR/column artifacts
    text = text.replace('fi ', 'fi').replace('fl ', 'fl')
    text = text.replace(' .', '.').replace(' ,', ',')
    # Fix spaces inserted mid-word by column-layout PDFs (e.g. "m anagement" → "management")
    # Pattern: lowercase letter, space, lowercase letter(s) that form a word continuation
    text = re.sub(r'(\w) (\w{1,3}) (\w)', lambda m: m.group(0) if len(m.group(2)) > 2 else m.group(1) + m.group(2) + ' ' + m.group(3), text)
    # Simpler: rejoin single space between single lowercase chars: "s o l d" → "sold"
    text = re.sub(r'\b(\w) (\w) (\w) (\w)\b', r'\1\2\3\4', text)
    text = re.sub(r'\b(\w) (\w) (\w)\b', r'\1\2\3', text)
    return text.strip()


def _extract_pdf_text(pdf_path):
    """Extract text from a PDF file with cleanup for better RAG indexing."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        print(f"    PyPDF2 not installed — cannot index {pdf_path}")
        return ""

    try:
        reader = PdfReader(str(pdf_path))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                cleaned = _clean_pdf_text(text)
                pages.append(f"[PAGE {i+1}]\n{cleaned}")
        return "\n\n".join(pages)
    except Exception as e:
        print(f"    PDF extraction failed for {pdf_path}: {e}")
        return ""


# ======================================================================
# INDEXING
# ======================================================================

_model = None
_reranker = None


def _get_model():
    """Load (once) and return the sentence-transformer embedding model.

    Module-level singleton so the long-running reply_monitor loads the model
    a single time per process instead of on every search() call (Phase 2.4).
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def _get_reranker():
    """Load (once) and return the cross-encoder reranker (same singleton pattern)."""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(RERANKER_MODEL_NAME)
    return _reranker


def _load_index():
    """Load existing FAISS index and metadata."""
    import faiss

    metadata = []
    if METADATA_FILE.exists():
        try:
            metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            metadata = []

    if INDEX_FILE.exists() and metadata:
        try:
            index = faiss.read_index(str(INDEX_FILE))
            return index, metadata
        except Exception:
            pass

    # Create new empty index
    index = faiss.IndexFlatIP(EMBEDDING_DIM)  # inner product (cosine after normalization)
    return index, []


def _tokenize(text):
    """Lowercased alphanumeric tokens for BM25 (Stage 2).

    Deliberately keeps 1-2 char tokens — dropping short tickers (GM, X) is the
    exact failure mode BM25 exists to fix. A leading '$' is not a token char,
    so "$ABR" and "ABR" both normalize to "abr" and match each other.
    """
    return re.findall(r'[a-z0-9]+', (text or "").lower())


# ======================================================================
# ENTITY TAGGING (Stage 3a — metadata-only, no re-embedding)
# ======================================================================

# Fund first-words too generic to use as standalone aliases ("Avenue", "Canyon"
# match street addresses / geography far more often than the fund).
_GENERIC_FUND_WORDS = {"avenue", "canyon"}

_entity_lexicon_cache = None


def _entity_lexicon():
    """(watchlist tickers, {alias_lower: canonical fund name}) — built once.

    Lazy import so search.py stays importable standalone; coverage is
    deliberately just the SEC watchlist + tracked funds + $TICK patterns
    (full company NER is deferred — see MEMORY_REFACTOR_SPEC Stage 3a).
    """
    global _entity_lexicon_cache
    if _entity_lexicon_cache is None:
        from sec_filings import WATCHLIST
        from fund_tracking import TRACKED_FUNDS
        aliases = {}
        for _cik, name in TRACKED_FUNDS:
            aliases[name.lower()] = name
            first = name.split()[0]
            if first.lower() not in _GENERIC_FUND_WORDS:
                aliases[first.lower()] = name
        _entity_lexicon_cache = (set(WATCHLIST), aliases)
    return _entity_lexicon_cache


def _extract_entities(text):
    """Entity tags for one chunk: watchlist tickers, $TICK mentions, fund names.

    Tickers match case-sensitively on word boundaries (lowercase "main" must not
    tag MAIN; all-caps filing headers can still false-positive — accepted noise).
    $-prefixed symbols are tagged even off-watchlist ($ALM, $AGI from 13D).
    Fund aliases match case-insensitively. Returns a sorted, deduped list.
    """
    if not text:
        return []
    watchlist, fund_aliases = _entity_lexicon()

    tags = set()
    # Any $TICK-style mention (strong ticker signal, watchlist or not)
    for sym in re.findall(r'\$([A-Za-z]{1,5})\b', text):
        tags.add(sym.upper())
    # Watchlist tickers as bare uppercase words
    for ticker in watchlist:
        if re.search(rf'\b{re.escape(ticker)}\b', text):
            tags.add(ticker)
    # Tracked-fund names / distinctive aliases
    lowered = text.lower()
    for alias, canonical in fund_aliases.items():
        if re.search(rf'\b{re.escape(alias)}\b', lowered):
            tags.add(canonical)

    return sorted(tags)


def _entity_key(s):
    """Normalize an entity for matching: '$ABR' / 'abr' / 'ABR' all compare equal."""
    return (s or "").lstrip("$").strip().lower()


def _filter_ids(metadata, date_filter=None, date_from=None, date_to=None,
                entity_filter=None):
    """Chunk ids passing all supplied filters (Stage 1 date prefix + Stage 3a
    range/entity). Returns None when no filter is active (= search everything)."""
    if not (date_filter or date_from or date_to or entity_filter):
        return None

    ent = _entity_key(entity_filter) if entity_filter else None
    allowed = []
    for i, m in enumerate(metadata):
        d = m.get("date", "")
        if date_filter and not d.startswith(date_filter):
            continue
        if date_from and d < date_from:
            continue
        if date_to and d > date_to:
            continue
        if ent and ent not in (_entity_key(t) for t in m.get("entities") or []):
            continue
        allowed.append(i)
    return allowed


def _rrf_fuse(rankings, k=60):
    """Reciprocal Rank Fusion: {id: sum of 1/(k + rank)} across rankings (Stage 2).

    Standard RRF with the conventional k=60 — ids ranked well by BOTH the dense
    and lexical lists float to the top without needing score normalization.
    """
    scores = {}
    for ranking in rankings:
        for rank, id_ in enumerate(ranking, 1):
            scores[id_] = scores.get(id_, 0.0) + 1.0 / (k + rank)
    return scores


def _bm25_top_ids(bm25, query, pool, allowed_ids=None):
    """Best-first chunk ids by BM25 score (score > 0 only), optionally restricted."""
    scores = bm25.get_scores(_tokenize(query))
    ids = allowed_ids if allowed_ids is not None else range(len(scores))
    scored = [(i, scores[i]) for i in ids if scores[i] > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [i for i, _ in scored[:pool]]


# In-process search-state cache (Stage 2): search() previously re-read the FAISS
# index + full metadata JSON from disk on EVERY call — fine at 629 chunks, multi-
# second at archive scale. One signature-checked cache covers the index, metadata,
# and the BM25 corpus (which needs the same staleness logic), so the long-running
# reply monitor picks up the day the morning digest appends without restarting.
_search_state = None


def _file_sig(path):
    """(mtime_ns, size) staleness signature for a file, or None if missing."""
    try:
        s = path.stat()
        return (s.st_mtime_ns, s.st_size)
    except OSError:
        return None


def _get_search_state():
    """Cached (index, metadata, bm25) for search(); reloads only when the
    on-disk index/metadata files change."""
    global _search_state
    key = (_file_sig(INDEX_FILE), _file_sig(METADATA_FILE))
    if _search_state is not None and _search_state["key"] == key:
        return _search_state

    index, metadata = _load_index()
    bm25 = None
    if metadata:
        from rank_bm25 import BM25Okapi
        bm25 = BM25Okapi([_tokenize(m.get("text", "")) for m in metadata])

    _search_state = {"key": key, "index": index, "metadata": metadata, "bm25": bm25}
    return _search_state


def _save_index(index, metadata):
    """Save FAISS index and metadata to disk."""
    import faiss
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_FILE))
    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")


def _get_indexed_dates(metadata):
    """Return set of dates already indexed."""
    return set(m.get("date", "") for m in metadata)


def _chunks_for_date(date_str):
    """Extract all chunks from a single archived date."""
    day_dir = ARCHIVE_DIR / date_str
    if not day_dir.exists():
        return []

    chunks = []  # list of (text, metadata_dict)

    # --- Digest HTML ---
    digest_file = day_dir / "digest.html"
    if digest_file.exists():
        text = strip_html(digest_file.read_text(encoding="utf-8"))
        for i, chunk in enumerate(_chunk_text(text)):
            chunks.append((chunk, {
                "chunk_id": f"{date_str}_digest_{i:04d}",
                "date": date_str,
                "source_type": "digest",
                "source_name": f"Daily Digest {date_str}",
                "source_file": str(digest_file.relative_to(SCRIPT_DIR)),
                "text": chunk,
                "url": "",
            }))

    # --- PDFs ---
    pdf_dir = day_dir / "pdfs"
    if pdf_dir.exists():
        for pdf_file in pdf_dir.glob("*.pdf"):
            pdf_text = _extract_pdf_text(pdf_file)
            if not pdf_text:
                continue

            # Try to extract source name from filename
            source_name = pdf_file.stem.replace("_", " ").title()

            # Find page numbers within chunks
            for i, chunk in enumerate(_chunk_text(pdf_text)):
                # Try to figure out which page this chunk is from
                page_num = None
                page_match = re.search(r'\[PAGE (\d+)\]', chunk)
                if page_match:
                    page_num = int(page_match.group(1))

                chunks.append((chunk, {
                    "chunk_id": f"{date_str}_pdf_{pdf_file.stem}_{i:04d}",
                    "date": date_str,
                    "source_type": "pdf",
                    "source_name": source_name,
                    "source_file": str(pdf_file.relative_to(SCRIPT_DIR)),
                    "page_number": page_num,
                    "text": chunk,
                    "url": "",
                }))

    # --- Substack articles ---
    substacks_file = day_dir / "substacks.json"
    if substacks_file.exists():
        try:
            articles = json.loads(substacks_file.read_text(encoding="utf-8"))
            for art in articles:
                text = art.get("text", "")
                title = art.get("title", "")
                author = art.get("author", "")
                url = art.get("url", "")
                source_name = author or art.get("publication", "Substack")

                if title:
                    text = f"{title}\n\n{text}"

                for i, chunk in enumerate(_chunk_text(text)):
                    chunks.append((chunk, {
                        "chunk_id": f"{date_str}_substack_{source_name.replace(' ', '_')}_{i:04d}",
                        "date": date_str,
                        "source_type": "substack",
                        "source_name": source_name,
                        "source_file": str(substacks_file.relative_to(SCRIPT_DIR)),
                        "text": chunk,
                        "url": url,
                    }))
        except Exception:
            pass

    # --- SEC filings ---
    filings_file = day_dir / "filings.json"
    if filings_file.exists():
        try:
            filings = json.loads(filings_file.read_text(encoding="utf-8"))
            for f in filings:
                content = f.get("content", "")
                if not content or content.startswith("["):
                    continue
                ticker = f.get("ticker", "")
                company = f.get("company", "")
                form_type = f.get("form_type", "")
                source_name = f"{ticker} {form_type}" if ticker else form_type
                url = f.get("url", "")

                header = f"{company} ({ticker}) — {form_type}\n\n"
                text = header + content

                for i, chunk in enumerate(_chunk_text(text)):
                    chunks.append((chunk, {
                        "chunk_id": f"{date_str}_filing_{ticker}_{form_type}_{i:04d}",
                        "date": date_str,
                        "source_type": "filing",
                        "source_name": source_name,
                        "source_file": str(filings_file.relative_to(SCRIPT_DIR)),
                        "text": chunk,
                        "url": url,
                    }))
        except Exception:
            pass

    # --- Emails ---
    emails_file = day_dir / "emails.json"
    if emails_file.exists():
        try:
            emails = json.loads(emails_file.read_text(encoding="utf-8"))
            for j, e in enumerate(emails):
                sender = e.get("from", "")
                subject = e.get("subject", "")
                # Use full body if available, fall back to snippet
                body = e.get("body", "") or e.get("snippet", "")
                source_name = sender.split("<")[0].strip() or sender

                header = f"From: {sender}\nSubject: {subject}\n\n"
                text = header + body

                if len(text.strip()) < 50:
                    continue

                # Chunk emails with body text (can be long for forwarded research)
                for i, chunk in enumerate(_chunk_text(text)):
                    chunks.append((chunk, {
                        "chunk_id": f"{date_str}_email_{j:02d}_{i:04d}",
                        "date": date_str,
                        "source_type": "email",
                        "source_name": source_name,
                        "source_file": str(emails_file.relative_to(SCRIPT_DIR)),
                        "text": chunk,
                        "url": "",
                    }))
        except Exception:
            pass

    # --- News articles ---
    news_file = day_dir / "news.json"
    if news_file.exists():
        try:
            articles = json.loads(news_file.read_text(encoding="utf-8"))
            for j, a in enumerate(articles):
                title = a.get("title", "")
                summary = a.get("summary", "")
                source = a.get("source", "")
                url = a.get("url", "")
                text = f"{title}\n{summary}" if summary else title

                if len(text.strip()) >= 30:
                    chunks.append((text, {
                        "chunk_id": f"{date_str}_news_{j:04d}",
                        "date": date_str,
                        "source_type": "news",
                        "source_name": f"{source}: {title[:50]}",
                        "source_file": str(news_file.relative_to(SCRIPT_DIR)),
                        "text": text,
                        "url": url,
                    }))
        except Exception:
            pass

    # --- Rating actions ---
    ratings_file = day_dir / "rating_actions.json"
    if ratings_file.exists():
        try:
            actions = json.loads(ratings_file.read_text(encoding="utf-8"))
            for j, a in enumerate(actions):
                title = a.get("title", "")
                desc = a.get("description", "")
                source = a.get("source", "")
                url = a.get("url", "")
                text = f"{title}\n{desc}" if desc else title

                if len(text.strip()) >= 30:
                    chunks.append((text, {
                        "chunk_id": f"{date_str}_rating_{j:04d}",
                        "date": date_str,
                        "source_type": "rating",
                        "source_name": f"{source}: {title[:50]}",
                        "source_file": str(ratings_file.relative_to(SCRIPT_DIR)),
                        "text": text,
                        "url": url,
                    }))
        except Exception:
            pass

    # --- PACER entries ---
    pacer_file = day_dir / "pacer_entries.json"
    if pacer_file.exists():
        try:
            entries = json.loads(pacer_file.read_text(encoding="utf-8"))
            for j, e in enumerate(entries):
                company = e.get("company", "")
                title = e.get("title", "")
                desc = e.get("description", "")
                link = e.get("link", "")
                text = f"{company}: {title}\n{desc}" if desc else f"{company}: {title}"

                if len(text.strip()) >= 30:
                    chunks.append((text, {
                        "chunk_id": f"{date_str}_pacer_{j:04d}",
                        "date": date_str,
                        "source_type": "pacer",
                        "source_name": f"PACER: {company}",
                        "source_file": str(pacer_file.relative_to(SCRIPT_DIR)),
                        "text": text,
                        "url": link,
                    }))
        except Exception:
            pass

    # --- 13D WILTW summary ---
    wiltw_file = day_dir / "wiltw.json"
    if wiltw_file.exists():
        try:
            wiltw = json.loads(wiltw_file.read_text(encoding="utf-8"))
            summary = wiltw.get("summary", "")
            title = wiltw.get("title", "13D WILTW")
            url = wiltw.get("url", "")

            if summary:
                for i, chunk in enumerate(_chunk_text(summary)):
                    chunks.append((chunk, {
                        "chunk_id": f"{date_str}_wiltw_{i:04d}",
                        "date": date_str,
                        "source_type": "wiltw",
                        "source_name": f"13D Research: {title}",
                        "source_file": str(wiltw_file.relative_to(SCRIPT_DIR)),
                        "text": chunk,
                        "url": url,
                    }))
        except Exception:
            pass

    # --- 13F fund results ---
    funds_file = day_dir / "fund_results.json"
    if funds_file.exists():
        try:
            results = json.loads(funds_file.read_text(encoding="utf-8"))
            for j, r in enumerate(results):
                fund = r.get("fund", "")
                filing_date = r.get("filing_date", "")
                changes = r.get("changes", {})

                lines = [f"{fund} 13F filing ({filing_date})"]
                for category in ("new", "exited", "increased", "decreased"):
                    items = changes.get(category, [])
                    if items:
                        lines.append(f"  {category.upper()}:")
                        for h in items[:5]:
                            lines.append(f"    {h.get('name', '')}: {h.get('shares', 0):,} shares, ${h.get('value', 0):,.0f}")

                text = "\n".join(lines)
                for i, chunk in enumerate(_chunk_text(text)):
                    chunks.append((chunk, {
                        "chunk_id": f"{date_str}_13f_{j:02d}_{i:04d}",
                        "date": date_str,
                        "source_type": "13f",
                        "source_name": f"13F: {fund}",
                        "source_file": str(funds_file.relative_to(SCRIPT_DIR)),
                        "text": chunk,
                        "url": "",
                    }))
        except Exception:
            pass

    # Entity tags (Stage 3a) — one place covers both index_daily_content and
    # rebuild_index; existing metadata is backfilled via `python search.py --retag`.
    for text, meta in chunks:
        meta["entities"] = _extract_entities(text)

    return chunks


def index_daily_content(date_str):
    """Index all content from a given date. Returns number of chunks added."""
    import faiss

    chunks = _chunks_for_date(date_str)
    if not chunks:
        print(f"  No content to index for {date_str}.")
        return 0

    print(f"  Indexing {len(chunks)} chunks from {date_str}...")

    model = _get_model()
    index, metadata = _load_index()

    # If this date is already indexed, remove old entries and re-index
    existing_dates = _get_indexed_dates(metadata)
    if date_str in existing_dates:
        print(f"  {date_str} already indexed — removing old entries and re-indexing...")
        # Must rebuild the full index since FAISS IndexFlatIP doesn't support removal
        # Filter out old metadata for this date, then rebuild
        old_metadata = [m for m in metadata if m.get("date") != date_str]
        if old_metadata:
            # Rebuild index from remaining metadata embeddings
            old_texts = [m["text"] for m in old_metadata]
            old_embeddings = model.encode(old_texts, show_progress_bar=False, normalize_embeddings=True)
            old_embeddings = np.array(old_embeddings, dtype=np.float32)
            index = faiss.IndexFlatIP(EMBEDDING_DIM)
            index.add(old_embeddings)
            metadata = old_metadata
        else:
            index = faiss.IndexFlatIP(EMBEDDING_DIM)
            metadata = []

    # Embed all chunk texts
    texts = [c[0] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype=np.float32)

    # Add to index
    index.add(embeddings)

    # Add metadata
    for _, meta in chunks:
        metadata.append(meta)

    _save_index(index, metadata)

    print(f"  Indexed {len(chunks)} chunks. Total index: {index.ntotal} vectors.")
    return len(chunks)


def retag_metadata():
    """Backfill entity tags onto existing chunk metadata (Stage 3a).

    Rewrites chunk_metadata.json ONLY — the FAISS vectors are untouched, so this
    is safe to run anytime and takes seconds. New chunks are tagged at index
    time; this exists for chunks indexed before tagging landed (or after a
    lexicon change — new watchlist ticker, new tracked fund).
    """
    _index, metadata = _load_index()
    if not metadata:
        print("No metadata to retag.")
        return 0

    tagged = 0
    for m in metadata:
        m["entities"] = _extract_entities(m.get("text", ""))
        if m["entities"]:
            tagged += 1

    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    print(f"Retagged {len(metadata)} chunks ({tagged} carry at least one entity tag).")
    return len(metadata)


def rebuild_index():
    """Re-index everything in the archive from scratch."""
    import faiss

    print("Rebuilding entire search index...")

    # Delete existing
    if INDEX_FILE.exists():
        INDEX_FILE.unlink()
    if METADATA_FILE.exists():
        METADATA_FILE.unlink()

    dates = []
    if ARCHIVE_DIR.exists():
        for d in sorted(ARCHIVE_DIR.iterdir()):
            if d.is_dir() and len(d.name) == 10 and d.name[4] == "-":
                dates.append(d.name)

    if not dates:
        print("No archived dates found.")
        return 0

    model = _get_model()
    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    metadata = []

    total = 0
    for date_str in dates:
        chunks = _chunks_for_date(date_str)
        if not chunks:
            continue

        texts = [c[0] for c in chunks]
        embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        embeddings = np.array(embeddings, dtype=np.float32)

        index.add(embeddings)
        for _, meta in chunks:
            metadata.append(meta)

        total += len(chunks)
        print(f"  {date_str}: {len(chunks)} chunks")

    _save_index(index, metadata)
    print(f"Rebuild complete: {total} chunks from {len(dates)} days.")
    return total


# ======================================================================
# SEARCH
# ======================================================================

def _search_vectors(index, query_vec, k, allowed_ids=None):
    """FAISS top-k search, optionally restricted to a subset of vector ids.

    The subset path is the Stage-1 date-filter fix: filtering *after* a global
    top-k retrieval (the old approach) surfaces few/no matches once the index
    spans many dates — the target day's chunks get crowded out of the global
    candidate pool. Restricted searches instead brute-force score exactly the
    allowed vectors (IndexFlat vectors are reconstructable; one day is only
    ~hundreds of chunks), which is exact and cheap at this scale.

    Returns (scores, ids) as parallel 1-D arrays, best-first.
    """
    if allowed_ids is None:
        k = min(k, index.ntotal)
        scores, indices = index.search(query_vec, k)
        return scores[0], indices[0]

    vecs = np.vstack([index.reconstruct(int(i)) for i in allowed_ids])
    sims = vecs @ query_vec[0]
    order = np.argsort(-sims)[:k]
    return sims[order], np.array([allowed_ids[j] for j in order])


def _rerank_candidates(query, candidates, top_k):
    """Re-score (query, chunk-text) pairs with the cross-encoder (Stage 1).

    Returns the top_k candidates by cross-encoder score. NOTE: the returned
    scores are cross-encoder logits, not cosine similarities — don't compare
    them against non-reranked scores.
    """
    if not candidates:
        return []

    reranker = _get_reranker()
    pairs = [(query, meta.get("text", "")) for meta, _ in candidates]
    scores = reranker.predict(pairs, show_progress_bar=False)

    ranked = [(meta, float(s)) for (meta, _), s in zip(candidates, scores)]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


def search(query, top_k=10, date_filter=None, rerank=False, hybrid=False,
           entity_filter=None, date_from=None, date_to=None):
    """
    Search the archive: dense retrieval (optionally fused with BM25), then
    keyword boost or cross-encoder rerank.

    Args:
        query: The search query string.
        top_k: Number of results to return.
        date_filter: Optional date prefix filter (e.g. "2026-04" or "2026-04-04").
            Applied BEFORE retrieval (restricted vector search), so day-filtered
            queries keep working as the archive grows.
        rerank: If True, re-score the candidate pool with the cross-encoder and
            rank by that (scores in the result are then logits, not cosine).
            If False (default), rank by the retrieval scoring below.
        hybrid: If True, fuse the dense ranking with a BM25 lexical ranking via
            Reciprocal Rank Fusion (scores are then RRF sums, not cosine) —
            fixes exact-token retrieval (tickers, CUSIPs) that embeddings miss.
            If False (default), keep the original cosine + keyword-boost scoring.
        entity_filter: Optional entity tag (Stage 3a) — restrict to chunks tagged
            with this ticker/fund ("$ABR", "ABR", "Oaktree Capital Management";
            case- and $-insensitive). Coverage = watchlist + $TICK + tracked funds.
        date_from / date_to: Optional inclusive ISO date range (Stage 3a), e.g.
            date_from="2026-06-01", date_to="2026-06-30". Combines with the others.

    Returns:
        List of (metadata_dict, score) tuples, best-first.
    """

    state = _get_search_state()
    index, metadata, bm25 = state["index"], state["metadata"], state["bm25"]
    if index.ntotal == 0:
        print("Search index is empty. Run indexing first.")
        return []

    model = _get_model()

    # Embed query
    query_vec = model.encode([query], normalize_embeddings=True)
    query_vec = np.array(query_vec, dtype=np.float32)

    # Filters (Stage 1 + 3a): restrict the searched vectors up front instead
    # of discarding non-matching chunks from a global top-k afterwards.
    allowed_ids = _filter_ids(metadata, date_filter=date_filter,
                              date_from=date_from, date_to=date_to,
                              entity_filter=entity_filter)
    if allowed_ids is not None and not allowed_ids:
        return []

    # Retrieve more candidates than needed for fuse/boost/rerank re-ordering
    pool = top_k * 10
    scores, indices = _search_vectors(index, query_vec, pool, allowed_ids)

    if hybrid and bm25 is not None:
        # Stage 2: dense + BM25 -> RRF fuse -> candidate pool
        dense_ids = [int(i) for i in indices if 0 <= i < len(metadata)]
        lexical_ids = _bm25_top_ids(bm25, query, pool, allowed_ids)
        fused = _rrf_fuse([dense_ids, lexical_ids])
        ranked_ids = sorted(fused, key=fused.get, reverse=True)[:pool]
        candidates = [(metadata[i], fused[i]) for i in ranked_ids]
    else:
        candidates = [(metadata[idx], float(score))
                      for score, idx in zip(scores, indices)
                      if 0 <= idx < len(metadata)]

    if rerank:
        return _rerank_candidates(query, candidates, top_k)

    if hybrid and bm25 is not None:
        return candidates[:top_k]

    # Legacy scoring: keyword boost (words 3+ chars) over the cosine score
    query_words = [w.lower() for w in re.findall(r'\b\w{3,}\b', query)]

    boosted = []
    for meta, score in candidates:
        text_lower = meta.get("text", "").lower()
        keyword_hits = sum(1 for w in query_words if w in text_lower)
        boosted.append((meta, score + keyword_hits * 0.05))

    # Sort by combined score descending
    boosted.sort(key=lambda x: x[1], reverse=True)

    return boosted[:top_k]


# ======================================================================
# CLI
# ======================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python search.py "your query here"')
        print('  python search.py "query" --date 2026-04')
        print('  python search.py "query" --entity ABR')
        print('  python search.py "query" --from 2026-06-01 --to 2026-06-30')
        print('  python search.py "query" --rerank')
        print('  python search.py "query" --hybrid')
        print("  python search.py --rebuild")
        print("  python search.py --index 2026-04-04")
        print("  python search.py --retag   (backfill entity tags; metadata only)")
        sys.exit(1)

    if sys.argv[1] == "--rebuild":
        rebuild_index()

    elif sys.argv[1] == "--retag":
        retag_metadata()

    elif sys.argv[1] == "--index" and len(sys.argv) >= 3:
        index_daily_content(sys.argv[2])

    else:
        query = sys.argv[1]

        def _flag_value(flag):
            if flag in sys.argv:
                fi = sys.argv.index(flag)
                if fi + 1 < len(sys.argv):
                    return sys.argv[fi + 1]
            return None

        results = search(query, top_k=10,
                         date_filter=_flag_value("--date"),
                         entity_filter=_flag_value("--entity"),
                         date_from=_flag_value("--from"),
                         date_to=_flag_value("--to"),
                         rerank="--rerank" in sys.argv,
                         hybrid="--hybrid" in sys.argv)

        if not results:
            print("No results found.")
        else:
            for i, (meta, score) in enumerate(results, 1):
                print(f"\n{'='*60}")
                print(f"  #{i} (score: {score:.3f})")
                print(f"  Date: {meta['date']} | Type: {meta['source_type']}")
                print(f"  Source: {meta['source_name']}")
                if meta.get("url"):
                    print(f"  URL: {meta['url']}")
                if meta.get("page_number"):
                    print(f"  Page: {meta['page_number']}")
                print("  ---")
                preview = meta["text"][:300].replace("\n", " ")
                print(f"  {preview.encode('ascii', 'replace').decode()}...")
