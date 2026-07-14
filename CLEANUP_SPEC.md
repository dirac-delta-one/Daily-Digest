# Cleanup Spec — second-pass review findings

> Output of the 2026-07-14 second-pass architecture/code review (full codebase re-read;
> findings verified empirically offline — 79 duplicate chunk_ids confirmed in the live
> index, memory context measured at 39.5k chars, market_data 1-of-6 incident confirmed
> in `source_counts.json`). Operator-approved scope 2026-07-14: **Stages A–E**. The
> same day's **2026-07-31 deadline** discussion (last operator work day) produced two
> amendments, embodied in this spec and approved with it: the memory cap is a
> self-activating budget guard (behavior-neutral on day one) instead of a
> park-and-watch tripwire, and a jared-facing operations runbook is added — every
> "watch item" must become code or a runbook line before 7/31, because there is no
> watcher afterwards.
>
> **Workflow (house rules):** implementation one stage at a time on explicit go-ahead;
> `ruff` + full `pytest` green between stages (baseline **307** tests); a dated WORKLOG
> entry per completed stage; HANDOFF.md updated only when the operator confirms a phase
> done. Tests-first: the pins land before the code they protect is touched.
>
> **Cost:** $0 Claude generation anywhere in this spec. Free steps: unit tests, the
> chunk_id index rebuild, the local retrieval eval. The operator granted **standing
> permission for $0 `count_tokens` calls** (2026-07-14) — recorded here, though no item
> in this spec needs one. The only model-visible change (Stage 3.1, the Sonnet memory
> index) is validated as a **ride-along observation on the next natural run** — no
> dedicated spend.
>
> **Explicitly declined / out of scope (recorded so they aren't re-derived):**
> - **F7 weekly-wrap token diet** (~$35/yr EV) — deferred; quantify via free
>   `count_tokens` first, and only ever bundle the change with some other permissioned
>   Friday ride-along. Not in this spec.
> - **F8 alert-eval cross-variant prompt cache** (~$25/yr EV) — declined; requires
>   restructuring a §6-adjacent prompt + permissioned validation. EV doesn't clear the bar.
> - **F9 `gmail_utils.py` extraction, F10 news-ranking hoist, F11 FULL/TEAM variant
>   loop** — declined as churn; explicitness is valued (§2) and everything is test-pinned.
> - **Type-annotation pass, CI** — declined (solo tool, excellent docstrings, local
>   stage gates). A `check.bat` QoL lands in Stage 4 instead.
> - **F22 HANDOFF consolidation** — approved but as a SEPARATE later docs pass, not here.
> - Everything in HANDOFF §6 (do-NOT-fix), §14.F (parked rerank/hybrid/substrate), and
>   NEXT_STEPS §2.2's rejected refactors — untouched; the review found no new evidence
>   against any of them.
>
> **Timeline context:** the operator's last work day is **2026-07-31**. This cleanup is
> sized for ~1–2 sessions, after which the **§7.2 server deploy should happen as early
> as possible** so the system gets maximum unattended soak time while a fixer still
> exists (the accrual-week precedent: live operation surfaced ~8 failure modes nothing
> else did). No target deploy date exists yet — choosing one is the first post-cleanup
> decision.

Finding IDs (F1–F22) reference the 2026-07-14 review report (in the session transcript;
key facts restated inline below so this spec stands alone).

---

## Stage 1 — Test pins first (additive only; ground truth before main() is touched)

### 1.1 Mocked `main()` wiring/order test **(F15)**

*What:* `digest.main()`'s unattended-critical ordering invariants were validated live but
have no regression net: `pacer.commit_seen()` fires only AFTER the last send (F1a-4);
`digest_sent_at.txt` (the O2 watchdog marker) is written AFTER the last send;
`update_memory` receives the TEAM html when the team variant exists (the substack-cleanse
invariant) and the FULL html otherwise; O3 counts are recorded exactly once; the team
send happens only when `TEAM_RECIPIENTS` is non-empty.
*Where:* new `tests/test_digest_main.py`.
*Fix:* one integration-style test module driving the real `main()` with everything
stubbed: fake Anthropic client (the `test_team_digest._capture_calls` pattern),
`MagicMock` Gmail service via monkeypatched `get_gmail_service`, `_fetch_all_sources` /
`fetch_recent_emails` / `fetch_substack_articles` / `fetch_wiltw` stubbed,
`summarize_with_claude` → canned `("<div>…</div>", "src")`, `evaluate_alerts` /
`build_news_html` / `index_daily_content` stubbed, `archive_daily_content` → tmp dir,
`_is_friday` → False. A shared call-log list records event order
(`send`, `send_team`, `commit_seen`, `marker`, `update_memory(html)`), asserted for both
the team-active and team-empty configurations. This test is written FIRST because
Stage 2.1 modifies `main()`.
*Verify:* `pytest` green; deliberately break the ordering locally (move `commit_seen`
before send) and confirm the test catches it, then restore.
*Priority:* Medium. *Effort:* Medium.

### 1.2 Midday result-parsing pins **(F16)**

*What:* `midday.py` has no dedicated test file — its ONE existing pin (recipient
combining) lives in `test_team_digest.py` — and its result-parsing block
(`midday.py:239–255`: the `NO_ALERT` check, the `"="*10` separator split, the
subject-line extraction, the strip-to-`<div`) is entirely untested, exactly the brittle
string logic the suite pins everywhere else.
*Where:* `midday.main` (parse block); new `tests/test_midday.py`.
*Fix:* the block is inline in `main()` and untestable as-is — extract a pure helper
`_parse_alert_result(result) -> (subject_desc, alert_html)` (mechanical move, no logic
change), then pin: `NO_ALERT` passthrough, separator split with/without preamble,
subject taken from the last pre-separator line, missing-separator fallback (first 60
chars), preamble stripped to first `<div`.
*Verify:* ~5 new tests green; `python -c "import midday"` clean.
*Priority:* Low. *Effort:* Small.

**Stage 1 verification plan:** `ruff` + full `pytest` green (~+8–10 tests). Purely
additive except the mechanical midday extraction. No paid steps.

---

## Stage 2 — Correctness guards

### 2.1 Code-enforce the post-activation TEAM leak guard **(F1 — the priority item)**

*What:* the TEAM/Substack privacy boundary currently depends entirely on the
`DIGEST_TO_TEAM` env var being present. On a server run where it's missing (fresh
install, regenerated env.bat): only the FULL digest generates → `search._chunks_for_date`
falls back to `digest.html` and **indexes Substack-laden prose** (post-activation digest
chunks are NOT excluded for team askers — `exclude_digest_before` only excludes dates
*before* activation) → AND `update_memory(final_html)` re-contaminates the cleansed
shared store, leaking Substack storylines into future TEAM digests via memory context.
The existing `main()` warning covers only the reverse misconfiguration. HANDOFF carries
this as a deploy note; unattended operation needs it as code (the F1a pattern:
runbook-note → guard).
*Where:* `digest.py` `main()` (~line 1355, the `team_active` block; ~line 1529, the
memory feed); `search.py` `_chunks_for_date` (~line 439, the digest-file fallback).
*Fix (three parts, one commit):*
1. `main()`: define the misconfiguration once —
   `TEAM_ACTIVATION_DATE and today >= TEAM_ACTIVATION_DATE and not TEAM_RECIPIENTS` —
   print a loud warning AND append a deterministic alert to the digest alert box
   (`{"name": "Team config missing", "detail": "...DIGEST_TO_TEAM unset post-activation;
   digest chunks not indexed, memory not updated...", "source": "config guard"}`), the
   same channel as Fed-stress/O3 so the cause is visible in the email itself.
2. `search._chunks_for_date`: skip `digest.html` when `config.TEAM_ACTIVATION_DATE` is
   set, `date_str >= TEAM_ACTIVATION_DATE`, and `digest_team.html` is absent (~5 lines;
   raw sources still index, so retrieval degrades gracefully instead of leaking).
   `search` gains a `from config import TEAM_ACTIVATION_DATE` (no cycle: config imports
   only stdlib).
3. `main()`: on the same condition, skip `update_memory(...)` with a loud message (one
   missed memory day beats store re-contamination — the cleanse was a one-time manual
   operation that cannot self-heal).
4. **Escape hatch — deliberate deactivation is not misconfiguration:** if the team
   variant is ever intentionally retired, `config.TEAM_ACTIVATION_DATE` must be set back
   to `None` — otherwise this guard keeps digest chunks un-indexed and the shared memory
   frozen forever, with only the daily alert as a clue. Add that instruction to the
   `TEAM_ACTIVATION_DATE` config comment as part of this item.
*Verify:* unit tests — `_chunks_for_date` fixture days: post-activation without team
file → zero digest-type chunks; with team file → team chunks (existing test); date
before activation → `digest.html` indexed as today. `main()` guard via the Stage-1.1
harness: alert appended, `update_memory` not called, run completes. Existing 307 stay
green (all archived days either predate activation or have team files).
*Priority:* **High.** *Effort:* Small. *Risk:* none of §6; no Claude run.

### 2.2 chunk_id uniqueness + rebuild + eval re-baseline **(F2 — confirmed live defect)**

*What:* CONFIRMED on the live index: **79 duplicate chunk_ids covering 208 chunks.**
Substack ids (`{date}_substack_{author}_{i:04d}`) collide when one author posts 2+
articles a day (`MAX_ARTICLES_PER_PUB = 3`; e.g. `2026-06-30_substack_Paul_Krugman_0000`
×2); filing ids (`{date}_filing_{ticker}_{form}_{i:04d}`) collide when a ticker files
the same form twice a day (130 duplicate filing chunks). The reply bot's
`_search_multiple._collect` dedups results by chunk_id, so genuinely distinct chunks are
**silently dropped from answer context**.
*Where:* `search.py` `_chunks_for_date` — substack loop (~line 490: `for art in
articles:`) and filings loop (~line 518).
*Fix:* enumerate both outer loops and include the ordinal in the id:
`f"{date_str}_substack_{name}_{a:02d}_{i:04d}"` and
`f"{date_str}_filing_{ticker}_{form_type}_{j:02d}_{i:04d}"`. Ids are regenerated at
index time and persist nowhere across runs (verified: the only consumers are in-process).
Then, per the Stage-2.6 house recipe: (1) back up `archive/index.faiss` +
`archive/chunk_metadata.json` (the rollback); (2) full `python search.py --rebuild`
(free, local); (3) `python tools/eval_retrieval.py --save post_cleanup_ids` — **gate:
metrics ≥ the current baseline (hit@1 0.862 / hit@3 0.966 / hit@5 1.0 / MRR 0.917,
zero misses) or the delta goes to the operator before anything is kept**; (4) a
uniqueness pin test (fixture day with two same-author articles + two same-ticker/form
filings → `len(ids) == len(set(ids))`).
*Verify:* steps above + `ruff` + full `pytest`.
*Priority:* Medium-High. *Effort:* Small (the work is the verification discipline).
*Risk:* eval is near-saturated (F17) so expect "identical" — that is the no-regression
gate working, not evidence of improvement.

### 2.3 Reply-bot allow-list derived from config **(F3)**

*What:* `check_for_replies` hardcodes three `from:` addresses in the Gmail query string.
Adding a team recipient requires remembering to edit code (TEAM_DIGEST_SPEC Stage 5
carries exactly that reminder); forgetting = the new teammate's replies are silently
ignored forever.
*Where:* `reply_monitor.py:239–245`.
*Fix:* build the clause at call time from
`sorted({*FULL_ACCESS_SENDERS, *DIGEST_RECIPIENTS, *TEAM_RECIPIENTS})` (lowercased,
deduped, sorted for determinism). **Operator directive 2026-07-14:**
`jaredtramontano@gmail.com` is REMOVED from `FULL_ACCESS_SENDERS` in the same commit —
it was never in the hardcoded query (replies from it have always been ignored), and the
operator chose to keep it unanswerable rather than let the config-driven union widen
access. **The bot is removed from `FULL_ACCESS_SENDERS` too (operator question,
2026-07-14 — the same 2026-06-29 slot-swap artifact, with no function: internal/tool
calls already get full access via `asker=None`, the bot never authors replies, and
after 2.5 it no longer even receives digests).** Full access is then
`jtramontano@acorninv.com` alone, and the answerable set collapses to exactly the
digest recipients (full list + team list): anyone who receives a digest can reply to
it; the answer's TIER (Substack-inclusive vs team) follows `FULL_ACCESS_SENDERS`.
jared's gmail deliberately STAYS in `FORWARDER_ADDRESSES` — that is a different
mechanism (forwarded-sender attribution in the digest, e.g. the Substack OTP
auto-forward chain), not reply access. **One remaining behavior change, called out for sign-off:** the list
becomes EXACTLY config-driven — acohen's access stops being hardcoded and depends on
membership in `DIGEST_TO` / `DIGEST_TO_TEAM` / `FULL_ACCESS_SENDERS` (today: covered
via `DIGEST_TO_TEAM`).
*Verify:* pin tests with `DIGEST_RECIPIENTS` / `TEAM_RECIPIENTS` monkeypatched (env.bat
is NOT loaded under pytest, so tests must not rely on the env-derived lists): the query
is built from the union, a team entry appears, every `FULL_ACCESS_SENDERS` member
appears. Update the existing tier test (`test_is_full_access_tiers`): the bot and
jared's gmail become team-tier; `asker=None` stays full; jtramontano stays full.
*Priority:* Medium. *Effort:* Small.

### 2.4 Expected-count floors for fixed-cardinality sources **(F4 — observed live)**

*What:* the 2026-07-14 run returned **1 of 6** market tickers (partial `yf.download`
failure; empty series are skipped silently) — a corrupted Market Snapshot table in the
sent email, invisible to O3 because the zero-streak rule only sees total outages. For
volume-variable sources that conservatism is correct; for fixed-cardinality sources the
expected count is known exactly.
*Where:* `content_monitor.py` (`check_degradation`); counts already recorded by
`digest.main`.
*Fix:* `EXPECTED_MIN = {"market_data": 6, "macro_data": 12, "fed_bs": 6}`; a second
check with the same streak shape: signal when a listed source has been below its floor
for `STREAK` consecutive runs having previously met it (guards against a config change
legitimately lowering cardinality). Same signal channel (digest alert box). Do NOT
extend to volume-variable sources.
*Verify:* unit tests in the `test_content_monitor.py` style: 6,6,6,1,1,1 → fires;
6,1,6,1 → no; never-met-floor → no; the zero rule and the floor rule don't
double-signal for the same all-zero streak.
*Priority:* Medium. *Effort:* Small.

### 2.5 Self-ingestion guard — drop the bot from recipient defaults + filter self artifacts from the inbox fetch **(new 2026-07-14, found answering "why is the bot a recipient?")**

*What:* the production `DIGEST_RECIPIENTS` default (`digest.py:92`) and `run_alert`'s
independent copy (`run_alert.py:39`) both include `acorn.research.bot@gmail.com`. That
is a historical slot-swap — on 2026-06-29 the bot replaced jared's personal gmail 1:1
in the recipient list — with **no identified function today**: the digest is already in
the bot's Sent mail and on disk (`digests/`, `archive/`), and reply threading needs no
inbox copy. Because the digest reads the BOT'S OWN INBOX as a source (`in:inbox`, last
24h, no sender/subject filter), the self-send creates a latent loop that has **never
executed** — every credentialed run so far used `DIGEST_TO=acohen`, which removes the
bot from the list. At server deploy (production defaults, `DIGEST_TO` unset):
yesterday's ~8:05 digest, the 1 PM midday alert, and any failure alerts land in the bot
inbox INSIDE the next 8:00 run's 24-hour window → ingested as "source emails" →
(a) recursive self-summarization (Opus reads yesterday's digest as inbox research), and
(b) the FULL digest re-enters the archive and search index as `source_type="email"` —
which the team-asker exclusions do NOT filter (they exclude `substack` and `digest`
types) — **a second Substack leak vector**. Empirical proof of the pathway:
`archive/2026-07-14/emails.json` already contains two of acohen's digest REPLIES
ingested as source emails.
*Where:* `digest.py:92` + `run_alert.py:39` (defaults); `digest.fetch_recent_emails` +
`midday._fetch_new_emails` (fetch-side filter).
*Fix:*
1. Drop the bot from both production defaults (digest → jtramontano + team list;
   failure alerts → jtramontano). **✅ Sign-off received (operator, 2026-07-14), as a
   general policy: RECIPIENTS MUST BE @acorninv.com ADDRESSES ONLY — nothing else on
   the receiving side.** (jared's gmail already left the recipient list 2026-06-29;
   the bot was the last non-acorninv recipient.) Encode the policy: a pin test
   asserting both production defaults contain only `@acorninv.com` addresses, and the
   policy stated in the config comment next to the `DIGEST_RECIPIENTS` default. Bonus
   alignment: every production recipient is then covered by IT's org-wide Outlook
   Abnormal allowlist (§7.2-7), with no non-Outlook re-verification case left.
2. Belt-and-suspenders, code-side skip in both inbox fetchers: drop messages whose
   sender is the bot OR whose subject contains `DIGEST_SUBJECT_PREFIX` (covers
   self-sent digests, humans' replies-to-digests — already observed ingested — and the
   `[FULL]` variants; stays robust even if the bot is ever re-added as a recipient).
*Verify:* unit tests on the skip predicate (bot sender / digest-subject reply /
`[FULL]` variant dropped; normal mail, forwarded research, and OTP mail pass);
recipient defaults pinned. No live run needed.
*Priority:* High (deploy-blocking-adjacent — same leak family as 2.1).
*Effort:* Small.

**Stage 2 verification plan:** `ruff` + full `pytest` green (~+14 tests); the 2.2
rebuild + eval gate; free `python market_data.py` smoke. No paid steps.

---

## Stage 3 — Memory bounds (the 7/31-amended F6; code instead of a watcher)

Context (measured 2026-07-14): `get_memory_context()` = **39,491 chars (~10k tokens)**
into the Opus digest prompt daily (roughly doubled since the 7/13 cleanse; 51 active
stories); `get_substack_memory_context()` = 25,060 chars; the Sonnet delta call re-sends
a **17,455-char story index** — today ~98% of that is ACTIVE-story lines (the resolved
section is 4 lines / ~278 chars), so the observed input growth (10,344 → 11,816 tokens)
is active-story growth; the resolved tail is the part that grows forever once aging
starts resolving stories. The store
only accumulates: the 30-day age-out cannot fire before ~7/30 and is reset by updates,
and multi-run validation days inflated the slope. Direct dollar cost is small (cache
absorbs most of it); the real issues are unbounded growth on an unwatched server and
attention dilution (a 10k-token memory wall ahead of the day's actual sources).

### 3.1 Resolved stories → ids-only in the Sonnet index **(the §14.F.F3-4 specified fix)**

*What:* `_story_index_for_prompt` renders `"  {id} — {topic}"` per resolved story,
forever. §14.F specified the fix when the watch triggered; the trigger fired (memory
pass input 10,344 → 11,816 tokens, 7/09 → 7/14).
*Where:* `memory.py` `_story_index_for_prompt` (~line 300).
*Fix:* resolved section renders ids only (ids are topic slugs — `hormuz-escalation` —
so recognizability survives). This is the ONE model-visible change in the spec (Sonnet
delta input). **Honest sizing:** it saves ~nothing today (4 resolved stories, ~278
chars) — its value is the FOREVER-BOUND on the resolved tail, which only starts growing
when the 30-day aging begins resolving stories (~August, exactly when no one is
watching). The ride-along therefore checks recreation risk, not savings.
*Verify:* unit test on the rendered text; **ride-along** on the next natural run: watch
the delta for resolved-story re-creation (`new_stories` re-minting a resolved topic).
Revert = restore the topic suffix, one line.
*Priority:* Medium. *Effort:* Small. *Risk:* model-visible to Sonnet only; ride-along.

### 3.2 Self-activating budget guard on the rendered contexts

*What:* replaces the review's park-and-watch tripwire, which the 7/31 deadline broke
(the decision point was mid-August; the first age-out data arrives literally on the
operator's last day, and the tripwire has no owner afterwards). Instead: a deterministic
budget that is **behavior-neutral today** and bounds growth forever.
*Where:* `memory.py` `get_memory_context` / `get_substack_memory_context` — which are
near-duplicate renderers; consolidate into one `_render_story_context(memory,
header_lines, footer)` helper as part of this item (the existing `test_memory.py`
format pins keep it byte-identical).
*Fix:* **SELECT by recency, RENDER in store order** — two distinct steps, deliberately:
choose the most-recently-updated active stories up to
`MEMORY_CONTEXT_MAX_STORIES = 60` / `MEMORY_CONTEXT_MAX_CHARS = 45_000`, then render the
selected stories in their ORIGINAL store order. (Rendering in recency order — the naive
reading — would reorder the context even while under budget: NOT byte-identical, and a
model-visible position change. Selection must also be deterministic — stable sort with
store-order tie-break — because the TEAM and FULL prompts each call this function and
their outputs must match byte-for-byte or the cross-variant prompt cache silently stops
engaging.) Budgets sit above today's 51 stories / 39.5k chars so day-one output is
**byte-identical — pinned by test**; **re-measure the live store at implementation
time** (it grows with every run) and raise the constants if it has crossed them, so the
neutrality claim is true on landing day. When the store eventually outgrows the budget,
the stalest-updated stories drop first — exactly the ones the 30-day age-out would
resolve days later anyway. Constants + a rationale comment live in `memory.py` next to
`STALE_DAYS`.
*Verify:* pin tests — under-budget store renders every story byte-identically
(fixture mirroring today's shape); over-budget fixture drops stalest-first, keeps
header/footer/format intact; substack renderer same behavior via the shared helper;
determinism pinned (two consecutive calls → identical output — the cross-variant
cache prerequisite).
*Priority:* Medium-High (it is the no-watcher guarantee). *Effort:* Small-Medium.
*Risk:* none on day one by construction.

### 3.3 Per-run size log line

*What:* growth must be visible in every digest log without archaeology (and it makes
jared's runbook line "if the digest looks thin, check this number" possible).
*Where:* `memory.py` `get_memory_context` (covers both callers).
*Fix:* `print(f"  Memory context: {len(text):,} chars / {n_active} active stories")`
(appears once per variant per run — acceptable).
*Verify:* rides on 3.2's tests (assert the line prints via capsys).
*Priority:* Low. *Effort:* Trivial.

**Stage 3 verification plan:** `ruff` + full `pytest` green (~+6 tests); 3.1's
ride-along observation noted in WORKLOG after the next natural run. No dedicated spend.

---

## Stage 4 — Small cleanups

### 4.1 Lazy BM25 build **(F12)**

*What:* `_get_search_state` tokenizes every chunk and builds `BM25Okapi` on every state
reload, but hybrid retrieval lost its eval twice and is PARKED PERMANENTLY (§14.F) — a
linearly-growing cost (~1s + RAM at 6k chunks, worse per F13's growth curve) for a path
that never runs.
*Where:* `search.py` `_get_search_state` (~line 404).
*Fix:* state carries `bm25=None`; a `_get_bm25()` builds on first `hybrid=True` call and
caches against the same file signature. The param-gated mechanism stays fully intact per
§14.F — this changes WHEN it's built, not whether it exists.
*Verify:* existing cache/BM25 tests updated (state reload asserts `bm25 is None`; a
hybrid call builds and caches it); eval harness `--hybrid` still runs.
*Priority:* Low. *Effort:* Small.

### 4.2 Substack full-text count into O3 **(F5b)**

*What:* the 9 custom-domain pubs (JBI, PETITION, HYL, creditcrunch, privatedebtnews,
techinvestments, YAVB, pari-passu, semianalysis) never receive the auth cookie
(`domain=".substack.com"`) — their full paid bodies arrive only via Substack's
unauthenticated per-post API, the same leak that masked the 2026-07-13 dead-cookie
incident. If Substack closes it, they silently degrade to previews: visible as
`[preview only…]` markers in the digest text, but nothing alerts.
*Where:* `digest.py` `main()` (the O3 counts dict, ~line 1412).
*Fix:* record `"substack_fulltext"` — articles whose text carries neither the
`[preview only…]` marker nor the `[Paid-only post…]` failure string — alongside the
existing `substack` total. The existing zero-streak
rule then fires if full-text access collapses entirely. **Honest limitation, accepted:**
a partial degradation (custom domains preview, substack domains fine) lands above zero
and stays invisible to O3 — the in-digest preview markers remain the mitigation for that
case (documented in Stage 5.3).
*Verify:* unit test on the counts construction; `test_content_monitor` untouched.
*Priority:* Medium-Low. *Effort:* Small.

### 4.3 Archive the substack memory snapshot **(F21)**

*What:* `archive.py` snapshots `memory.json` into each day dir (corruption-recovery
history) but not `substack_memory.json` — the jared-personal store has no history
anywhere until O4 backups exist.
*Where:* `archive.py` (~line 124).
*Fix:* mirror the existing snapshot block for `substack_memory.json` →
`archive/<date>/substack_memory.json`.
*Verify:* extend `tests/test_archive.py` (+1).
*Priority:* Low. *Effort:* Trivial.

### 4.4 Tooling nits **(F19 + check.bat)**

*What:* `.gitignore` carries a stale `test_send.py` entry (file long gone); the
stage-gate commands (`ruff check .` + `pytest -q`) are typed by hand every session.
*Fix:* drop the stale line; add `check.bat` (`ruff check . && pytest -q` via the venv
executables, `PYTHONUTF8=1`).
*Verify:* run `check.bat` → both gates green, exit 0; nonzero on a forced failure.
*Priority:* Low. *Effort:* Trivial.

### 4.5 Vectorized subset scan **(F13's cheap half)**

*What:* the restricted-search path (`_search_vectors` with `allowed_ids` — every
reply-bot phase, because `exclude_digest_date` yields a nearly-full id list) reconstructs
vectors in a per-id Python loop. Fine at 6k vectors; it is the first thing that degrades
on F13's growth curve (index measured at 6,067 vectors / 9 days, ~600–1,500 chunks/day
since the body-extract change → the "~100k revisit ceiling" arrives in ~3–8 months).
*Where:* `search.py` `_search_vectors` (~line 899).
*Fix:* `vecs = index.reconstruct_batch(np.asarray(allowed_ids, dtype=np.int64))`
(faiss-cpu 1.14.3 supports it), keeping the per-id loop as an `AttributeError` fallback.
Exactness is already pinned by the existing subset-search tests, which validate the swap
for free.
*Verify:* existing `test_search.py` subset tests green unchanged (they assert exact
dot-product scores); free `tools/eval_retrieval.py` spot run — metrics identical.
*Priority:* Low-Medium. *Effort:* Small.

**Stage 4 verification plan:** `ruff` + full `pytest` green (~+3 tests); free eval spot
run for 4.5. No paid steps.

---

## Stage 5 — Docs & deploy readiness (docs-only; no code)

### 5.1 Server-cutover checklist **(F20 — the highest-priority docs gap)**

*What:* NEXT_STEPS F1 has install steps but no CUTOVER step. Until jared's PC is
decommissioned, two production instances poll the same bot inbox: recipients get double
digests, and two reply daemons race on the same unread reply (`_mark_as_read` is not
atomic across processes — the exact race that kept the reply monitor off the dev machine).
*Where:* `NEXT_STEPS_SPEC.md` §3.F1 (the F1 deliverable was always "a checklist section
appended to this spec when the work starts" — this is that section).
*Fix:* append the deploy+cutover checklist: pre-deploy (secrets to copy: production
`token.json`, `credentials.json`, fresh `substack_cookie.txt`, `thirteen_d_session.json`,
`memory.json` + `substack_memory.json` + `wiltw_cache.json` + `pacer_seen.json` +
`source_counts.json`, the `archive/` tree + FAISS index; env.bat with ALL vars incl.
`DIGEST_TO_TEAM` + `SUBSTACK_EMAIL`; do NOT copy `credentials_JARED.json`); on-box
(venv, `setup_tasks.ps1` as admin, headless Playwright check, the 13D rename-session
skip drill, one manual green run); **cutover** (disable jared's machine's scheduled
tasks + his reply monitor — coordinate a same-day switch; exactly ONE reply daemon
anywhere; recipients to production — **@acorninv.com only**, operator policy
2026-07-14; confirm the first unattended server run end-to-end);
post (O4 backups incl. the state files above; confirm O2 watchdog fires on a simulated
miss).
*Priority:* Medium-High. *Effort:* Small.

### 5.2 `OPERATIONS.md` — the jared-facing runbook (new file, ~1 page)

*What:* after 2026-07-31 the person receiving failure alerts is jared, who has no code
context; HANDOFF is written for a maintainer. Every latent manual intervention needs a
recipe he can follow.
*Fix:* one page, plain language: what each email means (🚨 run FAILED / 🚨 digest
MISSING / red in-digest ALERTS incl. "Source degradation" and the new "Team config
missing"); the two manual recoveries (13D re-login: `python thirteen_d.py --login` on
the server, expected cadence "whenever WILTW goes missing for 2+ weeks"; Substack manual
cookie paste into `substack_cookie.txt` if auto-renewal ever fails); API credit — where
to check, expected burn (~$45–50/month at dual-variant rates), what happens at $0
(digest stops, failure alerts still send); how to restart tasks
(`Get-ScheduledTask -TaskPath "\DailyDigest\"`); where the data lives (archive/,
digests/, logs/).
*Priority:* Medium-High. *Effort:* Small.

### 5.3 HANDOFF/spec reconciliation (at phase close, on operator confirmation)

*What/Fix:* fold into the phase-close HANDOFF update: (a) §14.F.F3-4 memory-growth
watch item → "bounded in code" (Stage 3), with the measured numbers; (b) a §14 entry
for the **F13 index-growth plan**: the measured slope, the ~3–8-month ceiling estimate,
the escalation ladder (4.5's batch reconstruct → date-windowed retrieval default →
prune-and-archive old days → IVF last), and a concrete tripwire ("revisit at ~30–50k
vectors or when reply latency is felt") — plus the same line in OPERATIONS.md so the
post-7/31 owner sees it; (c) §5/§13 note for **F5a**: custom-domain Substack pubs are
leak-dependent (cookie scoped to `.substack.com`; preview markers + the 4.2 count are
the mitigations); (d) record this spec's declined items in §14 (F7 deferred with the
standing $0-count_tokens permission, F8/F9/F10/F11 declined, F22 → separate pass);
(e) deploy hygiene notes (F14): `credentials_JARED.json` stays on the dev machine;
tidy root-level `*.bak` / `memory_v1_backup.json` / `*_prestage5.bak` into a local
folder at deploy.
*Priority:* Medium. *Effort:* Small.

---

## Sequencing summary

| Order | Stage | Items | Output change? |
|---|---|---|---|
| 1 | 1. Test pins | main() ordering harness (F15); midday parse extraction + pins (F16) | none (one mechanical extraction) |
| 2 | 2. Correctness guards | TEAM leak guard (F1); chunk_id fix + rebuild + eval gate (F2); allow-list from config + jared-gmail removal (F3); count floors (F4); self-ingestion guard (2.5) | guard paths; production defaults lose the bot as recipient (2.5, approved — @acorninv.com-only policy) |
| 3 | 3. Memory bounds | resolved→ids-only (3.1, ride-along); self-activating budget guard (3.2, byte-identical today); size log (3.3) | 3.1 visible to Sonnet only |
| 4 | 4. Small cleanups | lazy BM25 (F12); substack_fulltext count (F5b); substack-memory snapshot (F21); gitignore + check.bat (F19); batch reconstruct (F13a) | none |
| 5 | 5. Docs/deploy | cutover checklist (F20); OPERATIONS.md; HANDOFF reconciliation (F13 plan, F5a, F14, declined items) | docs only |
| — | *Phase close → operator confirms → HANDOFF update (5.3) → then pick the deploy date* | | |

**Budget note:** $0 of API credit is needed by this spec. Test count grows from **307**
to roughly **~330–340**. The single ride-along observation (3.1) attaches to the next
natural run's normal spend.

**The clock:** last operator day **2026-07-31**. Target: cleanup complete in ~1–2
sessions → §7.2 deploy immediately after (date TBD — decide at cleanup close) →
maximum unattended soak with the operator still available → final fixes + handoff in
the last days of July.
