# Work Log

Running log of everything done in the Daily-Digest refactor, phase by phase (newest on top).
Companion to `HANDOFF.md` (the plan/spec) and its §11 "Needs Testing" (deferred verification).

---

## Current state (2026-07-22 evening — soak day 2 GREEN; big dev session committed; SERVER PULL PENDING)

**Soak day 2 GREEN** (Wed 7/22 08:00: both variants delivered, no changelog leak — pass-2 fix's
live check passed; watchdog silent). Then a large dev session (see the 2026-07-22 entry below) —
all committed on `main`, `ruff` clean, `pytest` **395** — whose headline items: digest generation
switched to **Claude Fable 5**; ticker glossary; bolded lead words + ticker-name pairing; **TL;DR
box removed**; PACER embedded-link fix; REDUCE_REPEATS Bundle 1 (anti-repetition prompt rules +
`repetition.py` metric + WSJ/FT dedupe). **⚠ The server had NOT pulled these commits at session
end — Thu 2026-07-23 08:00 is the biggest-change debut run since deploy.** Read it closely; check
the `Repetition:` log lines and the ~2x cost lines. The block below is the 7/21 deploy-era state,
kept for the S4U/stored-password findings.

---

## 2026-07-22 — Soak day 2 GREEN; Fable 5 switch; glossary; format overhaul; anti-repetition Bundle 1

**Morning verification (read-only, $0):** 7/22 08:00 production run verified via the bot's Sent
mail — both variants delivered 08:08 ET (TEAM 66,852 chars / FULL 68,461), **zero "Changes made:"
occurrences** (pass-2 leak fix live check PASSED), no FAILED/MISSING alerts. Soak day 2 GREEN.
Side finding: HANDOFF said "Daily Research Digest" but the *subject* is "📬 Daily Inbox Digest"
(the H1 differs from the subject by design) — HANDOFF clarified.

**Snapshot fixes (committed AM):** Market Snapshot footnote mis-attributed the HYG/LQD Portfolio
OAS mirror rows to FRED — footnote now built from the extras actually present (`" · FRED"` only
when a FRED extra landed; `" · Portfolio OAS rows = fund-reported (ishares.com)"` when iShares rows
did; `_build_yahoo_table` gained `note_suffix`). AI Snapshot gained NVDA / TSM (ADR) / INTC / MU —
all four verified live via Yahoo (free). Color semantics documented: green/red = good/bad move
(VIX, spreads, claims inverted); grey dash = no data; grey number = zero change; yields-up-green
and 2s20s-steepening-red are known quirks, deliberately left.

**Digest format overhaul (prompt, 2 paid test runs + fixes):** (1) every bullet in §1–9 now opens
`<strong>Topic:</strong>` (bolded lead word; entity leads use the FULL ticker form); (2) Market &
Macro forbids restating snapshot levels without analysis (section omitted if nothing qualifies);
(3) every cited ticker carries the issuer name in parens when the name is in the sources — the
no-guessing guard stays for unknowns. First Opus test run was perfect; second regressed to bare
`COF:` leads → rules tightened (tickers ALWAYS $-prefixed, incl. lead position) + pass-2 format
check. **TL;DR box REMOVED later in the day (operator)** — all 5 references excised; digest opens
at §1; pass 2 actively deletes any summary box a draft emits.

**Ticker glossary (`ticker_names.py`, new):** solves "$TICK (Name)" for bond-desk shorthand
($BRASKM, $VMED…) without weakening anti-hallucination. Prompt gains a TICKER GLOSSARY block built
from (a) SEC `company_tickers.json` titles via the new non-downloading `sec_filings.company_names()`
and (b) a learned cache (`ticker_names_cache.json`) of digest-rendered pairs validated against that
day's source text (+ proper-noun guard — Fable once wrote "$SDZSW (potential USD issuer)"; rejected
by tests now). **Cache-write discipline:** `collect()` only stages; `main()` `commit()`s once AFTER
both variants — a write between them would fork the TEAM/FULL shared cache prefix. Substack-only
tickers ride a supplemental glossary in the FULL tail (mapping = public metadata, so
Substack-learned pairs legitimately serve future TEAM digests). Cache self-seeds: 12 entries day 1.

**Fable 5 switch (digest generation only):** `config.FABLE_MODEL="claude-fable-5"` →
`digest.CLAUDE_MODEL`; alerts/13D/reply stay Opus. Two required fixes discovered by test runs:
(1) Fable returns thinking blocks first — `content[0].text` crashed; new `digest._response_text()`
selects text blocks by type (3 call sites: pass 1, pass 2, weekly); (2) `cost.py` had no Fable tier
— added ($10/$50 per MTok, exactly 2x Opus, from the authoritative API reference); unknown ids now
default to the fable tier (most-expensive safety). Real run cost ~$2.9 vs ~$1.3 on Opus (thinking
tokens bill as output). Fable's digest quality: format adherence at least as good; one behavioral
wobble (name-in-prose instead of "$TICK (Name)") fixed via rule tightening.

**PACER fix:** PACER RSS descriptions embed an `<a>` doc-link that rendered as escaped literal
markup in the 7/22 production email ("looks like a href didn't render") — descriptions now
`strip_html()`-ed at the two storage sites; Ch.11 detection still runs on raw text.

**Anti-repetition (REDUCE_REPEATS_SPEC.md, new — the active spec):** measured baseline (signals in
2+ sections, same day): Opus 13/87 (8 involving Top Takeaways), Fable 8/91 (worst: $CRWV told in 3
sections). 15 ideas specced with a decision checklist; spec cross-checked against the codebase
(5 corrections, incl. a no-TL;DR-guard-location trap). **Bundle 1 BUILT:** (12) `repetition.py`
metric — strong (ticker/bps/$) vs weak (bare %) split after the smoke test exposed percent-collision
false positives + a "50% inside 10.50%" substring bug, scores logged per run + persisted to
`repetition_scores.json`; (1+2+5+9) one batched prompt revision — plan-first line, SECTIONS ARE
EXCLUSIVE IN ORDER (earliest-wins), `<em>(→ §N)</em>` cross-ref device, pass-2 checklist reordered
DEDUPLICATE-first; (13) WSJ/FT appended-section dedupe — Haiku ranking hoisted to `main()` (F10
letter superseded, rationale respected — see HANDOFF §11.C), `build_news_html(articles,
exclude_text)` drops headlines the variant's own digest already covers ($TICK / proper-noun bigram /
≥60% token overlap), per-variant rendering. **Smoke test PASS ($2.89):** template intact, no plan
leak, no TL;DR, 3 working cross-refs, 6/15 headlines dropped; same-day strong dupes **2→1** (the
survivor: $CRWV with different facts per section — legitimate two-angle coverage). Bundle 2 decision
deferred ~1 week pending live scores (deliberately — attribution + Fable over-prescription risk +
not stacking more change onto the 7/23 debut run).

**Test-run harness note (dev box):** `env.bat`'s `DIGEST_TO` contains PRODUCTION recipients despite
its "test override" comment — every test run this session overrode `DIGEST_TO=acohen@acorninv.com`
+ `DIGEST_TO_TEAM=` (empty ⇒ misconfig guard ⇒ FULL-only, local memory/index frozen — the correct
dev-test state). `call env.bat` fails under the agent shell's `NoDefaultCurrentDirectoryInExePath`;
the working pattern parses env.bat's `set` lines in PowerShell. 4 paid test runs total today
(~$8.3): Opus format check $1.26/$1.28, Fable first run $1.48-report/​~$2.7-real (pre-tier-fix),
Bundle-1 smoke $2.89; two $0 failed launches (env loading).

**State:** `pytest` 360 → **395** (**+35**: footnote/ticker tests, glossary, thinking-block, cost
tiers, repetition metric, news dedupe); `ruff` clean; all committed on `main` by operator. Dev-local
side effects (inert): archive/index/digests for 7/22 overwritten by test runs; `substack_memory`
delta'd; shared `memory.json` untouched (guard). **Server pull pending → 7/23 debut.**

---

## Deploy-era state (2026-07-21, first unattended run GREEN — the server is LIVE)

**The §7.2 server deploy is COMPLETE, the first unattended cycle passed, and all post-deploy rollout
is done.** The dedicated Windows box (`ShawnArmstrong`) is the sole instance, running unattended:
**four** scheduled tasks registered and Ready (MorningDigest / Watchdog / Backup / ReplyMonitor —
MiddayAlert was removed 2026-07-21), the reply daemon polling, the pass-2 changelog-leak fix deployed
and verified live. **Tue 7/21 08:00 MorningDigest fired
unattended and delivered BOTH variants; the 09:00 Watchdog stayed silent (operator confirmed no
"DIGEST MISSING" email).** This was the first run with nobody driving — the whole point of the
dedicated server — and it passed. Only the multi-day **soak** remains. *(The `DEPLOY_PROGRESS.md`
live-resume doc was retired/deleted 2026-07-21 — deploy done; its content is folded into this block +
the 7/20/21 entries and preserved in git history.)* Full 7/20 cutover sequence + the S4U finding below.

**What's LIVE on the server:**
- Code on `main` at `d75a923` (latest; server pulled) — includes the `-StoredPassword` fallback, the
  `-u` reply-log fix, the O4 backup code, the pass-2 changelog-leak fix, the snapshot-footnote
  cleanup, the midday-alert removal, and the alerts↔`sec_filings.WATCHLIST` binding. `ruff` clean,
  `pytest` **360**; working tree clean, nothing unpushed. Memory 87 active after the 7/21 run.
- Secrets in place via Plan B (dev token pair copied — no interactive mint; MFA lockout never
  cleared and was routed around entirely). 13D session live (probe: no login redirect).
- **Four** tasks under a **stored-password** principal (NOT S4U — see the finding below):
  MorningDigest 08:00 / Watchdog 09:00 / **Backup 09:45** / ReplyMonitor at startup
  (MiddayAlert 13:00 was removed 2026-07-21 — see that entry). `DIGEST_UNATTENDED=1` machine-wide.
  First on-demand O4 backup ran clean (54.9 MB, `FAIL=0`) into `%OneDriveCommercial%\DailyDigest-Backup`.
- Monday manual run GREEN, $2.03; Tue 7/21 first unattended run GREEN (both variants, watchdog
  silent), two-pass $0.88 team + $0.68 full.

**BRANCH: work on `main` (2026-07-20).** `ava-updates` existed only to keep refactor work off
`main` while Jared ran production from `main`; Jared's retired and the server tracks `main`, so
**`main` is now the working/authoritative branch.** `ava-updates` is frozen/behind — don't use it;
deletable at will.

**DONE this session (2026-07-20):** cutover (see the entry below); watchdog drill (routed to
acohen, drill email arrived — failure-alert path works); O4 backup built (`run_backup.bat` +
5th `Backup` task 09:45 + `backup` alert label; STATE ONLY, secrets excluded — validated; into
`%OneDriveCommercial%\DailyDigest-Backup`); unbuffered reply-monitor log (`run_reply_monitor.bat`
`-u`, live-confirmed after restart — `Gmail authenticated.` now visible); OPERATIONS.md gained a
"Backups & restore" section. Repo confirmed NOT in OneDrive (no live-sync corruption, no secret
auto-upload). `ruff` clean, `pytest` **362** green.

**SERVER TODOs (2026-07-21) — ✅ BOTH DONE:**
1. ✅ Pulled the 7/21 run state (numbers in the GREEN-run entry below: memory **87 active / 8
   resolved / 95 total**; two-pass $0.88 team + $0.68 full). The pull surfaced the pass-2
   changelog-leak bug — fixed, see its entry below.
2. ✅ **Pass-2 fix DEPLOYED + O4 Backup task registered.** Operator committed + pushed the fix
   (`df29a59`); server `git pull` (fast-forward), `_strip_to_html` verified live on the box
   (stripped a synthetic changelog). `setup_tasks.ps1 -StoredPassword` (needed an **elevated**
   window — a non-elevated run hit `Register-ScheduledTask: Access is denied`) registered all
   **five** tasks incl. `Backup`; ReplyMonitor stayed `Running`. First on-demand Backup ran clean —
   6-block robocopy `FAIL=0`, **54.9 MB** into `%OneDriveCommercial%\DailyDigest-Backup` (`archive`
   incl. the index, `digests`, `logs`, all state JSONs). *(Note: the backup set also includes
   `logs\` — benign, non-secret, useful history; slightly broader than the "state-only" phrasing in
   the specs.)* Server has **no `ruff`/`pytest`** in its venv (dev-only deps, not in
   `requirements.txt`) — so `check.bat` can't run there; validate server code by importing the
   module directly.

**REMAINING — post-deploy (none blocks the live system):**
1. ✅ **Cleanups DONE (2026-07-21):** dev-Desktop `state_sync_2026-07-20.zip` → Recycle Bin;
   local `ava-updates` branch deleted (`40f7afe` confirmed already in `main`). **`origin/ava-updates`
   still exists remotely** — delete with `git push origin --delete ava-updates` (operator; agent
   pushes blocked) or just ignore it.
2. ✅ **`OPERATIONS.md` handed to jared** (operator-confirmed 2026-07-21).
3. **Soak** — the free live confirmation of the pass-2 fix is the **Wed 7/22 08:00** run (team
   digest should have no `**Changes made:**` block). `DEPLOY_PROGRESS.md` already retired/deleted
   2026-07-21 (deploy done). Drop `acohen` from `DIGEST_TO_TEAM` at the 2026-07-31 departure.

Live watches (detail in `HANDOFF.md §11.B`): memory active-count climbing **73 → 82 → 87** (7/17 / 7/20 /
7/21; budget trims, rendered 58 of 82 — M<N expected); first natural 30-day aging batch ~7/30 is the
archival decision point (operator still present); resolved-story re-creation ride-along clean so far.

---

## Alerts now bind "watchlist" to the real `sec_filings.WATCHLIST` (2026-07-21)

Two of the 7 alert triggers say "watchlist names" / "a watchlist company", but `evaluate_alerts`
only ever passed the trigger prose + source text to Opus — so "watchlist" was whatever the model
inferred, **unbound** to the concrete `sec_filings.WATCHLIST` (the ticker universe that already
drives SEC filings, earnings, and entity tagging). Closed the gap: `evaluate_alerts(source_text,
watchlist=None)` injects a "WATCHLIST DEFINITION" clause listing those tickers when the caller
passes them, and `digest.py` passes `sec_filings.WATCHLIST` on **both** the FULL and TEAM
evaluations. Net effect for the handoff: the SEC/earnings fetchers and the watchlist-scoped alerts
now key off **one list** — a semi-technical successor edits `sec_filings.WATCHLIST` in one place and
both respect it. Prompt building was extracted to `_build_alert_prompt` so the binding is
unit-tested with **no Claude call** (`tests/test_alerts.py`, 3 tests: clause present when a list is
passed, absent when None/empty). Triggers that don't mention "watchlist" (Large Chapter 11, HY
spread blowout, Fed surprise, Bank failure, Distressed exchange) are unaffected. No new Claude call —
just ~16 more tickers (~40 tokens) in the existing alert-eval prompt. `ruff` clean, `pytest` **360**
(357 + 3). $0.

---

## Removed the midday alert entirely (2026-07-21)

Operator decision — "no one wants it." Deleted the whole feature: `midday.py`, `run_midday.bat`,
`tests/test_midday.py`, and the `MiddayAlert` 13:00 task from `setup_tasks.ps1`. Nothing in
production code imported midday (only tests did), so it was a clean leaf removal. Also: dropped
`midday` from `run_alert.py`'s valid labels; scrubbed midday mentions from `config.py` / `cost.py` /
`digest.py` comments; retargeted two tests off the `midday` label (`test_run_alert` →
`backup`/`reply_monitor`, `test_search` self-artifact fixture → a failure-alert subject); removed the
one midday test in `test_team_digest`. Forward-facing docs updated (README / HANDOFF / MAINTENANCE /
OPERATIONS) — the README + OPERATIONS task tables also gained the previously-missing **`Backup`** row
in the process. Historical WORKLOG midday mentions left as-is (dated record; module in git history).

Kept: `archive/<today>/digest_sent_at.txt` — the O2 watchdog reads it (its comment was midday-flavored,
now corrected). Task count **5 → 4** (MorningDigest / Watchdog / Backup / ReplyMonitor). `ruff` clean,
`pytest` 364 → **357** (7 midday tests gone). **$0 — no Claude.**

**SERVER ACTION REQUIRED** (a `git pull` alone does NOT deregister it): `setup_tasks.ps1` only
adds/updates tasks, so the `MiddayAlert` task stays REGISTERED on the box until removed by hand.
After pulling, run once (elevated): `Unregister-ScheduledTask -TaskPath "\DailyDigest\" -TaskName
MiddayAlert -Confirm:$false`. (Otherwise it fires at 13:00, fails to find the now-deleted
`run_midday.bat`, and dies silently — harmless but untidy.)

---

## Post-deploy tidy-ups — doc prune + snapshot-footnote cleanup (2026-07-21)

Two small post-deploy cleanups after the first unattended run; both **$0 (no Claude)**, committed +
pushed + pulled on the server.

**1. Doc set pruned to 5 core docs (commit `435cb15`; `ava_refactor.md` deleted by the operator).**
Retired/deleted — all preserved in git history, intent folded into HANDOFF: `DEPLOY_PROGRESS.md`
(cutover-resume doc, job done → §1 + the 07-20/21 entries); `NEXT_STEPS_SPEC.md` (roadmap all ✅ +
deploy executed; live watch items → §1 / §11.B; deploy record → these WORKLOG entries); the
completed-track specs `CLEANUP_SPEC` / `CLEANUP_REFACTOR_SPEC` / `TEAM_DIGEST_SPEC` (→ §1 "Retired
specs" + §1a + §9); and `ava_refactor.md`. All cross-references rewired to tombstone notes — no
dangling forward pointers (only dated historical WORKLOG mentions remain, which is correct). **Live
doc set: README, HANDOFF, MAINTENANCE, OPERATIONS, WORKLOG.**

**2. Snapshot table source footnotes collapsed (commit `0fba811`).** The footnotes under the Snapshot
tables (`market_data._build_yahoo_table`, `macro_data._build_fred_table`) grouped tickers by each
instrument's own `as_of` date and enumerated raw symbols, so whenever timestamps diverged (common —
different exchanges/time zones/staleness) the line fragmented into ticker soup, e.g. `Yahoo Finance:
^GSPC ^VIX, as of 2026-07-21 | Yahoo Finance: DX-Y.NYB, as of 2026-07-20 | FRED: DGS20 (2026-07-18)`.
Collapsed to a single `Source: <sources>, as of <latest date>` (rows already name each instrument).
Sources precede the date; the Corporate Credit table's OAS **definition** trails as a note *after* the
date (operator chose "option B"): `Source: FRED · Yahoo Finance, as of <date> · OAS = ICE BofA index
option-adjusted spreads; Portfolio OAS rows = fund-reported (ishares.com)`. `_build_fred_table` gained
a `note_suffix` param to separate source-before-date from definition-after-date. **Deterministic
formatting only** — no SYSTEM_PROMPT, no LLM path, no runtime behavior change. `ruff` clean, `pytest`
**364** (`test_market_macro` pins the new format); previewed live via a snapshot-only test email to
acohen ($0).

---

## First unattended run GREEN (2026-07-21)

The first fully-unattended automation cycle on the server passed — nobody driving, the tasks fired on
their own:
- **08:00 MorningDigest** delivered **both variants** to production (operator confirmed receipt).
- **09:00 Watchdog** stayed **silent** — operator confirmed no "🚨 Daily Digest MISSING" email in the
  `acorn.research.bot@gmail.com` inbox, i.e. the watchdog found `archive/2026-07-21/digest_sent_at.txt`
  fresh and correctly did nothing (silent success is the pass condition).

This closes the `NEXT_STEPS_SPEC §5` cutover item "confirm the first unattended 08:00 run end-to-end".

**Live run numbers (pulled off the server 2026-07-21 — TODO #1 DONE):** server `memory.json` is
`last_updated 2026-07-21`, **87 active / 8 resolved / 95 total**. Active-count trajectory
**73 (7/17) → 82 (7/20) → 87 (7/21)**, climbing as the §5 watch predicted; first natural 30-day
aging batch still ~7/30 (operator present). The run's two `Memory context` main-store lines were
**byte-identical** — `45,246 chars / 58 of 82 active` — so cache determinism held; `58 of 82` is the
budget trimming (M<N expected, watch item #2). Substack store line `32,991 chars / 36 of 36`.
Post-run deltas: main `22 updated / 5 new / 0 resolved -> 87 active`; substack
`4 updated / 2 new / 0 resolved -> 38 active`. Cost: two-pass **$0.88 (team) + $0.68 (full)**;
`Excluded 1 Substack-origin email` logged on both variants; no "Team config missing". (This dev
laptop's `memory.json` stays frozen at 7/17 — 73/8/81 — until O4 backups sync server state off-box.)

**BUT the sent team digest carried a bug — see the next entry.** The pull also surfaced that pass 2
leaked its edit changelog into the team variant's HTML; fixed, deployed, and verified live 2026-07-21.

---

## Pass-2 review changelog leaked into the sent team digest — FIXED (2026-07-21)

**Symptom (operator-reported):** the bottom of today's TEAM digest email showed a messy raw-markdown
block — `**Changes made:** - **Fixed error:** … - **Added missed detail:** …` — that didn't render
(HTML email, markdown source). Confirmed on the box: `digests\2026-07-21_team.html` ends
`…</ul>\n</div>\n\n**Changes made:**\n- …`; the FULL variant (`2026-07-21.html`) ended clean at
`</div>` with no changelog.

**Cause:** the two-pass flow's pass 2 ([digest.py](digest.py) `summarize_with_claude`) prompts Opus
with a numbered review checklist (find missed items / fix errors / remove repetition / produce a
final enhanced version). Opus *sometimes* also appends a plain-English summary of the edits it made,
**after** the digest's closing `</div>`. `_strip_to_html` only dropped a *preamble* (everything
before the first `<div`) — it never trimmed trailing content, so the changelog rode into the sent
email. Per-variant nondeterministic: pass 2 volunteered it for TEAM but not FULL on the same run
(each variant runs its own 2-pass). Cosmetic — no data/privacy leak (Opus's own edit notes, not
source content) — but it reached production recipients (jtramontano/apain/acohen).

**Fix — two layers (belt & suspenders), $0 (offline, no Claude call):**
1. **Prompt:** added an explicit final instruction to pass 2 — *"Output ONLY the final digest HTML
   … begin at the opening `<div>` and end at the final `</div>`. Do NOT append any preamble,
   sign-off, commentary, or summary/changelog of the changes you made."* Reduces the odds and the
   wasted output tokens.
2. **Defensive strip (the reliable layer):** `_strip_to_html` now also truncates trailing chatter —
   it keeps text from the first `<div` through the **last HTML closing tag** (`re.finditer(r"</[a-zA-Z][a-zA-Z0-9]*>")`).
   Matching the last closing tag (not the last `>`) is deliberate: the real leak's changelog
   contained `>` ("Japan >$180B repatriation"), so a naive last-`>` cut would keep most of it. Added
   `import re`. Generic across templates, so the weekly wrap (shares the helper) is covered too.

**Tests:** two regressions in `tests/test_weekly_summary.py` — the exact 2026-07-21 trailing-changelog
leak, and a non-`</div>`-terminated template with trailing chatter (weekly-wrap guard). `ruff` clean,
`pytest` **364** green (was 362). Verified against the real server byte pattern: output == the clean
`</div>`-terminated doc, changelog gone, real bullets kept.

**DEPLOY — ✅ DONE (2026-07-21):** committed + pushed (`df29a59`), pulled on the server, and
`_strip_to_html` verified live on the box (stripped a synthetic changelog, returned the clean
`</div>`-terminated HTML). Landed in the same server session as the O4 Backup registration. Free
live confirmation is the Wed 7/22 08:00 run — the team digest should carry no `**Changes made:**`
block.

---

## Server cutover COMPLETE — S4U failed on AzureAD, stored-password fallback (2026-07-20)

Executed the §7.2 cutover on the server (`ShawnArmstrong`, `C:\Users\ShawnArmstrong\code\Daily-Digest`).
The system is now LIVE and unattended. Sequence, in order:

- **Code sync (step 0):** merged `ava-updates` → `main` (merge `00b0ab7`; pre-flight caught that
  `origin/main`'s only "unique" commit was the 7/15 PR-merge `1a64778`, carrying no code — clean),
  pushed, `git pull` on the server (fast-forward). `ruff` + **362 tests** green on `main`.
- **State re-sync (step 2):** secrets-free zip (archive + both memory stores + caches +
  `pacer_seen`/`source_counts` + digests; 32.5 MB) → moved via the bot Drive → extracted on the
  box. Verified byte-for-byte against dev: index 9,449 chunks, 12 days (6/30→7/17), memory 73
  active, 8 recorded runs, `wiltw_cache` carries 2026-07-16 (→ free WILTW hit Monday).
- **Secrets (step 3), Plan B — MFA lockout never cleared, routed around:** the bot Google account
  stayed MFA-locked (72h) the whole cutover; the operator DID get a live browser session (backup
  codes generated; recovery phone confirmed = a teammate staying past 7/31, so Friday's
  "recovery phone changed" alert was benign own-activity, not compromise). The durable production
  token was NOT re-minted on the box — instead the dev `credentials.json` + `token.json` PAIR was
  copied over (Drive, delete-after-download). Free Gmail smoke test: `authenticated as
  acorn.research.bot@gmail.com`, no browser → Plan B confirmed: refresh-token auth works straight
  through the lockout. `substack_cookie.txt` + `thirteen_d_session.json` (dev's known-good) copied
  too; server `env.bat` deliberately NOT overwritten (its recipients are already production-correct).
- **13D recheck (step 4):** headless Playwright probe loaded the copied session, navigated to the
  latest report — no login redirect → session live on the box (also validated headless Playwright).
- **Manual run (step 5), GATE cleared:** credit topped up first. `run_digest.bat` GREEN, $2.03:
  both variants to production (FULL → jtramontano, TEAM → apain+acohen; one transient SSL send-retry
  that recovered), WILTW 7/16 cache hit, cross-variant cache engaged (full pass 1 paid 37 uncached
  tokens), no "Team config missing", memory 73→82 active, substack 34→36, index → 10,468, memory
  render `59 of 73` (budget trimming as designed).

**THE FINDING — S4U task launch fails on the AzureAD-joined server; use `-StoredPassword`:**
`setup_tasks.ps1` (S4U principal) REGISTERED all four tasks fine, but the scheduler then silently
**refused to launch** them — `Start-ScheduledTask` returned no error yet `LastRunTime` stayed at
the `11/30/1999` sentinel with `LastTaskResult 267011` ("not yet run"), no process, no log. This is
the AzureAD/S4U risk the script header always flagged, now confirmed live. Fix: added a
**`-StoredPassword`** switch to `setup_tasks.ps1` (commit `6793009`) that re-registers the SAME
`AzureAD\ShawnArmstrong` account with a stored password (prompted once via `Get-Credential`)
instead of S4U — same run-whether-logged-on behavior, same user so the per-user Playwright/Chromium
+ HuggingFace caches stay valid (SYSTEM would lose those and break 13D). Re-ran
`setup_tasks.ps1 -StoredPassword` (Shawn entered his password); the launch test then PASSED —
ReplyMonitor → State `Running`, `LastRunTime` today, `LastTaskResult 267009` (running), log created.
Since all four tasks share the principal, this proves the 08:00 MorningDigest will fire tomorrow.
**Operational note for the next person: the server's tasks run under a stored password. If they
ever need re-registering, use `setup_tasks.ps1 -StoredPassword` (needs Shawn's password), NOT the
bare S4U default.**

**Also this session:** found the reply-monitor daemon's log stays empty (Python block-buffers
stdout to a file and the daemon never exits to flush) — fixed with `-u` in `run_reply_monitor.bat`
(the other three wrappers exit and flush fine); the running daemon picks it up on its next restart.

---

## Interim runs 7/16–7/17 GREEN; credit exhausted; Gmail-alerts filter; MFA lockout extended (2026-07-17, written 2026-07-20)

**Fri 7/17 interim run (manual `run_digest.bat`, ~12:43–12:52) — GREEN, exit 0, $3.72 (12 calls).**
Both variants delivered (FULL → jtramontano+acohen; TEAM → apain+acohen); FULL weekly wrap
generated, saved (`digests/weekly_2026-07-17.html`), and sent. First-run watch list results:
- **WILTW resumed:** 2026-07-16 report fetched via the dev 13D session, Opus-summarized ($0.87,
  the day's cost driver), cached under `2026-07-16`, PDF archived + indexed. O3 recorded
  `wiltw = 1` — its first nonzero data point, so the O3 WILTW blind spot (MAINTENANCE §4) is
  closed going forward. ⚠️ The dev fetch may have collided with the SERVER's 13D session if 13D
  is single-session — recheck on the box (cutover step 4).
- **Memory context budget ACTIVATED for the first time** (as predicted 7/16): `44,700 chars /
  58 of 64 active stories` — 6 stalest dropped; the two main-store lines byte-identical and the
  cross-variant cache held perfectly (team pass 1 wrote 65,482 tok; full pass 1 paid **37**
  uncached tokens + wrote only its 20,103-tok substack tail).
- **Substack-via-email boundary live-exercised** (watch item #7): `Excluded 1 Substack-origin
  email(s)` logged; team digest clean.
- **No resolved-story re-creation** (item #1): 9 new stories, none restating the 8 resolved ids.
- Deterministic ordering held: PACER commit + O2 completion marker written after the last send
  (12:51:32); index +1,183 → 9,449 vectors; memory delta 19 updated / 9 new → **73 active**;
  substack store → 34 active; alerts 2/7 both variants; no "Team config missing"; no self-artifacts.

**CREDIT EXHAUSTED on the run's FINAL Claude call:** the TEAM weekly wrap failed
`400 — credit balance is too low`. Non-fatal by design (try/except → exit 0), so **no failure
alert was emailed** — the only signals were the log line and apain's missing team weekly.
Operator decision: do NOT regenerate the team weekly. **Top-up is a hard blocker before the
Monday server run** (any Claude call fails until then; a digest run would crash at pass 1 —
that WOULD fire the failure alert, whose Gmail-only path still works).

**Google security alerts were being ingested as digest source email** (found investigating the
lockout): 5 on 7/16 + 4 on 7/17 from `no-reply@accounts.google.com` / `no-reply@google.com`
(the operator's own MFA-lockout attempts). The sent 7/17 FULL digest carried an Opus note —
"possible account-compromise attempt, worth verifying" — correct editorial behavior, but system
noise (heads-up for jared: that was the operator fighting the lockout, not a compromise).
**Operator decision (2026-07-17): Gmail filter → "Gmail Alerts" label, skipping the inbox**
(both sender domains). Trade-off accepted: the digest no longer surfaces bot-account compromise
alerts; OPERATIONS.md points jared at the label instead (that doc + NEXT_STEPS §5 updated —
the filter is account-side, nothing to re-create on the server).

**MFA lockout extended 48h → 72h** — repeated interactive sign-in attempts reset the window;
still locked Mon 7/20 morning. Mitigations recorded: stop retrying (each attempt can extend);
first post-expiry attempt from the dev machine (a device Google trusts for this account), not
the server; if any browser still holds a live bot session, generate **backup codes** from it
(also satisfies the MFA-must-be-team-owned item). **Plan B for the cutover, README-sanctioned:**
copy the dev `credentials.json` + `token.json` pair to the server over a non-email channel
(USB / corporate share / password-manager send — never the bot-Gmail zip, per the 7/15
secrets-never-emailed guardrail). The server then authenticates by refresh alone; its unused
new OAuth client stays in Cloud Console (delete neither client).

**Memory-growth data point + decision:** active stories 57 → 64 → 73 across three runs; the
context budget is now actively trimming. The **archival-to-side-bank idea was considered and
DEFERRED** (operator + review, 2026-07-17): it's the wrong lever for ACTIVE-count growth (only
8 resolved stories exist; archival tidies the resolved tail), it would weaken the resolved-ids
anti-recreation guard unless archived ids stay in the Sonnet index, and deploy week is the worst
time for a model-visible memory change. Decision point: **~7/30, when the 30-day aging gets its
first natural batch** (operator still present). Cheaper levers if aging doesn't bend the curve:
`STALE_DAYS` 30→~21, or a stricter "materially advances" bar in the delta prompt.

**The second-pass cleanup (`CLEANUP_SPEC.md`) is COMPLETE** — 5 stages + the
audit-gap and index-side-filter follow-ups, all committed ("cleanup spec stage
1..5" + two follow-up commits). `ruff` clean, `pytest` **349** green;
retrieval-eval baseline **hit@1 0.897 / hit@3 1.0 / MRR 0.937, zero misses**
(`2026-07-15_post_index_filter.json` — improved over 0.862/0.966/0.917: the
self-ingested reply artifacts had been suppressing real sources); **$0 Claude
spend across the whole track.** Durable outcomes: the TEAM privacy boundary is
code-enforced end-to-end (post-activation env guard + index-side digest skip +
fetch/index self-artifact filters + Substack-via-email exclusion); the receiving side is **@acorninv.com
only** (bot removed as recipient — self-ingestion loop killed); reply access is
config-driven (answerable = exactly the digest recipients; full tier =
jtramontano alone); memory contexts are budget-bounded (byte-identical today)
with a per-run size log; chunk_ids unique (were 208 dup chunks); O3 arms next
run and now catches partial failures + substack full-text collapse; deploy +
cutover checklist (NEXT_STEPS §5) and OPERATIONS.md (the jared runbook) exist.

**REMAINING (in order):**
1. **Finish the §7.2 server deploy — IN PROGRESS (started 2026-07-15; see
   `DEPLOY_PROGRESS.md`).** Staged on the box; blocked ~48h on a Google MFA lockout.
   Dev laptop covers interim runs (Thu/Fri), Monday 7/20 cutover, Tue 7/21 first
   automation. Operator's LAST WORK DAY is 2026-07-31 — resume promptly (the
   accrual-week precedent: live operation surfaced ~8 failure modes nothing else did).
2. **Apply the first-run watch list (NEXT_STEPS §5 subsection)** to the next
   natural run — especially the resolved-story re-creation ride-along (memory
   3.1) and the memory size log; both stay live watches through ~mid-August
   (the 30-day aging's first batch was pulled forward to 2026-07-15 for soak —
   4 stories resolved via the real path, then `STALE_DAYS` restored to 30 — so
   the re-creation ride-along is live on the NEXT run; see the 2026-07-15 entry).
3. **Push** — the branch is ahead of origin (operator pushes).
4. Optional, parked in HANDOFF §14.G: the F7 weekly-diet `count_tokens`
   quantification (standing $0-call permission); the F22 HANDOFF consolidation
   as its own later docs pass.

---

## SpaceX equity added to the AI Snapshot — it IPO'd (2026-07-16, follow-up 3)

Operator caught a stale assumption: SpaceX is no longer private — it **IPO'd June 12, 2026 on
Nasdaq as SPCX** ($135 offer, ~$1.77T — largest IPO ever; post-dates the assistant's knowledge
cutoff, verified via web + Yahoo). `SPCX` added to `YAHOO_TICKERS` (AI section, "Share price",
$135.94 live at add time, 21 trading days of history — the 1M change reaches back exactly to the
IPO, which only works because of today's `>= 21` off-by-one fix). Removed "SpaceX equity" from
the BBG wishlist (code comment + HANDOFF §14.A); the SpaceX **'56 G-spread** stays on it
(bond-level). pytest **362** green.

## HYG/LQD added to the iShares OAS fetch — credit table + Market Snapshot mirror (2026-07-16, follow-up 2)

Operator asked whether other BBG-wishlist items were recoverable from alternative sources.
Findings: **HYG (250.05 bps) and LQD (82.00 bps)** report the same page-embedded portfolio OAS as
IGLB/IGIB — added to `ishares_data.FUNDS` (operator decision: BOTH the Corporate Credit table AND
a Market Snapshot mirror via `MARKET_FRED_EXTRAS`, which now carries FRED + iShares series ids;
digest passes `macro_data + ishares_oas` as the mirror source list). **Still unavailable:** S&P
BDC index (publisher page bot-blocked, 403); bond-level items (FINRA's free per-CUSIP lookup =
fragile JS scraping + DIY G-spread math — declined); SpaceX (private). Credit footnote now reads
"Portfolio OAS rows = fund-reported (ishares.com)". Live-verified both tables; pytest **362**.

## IGLB/IGIB: price rows replaced with fund-reported Portfolio OAS (2026-07-16, follow-up)

Jared wanted the IGLB/IGIB rows changed to **reported G-spread**. Double-checked: no free ETF
G-spread source exists (the iShares characteristics data has no G-spread field — it's a Bloomberg
analytic; stays on the §14.A BBG wishlist). Shipped the operator-approved substitute instead: the
**Option Adjusted Spread each fund reports on its own ishares.com product page** (verified live:
IGLB 94.54 bps, IGIB 86.28 bps, as-of Jul 15 2026 — embedded HTML-escaped JSON, plain GET, no
auth). New module **`ishares_data.py`** (fetch → macro-shaped credit rows, metric "Portfolio OAS"
+ prompt formatter); registry row `ishares_oas` (O3-counted automatically); rows render after the
FRED index-OAS rows in the Corporate Credit Snapshot with an ishares.com footnote credit; IGLB/
IGIB removed from `YAHOO_TICKERS`. **Change columns accrue:** the site shows only the current
value, so 1D/1W/1M come from a local history cache (`ishares_oas_cache.json`, gitignored, pruned
at 60 days, keyed by the site's as-of date — same-day reruns don't self-compare). 1D populates
from day 2, 1W after a week, 1M after a month; added to the deploy copy + O4 backup lists.
Fallback if iShares ever blocks scraping: FRED's ICE BofA maturity-bucket OAS
(`BAMLC7A0C1015Y`/`BAMLC8A0C15PY` ≈ IGLB; `BAMLC3A0C57Y`/`BAMLC4A0C710Y` ≈ IGIB) — free, daily,
with history. 8 new tests (parse/history/rows/failure); pytest **362** green.

## Snapshot tables gained a Metric column (2026-07-16, follow-up)

Operator feedback in two rounds: (1) table values ("272 bps", "5.09%", "$48.95") didn't say WHAT
metric each row reports; (2) packing the metric into the name column read as crowded — make it a
separate column between the name and 1D. Final shape: **Name | Metric | Level/Current | 1D | 1W |
1M** in every snapshot table. Rows carry a `metric` field (in `YAHOO_TICKERS` / `FRED_SERIES`
tuples + the derived/BKLN-yield rows): Yield, Curve spread, Breakeven inflation, Real yield
(TIPS), Overnight rate, Index OAS, ETF price, Share price (KRW), 12M dist. yield, Index, Price.
Names reverted to clean instruments ("HY", "10Y", "ARCC (Ares Capital)"); the prompt formatters
emit "label + metric" so the short names stay unambiguous to Opus ("10Y Breakeven inflation" vs
"10Y Real yield (TIPS)"). Robustness: `MARKET_FRED_EXTRAS` and the derived-row insertion anchors
now key on `series_id` (labels are no longer unique). No formatter/monitor keys on labels
(verified: only the VIX/BTC/S&P/"Claims" switches, all untouched). pytest **354** green;
live-verified rates order + preview emailed to acohen.

## 20Y UST mirrored into the Market Snapshot (2026-07-16)

Operator request (jared): 20Y Treasury in the Market Snapshot IN ADDITION to the Rates Snapshot.
Yahoo has no 20Y index ticker, so the Market table embeds the FRED `DGS20` row — the reverse of
the credit table's Yahoo-row embedding: new `macro_data.table_rows_html` (extracted from
`_build_fred_table`), `market_data.MARKET_FRED_EXTRAS = ("20Y UST",)` +
`build_market_table_html(data, fred_data=None)`, FRED provenance appended to the table footnote.
Also today: **first live run with the new format — GREEN** ($1.78; all six snapshot tables
rendered; 0 cross-section near-dupes at the J≥0.30 scan that caught 1–2/day before; §7 Bloomberg
correctly shrank to non-covered items; TEAM leak scan clean; none of the 7 new memory stories is a
resolved-story restatement). **Next-run watches:** memory budget activates (64 active > 60 — expect
`60 of 64` and eyeball once); WILTW 7/16 posts late-Thursday → Friday run picks it up. `ruff`
clean, pytest **354**.

## Digest-format updates: anti-repetition prompt + snapshot redesign + a latent market-data bug (2026-07-15, later session)

Two operator-requested format changes (jared's feedback), plus a real bug found while validating.
`ruff` clean, **pytest 353** (349 → 353). $0 Claude spend — all validation was offline tests +
free Yahoo/FRED fetches rendered to a local HTML file.

**1. Cross-section repetition (commit `5ee7397`).** Jared flagged the digest as repetitive across
sections. Measured on the sent 7/14 + 7/15 digests: near-verbatim restatements ($CRWV in §3 AND §7
at 0.67 token-Jaccard; $HCA in §1 AND §3), and §5 Contrarian re-narrating stories from §1/§2 (4 of
5 bullets on 7/15). Three prompt-only fixes (no template/HTML change, so the §6 string-match
assembly and team/full cache sharing are untouched): a NO-REPETITION-ACROSS-SECTIONS rule in
`SYSTEM_PROMPT` (one home section per story; later sections give only a genuinely-new angle in one
line; TL;DR exempt); §7 Bloomberg restricted to items NOT already covered in §1–6; a repetition
check added to the pass-2 review instruction. **Live watch on the next run:** confirm consolidation
happened and Opus didn't over-consolidate (§5's new-angle value should survive).

**2. Snapshot section redesign (jared's spec).** Old layout: Market Snapshot / Macro Dashboard /
Fed BS / Treasury Auctions tables. New layout: **Market** (S&P, VIX, WTI, DXY, BTC — Gold dropped)
→ **Rates** (2Y/10Y/20Y/30Y, 2s20s, 10Y+30Y breakevens, 10Y+30Y reals, SOFR — FRED, incl. new
DGS20/DFII10/DFII30 + derived rows) → **Corporate Credit** (HY/IG/AAA/A/BBB/BB/B/CCC OAS via the
FRED ICE BofA series — the free analogs of the Bloomberg LF98/LUAC/… tickers jared listed — plus
Yahoo IGLB/IGIB rows) → **Private Credit** (RTY, ARCC, OTF, BKLN + its trailing yield) → **AI**
(Nasdaq, SK Hynix, Oracle, CoreWeave) → **Fed BS** (moved to bottom of snapshots) → earnings
calendar. Macro Dashboard + Treasury Auctions tables REMOVED, but their data still feeds the Opus
prompt (operator decision — §2 prose keeps citing CPI/claims/auctions);
`build_macro_table_html`/`build_auctions_table_html` deleted as dead code (repo convention).
Mechanics: FRED series + Yahoo tickers carry a `section` tag; `macro_data._build_fred_table` /
`market_data._build_yahoo_table` render per-section; the credit table embeds Yahoo rows via
`market_data.table_rows_html`. `_assemble_digest_html` re-pinned (params + order) in
`test_assemble_digest.py`; new formatting/section tests in `test_market_macro.py`.
**BBG-DATA-LICENSE WISHLIST (no free source — operator wants these if a license ever lands;
in-code comments at the section definitions):** HYG/LQD G-spreads; S&P BDC index (SPBDCUP);
BCRED '32 + ARCC '32 G-spreads; SpaceX equity + '56 G-spread; Oracle '66 G-spread; QTS G-spread;
CoreWeave '32 + Core Scientific '31 bond prices. (Bond-level data = TRACE, evaluated and rejected
at $9k/yr on 2026-07-13; SpaceX is private — DXYZ proxy considered and declined.)

**3. Latent off-by-one in `market_data` 1M lookback — FOUND + FIXED.** `if len(series) >= 20:
series.iloc[-21]` throws IndexError at exactly 20 rows, and the per-ticker silent except then
drops the ENTIRE row. On 2026-07-15 a `period="1mo"` download returned exactly 20 US trading
days, so **every US-listed ticker (including S&P 500) silently vanished** — the bug predates the
redesign and would have hit the original 6-ticker table the same day. Guard corrected to `>= 21`
(the `>= 15` fallback covers 15–20). Found because the redesign's validation render came back 6
rows instead of 16; a loud-except instrumented run pinpointed the line. Also added: one
unthreaded retry pass for tickers whose batch download comes back empty (defense against Yahoo
partial-batch failures — cheap, no-op when nothing is missing).

**O3 note for the next run:** `market_data` counts jump 6 → ~16 and `macro_data` ~12 → 24
(new series + deriveds). Increases can't fire the zero-streak/floor alerts, but don't be
surprised by the new baseline in `source_counts.json`.

**Deploy implication:** these commits are on `ava-updates` only. The server cloned `main` @
`1a64778` — **merge to main + pull on the server BEFORE the Monday 7/20 cutover** (step added to
`DEPLOY_PROGRESS.md`).

## Server deployment STARTED — staged on the box, blocked on a 48h Google lockout (2026-07-15)

Began the §7.2 deploy on the dedicated Windows server (user `ShawnArmstrong`,
`C:\Users\ShawnArmstrong\code\Daily-Digest`, cloned from `main` @ `1a64778`). **Full live status +
resume steps live in `DEPLOY_PROGRESS.md`** — this is the narrative.

**Staged on the server:** Python **3.12.7** venv (the box shipped with 3.13; installed 3.12 to match
the pinned env) + deps + Playwright; the ~9-day state transferred via a bot-Gmail zip and verified
(`search.py` returns ranked hits → torch/faiss/embedder + the index all work on-box); a **new OAuth
Desktop client**'s `credentials.json` (Google no longer allows re-downloading an existing client's
secret); `env.bat` (Anthropic + FRED + `DIGEST_TO_TEAM=apain,acohen`; `DIGEST_TO` unset →
jtramontano). Free smokes (news.py, search.py) pass.

**Blocked:** enabling **MFA** on the bot Google account triggered a ~48h interactive-login lockout →
can't mint the server `token.json` yet. Refresh tokens survive it (the dev laptop still reads/sends —
probe-confirmed). The substack cookie waits on the token (OTP reads the inbox; self-renews first run).

**Decisions:** Jared decommissioned (server = sole instance); recipients FULL→jtramontano /
TEAM→apain+acohen (drop acohen at 7/31); secrets **regenerated on-box, never emailed** (a safety
guardrail blocked bundling secrets for email — correctly); FRED key reused as a static value; 13D
logged in on both server + dev (possible single-session collision → recheck Monday; needs Jared's
paid creds). ⚠️ **MFA must be team-owned, not on acohen's device** (acohen leaves 7/31) or the team
loses bot-account re-auth.

**Plan:** dev laptop runs manually Thu 7/16 + Fri 7/17 (fully staged — token/13D/substack all valid);
**Monday 7/20 cutover** (stop dev → re-sync state dev→server → mint token → manual run →
`setup_tasks.ps1`); **Tue 7/21 first automation**. Dev is the authoritative state during the interim;
the cutover re-sync makes the server continue from Friday's state, not the stale 7/15 snapshot.

---

## Substack-via-email leak into the TEAM digest — FOUND + FIXED (2026-07-15)

Surfaced while eyeballing today's forced-run alert box (a deep-check the run
itself passed). `ruff` clean, `pytest` **349** green (+6).

**The leak.** The TEAM digest is meant to be Substack-free, but paid Substack
newsletters ALSO arrive as inbox email (PETITION from petition@substack.com; 6
more from no-reply@substack.com today). The team exclusion only covered the
substack.py SCRAPER layer (substack_articles=[]), so those emails flowed into the
team source, the team digest (PETITION's Serta Simmons LME analysis appeared in
apain's copy — alert box + a "Distressed / Credit Movers" item + a "Worth Reading"
link), and the index (322 email chunks were team-retrievable). FULL was unaffected
(it includes Substack anyway).

**Fix (boundary now enforced at the email layer too):**
- `config.is_substack_email(*senders)` — True for @substack.com / *.substack.com in
  From or effective_from (forwarded ones carry it in effective_from). Custom-domain
  pubs emailing from their OWN domain are a documented residual (extend
  `_SUBSTACK_EMAIL_DOMAINS` if observed).
- `digest.summarize_with_claude` drops Substack-origin emails from the shared prompt
  prefix + PDF loop (BOTH variants filter identically → cached prefix stays
  byte-identical → cross-variant cache preserved; FULL still gets Substack via the
  scraper block). Fixes the team alert eval for free (its source_text is that prefix).
  Logs "Excluded N Substack-origin email(s)".
- `search._chunks_for_date` tags Substack-origin email chunks source_type="substack"
  so team retrieval's exclude_source_types drops them like scraped chunks.
- `midday._fetch_new_emails` drops them too (the midday alert reaches team recipients).
- **Re-indexed 2026-07-15** (only day with substack senders): 322 email chunks
  retagged email→substack (PETITION 82, no-reply Substack 240); 0 substack-sender
  chunks remain "email"; index steady at 7,241 (metadata-only → vectors + the
  retrieval-eval baseline unchanged). Index backed up first.
- New `tests/test_substack_email_boundary.py` (6 tests: predicate incl. forwarded +
  negatives; index tagging incl. forwarded).

**Trade-off (accepted):** a Substack that emails the inbox but ISN'T in the scraper's
SUBSCRIPTIONS is now dropped from the FULL prompt too (PETITION IS scraped, so no loss;
the no-reply items were largely noise). The digest-prompt filter is live-exercised on
the NEXT run (watch list §5, new item 7). The already-SENT 7/15 team digest to apain
can't be recalled — heads-up if PETITION access is sensitive.

---

## 13D session-save guard + WILTW-is-Jared's-paid-account finding (2026-07-15)

Follow-up during the day's forced validation run (see the "Day's context" note
at the end). `ruff` clean, `pytest` **343** green (+7); $0 Claude for the code/tests.

**Incident.** A `thirteen_d.py --login` — run to refresh the 13D session before
the server deploy — surfaced two things: (1) the 13D account is **Jared's PAID
subscription** and the operator has no credentials; no free/bot-email account can
substitute (WILTW is gated behind the paid sub). (2) The login attempt (ENTER at
the prompt without actually logging in) **overwrote the valid session with an
unauthenticated one** — `thirteen_d_session.json` went from {visitrack, user} to
{visitrack} only. No backup exists (gitignored, not archived), so the prior
session is unrecoverable from disk. Impact bounded: the digest skips WILTW
gracefully (1 of ~17 sources) until Jared runs a real `--login`.

**Hardening (so the clobber can't recur).** `thirteen_d._save_session` now
refuses to write unless the state is authenticated — `_looks_authenticated`
requires a `user` auth cookie with a value — and never overwrites an existing
session with an unauthenticated one. It's the single save chokepoint, so it
guards both the manual-login path and the download-path saves. `_do_manual_login`
reports honestly ("Login complete" only on a real save). Same defensive shape as
the substack `_check_session` fix. The `user`-cookie assumption is documented
with its SAFE failure mode (won't clobber; would merely stop persisting if 13D
renames the cookie). New `tests/test_thirteen_d_session.py` (7 tests: authed
save, anonymous refuses + keeps existing, no-file case, empty/None states).

**Docs.** OPERATIONS.md + MAINTENANCE.md now state the 13D re-login needs Jared's
paid-account credentials (no free/alternative account); MAINTENANCE distinguishes
`Report not found` (publishing break — session fine) from `Session expired`
(dead), and flags the O3 blind-spot on a long WILTW zero-streak. NEXT_STEPS §5:
the pre-deploy secrets line marks the copied session as unauthenticated, and a
Cutover step spells out getting Jared to `--login` on the box.

**Day's context.** Forced manual `run_digest.bat` — GREEN, $1.96, both variants
to the intended recipients (FULL → jtramontano+acohen; TEAM → apain+acohen; env
recipients set for this run; apain added to `DIGEST_TO_TEAM`). First-run watch
list all clean: re-creation N/A (0 resolved that run, 10 genuinely-new stories);
the two main-store memory lines byte-identical (39,491 chars / 51 of 51); no
self-artifacts archived; no "team config missing"; O3 armed at 6 runs with the
new `substack_fulltext` count; market_data back to 6; cache engaged (team wrote /
full read); index +1,286 → 7,241; PACER committed after send. Aging pulled
forward for soak: `STALE_DAYS` 30→14 fired the first batch via the real
`_age_stale_stories` (resolved the 4 six-30 stories: tungsten, fsk-kkr,
big-tech-230, alamos-gold), then **restored to 30** — memory.json now 57 active /
8 resolved. WILTW "gap" explained: 13D Q2 publishing break, next report 7/16.

---

## Index-side self-artifact filter — the Stage-2 residual RESOLVED, archive untouched (2026-07-15)

Operator-approved follow-up (chosen over scrubbing the archive, for fidelity:
the raw record must keep showing exactly what the 7/14 runs ingested). `ruff`
clean, `pytest` **336** green (+1).

- **`config.is_self_artifact`** — the 2.5 predicate moved from digest.py to
  config so the INDEXER can share it (search can't import digest — circular);
  `digest._is_self_artifact` + `digest.BOT_ADDRESS` re-exported, all existing
  callers/tests unchanged.
- **`search._chunks_for_date` skips self-artifact emails at index time** —
  defense in depth behind the fetch guard, and the retroactive clean for days
  archived before the guard existed. Positional email ids preserved
  (enumerate-and-skip, so untouched emails keep archive-aligned chunk_ids);
  pinned incl. archive-file-not-rewritten.
- **Re-indexed 2026-07-14:** 1,484 → **1,372** chunks (112 artifact chunks
  gone; index 6,067 → 5,955; verified 0 artifact chunks remain). **Eval
  IMPROVED — new baseline: hit@1 0.897 / hit@3 1.0 / hit@5 1.0 / MRR 0.937,
  zero misses** (snapshot `2026-07-15_post_index_filter.json`; was
  .862/.966/.917). The artifacts were measurably polluting retrieval:
  blue-owl-otic now finds the FT redemption story at rank 1 instead of the
  reply quote. The scratchpad `emails_2026-07-14_prescrub.json` backup is now
  moot (nothing was modified) and can be discarded.

---

## Cleanup Stage 5 — docs & deploy readiness (CLEANUP_SPEC 5.1–5.3) — TRACK COMPLETE (2026-07-15)

Docs only (no code); `ruff` clean, `pytest` **334** green re-verified. **The
second-pass cleanup track is COMPLETE — all 5 stages, $0 Claude spend.**

- **5.1 — deploy + cutover checklist appended to NEXT_STEPS_SPEC (new §5)** —
  the F1 deliverable: pre-deploy secrets/state lists (incl. the durable
  token.json, `DIGEST_TO_TEAM` + `SUBSTACK_EMAIL` env, do-NOT-copy
  credentials_JARED.json), on-box validation (check.bat, setup_tasks.ps1 as
  admin, the 13D skip drill, one manual green run), the **CUTOVER step that
  was missing everywhere** (disable jared's machine's tasks + reply monitor
  same-day — exactly ONE reply daemon; recipients @acorninv.com only), and
  post-deploy (O4 backups incl. both memory stores + wiltw/pacer/counts
  state; watchdog drill; hand OPERATIONS.md to jared).
- **5.2 — `OPERATIONS.md` (new)** — the jared-facing one-pager: what each
  alert email means (incl. the new "Team config missing" and "Source
  degradation" signals), the three manual fixes (13D re-login, Substack
  cookie paste, API credit top-up at ~$45–55/month), task-scheduler basics,
  and the index-growth slow-burn note for a future developer.
- **5.3 — HANDOFF reconciliation:** §1 records the track (307 → 334 tests) +
  the pick-the-deploy-date call-to-action (operator's last day 2026-07-31);
  §5 gains the custom-domain-Substack leak-dependency risk; §14.B gains the
  F13 index-growth plan (measured slope, ~3–8-month ceiling, escalation
  ladder, 30–50k-vector tripwire); §14.F's memory-growth watch item marked
  BOUNDED IN CODE; new **§14.G** records the review's declined/deferred items
  (F7 count_tokens-first + standing $0-call permission, F8/F9/F10/F11
  declined, F22 → separate pass) so they aren't re-derived. README's env.bat
  sample now includes `DIGEST_TO_TEAM`. CLEANUP_SPEC got its completion
  banner (both residuals named: the 3.1 ride-along watch + the pending
  archive-scrub decision).

---

## Cleanup Stage 4 — small cleanups (CLEANUP_SPEC 4.1–4.5) (2026-07-15)

`ruff` clean, `pytest` **334** green (+1 net); free eval spot-run after the
reconstruct swap: **metric-identical** (0.862/0.966/1.0/0.917). No Claude spend.

- **4.1 — BM25 build is lazy** (`search._get_bm25`): hybrid is parked
  permanently (§14.F), yet every index-state reload tokenized all ~6k chunks
  and built the corpus. Now built on first `hybrid=True` use, cached per
  state; the §14.F mechanism is intact (eval `--hybrid` still runs).
- **4.5 — vectorized subset scan:** `_search_vectors`' allowed-ids path uses
  `index.reconstruct_batch` (per-id loop kept as fallback) — the exclusion
  filters pass nearly-full id lists, so this was the first thing to degrade
  on the F13 growth curve. Exactness pinned by the existing subset tests.
- **4.2 — `substack_fulltext` O3 count:** articles with real full text
  (neither preview-flagged nor paid-only-failure) recorded alongside the
  total — a Substack leak-closure (the custom-domain pubs are cookie-blind
  and leak-dependent) now shows as a fulltext zero-streak. Known limit,
  accepted: a PARTIAL custom-domain-only degradation stays above zero and
  relies on the in-digest preview markers.
- **4.3 — `substack_memory.json` snapshotted daily** into `archive/<date>/`
  (parity with memory.json; the indexer never reads either).
- **4.4 — tooling:** stale `test_send.py` .gitignore entry dropped;
  `check.bat` added (ruff + pytest, the stage gate as one double-clickable
  command; note: from git-bash invoke as `.\check.bat`).

---

## Cleanup Stage 3 — memory bounds (CLEANUP_SPEC 3.1–3.3) (2026-07-15)

`ruff` clean, `pytest` **333** green (+6). No Claude spend; the one
model-visible change (3.1, Sonnet delta input only) rides along on the next
natural run — watch its delta for resolved-story re-creation.

- **3.2 — self-activating context budget (replaces the review's
  park-and-watch tripwire, which the 2026-07-31 deadline broke):** the two
  near-duplicate context renderers consolidated into `_render_story_context`
  + `_story_block`; selection is most-recently-updated within
  `MEMORY_CONTEXT_MAX_STORIES = 60` / `MEMORY_CONTEXT_MAX_CHARS = 45_000`,
  RENDERING keeps store order, stable-sorted (deterministic — the
  cross-variant prompt cache requires byte-equal contexts). Budgets sit above
  the live stores (51/39,491 main, 28/25,060 substack — re-measured at
  implementation), so day-one output is **verified byte-identical on the real
  store** (exact char counts + determinism checked live; format pins green).
  When a store outgrows the budget, stalest-updated stories drop first — the
  ones the 30-day aging would resolve days later anyway. No watcher needed.
- **3.1 — resolved stories → ids-only in the Sonnet story index** (the
  §14.F.F3-4 specified fix; trigger observed: memory-pass input 10,344 →
  11,816 tokens 7/09→7/14). Saves ~nothing today (4 resolved / ~278 chars) —
  it is the forever-bound on the resolved tail, which starts growing when
  aging begins (~7/30, post-handoff). Ids are topic slugs, so the
  don't-recreate semantics survive; revert = re-append the topic.
- **3.3 — per-run size log:** "Memory context: N chars / M of K active
  stories" prints on every render — growth is visible in every digest log on
  the unattended server (and gives OPERATIONS.md a checkable number).

---

## Cleanup Stage 2 — correctness guards (CLEANUP_SPEC 2.1–2.5) (2026-07-15)

`ruff` clean, `pytest` **327** green at stage close (+13). Free rebuild + eval gate
included; no Claude spend.

- **2.1 — post-activation TEAM leak guard (code-enforced, was a docs note):**
  `TEAM_ACTIVATION_DATE` set + `DIGEST_TO_TEAM` empty now ⇒ loud warning, a
  "Team config missing" alert IN the sent email, `update_memory` skipped
  (store can't be re-contaminated), and `search._chunks_for_date` skips that
  day's digest chunks (raw sources still index). Escape hatch documented in
  config.py: deliberate team retirement must unset `TEAM_ACTIVATION_DATE`.
  Pinned via the Stage-1 main() harness + 3 new `_chunks_for_date` tests
  (post-activation skip / pre-activation fallback / guard-off).
- **2.2 — chunk_id collisions FIXED + index rebuilt + eval gate PASSED:**
  substack ids gain a per-article ordinal, filing ids a per-filing ordinal
  (the old scheme collided for same-author articles and same-ticker/form
  filings — 79 dup ids / 208 chunks live, silently dropping distinct chunks
  from reply context via the chunk_id dedup). Pre-rebuild index backed up
  (scratchpad `index_backup_prechunkids/`); full `--rebuild` → **6,067 chunks
  / 9 days, dupes now 0**; eval **metric-identical** (0.862/0.966/1.0/0.917,
  zero misses; snapshot `2026-07-15_post_cleanup_ids.json`). Uniqueness pinned.
- **2.3 — reply allow-list config-driven + access trims (operator directives
  2026-07-14):** new `_reply_query()` builds the Gmail `from:` clause from
  FULL_ACCESS_SENDERS ∪ DIGEST_RECIPIENTS ∪ TEAM_RECIPIENTS (a new team
  recipient is answerable automatically — was 3 hardcoded addresses).
  `FULL_ACCESS_SENDERS` trimmed to **jtramontano@acorninv.com alone** (jared's
  gmail: kept unanswerable by choice; the bot: 2026-06-29 slot-swap artifact).
  jared's gmail stays in FORWARDER_ADDRESSES (attribution, not access).
- **2.4 — partial-degradation floors (O3):** `EXPECTED_MIN = {market_data: 6,
  macro_data: 12, fed_bs: 6}` — same streak shape keyed on below-floor, zero
  rule takes precedence (no double signal). Would have caught the observed
  2026-07-14 one-of-six-tickers day. +5 tests.
- **2.5 — self-ingestion guard (found answering "why is the bot a recipient?"):**
  the bot REMOVED from both production recipient defaults (digest.py +
  run_alert.py — operator policy: **@acorninv.com only on the receiving
  side**), killing the latent loop where server self-sends land in the inbox
  the digest reads as a source. Belt-and-braces `_is_self_artifact` filter in
  `fetch_recent_emails` + midday's fetch (bot sender OR digest-subject —
  covers digests, alerts, and humans' replies-to-digests, two of which were
  observed ingested in `archive/2026-07-14/emails.json`). Policy pinned
  (defaults @acorninv.com-only; filter tests incl. the [FULL] marker and
  pass-through for forwards/OTP mail).
- **⚠️ Residual for operator decision:** the two already-archived reply
  artifacts (7/14 `emails.json`) remain in the archive/index — one quotes the
  FULL digest, so its chunks are team-visible as source_type="email". Scrub =
  filter the day's emails.json (backup already in scratchpad
  `emails_2026-07-14_prescrub.json`) + re-index the day; NOT done — archive
  mutation was outside the committed spec (permission denied, correctly).

---

## Cleanup Stage 1 — test pins first (CLEANUP_SPEC 1.1 + 1.2) (2026-07-14)

Additive pins landed BEFORE Stage 2 touches `main()`. `ruff` clean, `pytest`
**314** green (+7: two new test files; one mechanical extraction in midday).

- **1.1 — `tests/test_digest_main.py` (+2):** the real `main()` driven with every
  external effect stubbed + recorded, pinning the unattended-critical wiring for
  both configurations (team-active and full-only): `commit_seen` strictly AFTER
  the last send (F1a-4); the O2 completion marker absent at every send/commit
  moment and present by run end; the team variant generated FIRST (cache
  prefix); shared memory fed the TEAM assembled html when the team variant
  exists, the FULL one otherwise; per-variant alert evals (full source first);
  O3 counts recorded exactly once. Two pin corrections made during writing —
  the tests originally assumed `update_memory` receives the raw model html (it
  receives the ASSEMBLED html) and that midday strips leftover separator chars
  without a `<div` anchor (it doesn't; pinned as-is).
- **1.2 — midday parse extraction + `tests/test_midday.py` (+5):** the
  result-parsing block moved verbatim from `main()` into a pure
  `_parse_alert_result(result)` (subject from last pre-separator line;
  no-separator 60-char fallback; strip-to-`<div`); behavior byte-identical, now
  pinned incl. the leftover-`=` quirk.

---

## Docs sync before cleanup (2026-07-14)

Docs-only pass by a fresh session after a full project read (every module/test/tool/wrapper/
spec); no code changes. Re-verified before asserting: `ruff` clean, `pytest` **307** green,
golden set = 29 questions, current eval baseline **hit@1 0.862 / hit@3 0.966 / hit@5 1.0 /
MRR 0.917, zero misses** (`2026-07-14_2026-07-14_f3_refresh.json`). The 11 outstanding
commits were pushed by the operator before this pass. Reconciled:

- **HANDOFF §1:** status line 277 → **307** tests (2026-07-14); the three §14.B cosmetic
  watch items marked FIXED; new 2026-07-14 paragraph added (forwarding-visibility fix,
  numbering fix + `[FULL]` marker, F3 refresh 26 → 29 questions + the re-baseline above);
  the §13 gaps wording now reads CLOSED.
- **HANDOFF §7.1.8:** the stale "sender/mailbox flip NOT done / plan-only" block marked
  ✅ SUPERSEDED (the flip executed 2026-06-30; only the optional Substack *account*-email
  flip remains open, jared's call).
- **HANDOFF §4/§7.1/§7.2 + README:** "magic-link" wording → OTP-code / one-time login code
  (matches the 2026-07-14 renewal rework).
- **HANDOFF §14.B:** the three cosmetic nits closed with what fixed each; 3.5a notes the
  numbering family is fixed while the string-matching mechanism stays wait-and-see.
  **§14.F:** golden-set count 26 → 29.
- **NEXT_STEPS_SPEC:** Abnormal allowlist 🔄 submitted → ✅ CONFIRMED 2026-07-13 in the F1
  track row (+ the F1a runbook line); the F1 row's "Remaining" list now carries the full
  on-box install items (fresh cookie, substack_memory.json, `DIGEST_TO_TEAM`/`SUBSTACK_EMAIL`
  env, 13D skip drill).

Two live observations recorded for the next session (no action taken): the 2026-07-14 run's
`market_data` count was **1 of the usual 6** (likely a one-off Yahoo flake — nonzero, so O3
can't flag it; eyeball the next run's Market Snapshot), and O3 is one run from arming
(5 of ~6 recorded).

---

## Substack auto-renewal FIXED (OTP-code flow) — the "automated" claim was false (2026-07-14)

Operator asked to run the expired-cookie renewal drill (spec option (a): capture the browser
code-login, then fix). The drill proved Substack auto-renewal **never worked** — the docs'
"renewal AUTOMATED 2026-07-13" claim was aspirational (wired, never exercised against the live
API). Diagnosed → reworked → live-validated end-to-end. `ruff` clean, `pytest` **307** green.

**What was broken (found by the drill, invisible to inspection):**
- `_request_magic_link` POSTed `/api/v1/login` — Substack's PASSWORD endpoint, which now 400s
  "Please enter a longer password".
- Substack's passwordless flow no longer sends a clickable magic LINK; it emails a **6-digit
  verification CODE** ("NNNNNN is your Substack verification code", no URL in the body), so the
  URL-regex `_find_magic_link_in_gmail` (filtered on `subject:sign`) could never match.
- `_complete_login` was a **FALSE POSITIVE**: it saved whatever `substack.sid` sat on the session,
  but Substack sets an ANONYMOUS substack.sid on every request — so it "succeeded" while saving a
  dead cookie (the same masking that hid the 2026-07-13 outage; the first drill fetched 6 articles
  yet `/profile/self` on the saved cookie was 401).
- The finder could grab a **STALE code** (the inbox holds several within the hour) → `/complete`
  returned 400 "Invalid Code".

**The fix (`substack.py`, live-validated):**
- `_request_login_code` → `POST /api/v1/email-login` (confirmed 200; sends the code).
- `_find_login_code_in_gmail(since_epoch=)` → searches `from:no-reply@substack.com` (dropped
  `subject:sign`), pulls the 6-digit code from the subject via new `_extract_otp_code`, and only
  accepts an email NEWER than the request (kills the stale-code bug).
- `_complete_login` → `POST /api/v1/email-otp-login/complete` {code,email,redirect}; saves the
  cookie ONLY if `/complete` returns 200 AND the session then passes the real `/profile/self`
  probe (kills the false positive — fails loudly otherwise).
- Endpoints confirmed from jared's browser Network capture (`/email-otp-login/complete` + payload)
  and probes (`/email-login` 200; `/email-otp-login` 404; `/api/v1/login` 400 password).
- `tests/test_substack.py` +5 (`_extract_otp_code`: subject, body-fallback, non-code-email
  rejection, no-digits, empty).

**Live proof:** expired-cookie drill (garbage cookie planted) → "Login code email sent" → fresh
code read from the bot inbox (jared's auto-forward preserves the original From, verified) →
`/complete` → a **fresh cookie that authenticates via `/profile/self` from a clean session**
(True; the first false-positive drill returned False here). Confirms `/email-login` is the correct
request endpoint — the earlier 400 was purely a stale code.

**Notes:** jared's `no-reply@substack.com` → bot auto-forward is set up + operator-confirmed
(2026-07-14). A 429 "too many login emails" was hit mid-testing from ~6 probe requests in an hour
— NOT a production risk (real renewal fires ~once per cookie expiry, weeks/months apart; ≤1/day
even if failing). Manual `substack.sid` paste stays the documented fallback; O3 flags a zero-streak
if renewal ever fails. HANDOFF §1/§13 corrected. Left the machine on a freshly-renewed, verified
cookie; scratchpad holds pre-drill backups.

---

## Forwarding-visibility fix (3 stages) + numbering-collision fix — SHIPPED (2026-07-14)

Built the 3-stage forwarding fix (spec drafted, code-reviewed against the codebase —
caught a circular-import blocker + two overstatements before building — operator-approved)
so forwarded emails are SEEN and ATTRIBUTED by the morning digest, closing the two §13
"known limits." `ruff` clean, `pytest` **302** green. The standalone spec
(`FORWARDING_FIX_SPEC.md`) is **retired/deleted** per the completion convention (recoverable
from git; full record here).

- **Stage 1 — embedded-sender detection** (`fwd email spec stage 1`): `html_utils.parse_forwarded_from`
  recovers the original sender from a forwarded body (Outlook/Gmail, newline- or space-collapsed;
  conservative guard); `digest.fetch_recent_emails` adds `effective_from` (triggers on FW:/Fwd: or
  `config.FORWARDER_ADDRESSES`); `_build_source_prompt` renders "From: <real> (forwarded by jared)".
  Spot-checked on the real archive: Bloomberg→bloomberg.net, KBW/Stifel/Barclays/Greenmantle/
  Guggenheim resolve; direct emails (WSJ/Economist) keep their own sender. +9 tests.
- **Stage 2 — capped body extract** (`fwd email spec stage 2`): the prompt now carries a capped body
  slice (4k chars/text email; PDF-carried emails stay lean; 40k/run budget, forwarded-text funded
  first; forwarded-header stripped; conservative `_looks_like_promo` snippet-demotion) instead of the
  ~200-char snippet. +14 tests. Live-validated (both variants → acohen, $2.13, 29-email day): the
  Bloomberg section now POPULATES and content is attributed (Bloomberg/CoinDesk/Benzinga); the budget
  held; cross-variant cache still engages.
- **Stage 3 — index attribution** (`fwd email spec stage 3`): `search._chunks_for_date` uses the
  effective sender for the email chunk header + `source_name` (reads stored `effective_from`, else
  re-parses the body so `--rebuild` backfills old days; `archive.py` unchanged — it already passes the
  field through). Full `--rebuild` → **5997 chunks / 9 days**; 177 email chunks re-attributed to
  "Today's News (BLOOMBERG)". Eval re-baselined **0.846 / hit@3 0.923 / hit@10 1.0 / MRR 0.894**; an
  ISOLATION eval vs the pre-Stage-3 index was IDENTICAL → Stage 3 is metric-neutral (the dip vs 07-13
  is corpus growth, the known F3 relative-time staleness). Live reply-bot check ($0.12): the answer
  cites (Bloomberg/CoinDesk), (Bloomberg / The Block), (FT) — forwarded sources named correctly, no
  longer "an internal email."

**Numbering-collision fix (§14.B-3.5a, separate commit):** the appended sections used hard-coded
numbers ("10. WSJ/FT Articles", "11. Fund Position Changes") that collided with Opus's dynamic 1..N
count (Stage 2's richer content made Opus add a "New Issues" section, pushing Rating Actions to "10").
Fix: dropped the hard-coded numbers so the appended sections are UNNUMBERED (matching the existing
"Bankruptcy Court Activity"), and SYSTEM_PROMPT now tells Opus to number only its own sections.
Live-validated 2026-07-14: FULL produced 10 numbered sections, TEAM 11 — **ZERO duplicate numbers in
either variant**. Also fixed same session (pre-forwarding): the three cosmetic nits (memory-tag leak,
bare-ticker rule, bankruptcy carve-out) and the `[FULL]` subject marker on jared's variant (reply
query reworked to survive it).

Live-run spend this session: cosmetic-run $1.47 + stage-2 $2.13 + reply $0.12 + final $2.22.

---

## Current state (2026-07-13, end of session — all session work committed)

**Every code track is done AND live-validated — including the NEW `TEAM_DIGEST_SPEC`
track, which went spec → build → audit → paid validation → Stage-5 activation →
live-run proof in this one session.** Substack is now jared-personal: two digests
generate daily (full to jared's list, Substack-free team variant to `DIGEST_TO_TEAM`
— **pilot: acohen**), sharing a prompt-cache prefix (team runs first, full pays only
its substack tail); separate `substack_memory.json`; asker-tiered reply bot
(reply-to-asker-only; non-`FULL_ACCESS_SENDERS` askers get substack-free retrieval,
the team digest as context, no substack storylines); the team digest is the indexed
one; per-variant alert boxes; team weekly wrap. The first activated run (GREEN,
$1.47) closed every run-day check: sent team email greps CLEAN, cross-variant cache
confirmed, both memory feeds flipped, eval re-baselined **0.846/0.962/0.897**
(`2026-07-13_post_team_activation.json`). Also this session: Substack renewal
automated (dead cookie found + replaced, real auth probe, `SUBSTACK_EMAIL` set,
jared auto-forward requested), paid-sub coverage 11 → **17 pubs**, paywall-preview
flagging, the weekly-wrap review PASSED, IT's Abnormal allowlist CONFIRMED.
`ruff` clean, `pytest` **277** green. Session spend ~$3.3 (validations $1.81 + the
activated run $1.47) against the fresh top-up; daily runs remain stopped (task
disabled).

**REMAINING:**
1. **jared's one-time Gmail forward confirmation** — watch the bot inbox for
   Google's confirmation email (none as of 2026-07-13 EOD); Substack auto-renewal
   is inert until it's clicked (manual cookie paste is the fallback).
2. **§7.2 server deploy** (F1 checklist; `setup_tasks.ps1` as admin on the box) —
   the project's definition of "done". **Deploy checklist additions from this
   session:** server env.bat must carry `DIGEST_TO_TEAM` (else post-activation
   full digests get indexed and leak to team askers) + `SUBSTACK_EMAIL`; copy the
   fresh `substack_cookie.txt` and `substack_memory.json`.
3. **Three cosmetic watch items from the first dual run** (details in the
   comparison entry below): (a) the model occasionally appends "memory" to source
   tags — "(Greenmantle memory)", "(13D memory)", and one alert detail said
   "Substack memory references..." — candidate one-line SYSTEM_PROMPT/memory-header
   tweak if it recurs; (b) run-variance factual slip in the team variant ($TCBK
   expanded as "TrustCo Bancorp"; it's TriCo Bancshares — each variant is an
   independent generation with independent error draws); (c) full digest wrote its
   own "9. Bankruptcy Activity" and numbered Rating Actions "10", colliding with
   the appended "10. WSJ/FT" (§14.B template-drift family, cosmetic).
4. **F3 golden-set refresh:** `mstr-week-evolution` is a stale relative-time
   question (the eval's one top-3 slip); refresh/add questions for the new days.
5. Optional end-state: flip the Substack account email to the bot (jared's call).

---

## Sent-email comparison (jared vs team) + three cosmetic watch items (2026-07-13)

Operator-requested: both sent emails fetched read-only from the bot's Gmail Sent
mail and verified **byte-identical** to the local `digests/` saves (delivery
fidelity confirmed), then compared side-by-side.

**Verdict: the separation works as a product, not just a filter.** Shared
infrastructure identical in both (all data tables, appended WSJ/FT + PACER
sections, ratings, the MSTR 8-K). Jared-only: the substack-memory-sourced
"Distressed exchange" alert box, 2 of 3 TL;DR bullets, and the deep substack
analysis (JBI capital-allocation conflict, Blue Owl/UBS post-mortem, software
markdowns, redemption scoreboard, HYL/ARE, Krugman, Burry). The team variant
**redistributed attention rather than hollowing out**: Greenmantle's Burnham-UK
analysis got 3 takeaways + themes + contrarian + the Worth Reading slot (the full
digest compresses it to one bullet), plus richer MSTR-8-K and CFTC-COT detail.
Team leak grep on the delivered artifact: CLEAN.

**Three cosmetic nits logged as watch items (also in Current state):**
1. **"…memory" leaking into source tags** — the team digest cited "(Greenmantle
   memory)" / "(13D memory)" and the full digest's alert detail opened with
   "Substack memory references…". Violates the never-cite-the-memory-system
   spirit at the wording level (attribution itself was correct). If it recurs:
   a one-line tweak to the SYSTEM_PROMPT rule and/or the memory context headers.
2. **Team-variant factual slip:** `$TCBK` expanded as "TrustCo Bancorp" — it's
   TriCo Bancshares (full digest + WSJ correct). Reminder that the team digest
   is an independent second generation with independent hallucination draws.
3. **Numbering collision in the full digest:** Opus added its own "9. Bankruptcy
   Activity" section and numbered Rating Actions "10", colliding with the
   appended "10. WSJ/FT Articles" (and duplicating the appended PACER section's
   content). §14.B-3.5a template-drift family — cosmetic, renders fine.

---

## First activated run — GREEN, $1.47; Stage-5 run-day items CLOSED (2026-07-13)

Operator-requested manual run via `run_digest.bat` (~14:51–14:57), the first with
the team pipeline live. Wrapper exit 0; both digests delivered to acohen
(DIGEST_TO + DIGEST_TO_TEAM). **The team-digest track is now fully COMPLETE —
built, validated, activated, and live-run-proven in one day.**

- **Team-email grep — PASS (Stage-5 item):** the SENT team digest (41,424 chars)
  contains ZERO substack markers across 20 probes; the full digest control
  carries 10. The indexed digest chunks for 2026-07-13 (19) come from
  `digest_team.html` with zero markers — the indexing flip works live.
- **Cross-variant cache in production — CONFIRMED:** team pass 1 wrote the
  32,270-token shared prefix (incl. the day's 1 inbox PDF); full pass 1 paid 36
  uncached input tokens, wrote only its 23,979-token substack tail (6 articles
  + the substack-memory context); full pass 2 read all 56,249. Team 2-pass
  $0.51 + full 2-pass $0.56.
- **Per-variant alerts — the separation showcase:** full triggered 1/7 — a
  "Distressed exchange" alert evidenced by the substack-memory LME-wave story —
  while the team variant triggered 0/7 and renders NO alert box. Also proves
  the alert-window carve (the substack tail was visible to the full eval).
  Cosmetic watch: the alert detail text says "Substack memory references..." —
  the eval citing the memory layer in its detail wording (jared-only, harmless).
- **Memory feeds flipped live:** shared memory updated FROM THE TEAM DIGEST
  (9 updated / 7 new -> 35 active — substack-free store rebuilding team-visible
  narratives as predicted); substack memory updated in place (5 updated / 1 new
  -> 24 active — no duplication of the migrated stories). PACER commit +
  completion marker written together after both sends. O3 counts recorded once.
- **Eval re-baselined (Stage-5 item):** hit@1 0.846 / hit@3 0.962 / hit@5 0.962
  / hit@10 1.0 / MRR 0.897 (snapshot `2026-07-13_post_team_activation.json`; was
  0.846/1.0/0.904). The one top-3 slip is `mstr-week-evolution` — a
  relative-time ("this week") question written against the 7/06–09 week, now
  outranked by the new week's 614 chunks: golden-set staleness + corpus growth,
  not a retrieval regression. F3 cadence: refresh relative-time questions when
  the set next grows.
- **WILTW 2026-07-09: permanently absent** — still "Report not found" 4 days
  after its publish date; 13D appears to have skipped that week entirely
  (upgrades the 7/10 "not posted yet" to "never posted"). Nothing to fix.
- Run stats: 12 emails (1 PDF — the trimmed cleaner's first live PDF), 6
  substacks, fetch pool 21s/13 sources, index +614 -> 4,561 vectors / 8 days,
  full alert eval $0.136 + team $0.117, total **$1.47**.

---

## TEAM_DIGEST_SPEC Stage 5 — ACTIVATED, pilot = acohen (2026-07-13)

Operator chose activation now with themselves as the pilot team recipient
(monitor the Substack-free variant end-to-end before real teammates join).
Free — no Claude calls. `ruff` clean, `pytest` **277** green.

- **`DIGEST_TO_TEAM=acohen@acorninv.com`** in env.bat — every future run on this
  machine generates/sends/indexes the team variant. **Deploy note: the server's
  env.bat must carry this var too**, or post-activation full digests would be
  indexed and leak to team askers (recorded in the config comment).
- **`config.TEAM_ACTIVATION_DATE = "2026-07-13"`** — safe because no digests
  will be generated between now and the next (team-aware) run; all indexed
  digests ≤ 2026-07-10 are correctly excluded for team askers.
- **Memory cleanse APPLIED** (heuristic + operator-visible dry-run, per spec):
  52 → **32 shared stories** (28 active), **20 substack-sourced stories moved**
  to substack_memory.json (now 26 incl. the 6 fresh ones — some topical overlap
  between migrated and fresh AI-capex/tower stories is accepted, jared-only
  context). Verified: zero substack-flagged stories left in the shared store;
  the rendered shared context (21,388 chars) greps CLEAN of all pub markers.
  Backups: `memory_prestage5.bak` / `substack_memory_prestage5.bak`.
  Self-healing note: narratives the cleanse removed from team memory (private
  credit redemptions, serial LME wave) rebuild automatically from team-visible
  sources once team digests start feeding the store.
- **Heuristic upgraded first** (the dry-run caught misses): word-level matching
  + a literal-"substack" keyword in `_story_mentions_substack` — "Krugman
  Substack"/"Burry Substack" class now matches; shared by the router guard and
  the cleanse; +4 test assertions.
- **No-ops (already satisfied):** acohen already on the reply `from:` allow-list
  (team tier — deliberately NOT in FULL_ACCESS_SENDERS); Abnormal covers
  acorn.com Outlook. **Deferred to the FIRST activated run:** eval re-baseline
  (indexed digest corpus flips to team) + substack-free grep of the sent team
  email. Also: `substack_memory.json` added to .gitignore (was missing).

---

## TEAM_DIGEST_SPEC paid validations — ALL THREE PASSED ($1.81 total, 2026-07-13)

Run same-day on the operator's go-ahead after the credit top-up. Isolation methods
throughout (nothing sent, real stores untouched except the intended substack-memory
seeding); outputs in the session scratchpad.

1. **Substack-memory delta ($0.045)** — first real run on 7 fresh articles: **6 new
   stories**, sane topics/sources/data points (AI capex equity/credit split, Blue
   Owl OTIC run, custom-memory cycle…); context renders with the SUBSTACK MEMORY
   header. **The production `substack_memory.json` is now seeded** — jared's next
   digest gets the context.
2. **Reply A/B at both tiers ($0.23)** — same AI-capex question, digest_date
   7/10: FULL (asker=None) 20 chunks/32.5k chars, cites Junk Bond Investor ×4;
   TEAM (asker=acohen) 20 chunks/18.5k chars, **zero substack citations** while
   still covering Oracle/CRWV from ratings+filings+news; storyline router and
   [team access] tier label fired; missing digest_team.html correctly omitted the
   digest context. (One false alarm during review: a case-insensitive "PETITION"
   marker matched "com**petition**"/"voluntary petition" — bankruptcy vocabulary,
   not the pub; case-sensitive grep clean.)
3. **Digest structure A/B ($1.53)** — archived 7/10 inputs + that morning's exact
   memory snapshot; three arms (team-new, full-new, full-old-from-git-HEAD):
   - **Cache: cross-variant hit exactly as designed** — team pass 1 wrote the
     28,403-token shared prefix; full pass 1 READ all 28,403 and wrote only the
     7,311-token substack tail; full pass 2 read 35,714. Full-variant 2-pass cost
     **$0.41 vs $0.57 old** — the restructure is a net saving when both run.
   - **Output equivalence: PASS** — identical template/sections/numbering, same
     stories with the same numbers (Oracle BBB-/$160B, CRWV Form 4 details, GBDC
     revolver terms, HYL CCI/SBAC figures, market data, docket names, same Worth
     Reading links). Substack integration UNDIMINISHED by the tail move (HYL/Burry
     woven through Takeaways/Ideas/Themes/Contrarian as before). Differences are
     normal run variance. The "eyeball jared's next run" caveat is CLOSED — this
     was the Group-C-style check.
   - **Team render: PASS** (same template; Stifel/KBW/ratings fill the space) —
     with one EXPECTED finding: substack pub names surfaced via the **pre-cleanse
     memory context** (4 contaminated stories verified in the archived snapshot),
     proving the Stage-5 memory cleanse is load-bearing. Hardened same day:
     `main()` now prints a loud warning if team generation runs while
     `TEAM_ACTIVATION_DATE` is unset.

Remaining before any real team send: the Stage-5 activation checklist only.

---

## TEAM_DIGEST_SPEC built — Substack becomes jared-personal (Stages 1–4, 2026-07-13)

Operator-approved spec (`TEAM_DIGEST_SPEC.md`, drafted + consistency-reviewed the
same day) built in one pass. `ruff` clean, `pytest` 238 → **275** (+32 across a new
`tests/test_team_digest.py` and grown search/reply/memory/archive/prompt suites).
$0 Claude spend — all verification free/offline (see the residual paid items below).

**What it does:** Substack summary/analysis reaches only jared. When
`DIGEST_TO_TEAM` is non-empty a second, Substack-free digest (and Friday wrap) is
generated and sent to the team list; with the list empty (today) only jared's full
variant runs, at today's cost.

- **Stage 1 — recipients:** `_recipients_from_env` helper; `TEAM_RECIPIENTS` (env
  `DIGEST_TO_TEAM`, default empty). `DIGEST_RECIPIENTS`/`DIGEST_TO` semantics
  unchanged (midday/reply_monitor import it by name; run_alert reads the env).
- **Stage 2 — asker-aware reply bot:** answers now go to the ASKER ONLY (was: every
  answer broadcast to all recipients). `check_for_replies` captures the From
  address; `config.FULL_ACCESS_SENDERS` (jared ×2 + the bot; acohen deliberately
  team-tier) picks the tier. Team askers: retrieval excludes `substack` chunks and
  digest chunks dated before `config.TEAM_ACTIVATION_DATE` (None ⇒ all digest
  chunks — every archived digest is a full one today) via new
  `search(exclude_source_types=, exclude_digest_before=)` params (the §14.F parked
  source_type filter, now production-triggered); digest context loads
  `digest_team.html` (absent pre-activation ⇒ omitted, never the full one); the
  storyline router drops substack-store stories and (heuristic pub-name match vs
  SUBSCRIPTIONS) main-store stories that look substack-sourced. `asker=None`
  (internal/tool calls) = full access, back-compat.
- **Stage 3 — substack memory:** `memory.py` store-parameterized (main-store
  behavior byte-identical, v1-backup logic main-only); new
  `substack_memory.json` fed daily from the articles themselves (3k-char/article
  cap), rendered by `get_substack_memory_context()` into the FULL prompt only;
  `match_stories(path=)` lets full-access askers match substack storylines.
- **Stage 4 — dual generation (gated):** Substack moved OUT of
  `_build_source_prompt` into a trailing `_build_substack_block` content block
  after the shared cache breakpoint — the team prompt is a byte-identical strict
  prefix of the full prompt (test-pinned), so when both variants run (team first)
  the full run reads the team run's cached prefix and pays only for the substack
  tail. Per-variant alert eval (team alerts can never cite a Substack pub);
  deterministic signals (Fed stress, O3) appended to both boxes; shared pre-built
  sections; `digests/<date>_team.html` + `archive/<date>/digest_team.html`;
  **search indexes the team digest when present** (full-digest prose embeds
  substack analysis — the v2 leak fix); `memory.json` fed by the team digest once
  it exists (full until then); PACER commit + the O2 marker moved after the LAST
  send; team weekly wrap from team dailies. The two A/B tools updated for the new
  builder split.

**Free verifications:** 275 tests; entry points import; retrieval eval
**metric-identical** (0.846/1.0/0.904 — the search changes are behavior-neutral for
all existing callers); live-index check — a team-asker query returns zero
substack/digest chunks where the unrestricted query surfaces both.

**Post-build spec audit (same session, operator-requested):** found + fixed four
gaps — (1) **midday alert now sends to both lists** (deduped; the spec's §1 row
had been missed — midday.py was untouched); (2) **full-variant alert source
carves a guaranteed 15k-char window for the substack tail** (alerts.py evaluates
only the first ~50k chars, and with Substack moved to the tail jared's alert box
would otherwise have been silently blind to it — e.g. PETITION flagging an LME);
(3) storyline context re-capped at 2 across both stores (the Stage-5 pinned
budget; main-store matches take priority); (4) full/team daily saves isolated
into separate non-fatal try blocks. Final: `pytest` **277** green, `ruff` clean.
Known accepted nit: the frozen groupb_ab harness reconstructs the un-carved
alert source (pre-carve production behavior) — fine for its A/B purpose.

**Residual (flagged in the spec banner):** Stage-5 activation checklist (when the
first team recipient is added: set env + activation date, memory cleanse, reply
allow-list, eval re-baseline, substack-free grep of the first team send); paid
validations pending permission — reply (~$0.15), substack-memory delta (~$0.10),
and the Stage-4 A/B day (~$2–3) before any real team send. ⚠️ The prompt
restructure is live for jared's daily digest NOW — eyeball the next natural run's
output (the Group-C-style paid A/B is the rigorous check).

---

## Substack: renewal automated, dead-cookie incident, +7 paid pubs; weekly wrap reviewed (2026-07-13)

Operator-driven session (browser access to jared's Substack + free read-only API probes; $0
Claude spend). `ruff` clean, `pytest` **232** green (+5, first-ever `tests/test_substack.py`).

**Weekly-wrap template review — PASSED (closes the 2026-07-10 operator-eyeball item).** The
wrap wasn't on disk (save-to-disk landed after the 7/10 run), so it was fetched read-only from
the bot's Gmail Sent mail. Verdict: correct Georgia/680px inline-style template, the 4
requested sections in order, plus two sensible additions in house style (a TL;DR-style "Week
at a Glance" box and a Mon→Fri scorecard table) and an honest footnote for a missing Friday
S&P level. No fixes needed.

**Substack account audit (operator's logged-in Chrome + the saved cookie via API):**
- Account: **jaredtramontano@gmail.com** (handle @dirac1), **43 subscriptions = 12 paid +
  31 free**. The code fetched only 5 of the 12 paid pubs.
- **+7 paid pubs added to `SUBSCRIPTIONS`** (11 → 18): Damnang's Substack, Fixed Income
  Beacon, Pari Passu, PauloMacro, SemiAnalysis, Tech Investments, The Unicus Investor —
  live-verified (SemiAnalysis 84k-char paid bodies; Pari Passu's custom domain bot-blocks
  like polymath, kept with a comment, degrades gracefully).
- **polymathinvestor REMOVED** (operator: not renewing) — the paid sub had lapsed to free AND
  the site 403s; it contributed nothing every run. 18 → **17 pubs**.
- Kept (operator decisions): whatiscalledthinking + aletteraday (free tier — free posts +
  ~350-char paywall previews accepted); **yetanothervalueblog kept-until-breaks** (NO active
  sub — its full text arrives only via Substack's public per-post API; flag to jared).

**Dead-cookie incident (found during the audit; the §13 risk had ALREADY fired, silently):**
- The saved `substack_cookie.txt` no longer authenticated (401 on real auth endpoints), yet
  nothing noticed: `_check_session` probed `/api/v1/reader/feed`, which returns **200 even
  logged out** (vacuous check), and Substack's per-post API serves many pubs' full paid bodies
  **unauthenticated** (verified: byte-identical with/without cookie on HYL, PETITION, Burry) —
  the leak masked the outage. Properly-gated pubs (Fixed Income Beacon, PauloMacro) were
  silently delivering previews only.
- **Fixes:** operator pasted a fresh `substack.sid` from the logged-in browser (verified:
  auth probe 200 as "Dirac"; Fixed Income Beacon 903 → **35,081** chars; PauloMacro 1,273 →
  **464,773** chars — full paid bodies); `_check_session` now probes
  **`/api/v1/user/profile/self`** (200 = live, 401 = dead — the probe endpoint is test-pinned
  so the vacuous check can't return).

**Renewal automated (the §13 decision, operator-chosen from 4 options):** keep the account as
jared's; auto-forward the magic link. Chain: dead cookie detected (fixed probe) →
`_login_via_magic_link` posts `SUBSTACK_EMAIL=jaredtramontano@gmail.com` (now set in env.bat)
→ Substack emails jared's gmail → **jared's auto-forward filter** (`from:no-reply@substack.com`
→ the bot; text sent, filter presumed set) → the code finds it in the bot's inbox → fresh
cookie saved → the SAME run proceeds. Failure path: renewal fails → Substack `[]` → retried
every run → O3 flags after 3 zero runs (Option A, operator-chosen: visible failure over
silent leak-dependent degradation). **Inert until jared's one-time Gmail forward confirmation
is clicked** — the bot inbox had no confirmation email yet at EOD.

**Also:** digest.py's stale "14 sources" comments corrected to 13 (post-TRACE); HANDOFF §1 /
§7.1 (octus_session gone) / §7.2-7 (allowlist confirmed) / §13 / latent-maintenance updated.
Two dev-machine/prod notes: jared's machine and this one hold independent Substack sessions
(no conflict; account-level logout/2FA would kill both); IT's allowlist confirmation covers
Outlook inboxes org-wide.

---

## Docs housekeeping: cleanup-track phase-close in HANDOFF; Substack flagged (2026-07-13)

Operator-confirmed phase close for the cleanup/refactor track (docs only, no code):

- **HANDOFF §1** now records the track complete (9 stages, tests 180 → **227**, pypdf
  bump + metric-identical eval, $0 spend) and the stale "pytest 180" status corrected;
  **§10** "Done" list extended; **§4** — the `grab_session.py` row removed (file was
  deleted back in Phase 0, commit `1f400f6`; the deferred 1.2d item) and the wrapper row
  notes the clean `exit /b 0`.
- **CLEANUP_REFACTOR_SPEC.md** got a completion banner (incl. the note that its
  trace_data freeze was lifted by the 2026-07-13 §13 decision); retained as the record.
- **Substack ownership/renewal 🚩 FLAGGED** (§13 + §1 + this file's Current state):
  operator is speaking to jared. It is the last open §13 item; polymathinvestor's 403
  rides along in the same conversation.

---

## §13 closure: Octus/HY-new-issue item RESOLVED — accepted, no replacement (2026-07-13)

Operator decision (docs-only; the Octus code was already removed 2026-06-29): no paid
feed and no scraper. Evidence from the same-day inbox audit: **20 Stifel "New Issue
Flash" forwards in 21 days (11 HY + 9 IG)** already deliver deal-by-deal new-issue
color through the inbox. Accepted loss: a systematic pipeline/tracker view; if ever
wanted, the code side is one standard fetcher module. **§13 is now down to a single
open item: Substack ownership/renewal (+ the polymathinvestor 403).** HANDOFF §1/§13
updated.

---

## §13 closures: forwarding-completeness audit RESOLVED + TRACE module REMOVED (2026-07-13)

Two §13 items closed by operator decision, evidence-backed by free read-only probes
(archive `emails.json` + Gmail metadata/full-text; no Claude, nothing modified in the
inbox). `ruff` clean, `pytest` **227** green.

**Forwarding completeness — RESOLVED ("we have everything").** The audit (21 days, 143
inbox emails) found the ENTIRE inbox layer is jared's rule-based forwards
(all outer-sender jared, "FW:" subjects — the sender rewrite is inherent to Outlook's
forward action; redirect would preserve it but commonly breaks DMARC/corporate policy,
so not recommended). What flows: Stifel HY+IG (daily notes, New Issue Flashes), KBW
daily, Barclays Special Sits daily, Guggenheim, the Greenmantle country-update PDF
series (= the archive's "geopolitical PDFs" — branding only visible in bodies), and
**Bloomberg "Today's News" DAILY at 13:30 UTC** (the subject-less "FW:" emails; in the
archive every single run day — earlier "no Bloomberg" audit conclusions were
header-level illusions, corrected). **Grant's: genuinely absent** (0 full-text hits,
30 days) — operator accepted; the prompts' "(Grant's)" strings stay as format examples.
**Known accepted limits (future spec item if ever wanted):** §7's `bloomberg.net`
sender-match can't fire on forwards, and the digest prompt gets only ~200-char
snippets (bodies go to archive/RAG) — so Bloomberg is reply-bot-searchable but
effectively unread by the morning digest; fixing that = embedded-From detection + a
capped body extract = prompt-adjacent + token cost ⇒ sign-off first.

**FINRA TRACE — RESOLVED: not using it; module removed (§13 option c).** Priced it
first (finra.org): the needed End-of-Day Transaction File is $750/month per data set
(≈$9k/yr) — indefensible for a 2-issuer watchlist; the $0 tier is aggregates-only and
the free web UI prohibits scraping. The stub never returned a record anywhere.
Removed: `trace_data.py` (git rm), digest wiring (import, registry row, prompt
section + `trace_data` params in `_build_source_prompt`/`summarize_with_claude`,
`build_trace_html` call, `trace_html` in `_assemble_digest_html`), the
`.gitignore` `trace_cache.json` entry (file never existed), the config UA-comment
mention, the content_monitor docstring example, registry/prompt/assemble test
references, and the two tools' `trace_data=[]` args. O3 keys off each run's actual
counts, so the key just stops appearing. Recoverable from git. This lifts the
2026-07-10 "trace_data.py frozen" carve-out in CLEANUP_REFACTOR_SPEC.md — the freeze
was pending exactly this §13 decision, now made. HANDOFF §1/§2/§4/§7.1/§8/§13 updated.

---

## Cleanup Stage 2.6 — PyPDF2 → pypdf + rebuild + eval re-baseline — TRACK COMPLETE (2026-07-10)

The last spec stage; **the cleanup/refactor track (CLEANUP_REFACTOR_SPEC.md) is
code-complete.** All free/offline. `ruff` clean, `pytest` **227** green.

- **Dep swap:** `PyPDF2==3.0.1` (unmaintained) → **`pypdf==6.14.2`** (its official
  continuation) in `requirements.txt` + the `search.py` import; PyPDF2
  uninstalled from the venv.
- **Extraction diff (the measure-first step), real 11-PDF corpus:** 0/11
  byte-identical, but every difference is small (~0.1–0.5% of chars) and
  quality-POSITIVE — pypdf fixes PyPDF2's spurious space-before-punctuation
  ("UPDATE : STRAIT TALKING ?" → "UPDATE: STRAIT TALKING?"), rejoins words
  PyPDF2 split ("battl e" → "battle", "Le Pen ’s" → "Le Pen’s"), and breaks the
  WILTW header block onto proper lines. No damage class found.
- **Index rebuilt:** full `--rebuild` → **3,947 chunks / 7 days** (was 3,948;
  net −1 from the changed extraction text). Pre-rebuild `index.faiss` +
  `chunk_metadata.json` backed up (session scratchpad `index_backup_prepypdf/`;
  rollback = restore those two files + revert the pin/import).
- **EVAL GATE: PASSED, METRIC-IDENTICAL** — hit@1 **0.846** / hit@3 **1.0** /
  MRR **0.904** on the 26-question set (snapshot
  `tools/eval_results/2026-07-10_post_pypdf.json`); per the pre-committed gate,
  no operator sign-off needed. Spot search sane (Wynn Moody's rating top-1,
  0.931).
- Historical references to "PyPDF2 3.0.1" in `_clean_pdf_text`'s docstring stay
  as-is (they record what the 3.3 measurement was made against).

---

## Cleanup Stage 2.5 — 13D unattended-login guard (R8) (2026-07-10)

`ruff` clean, `pytest` **227** green (+3). Attended behavior byte-identical
(flag unset = today's laptop behavior, test-pinned).

- **The last "interactive prompt inside an unattended run" hang risk is guarded**
  (same failure family F1a-1 closed for Gmail): when the 13D session is missing
  or expires mid-run, `thirteen_d` used to launch a HEADED Chromium and block on
  `input()` — on the server (S4U, session 0) worst-case a hang until the 3h task
  limit kills the WHOLE digest run. Now, with `DIGEST_UNATTENDED=1`: a missing
  session fails soft in `fetch_wiltw` BEFORE any Playwright work; the
  `_download_pdf` entry and the mid-run login-redirect path do the same (loud
  "manual re-login required" log lines; O3 flags the resulting wiltw zero-streak).
- **Env check centralized:** new `config.unattended()`; `digest._unattended`
  delegates (its F1a-1 tests still green, unchanged); `thirteen_d` shares it.
- **Pinned:** unattended + no session → skip with `_download_pdf`/
  `_do_manual_login` boom-guards never firing; attended + no session → the
  manual login IS attempted (sentinel).
- **Deploy-checklist residual (add to the §7.2 on-box steps):** on the server,
  temporarily rename `thirteen_d_session.json`, trigger a run, confirm the loud
  skip line in the log and no hang — the session-0 stdin/headed-launch behavior
  is only fully provable there.

---

## Cleanup Stage 2.4 — weekly-wrap bundle (operator-approved output changes) (2026-07-10)

`ruff` clean, `pytest` **224** green (+8 new `tests/test_weekly_summary.py`, −1
obsolete weekly-prefix test). The three visible changes get live confirmation by
riding along with the next natural Friday run (no dedicated spend).

- **R6 — weekly subject (operator-specified):** now
  **"📊 Weekly Research Wrap — Week of Monday, July 6"** style, via new
  `digest._weekly_subject()` (Monday from the shared `_week_monday()` helper,
  which `_get_week_digests` now also uses; no leading zero on the day).
  `send_digest_email` swapped its `subject_prefix` param for a full `subject=`
  override (daily default via the 1.2a constant, byte-identical — pinned).
  Reply-bot coupling: none, and now test-pinned (the weekly subject must never
  start with `DIGEST_SUBJECT_PREFIX`).
- **R5 — weekly saved to disk:** new `save_weekly_digest()` writes
  `digests/weekly_YYYY-MM-DD.html` before sending (non-fatal on failure). The
  filename is invisible to `_get_week_digests`'s exact-name loader — test-pinned
  so a saved weekly can't get slurped back in as next Friday's input.
- **R4 — weekly preamble strip:** pass 2's strip-to-first-`<div` logic extracted
  to `_strip_to_html()` and applied to the weekly too (pass 2 behavior
  unchanged; midday keeps its own copy).

---

## Cleanup Stage 2.3 — seen-state / cache-state fixes (2026-07-10)

`ruff` clean, `pytest` **217** green (+7).

- **R1 — PACER seen-state eviction is now insertion-ordered** (`pacer.py`, new
  `_ordered_seen` helper + both scan loops). The old `list(set)[-1000:]` /
  `[-500:]` trims truncated a SET — arbitrary order — so once a busy court
  (DEB/TXSB) crossed the cap, recently-seen filings could be evicted and
  re-reported as duplicate "NEW Chapter 11" entries (re-triggering the paid
  Sonnet size filter on re-evaluation). Now seen ids live in an ordered list
  (set alongside for O(1) membership) and the cap evicts oldest-first. On-disk
  format unchanged (JSON list) — legacy unordered files load as-is. Pinned by
  mocked-RSS tests (NO live pacer run — its path can trigger Sonnet): seen ids
  suppress; a 990-seeded + 30-new overflow evicts exactly the 20 oldest.
- **R2 — CFTC COT WoW compares against the prior WEEK, not the prior file**
  (`cftc_cot._load_prior_week(current_report_date)` + `fetch_cot_data`
  restructured to parse rows before picking the baseline). The old code loaded
  the newest cache file — on the 2nd/3rd run of the same report week that file
  IS the current report, so `spec_net_change` printed 0 for every contract
  (silently wrong data on Tue/Wed). Now the newest file STRICTLY OLDER than the
  current report is used; same-date-only cache → honest "n/a". Pinned by
  fixture-cache tests (live COT smoke not possible today — Friday skip day; the
  fix is exercised on the next Mon–Wed run).

---

## Cleanup Stage 2.2 — small correctness + the missed escaping (2026-07-10)

`ruff` clean, `pytest` **210** green (+11: three new test files + one grown).

- **S1 — `fund_tracking.build_funds_html` now escapes** (the one builder the
  Phase-1.2 pass missed): `esc()` on fund/issuer names + filing date,
  `safe_href()` on the link. 13F issuer names routinely carry `&` ("AT&T INC") —
  raw interpolation produced invalid entities. Pinned by
  `tests/test_fund_tracking_html.py` (escaping, `javascript:` → `#`, normal names
  byte-identical).
- **R7 — `treasury_auctions.format_auctions_for_prompt`:** the header claimed
  "last 48h" while `HOURS_LOOKBACK = 24` (misinformed Opus about the window) —
  now derived from the constant; and a non-numeric `high_investment_rate`
  (parsed to None) crashed the yield f-string, silently losing the whole section
  via the registry try/except — now renders "yield n/a". Pinned by
  `tests/test_treasury_auctions.py`; live free smoke shows "last 24h" + real data.
- **R3 — `cftc_cot._find_contract`:** the loose fallback returned the FIRST line
  merely containing the code substring (e.g. inside another contract's
  open-interest figure), making the exact-code check unreachable. Now: exact
  parsed-code match anywhere wins; the substring hit survives only as a fallback
  when no exact match exists. Pinned by `tests/test_cftc_cot.py` (crafted
  legacy-format lines; live COT smoke not possible today — Friday is a skip day).
- **D5 — `thirteen_d` download paths unified through new `_persist_pdf()`:** the
  button-click path used to leave an unarchived `wiltw_<date>.pdf` in the repo
  root; all three paths now archive to `archive/<today>/pdfs/WILTW_<report>.pdf`
  (the link path's behavior) and clean up temp files. Helper unit-tested; the
  Playwright call sites are code-reviewed (exercised by the next live WILTW fetch).

---

## Cleanup Stage 2.1 — test additions (tests-first; zero production-code change) (2026-07-10)

Purely additive. `ruff` clean, `pytest` **199** green (+15, three new test files).

- **`tests/test_feeds.py` (+7)** — `feeds.py` had no committed tests (the Phase-2.3
  "unit tests" were session-ad-hoc). Pins `parse_date` (RFC-2822, ISO-with-Z,
  garbage→None) and `is_recent` (inside/outside window, naive-date→UTC assumption,
  and the §6 unparseable→True over-inclusion — pinned as deliberate, not changed).
- **`tests/test_assemble_digest.py` (+5)** — first coverage for the documented
  brittle `_assemble_digest_html` coupling (HANDOFF §5): pre-sections insert after
  the double-border header and before the TL;DR in the pinned order
  (alerts→market→macro→earnings→fedBS→auctions); post-sections append before the
  final `</div>` (news→funds→pacer); empty input passes through unchanged; a digest
  missing the header anchor degrades gracefully (pre-sections skipped, no crash).
  **The function itself is untouched** (§14.B-3.5a stays wait-and-see).
- **`tests/test_archive.py` (+3)** — pins hostile-PDF-filename sanitization, PDF
  bytes saved + `pdf_filenames` recorded, base64 stripped from the archived
  `emails.json`, wiltw snapshot, empty-source JSON shapes, and that a corrupt
  base64 payload doesn't crash the archiver.

---

## Cleanup Stage 1.3 — wrapper clean-exit (forfiles quirk) — PHASE 1 CODE DONE (2026-07-10)

Behavior-neutral for outputs (only the wrapper's own exit code changes). `ruff` clean,
`pytest` **184** green.

- **All four wrappers (`run_digest/midday/reply_monitor/watchdog.bat`) now end with
  `exit /b 0`** (+ explanatory REM). The O1 `forfiles /d -30` prune exits 1 when
  nothing is >30 days old, so a CLEAN run left the wrapper — and Task Scheduler's
  LastTaskResult — at 0x1 (the 2026-07-10 live-run quirk). Safe: the failure alert
  fires inline off python's own `%ERRORLEVEL%` earlier in the wrapper, so the final
  exit code carries no alerting duty.
- **Scratch-dir validated** (the O1 method): old tail with only a fresh log → exit 1
  (quirk reproduced); new tail same case → exit 0; new tail with a fabricated
  40-day-old log → old log pruned, fresh log kept, exit 0.
- Phase 1's code items are complete (1.1 + 1.2 + 1.3); the 1.2d HANDOFF §4 touch-up
  waits for the operator's phase-done confirmation per workflow.

---

## Cleanup Stage 1.2 — shared constants + tooling pin (2026-07-10)

Behavior-neutral (all emailed subjects byte-identical, pinned by test). `ruff` clean,
`pytest` **184** green (+4, new `tests/test_shared_constants.py`).

- **1.2a — one digest-subject constant (`config.DIGEST_SUBJECT_PREFIX`).** The string
  the reply bot's Gmail query matches ("📬 Daily Inbox Digest") was built
  independently in `digest.send_digest_email` and hardcoded in `reply_monitor` —
  drift would silently kill reply matching. Now: `config.py` owns it;
  `reply_monitor` imports it; `digest` builds subjects via a new `_digest_subject()`
  helper (added for testability — also pre-plumbs Stage 2.4c's weekly-subject
  change). The Friday call site now passes the full "📊 Daily Inbox Digest" prefix
  (the function no longer appends the name), keeping the weekly subject
  byte-identical. Tests pin identity (same object, not just equal) + both legacy
  subject formats.
- **1.2b — earnings watchlist → single source of truth.** `EARNINGS_WATCHLIST` was a
  byte-identical copy of `sec_filings.WATCHLIST` (a ticker added to one list
  half-applied); now imported from `sec_filings`. The now-redundant
  `extra_tickers=SEC_WATCHLIST` lambda in digest's source registry became a plain
  `fetch_earnings_calendar` reference (the base list IS that watchlist now; the
  `extra_tickers` param itself stays). Test pins list identity.
- **1.2c — ruff pinned** (`ruff==0.15.17` in `requirements-dev.txt`) — the lint gate
  every stage relies on was unpinned/unlisted.
- **Verified:** ruff + 184 tests green; free `python earnings.py` smoke → checked all
  16 watchlist tickers (0 upcoming in the next 7 days — mid-July, between seasons).
- *(1.2d — the stale HANDOFF §4 `grab_session.py` row — deliberately deferred to the
  Phase-1-complete HANDOFF update, per workflow.)*

---

## Cleanup/refactor track opened: review + spec + Stage 1.1 dead code (2026-07-10)

A full-codebase cleanup/refactor review (every module/test/tool/wrapper read; baseline
re-verified `ruff` clean + `pytest` 180 green) produced **`CLEANUP_REFACTOR_SPEC.md`**
(operator-approved item list, same day): Phase 1 = behavior-neutral cleanup (3 stages),
Phase 2 = correctness/tests/weekly-polish/13D-guard/pypdf (6 stages, tests-first,
pypdf last behind the eval gate). Zero Claude spend anywhere in the plan. Out of scope
by operator decision: `trace_data.py` frozen entirely (its fate is the §13 decision);
all HANDOFF §6 / §14.F / NEXT_STEPS §2.2 exclusions respected (review found no new
evidence against any of them).

**Stage 1.1 — dead code — DONE.** `ruff` clean, `pytest` **180** green (deletions
only, no new tests). Uncommitted pending operator go-ahead.

- **1.1a `macro_data.py` write-only FRED cache removed** — `fred_cache.json` was
  loaded/updated/saved every run but never read by anything (grep-verified; same
  pathology as the market_data cache removed 2026-06-30). Deleted `CACHE_FILE` +
  `_load_cache`/`_save_cache` + the cache lines in `fetch_macro_data`, the now-unused
  `json`/`Path` imports, the `.gitignore` entry, and the on-disk file. Deliberately
  NOT converted into a read-fallback (degrade-to-omission + O3 already cover FRED
  outages; stale-data fallback would be new, mislabel-prone behavior).
- **1.1b `macro_data.py` dead "dollar" unit branches removed** (`_fmt_val`,
  `_fmt_change_cell`) — no FRED series carries unit "dollar"; dollar-priced assets
  live in `market_data.py` by design.
- **1.1c `reply_monitor._extract_question` dead trailing-newline loop removed** —
  `question` is `.strip()`ed the line above, so `while question.endswith("\n")`
  could never fire.
- **1.1d `digest._rank_news_articles` default aligned 8 → 15** — the sole caller
  (`build_news_html`) always passes 15; the old default was dead and misleading.
- **Verified:** grep shows the only remaining `_load_cache`/`_save_cache` are
  fund_tracking's real read-cache and frozen trace_data; `ruff` clean; `pytest` 180
  green; live free smoke `python macro_data.py` → 12 FRED series, sane values, and
  no `fred_cache.json` regenerated. (Smoke note: reproduced the known 2026-07-02
  launcher quirk — relative `call env.bat` doesn't resolve in the agent shell;
  absolute path works, wrappers already use `%~dp0` so nothing to fix.)

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
