# Work Log

Running log of everything done in the Daily-Digest refactor, phase by phase (newest on top).
Companion to `HANDOFF.md` (the plan/spec) and its §11 "Needs Testing" (deferred verification).

---

## Current state (2026-07-01)

**The system is LIVE-validated end-to-end on the bot identity.** All prior refactor work
(Phase 0–3, de-hardcoding, A1, Gmail RefreshError hardening) is committed + offline-verified. Since
then: the **email identity migrated to `acorn.research.bot@gmail.com`** (OAuth provisioned + verified),
**Octus was removed**, the **$20 Anthropic key + a free FRED key** were installed, and the **first
credentialed run of the whole stack succeeded**, all → acohen: `digest.py` **$1.52**,
`reply_monitor.py --once` **$0.20**, `midday.py --force` **$0.01** (~$1.73 of $20). `ruff` clean,
`pytest` 56 green, FRED macro + Fed-balance-sheet sources now active. See the 2026-06-30 entries below.
A post-live **optimization session** then landed (Opus 4.8 upgrade, model/UA centralization, dead-code
removal incl. `net_utils`/`build_ratings_html`, 3.1 keyword-only, Fed-stress numeric wiring,
SYSTEM_PROMPT §9 fix, A2 structured outputs) — **all committed** (`62002e0`→`543065a`; working tree clean).

✅ **Group B Opus→Sonnet cost A/B — DONE 2026-07-01.** The A/B's *quality* verdict was keep-all-Opus.
Detail in the dedicated section below and HANDOFF §11 "Cost/efficiency" → Group B.

✅ **Cost refactor steps 1–3 — DONE 2026-07-01** (`pytest` **60** green, `ruff` clean): (1) **13D WILTW
summary cache** (`wiltw_cache.json`) — stops re-summarizing the same weekly PDF 4–6×/week (~$130–150/yr,
zero quality impact); (2) **memory → Sonnet** — a *cost* follow-up to the A/B (memory output was
near-identical, ~$0.16/run saved; one-line, reversible); (3) **2-pass digest prompt caching** — pass 1
writes the source/PDF prefix to cache, pass 2 reads it (~0.1×) instead of re-sending at full price
(~$0.10/run text-day, ~$0.54/run on a 5 MB-PDF day). Validated output-equivalent + cache-engaging via a
permissioned before/after (~$3.5). Detail in the sections below.

➡️ **COST REFACTOR COMPLETE.** Remaining cost ideas are lower-value (conditional pass-2 skip; 13D
text-extraction) — see §14; not worth the effort/risk. **NEXT MAJOR TRACK: the memory / retrieval
refactor, scoped + reviewed in `MEMORY_REFACTOR_SPEC.md`** (eval harness → reranker → hybrid search →
entity metadata → System A↔B convergence; mostly local/free to build + test). **Stage 0 (eval harness)
is BUILT — 2026-07-01, baseline recorded; Stage 1 (reranker + date-filter fix) is next.** **Other
tracks:** the §7.2 server deploy (= "done") and the §13 coverage gaps.

**Remaining:** the §13 source-coverage gaps (Substack renewal, forwarding completeness w/ jared,
TRACE + Octus unreplaced), the `.bat`/`setup_tasks` scheduling test, the remaining do-and-test item
**3.3** (PDF review, needs more PDF data), the wait-and-see items (3.5), and the **§7.2 server deploy**
(= "done"). See HANDOFF §14.

---

## Memory / retrieval refactor — Stage 2: BM25+RRF hybrid + search-state cache (2026-07-02)

Built offline/free (no Claude calls). New dep `rank_bm25==0.2.2` (pure Python, pinned).
`ruff` clean, `pytest` **81** green (+8).

**What landed (`search.py`):**
- **Search-state cache — LIVE for all callers:** `_get_search_state()` holds the FAISS index +
  metadata + BM25 corpus behind one mtime/size file signature, replacing the per-call disk
  reload/JSON parse (multi-second at archive scale). The long-running reply monitor picks up the
  day the morning digest appends without restarting. Behavior-neutral: the default path is
  eval-identical to the committed baseline.
- **Hybrid retrieval, param-gated:** `search(hybrid=True)` fuses the dense ranking with a BM25
  lexical ranking via RRF (k=60), feeding the fused pool to the optional Stage-1 rerank. New
  `_tokenize` keeps 1–2 char tickers (GM, X) and normalizes `$ABR`↔`ABR` — the short-ticker
  failure mode the old `\w{3,}` boost regex had. CLI/eval `--hybrid` flags.
- Unit tests (+8): tokenizer (short tickers, $-normalization), RRF math + both-lists-beats-solo,
  BM25 exact-token + allowed-ids restriction + zero-score cut, cache hit/invalidation round-trip
  on a real tiny FAISS index.

**Eval:** default = baseline exactly (hit@1=0.933/MRR=0.956 — cache neutrality confirmed); hybrid
(and hybrid+rerank) = 0.867/0.922 — the same 1-day duplication ceiling as Stage 1 (digest chunk +
the WILTW PDF's oil discussion outrank the golden set's preferred sources; both defensible).
Snapshot `2026-07-02_stage2-hybrid.json`. **Decision: keyword boost stays default; the hybrid flip
joins the reply-bot rerank opt-in as a single revisit once ~2 weeks of archive accrue** — BM25's
discriminating case (dense retrieval *missing* a ticker) can't occur while one day's chunks all fit
in the candidate pool. Next: Stage 3a (entity tags + date-range filter, no reindex).

---

## Memory / retrieval refactor — Stage 1: reranker + date-filter fix (2026-07-01)

Built entirely offline/free (no Claude calls; one-time ~90MB `ms-marco-MiniLM-L-6-v2` download).
`ruff` clean, `pytest` **73** green (+5).

**What landed (`search.py`):**
- **Date-filter fix (both paths):** `date_filter` is now applied *before* retrieval — new
  `_search_vectors(index, query_vec, k, allowed_ids)` brute-force scores exactly the matching
  vectors (IndexFlat reconstruct; exact, cheap at ~hundreds of chunks/day) instead of discarding
  non-matching dates from a global top-k. Kills the §2B scaling bug before it could bite. Pinned by
  unit tests (subset-only results, exact dot-product scores, k-cut, global path = FAISS order).
- **Cross-encoder reranker, param-gated:** `search(rerank=True)` re-scores the `top_k*10` candidate
  pool with a CrossEncoder singleton (`_get_reranker`, same lazy pattern as the embedder) and ranks
  by logit; default `rerank=False` keeps the cosine+keyword-boost scoring byte-identical. CLI
  `--rerank` on search.py; `--rerank` on the eval harness too.

**Eval (Stage-0 golden set):** the refactored default path is **identical to the committed baseline**
(hit@1=0.933, MRR=0.956 — behavior-neutral refactor confirmed). The rerank path scored *nominally
lower* (hit@1=0.867, MRR=0.922) — inspection shows an eval artifact, not a quality loss: the
reranker promotes **digest chunks** (dense summaries matching almost any question) over the raw
source chunks the strict golden set expects. Snapshot saved (`2026-07-01_stage1-rerank.json`).

**Decision — reply-bot opt-in DEFERRED:** flipping `_search_multiple` to `rerank=True` on a 1-day
archive would mean overriding the eval we just built ("it's probably wrong") — the opposite of the
Stage-0 discipline. Revisit once ~2 weeks of archive accrue and the eval can discriminate. **Insight
banked for Stage 4:** the reply bot already loads the day's digest as separate context, so same-day
digest chunks in retrieval are redundant for it — exclude/deprioritize them in the reply path
(MMR/dedup). Golden-set readme updated with the digest-chunk expectation convention.

---

## Memory / retrieval refactor — spec review + Stage 0 eval harness (2026-07-01)

Reviewed `MEMORY_REFACTOR_SPEC.md` against the actual code and **restructured it** (operator-approved):

- **New finding — date-filter scaling bug (added to Stage 1):** `search()` applies `date_filter`
  *after* FAISS retrieval, so the `top_k*10` candidates are global; with 100+ days indexed the reply
  bot's day-filtered phase will often surface few/no target-day chunks. Invisible today (1 day
  indexed). Fix specced (over-fetch or per-day brute-force) + pinned by a day-filtered eval case.
- **New finding — per-call index reload (added to Stage 2):** `search()` re-reads the FAISS index +
  full metadata JSON from disk on every call; fold an mtime-invalidated cache in with the BM25 build
  (which needs the same staleness logic).
- **Stage 3 split:** 3a (entity/date metadata tags + date-range filter — metadata-only, NO reindex,
  can land anytime) vs 3b (embedder swap / structure-aware chunking — the actual reindexes, now
  **conditional** on Stage 0/1 evidence, done as separate measured reindexes). Also set honest
  entity-coverage expectations (watchlist + $TICK patterns only until real NER).
- Stage 2 tokenizer note (keep 1–2 char tickers — the exact failure mode BM25 exists to fix);
  §2B accuracy fix (only `date` is filterable, not source_type); model-download footprints noted
  for the §7.2 server disk list. Operator confirmed the digest can run daily on this machine, so
  the archive (and eval signal) accrues.

**Stage 0 — BUILT (free, offline, no Claude calls):** `tools/eval_retrieval.py` (harness: hit@1/3/5/10 +
MRR, per-question first-match rank, `--save` snapshots to gitignored `tools/eval_results/`) +
`tools/eval_golden.json` (15 versioned golden questions from the 2026-06-30 archive, spanning
substack/filing/wiltw/rating/email/news/digest; includes the required **day-filtered** case and
ALM/AGI/WF6 exact-token probes — a true 1–2 char ticker case gets added when one appears in the
archive). Match semantics pinned by new `tests/test_eval_retrieval.py` (+8; suite **68** green, ruff
clean). **Baseline (2026-07-01): hit@1=0.933, hit@3/5/10=1.0, MRR=0.956** — near-saturated, as
expected with a single archived day (little competition); treat Stage 1/2 deltas as directional
until more days accrue. Note: the WILTW report is indexed twice (Opus summary `wiltw` + raw `pdf`),
so 13D golden items accept either; the one non-rank-1 item (13d-portfolio, rank 3) is a raw-PDF
chunk outranking the summary.

---

## Memory / retrieval refactor — scoped (2026-07-01)

Planning only (no code). Wrote **`MEMORY_REFACTOR_SPEC.md`** — a standalone staged plan to improve
retrieval and converge the two "memory" systems. Captures the TL;DR of both systems and the disconnect
(System A = the cross-digest `memory.json` storylines, only feeds the digest; System B = the FAISS
archive + reply bot, answers questions but can't piece together across time), plus Stages 0–5:
(0) eval harness, (1) cross-encoder reranker, (2) hybrid BM25+dense (RRF), (3) index upgrade — entity/date
metadata + stronger embeddings (one reindex), (4) smarter reply-bot retrieval (query understanding +
MMR/dedup), (5) System A↔B convergence (queryable story-timeline store wired into the bot). Mostly
local/free to build + test (only the reply answer, Opus, costs). **Thin-archive caveat:** only 1 day is
indexed today, so retrieval-quality measurement is directional until more days accrue. *(Superseded
same day: the spec was reviewed/restructured and Stage 0 built — see the entry above.)*

---

## Cost refactor — step 3: 2-pass digest prompt caching (2026-07-01)

`digest.summarize_with_claude` restructured so the two Opus passes share a cached source prefix.
`pytest` **60** green, `ruff` clean.

**The problem:** pass 2 re-sent the entire source material + all PDFs at full price (`review_prompt.extend(content)`)
so the big input was billed ~twice. Naive caching couldn't help (the two passes had different `system`
prompts and pass 2 put the draft/review text *before* the sources — no shared cacheable prefix; this was
the §14.E "2.1 dropped" finding).

**The restructure (cache-correct):**
- Both passes now use the **same `system` (`SYSTEM_PROMPT`)**; the pass-2 "you are reviewing a draft"
  framing moved into the trailing user block.
- The source material (text + PDFs) is the **identical leading prefix** in both passes, with a
  `cache_control: ephemeral` breakpoint on the last shared block; each pass's instruction (generate /
  review-this-draft) goes **after** the breakpoint. Pass 1 writes the cache, pass 2 reads it (~0.1×).
  The passes run seconds apart, inside the 5-min TTL.

**Validation (permissioned A/B, ~$3.5 total — a foreground run timed out mid-PDF-mode; recovered):**
- **Output equivalence — PASS.** Baseline vs restructured final digests on the archived 2026-06-30
  sources were equivalent (same stories, structure, no errors); the restructured version actually
  adhered *better* to the template's `<span style="color:#888">` source-tag styling (pass 2 now runs
  under the full `SYSTEM_PROMPT`). Caching itself is **transparent to the model** (identical tokens
  either way), so the only output-affecting change is the restructure — proven safe on the text case,
  which covers the PDF case too.
- **Cache engagement — CONFIRMED.** A 2-call check showed pass 1 `cache_creation=30,183`, pass 2
  `cache_read=30,183` (uncached input just 6,568) — real numbers, SDK 0.109.2 / Opus 4.8.
- **Saving:** cached ≈ $0.57 vs baseline ≈ $0.67 on a 30k-token text day (**~$0.10/run**); deterministic
  math + `count_tokens` put a 5 MB-PDF day at **~$0.54/run**. Win scales with inbox-PDF volume, so the
  bulk is **latent until the §13 PDF-forwarding is flowing** (the archived run had 0 inbox PDFs).
- The in-function cost print is now cache-aware (`cost.cost_of`) and logs `pass 1 wrote N / pass 2 read N`
  — that line is the live confirmation the cache engages on real runs. Dropped the now-unused
  `OPUS_PRICE_IN/OUT` imports from `digest.py`.
- A/B harness (`step3_cache_ab.py`) + the four text-mode digests were kept in the session scratchpad;
  **moved into the repo 2026-07-01** — harness committed at `tools/step3_cache_ab.py` (paths made
  repo-relative), digests preserved locally at `tools/step3_outputs/` (gitignored).

---

## Cost refactor — steps 1 & 2 (2026-07-01)

First two changes from the cost-cutting plan (both offline-safe; no permissioned Claude call needed —
step 2 was already validated by the Group B A/B, step 1 has zero quality surface). `pytest` **60** green
(+4), `ruff` clean.

**Step 1 — 13D WILTW summary cache (`thirteen_d.py`).** `fetch_wiltw` now caches each summary by report
date in `wiltw_cache.json` (gitignored). WILTW publishes Thursdays but the digest runs daily, so the
same 4.7 MB PDF was re-downloaded (Playwright) and re-summarized (a ~$0.65 Opus call) every run
Thursday→Wednesday. On a cache hit `fetch_wiltw` returns the stored summary and skips both the download
and the Opus call (the Playwright import moved *after* the cache check, so a hit needs no browser).
Estimated saving ~$2.5–3/week (~$130–150/yr); **zero quality impact** (same summary, generated once).
Pinned by new `tests/test_thirteen_d_cache.py` (cache round-trip; cache hit must not download or
summarize; stale-report skip).

**Step 2 — memory → Sonnet (`memory.py`).** `CLAUDE_MODEL` is now `SONNET_MODEL`. A *cost* follow-up to
the Group B A/B (whose keep-all-Opus verdict was a quality call): memory output was near-identical
Opus↔Sonnet — Opus kept 2 more credit stories — so this banks ~$0.16/run for a slight completeness
trade. One-line, reversible. **Watch for ~a week:** memory compounds day-over-day (each update rewrites
the prior memory), so keep a live eye on story retention; revert to `OPUS_MODEL` if it drifts.
Structured outputs (A2) already work on Sonnet.

**Not done (deferred):** step 3 (prompt caching on the 2-pass digest — permissioned before/after, touches
the load-bearing `SYSTEM_PROMPT`); the 13D text-extraction / Sonnet+tightened-prompt squeeze (marginal
once the cache lands — PDF→md extraction reassigned to the Part-2 retrieval work); alerts left on Opus
(the A/B evidence there was a single null datapoint).

---

## Group B cost A/B — Opus 4.8 vs Sonnet 4.6 (2026-07-01)

**DONE — decision: keep all four calls on Opus. No code changes** (working tree still clean;
`memory.CLAUDE_MODEL` / `alerts.CLAUDE_MODEL` / `thirteen_d.CLAUDE_MODEL` / `reply_monitor.REPLY_MODEL`
all remain `OPUS_MODEL`). The permissioned A/B ran the four embedded/secondary Claude calls through
**both** Opus 4.8 and Sonnet 4.6 on the real 2026-06-30 archived inputs, isolating the model as the
only variable — side effects disabled (no email, `memory._save_memory` monkeypatched to a no-op so
`memory.json` was untouched, and reply's retrieval context frozen so only the answer model varied).
**Total spend $1.89** (est. was ~$1.75; budget $1.50–$2.00).

Per-call results (cost = one call each model; saving = per-run if that call were switched to Sonnet):

| Call | Opus 4.8 | Sonnet 4.6 | Saving/run | Finding |
|---|---|---|---|---|
| Alerts | $0.098 | $0.042 | ~$0.056 | Identical result (0/7 triggered) — one null datapoint, can't distinguish quality. |
| Memory | $0.278 | $0.116 | ~$0.162 | Near-identical content; Opus kept 2 more credit stories (Wynn Moody's cut; PE debt-like deals). |
| 13D WILTW | $0.721 | $0.425 | ~$0.296 | Sonnet richer/more granular but blew the 500–800-word cap (~1,900 vs ~700 words) — would bloat the digest 3×. |
| Reply | $0.139 | $0.065 | ~$0.074 | **Sonnet malformed** — wrapped its answer in a ```html fence + a full `<!DOCTYPE html>` document → renders broken in the email. |

- **Decision (operator, 2026-07-01): keep all four on Opus.** Reply and 13D have concrete quality
  catches; memory/alerts savings are small (~$0.06–0.16/run) against a ~$1.50/day system — not worth
  trading quality/consistency for ~$0.30/day best case.
- **Notes for any future revisit:** 13D→Sonnet is only viable *with a tightened length instruction*;
  reply must stay Opus (render bug); the Opus em-dash `—` mojibake seen in the memory A/B was
  **run-variance** — the live 2026-06-30 `memory.json` is clean. The A/B harness (`groupb_ab.py`) and
  the side-by-side outputs were kept in the session scratchpad; **moved into the repo 2026-07-01** —
  harness committed at `tools/groupb_ab.py` (paths made repo-relative), outputs preserved locally at
  `tools/ab_outputs/` (gitignored).

---

## A2 — structured outputs (permissioned test run, 2026-06-30)

The one deferred code item that needed a live run. All 5 JSON-returning Claude call sites now use
`output_config.format` (structured outputs), so the model returns **guaranteed-valid JSON** matching a
schema — no ```json-fence stripping, no silent parse-failure drops (the key win for alerts/memory,
which previously discarded the whole pass on a bad parse). ~$0.04 total; small inputs; no email.

- **Support confirmed live** on Opus 4.8 / Sonnet 4.6 / Haiku 4.5 via the native `output_config=`
  kwarg (SDK 0.109.2 — no `extra_body` needed). The Models-API `capabilities["structured_outputs"]`
  read back `None` (a pinned-SDK metadata quirk); the live calls prove support.
- **New `claude_utils` helpers:** `json_schema_output(schema)` and `wrapped_array_schema(key, item_type)`
  (structured outputs want a top-level object, so array returns are wrapped under a key and unwrapped
  after parse).
- **Call sites:** `alerts.evaluate_alerts` (Opus; `results` array, nullable `detail`/`source` via
  `["string","null"]`), `memory.update_memory` (Opus; nested story object), `digest._rank_news_articles`
  (Haiku; `indices`), `pacer._filter_by_size` (Sonnet; `indices`), `reply_monitor._extract_search_queries`
  (Sonnet; `queries`). Prompts describe the object shape; parsing unwraps the key.
- **Live-confirmed** (small inputs): alerts → correct 2/7 triggers; news rank → the 4 credit items of 9;
  reply → 2 clean queries; memory → valid nested object (all 6 story fields); pacer → the 2 large
  entities. Memory + pacer were exercised as isolated schema probes to avoid touching `memory.json` /
  triggering PACER's web scraping.
- **Tests:** new `tests/test_claude_utils.py` (parse + schema helpers, +7). `ruff` clean, `pytest` **56**.

---

## SYSTEM_PROMPT §9 fix + Rating-Actions clarification (2026-06-30)

Follow-up to a premise error the operator caught: an earlier note claimed the digest had **no** §9
Rating Actions section and that `build_ratings_html` should be re-enabled to add one. Checking the
**archived 2026-06-30 email** disproved it — §9 was present, written by **Opus** (curated prose with
ticker + "(Moody's via …)" source tags; none of `build_ratings_html`'s ▼/▲ arrows or per-item links).

- **Root cause:** the `SYSTEM_PROMPT` said "Sections 9 (Rating Actions), 10, 11 … do NOT generate those
  yourself," but the rating data is fed to Opus and it writes §9 anyway (instruction ignored) — while
  §10/§11 really are appended (`build_news_html` / `build_funds_html`). A latent contradiction.
- **Fix:** made §9 an explicit **Opus-owned** section in the `SYSTEM_PROMPT` (added a Rating Actions
  spec + template comment) and scoped the "do NOT generate" line to §10/§11 only. Clarified the
  `digest.py` `ratings_html=""` comment (Opus writes §9; `build_ratings_html` is the disabled raw-table
  alternative — enabling it naively *duplicates* §9).
- **Decision + follow-up cleanup:** `build_ratings_html` was **removed as dead code** (zero references;
  it would have duplicated Opus's §9) — along with its now-unused `esc`/`safe_href` import and the
  vestigial always-`""` `ratings_html` plumbing in `_assemble_digest_html` (param + dead branch + call
  arg). The curated Opus §9 is the better product; the table's only edge was completeness. Not
  Octus-related after all. Recoverable from git. ruff + pytest 49 + live `ratings.py` run green.
- Corrected the stale premise + "keep the function" across HANDOFF §1 / §6 / §10 / §14.D.
- **Note:** this touches the load-bearing `SYSTEM_PROMPT`, so the §9 output should be eyeballed on the
  next digest run. Low-risk (matches existing behavior; `_assemble_digest_html` anchors untouched);
  `ruff` + `pytest` 49 green offline.

---

## Fed stress alert → numeric check wired in (2026-06-30)

Converted the discount-window stress alert from an LLM-evaluated config rule to a deterministic code
check (operator chose this over just fixing the threshold, for testability + single-source-of-truth).
Offline, no Claude call. `ruff` clean, `pytest` **49 green** (+8), alert-box render confirmed.

- **Removed** the stale `alerts_config.json` "Fed stress signal" rule (was "$5B / +$2B WoW" — would
  mis-fire daily against the corrected ~$8B discount-window baseline, since it was calibrated against
  the old mislabeled ~$900B TGA series).
- **Wired `fed_balance_sheet.check_fed_stress(fed_bs)` into `digest.main`** — its $25B-absolute /
  $10B-WoW-surge signals now merge into the same red "⚠️ ALERTS" box via `build_alerts_html`. Runs even
  if the LLM alert eval fails. Threshold now lives in exactly one place (code, next to the series).
- Qualitative Fed events (emergency statements, new facilities) stay covered by the separate LLM
  "Fed surprise" rule — the numeric check owns only the discount-window *level*.
- New `tests/test_fed_stress.py` (8 tests): threshold logic (silent at baseline, absolute + surge fire,
  non-DW rows ignored, `wow_change=None` safe) + the merge rendering in the alert box.

---

## General code cleanup + Opus 4.8 upgrade + 3.1 keyword-only refactor (2026-06-30)

Offline-only pass (no Claude calls), all verified: `ruff` clean, `pytest` **41 green**, all touched
modules import, constants resolve, `python market_data.py` runs (free Yahoo).

- **Phase 3.1 — digest-core keyword-only** — `_build_source_prompt` / `summarize_with_claude` (17
  same-typed source args, a misroute footgun) converted to keyword-only (`def f(*, ...)`); both call
  sites in `digest.py` now pass named args. The full `main()` source-registry refactor was left out
  (optional). Pinned offline by new `tests/test_digest_prompt.py` (keyword-only contract → `TypeError`
  on positional; per-source sentinel routing; determinism). The HANDOFF "byte-identical end-to-end
  run" acceptance was over-conservative for a mechanical signature swap — no permissioned run used. +5
  tests (36 → 41).
- **Opus 4.6 → 4.8** (operator-directed; same API surface + $5/$25 pricing, verified against the
  claude-api pricing reference). One-line change in
  `config.py` (`OPUS_MODEL`), which the 5 importing modules pick up automatically. HANDOFF §2/§10
  "keep 4.6" constraint updated.
- **Model-ID consolidation** — Phase 1.1 had only centralized Opus; Sonnet/Haiku were still scattered
  string literals while `config.SONNET_MODEL`/`HAIKU_MODEL` sat unused. Routed every call through
  config: `midday.py` (dropped its own local `SONNET_MODEL`), `pacer.py`, `reply_monitor.py` →
  `config.SONNET_MODEL`; `digest.py` (×2) → `config.HAIKU_MODEL`. **Behavior-neutral:** set
  `config.HAIKU_MODEL` to the exact dated snapshot already in use (`claude-haiku-4-5-20251001`), so
  the string is unchanged.
- **Shared scraper User-Agent** — the duplicated `"DailyDigest/1.0 (acorn.research.bot@gmail.com)"`
  contact (sec_filings / pacer / trace_data / fund_tracking) is now one `config.USER_AGENT` constant.
- **Dead code removed** — `market_data.py`'s write-only cache (`_load_cache` was defined but never
  called after Phase 0.2 removed its reader; nothing consumed `market_data_cache.json`): deleted the
  cache functions, the cache-build block, the now-unused `json`/`datetime`/`Path` imports, the
  `.gitignore` entry, and the stale on-disk file. Removed unused `SCRIPT_DIR` from `reply_monitor.py`.
- **Stale text** — dropped the "Octus intelligence" mention from `reply_monitor.py`'s RAG system
  prompt (Octus was removed); fixed README's Substack config (`MAX_ARTICLES` →
  `MAX_ARTICLES_PER_PUB`, default 3).
- **Nice-to-have dedups (DONE in a follow-up pass, same day)** — new `net_utils.py` (`edgar_get` +
  `unverified_ssl_context`): the two EDGAR `_make_request` (sec_filings parses JSON, fund_tracking
  takes raw text + 20s timeout) now share `edgar_get`; the duplicated unverified-SSL context
  (treasury_auctions + cftc_cot) now shares `unverified_ssl_context`. Separately, `fed_research`'s
  `_parse_date`/`_is_recent` now import `feeds.is_recent` (its divergent `_fetch_feed` stays).
  Behavior-neutral: `ruff` clean, `pytest` 41 green, plus live free-fetcher smoke (edgar_get → dict/text,
  Treasury + CFTC auctions/positioning, fed_research date-filtering) all confirmed.
- **Bare RSS/data-feed User-Agent centralized** — `"DailyDigest/1.0"` (distinct from the SEC/PACER
  contact UA) was repeated in 7 files; now one `config.FEED_USER_AGENT`. `feeds.fetch_feed` defaults to
  it (so news/ratings dropped their redundant local constant + explicit arg); `fed_research`, `cftc_cot`,
  `fdic_monitor`, `treasury_auctions` import it. Behavior-neutral (same string); ruff + pytest 41 +
  news/fdic live smoke green.
- **Intentionally NOT done** (deliberate divergence): `news._clean_html` vs the inline `re.sub` tag
  strips in `ratings.py`/`fed_research.py` — `_clean_html` also unescapes entities, so merging would
  change what's fed to Opus/embeddings (§3.2). The `alerts_config.json` Fed `$5B` threshold is a
  behavior/decision item, not cleanup.

---

## Credentialed bring-up + first live end-to-end run (2026-06-30)

First time the full pipeline ran with real secrets. **All Tier-C tests green; ~$1.73 spent of $20.**

### Email identity → acorn.research.bot@gmail.com
- Swapped `jaredtramontano@gmail.com` → the bot in `DIGEST_RECIPIENTS` (`digest.py`) and the reply
  allow-list (`reply_monitor.py`); switched the SEC/PACER scraping User-Agent to the bot in
  `sec_filings.py` / `pacer.py` / `trace_data.py` / `fund_tracking.py` (overrides the old §7.1.6
  keep-jared decision).
- **Bot Gmail OAuth provisioned + verified** — fresh Cloud project owned by the bot, Gmail API enabled,
  bot added as a test user. `getProfile` confirms the authenticated account is the bot; its inbox
  receives jared's forwarded research (KBW, STIFEL IG/HY, Barclays Distressed, Guggenheim, etc.).
- `.gitignore` broadened to `credentials_*.json` / `token_*.json` / `*.bak` so the jared backup
  (`credentials_JARED.json`) can't be committed.

### Octus removed
- Deleted `octus.py` + `octus_session.json`; stripped all wiring from `digest.py`, `archive.py`,
  `search.py`; scrubbed docs. The live digest ran Octus-free with no hang (the stale Octus login would
  otherwise have blocked an unattended run on its interactive re-login prompt — the same latent risk was
  confirmed-absent for 13D via a headless session probe before the run).

### First live run (all → acohen; key in env.bat)
- `digest.py` (bounded for the first run: `MAX_EMAILS` 6 / `MAX_PDF_SIZE_MB` 2, both reverted after) →
  **$1.52**: 6 emails, 7 Substack, 5 SEC filings, 144 WSJ/FT (ranked to 15), 4 ratings, 13D WILTW
  (4.7MB PDF → Opus summary **$0.65 = the cost driver**), 2-pass Opus $0.60, alerts (0 triggered),
  memory (18 stories), PACER Sonnet size-filter. Email rendered correctly; `archive/2026-06-30/` +
  FAISS (629 chunks) + `memory.json` all written. The SSL-retry on send fired once and recovered.
- `reply_monitor.py --once` → **$0.20**: answered acohen's "state of private credit H1 2026" question
  with a detailed, well-sourced RAG answer (top-10 funds table, contrarian framing, adjacent
  FSK/FT/Bloomberg points) — **retrieval quality confirmed high**. Threaded back to acohen.
- `midday.py --force` → **$0.01**: Sonnet materiality check returned NO_ALERT (correct — nothing
  material since the 10:39 morning cutoff); `--force` sent it anyway. Confirms the path works AND that
  unforced middays correctly stay silent.
- Key + the 3 model IDs (`claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`)
  smoke-tested OK before the run.

### FRED provisioned + tested
- `FRED_API_KEY` added to `env.bat`. `macro_data.py` → 12 series ✅ (HY/IG OAS, 2Y/10Y + derived 2s10s,
  breakevens, jobless claims, CPI, dollar, fed funds, SOFR). `fed_balance_sheet.py` → 6 series ✅.
- **Finding + fix (data bug):** `fed_balance_sheet.py` series were mislabeled by magnitude — "Discount
  Window" (`WDTGAL`) read **$901.8B** and "Treasury Holdings" (`WTREGEN`) read $0.92T, but both IDs are
  the Treasury General Account. Verified against the FRED API and **fixed same day**: Treasury Holdings
  → `WSHOTSL` (SOMA UST ~$4.49T), Discount Window → `WLCFLPCL` (primary credit ~$7.9B); also fixed an
  ON RRP **units bug** (`RRPONTSYD` is in billions → added a per-series ×1000 scale; was showing $4M vs
  ~$3.5B). Re-ran clean (ruff + compile + sane values). **Also retuned `check_fed_stress`** (the old
  $5B level always tripped against the mislabeled TGA) → $25B absolute + $10B WoW-surge; now silent at
  the ~$8B baseline. Detail in HANDOFF §13.

---

## Credential bring-up + Gmail token-refresh hardening (2026-06-21, uncommitted)

First time the gitignored secrets were present on the dev machine; validated the key-free paths and
hardened Gmail auth against a failure we actually hit. (Only Claude calls need the Anthropic key, so
Gmail + the scraper sessions are testable without it.)

### Credential validation
- **Substack ✅** — `substack_cookie.txt` valid; `python substack.py` fetched 3 articles. (One sub,
  polymathinvestor.com, returns 403 — likely lapsed/blocked; degrades gracefully.)
- **Gmail ❌** — the copied `token.json`'s refresh token is **rejected (`invalid_grant`)** (expired or
  revoked). Fix = a fresh OAuth consent (remove token.json → run the flow), logged in as the mailbox
  owner (jared — the digest reads his inbox as a data source). Deferred by operator.
- **Octus ⚠️** — `octus_session.json` has 5/7 cookies expired; refresh needs jared's Octus login
  (not available) → blocked.
- **13D** — `thirteen_d_session.json` structurally healthy; live probe not yet run.
- **`env.bat`** created (gitignored): `DIGEST_TO=acohen@acorninv.com`, `PYTHONUTF8=1`;
  `ANTHROPIC_API_KEY` blank (acohen getting their own key); `SUBSTACK_EMAIL`/`FRED_API_KEY` optional.

### Code — `get_gmail_service` hardening (`digest.py`)
- **Problem:** with a present-but-expired `token.json` that still has a refresh token,
  `get_gmail_service` called `creds.refresh()` with no error handling → a dead refresh token threw
  `RefreshError` (invalid_grant) and **crashed the run** (exactly what we hit).
- **Fix:** wrapped the refresh in `try/except RefreshError` → on failure, log + fall through to the
  fresh browser-consent flow (same path as a missing token). Otherwise unchanged: a good refresh
  still skips consent; a missing token still consents.
- **Tested:** new `tests/test_gmail_auth.py` (2 mocked tests) — dead refresh token falls back to
  consent (no crash) + saves the new token; good refresh skips consent. Suite now **36**; ruff clean.

### §7.2 deploy finding (recorded in HANDOFF §7.2)
Google OAuth refresh tokens for an app in **"Testing"** publishing status expire after 7 days — an
always-on server needs the app in **"production"** publishing or Gmail breaks weekly. (jared's
production digest running daily implies his app is already in production; the copied token more
likely died from being superseded/revoked.)

---

## Phase 3 — 3.4 tests + 3.2 HTML/Gmail consolidation (done)

- **Status:** ✅ 3.4 + 3.2 done + green (34 tests), ruff clean — committed `004722b`. **3.1
  (digest-core arg refactor) deferred to the credentialed phase** — its acceptance needs a
  byte-identical end-to-end baseline, which needs secrets (workflow decision 2026-06-19).

### 3.4 — pytest for the bug-prone pure functions
- New `tests/` (pytest): `test_pacer.py`, `test_reply_monitor.py`, `test_search.py`,
  `test_market_macro.py`. Covers `pacer._extract_case_info` / `_is_corporate_entity` /
  `_is_chapter_11_filing`, `reply_monitor._extract_question` / `_extract_digest_date` (subject
  path), `search._chunk_text`, and the market/macro formatters + the rate→bps conversion. 25 tests.
- `pytest==9.1.1` installed into the venv; pinned in a new `requirements-dev.txt` (kept out of the
  production `requirements.txt`). Run: `python -m pytest -q`.
- **Finding (not a bug):** the tests pin that `_extract_case_info` strips trailing punctuation, so
  "JOANN Inc." → "JOANN Inc" — intended cleanup, harmless (corp detection still matches `\bInc\b`).
- **Tested:** `python -m pytest tests/ -q` → 25 passed; ruff clean.

### 3.2 — consolidate HTML strippers + Gmail body extractors (new `html_utils.py`)
- New `html_utils.py`: `HTMLStripper` + `strip_html()` (the byte-identical stripper shared by
  `search.py` and `sec_filings.py`) and `extract_gmail_body(payload, cap=None)` (merges
  `digest._extract_email_body` [cap=50000] and `reply_monitor._extract_body` [uncapped] — the
  `cap` param reproduces the prior per-recursion truncation exactly).
- Rewired: `search.py` (`strip_html`), `sec_filings.py` (`HTMLStripper`), `digest.py`
  (`extract_gmail_body(..., cap=50000)`), `reply_monitor.py` (`extract_gmail_body` + `strip_html`,
  dropping the cross-module `from search import _strip_html`). Removed the now-unused
  `html`/`HTMLParser` imports from search/sec_filings.
- **Left intentionally divergent (NOT folded in):** `substack._HTMLStripper` / `_html_to_text`
  (different tag set, no whitespace collapse) and `substack._extract_gmail_body` (no text/html
  split — used for magic-link scraping).
- **Tested (offline):** new `tests/test_html_utils.py` (9 tests pinning the stripper + extractor,
  incl. the 50K cap) written + green **before** rewiring; full suite 34 passed; ruff clean; all
  modules import; `python sec_filings.py` runs clean (live EDGAR, no key).

---

## Cost/efficiency — A1 (cost instrumentation) done; A2 (structured outputs) paused

- **Status:** ✅ A1 code-complete + offline-tested (ruff/compile clean, unit tests pass) — committed
  `a04f892`. **A2 deferred to the credentialed phase** — see below.

### A1 — full per-run Claude cost accounting (new `cost.py`)
- Before: `digest.py` priced only the two Opus passes; memory / alerts / 13D / weekly and the
  Sonnet/Haiku ranker calls were uncounted, so the reported per-run cost understated reality.
- New `cost.py`: a module-level `record(label, model, usage)` accumulator + `cost_of()` +
  `summary()`. Added Sonnet (3/15) and Haiku (1/5) price constants to `config.py` alongside Opus.
- Instrumented all 12 call sites (digest passes ×2 + news rank + weekly; memory; alerts; octus;
  pacer; 13D; midday; reply ×2). Entry points print a per-run total: `digest.main()` at the end,
  `midday.main()` after the materiality check, `reply_monitor` per reply (reset + print).
- Measurement only — no behavior change, no API calls added.
- **Tested (offline):** `cost_of` vs known counts (2M in + 1M out Opus = $35; Sonnet 1M+1M = $18;
  Haiku = $6; unknown model → opus tier; cache read 0.1× / write 1.25×); `record`+`summary`
  aggregation across opus/sonnet/haiku with a None-usage skip; ruff + py_compile clean; all entry
  points import with `cost` wired.

### A2 — structured outputs: paused, needs the key
Getting `output_config.format` right (array-vs-object top level, `additionalProperties: false`,
nullable fields) needs iteration against the live API, and confirming **opus-4-6 even supports
structured outputs** needs a Models API call — both require credentials. So A2 can't be safely
shipped + verified offline. **Decision (2026-06-19): deferred to the credentialed phase** — when
secrets land, confirm opus-4-6 support via the Models API, iterate the schemas against the live API,
then apply + test. Tracked in HANDOFF §11.

---

## Phase 2 — Quality/cost refactors (2.2, 2.3, 2.4 done; 2.1 deferred)

- **Status:** ✅ 2.2 / 2.3 / 2.4 code-complete and **offline-tested** (ruff + py_compile clean,
  unit tests + live free-RSS runs green). **2.1 (prompt caching) dropped** by decision (2026-06-19) —
  verified counterproductive as specced (see below). Committed `d9dfd50`.

### Done
- **2.2 — `claude_utils.parse_json_response()` (new `claude_utils.py`)** — one helper that strips an
  optional ```json fence and `json.loads()` the body. Replaced the duplicated block in `digest.py`
  (`_rank_news_articles`), `octus.py` (`_rank_articles`), `alerts.py`, `memory.py`, `pacer.py`
  (`_filter_by_size`), `reply_monitor.py` (`_extract_search_queries`). Removed the now-unused
  `import json` from `digest.py` and `reply_monitor.py`. Still raises `json.JSONDecodeError`, so the
  existing try/except paths are unchanged.
- **2.3 — `feeds.py` (new)** — shared `fetch_feed` / `parse_date` / `is_recent`, used by `news.py`
  and `ratings.py` (their private copies removed). `pacer.py` / `fed_research.py` intentionally NOT
  folded in (different feed shapes). Only behavioral delta is the fetch-error log string.
- **2.4 — `search._get_model()` singleton** — module-level lazy `_model`; the long-running
  `reply_monitor` now loads the sentence-transformer once per process instead of per `search()`.

### Tested (offline, no secrets / no Claude)
- `ruff check` clean; `py_compile` of all touched + new modules.
- 2.2: `parse_json_response` unit tests — fenced / plain-fence / unfenced / whitespace / object /
  garbage / empty (garbage + empty raise `JSONDecodeError`).
- 2.3: `parse_date` / `is_recent` unit tests; `python news.py` → 119 WSJ/FT articles,
  `python ratings.py` → 8 rating actions (live free RSS, via `feeds`).
- 2.4: `_get_model()` returns the same object on the 2nd call; `_model` is None before first use.

### 2.1 (prompt caching across the two Opus passes) — NOT implemented; decision needed
Verified against the Anthropic prompt-caching docs — caching is a strict **prefix** match over
`tools → system → messages`. As specced it can't produce a cache hit and would *raise* cost:
- Pass 1 uses `system=SYSTEM_PROMPT`; pass 2 uses a different review `system` AND prepends a review
  block before the shared content. The prefix diverges at the system prompt, so pass 2 shares no
  cacheable prefix with pass 1 → 0 cache reads, while pass 1 still pays the ~1.25× cache-write
  premium = net cost increase.
- Making it actually cache needs an identical `system` + the shared content as a leading prefix in
  both passes, with per-pass instructions moved after the breakpoint. That changes pass 2's behavior
  and touches the load-bearing `SYSTEM_PROMPT` / `_assemble_digest_html` coupling (§6), so it can't
  be guaranteed output-neutral without a permissioned before/after digest comparison.
- **Decision (2026-06-19): dropped.** The naive version is a net cost increase; the cache-correct
  version would change pass 2's output and touch the §6 SYSTEM_PROMPT — not worth it. Phase 2 is
  complete with 2.2 / 2.3 / 2.4.

---

## Stage 1 — §7.1 machine de-hardcoding (location + test-recipient)

- **Status:** ✅ Code/doc changes applied and **offline-tested** (see "Tested" below). Full
  end-to-end (credentialed) run still pending — tracked as a TODO in HANDOFF §11. Committed `e7b9a6c`.

### Changes
- **`run_digest.bat` / `run_midday.bat` / `run_reply_monitor.bat`** — replaced
  `cd /d C:\Users\jared\Daily-Digest` with `cd /d "%~dp0"`, the hardcoded jared `python.exe`
  with `"%~dp0.venv\Scripts\python.exe"`, added `set PYTHONUTF8=1` (cp1252 log-crash fix) and
  `if not exist logs mkdir logs`.
- **`setup_tasks.bat`** — the three `schtasks /TR` targets now use `"%~dp0run_*.bat"`, so the
  registered tasks point at wherever the repo lives.
- **`digest.py`** — `DIGEST_RECIPIENTS` is now `DIGEST_TO`-env-driven (comma-split, stripped),
  defaulting to the production list (jared). Re-added `import os`. `midday.py` imports this, so
  the override applies there too — no midday edit needed.
- **`reply_monitor.py`** — added `acohen@acorninv.com` to the `from:` reply allow-list; reply
  recipient is now `", ".join(DIGEST_RECIPIENTS)` (imported from `digest`) so it follows `DIGEST_TO`.
- **`README.md`** — Task Scheduler section now points at the shipped `.bat`s / `setup_tasks.bat`;
  dropped the stale `SUBSTACK_PASSWORD` + Playwright-Substack instructions; documented `env.bat`
  (incl. `DIGEST_TO`) and `PYTHONUTF8`; fixed the Files list (`substack_cookie.txt`, not
  `substack_session.json`).
- **User-Agent contact** — intentionally **left as `jtramontano@acorninv.com`** in
  `sec_filings.py` / `pacer.py` / `trace_data.py` / `fund_tracking.py` (decision 2026-06-19,
  overrides HANDOFF §7.1.6 — courtesy contact for SEC/PACER admins, not a credential).

### Tested (offline, no secrets)
- `ruff check` clean; `py_compile` of digest / reply_monitor / midday.
- `DIGEST_TO`: unset → jared; `=acohen@acorninv.com` → acohen; comma+spaces stripped;
  `reply_monitor` inherits it (imported from `digest`).
- Ran `run_digest.bat` to the credential check: `%~dp0` cd, `mkdir logs`, missing `env.bat`
  non-fatal, venv-python resolves, `digest.py` fails fast at missing `credentials.json` (no
  network / no Claude). `PYTHONUTF8=1` verified — the `→` in the log is valid UTF-8 (bytes
  `E2 86 92`), no `UnicodeEncodeError`. (`run_midday.bat` / `run_reply_monitor.bat` are
  byte-identical wrappers — not separately run; `setup_tasks.bat` not run — it registers real
  scheduled tasks.)

### Still pending (operator/manual)
- Create `env.bat` with real keys + `DIGEST_TO=acohen@acorninv.com`.
- Copy the gitignored secret files (jared's `credentials.json` / `token.json` + session files).
- **Full end-to-end de-hardcoding test** (all three wrappers + `setup_tasks.bat`) — blocked until
  the above; acceptance criteria in HANDOFF §11.

---

## Phase 1 — Cost-pricing fix, model centralization, HTML escaping

- **Commit:** `f78ef45` — "Phase 1 done, tested with no secrets"
- **Status:** ✅ Code complete; verified offline (no secrets). Optional end-to-end render check
  deferred to a credentialed run.

### Code changes
- **1.1 — `config.py` (new)** — centralized constants: `OPUS_MODEL` / `SONNET_MODEL` / `HAIKU_MODEL`
  and `OPUS_PRICE_IN` (5.0) / `OPUS_PRICE_OUT` (25.0); also houses the `esc()` / `safe_href()` HTML
  helpers (used by 1.2). Wired `OPUS_MODEL` into the 5 files that hardcoded `claude-opus-4-6`
  (`digest.py`, `memory.py`, `alerts.py`, `reply_monitor.py`, `thirteen_d.py`), and replaced the
  stale `15`/`75` $/MTok literals in `digest.py`'s cost calc with `OPUS_PRICE_IN`/`OPUS_PRICE_OUT`
  (Opus 4.6 is $5/$25 — the old printout over-stated cost ~3×). Model string unchanged (opus-4-6).
- **1.2 — HTML escaping** — wrapped every interpolated scraped value + `href` in the 5 build
  functions that take free text/URLs: `octus.build_deals_table_html`, `digest.build_news_html`,
  `ratings.build_ratings_html`, `pacer.build_pacer_html`, `alerts.build_alerts_html`. Text → `esc()`,
  links → `safe_href()` (non-http(s) schemes such as `javascript:` collapse to `#`). Output is
  unchanged for normal input.

### Tests run (all green, no secrets)
- `ruff check` clean; `py_compile` all; all **25** modules import (config wiring — no circular imports).
- **1.1 unit check:** model constants resolve to opus-4-6 across all 5 files; pricing 5.0/25.0; cost
  formula replicated → $35 for 2M in + 1M out.
- **1.2 unit check:** fed `<`, `&`, `"`, and `javascript:` through `esc`/`safe_href` and all 5 build
  functions — special chars escaped, non-http(s) hrefs neutralized to `#`.

### Deferred to a credentialed run
Optional: one small permissioned end-to-end `digest.py` run to `acohen@` to confirm the assembled
email still renders. See `HANDOFF.md` §11 "Needs Testing → Phase 1."

---

## Phase 0 — Cleanup + dev-machine bring-up

- **Commit:** `1f400f6` — "Phase 0 finished, tested with no secrets"
- **Status:** ✅ Complete; validated without any secrets/keys.

### Environment (dev machine `KimCohen`)
- Installed **Python 3.12.10** (winget; system 3.14.5 left untouched — 3.14 lacked wheels for
  torch/faiss/sentence-transformers).
- Created venv at `.venv`, upgraded pip, installed all deps + `playwright install chromium`.
- Windows console UTF-8 gotcha noted: run with `PYTHONUTF8=1` (emoji / `—` in logs crash under the
  default cp1252 console / redirected logs).

### Code changes
- **0.1 `pacer.py`** — removed the dead `try: from search import search as _unused / except: pass`
  block in `_search_company_size` (a no-op "verify imports" import).
- **0.2 `market_data.py`** — removed the dead 1-week-cache `elif` branch (could never fire —
  `value_1w` is never written by `_save_cache`) and the now-orphaned `prior_cache = _load_cache()`.
- **0.3 `search.py`** — removed the duplicate `_get_model()` call inside the re-index branch (model
  already loaded earlier in `index_daily_content`).
- **0.4 `requirements.txt`** — pinned all 12 direct deps to the versions resolved on Python 3.12;
  left **PyPDF2 3.0.1** unbumped (per the Phase 3.3 caution). Added a header comment.
- **0.5 linting** — added `ruff.toml` (`select = ["E","F"]`, `line-length = 100`, `ignore = ["E501"]`,
  excludes `.venv`/archive dirs); ran `ruff check` → fixed all **28** findings:
  - **F401 unused imports:** `digest.py` (`os`, `check_fed_stress`), `search.py` (`os`, in-func
    `faiss`), `fed_balance_sheet.py` (`Path`), `treasury_auctions.py` (`Path`), `octus.py` (`time`),
    `pacer.py` (`datetime`), `substack.py` (`json`, in-func `base64`), `midday.py`
    (`fetch_recent_emails`).
  - **F841 unused locals:** `earnings.py` (`except … as e`), `fund_tracking.py` (`primary_docs`),
    `market_data.py` (`prior_cache`), `midday.py` (`today`/`day`), `sec_filings.py`
    (`accession_dashed`), `substack.py` (`r =` → kept the side-effecting `session.get`).
  - **F541 f-strings w/o placeholders:** `fdic_monitor.py`, `fund_tracking.py` (×2),
    `reply_monitor.py` (×4), `search.py`, `thirteen_d.py` (×2), `trace_data.py`.
  - Did **not** run `ruff format` — `ruff check` + fixes only, so the diff stays behavior-only.
- **0.6 `grab_session.py`** — **deleted** (dead: wrote `substack_session.json`, which nothing reads;
  the live Substack auth uses `substack_cookie.txt`). Confirmed dead across all run paths first.
- **Housekeeping** — added `.venv/` + `venv/` to `.gitignore`; removed the orphaned
  `substack_session.json` line from `.gitignore`.
- **Docs (`HANDOFF.md`)** — added the 3-tier cost model (§2), FROM-jared / TO-acohen send mechanics
  (§7.1.7), FRED deferred note (§8), reconciled §8/§10, marked Phase 0 done (§1 + §9), and added §11
  "Needs Testing." (Out-of-repo memory files were updated to match.)

### Tests run (all green, no secrets)
- `ruff check` clean; `py_compile` of every `.py`; all **24** modules import.
- **13 free fetchers** exited 0: `news`, `market_data`, `sec_filings` (pulled a live 8-K),
  `fund_tracking`, `earnings`, `treasury_auctions`, `fdic_monitor`, `trace_data`, `ratings`,
  `fed_research`; `cftc_cot` (correctly skipped — weekday); `macro_data` / `fed_balance_sheet`
  (correctly skip — no FRED key).
- `pacer` pure-function asserts: `_extract_case_info`, `_is_corporate_entity`,
  `_is_chapter_11_filing` ✓.
- `search` index round-trip on a throwaway temp archive: index → **re-index (the 0.3 branch)** →
  identical vector count → query returned a hit ✓.

### Deferred to a credentialed run
The LLM/Gmail/paid-scraper paths — see `HANDOFF.md` §11 "Needs Testing → Phase 0."
