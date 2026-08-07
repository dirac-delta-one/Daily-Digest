# Daily Research Digest — Engineering Handoff

_Last updated: 2026-08-07 (the WORKLOG merge + two prune passes — this doc absorbed
`WORKLOG.md`'s role; closed-watch narratives compressed to their live residue, full text at
each pre-prune git tip).
Living continuity doc for `Daily-Digest`. This keeps only what you need to understand, run, and
extend the system today; the full dated narrative of every change ever made and why lives in
git history — `WORKLOG.md` through commit `3965f7e`, plus each pre-prune tip of this file — and
the condensed digest is the **Session history** section below. **Pointer conventions:** a
"WORKLOG <date>" citation anywhere in this repo (docs, code comments, commit messages) is a
historical pointer into that file at `3965f7e`; code comments citing "HANDOFF §13"/"§14"/"§14.F"
use pre-2026-07-15 section numbers (§13 → today's §10 coverage gaps; §14/§14.F → §6 + §11.B
parked-retrieval items) — treat all doc citations as historical pointers and grep by topic when
in doubt. **Doc renames (2026-08-07 realignment):** `OPERATIONS.md` → `OPERATOR_GUIDE.md` and
`MAINTENANCE.md` → `DEPLOYMENT.md` (+ its "changing the code safely" content → §2a here) —
old-name mentions in the Session history digests refer to those files' git history. Read the
DEPLOYMENT STATE + PICKUP blocks below, then §2 (constraints), before making changes; §6
("do NOT fix") exists because several blunt-looking pieces of code are intentional and
battle-tested — constraints, not bugs._

_**Companion docs:** `OPERATOR_GUIDE.md` = the operator runbook (emails, How-Tos, every
failure's fix); `DEPLOYMENT.md` = machine setup + scheduling only; `README.md` = the repo TLDR.
**Active spec:** `JPM_SPEC.md` (the one parked workstream — JPM dealer research; Phase 1 login
succeeded 2026-07-29 but the portal is JPM's file-transfer service, not Markets research;
awaiting jared's re-scope-or-drop call — read its top section first). **Retired docs (all →
git history):** `WORKLOG.md` (2026-08-07, merged here); `REORG_CHECKLIST.md` (2026-08-07 —
Phase 0/`REPO_ROOT` done and load-bearing, Phase 1 parked → §11.A); `REDUCE_REPEATS_SPEC.md`
(2026-07-30 — anti-repetition all built; NO score-wired alert, a reader complaint is the
trigger; ladder → §11.B); `SNAPSHOT_UPDATE.md` (2026-07-27 — freshness work shipped; paid-data
lanes → §11.A); `ALERT_COMMANDS_SPEC.md` (2026-07-22 — email-managed alerts/watchlist, all
shipped; how-it-works → §4 + OPERATOR_GUIDE); `DEPLOY_PROGRESS.md` + `NEXT_STEPS_SPEC.md` (2026-07-21
— deploy executed); `CLEANUP_SPEC.md` / `CLEANUP_REFACTOR_SPEC.md` / `TEAM_DIGEST_SPEC.md`
(2026-07-21 — intent distilled into §1a/§9/Session history). This file was first condensed
2026-07-15 (F22 pass)._

---

**DEPLOYMENT STATE + STANDING RULES:**

**Current state — DEPLOYED & LIVE (server cutover completed 2026-07-20).** The dedicated Windows
server (`ShawnArmstrong`) is the SOLE instance, running unattended: four scheduled tasks Ready under
a **stored-password** principal (MorningDigest 08:00 / Watchdog 09:00 / Backup 09:45 / ReplyMonitor;
the MiddayAlert task was removed 2026-07-21), `DIGEST_UNATTENDED=1` machine-wide, production digests
delivered from the box, the reply daemon polling. Code is `ruff` clean, `pytest` **502 green**,
retrieval eval baseline **hit@1 0.897 / hit@3 1.0 / MRR 0.937, zero misses**
(`tools/eval_results/2026-07-15_post_index_filter.json`). **Operator since 2026-08-03:
`jtramontano@acorninv.com` (jared)** — built and handed off by `acohen@acorninv.com`, departed
2026-07-31; **Jared's old dev instance is decommissioned.** **Digest generation runs on Claude Fable 5 since 2026-07-22**
(`config.FABLE_MODEL` → `digest.CLAUDE_MODEL`; alerts/13D/reply bot stay on Opus) — observed
run costs (validated from the 7/31–8/7 logs): **$6.45–8.51 weekdays** (Mondays high — the
weekend catch-up window), **~$12 Fridays** including both weekly wraps ≈ **$160–180/mo**
(re-baselined 2026-07-30; OPERATOR_GUIDE carries the operator-facing numbers). Digest passes STREAM at max_tokens
48,000 with a truncation guard (stop_reason → WARNING + ops-footer notice + pass-2→pass-1
fallback). **Ops-signal routing since 2026-07-28 (jared's request — one email, not two):
operational signals (source degradation, truncation, config guards) render as a grey "⚙️ System
notices" FOOTER on the FULL sends** instead of the 2026-07-22 separate ⚙️ email; the footer is a
send-time append, so the TEAM sends and the durable artifacts (saved/archived/indexed/memory-fed)
never carry it. Orphaned-owner "Paused alerts" notices were dropped entirely (small team —
handled in person; `alert_commands.orphan_notices` kept but uncalled). The 🚨 run-FAILED/MISSING
emails (`run_alert.py`) remain separate emails — a failed run has no digest to carry a footer.

**Branch: work on `main`.** `ava-updates` existed only to keep refactor work off `main` while Jared
ran production from `main`; that's retired, the server tracks `main`, so **`main` is now the
working/authoritative branch** — commit and deploy from it. `ava-updates` was deleted from the
remote 2026-08-07 (tip `e576f7b`, fully merged into `main`, no local copy existed — nothing lost).

**Key operational facts (standing):**
- **Scheduled tasks run under a STORED PASSWORD, not S4U.** S4U registered fine but the AzureAD box
  silently refused to *launch* the tasks; `setup_tasks.ps1 -StoredPassword` (needs Shawn's Windows
  password) is the working path. Re-register that way, never the bare S4U default.
- **The server's Gmail token is the dev laptop's copied token pair (Plan B)** — the MFA lockout was
  never resolved, just routed around; refresh-token auth works through it. (The dev laptop's copy
  was deleted 2026-08-03 — the server's is now the only one.) MFA is team-owned: the MFA email is
  `sarmstrong@acorninv.com` and the phone is Jared's cell (recorded by the operator 2026-08-07);
  backup codes are in the vault AND emailed to jared on the thread where
  `acorn.research.bot@gmail.com` was created.
- **O4 backup = state-only `robocopy` into `%OneDriveCommercial%\DailyDigest-Backup`** (weekday
  09:45), which OneDrive syncs off-box; works because the server is kept logged-in-and-locked.
- **Durable pull rule: any pull touching `reply_monitor.py`/`alert_commands.py` (or changing
  recipients in `env.bat`) needs `schtasks /End` + `/Run` on `\DailyDigest\ReplyMonitor`** —
  the daemon holds old code/config until restarted. Pulls touching only the digest-run path
  (e.g. `digest.py`) need no restart: each morning run is a fresh process.
- **Doc-freeze rule (operator, 2026-08-07): `README.md`, `DEPLOYMENT.md`, and
  `OPERATOR_GUIDE.md` are formatted and edited to the operator's taste — do NOT edit them
  unless strictly necessary** (a new feature changes behavior they describe, or a factual
  error). Any necessary edit must match the target doc's existing formatting and plain, simple
  style — no reflows, no new sections, no style drift. Routine/living updates belong in THIS
  doc (the PICKUP block + a Session history digest), never in those three.

---

**PICKUP (2026-08-07 — START HERE). The build/soak/handoff cycle is 100% CLOSED**: the original
developer (`acohen`) departed 2026-07-31; the first fully-unattended week (7/31–8/7) was
validated green from the server logs on 2026-08-07 — 5 sends every day, zero WARNINGs/alerts,
**the 30-day memory ager fired 7/31 exactly on schedule** (store 146→203 active, the designed
ramp toward ~300–400 equilibrium; memory-pass output peak 9,755 vs the 16k cap), both production
streaming weeklies complete (10.6–15.9k out vs the 32k cap), costs $6.45–8.51 weekdays / ~$12
Fridays ≈ the **$160–180/mo** baseline. The 7/31 "FOMC day" weekly-wrap confabulation was fixed
code-side 2026-08-03 (`digest._weekly_digest_text` injects factual NO-DIGEST gap notes; full
weeks byte-identical, test-pinned; inert until a weekday digest is missing) and is **DEPLOYED**
(live from the Mon 8/10 run). **The server last synced 2026-08-07 (`b200285`)** — every
behavioral change through the gap-note fix + the ops-footer string is on-box, with **no
restarts owed**. Docs-only commits made after that sync may trail on the server harmlessly
(pull whenever); if anything BEHAVIORAL is ever pending a pull, this PICKUP will say so
explicitly. Post-departure facts: **operator = jared**
(receives the failure alerts); **Anthropic billing = firm-paid, auto-reload ON** (no manual
top-ups); FRED key on the bot Gmail (operator recollection, unverified); Gmail backup codes in
the vault AND with jared on the bot-creation email thread; **the dev machine holds NO secrets**
(§7.1 — the server is the only live set).

**The ONLY open item: JPM** — awaiting jared's re-scope-or-drop call; he was told 2026-08-03
it's waiting on him, and the departing operator's lead is that **the share link he originally
sent may have been the wrong one** (which would explain the SCDP file-transfer dead end) —
details + re-run instructions in `JPM_SPEC.md`'s top section.

**Passive, self-announcing watches (no action until the signal):** the gap-note fix's first
armed Friday (a wrap after a crash-missing weekday); the `Memory pass tokens ... out` line
nearing ~14k (raise the 16k cap or stream — §11.B); the TEAM weekly's output trend (15,938 on
8/7; revisit the 32k cap only if a log shows ~28k); a READER complaining about repetition
(§11.B ladder — never the score); the F13 index at ~200k vectors / felt reply slowness
(~late 2027 — §5).

---

## Session history (condensed)

_The full dated narrative (WORKLOG.md, ~3,900 lines) was merged here and pruned 2026-08-07 —
the complete how-and-why record is in git history at `3965f7e`. Compressed digests below,
newest first; durable rules and numbers are folded into the numbered sections. The deepest
post-mortems keep faithful multi-sentence distillations in the **Post-mortem library** at the
end of this section._

**Dated digests (newest first):**

- **08-07 (later — the doc-set realignment to the user's cross-project format):** `WORKLOG.md`
  merged into this doc and both pruned (4,764 → ~1,150 lines; full text preserved at
  `3965f7e`); a second prune pass then compressed §11.B's closed-watch narratives, §7.2, and
  the build-era digests to their live residue (~1,200 → ~900; full text at the pre-prune tip);
  cross-reference conventions declared in the header; a cold-read review pass then
  fixed 7 stale spots (`533cfa5`). README rewritten as a true repo TLDR (~65 lines). The final
  step renamed the companion docs to the reference set's names and shapes: `OPERATIONS.md` →
  **`OPERATOR_GUIDE.md`** (TLDR header + How-To/Question sections; gained the rerun-a-missed-
  digest and pull-code-updates How-Tos; later the same day the failure-handling content merged
  INTO its email-meanings section + How-Tos and the maintenance calendar was deleted as
  redundant — operator's calls: DEPLOYMENT stays deploy-only, one failure list not two; the
  developer-recovery facts moved to §4 "State recovery") and `MAINTENANCE.md` →
  **`DEPLOYMENT.md`** (numbered steps 1–8); MAINTENANCE's
  "changing the code safely" became §2a here, its "if you're stuck" dropped as redundant with
  this doc's charter; this doc's blocks reordered to the reference layout (STANDING RULES →
  PICKUP → Session history → §1 What it is); the ops footer in `digest.py` now names
  OPERATOR_GUIDE.md (the one code touch, string-only).
- **08-07 (`f731d73`):** Server pull to `f731d73` confirmed (weekly-wrap gap-note fix, armed
  from Mon 8/10) and the full 7/31–8/7 log set read, closing every remaining observation: the
  30-day memory ager is live (first firing Fri 7/31 `aged 2`; store 146→157→166→183→194→**203
  active**, memory-pass peak 9,755 tokens vs the 16k cap), both production streaming weeklies
  complete (7/31 = 10,584 FULL / 12,181 team; 8/7 = 12,893 / 15,938, zero truncation WARNINGs),
  and costs landed at $6.45/$6.46/$7.01/$8.51 weekdays and $12.02/$12.18 Fridays — matching the
  $160–180/mo re-baseline, 5 sends every day. README de-staled the same day (dropped the retired
  intraday-alert claim, $45–55 → $160–180/mo, added `JPM_SPEC.md` + `jpm_session.json`).
  `REORG_CHECKLIST.md` RETIRED (a root runbook for indefinitely-parked work reads as a pending
  TODO); its essentials — Phase 0/`REPO_ROOT` is done and load-bearing, Phase 1 is a
  maintenance-window op never a pull — moved to §11.A. Handoff 100% closed; only jared's JPM
  re-scope-or-drop decision remains.
- **08-03 (6 items):** Mon 8/3, the first fully-unattended run, verified clean email-side
  (5 digests 08:19 ET, no weeklies = correct Monday, no alert emails). Account ownership
  recorded: **Anthropic is firm-paid with auto-reload ON** — the monthly top-up duty does not
  exist (residual failure mode = the reload card expiring); a stale `~$45–55/month` burn figure
  in MAINTENANCE was corrected to $160–180. The dev machine was **de-credentialed** (all
  credential/session files + `jpm_recon/` deleted) because a departed employee's laptop holding
  the production Gmail token was a loose credential with zero operational value — consequence:
  nothing authenticated, including read-only sent-mail verification, runs from that box again.
  The 7/31 FOMC "cosmetic nit" was overruled and fixed code-side as **grounding, not a rule**:
  `digest._missing_week_days` + `digest._weekly_digest_text` inject a factual "NO DIGEST … do
  NOT infer or invent a reason" block; full weeks stay byte-identical (test-pinned), `pytest`
  496→**502**. Doc sweep generalized the test-recipient rule from the literal
  `acohen@acorninv.com` to "your own `@acorninv.com` address."
- **07-31:** Last-day email-side validation (read-only sent-mail pull, $0): **5 digests + 5
  weekly wraps**, acohen absent from every send — the 7/30 `env.bat` recipient drop confirmed
  live — no failure/ops emails, no System-notices footer. **The first production STREAMING
  weekly is COMPLETE** (~13–14k chars vs the 32k cap), closing the last untested armed-path seam
  from the 7/29 sweep. One nit recorded not fixed: both weeklies noticed the missing Wednesday
  and attributed it to "FOMC day" (the real cause was the 7/29 crash) — superseded by the 8/3
  grounding fix. The server log could not be pulled.
- **07-30 (2 entries):** 5-day log analysis settled both open decisions. **txsb RSS recovered
  on its own** — helpdesk email CANCELLED; the lesson for the docs is that a court-side 404
  deserves ~a week of watching before being called permanent. Repetition's full metric-v2 week
  read 0–4, mean ~2 → the operator **rejected wiring any alert to the score** (repetition is a
  reader-perception problem; an unexplained footer number would just teach the new operator to
  ignore footers); `REDUCE_REPEATS_SPEC.md` retired, Idea 10 not triggered. Memory aging = NO
  ACTION (`0 resolved` is the designed ramp toward ~300–400 active equilibrium, not a leak).
  Burn re-baselined **~$160–180/mo** ($6.64 on 7/28, $7.83 on 7/30 vs $10.32 pre-fix, $15.01 on
  7/24). Evening entry: the **F13 index tripwire was RETIRED by benchmark** — at 50k vectors the
  worst path is 13 ms, at 200k 54 ms, at 500k 138 ms (reindex copy 312 ms); new tripwire is
  ~200k vectors (~late 2027) or felt reply slowness, with a ⚠ that the date-window step must
  pass `tools/eval_retrieval.py` (rerank and hybrid both lost that eval).
- **07-29 (5 entries; `e44240f`):** The 08:00 run crashed building the TEAM prompt —
  `format_market_data_for_prompt` rendered `pct_1d` unconditionally whenever `chg_1d` was set,
  but the BKLN 12M-yield row deliberately carries `pct=None`; fixed with
  `market_data._fmt_change_for_prompt` (parenthetical % only when pct exists, pct-unit changes
  in bps), `pytest` **485**; blast radius ~$0.007, no state lost, and the pull became
  crash-blocking because the cache has history permanently. Follow-through: an **armed-path
  sweep** pre-tested every warm-up feature offline (iShares OAS audited clean, streaming-weekly
  seams, PACER January year-boundary, BKLN 1W/1M), adding §2's constraint "**warm-up features
  ship with warmed-up tests**"; `pytest` **488**. JPM: attempt #2 died on a 400 at page load →
  drive installed Chrome via Playwright `channel`, deliberately **no automation-hiding flags**;
  attempt #3 revealed share-login is **resource-scoped** (`resourceName` cookie) so
  `_login_root` now preserves path+query, plus a false-positive session-save fix and 8 offline
  tests (`pytest` **496**); attempt #4 **succeeded** — but the portal is JPM's Secure Content
  Delivery Portal (file transfer, role `SCDP_-_External`, one 2.7 KB welcome file), not
  J.P. Morgan Markets, so the spec's premise has no evident source and the workstream now waits
  on jared (T&C acceptance is a legal agreement in his name and was not clicked).
- **07-28 (5 entries):** The PACER `pacer_entries: 0` ops alert was diagnosed as a **false
  positive** (the 7/23 freshness filter working; large corporate Ch.11s simply don't file daily,
  and the monitor's 83%-nonzero baseline was pre-filter). Fix shipped: O3 now watches
  **`pacer_raw_ch11`**, the pre-filter Ch.11 keyword hit count (raw>0 = feeds alive; raw=0 =
  feeds dead), tests 480→**483**. The txsb Houston 404 was investigated and found to be a
  **fresh 7/23→7/28 removal by the court** (no alternate public endpoint; juriscraper builds the
  same URL) → shipped **per-court `pacer_rss_<court>` feed-health keys** because the aggregate
  can't see one court die, tests →**484**. Ops signals were rerouted from a separate ⚙️ email to
  a grey "⚙️ System notices" footer at the bottom of the FULL sends only (jared's request;
  appended after `_assemble_digest_html` so every durable artifact stays footer-free), and
  **orphan notices were dropped entirely** — acohen's 7/31 alert pause is now silent. Tuesday's
  log **validated the 1h cache TTL** (pass 2 read 76,996 / 103,291 tokens; run **$6.64** vs
  Monday's $10.32) and showed the 16k memory cap has real headroom (20,760 in / 6,534 out);
  index 17,944 vectors (+961/day).
- **07-27 (4 entries; `6fa5ee2`, `38a2f69`, `21e595b`):** Server pulled to `6fa5ee2`; the Monday
  log validated the weekend-aware lookback's first real Monday (`72h`) and showed memory
  recovered but at **7,822/8,000 out (98%)** with 118 active stories → both `memory.py` update
  calls raised 8k→16k `max_tokens` (`38a2f69`); cost $10.32. Snapshot work: a shared
  `config.change_cell_html` renders grey "unch" when a change rounds to zero at display
  precision, and a self-seeding `bkln_yield_cache.json` was added because Yahoo's
  `dividendYield` is a current-only scalar with no time series (changes are percentage points,
  rendered in bps); `pytest` **480**. `REORG_CHECKLIST.md` written and **Phase 0 executed**
  (`21e595b`): `config.REPO_ROOT` (sentinel walk for requirements.txt + .gitignore) replaced
  `Path(__file__).parent` in all 17 production modules, removing the Phase-1 "killer" where 26
  modules located the server's untracked state via module-relative paths; `pytest` 478.
  `SNAPSHOT_UPDATE.md` retired.
- **07-24 (`5795a84`, `d2021bf`, `9357b0b`, `503decd`, `e4ef194`):** Debut verified read-only
  from sent mail (6 digests + 6 per-recipient weekly wraps, zero ops-alert emails, all checklist
  items correct). Three nits fixed in `5795a84` (pytest 473→476): WSJ dedup keyed on URL sans
  query, Market Snapshot footnote now sees mirror rows, and every prompt market row carries
  `as of <date>` — §1 had called SK Hynix's -8.3% "Thursday" when it was the Friday Seoul
  session, because undated rows let the model borrow Greenmantle's US-evening framing. The
  server log then forced two fixes (`d2021bf`, pytest 478): **both weeklies truncated at exactly
  10,000 out** → `generate_weekly_summary` moved to streaming at 32k, and both passes logged
  `read 0 tok from cache` because pass-1 streamed generation now exceeds the 5-min TTL → both
  breakpoints set to **`ttl: "1h"`** (~$1.5+/run, ~$400/yr). The duplicate HY-spread confusion
  produced a general rule — **where the same asset appears at two lags, keep only the
  freshest**: HYG restored, both broad ICE HY/IG rows dropped (`9357b0b` then `503decd` +
  follow-up), making HYG/LQD the digest's headline HY/IG spreads while the ICE quality buckets
  stay. Weekly-wrap repetition scoring added as log-only so it can't pollute the daily v2 series
  (`e4ef194`, pytest 477). Friday all-in **$15.01**.
- **07-23 (`8197495`, `31ca28e`, `d95de25`, `8eb3672`, `b023ba4`; ~$19.2 spend):** Five
  workstreams. Weekly wraps went per-recipient (no reply-all exposure) and HANDOFF was corrected
  — the wrap runs on Fable, not Opus. Anti-repetition Bundle 2 shipped (Ideas 4/7/14), then the
  metric was **recalibrated to v2** (SEC Filings + Rating Actions excluded as content-mandated
  listings; noise floor 1–3; decision rule "sustained ≥4"). **Idea 15 (merge §4+§5) FAILED** at
  $3.58 and paid for itself by exposing that `stop_reason` was never checked anywhere → the
  **truncation guard** shipped (`8197495`; caps 20k→32k→48k, streaming required above ~20k). The
  real design was self-contained §1 (`31ca28e`, first 0-strong run; approved `d95de25`).
  Cross-day delta shipped (`8eb3672`): `pacer._fresh_filing`, weekend-aware
  `_set_lookback_hours` (Monday = 72h, fixing a silent Fri→Sun gap), and a PREVIOUS DIGEST
  prompt block — new cost baseline **$5.26/run**. Snapshot freshness (`b023ba4`):
  `treasury_yields.py` puts rates on T-1, NY Fed SOFR direct, lag-honest footnotes and `*`/`**`
  row markers, a `Freshness:` log line, and `cliffwater_data.py` for the BDC index row.
- **07-22 (3 entries):** Soak day 2 verified green (zero "Changes made:" occurrences — the
  pass-2 leak fix confirmed live). **Fable 5 switch for digest generation only** (alerts/13D/
  reply stay Opus), which required handling thinking-blocks-first (`digest._response_text`) and
  adding a Fable price tier to `cost.py` ($10/$50 per MTok, exactly 2x Opus; unknown ids now
  default to the most expensive tier) — run cost ~$2.9 vs ~$1.3 on Opus since thinking bills as
  output. Also: ticker glossary (`ticker_names.py`, cache committed only after both variants so
  the shared prefix can't fork), format overhaul, TL;DR box removed, PACER description
  `strip_html`, and anti-repetition Bundle 1 (`repetition.py` metric, batched prompt revision,
  WSJ/FT dedupe); `pytest` 360→**395**. `ALERT_COMMANDS_SPEC` built and shipped the same day:
  alerts + SEC watchlist became **email-managed runtime state** over the reply-to-digest channel
  (zero digest-contamination risk since it rides `is_self_artifact`), operational signals split
  into a separate ⚙️ email, `pytest` 424→427. Part II gave every thematic alert exactly **one
  owner** with batched cross-owner eval (still ≤2 Claude calls/run) and per-recipient sends
  whose personal alert boxes never reach saves/archive/index/memory; `pytest` **440**; deployed
  the same night with the first live command round-trip passing.
- **07-21 (6 entries; `df29a59`, `435cb15`, `0fba811`, `d75a923`):** The **first fully
  unattended cycle passed** — 08:00 delivered both variants with nobody driving, and the 09:00
  watchdog stayed correctly silent; memory 87 active / 8 resolved, two-pass $0.88 team + $0.68
  full. The pull surfaced that pass 2 had leaked its edit changelog into the sent TEAM digest →
  fixed in two layers (`df29a59`): a prompt instruction plus `_strip_to_html` truncating to the
  **last HTML closing tag** — deliberately not the last `>`, because the real leak contained
  "Japan >$180B"; `pytest` **364**. The midday alert was deleted entirely (operator: "no one
  wants it"), tasks 5→4, with the caveat that a `git pull` does not deregister a task (manual
  `Unregister-ScheduledTask` required). Doc set pruned to 5 core docs (`435cb15`) and snapshot
  footnotes collapsed (`0fba811`). Alerts were bound to the real `sec_filings.WATCHLIST` so one
  list drives filings, earnings and watchlist-scoped alerts. Server live on `d75a923`; `main`
  is the authoritative branch since.
- **07-20 (`00b0ab7`, `6793009`):** Server cutover COMPLETE and unattended — code merged to
  `main` (`00b0ab7`), 32.5 MB of state re-synced and verified byte-for-byte, secrets installed
  via **Plan B** (the dev `credentials.json` + `token.json` pair copied instead of re-minting,
  proving refresh-token auth works straight through a Google MFA lockout), 13D session probe
  live, manual run GREEN at $2.03. **THE FINDING: S4U task launch fails on the AzureAD-joined
  server** (see the Post-mortem library) → `-StoredPassword` switch added (`6793009`); any
  future re-registration must use it. Also fixed the reply monitor's empty log (unbuffered `-u`).
- **07-17 (written 07-20):** Friday run GREEN $3.72 — WILTW resumed, the memory context budget
  activated (58 of 64 stories). **Credit exhausted on the run's final Claude call fired NO
  failure alert** (non-fatal by design — a log line + a missing email were the only signals).
  Google security alerts were being ingested as digest source email → filtered to a "Gmail
  Alerts" label (bot-account compromise alerts no longer surface in the digest — check the
  label directly). Eval baseline 0.897 / 1.0 / 0.937, `pytest` 349.
- **07-16:** Snapshot build-out (jared): Metric column on every table (anchors re-keyed on
  `series_id`), IGLB/IGIB/HYG/LQD as fund-reported Portfolio OAS via new `ishares_data.py` (no
  free ETF G-spread source exists; changes accrue in a cache keyed by the site's as-of date),
  20Y UST mirror, SpaceX added as `SPCX` (IPO'd June 12 2026). `pytest` 362.
- **07-15 (9 entries; `5ee7397`):** Cleanup Stages 2–5 ($0 Claude): code-enforced TEAM leak
  guard, chunk_id dedup rebuild (0 dupes), config-driven reply allow-list (`FULL_ACCESS_SENDERS`
  = jtramontano only), self-ingestion guard, memory context budget (60/45k), lazy BM25,
  vectorized subset scan, `OPERATIONS.md`. The index-side self-artifact filter **improved the
  eval to 0.897/1.0/0.937** (self-ingested reply artifacts had been suppressing real sources).
  Incidents: `--login` could overwrite a valid session with an unauthenticated one (hardened),
  and the **Substack-via-email TEAM leak** (newsletters also arrive as inbox email →
  `config.is_substack_email` filters both variants). A latent off-by-one (`>= 20` +
  `iloc[-21]`) had silently dropped every US-listed ticker on 20-day downloads. `pytest` 353.
- **07-14:** `main()` test pins landed before refactors touched it (`test_digest_main.py`, all
  effects stubbed). **Substack auto-renewal had never worked** (see Post-mortem library) —
  rebuilt on the OTP-code flow, live-validated. 3-stage forwarding fix (embedded-sender
  detection + attribution; eval re-baselined metric-neutral); appended sections unnumbered.
- **07-13:** `TEAM_DIGEST_SPEC` spec→build→activation in one day: Substack became
  jared-personal; the team prompt is a **byte-identical strict prefix** of the full prompt (the
  full run reads the team run's cache); asker-tiered reply bot; the TEAM digest is the indexed
  one. A team render proved the memory cleanse is load-bearing (pub names leaked via memory
  context). Also: dead-cookie incident (probe fixed), paid pubs 11→**17**, TRACE removed
  ($9k/yr for a 2-issuer watchlist), forwarding completeness resolved.
- **07-10 (12 entries):** GREEN live validation $1.58 (first weekly wrap, first v2 memory
  delta); E3 Gmail-batch SKIPPED (not the bottleneck). **OAuth app published to production +
  durable token minted** — order matters: a token minted in Testing keeps its 7-day expiry even
  after publishing. The `CLEANUP_REFACTOR_SPEC` track ran end to end (dead code, correctness,
  insertion-ordered PACER seen-state eviction, CFTC COT vs prior *week*, PyPDF2→pypdf with a
  metric-identical eval gate; pytest 180→227).
- **07-09 (9 entries):** The CHECKPOINT ruled on pre-committed gates: **default cosine+boost
  wins every metric; rerank + hybrid REJECTED and parked permanently** (Post-mortem library).
  Stage 5 delivered **memory v2** (story-timeline deltas, $0.098 vs v1's $0.274 — Post-mortem
  library). Efficiency: parallel fetch 21s→7s, reindex-via-`reconstruct` 208.8s→0.01s, O2/O3
  monitors, dated logs. F1a closed the three deploy blockers. The PDF review found **the
  "rescue" rules were the damage** (Post-mortem library).
- **07-06/07:** Deploy failure modes fired for real: a signed-out machine missed the 8 AM run
  (0xC000013A when its console was closed → lock, never sign out); the catch-up ran before
  Wi-Fi, killing the run AND the failure alert silently → `RunOnlyIfNetworkAvailable`; the
  Testing-mode 7-day token death hit on schedule; **Abnormal AI quarantined the 7/2 digest as
  malicious** → org-wide Outlook allowlist became a deploy requirement.
- **07-01/02:** Group B A/B ruled **keep all secondary calls on Opus** (Sonnet's reply rendered
  broken; its 13D summary blew the word cap). The 2-pass prompt cache got its correct form
  (shared system + source prefix + ephemeral breakpoint, engagement confirmed live). Eval
  harness + golden set established (Stage-0 discipline: a param-gated cross-encoder was
  **deferred rather than flipped** — never override a just-built eval on a 1-day archive).
  `run_alert.py` shipped, deliberately self-contained (the failure path must not import the
  code that just failed); wrappers fixed to `call "%~dp0env.bat"`.
- **06-19 → 06-30 (build era; `1f400f6` … `004722b`):** Bring-up: Python 3.12 venv (3.14
  lacked torch/faiss wheels), ruff, first tests; `config.py` centralized model IDs/pricing (the
  stale literals had overstated reported cost ~3×); HTML escaping; `%~dp0`/env-driven
  de-hardcoding; naive prompt caching deliberately dropped (zero reads + 1.25× write premium
  with differing system prompts). 06-21: hardened `get_gmail_service` against dead refresh
  tokens; recorded the Testing-mode 7-day rule. 06-30: first credentialed end-to-end run
  ($1.52), identity flipped to the bot, Octus deleted, FRED provisioned — catching mislabeled
  `fed_balance_sheet` series + an ON RRP ×1000 bug; Opus 4.6→4.8; A2 structured outputs on all
  5 JSON call sites; `SYSTEM_PROMPT` §9 made explicitly model-owned (`build_ratings_html`
  removed as dead code that would have duplicated it).

### Post-mortem library (the lessons a one-liner can't carry)

- **07-29 — the BKLN crash anatomy (the one-day-fuse time bomb).**
  `market_data.format_market_data_for_prompt` rendered `pct_1d` unconditionally whenever
  `chg_1d` was set, but the BKLN 12M-yield row added by the 7/27 accrual-cache work deliberately
  sets `pct_*=None` (a percentage change of a percentage is meaningless). The cache seeded
  silently on 7/28, so 7/29 was the **first morning `chg_1d` was ever non-None** →
  `TypeError`. Monday's pull shipped the bug, Tuesday ran clean, Wednesday detonated. The 1W and
  1M lines carried the identical latent bug and would have fired ~8/4. The fix
  (`_fmt_change_for_prompt`) emits the parenthetical % only when pct exists and renders
  percentage-point moves in **bps** to match the table cell (prompt/table consistency being the
  7/24 SK Hynix lesson). Durable consequences: the crash was pull-blocking (the cache holds
  history permanently, so every pre-fix run would crash every morning), and the failure *class*
  — "a feature whose first ARMED execution comes days after deploy" — became §2's constraint:
  **warm-up features ship with warmed-up tests**; ask at validation time "what is this code's
  first ARMED execution?" and construct that state in a test. The same-day armed-path sweep
  pre-tested the whole live inventory offline for $0.
- **07-23 — the Idea-15 §-merge failure (the failure that paid for itself).** Merging §4+§5
  cost $3.58 and failed: both passes capped at 20k output tokens (Fable's thinking bills as
  output) and the email went out **truncated mid-§6 with no warning** — the real finding being
  that `stop_reason` had never been checked anywhere, so a capped generation was
  indistinguishable from a complete one. Idea 15 was reverted; the truncation guard shipped
  permanently (`8197495`: WARNING log + ops notice + pass-2→pass-1 fallback; caps 20k→32k→48k).
  Raising the cap surfaced a second constraint immediately: the SDK raises `ValueError` on long
  non-streaming calls, so **streaming is required above ~20k** (`stream.get_final_message()`).
  Committed split — guard first, redesign second — so the redesign alone could be reverted.
- **07-28 → 07-30 — txsb: a thorough investigation, corrected by data.** The 7/28 evidence
  genuinely supported "fresh removal by the court" (a txsb filing in the 7/23 archive, full
  seen-history, host up with only `rss_outside.pl` gone, no alternate public endpoint,
  mid-NextGen-upgrade plausible). The structural lesson shipped as code — the aggregate
  `pacer_raw_ch11` **cannot see one court's feed die**, so per-court `pacer_rss_<court>` keys
  were added (txsb starting dead, arming only on recovery). Then 7/30 corrected the conclusion:
  txsb 404'd only 7/27–7/29 and recovered untouched — a ~3-business-day transient. Documented
  lesson: **a court-side 404 deserves ~a week of watching before being called permanent** — a
  single day's probe, however thorough, cannot distinguish an outage from a removal.
- **07-09 — rerank/hybrid: measured, not assumed (load-bearing result).** Both "best-practice"
  retrieval upgrades lost to the simple cosine+boost baseline, twice. Rerank (0.769/0.885/0.839)
  regressed 6 questions by promoting digest/broker-email chunks — dense summaries that match
  almost any question — over primary sources; hybrid (0.808/0.962/0.872) token-flooded on "oil";
  rerank's one permitted retest under its best-case condition still failed the pre-committed
  gate. Both park permanently, param-gated in `search()`, nothing deleted. This result is why
  the 7/30 F13 entry declined to pre-build the date-window index step: it is eval-risky work
  solving a problem that measurably does not exist.
- **07-20 — S4U vs stored password on an AzureAD-joined server.** The S4U principal
  **registered all four tasks without error** — and the scheduler then silently refused to
  launch them (`Start-ScheduledTask` no error; `LastRunTime` stuck at the 11/30/1999 sentinel;
  `LastTaskResult 267011`; no process, no log). Dangerous precisely because registration
  succeeds. Fix: `setup_tasks.ps1 -StoredPassword` re-registering the **same**
  `AzureAD\ShawnArmstrong` account with a stored password — same user deliberately, so the
  per-user Playwright/HuggingFace caches stay valid (SYSTEM would break 13D). Re-registration
  must use that switch in an **elevated** window (non-elevated fails with `Access is denied`).
- **07-09 — "the rescue rules WERE the damage" (PDF extraction).** Measured on the real
  10-PDF corpus, the pathology the aggressive cleaning rules existed to fix **did not occur at
  all** (0 firings), while the mid-word rejoin rule fired **5,852 times, 96% gluing a real word
  onto a following of/to/in/is** — corrupting 99% of the live index's PDF chunks. Retrieval had
  survived only because dense embeddings are typo-tolerant. The cleaner was trimmed to
  conservative rules with a standing docstring rule: rescue logic may only return **gated behind
  a fragmentation heuristic**, never unconditionally. The rebuild came back metric-identical —
  which is the point: the damage was invisible to the eval that would have justified the rules.
- **07-13/14 — the Substack false-positive class (two probes that lied).** `_check_session`
  probed an endpoint that **returns 200 even logged out**, masked further by Substack's per-post
  API serving many pubs' full paid bodies unauthenticated — so a dead cookie looked like normal
  operation while properly-gated pubs quietly delivered previews (Fixed Income Beacon 903 →
  35,081 chars once a live cookie landed). And the "automated" renewal had never worked:
  `_complete_login` saved whatever `substack.sid` sat on the session, and Substack sets an
  anonymous one on every request — success reported, dead cookie persisted. Durable lesson:
  **a health probe must assert something only an authenticated session can produce**
  (`/api/v1/user/profile/self`, 200 vs 401, test-pinned).
- **07-09 — why memory v2 exists (the Wynn story that never was).** The Wynn Moody's downgrade
  appeared in the 6/30 digest and the eval golden set, yet **never entered v1 memory at all** —
  v1 re-emitted the entire store every day, so any story the model failed to re-write vanished
  with no signal, and wholesale rewrites also merged/reshaped existing stories, destroying
  `first_seen` lineage. v2 has the model return only a structured delta by story id while code
  appends timeline entries — **a created story is permanent until explicitly resolved; the model
  cannot silently drop one** — and cost $0.098 vs v1's $0.274 on the identical transition, with
  v1's cost compounding weekly.
- **07-31 → 08-03 — the FOMC confabulation (vacuum-filling as a hallucination class).** Both
  7/31 weekly wraps attributed the crash-missing Wednesday to "FOMC day" — plausible, invented,
  wrong. The mechanism (a model filling a data vacuum with confident fiction, read by a team
  with no one left to catch it) is bounded — it arms only when a weekday digest file is missing,
  and wraps are never indexed or memory-fed — but it is a class, not a nit. The fix was
  **grounding, not a rule**: inject a factual NO-DIGEST block into the missing day's slot
  ("cause not known to you; do not infer a reason; labeled synthesis from adjacent days is
  fine") rather than instructing abstinence. Full weeks produce **byte-identical prompt text**
  (test-pinned) — inert until armed — which is what made shipping without a paid validation
  acceptable.
- **07-30 — retiring a tripwire by measuring instead of guessing (F13).** The synthetic
  benchmark ran `search.py`'s exact operations at scale: at 50k vectors (the old tripwire) the
  worst path is **13 ms**; at 200k, 54 ms; at 500k, 138 ms + a 312 ms reindex copy. The
  reasoning that closes it: reply-bot felt latency is the Opus call (seconds), FAISS is
  milliseconds at any realistic scale, and an exact index can never return *wrong* answers — no
  cliff, no armed date. New tripwire: ~200k vectors (~late 2027) **or felt reply slowness /
  memory pressure — a symptom, never a date** — and the ladder's date-window step must pass the
  eval gate that rerank and hybrid both failed.

---

## 1. What it is

A solo-operator Python automation that runs daily on a schedule. It gathers ~17
financial/market data sources (Gmail inbox + forwarded research PDFs, paid Substack subs, SEC
EDGAR, FRED macro, Fed balance sheet, Yahoo Finance, earnings calendar, PACER, 13F filings, rating
actions, central-bank research, Treasury auctions, CFTC COT, FDIC, WSJ/FT RSS, 13D WILTW),
summarizes them with Claude in a **two-pass** flow (draft → review/enhance), emails an HTML "Daily
Research Digest" (that's the in-email H1; the *subject line* is "📬 Daily Inbox Digest" =
`config.DIGEST_SUBJECT_PREFIX`, which the reply bot's Gmail query anchors on — search sent mail by
the latter), archives all raw content to disk, and indexes it into a local FAISS vector store
that powers an **email-reply Q&A bot**. Since 2026-07-13 each run produces **two variants** — a
FULL digest (with Substack) and a Substack-free TEAM digest (see §1a).

**Module convention:** nearly every source module exposes `fetch_X()` (gather),
`format_X_for_prompt()` (text for the Opus prompt), and `build_X_html()` (pre-rendered HTML
section). `digest.py` orchestrates: fetch all → build prompt → 2-pass Claude → assemble HTML →
send → archive → index → update memory → (Fridays) weekly summary.

### 1a. FULL vs TEAM variants (TEAM_DIGEST_SPEC, activated 2026-07-13)

Substack content is personal to jared. Each run generates two digests:
- **FULL** → `DIGEST_TO` (default `jtramontano@acorninv.com`): Substack + a `substack_memory.json`
  layer; subject carries a `[FULL] ` marker.
- **TEAM** (Substack-free) → `DIGEST_TO_TEAM` (**empty ⇒ team generation skipped entirely**).

The TEAM prompt is a byte-identical cache prefix of the FULL prompt (team runs first; FULL reads
the cache). **The TEAM digest is the indexed one** and the one that feeds the shared `memory.json`
(so team askers' reply-bot retrieval never sees Substack). The reply bot answers each asker at
their tier: `FULL_ACCESS_SENDERS` (jtramontano only) get Substack; everyone else gets the team
view. **Deploy-critical:** the server's `env.bat` **must** carry `DIGEST_TO_TEAM` — a
post-activation run without it is code-treated as misconfigured (warn + a "Team config missing"
notice in the FULL send's ops footer + digest chunks un-indexed + memory frozen; escape hatch = set
`config.TEAM_ACTIVATION_DATE` back to `None` if the team variant is ever deliberately retired).

---

## 2. Key constraints

- **Digest generation is `claude-fable-5` (FABLE_MODEL, since 2026-07-22); everything else Opus-tier
  stays `claude-opus-4-8`.** All model IDs are centralized in `config.py` (`FABLE_MODEL` /
  `OPUS_MODEL` / `SONNET_MODEL="claude-sonnet-4-6"` / `HAIKU_MODEL="claude-haiku-4-5-20251001"`);
  every call site imports them. Fable specifics: returns thinking blocks first (extract text via
  `digest._response_text`, never `content[0].text`), bills $10/$50 per MTok (2x Opus — its own
  `cost.py` tier; thinking tokens bill as output), and unknown model ids now default to the fable
  tier (most expensive) in cost accounting. Roll back = point `digest.CLAUDE_MODEL` at `OPUS_MODEL`.
- **This is a working single-operator tool.** Explicitness and tuned heuristics have real value;
  prefer small, reversible changes over architecture-level refactors.
- **Warm-up features ship with warmed-up tests.** Any feature whose behavior depends on accrued
  state (caches needing N days of history, monitors needing run history, date-boundary branches)
  must ship with a test that CONSTRUCTS the accrued state — the plan's "activates on <date>" line
  is otherwise the date it crashes. Proven 2026-07-29: the BKLN 1D path, armed by one day of
  cache history, took down the run; every pre-deploy check had exercised only the empty-cache
  path, and both a green pytest and a clean live test run on deploy day were unable to see it.
  When validating a change, ask "what is this code's first ARMED execution?" and simulate that
  day in a test. (The 2026-07-29 armed-path sweep pre-tested the then-known cases: BKLN 1W/1M,
  the Fri 7/31 streaming weekly seams, the PACER January window; iShares audited None-safe.)
- **Test between every phase.** Route all test output **locally or to YOUR OWN
  `@acorninv.com` address** (whoever is doing the dev work) — never to the config recipients
  (jared's addresses) during testing. *(Wording generalized 2026-08-03: the rule used to name
  `acohen@acorninv.com`, the original operator, who has departed — the principle was always
  "send test output to yourself.")*
- **External tooling falls into three cost tiers — know which before testing:**
  - **Pay-per-query (the only real per-call cost): the Anthropic/Claude API.** Token-billed across
    the 2-pass **Fable** digest ($6.45–8.51/run observed, 7/31–8/7 logs) plus the **Fable** Friday
    weekly wraps (~$4.50/Friday extra; share `digest.CLAUDE_MODEL`), Haiku (news ranking), Sonnet
    (PACER size-filter, reply query-extract, memory), and Opus (13D summary, alerts, reply
    answers).
    **Ask explicit permission before any test that calls Claude**, run once on a small input, and
    never loop the full digest. *(Standing exception, operator 2026-07-14: $0 `count_tokens` calls
    are pre-authorized; generation calls stay ask-first.)*
  - **Flat paid subscriptions (already paid; zero marginal cost per run): Substack, 13D Research.**
    Scraped via saved login/cookies — free to test repeatedly. Only cautions: scraping
    etiquette/rate-limits, and that sessions expire and need re-login. 13D *also* fires a small
    embedded Opus call (a Claude cost, not a subscription cost); Substack has none.
  - **Free (no charge): everything else.** No-key public APIs — SEC EDGAR, Yahoo Finance, WSJ/FT &
    Google News RSS, Treasury, CFTC, FDIC, PACER court RSS — plus local compute (FAISS +
    sentence-transformer embeddings). Also free but key/auth-gated: **Gmail API** (quota-limited,
    never billed) and **FRED** (free key). "Needs a key" ≠ "costs money": only the Claude key maps
    to per-use billing.

### 2a. Engineering conventions (absorbed from the retired MAINTENANCE.md, 2026-08-07)

- **The gate:** `check.bat` = `ruff check` + `pytest` (**502** tests as of 2026-08-03). Both must
  pass before commit.
- **The eval harness:** `tools/eval_retrieval.py` + `tools/eval_golden.json` measure retrieval
  quality (current baseline: hit@1 0.897 / hit@3 1.0 / MRR 0.937, zero misses,
  `tools/eval_results/2026-07-15_post_index_filter.json`). Re-run and compare after ANY change to
  chunking, embedding, indexing, or the reply path. Rebuild the index with
  `python search.py --rebuild` after extraction/chunking changes. Grow the golden set as archive
  days accrue — it only stays meaningful if it compounds.
- **A new source** is one module in the §1 fetch/format/build shape plus a row in `digest.py`'s
  fetch registry (pinned by `tests/test_source_registry.py` / `test_digest_prompt.py`).
- **Alerts & the watchlist — two separate levers.** The top-of-digest alert *triggers* live in
  `alerts_config.json` (email-managed runtime state — no code). The *ticker universe* is
  `WATCHLIST` in `sec_filings.py` (a Python list — a **code** edit) and is the single source of
  truth for SEC filings, earnings, entity tagging, **and** (since 2026-07-21) the scoping of the
  two "watchlist"-referencing alerts (Insider selling, Rating downgrade) — editing that one list
  updates all four at once. Event-based triggers (Large Chapter 11, HY spread blowout, Fed
  surprise, Bank failure, Distressed exchange) are watchlist-independent. Alerts are evaluated
  **per variant** (FULL sees Substack; TEAM doesn't) — a Substack-sourced alert appears only in
  the owner's box, by design.
- **Commits:** work on `main` (the server tracks it); short-lived feature branches only for risky
  in-progress work. Keep the change-log habit — a dated digest in the Session history explaining
  what changed and *why* is how the next person (or you, in six months) stays oriented.

---

## 3. Terminology

- **Two-pass / pass 1 / pass 2:** the digest model (Fable 5 since 2026-07-22; previously Opus)
  generates a draft digest (pass 1), then a second call reviews the draft against the *same* source
  material and produces the final (pass 2 — its checklist now leads with DEDUPLICATE, then missed
  items/errors/source-tags/format). Intentional and valued — keep it.
- **Cross-digest memory:** `memory.json`, a model-maintained store of evolving storylines injected
  into the next day's prompt (`memory.py`; Sonnet since 2026-07-01). Since Stage 5 it is a **v2
  story-timeline store** updated by incremental deltas (per-story dated update history, no wholesale
  rewrites) and also feeds the reply bot's storyline router. Contexts are budget-bounded (60 stories
  / 45k chars). A separate `substack_memory.json` holds jared-personal Substack storylines.
- **Archive / indexing / embedding:** After each run, raw content is saved to `archive/<date>/`,
  then chunked, **embedded** (text → 384-dim vectors via `sentence-transformers`) and **indexed**
  into a **FAISS** store (`search.py`). The reply bot embeds an incoming question, finds nearest
  chunks, and feeds them to Opus.
- **Reply monitor:** `reply_monitor.py`, a long-running poller that answers email replies to
  digests via RAG over the archive (asker-tiered — see §1a).

---

## 4. Relevant files

| File | Role |
|---|---|
| `digest.py` | Main orchestrator: Gmail, prompt build, 2-pass Claude, FULL/TEAM assembly, send, weekly. Config at top: `HOURS_LOOKBACK`, `MAX_EMAILS`, `MAX_PDF_SIZE_MB`, `DIGEST_RECIPIENTS`/`TEAM_RECIPIENTS`, email-body char budgets, `MAX_FETCH_WORKERS`. |
| `config.py` | Model IDs, pricing, User-Agents, `BOT_ADDRESS`, `DIGEST_SUBJECT_PREFIX`, `FULL_ACCESS_SENDERS`, `FORWARDER_ADDRESSES`, `TEAM_ACTIVATION_DATE`, `is_self_artifact()`, `unattended()`, `esc()`/`safe_href()`. |
| `substack.py` | API/cookie-based Substack scraper (OTP-code auto-login via Gmail). Uses `substack_cookie.txt`; `SUBSCRIPTIONS` list (17 pubs). |
| `search.py` | FAISS index + chunking + embeddings + hybrid/rerank (both param-gated, parked). CLI: `--rebuild`, `--index <date>`, `--retag`. |
| `memory.py` | v2 story-timeline cross-digest memory + substack memory + reply-bot story router. |
| `reply_monitor.py` | Email-reply RAG bot; asker-tiered (config-driven allow-list); `--once` mode + `while True` daemon. Since 2026-07-22 also the alert-command channel: `_handle_command` routes command replies to `alert_commands` before Q&A (parse failure falls through to Q&A). |
| `alerts.py`, `archive.py`, `cost.py`, `claude_utils.py`, `content_monitor.py`, `run_alert.py` | Plain-English alerts; raw-content archiver; per-run cost accounting; JSON/structured-output helpers; O3 source-count degradation monitor; failure-alert + O2 completion watchdog. *(PACER discovery gained a since-last-run freshness filter 2026-07-23 — see §11.B cross-day entry.)* |
| `alert_commands.py` | Email-managed alerts + SEC watchlist (ALERT_COMMANDS_SPEC, 2026-07-22; Part II same day): owns `alerts_config.json`/`watchlist.json` (seed-on-missing, atomic writes, expiry, the Part-II owner migration), the Sonnet command classify/parse (owner-grounded), deterministic apply + confirmation HTML, expiry lifecycle (`consume_expired`/`expiring_today`, owner-attributed), and `orphan_notices` (uncalled since 2026-07-28 — kept for a future notification channel). **Thematic alerts are per-user** (owner-only visibility/editing; jared + acohen own the migrated originals; new users start empty); the watchlist is shared. Reply-channel = contamination-safe (`is_self_artifact()` exclusion). |
| `ticker_names.py` | Ticker→issuer-name glossary for the prompt (2026-07-22): SEC registry titles + a learned cache of digest-rendered "$TICK (Name)" pairs validated against that day's sources. Staged collect() / single post-variants commit() so the TEAM/FULL cache prefix can't fork mid-run. |
| `repetition.py` | Cross-section repetition metric (REDUCE_REPEATS Idea 12, 2026-07-22): deterministic scorer over assembled digest HTML, logged per run + persisted to `repetition_scores.json`. The yardstick for all anti-repetition prompt work. |
| Source fetchers (free APIs) | `news.py`, `ratings.py`, `market_data.py`, `macro_data.py`, `sec_filings.py`, `treasury_auctions.py`, `treasury_yields.py` (2026-07-23: Treasury.gov daily par curves — the Rates Snapshot's T-1 source + NY Fed SOFR; FRED = fallback), `cliffwater_data.py` (2026-07-23: Cliffwater BDC index, jared-approved SPBDCUP substitute), `cftc_cot.py`, `fed_balance_sheet.py`, `fdic_monitor.py`, `earnings.py`, `fund_tracking.py`, `thirteen_d.py`, `fed_research.py`, `pacer.py`. |
| `net_utils.py`, `feeds.py`, `html_utils.py` | Shared EDGAR fetch + unverified-SSL context; RSS feed/date/recency helpers; HTML strippers + Gmail body extractor + `parse_forwarded_from`. |
| `run_*.bat`, `setup_tasks.ps1`, `check.bat` | Task Scheduler wiring: 4 `%~dp0`-relative wrappers (dated logs + 30-day prune, clean `exit /b 0`) + the PowerShell provisioning script (run-whether-logged-on, wake/catch-up/network, the 09:00 watchdog, `DIGEST_UNATTENDED`). `check.bat` = ruff + pytest. |

**Removed modules (history in WORKLOG):** `octus.py` (2026-06-29), `trace_data.py` (2026-07-13),
`grab_session.py` (Phase 0). Don't reintroduce references.

**Gitignored, account-bound secrets** (must exist on the machine; copy or regenerate):
`credentials.json`, `token.json` (Gmail — the durable *production* token minted 2026-07-10),
`substack_cookie.txt`, `thirteen_d_session.json`, `jpm_session.json` (JPM Playwright session,
2026-07-27 — see JPM_SPEC), `env.bat`, plus caches/state (`ishares_oas_cache.json`,
`ticker_names_cache.json`, `bkln_yield_cache.json` (BKLN 12M-yield accrual, self-seeds),
`pacer_seen.json`, `memory.json`, `substack_memory.json`, `source_counts.json`,
`repetition_scores.json`, `wiltw_cache.json`, and — email-managed, self-seeding from
`alert_commands.py` defaults if absent — `alerts_config.json` + `watchlist.json`).
All caches/state self-seed if absent (no manual copy needed); the *secrets* above must be
installed. **State recovery:** each `archive/<date>/` snapshots that day's `memory.json` /
`substack_memory.json` — if the live one is ever corrupted, copy the last good snapshot back
(the resolved-story revert lever is named in `memory._story_index_for_prompt`).
`alerts_config.json`/`watchlist.json` are written atomically; a corrupted one makes the code
run on built-in defaults WITHOUT overwriting the damaged file — restore it from the O4 backup,
or delete it to accept a fresh default seed. *(`credentials_JARED.json`, a pre-2026-06-30-flip OAuth-client dev backup, was deleted
2026-07-27 — obsolete since the bot-identity flip; the live client is `credentials.json`.)*
**⚠ Since 2026-08-03 the SERVER holds the only live copy of every secret:** the dev machine's
copies (all six files above, plus the `jpm_recon/` dumps) were deliberately deleted at the
operator's departure. Standing up a new dev environment = copy from the server or regenerate
per DEPLOYMENT §3a.

**Env vars:** `ANTHROPIC_API_KEY` (required), `FRED_API_KEY` (macro + fed balance sheet),
`SUBSTACK_EMAIL` (Substack OTP-code renewal), `DIGEST_TO` (full-digest recipient override — leave
UNSET in production so it defaults to jtramontano@acorninv.com), `DIGEST_TO_TEAM` (the Substack-free
TEAM digest's recipients — **must be set on the server**; empty = team generation skipped).

---

## 5. Risks

- **Silent degradation:** the `try/except`-everywhere design means a broken source yields an empty
  section, not a crash. Mitigated by the O3 content monitor (per-source zero-streak → the "System
  notices" ops footer on the FULL sends since 2026-07-28, previously a separate ⚙️ email; the
  digest's red box carries content alerts only) but still: read logs.
- **LLM-output coupling:** `_assemble_digest_html` finds insertion points by string-matching the
  Opus-generated HTML. Stable in practice (heavily-pinned prompt) but brittle if the template drifts.
- **HTML correctness:** scraped text/URLs are interpolated into emailed HTML; `esc()`/`safe_href()`
  wrap the build-step inputs, but this is self-sent + client-sanitized (low security risk).
- **Account binding:** the pipeline authenticates via the account-bound secret files above
  (Gmail = the bot `acorn.research.bot@gmail.com`; Substack cookie + 13D session = jared's
  accounts). A new machine reuses those identities unless re-provisioned.
- **Custom-domain Substack pubs are leak-dependent (flagged 2026-07-15):** the auth cookie is
  scoped to `.substack.com`, so the 9 custom-domain pubs receive full paid bodies only via
  Substack's *unauthenticated* per-post API. If Substack closes that hole they degrade to previews:
  visible via the `[preview only…]` markers in the digest and, if total, via the
  `substack_fulltext` O3 zero-streak. Real per-domain auth (SSO) deliberately not built.
- **Index growth (F13; BENCHMARKED 2026-07-30 — the mid-August "tripwire" is RETIRED; no 2026
  action expected):** the FAISS index grows ~1,000–1,400 chunks/weekday (15,192 on 7/24 →
  **20,157 on 7/30**). The 30–50k revisit point (and the mid-to-late-August date it implied) was
  a pre-measurement guess; a same-day synthetic benchmark of the exact `search.py` operations
  (IndexFlatIP, 384-dim normalized float32 — identical math to production) measured:

  | Vectors | Global top-100 | Subset brute-force (~95% ids) | `reconstruct_n` (reindex) | Vector RAM |
  |---|---|---|---|---|
  | 20k (2026-07-30) | 2 ms | 8 ms | 11 ms | 31 MB |
  | 50k (~Oct 2026) | 4 ms | 13 ms | 27 ms | 77 MB |
  | 100k (~spring 2027) | 6 ms | 31 ms | 46 ms | 154 MB |
  | 200k (~late 2027) | 13 ms | 54 ms | 94 ms | 307 MB |
  | 500k | 30 ms | 138 ms | 312 ms | 768 MB |

  Reply-bot latency is dominated by the Opus API call (seconds); FAISS contributes milliseconds
  at any 2026–2027 scale. The other growing piece, `chunk_metadata.json` (~920 bytes/chunk,
  re-parsed only when the index changes — once a day in the reply daemon), is a one-time ~3 s
  load even at 150k chunks. Degradation is gradual (latency + RAM only), **never wrong answers**
  (exact index). **New tripwire: revisit at ~200k vectors (~late 2027 at current rates), or
  earlier ONLY if reply answers actually feel slow or the server shows memory pressure.**
  Escalation ladder unchanged (cheapest first): ✅ vectorized subset scan (done) → date-windowed
  retrieval default → prune-and-archive old days → IVF. ⚠ The date-window step is a
  RETRIEVAL-BEHAVIOR change — eval-gate it like rerank/hybrid (`tools/eval_retrieval.py`,
  ≥ default on hit@3 AND MRR, no new misses); this project has parked two retrieval
  "improvements" that lost that eval. Also noted in OPERATOR_GUIDE.md for the post-handoff owner.

---

## 6. Do NOT "fix" these — intentional / load-bearing

Investigated and confirmed as deliberate. Changing them adds risk for no benefit:

- **Module-level `--email_time=` argv parse** (top of `digest.py`): must run before the `def`s
  because `HOURS_LOOKBACK` is captured as a default-arg value at definition time. Correct placement.
- **`_clean_pdf_text` is conservative on purpose.** MEASURED 2026-07-09 (3.3): the fragmentation
  pathology the old aggressive regexes targeted never occurs on the real corpus, and those rules
  were the main *source* of damage (5,852 glue events, 96% corrupting real words; 99% of PDF chunks
  affected). Now hyphen/line-join + whitespace only. If a genuinely fragmented PDF ever appears,
  reintroduce rescue rules **gated behind a fragmentation heuristic** — never unconditionally.
- **Rating Actions §9 is Opus-written, not pre-rendered.** Opus writes the digest's §9 from the RSS
  rating data (SYSTEM_PROMPT). There is no `build_ratings_html` (removed as dead code 2026-06-30).
  **Gotcha:** don't "restore" a ratings table without also suppressing Opus's §9, or you get two.
- **`_is_recent` returns `True` on unparseable dates** (news/ratings/substack): intentional
  over-inclusion; Opus curates downstream.
- **`reply_monitor` `while True` daemon:** deliberate (a `--once` mode also exists). Not a bug.
- **FAISS `IndexFlatIP`:** exact and correct for personal scale; revisit only per the §5 tripwire.
- **Rerank / hybrid retrieval are param-gated and PARKED** (`search(rerank=True)` / `hybrid=True`).
  Both lost the 6-day/26-question eval AND the Stage-4 retest — they promote digest/broker/substack
  chunks over primary sources (rerank) or token-flood (hybrid). The mechanisms stay in code for
  re-testing; re-test only if the corpus character changes fundamentally (gate: ≥ default on hit@3
  AND MRR, no new misses). Detail: §11.B's parked-retrieval bullet + the Post-mortem library's
  07-09 entry.

---

## 7. Machine migration

### 7.1 Dev machine (`KimCohen`) — ✅ DONE; **DE-CREDENTIALED 2026-08-03**

**As of the operator's departure the dev machine holds NO secrets** — `credentials.json`,
`token.json`, `substack_cookie.txt`, `thirteen_d_session.json`, `jpm_session.json`, `env.bat`,
and the `jpm_recon/` dumps were deleted 2026-08-03 (operator-authorized; no secrets were in
Windows env vars). The checkout, `.venv`, caches/state, and Claude session memory remain, but
nothing authenticated can run from this box until secrets are re-installed (copy from the
server or regenerate per DEPLOYMENT §3a). The server is unaffected and self-sufficient.

Historical record of the de-hardcoding (completed earlier): `.bat`/`setup_tasks.ps1` use `%~dp0`
+ project `.venv` + `PYTHONUTF8=1`; recipients are `DIGEST_TO`/`DIGEST_TO_TEAM`-env-driven; the
SEC/PACER User-Agent contact and the recipient/allow-list point at the bot
`acorn.research.bot@gmail.com`; all secret files were installed and working until the 2026-08-03
cleanup. The email identity flipped to the bot 2026-06-30 (jared's
rule-based forwards flow into the bot inbox; `token.json` = the bot sends + reads inbox; Substack
renewal reads the forwarded OTP code from the bot inbox). The Substack *account* stays jared's — an
optional end-state flip to the bot is his call (§10). Full history: Session history, 06-19 → 08-03.

### 7.2 Dedicated Windows server — DEPLOYED 2026-07-20 and LIVE

The step-by-step for a rebuild or a new machine is **DEPLOYMENT.md** (steps 1–6 to stand up,
§9 to restore from the OneDrive backup; it also carries the cutover rule: exactly ONE reply
daemon + ONE digest instance may run anywhere). What this
section keeps is the **field findings** — the "why" behind DEPLOYMENT's rules, each learned
live during the 2026-07-06→09 accrual week (all code fixes DONE): unattended-consent hang →
`DIGEST_UNATTENDED=1` fails fast (SystemExit 3); OAuth Testing-mode 7-day token death →
published to production + a durable token; `schtasks` can't set
`WakeToRun`/`StartWhenAvailable`/`RunOnlyIfNetworkAvailable` → `setup_tasks.ps1` exists;
network-down wake/logon race → `RunOnlyIfNetworkAvailable` + the O2 watchdog; PACER seen-state
lost on failed runs → `commit_seen()` only after a successful send; Abnormal AI quarantined the
7/2 digest as malicious → IT allowlisted the bot org-wide for Outlook (re-verify only if a
non-Outlook recipient is added); WILTW posts after 8 AM Thursdays → picked up by the next run
(no fix needed).

---

## 8. Testing protocol

- **Free, no permission needed:** offline unit tests (`pytest` / `check.bat`), and standalone
  fetchers that hit only free APIs (`python news.py`, `market_data.py`, `macro_data.py`,
  `sec_filings.py`, `ratings.py`, `treasury_auctions.py`, `cftc_cot.py`, `fed_balance_sheet.py`,
  `fdic_monitor.py`, `earnings.py`, `fund_tracking.py`).
- **Requires permission (costs money/credits):** any path that calls Claude — full `digest.py`,
  `memory.py`, `alerts.py`, `reply_monitor.py`, news ranking, **and `python pacer.py`**
  (its `__main__` can trigger the Sonnet size filter when new filings exist). Substack (`substack.py`)
  scraping is a flat subscription — **free to test** (makes no Claude call).
- **Token discipline:** prefer unit tests; when an LLM path must run, run **once** on a **small**
  input (e.g. temporarily lower `MAX_EMAILS`), never in a loop. **Always** redirect email output to
  **your own `@acorninv.com` address** (or render HTML to a local file) during tests. For reply/memory testing,
  drive `answer_question()` / `update_memory()` directly on archived inputs (avoids racing the
  production reply monitor on the shared bot inbox; needs no live Gmail injection).
- **⚠ Dev `env.bat` FOOTGUN (found 2026-07-22):** its comment says `DIGEST_TO` is a "test-recipient
  override," but its VALUES are the production recipients (jtramontano + apain + acohen). Any manual
  dev run MUST explicitly override: `DIGEST_TO=<your own @acorninv.com address>` and `DIGEST_TO_TEAM=` (empty —
  which also triggers the §1a misconfig guard: FULL-only, memory frozen, digest chunks un-indexed —
  the correct state for a dev test run; a "Team config missing" line in the FULL email's grey
  "System notices" footer is expected — since 2026-07-28 it rides the digest footer, not a
  separate ⚙️ email, and never the red box). Loading `env.bat` from PowerShell: parse the `set` lines (see WORKLOG 2026-07-22) —
  bare `call env.bat` fails under `NoDefaultCurrentDirectoryInExePath`.

---

## 9. Change-spec history (Phases 0–3) — ✅ ALL DONE

The original phased refactor (Phase 0 cleanup → Phase 1 correctness/escaping → Phase 2 quality/cost
→ Phase 3 tests/consolidation) plus A1 cost accounting, A2 structured outputs, the Opus 4.8 upgrade,
and the §7.1 de-hardcoding are all committed and validated. Per-item detail and commit hashes:
the Session history's 06-19 → 06-30 digests, and WORKLOG's dated entries in git history
(`3965f7e`). Nothing here is open. *(Section kept as a stub to preserve §-numbering — code
comments cite §10/§11 by number.)*

---

## 10. Open coverage gaps (§13 residuals)

The 2026-06-30 → 07-14 source-coverage audit is closed. What remains:

- **13D session** will expire and need a **manual re-login** (interactive; unattended runs skip
  gracefully via the R8 guard and O3 flags the WILTW zero-streak). Procedure in OPERATOR_GUIDE.md.
- **Custom-domain Substack pubs ride the unauthenticated per-post API** (see §5) — accepted;
  degrades visibly if Substack ever closes the hole.
- **Substack account-email flip to the bot** — optional end-state that would remove the last
  jared-account dependency; his call, not built.

**Resolved (no action; history in WORKLOG 2026-06-30 → 07-14):** FRED provisioned + Fed-balance-sheet
series-label bug fixed; Substack cookie/renewal fixed (OTP flow) + 7 paid pubs added; forwarding
completeness (Bloomberg/Greenmantle flowing + attributed; Grant's absent, accepted); Octus
HY-new-issue (accepted, Stifel New Issue Flashes carry the color); FINRA TRACE (module removed —
never worked, $9k/yr for a 2-issuer watchlist).

---

## 11. Flagged / deferred — items that are open or intentionally not done

*(Everything considered-and-resolved has been removed from this list — it lives in WORKLOG + git.
What remains is only what a future session might still act on.)*

### A. Conditional — do only if a real problem appears (no evidence yet)
- **BBG-Data-License snapshot wishlist (2026-07-15, jared)** — snapshot metrics that have no clean
  free source; add if a Bloomberg Data License ever lands. In-code comment blocks mark the slots
  (`market_data.YAHOO_TICKERS`, `macro_data.FRED_SERIES` credit section). Grouped by what BBG buys:
  - **(i) Substituted — shipping today via a fragile free stand-in (BBG = a quality *and* robustness
    upgrade):** **HYG / LQD / IGLB / IGIB** ship as fund-reported **portfolio OAS** scraped from
    ishares.com (`ishares_data.py`, 2026-07-16). BBG would (a) swap **OAS → the wanted G-spread** —
    the precise metric jared asked for — and (b) replace the ishares.com **web scrape**, which can
    silently break if the page layout changes, with a licensed feed. So this row is both
    *approximate* and *fragile* today; BBG fixes both. This is the ONLY currently-shipping item here.
    *(2026-07-24, operator rule — "where the same asset appears at two lags, keep only the
    freshest": the ICE **broad HY and IG index OAS rows were both dropped** — `BAMLH0A0HYM2` +
    `BAMLC0A0CM` removed from `macro_data.FRED_SERIES` — because each sat next to its T-1
    fund-reported iShares twin (HY↔HYG, IG↔LQD) reporting a different spread a day later.
    **HYG and LQD (T-1) are now the digest's headline HY/IG spreads.** The ICE quality buckets
    (AAA/A/BBB/BB/B/CCC) stay T-2 with `**` markers — no T-1 substitute exists at that
    granularity. Revert note in the `FRED_SERIES` comment.)*
  - **(ii) Completely missing — no free source at all (BBG is the only way to get them):**
    - ~~**S&P BDC index (SPBDCUP)**~~ — *SUBSTITUTED 2026-07-23, jared-approved: the free daily
      **Cliffwater BDC Index** ships via `cliffwater_data.py` (labeled Cliffwater, never S&P).
      SPBDCUP itself remains paid-only; on a BBG cutover jared can choose to swap back.*
    - **BCRED '32 / ARCC '32 G-spreads**, **SpaceX '56 G-spread**, **Oracle '66 G-spread**,
      **QTS G-spread** — no free issuer-level spread source.
    - **CoreWeave '32 + Core Scientific '31 bond prices** — bond-level data = TRACE ($9k/yr,
      rejected 2026-07-13; FINRA's free per-CUSIP web lookup judged too fragile to scrape).

  *(SpaceX **equity** came off the list 2026-07-16 — it IPO'd June 12, 2026 (Nasdaq: SPCX) and is
  now a normal Yahoo row in the AI Snapshot.)*

  **Paid-data lane options (distilled from the retired `SNAPSHOT_UPDATE.md` §3.1, researched
  2026-07-23 — full comparison tables in git history):** three ways to buy the wishlist, none
  urgent, all jared's call:
  - **Lane A alone — FINRA TRACE Snapshot feed, ~$6k/yr** (BTDS + 144A sets, $250/mo each,
    once-daily file = exactly a morning digest's shape). T-1 *trade-print* prices for the wishlist
    bonds + computable G-spreads vs the Treasury.gov curve. Caveat: prints gap on illiquid names
    (no evaluated marks). NOTE: this re-prices HANDOFF's earlier "TRACE $9k/yr, rejected
    2026-07-13" — that sizing predates the fee-schedule read, and the rejection was against a
    2-issuer watchlist, not the full 7-bond wishlist; re-decide if wishlist visibility is wanted.
    **The recommended starting lane if anything is bought.**
  - **Cheap stack, ~$8k/yr** = Lane A + Databento CME Standard (~$2.1k/yr: live 8AM Treasury
    quotes via BrokerTec + index/WTI/SOFR futures; needs bond math in code). ~80% of the
    reader-visible value at ~40% of BBG's cost. Credit index OAS stays FRED T-2 (no cheap vendor
    exists for ICE/BBG index OAS — enterprise-only).
  - **BBG Data License, ~$20k/yr** = one vendor, turnkey: evaluated BVAL marks daily on every
    wishlist bond, true G-spreads for the ETF rows (replacing the ishares scrape), T-1 index OAS,
    live 8AM Treasuries. What the extra ~$12k buys over the cheap stack: evaluated-vs-print
    quality, index-OAS parity with terminals, one onboarding.
  Structural fact underneath all lanes: nothing makes the snapshots "live at 08:00" — most rows
  are T-1-or-worse at any vendor; DL's unique value is the wishlist + credit-index T-1.
- **`_assemble_digest_html` string-match insertion** — revisit only **if** archived digests show
  real section misplacement; the fix risks the tuned `SYSTEM_PROMPT` (§6). *(The numbering-collision
  member of this family was already fixed 2026-07-14 — appended sections are unnumbered.)*
- **PACER company-sizing search (`pacer._search_company_size`)** — Google scraping is fragile but
  degrades gracefully. Options if it ever breaks: a free-tier search API (e.g. Brave) or drop the
  web step. Low priority, low volume.
- **Index growth** — see §5 (F13 ladder + tripwire).
- **Repo reorg to a `src/` layout — parked indefinitely; runbook in git history**
  (`REORG_CHECKLIST.md`, retired 2026-08-07 — it read like pending work and it isn't; flat-at-root
  is a legitimate layout for a solo tool, and the reorg buys organization, not capability). What
  survives it: **Phase 0 is DONE and load-bearing** — `config.REPO_ROOT` (sentinel-walk anchor)
  is how all modules locate root state/secrets/`archive/`; never revert to
  `Path(__file__).parent` for those. If a future maintainer wants the reorg anyway: it is a
  coordinated code+server maintenance-window op, NOT a pull (entry points + `.bat` wrappers stay
  at root so tasks need no re-registration; stop the daemon, pull, smoke-test every entry point,
  restart, watch the next 08:00 run) — recover the full checklist from git history before
  attempting it.

### B. Watch → trigger → fix (implement only if the output says otherwise)
- **Cross-day "daily delta" (2026-07-23; VALIDATED live 07-27).** Three pieces keep the digest
  from repeating yesterday: `pacer._fresh_filing` (entries need a since-last-run pub date AND a
  current-year case number; January accepts prior year; unparseable over-includes),
  `digest._set_lookback_hours` (every source window = hours since the last digest file —
  Monday = 72h; also retunes `pacer.LOOKBACK_HOURS` per run), and
  `digest._previous_digest_block` (the prior TEAM digest rides as a shared content block —
  **deliberately NOT in `prompt`, which feeds alert evaluation**; the SYSTEM_PROMPT dated-framing
  rule leans on it).
- **PACER O3 signal = the RAW Ch.11 count (fixed 07-28, validated 07-30).** O3 watches
  `pacer_raw_ch11` (`pacer.raw_ch11_count()`, pre-filter, rerun-safe: raw>0 = feeds alive,
  raw=0 = actually dead) plus per-court `pacer_rss_<court>` keys (the aggregate can't see one
  court die — the txsb lesson, Post-mortem library). The filtered `pacer_entries` count is
  legitimately 0 most days — never re-point O3 at it. New keys self-calibrate (need
  `MIN_HISTORY` 3 runs; a court that starts dead never nags). If a court ever removes RSS
  permanently, the replacement lane is the PACER Case Locator API (~pennies/day, needs an
  account + a small module; CourtListener's free API rides the same feeds).
- **Snapshot-table data lag — CLOSED 2026-07-27** (fixes shipped + debut-validated: Treasury.gov
  T-1 rates, NY Fed SOFR, lag-honest footnotes, the freshest-only rule in §11.A; same-day rows
  at 08:00 = VIX/WTI/DXY/BTC/SK Hynix, everything US-listed = prior session — structural, not
  fixable free). Full investigation: `SNAPSHOT_UPDATE.md` in git history.
- **Repetition: the metric is a development yardstick, NEVER a production alert (operator
  ruling 2026-07-30).** Every run logs `Repetition: N strong + M weak` and appends to
  `repetition_scores.json` (metric v2 since 7/23: content-mandated sections excluded; noise
  floor 1–3 strong, clean-week ceiling 4; v1 entries ≤7/23 read high and aren't comparable;
  if the server ever ran `check.bat` before the 7/23 conftest fix, prune zero-score junk
  entries before reading the series). **The trigger for any future work is a READER saying
  "this feels repetitive" — never the score** (an unexplained number would train the operator
  to ignore footers). **Escalation ladder if that complaint ever comes** (the prompt lever is
  exhausted — residual signals are incidental mentions more rules can't remove; full spec in
  git history):
  1. ~~Deterministic tripwire~~ — **decided NO 2026-07-30** (above).
  2. **Idea 10 — gated Sonnet dedup pass 2.5** (~recurring spend, owner sign-off): the only
     lever that mechanically catches paraphrase/story-level echo; implementation sketch in the
     retired spec (git history).
  3. **Structural, jared's sign-off: Idea 15** (merge §4+§5 into §1–§3 — the residual
     collisions sit on those boundaries). **⚠ Attempted 2026-07-23 and REVERTED** — see the
     Post-mortem library (its durable residue is the truncation guard); retry preconditions in
     the retired spec. Alternative: §1 → pointer index (also jared's — §5/§1 are signature
     features).
  4. Fallback only: de-prescribe the rule stack to one editorial principle (2-week A/B).
  If tuning continues past that, the regex metric itself is the bottleneck — an LLM-judged
  score, but only if Idea 10 ships and disputes persist.
- **Ticker-name learned cache (`ticker_names_cache.json`, 2026-07-22).** Self-seeds from each run
  ("Ticker-name cache: learned N" log line; 12 entries after day one). Watch: a wrong issuer name
  appearing in a digest → inspect/delete the bad cache entry (the proper-noun + source-text guards
  should prevent this; one descriptive-phrase class was already caught and guarded in tests).
- **Paraphrase-level dedup / true MMR** in the reply path. Current dedup is token-Jaccard ≥0.85
  (near-verbatim twins only). Watch: reply answers feel repetitive from reworded same-story chunks.
  Fix: real MMR over candidate vectors (accept the `search()` return-shape change), or lower the
  Jaccard threshold.
- **Real company NER for entity tags.** Coverage is deliberately watchlist + `$TICK` + tracked funds
  only — "Wynn Resorts" spelled out is untaggable. Watch: entity-filtered retrieval or the story
  router repeatedly missing name-only entities. Fix: NER at index time (spaCy or a cheap model pass)
  + `--retag`.
- **`source_type` include-filter on `search()`.** Only the exclude side shipped
  (`exclude_source_types`). Watch: query understanding wanting "only filings / only ratings"
  retrieval. Fix: ~5 lines in `search._filter_ids` + a param.
- **Memory: one live watch line.** If `Memory pass tokens: N in + M out` shows `M` near
  **~14,000**, raise the 16k `max_tokens` (BOTH update calls in `memory.py`) or switch that call
  to streaming the same day — precedent: the 7/24 8k-cap truncation froze `memory.json` for a
  weekend (`stop_reason` keep-existing guard held; fixed `38a2f69`). Everything else about
  memory growth is **CLOSED and confirmed live 8/7**: the 30-day ager
  (`memory._age_stale_stories`, code-enforced) fired 7/31 exactly as designed and runs
  routinely; the store ramps toward a ~300–400-active equilibrium (~10 new/day × ≥31-day
  lifetime) at which every cost stays bounded — prompt context is budget-capped (60/45k),
  update INPUT grows ~25k tokens (trivial on Sonnet), and OUTPUT scales with stories *changed*
  per day, not store size. The ~90-day archive-to-side-file batch is NOT needed — reconsider
  only if the aged store materially exceeds ~400 active. (The resolved-ids index tail is a
  2027 concern, noted in `_story_index_for_prompt`.)
- **Parked retrieval mechanisms (rerank / hybrid)** — see §6. Re-test kit: `tools/eval_retrieval.py`
  + `tools/eval_golden.json` (29 questions; grow the golden set as archive days accrue —
  cadence rule in §2a: grow it whenever you touch the project).

### C. Declined at the 2026-07-15 second-pass review (recorded so they aren't re-derived)
- **F7 weekly-wrap token diet** (~$35/yr EV): DEFERRED — quantify first with the free `count_tokens`
  endpoint, and only ship bundled with a permissioned Friday ride-along (wrap template adherence may
  derive from SEEING the digest HTML).
- **F8 alert-eval cross-variant prompt-cache share** (~$25/yr): DECLINED — restructures a §6-adjacent
  prompt for marginal EV.
- **F9 extract Gmail auth/send into `gmail_utils.py`**: DECLINED as churn (satellites importing
  `digest` is deliberate).
- **F10 hoist Haiku news-ranking out of `build_news_html`**: DECLINED (never move it into the free
  `python news.py` path). *SUPERSEDED 2026-07-22 (REDUCE_REPEATS Idea 13): the hoist happened —
  ranking moved to `main()` so news renders per variant with digest-dedupe filtering — but F10's
  rationale is fully respected: ranking stays in digest.py's paid path, `news.py` untouched.*
- **F11 FULL/TEAM variant loop in `main()`**: DECLINED — explicitness is valued (§2); every branch
  is pinned.
- **F4 pin a CA bundle** instead of the unverified-SSL contexts for Treasury/CFTC: cosmetic; do
  opportunistically if ever touching those fetchers.
