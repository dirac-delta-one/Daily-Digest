# Next Steps — Roadmap Spec

> Forward roadmap for the whole project: the post-accrual-week checkpoint procedure, the three
> operator-requested refactor tracks, and fresh suggestions. Companion to `HANDOFF.md` (overall
> state), `WORKLOG.md` (running log), and `MEMORY_REFACTOR_SPEC.md` (**which remains the source
> of truth for the memory track** — this spec only sequences it). Written 2026-07-02.
>
> **Operator decisions embedded here (2026-07-02):** "general efficiency" = all three flavors
> (runtime + code simplicity + operational); after the checkpoint, **the memory refactor
> finishes first, then the §7.2 server deploy**.

## Track status

| Track | State |
|---|---|
| §1 Checkpoint (post-accrual-week decision session) | ✅ RUN 2026-07-09 — week 6/6 green; rerank + hybrid flips REJECTED on the 26-question eval (default won every metric); 3b SKIPPED; Sonnet watch CLOSED (stays); runs stopped (task disabled, operator decision); 3.3 trigger met at the margin (10 unique PDFs: 8 broker + 2 WILTW). Token swap still pending (before 7/14). Full detail in WORKLOG |
| §2.1 Memory layer (Stages 4–5 + flips) | ✅ **DONE 2026-07-09** — all stages complete (Stage 4 live-validated $0.12; Stage 5 delta-replay-validated $0.098: 64% cheaper than v1's same-day $0.274, zero story loss; **rerank + hybrid parked permanently** after the failed retest); see `MEMORY_REFACTOR_SPEC.md` |
| §2.2 General efficiency (E/S/O items) | ⬜ specced here; O2 allowed during accrual week, rest after checkpoint |
| §2.3 Cost reduction | ✅ CLOSED (audit below; residual savings ride along with the memory track) |
| §3.F1 Server-deploy readiness (§7.2) | ⬜ queued after memory track; checklist pre-work can start anytime |
| §3.F2 PDF-extraction review (3.3) | ⬜ data-gated — runnable at ~8–10 archived inbox PDFs |

---

## 1. The checkpoint — what to do based on the accrual week's outcome

**Expected state going in:** ~6 archived days (6/30, 7/2, 7/6–7/9), ~2.5–3k FAISS vectors, 6
daily Sonnet memory updates in `memory.json`, a small inbox-PDF corpus, ~$5–6 of API credit left.

**Code freeze during the accrual week (7/6–7/9):** no changes to the daily-run path
(`digest.py`, `search.py` indexing, the fetchers) so the week's data comes from one consistent
code version. Allowed: spec/checklist drafting, golden-set questions, and additive off-path
work (§2.2 O2 — the watchdog is a new task + new alert mode, it touches no run-path code).

### Ordered checkpoint procedure

0. **Week health review.** Did all 4 scheduled runs fire (digest emails or failure alerts each
   day)? Scan `logs/digest.log` for silent per-source degradation (Substack cookie, 13D
   session, sections at zero). Total the week's cost (`cost.py` prints in the log) against the
   remaining budget.
1. **Grow the golden set** (`tools/eval_golden.json`): ~3–5 questions per new day, and add the
   first **cross-day evolution questions** ("how did the Wynn story develop across the week?")
   — the query class a 1-day archive could never test and the whole point of accruing.
2. **Re-run the eval matrix:** `tools/eval_retrieval.py` in all four modes — default,
   `--rerank`, `--hybrid`, `--hybrid --rerank` — with `--save` snapshots.
3. **Apply the pre-committed decision gates** (written down now so the decisions aren't
   rationalized later):
   - **Rerank flip** (reply bot passes `rerank=True` in `_search_multiple`): flip if rerank ≥
     default on hit@3 AND MRR, with no new misses. Judge digest-chunk artifacts with Stage 4's
     same-day-digest exclusion in mind — the flip may land *as part of* Stage 4 rather than
     standalone.
   - **Hybrid flip** (`hybrid=True` default): flip if hybrid ≥ default overall AND it wins at
     least one exact-token query that default misses.
   - **If the eval still can't discriminate:** either extend accrual one more week (~$5–7) or
     flip on mechanism-superiority grounds — record whichever call is made and why.
   - **Stage 3b (embedder swap / re-chunking):** pursue only if Stages 1+2 leave measurable
     headroom (misses that a stronger bi-encoder plausibly fixes). Expected outcome: skip.
   - **Memory→Sonnet watch verdict** (open since 2026-07-01): review 6 days of story retention
     in `memory.json` — stories dropped without being resolved? Revert `memory.CLAUDE_MODEL`
     to `OPUS_MODEL` if there's drift; close the watch if clean.
   - **Extend-or-stop the `DailyDigest\MorningDigest` task** (it recurs Mon–Thu weekly until
     deleted): if the memory track continues, keep accruing (consider adding FRI) — which
     means a **credit top-up decision** (each week ≈ $5–7; console.anthropic.com is the
     authoritative balance).
   - **OAuth token swap (added 2026-07-07 — HARD DEADLINE Tue 7/14):** the 7-day Testing-mode
     token death fired live on 7/7 (§7.2's top-risk item, confirmed). Operator publishes the
     bot's OAuth app to "production" (console.cloud.google.com as the bot → OAuth consent
     screen → Publish app) any time before the checkpoint; AT the checkpoint (after Thursday's
     run): delete `token.json`, one fresh consent as the bot → durable production token.
     Without both halves, the 7/14 run hangs on a browser consent.
   - **3.3 trigger check:** count `archive/*/pdfs/` inbox PDFs; at ~8–10, §3.F2 is runnable.
4. **Build Stage 4** (per `MEMORY_REFACTOR_SPEC.md`): query understanding → the already-live
   `entity_filter`/`date_from`/`date_to` search params, MMR/dedup in `_search_multiple`, and
   same-day digest-chunk exclusion in the reply path (the digest is already separate context).
   Validate offline against the grown eval set + **one permissioned reply run (~$0.20)**.

**Contingencies:** ≥4 archived days is enough to proceed — missed days are just missed data,
not blockers. A machine-asleep/logged-out miss is a §7.2 lesson to record (it's exactly the
failure mode the dedicated server eliminates).

---

## 2. Refactor tracks

### 2.1 Memory layer — IN PROGRESS (source of truth: `MEMORY_REFACTOR_SPEC.md`)

Sequencing only (details live in that spec): **flips** (data-gated, §1 above) → **Stage 4**
(built at the checkpoint) → **Stage 5** — the memory convergence, now designable against a
real week of `memory.json` daily evolution instead of a single snapshot. Stage 5 reminders:
incremental append-not-rewrite story store, queryable timeline, reply-bot router; the digest's
`get_memory_context()` contract must keep working; medium-high risk ⇒ old `memory.json` format
stays readable during transition. Stage 5 also carries the last meaningful **cost** savings
(kills the daily wholesale-rewrite tokens — see §2.3).

### 2.2 General efficiency — NEW track (all three flavors, ranked by payoff)

#### Runtime (biggest headroom)

- **E1 — Parallelize source fetching in `digest.main`.** ~14 independent HTTP fetchers run
  sequentially today (fetch phase ≈ 5–8 min of the run); a `ThreadPoolExecutor` (~6 workers)
  over the pure-HTTP sources (news, ratings, market, macro, sec_filings, earnings, trace,
  pacer, fund_tracking, fed_research, treasury, cftc, fed_balance_sheet, fdic) cuts that to
  ~1–2 min. Keep Gmail, Substack, and 13D serial: the shared `googleapiclient` service object
  is not thread-safe, and 13D runs Playwright. Per-source `try/except` isolation already
  exists; per-source rate-limit sleeps stay correct within their own threads. Risk:
  low-medium (interleaved log prints — acceptable, or buffer per-source output). **Lands
  after the checkpoint** (code freeze) with an output-equivalence check on archived inputs
  where possible and one observed live run.
- **E2 — Re-index without re-embedding.** `search.index_daily_content`'s re-index branch
  re-encodes *every* prior chunk when a date is re-indexed; instead reconstruct the stored
  vectors from the existing FAISS index (`index.reconstruct` — exact, returns the stored
  vectors) and embed only the new day's chunks. Unit-testable offline (reconstructed index ==
  original for retained chunks); the win grows linearly with archive size.
- **E3 — Gmail batch fetch** (`BatchHttpRequest` for per-message gets + attachments in
  `fetch_recent_emails`). Moderate win, fiddly per-item error handling — lowest priority of
  the three; skip unless E1 leaves the Gmail phase as the visible bottleneck.

#### Code simplicity (modest — most dedup passes are already done; be honest about that)

- **S1 — `digest.main()` source-registry refactor** (the deliberately-deferred second half of
  Phase 3.1): a registry table `(name, fetch_fn, default)` driving the 16 near-identical
  fetch-with-try/except blocks (~150 lines → ~40) and the kwargs assembly. Behavior-neutral;
  per-source routing is already pinned by `tests/test_digest_prompt.py` sentinels. Do it
  **together with E1** — same function, one review.
- **Considered and rejected** (recorded so they aren't re-litigated): centralizing the
  per-module `HOURS_LOOKBACK` constants (deliberate explicitness per HANDOFF §2); an async
  rewrite; a vector-store substrate swap (spec'd as conditional in MEMORY_REFACTOR_SPEC);
  a type-hints pass; structured logging. All over-engineering for a solo-operator tool.

#### Operational (overlaps §7.2 — doing these now directly de-risks the deploy)

- **O1 — Log rotation.** `logs/*.log` grow unbounded (append-only from the wrappers).
  Simplest: date-stamped logs + a cleanup line in the wrappers (keep ~30 days).
- **O2 — Hung-run watchdog.** Failure alerting (2026-07-02) can't catch a run that never
  exits. Add a `--check-completed <label>` mode to `run_alert.py` (digest: is
  `archive/<today>/digest_sent_at.txt` fresh?) + a ~9:00 AM weekday scheduled task that
  alerts when the morning run hasn't completed. **Additive/off-path ⇒ allowed during the
  accrual week.**
- **O3 — Content monitor** (the remaining half of HANDOFF §7.2 item 4). Persist per-source
  item counts per run (small JSON); a normally-nonzero source at 0 for 3 consecutive runs ⇒
  alert via `run_alert`. Catches the silent-degradation failure mode (expired Substack
  cookie, dead 13D session) that per-source `try/except` deliberately swallows.
- **O4 — Backups** of `archive/`, `memory.json`, and the FAISS index (scheduled copy).
  Finalize as part of the server deploy; interim: any simple periodic copy.

### 2.3 Cost reduction — CLOSED (audit result: nothing left justifies a standalone project)

Residual ideas, honestly EV'd, for the record:

| Idea | EV / verdict |
|---|---|
| Conditional pass-2 skip on thin days | Small ($0.2–0.3 on rare thin days); touches the valued 2-pass design (§3/§6) — **parked** |
| 13D text-extraction instead of PDF→Opus | Post-cache ceiling is ~$0.65/week; quality risk — **parked** |
| Weekly summary → Sonnet | ~$0.15–0.25/week; only ever bundle the A/B with some other permissioned run — **low priority** |
| Stage 5 incremental memory update | Real savings (kills the ~daily wholesale-rewrite tokens) — **delivered by the memory track**, not a cost project |
| Fewer reply chunks after rerank (20 → ~10) | ~~delivered by Stage 4~~ **DEAD 2026-07-09** — conditioned on rerank's precision; rerank failed its Stage-4 retest and parked, so `SEARCH_TOP_K` stays 20 |

Monitoring continues for free via the `cost.py` per-run summaries in every log.

---

## 3. Fresh suggestions (beyond the three requested tracks)

- **F1 — Server-deploy readiness pack** (the queued big track after memory, per operator
  decision — §7.2 is the project's definition of "done"). Pre-work doable before hardware
  exists: **verify the Google OAuth app's publishing status is "production"** (Testing-mode
  refresh tokens die after 7 days = weekly breakage unattended — the single highest-risk
  deploy item); machine-level env-var plan (not user-level `env.bat`); validate headless
  Playwright (13D) under a non-interactive Task Scheduler session; update `setup_tasks.bat`
  for run-whether-logged-on (`/RU`); TZ/schedule confirmation; provisioning checklist — disk
  for ~1–2 GB HF model cache (MiniLM + reranker; + bge if 3b ever happens) + archive growth;
  O4 backups. Deliverable: a checklist section appended to this spec when the work starts
  (not another standalone doc).
- **F1a — Deploy-blocking fixes from the 2026-07 accrual week** (full detail in HANDOFF §7.2
  "Field findings" — the week live-confirmed the §7.2 risk list and added new items). The
  code-level ones, in priority order:
  1. **Unattended-consent guard** (`digest.get_gmail_service`): the RefreshError fallback opens
     an interactive browser consent that **hangs forever headless** (run never exits → no
     failure alert). Add an unattended mode (env flag) that fails fast + fires `run_alert`
     instead; reuse the refresh-only pattern from `run_alert._gmail_service_noninteractive`.
  2. **Task registration rewrite** (`setup_tasks.bat` → PowerShell `Register-ScheduledTask`):
     `schtasks` cannot set the three settings that made the week survivable (`WakeToRun`,
     `StartWhenAvailable`, `RunOnlyIfNetworkAvailable` — applied by hand this week), pops a
     killable console window in interactive mode (observed: run killed at 6s), and `/RL
     HIGHEST` needs elevation. Server tasks must register run-whether-logged-on, no window,
     with the settings object.
  3. **O2 completion watchdog — promoted to must-do:** the 7/7 network race killed the run AND
     the alert (both need network) — a fully silent miss. `RunOnlyIfNetworkAvailable` covers
     the start; only the watchdog covers hangs/never-starts.
  4. **PACER seen-state durability** (minor): persist `pacer_seen.json` after a successful
     send, not during discovery — a mid-run crash currently drops the marked entries from the
     next digest (30 lost on 7/2).
  Config/runbook (operator-side): OAuth app → **production publishing status** + fresh consent
  (7-day Testing token death confirmed live 7/7; interim deadline 7/14); **recipient-side
  allowlisting of `acorn.research.bot@gmail.com`** at every production recipient (Abnormal AI
  flagged the 7/2 digest as malicious — quarantine silences digests AND alerts). Known
  behavior, no fix: WILTW posts after 8 AM Thursdays → picked up next scheduled run.
- **F2 — 3.3 PDF-extraction review** — no longer hypothetical: the broker-PDF corpus started
  accruing 2026-07-02 (MENA + Taiwan notes) and reached **10 unique PDFs by 7/9 — 8 broker notes
  + 2 WILTW weeklies (trigger met at its ~8–10 lower bound; a thin corpus, so hold conclusions
  loosely or accrue a few more days before deciding the pypdf bump)**. Measure
  `_clean_pdf_text` fire-rate and cleaned-vs-raw damage on the real corpus, then decide
  fragmentation-gating and the PyPDF2→pypdf bump. Measure-before-touch per HANDOFF §6; also
  the pinned-PyPDF2 release valve.
- **F3 — Golden-set growth cadence.** A documented habit, not a tool: every time we touch the
  project, add a few questions for new archive days (incl. cross-day questions). The eval
  only stays meaningful if it compounds with the archive.
- **F4 — noted, low priority:** the unverified-SSL contexts for Treasury/CFTC
  (`net_utils.unverified_ssl_context`) could pin a CA bundle instead of disabling
  verification. Cosmetic risk reduction; do opportunistically if ever touching those fetchers.

---

## 4. Sequencing summary

| When | What |
|---|---|
| ~~Accrual week (7/6–7/9)~~ | ✅ DONE — 6/6 runs green; §7.2 field findings collected (→ F1a) |
| ~~Checkpoint (7/09)~~ | ✅ RUN — flips rejected, 3b skipped, Sonnet watch closed, runs stopped; see WORKLOG |
| ~~Next~~ | ✅ **Stage 4 DONE 2026-07-09** (query understanding + dedup + digest-exclusion; rerank retest run + FAILED → rerank/hybrid parked permanently; live-validated same day, $0.12) |
| ~~Then~~ | ✅ **Stage 5 DONE 2026-07-09** — v2 story-timeline store, incremental delta updates, reply router; delta-replay validated ($0.098 vs v1's $0.274 same-transition, zero story loss). **Memory track complete** |
| Next | Efficiency batch: **E1+S1** together, **E2**, **O1**, **O3** (E3 only if still needed) |
| Then | **F1 + F1a → §7.2 server deploy** — the project's "done" |
| Unblocked, anytime | **F2** (3.3 PDF review — 10 unique PDFs archived, trigger met at the margin) |

**Budget thread:** ~$11.7 remained after 7/2; the accrual week spends ~$5–7 → ~$5–6 left at
the checkpoint; the checkpoint itself needs ~$0.20. Extending daily runs ≈ $5–7/week ⇒ the
top-up decision belongs to the checkpoint. Everything else in this spec is local/free except
where marked permissioned.
