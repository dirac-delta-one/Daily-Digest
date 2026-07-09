# Memory / Retrieval Refactor — Spec

> Staged plan to improve how the system remembers and answers questions. Companion to
> `HANDOFF.md` (overall project state) and `WORKLOG.md` (running log). Scoped 2026-07-01;
> reviewed + restructured same day (Stage 3 split, date-filter + caching items added);
> **Stage 0 built 2026-07-01.** Update the Status table as stages land.

## Status

| Stage | What | State |
|---|---|---|
| 0 | Eval harness (golden Q→source set) | ✅ done 2026-07-01 — `tools/eval_retrieval.py` + `eval_golden.json` (15 Qs); baseline hit@1=0.93, MRR=0.96 (near-saturated: 1-day archive) |
| 1 | Cross-encoder reranker + date-filter fix | ✅ built 2026-07-01; **flip REJECTED at the 2026-07-09 checkpoint** — on the 6-day/26-question eval, rerank lost decisively (hit@3 0.885 vs 1.0, MRR 0.839 vs 0.904; promotes digest/broker-email chunks over primary sources). Mechanism stays param-gated; one retest inside Stage 4 (with digest-exclusion), else park |
| 2 | Hybrid search (BM25 + dense, RRF) + index caching | ✅ built 2026-07-02 (cache LIVE); **flip REJECTED at the 2026-07-09 checkpoint** — hybrid lost overall (MRR 0.872 vs 0.904) and introduced a genuine top-10 MISS (BM25 'oil' token flooding). Mechanism stays param-gated |
| 3a | Entity/date metadata tags + date-range filter (no reindex needed) | ✅ built 2026-07-02 — tags live at index time + `--retag` backfill (66/629 chunks tagged); `search(entity_filter=, date_from=, date_to=)`; entity-filtered eval case hits rank 1 |
| 3b | Stronger embeddings / structure-aware chunking (reindex) | ❌ SKIPPED (2026-07-09 checkpoint) — default retrieval has hit@3 = 1.0 on the 6-day eval; no headroom a bigger embedder addresses |
| 4 | Smarter retrieval in the reply bot (query understanding + MMR/dedup) | ⬜ not started |
| 5 | Converge System A ↔ B (story-timeline memory wired into the bot) | ⬜ not started |
| — | Optional: substrate swap (LanceDB / sqlite-vec) | ⬜ conditional |

*(Restructured 2026-07-01 after review: Stage 3 split — tagging only rewrites `chunk_metadata.json`,
no re-embedding, so it isn't gated on a reindex; the embedder swap is now conditional because the
Stage 1 reranker may capture most of the quality gain. The date-filter fix and index caching were
added — see the stage notes.)*

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
  fixed-size chunking across all source types (tables/filings split mid-fact); only `date` is filterable
  (the metadata *carries* `source_type` but `search()` exposes no filter for it; no entity index); the
  "sequential search" = per-query loop + two-phase retrieval. ⚠️ **Latent scaling bug:** `date_filter`
  is applied *after* FAISS retrieval — the top `top_k*10` candidates are fetched *globally*, then
  non-matching dates are discarded. Invisible with 1 day indexed; with 100+ days, the reply bot's
  day-filtered phase will often find few/no candidates from the target day even when relevant chunks
  exist. Fixed in Stage 1. Also: `search()` reloads the FAISS index and re-parses the full metadata
  JSON from disk on **every call** — fine at 629 chunks, multi-second at archive scale. Fixed in Stage 2.

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
  days to accrue over time. Stage 0 squeezes what signal the one day allows. *(Operator confirmed
  2026-07-01 the digest can run daily on this machine, so the archive accrues — hold the "did it
  help" verdicts loosely until it does.)*
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
and reports hit@k / MRR / "expected source in top-k?".
- **Where:** `tools/eval_retrieval.py` + a versioned `tools/eval_golden.json` (committed; grows as
  archived days accrue — add a few questions per new day worth testing).
- **Required coverage:** at least one **day-filtered** query (exercises the Stage-1 date-filter fix)
  and one **short-ticker** query (exercises the Stage-2 tokenizer), alongside the topical ones.
- **Why first:** every later stage needs a way to prove it helped, not guess.
- **Risk:** none. Grows more useful as days accrue.

### Stage 1 — Cross-encoder reranker + date-filter fix *(highest ROI; free, offline)*
Retrieve a larger candidate pool (code already fetches `top_k*10`), then rerank `(query, chunk)` pairs
with a CrossEncoder (`bge-reranker-base` or `ms-marco-MiniLM`), return top-k by rerank score.
- **Where:** [`search.search`](search.py), param-gated (reply bot opts in).
- **Also fix here (same function):** the post-retrieval `date_filter` scaling bug (§2B) — when a
  filter is present, over-fetch (raise `search_k`) or brute-force score just the matching chunks
  (flat-index vectors are reconstructable; one day ≈ hundreds of chunks) so day-filtered queries
  keep working as the archive grows. Pin with a Stage-0 day-filtered eval case.
- **Bonus:** higher-precision top-k lets the reply bot send *fewer* chunks → better answers + a
  slightly cheaper Opus reply.
- **Dep:** sentence-transformers CrossEncoder (~90–440 MB one-time download into the HF cache,
  CPU-fine, ~50–200 ms/query — irrelevant for an async email bot; note the disk footprint in the
  §7.2 server provisioning list).
- **Test:** Stage-0 eval before/after; unit-test rerank ordering. **Risk:** low, reversible.
- **Built 2026-07-01 — findings:** mechanism landed (`rerank=` param, `_rerank_candidates`,
  `ms-marco-MiniLM-L-6-v2` singleton) and the date-filter fix (`_search_vectors` subset search) is
  in for BOTH paths, pinned by unit tests. The no-rerank default is eval-identical to the Stage-0
  baseline. The rerank path scored *nominally lower* (hit@1 0.867 vs 0.933, MRR 0.922 vs 0.956) —
  inspection shows an artifact, not a quality loss: the reranker promotes **digest chunks** (dense
  summaries of everything) over raw source chunks, and the strict golden set prefers the underlying
  source. Real insight for Stage 4: the reply bot already loads the day's digest as separate context,
  so same-day digest chunks in retrieval are REDUNDANT for it — consider excluding/deprioritizing
  them there (MMR/dedup). **Decision: reply-bot opt-in (`rerank=True` in `_search_multiple`) is
  deferred until the archive has enough days for the eval to discriminate** — flipping production on
  "the eval is probably wrong" would defeat the Stage-0 discipline. Revisit at ~2 weeks of archive.

### Stage 2 — Hybrid search: BM25 + dense (RRF) + index caching *(free, offline)*
Add a BM25 lexical ranking (`rank_bm25`, built in-memory from `chunk_metadata`) and fuse with the dense
ranking via Reciprocal Rank Fusion — replacing the crude `+0.05` keyword boost ([search.py](search.py)).
- **Fixes** exact-token retrieval (tickers, CUSIPs, spreads) that dense embeddings miss.
- **Tokenizer must keep short tickers:** the existing boost regex (`\b\w{3,}\b`) drops 1–2 char
  tickers (GM, X…) — the exact failure mode this stage exists to fix. Tokenize so `$TICK`-style and
  1–2 char uppercase tokens survive; pin with a Stage-0 short-ticker eval case.
- **Also fix here:** cache the loaded FAISS index + metadata + BM25 index in-process with
  mtime-based invalidation (§2B — `search()` currently re-reads both from disk every call; the
  long-running reply monitor must pick up the new day the morning digest appends). One cache covers
  all three, since the BM25 build needs the same staleness check anyway.
- **Pipeline:** dense + BM25 → RRF fuse → candidate pool → (Stage 1) rerank → top-k.
- **Dep:** `rank_bm25`. **Test:** Stage-0 eval, esp. ticker/number queries; unit-test RRF +
  cache invalidation. **Risk:** low, reversible.
- **Built 2026-07-02 — findings:** mechanism landed (`hybrid=` param: dense + BM25 → RRF k=60 →
  pool → optional Stage-1 rerank; `_tokenize` keeps 1–2 char tickers and normalizes `$ABR`→`abr`;
  `rank_bm25==0.2.2` pinned). The **search-state cache is live for all callers** (index + metadata +
  BM25 behind one mtime/size signature; default path eval-identical to baseline, so behavior-neutral
  confirmed). Hybrid evals at hit@1 0.867 vs 0.933 — the same 1-day duplication ceiling as Stage 1
  (a digest chunk and the WILTW PDF's oil discussion outrank the golden set's preferred sources; both
  defensible answers). **Decision: keyword-boost stays the default; the hybrid flip (and the reply-bot
  opt-in) wait for the same multi-day eval evidence as Stage 1.** Revisit both together at ~2 weeks of
  archive — BM25's discriminating case (a ticker dense retrieval *misses*) can't occur when every
  chunk fits in the candidate pool anyway.

### Stage 3a — Entity/date metadata tags + date-range filter *(free, offline, NO reindex)*
Tagging only rewrites `chunk_metadata.json` — the vectors are untouched — so this is decoupled from
any re-embedding and can land anytime (even before Stage 2):
- **Entity tags:** tag each chunk with tickers (regex + `sec_filings.WATCHLIST` /
  `fund_tracking.TRACKED_FUNDS` name match — free; full company NER deferred) → enables
  "everything about $ABR"-style filtered retrieval.
- **Coverage expectation (be honest in acceptance tests):** this covers the ~16 watchlist tickers,
  ~13 tracked funds, and `$TICK`-pattern mentions in text. Entities *outside* the watchlist
  (e.g. a memory storyline like "Wynn Resorts") are NOT tagged until real NER — don't overpromise.
- **Date-range filter:** the current `date_filter` is a string prefix match; a range (`date_from`/
  `date_to`) is a small `search()` change on the existing `date` field — no metadata change at all.
- **Test:** ticker tags populate; filters work; Stage-0 eval unchanged (this adds capability, not
  ranking changes). **Risk:** low, reversible.
- **Built 2026-07-02 — findings:** `_extract_entities` (watchlist tickers case-sensitive on word
  boundaries; any `$TICK` mention even off-watchlist — caught 13D's $ALM and the KBW note's
  IBKR/OCFC; tracked-fund names + distinctive first-word aliases, with "Avenue"/"Canyon" excluded as
  too generic). Tags are applied at index time in `_chunks_for_date` and backfilled via
  `python search.py --retag` (metadata-only rewrite; vectors untouched). New `search()` params
  `entity_filter` / `date_from` / `date_to` (all pre-retrieval via the shared `_filter_ids`;
  $- and case-insensitive entity matching). Real-archive backfill: **66/629 chunks tagged** (MSTR 11,
  RWT 7, PGY 6, WYNN/ALM 2, plus fund names). Eval: all prior items unchanged; the new
  entity-filtered golden case (vague query + `entity_filter=MSTR`) hits rank 1. Unit tests +11
  (tagger incl. case-sensitivity + generic-word skip; combined date/range/entity filtering incl.
  pre-retag chunks without an `entities` key). Nothing consumes the filters in production yet —
  that's Stage 4's query understanding.

### Stage 3b — Stronger embeddings / structure-aware chunking *(reindex; CONDITIONAL)*
The pieces that genuinely require re-embedding, held until the Stage-0/1 evidence says they're
needed — the Stage-1 cross-encoder often captures most of the quality gain a bigger bi-encoder
would, so measure first:
- **Stronger embedder:** MiniLM 384-dim → e.g. `bge-base-en-v1.5` 768-dim (handle its query/passage
  prefix; bump `EMBEDDING_DIM`; ~400 MB+ download — add to the §7.2 disk list).
- **Structure-aware chunking + PDF→md extraction** — also change indexed content.
- **Do these as SEPARATE measured reindexes** (embedder first, then chunking, or vice versa) — a
  bundled reindex makes the eval delta unattributable.
- **Test:** Stage-0 eval old vs new per reindex. **Risk:** medium (dim change, prefix handling,
  reindex — but local/fast). Reversible via revert + rebuild.

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

1→2 are additive, no reindex, immediate precision gains, fully offline. 3a is additive too (metadata
only); 3b holds the only reindexes, gated on evidence. 4 leverages the new metadata. 5 sits on a solid
System B. Everything through Stage 4 is free to iterate; the first real Claude spend is the single
reply-validation run.

**Recommended start:** Stage 0 + Stage 1 (eval harness + reranker) — free, offline, reversible, biggest
single quality jump.
