# Work Log

Running log of everything done in the Daily-Digest refactor, phase by phase (newest on top).
Companion to `HANDOFF.md` (the plan/spec) and its §11 "Needs Testing" (deferred verification).

---

## Current state (2026-07-10)

**Every code track is done AND live-validated.** The 2026-07-10 live validation run (next entry)
passed the whole HANDOFF §11 checklist in one shot: the 7/09 efficiency batch (S1+E1, O1, O3),
the F1a fixes exercised on the run path (PACER commit-after-send; consent-guard default path),
the **first live v2 memory migration + delta** (v1 backed up automatically), and the
**first-ever Friday weekly summary**. **E3 (Gmail batch fetch) is SKIPPED — the efficiency
track is CLOSED** (Gmail was seconds of a ~7-minute run; the wall-clock lives in the 5 Claude
calls). `ruff` clean, `pytest` **180** green. Budget **~$4.50** after the run's $1.58; daily
runs remain stopped (task disabled).

**REMAINING (all non-code):** (1) ~~operator OAuth publish + fresh consent~~ ✅ **DONE
2026-07-10** (see entry below — the 7/14 deadline is cleared; the durable production token is
what the server gets at deploy); (2) §7.2 server deploy (F1 checklist; run `setup_tasks.ps1`
as admin on the box); (3) §13 coordination items with jared (Substack ownership, forwarding
completeness, TRACE/Octus replacements). ~~Watch-item: the 7/09 WILTW~~ **CLOSED — miss
accepted (operator, 2026-07-10):** the 7/09 WILTW hadn't posted by Friday's run; with daily
runs stopped there are no automatic retries, so the week is skipped rather than manually
probed. One-off only — on the server's Mon–Fri schedule the pipeline retries every day of the
≤6-day window (Fri + Mon–Wed) and O3 alerts if wiltw stays at 0 for 3 runs, so this can't
recur silently once deployed.

---

## Abnormal allowlist request submitted (2026-07-10)

Operator contacted IT / the AAC Service Desk to **allowlist `acorn.research.bot@gmail.com` in
Abnormal** (the §7.2 field-finding-7 runbook item: Abnormal quarantined the 7/02 digest as
phishing, and since digests + failure alerts share the sender, quarantine silences both signal
paths at once). **Confirmation from IT pending** — watch that digests keep arriving. Still open
for deploy: the same allowlisting for every OTHER production recipient (incl.
`jtramontano@acorninv.com`) before recipients are switched to production. HANDOFF §7.2 item 7 +
NEXT_STEPS F1a updated.

---

## OAuth production publish + durable token — DONE (2026-07-10)

The 7/14 hard-deadline item, closed four days early. Free (Gmail API only, no Claude).

- **Operator published the bot's OAuth app to "production"** (console.cloud.google.com as
  `acorn.research.bot@gmail.com` → OAuth consent screen → Publish app; left unverified —
  fine for a single-user tool, the consent just shows the "unverified app" interstitial).
- **Fresh consent minted the durable token:** old `token.json` (Testing-mode, would have died
  7/14) backed up to `token_testing_0707.json.bak` (gitignored via `*.bak`); consent flow run
  via `get_gmail_service()` with the operator clicking through as the bot; new `token.json`
  written. **Order mattered:** a token minted while the app is in Testing keeps its 7-day
  expiry even after publishing, so publish-then-consent.
- **Verified:** `getProfile` → authenticated as `acorn.research.bot@gmail.com`;
  `run_alert._gmail_service_noninteractive()` (the refresh-only failure-alert path) also OK.
- **Deploy note:** THIS `token.json` is the one to copy to the server (§7.2 item 3) — it no
  longer expires on a timer, which is the whole unattended-operation requirement.

---

## 2026-07-10 live validation run — GREEN, $1.58 (checklist 9/9; E3 gate: SKIP)

Manual via `run_digest.bat` (absolute-path invocation; task stays disabled). Digest AND the
first-ever weekly summary both delivered to acohen (`DIGEST_TO` honored). Total **$1.58**
(under the $1.5–2.0 estimate — no WILTW spend, see below); **~$4.50 credit remains**.
Per-call: pass 1 $0.39 (cache wrote 36,401 tok) / pass 2 $0.22 (cache read 36,401) / alerts
$0.12 (2 of 7 triggered) / pacer size-filter $0.06 (5 of 74 kept) / news rank $0.01 (15 of
126) / memory $0.08 / weekly $0.71 (105,407 in — the run's cost driver).

**Checklist results (HANDOFF §11):**
1. **O1 wrapper ✓** — `logs\digest_2026-07-10.log` (dated name) created, `env.bat` loaded
   (FRED live). Prune quirk noted: `forfiles` exits 1 when nothing is >30d old, so the *bat's*
   exit code is 1 on a clean run — harmless (the failure-alert hook keys off python's exit
   right after the run, which was 0; no false alert fired), but anything checking the wrapper's
   own exit code should know.
2. **E1/S1 ✓** — `Fetch phase: 44s (14 sources, 6 workers)`; per-source log blocks contiguous
   (no interleaving); all sections populated (TRACE 0 = known-broken; polymathinvestor 403 =
   known; COT correctly Fri-skipped; 0 inbox PDFs today).
3. **E3 GATE → SKIP, track closed.** Run wall-clock 9:15:22→9:22:28 (~7m06s): Gmail (5
   emails, 0 PDFs) took seconds; 44s fetch pool; the rest is the 5 Claude calls + 379-chunk
   embed. Gmail batch fetch would buy nothing.
4. **Memory v2 ✓** — `Backed up v1 memory to memory_v1_backup.json` (41 active + 7 resolved
   preserved); delta applied 10 updated / 4 new / 0 resolved → **45 active**; `memory.json`
   now `"version": 2`; spot-read timeline good (private-credit story gained a dated GBDC
   revolver-extension entry with real terms).
5. **Weekly summary ✓ (first-ever live run)** — synthesized the week's 5 digests
   (7/06–7/10), sent 📊 to acohen. $0.71. **Operator: eyeball template/styling adherence in
   the inbox** (its system prompt had never run; the output is not saved to disk).
6. **PACER commit-after-send ✓** — `pacer_seen.json` mtime 09:19:01, after the digest save
   (09:19:00) + send; discovery found 76 raw / 74 corporate / 5 kept ≥$500M.
7. **O3 ✓** — `source_counts.json` created, run 1 of the ~6 needed to arm; counts sane.
8. **Consent guard default path ✓** — `DIGEST_UNATTENDED` unset ⇒ token refreshed silently,
   no consent, run proceeded (unchanged attended behavior).
9. **3.3 ✓** — digest rendered with all sections (alert box, market/macro/Fed BS/auctions
   tables, Opus §9, WSJ/FT, PACER); archive/2026-07-10 written; index +379 chunks → **3,948
   vectors / 7 days**; cost summary sane. (No inbox PDFs today, so the trimmed cleaner had no
   new PDF to exercise — already pinned by tests + the 7/09 rebuild.)

**WILTW note (checklist expected it, reality differed):** `WILTW_2026-07-09` returned "Report
not found" at 9:15 AM Friday — the report wasn't posted yet (the §7.2 field-finding timing
behavior, a day later than usual). Graceful skip, $0 spent, no Playwright hang. Window to
catch it closes Wed 7/15 (see Current state).

---

## F2 / 3.3 PDF-extraction review: the "rescue" rules WERE the damage (2026-07-09)

The last item from the original phased spec, run measure-before-touch per HANDOFF §6 on the real
10-unique-PDF corpus (8 broker notes + 2 WILTWs, ~340k chars raw). Free/offline. `ruff` clean,
`pytest` **180** green (+4).

**Measurement inverted the §6 assumption.** Instrumented every `_clean_pdf_text` rule:
- The pathology the aggressive rules target **does not exist**: zero single-char fragmentation
  runs in the raw extractions; the ligature (`'fi '/'fl '`) and single-char-rejoin rules fired
  **0 times** across all 10 PDFs. PyPDF2 3.0.1 extracts this corpus cleanly.
- The mid-word rejoin rule (`(\w) (\w{1,3}) (\w)` gluing when the middle token is 1–2 chars)
  fired **5,852 times — 96% of them gluing a real word onto a following of/to/in/is/a/on/by**:
  "action of Russia" → "actionof Russia", "the wifeof oneof our colleagues", "Huangis
  describingis". **99% of the live index's 581 PDF chunks carried this damage.** Retrieval
  survived because dense embeddings are typo-tolerant (and WILTW also indexes via its clean Opus
  summary), but keyword/exact-token matching on PDF chunks was degraded and the reply bot was
  quoting mangled text to Opus.
- The hyphen-linebreak rejoin (61 fires) and lowercase line-join (2,234) are legitimate.

**Fix applied (operator-approved):** `_clean_pdf_text` trimmed to the conservative rules
(hyphen rejoin, line join, whitespace collapse, space-before-punctuation tidy); the ligature,
mid-word, and single-char rules deleted with a docstring rule: rescue logic may only return
**gated behind a fragmentation heuristic**, never unconditionally. +4 tests pin the keep-rules
and the two damage classes ("of" never glued; DeFi/WiFi untouched).

**Rebuild + re-baseline:** full `--rebuild` → **3,569 chunks** (was 3,554; cleaner text chunks
slightly differently); eval **metric-identical** (0.846/1.0/0.904, snapshot
`2026-07-09_post33_rebuild.json`); known glued tokens verified at 0 occurrences with correct
spaced forms present. **PyPDF2→pypdf bump: no longer gated on 3.3 but deferred** (extraction
was clean — no motivating problem; requirements note updated). HANDOFF §5/§6/§14.A updated —
the §6 "do NOT fix" entry is now a measured, closed item.

---

## F1a deploy-blocking fixes: consent guard, task provisioning, PACER seen-state (2026-07-09)

The three code-level deploy blockers from the accrual week's field findings, built ahead of the
Stage-1 live run so tomorrow's single run validates the run-path pieces. `ruff` clean, `pytest`
**176** green (+6); `setup_tasks.ps1 -DryRun` validated locally.

- **F1a-1 — unattended-consent guard (`digest.get_gmail_service`):** with `DIGEST_UNATTENDED=1`
  (machine env on the server; `setup_tasks.ps1` sets it), a dead/expired token now **fails fast
  (SystemExit 3)** instead of falling into `flow.run_local_server()` — which on a headless box
  blocks forever, so the run never exits and even the wrapper's nonzero-exit alert can't fire
  (observed live 7/07). The fast exit lets the wrapper fire `run_alert`; re-consent stays a
  deliberate manual step. Flag unset (dev laptop, tomorrow's run) = byte-identical behavior;
  covers midday/reply too (they import the same function). Test-pinned (fail-fast, no consent
  call, no token write; healthy refresh unaffected; flag parsing).
- **F1a-2 — task provisioning rewrite: `setup_tasks.bat` DELETED → `setup_tasks.ps1`.**
  Registers all four tasks (MorningDigest 08:00, **Watchdog 09:00 — O2's task, now provisioned
  here as planned**, MiddayAlert 13:00, ReplyMonitor at startup; Mon–Fri) with everything
  `schtasks` couldn't do: `WakeToRun`/`StartWhenAvailable`/`RunOnlyIfNetworkAvailable`, S4U
  run-whether-logged-on (no stored password, no killable console window), RunLevel Limited (no
  /RL HIGHEST elevation trap), a 3h execution limit on run-once jobs (a hung run gets killed;
  the watchdog reports it) and NO limit on the daemon. Also sets `DIGEST_UNATTENDED=1`
  machine-wide. New `run_watchdog.bat` wrapper (O1-style dated log). `-DryRun` previews without
  registering — validated on the dev laptop (all 4 tasks, correct triggers/paths). Script
  documents the stored-password fallback if S4U balks on an AzureAD-joined account. README
  scheduling section updated.
- **F1a-4 — PACER seen-state durability (`pacer.py` + `digest.main`):** discovery/tracking now
  **stash** the updated seen-state in memory; `digest.main` calls `pacer.commit_seen()` only
  after the digest actually sends (standalone `python pacer.py` commits at exit as before). A
  crash anywhere earlier leaves entries unseen for the next run — duplication over silent loss
  (30 entries were lost this way on 7/02). Test-pinned (no disk write before commit; in-process
  readers see pending state; commit round-trip; no-op commit).

**F1a remaining:** running `setup_tasks.ps1` on the server itself (deploy day), plus the two
operator/config halves — OAuth production publish + re-consent (before 7/14) and recipient-side
allowlisting of the bot sender.

---

## Efficiency Stage 4 — O3 content monitor + O2 watchdog code (2026-07-09)

The alerting pair; **the efficiency batch's build work is complete** (E3 stays gated on the
Stage-1 live run's phase timings). `ruff` clean, `pytest` **169** green (+18); free live checks
green (no Claude).

- **O3 — content monitor (new `content_monitor.py`, wired into `digest.main`):** each run records
  per-source item counts (emails, substack, wiltw + the 14 registry sources) to a rolling
  30-run `source_counts.json` (gitignored); a source at **0 for 3 consecutive runs** that was
  nonzero in ≥50% of the prior runs fires a "Source degradation" signal, merged into the SAME red
  digest alert box as the Fed-stress check (no second email — deliberate improvement over the
  spec's "alert via run_alert"). The normally-nonzero test is data-driven, so always-zero TRACE,
  quarterly 13F, and COT's Thu skip can't false-positive; the signal repeats until the source
  recovers. History accrues once daily runs resume (needs ≥6 runs to arm).
- **O2 — hung-run watchdog (`run_alert.py --check-completed digest`):** checks today's
  `archive/<date>/digest_sent_at.txt`; absent ⇒ a "digest run MISSING" alert with the newest log
  tail (covers the run-hangs/never-starts hole that nonzero-exit alerting can't — the 7/7 silent
  double-failure). `--test` sends a drill regardless. digest-only by design (midday is
  silent-by-design most days, no completion artifact). **The ~9 AM weekday task is NOT registered
  now** — it registers at deploy via F1a-#2's `Register-ScheduledTask`, arming exactly when
  unattended runs exist again. Supporting refactors: `build_alert_html` gained headline/detail
  params (defaults byte-compatible, test-pinned); sending extracted to `_send_email`.
- **Live-validated (free):** OK-path read the real 7/09 completion marker
  ("OK: digest completed today (…09:44:02)"); one `--check-completed --test` drill delivered to
  acohen only (DIGEST_TO honored). Closes HANDOFF §7.2 item 4's two remaining halves at the code
  level.
- **Follow-up (operator-reported, same day):** the drill's TEST marker sat at the END of the
  subject, exactly where clients truncate — the operator read the drill as a real "Daily Digest
  MISSING" alert at first glance. Both drill paths (`send_alert --test` + the watchdog) now put
  **"(TEST drill)" FIRST** in the subject; real alerts unchanged. Test-pinned (marker must precede
  the alarming words; real alerts must not carry it).

---

## Efficiency Stage 3 — O1 log rotation (2026-07-09)

Offline/free. `ruff` clean, `pytest` **151** green (+4).

- **Wrappers (`run_digest/midday/reply_monitor.bat`):** logs are now date-stamped
  (`logs\digest_YYYY-MM-DD.log`; date via an inline PowerShell `Get-Date` — pure-batch `%date%`
  parsing is locale-fragile), and each run ends with a `forfiles /d -30` prune of `logs\*.log`
  older than ~30 days (`2>nul` — forfiles errors when nothing matches). The reply-monitor daemon's
  log is named by its START date and rotates on restart (accepted: a long-lived daemon accrues one
  file). Wrappers rewritten CRLF/ASCII.
- **`run_alert._find_log`:** the failure alert now tails the NEWEST `logs/<label>*.log` by mtime —
  covers the new dated names, the legacy un-dated files (which age out via the same prune), and a
  run crossing midnight. Labels can't cross-match (digest/midday/reply_monitor share no prefix).
- **Validated:** unit tests (+4: newest-dated wins, legacy-only, no cross-label match, missing-dir
  fallback) + a scratch-dir dry run of the exact wrapper lines — `LOGDATE=2026-07-09` computed
  correctly, dated log written, prune deleted a 40-day-old file and kept a 5-day-old one. The real
  `logs/` was not touched; the legacy accrual-week logs stay readable ~30 more days (their mtimes
  are current), and the timing baselines they contain are recorded here.

---

## Efficiency Stage 2 — E2 re-index without re-embedding (2026-07-09)

Offline/free. `ruff` clean, `pytest` **147** green (+4).

- **The change (`search.py`):** new `_rebuild_index_without_date` — dropping a re-indexed date now
  copies the retained vectors out of the flat index via `reconstruct_n` (byte-exact) instead of
  re-encoding every retained chunk's text. `index_daily_content` uses it whenever the position
  invariant holds (`ntotal == len(metadata)`); a diverged index falls back to the old re-encode
  path with a loud warning. Also more *faithful* than before: retained chunks keep their original
  vectors even across an embedding-library upgrade.
- **Measured on the real archive (temp copy, live index untouched):** dropping 7/09's 558 chunks
  from the 3,554-vector index = **0.01s reconstruct vs 208.8s re-encode** of the 2,996 retained
  chunks. Full production re-index of the day: ~245s before → **36s now** (all remaining time is
  embedding the new day's chunks, inherent either way). Retained block verified byte-exact in the
  final on-disk index; counts intact (3,554/3,554); spot search correct (Wynn rating top-1). The
  old path's cost grew linearly with the archive; the new one is effectively free on the retained
  side.
- Unit tests (+4) pin: only the target date drops, absent-date = identity, only-date = empty
  index, byte-exact retention, and search-order preservation on the rebuilt index.

---

## Efficiency Stage 1 — S1 source registry + E1 parallel fetch built (2026-07-09)

Built offline/free. `ruff` clean, `pytest` **143** green (+7). Awaiting the one permissioned live
digest run (~$1.0–1.5) that closes the stage.

**What landed (`digest.py`):**
- **S1 — source registry.** The 14 near-identical fetch-with-try/except blocks in `main()` are now
  one `SOURCE_FETCHERS` table (key, progress line, failure label, callable) + a 16-line unpack;
  per-source failure isolation unchanged (any source → `[]` + its old failure message). Gmail,
  Substack, and 13D deliberately stay serial outside the registry (auth root / shared Gmail
  service / Playwright). Registry keys are pinned against `summarize_with_claude`'s kwargs by test
  so a misnamed key can't silently drop a source from the prompt.
- **E1 — parallel fetch.** `_fetch_all_sources` runs the registry on a 6-worker
  `ThreadPoolExecutor`; each source's prints are buffered via a thread-local stdout proxy and
  emitted as one coherent block on completion (no log soup), with a `Fetch phase: Ns` timing line.
  Rate-limit sleeps stay per-thread-correct; `cost.record` appends are GIL-safe.

**Measured (free live check, 13 sources, PACER stubbed — Claude/seen-state):
serial 21s → parallel 7s (3×).** Honest correction to the spec's estimate: the pure-HTTP pool was
never the "5–8 min fetch phase" — that time lives OUTSIDE the registry (Gmail's sequential
per-message fetch + attachments, Substack, 13D Playwright, PACER's court+Google sleeps, and the
2-pass Claude calls). So E1's absolute win is ~15–30s/run (more on heavy PACER days, which the pool
now absorbs), S1's value is the cleanup itself, and **the E3 (Gmail batch) gate question is now the
interesting one** — the live run should apportion the remaining wall-clock (Gmail vs Claude passes)
to settle it. Result counts on the check were sane (12 FRED, 6 fed-BS, 6 market, 125 news, 5
filings; COT correctly Thursday-skipped; TRACE 0 = known-broken).

**Remaining for Stage 1:** one permissioned live digest run → acohen (~$1.0–1.5) for
output-equivalence + phase timing. ⚠️ Scheduling note: run on a FRESH day (or back up
`archive/2026-07-09` + `memory.json` + the FAISS index first — doubles as the interim O4): a rerun
today would overwrite the archived 7/09 day and re-index it, shifting the eval corpus under the
golden set. It will also trigger the FIRST real v2 memory delta on the live store (v1 backup is
automatic).

---

## Memory / retrieval refactor — Stage 5 DONE: story-timeline memory + reply router (2026-07-09)

Built offline/free, then validated with one permissioned delta replay ($0.098 — see bottom of this
entry). `ruff` clean, `pytest` **136** green (+21). The last stage of `MEMORY_REFACTOR_SPEC.md` —
**the memory/retrieval refactor track is complete.**

**What landed (`memory.py` rewritten; `reply_monitor.py` wired):**
- **v2 story-timeline store:** each story gets a stable `id`, `entities[]`, `status`, and a dated
  `timeline[]` of updates alongside the rolling summary/data points. v1 files migrate **in memory
  on load** (no write); the first v2 save backs up the v1 file once (`memory_v1_backup.json`,
  gitignored).
- **Incremental delta updates:** `update_memory` sends Sonnet a compact story index (**31%** of the
  old full-JSON resend on the real 48-story file) + the HTML-stripped digest, and gets back only a
  structured delta (`story_updates` by id, `new_stories`). Code appends timeline entries, refreshes
  summaries, resolves concluded stories — the model **cannot silently drop a story anymore** (the
  v1 wholesale rewrite re-emitted everything every day). The 30-day staleness rule moved from
  prompt instruction to deterministic code (`_age_stale_stories`).
- **Reply-bot router (`memory.match_stories` → `reply_monitor`):** questions match tracked
  storylines by entity hits (2x; lexicon or literal word), store-unique topic words (1.5x — a df=1
  word like "wynn" identifies a story alone), and common topic words (1x, need ≥2). Matched stories
  add **story-targeted retrieval phases** (story entities inside the story's lifespan window — this
  reaches entities the Stage-4 question-side lexicon can't) and their **timeline joins the answer
  context** as the narrative spine (≤2 stories, last 8 entries, cite-original-sources header).
  No match ⇒ byte-identical Stage-4 behavior.
- **Contracts held:** `get_memory_context()` renders **byte-identical output** on the real
  48-story file (33,665 chars, verified against the v1 renderer); `update_memory(digest_html)`
  signature unchanged; digest.main untouched.

**Real-data finding (the Stage-5 thesis, proven in our own store):** the Wynn Moody's downgrade —
in the 6/30 digest AND the eval golden set — **never entered v1 memory at all**: the 7/02 snapshot
(= the 6/30 run's output, 18 stories) has no Wynn story, and none ever appeared. The Group B A/B
had even flagged it ("Opus kept 2 more credit stories — Wynn Moody's cut"); the production Sonnet
rewrite just never created it, and every later rewrite compounded the omission. Under v2 a created
story is permanent until explicitly resolved. (Router consequence today: "the Wynn story" finds no
storyline — inherited v1 gap, falls back to Stage-4 chunk retrieval, where wynn-moodys hits rank 1.)

**Permissioned delta replay — DONE same day, $0.098. STAGE 5 COMPLETE; THE MEMORY/RETRIEVAL
REFACTOR IS DONE.** Replayed the archived 7/09 digest against the 7/09 pre-update snapshot
(39 active + 4 resolved) in a temp store (real memory.json untouched):
- **Delta quality:** 13 stories updated — specific, dated, correctly-id'd entries (Hormuz transit
  shift + IRGC firing; CRWV triple Form 4s with prices; hawkish Fed minutes; TPI/First Brands on
  the LME wave) — and 6 new stories created with sane entity tags (Burry GPU-depreciation →
  AMZN/CRWV/META/NVDA; DMRC governance flag). Every pre-state story retained by construction.
- **Cost, same-transition apples-to-apples:** v1's actual 7/09 memory pass cost **$0.274**
  (32,041 in + 11,839 out) vs v2's **$0.098** (10,344 in + 4,439 out) — **64% cheaper**, and the
  log shows v1's cost compounding with store size all week ($0.189 → $0.209 → $0.250 → $0.274)
  while v2 scales with the day's news instead. At v1's growth rate this saving widens every week
  the system runs.
- **Fidelity, same day:** v1's wholesale rewrite merged/reshaped 3 existing stories into new
  umbrella topics (both Hormuz threads → "stably unstable new normal"; TelePacific → "serial LME
  wave"), destroying their first_seen lineage and dated history; v2 updated the same stories in
  place. New-story coverage comparable (5 of 6 v2-new match v1-new topics; one unique pick each —
  normal variance).
- Budget after run: ~**$6.08**. The optional substrate swap stays dead (filtering runs fine on
  FAISS-flat + JSON). Next per NEXT_STEPS: the efficiency batch (E1+S1, E2, O1, O3), then
  F1/F1a → the §7.2 server deploy.

---

## Memory / retrieval refactor — Stage 4: reply-bot retrieval built; rerank retest FAILED → parked (2026-07-09)

Built offline/free (no Claude calls). `ruff` clean, `pytest` **115** green (+17).

**What landed:**
- **Same-day digest exclusion** — new `search(exclude_digest_date=)` (pre-retrieval via
  `_filter_ids`; `""` = all digests, the eval-retest condition). `_search_multiple` passes the
  reply's digest day in **every** phase: that digest is already loaded verbatim into the bot's
  context, so retrieving its chunks was pure slot-waste (the Stage-1/2 finding, now acted on).
- **Query understanding** (`reply_monitor._extract_query_filters`) — regex-only, free,
  deterministic: entities via the index's own tag lexicon (new public `search.extract_entities`),
  date windows from ISO dates / "Month DD" / this-week/last-week phrases anchored to the digest
  day. Drives new entity-filtered + date-windowed phases in `_search_multiple` — **the Stage-3a
  filters are now consumed in production** (they'd had no production caller since 7/02).
- **Near-dup dedup** (`search.dedupe_near_duplicates`) — token-set Jaccard ≥ 0.85 drop, walking
  best-first. Real-archive case it fixes: the same broker PDF forwarded on consecutive days
  (7/7 + 7/8 "Global Update") indexed twice and could fill multiple context slots with identical
  text. The bar is far above the ~0.2 overlap adjacent chunks share via CHUNK_OVERLAP.

**Eval (26-question set, snapshots `2026-07-09_stage4_*.json`):**
- default: **identical to the checkpoint baseline** (0.846/1.0/0.904) — behavior-neutral for all
  existing callers; nothing outside the reply path changes.
- default + exclude-digest: **0.885 / 0.962 / 0.924** — the exclusion *helps* the default path
  (digest chunks were crowding primary sources here too).
- **rerank retest (+ exclude-digest): 0.808 / 0.923 / 0.876 — FAILED the pre-committed gate**
  (≥ default on hit@3 AND MRR) even in its best-case condition (ALL digests excluded, vs the
  same-day-only exclusion production gets). Exclusion did help rerank (MRR 0.839 → 0.876 — the
  checkpoint diagnosis was half right), but it still promotes broker-email/substack chunks over
  primary sources. **Ruling: rerank and hybrid park permanently**; both mechanisms stay
  param-gated in `search()`, nothing deleted.
- Kept per spec: production excludes only the **same-day** digest (older digests remain
  retrievable as cross-day summaries); `SEARCH_TOP_K` stays 20 (the 20→10 cut was conditioned on
  rerank's precision, which never materialized).

**Permissioned validation — DONE same day, $0.12 (under the ~$0.20 estimate). STAGE 4 COMPLETE.**
Ran `answer_question()` directly (the Group-B method) on "How did the MSTR story evolve this
week — filings, Bitcoin sales, credit rating?" with digest_date=2026-07-09 — chosen over
injecting a live inbox reply to avoid racing jared's production reply monitor on the shared bot
inbox (the Gmail glue it skips — `check_for_replies`/`send_reply` threading — is unchanged since
its 2026-06-30 live validation, and no Gmail token was needed, so the 7/14 deadline didn't
apply). All three mechanisms fired: `Query filters: entities=['MSTR']
window=2026-07-06..2026-07-09` (entity + this-week window from the regex), 4-phase retrieval
with same-day digest exclusion + dedup → 20 chunks / 30.5k chars, Opus answer a high-quality
cross-day synthesis (6/29 framework 8-K → 7/6 first-ever BTC-sale 8-K → substack/NAV analysis,
all source-tagged). Bonus design validation: Sonnet's rewritten queries mis-guessed the year
("2025") — harmless, because filters come from the deterministic regex on the ORIGINAL question,
not Sonnet's rewrites. Budget after run: ~$6.18. Sonnet extract $0.002 + Opus answer $0.122.

---

## CHECKPOINT (2026-07-09): week green; rerank + hybrid flips REJECTED; 3b skipped; Sonnet watch closed

**Week scorecard:** 6/6 runs green (Wed+Thu fully hands-off via the hardened task); week spend
≈ $6.45, **~$6.30 credit remains**. Archive: **6 days / 3,554 chunks**; PDF corpus **11 files =
10 unique (8 broker notes + 2 WILTW weeklies; operator caught my earlier "17" — a bad `ls|grep`
count that included directory headers)** — 3.3 trigger met at the margin (3.3
trigger MET). Memory: 18 → **41 active + 7 resolved** across six Sonnet updates. **Operator
decisions:** stop daily runs after this week (task DISABLED — re-enable via
`schtasks /Change /TN "DailyDigest\MorningDigest" /ENABLE`); remaining credit reserved for
refactor testing; top-up deferred to deploy. OAuth "Publish app" still pending (do + re-consent
before 7/14 so testing isn't interrupted).

**Eval (golden set grown 16 → 26 questions — first cross-day, date-range, and new-week items;
harness passes `date_from`/`date_to` through):**

| Mode | hit@1 | hit@3 | MRR | Notes |
|---|---|---|---|---|
| **default (cosine+boost)** | **0.846** | **1.0** | **0.904** | wins every metric |
| rerank | 0.769 | 0.885 | 0.839 | promotes digest/broker-email chunks over primary sources (6 regressions) |
| hybrid | 0.808 | 0.962 | 0.872 | one genuine top-10 MISS (oil-quarter — BM25 'oil' flooding) |
| hybrid+rerank | 0.731 | 0.885 | 0.820 | worst |

**Gate rulings (pre-committed criteria, NEXT_STEPS_SPEC §1):** rerank flip **REJECTED**; hybrid
flip **REJECTED**; Stage 3b **SKIPPED** (hit@3=1.0 = no embedder-addressable headroom);
**memory→Sonnet watch CLOSED — Sonnet stays** (healthy evolution + resolutions all week). The
Stage-0-first discipline paid for itself twice: both "obvious best-practice" upgrades lost to
the simple baseline on this corpus, measured instead of assumed. Mechanisms stay param-gated;
rerank gets exactly one retest inside Stage 4 (with same-day-digest exclusion), else both park.

**Next: build Stage 4** (query understanding → live entity/date filters; MMR/dedup; same-day
digest-chunk exclusion in the reply path) + one permissioned reply validation (~$0.20), then
Stage 5. 3.3 is unblocked and queues behind Stage 4.

---

## Accrual week day 2: network race + the 7-day token death, both live-confirmed (2026-07-07)

Two more §7.2 failure modes fired for real — both now handled. Tuesday's data was recovered.

**Failure 1 — wake/logon network race.** The `StartWhenAvailable` catch-up fired at the 9:38
logon *before Wi-Fi connected*: the first network call (Gmail token refresh) died on DNS
(`getaddrinfo failed`), and the failure alert died the same way (it needs Gmail too) — a fully
silent miss. **Fix:** `RunOnlyIfNetworkAvailable = true` on the task; the trigger chain is now
wake (`WakeToRun`) → catch up missed start at logon (`StartWhenAvailable`) → hold until the
network is up (`RunOnlyIfNetworkAvailable`). $0 spent on the crashed attempt.

**Failure 2 — the Testing-mode 7-day refresh-token death (HANDOFF §7.2's top-risk item),
live-confirmed on schedule:** the bot's OAuth project was provisioned 6/30 in "Testing"
status; on day 7 the manual rerun hit `invalid_grant: Token has been expired or revoked` →
the 2026-06-21 RefreshError hardening worked as designed and fell through to a browser
consent, which the operator completed as the bot. **Plan (added to NEXT_STEPS_SPEC §1):**
operator publishes the OAuth app to "production" this week; the fresh-token re-consent happens
at the Friday checkpoint; **hard deadline Tue 7/14** (the new Testing token's expiry) or the
7/14 run hangs unattended. Also confirmed: laptop lid-close = Modern Standby (S0) — operator
guidance is sleep-don't-shutdown, with StartWhenAvailable as the self-heal.

**Tuesday's run (manual, ~10:05) — green, $1.06:** 11 emails incl. a 4th broker PDF (Global
Update); 5 Substacks; **WILTW cache HIT** (first live hit — skipped download + Opus exactly as
designed); FRED 12; 5 rating actions; 2 alerts triggered; cache engaged (48,288 tok). Archive:
**+529 chunks → 2,303 vectors / 4 days**; memory 28 → **32 active + 3 resolved**. Budget:
~**$8.8** remains (→ ~$6.8 expected at the checkpoint after Wed+Thu).

---

## Accrual week day 1: missed-start recovered + two §7.2 lessons (2026-07-06)

**Monday's 8 AM run missed — root cause chain:** the machine was **logged out** overnight
(the task is "interactive only", so no session = no run). At the operator's ~9:39 logon, Task
Scheduler started a catch-up run, but it died after ~6s with exit `0xC000013A` = **its console
window was closed** (the interactive task pops a black cmd window; closing it kills the run).
$0 spent, nothing archived. **Fixes:** (a) `StartWhenAvailable` enabled on the task — a missed
8 AM start now self-heals at logon; (b) operator guidance: **lock (Win+L), don't sign out**,
and leave the black `run_digest` window alone (it self-closes). The clean fix (run-whether-
logged-on, no window) is the §7.2 server config — this week keeps proving why it's the goal.

**Abnormal AI quarantine — delivery is now a known failure mode.** The operator's corporate
mail security flagged the **Thursday 7/2 digest as malicious and removed it** (new-ish Gmail
sender + emoji subject + link-dense HTML = phishing heuristics; the plain failure-alert email
passed). Consequences: the operator likely never saw the 7/2 digest email (content safe in
`digests/` + the index), and until the sender is allowlisted, digests AND failure alerts (same
sender) can be silently quarantined — "no email" no longer strictly means "no run". **Operator
action:** release + allowlist `acorn.research.bot@gmail.com` via the AAC Service Desk /
Abnormal false-positive flow. Monday's digest was delivered normally, so the flagging is
intermittent — allowlisting still required.

**Monday's catch-up run (manual, ~11:45) — green, $1.84:** 10 emails incl. a 3rd broker PDF
(NATO note); 4 Substacks; **WILTW 2026-07-02 fetched + summarized** (3.4 MB PDF, the week's
one ~$0.9 WILTW spend — now cached through Wednesday); FRED 12; 7 rating actions; PACER
discovery batch (small TXSB names, size-filtered). Cache engaged (41,235 tok written/read).
Archive/index: **+745 chunks → 1,774 vectors / 3 days**; memory 25 → **28 active + 3 resolved**
(Sonnet retention still healthy). Budget: ~**$9.9** remains; Tue–Thu ≈ $3 more → ~$7 at the
checkpoint.

---

## NEXT_STEPS_SPEC.md written — forward roadmap (2026-07-02)

Docs only (operator-requested, plan-mode approved). New **`NEXT_STEPS_SPEC.md`** captures:
(§1) the post-accrual-week **checkpoint procedure with pre-committed decision gates** (rerank/
hybrid flips, Stage 3b, the memory→Sonnet watch verdict, extend+top-up, the 3.3 trigger) and a
**code freeze on the daily path during the accrual week**; (§2.1) memory-track sequencing (flips
→ Stage 4 → Stage 5; `MEMORY_REFACTOR_SPEC.md` stays the source of truth); (§2.2) the new
**general-efficiency track** — runtime (E1 parallel fetch, E2 reindex-via-reconstruct, E3 Gmail
batch), code simplicity (S1 `main()` source registry; rejected ideas recorded), operational (O1
log rotation, O2 hung-run watchdog — accrual-week-safe, O3 content monitor, O4 backups); (§2.3)
the **cost track formally CLOSED** with residual ideas EV'd (remaining savings ride along with
memory Stages 4–5); (§3) fresh suggestions — F1 server-deploy readiness pack (OAuth production
status = top deploy risk), F2 the now-data-unblocked 3.3 PDF review, F3 golden-set cadence, F4
SSL-context note. Operator decisions embedded: efficiency = all three flavors; **memory refactor
finishes before the server deploy**. HANDOFF §1 updated + §12 marked superseded by the new spec.

---

## Run-failure alerting (§7.2 observability, first slice) (2026-07-02)

Unattended failures are no longer silent. Free to build/test (one Gmail send, no Claude calls).
`ruff` clean, `pytest` **98** green (+6).

- **New `run_alert.py`:** `run_alert.py <label> [--test]` emails the DIGEST_TO/production recipients
  a red failure notice with the last 40 lines of `logs/<label>.log`. **Deliberately self-contained**
  (no `import digest` — the failure path must not depend on the code that just failed) and
  **refresh-only Gmail auth** (never opens an interactive consent at 8 AM; if the token itself is
  dead it logs + exits, and the missing digest email stays the fallback signal). The `--test` flag
  marks the subject as a drill.
- **Wrappers wired:** `run_digest.bat` / `run_midday.bat` fire the alert on
  `%ERRORLEVEL% NEQ 0`; `run_reply_monitor.bat` alerts on **any** exit (it's a daemon — exiting at
  all is abnormal; note this also fires on a deliberate manual stop, acceptable).
- **Validated end-to-end:** unit tests for the log-tail + HTML building (escaping incl.
  `<script>`), plus one real `--test` send delivered to acohen.
- **Covers** the "email acohen@ if a run errors" half of §7.2 item 4; the "key section empty N days
  running" content-monitoring half remains a §7.2 deploy item. Also NOT covered: a *hung* run
  (never exits → no alert) — the missing digest email remains the signal for that case.

---

## Daily-run week started + §11 step-4 wrapper bug found & fixed (2026-07-02)

**Plan (operator-approved):** accrue archive for the retrieval refactor — one manual run today
(Thursday), then **scheduled runs Mon–Thu next week** (~$5–7 total; checkpoint session Friday
2026-07-10: re-run the eval matrix multi-day → decide the rerank/hybrid flips + Stage 3b, build
Stage 4). Holiday Friday 7/3 + weekend deliberately skipped (markets closed, thin sources).

**Scheduled task registered:** `DailyDigest\MorningDigest` → `run_digest.bat`, WEEKLY MON–THU 08:00,
first fire **Mon 2026-07-06**; `WakeToRun` enabled + wake timers confirmed allowed on AC (the box
sleeps at 3h idle — without WakeToRun the 8 AM trigger would never fire). Logon mode is
"Interactive only": the machine must be **on/asleep with KimCohen logged in** (locked is fine).
Created via `schtasks` directly (NOT `setup_tasks.bat` — midday + reply monitor stay OFF this
machine so we don't race jared's production reply monitor on the shared bot inbox). Task recurs
weekly until deleted — the 7/10 checkpoint decides extend-or-stop.

**§11 step-4 finding — `call env.bat` fixed to `call "%~dp0env.bat"` (all 3 wrappers).** The first
wrapper-driven digest run crashed at pass 1: `env.bat` never loaded (no ANTHROPIC/FRED keys) even
though `cd /d "%~dp0"` had set the right cwd. Diagnosis: relative `call env.bat` failed to resolve
in the sandboxed agent shell (absolute-path `call` worked; plain cmd/Task Scheduler is likely fine)
— but absolute `%~dp0` resolution matches how the wrappers already invoke the venv python and is
robust under any launcher. $0 spent on the crashed run (auth failed before any Claude call); side
effect: PACER discovery marked its first-scan backlog (30 mostly-stale entries) as seen, so today's
PACER section is thin — self-heals tomorrow.

**Today's run (fixed wrapper) — green, $1.07:** 6 emails **incl. 2 real broker PDFs (MENA, Taiwan
— the first §13 inbox PDFs; extracted + indexed → the 3.3 corpus is finally accruing)**; 5 Substack;
9 filings; 122 WSJ/FT (ranked to 15); 4 ratings; FRED 12 + Fed BS 6 (working with env.bat loaded);
WILTW 2026-07-02 not posted yet at run time (graceful skip; Monday's run pays the ~$0.65 within the
6-day window). **2-pass prompt cache fully engaged on a PDF day: pass 1 wrote 54,348 tok, pass 2
read 54,348 (2-pass $0.73)**. 3 alerts triggered; sent to acohen; archive/index +400 chunks →
**1,029 vectors / 2 days**; memory (Sonnet, first real daily update) 18 → **25 active + 2 resolved**
— no story-loss signal. Stage-3a auto-tagging live: 40/400 new chunks tagged (CRWV 12, RWT 11,
ABR 7; off-watchlist $TICK caught VEON/MAA/KLAC/SBAC). Budget: ~$11.7 of the $20 remains; the
Mon–Thu week fits with ~$6 buffer.

---

## Memory / retrieval refactor — Stage 3a: entity tags + date-range filter (2026-07-02)

Metadata-only (no reindex, vectors untouched), offline/free. `ruff` clean, `pytest` **92** green (+11).

**What landed (`search.py`):**
- **Entity tagging:** `_extract_entities` tags chunks with (a) watchlist tickers — case-sensitive
  word match, so lowercase "main" can't tag MAIN; (b) **any** `$TICK` mention, watchlist or not
  (caught 13D's $ALM/$AGI and the KBW note's IBKR/OCFC); (c) tracked-fund names + distinctive
  first-word aliases ("Oaktree" → "Oaktree Capital Management"; "Avenue"/"Canyon" excluded as
  generic). Applied at index time in `_chunks_for_date` (covers daily + rebuild); existing chunks
  backfilled via new **`python search.py --retag`** (rewrites `chunk_metadata.json` only).
- **New filters:** `search(entity_filter=, date_from=, date_to=)` — combined with the Stage-1 date
  prefix in one pre-retrieval `_filter_ids` (entity match is $- and case-insensitive; inclusive ISO
  range). CLI: `--entity`, `--from`, `--to`. Not yet consumed in production — Stage 4's query
  understanding will drive them.
- Unit tests +11 (tagger + combined filtering, incl. chunks predating tagging).

**Verified on the real archive:** `--retag` → **66/629 chunks tagged** (MSTR 11, Elliott 11, Ares 12,
RWT 7, PGY 6, WYNN 2, ALM 2 …). Eval: all 15 prior items unchanged (hit@1=0.933-equivalent); new
entity-filtered golden case — vague query "capital framework preferred securities announcement" +
`entity_filter=MSTR` — **hits the MSTR 8-K at rank 1** (16 Qs now: hit@1=0.938, MRR=0.958; snapshot
`2026-07-02_stage3a.json`). Coverage expectation per spec: watchlist + $TICK + tracked funds only
(no general NER) — "Wynn Resorts" spelled out untagged unless $WYNN/WYNN appears.

**Track status:** Stages 0/1/2/3a done. Recommended next: **let the archive accrue (~2 weeks of daily
runs)**, then revisit the deferred rerank/hybrid flips with a discriminating eval, and build Stage 4
(query understanding → these filters + MMR/dedup + same-day-digest exclusion) against a real multi-day
archive. Stage 3b stays conditional.

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
