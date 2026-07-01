# Memory / Retrieval Refactor — Spec

> Staged plan to improve how the system remembers and answers questions. Companion to
> `HANDOFF.md` (overall project state) and `WORKLOG.md` (running log). Scoped 2026-07-01;
> **nothing built yet.** Update the Status table as stages land.

## Status

| Stage | What | State |
|---|---|---|
| 0 | Eval harness (golden Q→source set) | ⬜ not started |
| 1 | Cross-encoder reranker | ⬜ not started |
| 2 | Hybrid search (BM25 + dense, RRF) | ⬜ not started |
| 3 | Index upgrade: entity/date metadata + stronger embeddings (reindex) | ⬜ not started |
| 4 | Smarter retrieval in the reply bot (query understanding + MMR/dedup) | ⬜ not started |
| 5 | Converge System A ↔ B (story-timeline memory wired into the bot) | ⬜ not started |
| — | Optional: substrate swap (LanceDB / sqlite-vec) | ⬜ conditional |

---

## 1. Objective

Make the system (a) **retrieve better** for the email-reply Q&A bot and (b) **piece information
together across time** ("how did story X evolve", "everything about $ABR across sources") — which it
cannot do today. Also TL;DR-documents how the two "memory" systems actually work, since they are
easily confused.

## 2. The two "memory" systems (they don't talk to each other)

### System A — Cross-digest memory (`memory.py` → `memory.json`)
A model-maintained running summary of evolving storylines ("what's the ongoing narrative").
- **Loop:** after the digest sends, `digest.main` calls [`update_memory(final_html)`](memory.py) →
  loads current `memory.json`, sends it + today's digest to the model (**Sonnet**, since the
  2026-07-01 cost refactor), and **rewrites the whole memory** into
  `{last_updated, active_stories[], resolved_stories[]}` (each story =
  `{topic, first_seen, last_updated, summary, key_data_points[], sources[]}`). Next morning
  [`get_memory_context()`](memory.py) serializes the active stories into the digest prompt for
  continuity ("tracking since June 12: now X"). ~18 active stories currently.
- **Weaknesses:** rewritten **wholesale daily** (expensive-ish, lossy — the model silently
  drops/reshapes stories); **flat list**, no links, no real timeline (only first/last seen, not a
  dated update history); **only feeds the next digest** — not searchable, the reply bot never uses it.

### System B — RAG archive + Q&A bot (`archive.py` + `search.py` + `reply_monitor.py`)
The searchable long-term record and the reply bot over it. **This is what answers questions.**
- **Loop:** after each digest, [`archive_daily_content`](archive.py) dumps raw JSON per source + PDFs
  to `archive/<date>/`; [`index_daily_content`](search.py) chunks everything
  ([`_chunk_text`](search.py): 800-char windows, 150 overlap), embeds with `all-MiniLM-L6-v2`
  (384-dim, local/free), and adds to a FAISS flat index (`chunk_metadata.json` holds per-chunk
  date/source_type/source_name/url/page). The reply bot:
  [`_extract_search_queries`](reply_monitor.py) (Sonnet splits the question) →
  [`_search_multiple`](reply_monitor.py) (per query: day-filtered then broad; dedupe) → top-20 chunks
  + the original digest as context → **Opus** answers → threads back.
- [`search.search`](search.py): embed query → FAISS candidates → crude keyword boost
  (`+0.05` per query word in chunk) → sort → top-k.
- **Weaknesses:** single dense vector search + naive keyword nudge (no BM25, **no reranker**); uniform
  fixed-size chunking across all source types (tables/filings split mid-fact); only `date`/`source_type`
  are filterable (no entity index); the "sequential search" = per-query loop + two-phase retrieval.

### The disconnect
System A knows storylines-over-time but is a throwaway blob for the digest. System B has all the raw
material and answers questions, but retrieves by pure similarity — no entity index, no timeline
stitching. **They never talk.** Closing that gap (Stage 5) is the real "piece together" upgrade.

## 3. Hard constraints / notes

- **Cost:** almost all of this is **local/free** to build and test (embeddings, reranker, BM25 run
  on-device). The only Claude spend is the reply bot's answer (Opus, ~$0.20/reply) — so build + test
  retrieval **offline**, then validate end-to-end with **one permissioned reply run**. (Optional
  LLM-NER at index time would add cost — avoid; use regex/watchlist first.)
- ⚠️ **Thin archive:** only **1 day is archived** (2026-06-30, 629 chunks), so retrieval-quality
  *measurement* is directional at best. Doesn't block building; real benchmarking needs more archived
  days to accrue over time. Stage 0 squeezes what signal the one day allows.
- **Substrate today:** FAISS `IndexFlatIP` + parallel `chunk_metadata.json` (index position i ↔
  metadata[i]). Fine on scale (good to ~100k chunks per HANDOFF §6); the friction is metadata
  filtering, not size.
- **Reversibility:** Stages 1–2 are additive (flag-gated). Stage 3 needs a full `rebuild_index()`
  (local/fast, reversible via revert + rebuild). Stage 5 changes the memory contract — keep the old
  `memory.json` format readable during transition; the digest's `get_memory_context()` reader must
  stay compatible.

---

## 4. Staged plan

### Stage 0 — Eval harness *(do first; free, offline)*
Build a small golden set of ~10–15 `question → expected-source` pairs from the 2026-06-30 archive
(e.g. "private credit fundraising" → Credit Crunch chunks; "MSTR capital framework" → MSTR 8-K;
"tungsten names / $ALM" → 13D; "$AGI seismic production cut" → 13D), plus a script that runs `search()`
and reports precision@k / MRR / "expected source in top-k?".
- **Why first:** every later stage needs a way to prove it helped, not guess.
- **Risk:** none. Grows more useful as days accrue.

### Stage 1 — Cross-encoder reranker *(highest ROI; free, offline)*
Retrieve a larger candidate pool (code already fetches `top_k*10`), then rerank `(query, chunk)` pairs
with a CrossEncoder (`bge-reranker-base` or `ms-marco-MiniLM`), return top-k by rerank score.
- **Where:** [`search.search`](search.py), param-gated (reply bot opts in).
- **Bonus:** higher-precision top-k lets the reply bot send *fewer* chunks → better answers + a
  slightly cheaper Opus reply.
- **Dep:** sentence-transformers CrossEncoder (~90–440 MB, CPU-fine, ~50–200 ms/query).
- **Test:** Stage-0 eval before/after; unit-test rerank ordering. **Risk:** low, reversible.

### Stage 2 — Hybrid search: BM25 + dense (RRF) *(free, offline)*
Add a BM25 lexical ranking (`rank_bm25`, built in-memory from `chunk_metadata`) and fuse with the dense
ranking via Reciprocal Rank Fusion — replacing the crude `+0.05` keyword boost ([search.py](search.py)).
- **Fixes** exact-token retrieval (tickers, CUSIPs, spreads) that dense embeddings miss.
- **Pipeline:** dense + BM25 → RRF fuse → candidate pool → (Stage 1) rerank → top-k.
- **Dep:** `rank_bm25`. **Test:** Stage-0 eval, esp. ticker/number queries; unit-test RRF.
  **Risk:** low, reversible.

### Stage 3 — Index upgrade: richer metadata + stronger embeddings *(one reindex; free, offline)*
Bundle everything that needs re-embedding into a single `rebuild_index()`:
- **Entity/date metadata:** tag each chunk with tickers (regex + `sec_filings.WATCHLIST` /
  `fund_tracking.TRACKED_FUNDS` name match — free; full company NER deferred) and dates → enables
  "everything about $ABR" + date-range filters (today only `date`/`source_type` filter).
- **Stronger embedder:** MiniLM 384-dim → e.g. `bge-base-en-v1.5` 768-dim (handle its query/passage
  prefix; bump `EMBEDDING_DIM`).
- (Optional to fold in here: **structure-aware chunking + PDF→md** extraction — they also change
  indexed content, so share the reindex.)
- **Test:** Stage-0 eval old vs new; confirm ticker tags populate + filter works.
  **Risk:** medium (dim change, prefix handling, reindex — but local/fast). Reversible via revert + rebuild.

### Stage 4 — Smarter retrieval in the reply bot *(mostly free; 1 permissioned reply to validate)*
- **Query understanding:** parse the question for entities/date-ranges (regex + the existing Sonnet
  extract) to drive the new metadata filters (entity-filtered + date-windowed retrieval).
- **MMR / dedup** in [`_search_multiple`](reply_monitor.py) / context build so near-duplicate chunks
  (same story across days) don't crowd the 80k-char window.
- **Test:** offline retrieval + one ~$0.20 permissioned reply run to confirm end-to-end. **Risk:** low.

### Stage 5 — Converge System A ↔ B (the real "piece together" bet; larger lift)
- Restructure cross-digest memory into a **queryable story-timeline store** — per-story dated update
  history, updated **incrementally** (append, not daily wholesale rewrite) → cheaper, higher-fidelity,
  queryable. (Also addresses System A's day-to-day drift/dropping.)
- **Wire it into the reply bot as a router:** storyline → entities + date window → targeted
  (filtered/hybrid/reranked) retrieval → synthesis. Turns "search returns chunks" into "assembles the
  narrative across time."
- **Touches** `memory.py` (model-driven → permissioned) and the reply bot; must stay compatible with
  the digest's `get_memory_context()` reader. **Risk:** medium-high; keep the old format readable
  during transition.

### Optional infra — substrate swap
Swap FAISS-flat + JSON for a metadata-native embedded store (**LanceDB / sqlite-vec / Chroma**) **only
if** the filtering in Stage 3/4 makes the current substrate clumsy. Defer unless it hurts.

---

## 5. Sequencing rationale

1→2 are additive, no reindex, immediate precision gains, fully offline. 3 bundles the one reindex. 4
leverages the new metadata. 5 sits on a solid System B. Everything through Stage 4 is free to iterate;
the first real Claude spend is the single reply-validation run.

**Recommended start:** Stage 0 + Stage 1 (eval harness + reranker) — free, offline, reversible, biggest
single quality jump.
