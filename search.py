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
import os
import html as html_module
from html.parser import HTMLParser
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).parent
ARCHIVE_DIR = SCRIPT_DIR / "archive"
INDEX_FILE = ARCHIVE_DIR / "index.faiss"
METADATA_FILE = ARCHIVE_DIR / "chunk_metadata.json"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

CHUNK_SIZE = 800       # chars (~150-200 tokens) — larger for better context
CHUNK_OVERLAP = 150    # more overlap to avoid splitting key details across chunks


# ======================================================================
# HTML STRIPPING
# ======================================================================

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "head"):
            self._skip = True
        if tag in ("p", "br", "div", "tr", "h1", "h2", "h3", "h4", "li", "td"):
            self.result.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "head"):
            self._skip = False
        if tag in ("p", "tr", "table"):
            self.result.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.result.append(data)

    def get_text(self):
        text = html_module.unescape("".join(self.result))
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def _strip_html(text):
    if not text:
        return ""
    stripper = _HTMLStripper()
    try:
        stripper.feed(text)
        return stripper.get_text()
    except Exception:
        return re.sub(r'<[^>]+>', ' ', text)


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

def _get_model():
    """Load the sentence-transformer embedding model."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


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
        text = _strip_html(digest_file.read_text(encoding="utf-8"))
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

    # --- Octus articles ---
    octus_file = day_dir / "octus_articles.json"
    if octus_file.exists():
        try:
            articles = json.loads(octus_file.read_text(encoding="utf-8"))
            for j, a in enumerate(articles):
                title = a.get("title", "")
                text = a.get("text", "")
                company = a.get("company", "")
                url = a.get("url", "")

                full_text = f"{title}\n{company}\n\n{text}" if text else title
                for i, chunk in enumerate(_chunk_text(full_text)):
                    chunks.append((chunk, {
                        "chunk_id": f"{date_str}_octus_{j:02d}_{i:04d}",
                        "date": date_str,
                        "source_type": "octus",
                        "source_name": f"Octus: {company or title[:40]}",
                        "source_file": str(octus_file.relative_to(SCRIPT_DIR)),
                        "text": chunk,
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

    # --- Octus deals ---
    deals_file = day_dir / "octus_deals.json"
    if deals_file.exists():
        try:
            deals = json.loads(deals_file.read_text(encoding="utf-8"))
            if deals:
                # Index all deals as a single block (they're structured data, not long text)
                deal_lines = []
                for d in deals:
                    parts = [d.get("entity", "")]
                    for k in ("coupon", "yield", "price_talk", "rating", "bookrunners", "size"):
                        v = d.get(k, "")
                        if v and v != "-":
                            parts.append(f"{k}: {v}")
                    deal_lines.append(" | ".join(parts))
                deal_text = "Primary Market Deals:\n" + "\n".join(deal_lines)

                chunks.append((deal_text, {
                    "chunk_id": f"{date_str}_deals_0000",
                    "date": date_str,
                    "source_type": "deals",
                    "source_name": "Octus Primary Deal Tracker",
                    "source_file": str(deals_file.relative_to(SCRIPT_DIR)),
                    "text": deal_text,
                    "url": "",
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
            model = _get_model()
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

def search(query, top_k=10, date_filter=None):
    """
    Hybrid search: vector similarity + keyword boost.

    Args:
        query: The search query string.
        top_k: Number of results to return.
        date_filter: Optional date prefix filter (e.g. "2026-04" or "2026-04-04").

    Returns:
        List of (metadata_dict, similarity_score) tuples, sorted by combined score.
    """
    import faiss

    index, metadata = _load_index()
    if index.ntotal == 0:
        print("Search index is empty. Run indexing first.")
        return []

    model = _get_model()

    # Embed query
    query_vec = model.encode([query], normalize_embeddings=True)
    query_vec = np.array(query_vec, dtype=np.float32)

    # Retrieve more candidates than needed for hybrid re-ranking
    search_k = min(top_k * 10, index.ntotal)

    scores, indices = index.search(query_vec, search_k)

    # Extract keywords from query for boosting (words 3+ chars, lowered)
    query_words = [w.lower() for w in re.findall(r'\b\w{3,}\b', query)]

    candidates = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(metadata):
            continue

        meta = metadata[idx]

        # Apply date filter
        if date_filter and not meta.get("date", "").startswith(date_filter):
            continue

        # Keyword boost: add 0.05 per query keyword found in the chunk text
        text_lower = meta.get("text", "").lower()
        keyword_hits = sum(1 for w in query_words if w in text_lower)
        boost = keyword_hits * 0.05

        combined_score = float(score) + boost
        candidates.append((meta, combined_score))

    # Sort by combined score descending
    candidates.sort(key=lambda x: x[1], reverse=True)

    return candidates[:top_k]


# ======================================================================
# CLI
# ======================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python search.py "your query here"')
        print('  python search.py "query" --date 2026-04')
        print("  python search.py --rebuild")
        print("  python search.py --index 2026-04-04")
        sys.exit(1)

    if sys.argv[1] == "--rebuild":
        rebuild_index()

    elif sys.argv[1] == "--index" and len(sys.argv) >= 3:
        index_daily_content(sys.argv[2])

    else:
        query = sys.argv[1]
        date_filter = None
        if "--date" in sys.argv:
            di = sys.argv.index("--date")
            if di + 1 < len(sys.argv):
                date_filter = sys.argv[di + 1]

        results = search(query, top_k=10, date_filter=date_filter)

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
                print(f"  ---")
                preview = meta["text"][:300].replace("\n", " ")
                print(f"  {preview.encode('ascii', 'replace').decode()}...")
