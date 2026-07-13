# Cleanup + Refactor Spec

> ✅ **TRACK COMPLETE 2026-07-10 — all 9 stages implemented, gated, and committed**
> ("fable cleanup/refactor stage X.Y done" commits; per-stage detail in WORKLOG).
> Final state: `ruff` clean, `pytest` 180 → **227**, pypdf eval re-baseline
> **metric-identical** (0.846/1.0/0.904), $0 Claude spend. The `trace_data.py`
> freeze below was lifted 2026-07-13 when the operator resolved §13 (module
> removed — see WORKLOG 2026-07-13). This document is retained as the record of
> what was specced and why.

> Output of the 2026-07-10 full-codebase review (operator-approved item list, same day).
> Companion to `HANDOFF.md` (state/constraints) and `WORKLOG.md` (running log);
> follows the house item style (what / where / fix / verify + priority / effort).
>
> **Workflow (operator-set):** implementation happens one stage at a time on explicit
> go-ahead; `ruff` + full `pytest` green between stages (baseline **180 tests**, count
> grows as stages add tests); a dated WORKLOG entry per completed stage; HANDOFF.md
> updated only when the operator confirms a phase is done.
>
> **Cost:** every stage is verifiable **free and offline** — no Claude calls, no
> permissioned paid runs anywhere in this spec. The two outward-visible changes
> (Stage 2.4's weekly subject + save-to-disk) get live confirmation by riding along
> with whatever the next natural Friday run is — no dedicated spend.
>
> **Explicitly excluded (do not touch in this effort):**
> - `trace_data.py` — frozen entirely (operator, 2026-07-10); its fate is the §13
>   jared decision. (For the record it contains a dead `_make_request` helper and a
>   write-only cache — actioned never/later with §13.)
> - Everything in HANDOFF §6 (do-NOT-fix), §14.F (parked rerank/hybrid etc.), and
>   NEXT_STEPS_SPEC §2.2's rejected refactors. The review found no new evidence
>   against any of them.
> - `_assemble_digest_html`'s string-matching mechanism (§14.B-3.5a) — unchanged;
>   Stage 2.1 only *pins* it with an additive test.

---

## Phase 1 — Cleanup (behavior-neutral; zero output change expected)

### Stage 1.1 — Dead code

1.1a **Remove the write-only FRED cache** — `macro_data.py`.
*What:* `fred_cache.json` is loaded, updated, and saved every run but **never read
for any purpose** by anything (grep-verified repo-wide). Identical pathology to the
`market_data` write-only cache removed 2026-06-30.
*Where:* `macro_data.py:15–16` (`CACHE_FILE`), `:40–50` (`_load_cache`/`_save_cache`),
`:71` (`cache = _load_cache()`), `:140` (`cache[series_id] = ...`), `:174`
(`_save_cache(cache)`); `.gitignore:12` (`fred_cache.json`); the on-disk
`fred_cache.json` file.
*Fix:* delete all of the above. Do **not** build a read path instead (the
degrade-to-omission behavior + O3 monitoring already cover FRED outages; a stale-data
fallback would be new, mislabel-prone behavior).
*Verify:* `grep` shows zero remaining references; `ruff`; full `pytest`; free
`python macro_data.py` (FRED key is provisioned) prints the same series.
*Priority:* Low. *Effort:* Small.

1.1b **Remove dead "dollar" unit branches** — `macro_data.py`.
*What:* no FRED series carries unit `"dollar"` (dollar-priced assets live in
`market_data.py` by design), so these branches can never execute.
*Where:* `macro_data.py:188–189` (`_fmt_val`) and `:219–220` (`_fmt_change_cell`).
*Fix:* delete both `elif unit == "dollar"` branches.
*Verify:* `pytest` (test_market_macro pins the live branches); `python macro_data.py`.
*Priority:* Low. *Effort:* Small.

1.1c **Remove dead trailing-newline loop** — `reply_monitor.py`.
*What:* `question` is `.strip()`ed on the line above, so
`while question.endswith("\n")` can never fire.
*Where:* `reply_monitor.py:88–91` (`_extract_question`).
*Fix:* delete the loop.
*Verify:* `pytest` (test_reply_monitor extractor tests unchanged).
*Priority:* Low. *Effort:* Small.

1.1d **Align the unused `_rank_news_articles` default** — `digest.py`.
*What:* the signature default is `max_articles=8` but the sole caller
(`build_news_html`) always passes 15 — the default is dead and misleading.
*Where:* `digest.py:669`.
*Fix:* change the default to 15 (matches the only call site; zero output change).
*Verify:* `ruff`; `pytest`.
*Priority:* Low. *Effort:* Small.

**Stage 1.1 verification plan:** `ruff check` clean + full `pytest` green (no new
tests needed — deletions only) + free `python macro_data.py` smoke. No paid steps.

### Stage 1.2 — Duplication, naming, tooling

1.2a **Single digest-subject constant** — `config.py` + `digest.py` + `reply_monitor.py`.
*What:* the subject string the reply bot's Gmail query depends on is built
independently in two files — `digest.py:917` (`f"{subject_prefix} Daily Inbox Digest
— {today}"`) and `reply_monitor.py:43` (`DIGEST_SUBJECT_PREFIX = "📬 Daily Inbox
Digest"`). Any future drift silently kills reply matching (no error; the bot just
ignores the inbox). Stage 2.4 is about to touch subject code, so close this first.
*Where:* as above.
*Fix:* add `DIGEST_SUBJECT_PREFIX = "\U0001f4ec Daily Inbox Digest"` to `config.py`;
`digest.send_digest_email` builds the daily subject from it (byte-identical output);
`reply_monitor` imports it and drops its local copy.
*Verify:* new unit test pinning that both modules reference the one constant and the
built daily subject is byte-identical to today's format; existing subject-parse test
(`test_reply_monitor.py:42`) still green.
*Priority:* Low-Medium. *Effort:* Small.

1.2b **De-duplicate the earnings watchlist** — `earnings.py`.
*What:* `EARNINGS_WATCHLIST` is a byte-identical copy of `sec_filings.WATCHLIST`,
and `digest.main` additionally passes `extra_tickers=SEC_WATCHLIST` — so a ticker
added to only one list half-applies. Two lists to maintain, one intent.
*Where:* `earnings.py:11–14`; caller `digest.py:960`.
*Fix:* `from sec_filings import WATCHLIST` as the base list in `earnings.py` (keep
the `extra_tickers` param and the set-dedupe). Behavior-neutral today (sets are
identical).
*Verify:* new unit test asserting the resolved ticker set equals
`set(sec_filings.WATCHLIST)`; `pytest`; free `python earnings.py` still runs.
*Priority:* Low. *Effort:* Small.

1.2c **Pin ruff** — `requirements-dev.txt`.
*What:* every stage gate relies on `ruff check`, but ruff is unpinned and unlisted.
*Fix:* add `ruff==<the venv's installed version at implementation time>` to
`requirements-dev.txt`.
*Verify:* `pip install -r requirements-dev.txt` in the venv is a no-op; `ruff check` clean.
*Priority:* Low. *Effort:* Small.

1.2d **Stale-doc note (executed at phase close, per workflow):** HANDOFF §4's file
table still lists `grab_session.py`, deleted in Phase 0 (commit `1f400f6`). Fold the
row's removal into the Phase-1-complete HANDOFF update the operator confirms —
not a standalone edit.

**Stage 1.2 verification plan:** `ruff` + full `pytest` green (+~2 tests); grep
confirms one subject constant and one watchlist source of truth. No paid steps.

### Stage 1.3 — Wrapper exit-code quick win

1.3a **Neutralize the `forfiles` exit-code quirk** — all four wrappers.
*What:* the WORKLOG 2026-07-10 finding: the trailing `forfiles /d -30` prune exits 1
when nothing is >30 days old, so a **clean** run leaves the wrapper's (and Task
Scheduler's `LastTaskResult`) exit code at 0x1 — misleading at deploy when task
history gets read.
*Where:* final line of `run_digest.bat`, `run_midday.bat`, `run_reply_monitor.bat`,
`run_watchdog.bat`.
*Fix:* append `exit /b 0` as the last line of each wrapper. Safe: the failure alert
is already fired inline off python's own `%ERRORLEVEL%` check, so the wrapper's final
exit code carries no alerting duty.
*Verify:* scratch-dir dry run of the wrapper tail (the O1 validation method):
`echo %ERRORLEVEL%` is 0 both with nothing to prune and with a fabricated >30-day-old
log present (which must also still get pruned); eyeball that the inline
`if %ERRORLEVEL% NEQ 0 ... run_alert` line precedes the change untouched.
*Priority:* Low. *Effort:* Small.

**Stage 1.3 verification plan:** scratch-dir wrapper dry run (free); `pytest`
untouched but run anyway per stage gate. No paid steps.

---

## Phase 2 — Refactor (behavior-affecting or structural; tests first)

### Stage 2.1 — Test additions (additive only; pins ground before the fixes)

2.1a **`tests/test_feeds.py` (new)** — `feeds.py` has no committed tests (the
Phase-2.3 "unit tests" in WORKLOG were session-ad-hoc). Pin: `parse_date` on RFC-2822,
ISO-with-Z, and garbage (→ None); `is_recent` inside/outside the window, naive-vs-aware
timezone handling, and the deliberate unparseable→True over-inclusion (§6 behavior —
pinned, not changed).
*Priority:* Low-Medium. *Effort:* Small (~6 tests).

2.1b **`_assemble_digest_html` pin test (new)** — the documented brittle coupling
(HANDOFF §5) has zero test coverage. Additive test with a fixture digest in the Opus
template shape (header div with `border-bottom: 3px double`, trailing `</div>`):
assert alerts/market/macro/earnings/fed-BS/auctions insert after the header and
before the TL;DR; news/funds/pacer append before the final `</div>`; no-sections
input returns unchanged; a digest missing the header anchor degrades gracefully
(pre-sections skipped, no exception). **No change to the function itself.**
*Where:* new `tests/test_assemble_digest.py` (or grow `test_digest_prompt.py`).
*Priority:* Medium. *Effort:* Small.

2.1c **`tests/test_archive.py` (new)** — pin `archive_daily_content`'s PDF filename
sanitization (hostile name → safe chars only), PDF bytes written to `pdfs/` +
`pdf_filenames` recorded, base64 stripped from the archived `emails.json`, and
`wiltw.json` written when present (use `tmp_path` + monkeypatched `ARCHIVE_DIR`).
*Priority:* Low. *Effort:* Small.

**Stage 2.1 verification plan:** `ruff` + full `pytest` green (~+12–15 tests).
Purely additive — zero production-code change. No paid steps.

### Stage 2.2 — Small correctness + escaping

2.2a **HTML-escape `build_funds_html`** — `fund_tracking.py`. **(S1)**
*What:* the one builder the Phase-1.2 escaping pass missed: 13F issuer names from
external XML are interpolated raw (`{h["name"]}`, `{fund}`, `href="{url}"`). Names
routinely contain `&` ("AT&T INC") → invalid entities/broken rendering.
*Where:* `fund_tracking.py:390–440` (incl. the nested `_render_list`).
*Fix:* `esc()` every text value, `safe_href()` the URL — the exact 1.2 pattern.
*Verify:* new unit tests: `&`/`<` in issuer/fund names comes out escaped; a
`javascript:` URL neutralizes to `#`; normal names render byte-identically.
*Priority:* Medium. *Effort:* Small.

2.2b **Treasury auctions: stale window label + None-format guard** — `treasury_auctions.py`. **(R7)**
*What:* the prompt header says "last 48h" while `HOURS_LOOKBACK = 24` (misinforms
Opus about the data window — prompt-bytes change, hence Phase 2); and
`f"{yld:.3f}% yield"` raises if `high_investment_rate` was non-empty but non-numeric
(`_num` → None), which the registry try/except turns into a silently lost section.
*Where:* `treasury_auctions.py:133` (label), `:142` (format).
*Fix:* label derives from `HOURS_LOOKBACK`; guard `high is None` (skip the row or
print "n/a").
*Verify:* unit tests for both; free `python treasury_auctions.py`.
*Priority:* Low. *Effort:* Small.

2.2c **CFTC `_find_contract`: make the exact-code match real** — `cftc_cot.py`. **(R3)**
*What:* the loose fallback (`if parsed: return parsed`) fires on the first line
merely *containing* the code substring, making the exact `cftc_code` comparison above
it dead — a substring hit in another contract's line returns the wrong positioning data.
*Where:* `cftc_cot.py:109–120`.
*Fix:* scan **all** lines for an exact parsed-code match first; only if none is found,
fall back to the first parsed partial match (preserves today's lenient behavior for
oddly-formatted codes like `13874+`).
*Verify:* unit tests with crafted CFTC-format lines: exact match on a later line beats
a substring hit on an earlier line; no-exact-match falls back; absent code → None.
*Priority:* Low. *Effort:* Small.

2.2d **13D download-path consistency** — `thirteen_d.py`. **(D5)**
*What:* the first button-click download path writes `wiltw_<date>.pdf` into the repo
root, never deletes it, never archives it (only `wiltw_temp.pdf` from the *other*
fallback is gitignored + unlinked); the link path archives correctly.
*Where:* `thirteen_d.py:169–177` vs the link path at `:190–197`.
*Fix:* extract one `_persist_pdf(pdf_bytes)` helper (write to
`archive/<today>/pdfs/WILTW_<report-date>.pdf`, the link path's behavior) used by all
three download paths; temp files unlinked.
*Verify:* unit-test the helper (tmp_path); code-review the call sites (Playwright
objects aren't unit-testable — the paths are exercised on the next natural live WILTW
fetch, free of Claude cost on a cache-miss Thursday... note the Opus summary that
follows a real fetch is normal daily spend, not a test cost).
*Priority:* Low. *Effort:* Small.

**Stage 2.2 verification plan:** `ruff` + full `pytest` green (~+8 tests); free
`python treasury_auctions.py` + `python cftc_cot.py` (Mon–Wed) smokes. No paid steps.

### Stage 2.3 — Seen-state / cache-state fixes

2.3a **PACER seen-state: ordered eviction** — `pacer.py`. **(R1)**
*What:* `disc_seen[court] = list(court_seen)[-1000:]` (and `[-500:]` for tracking)
truncates a **set** — arbitrary order — so once a busy court (DEB/TXSB) exceeds the
cap, eviction can drop *recently seen* IDs, which then re-surface in later digests as
duplicate "NEW Chapter 11" entries (and re-trigger the paid Sonnet size filter on
re-evaluation). Unintended randomness that worsens with time.
*Where:* `pacer.py:380` (`court_seen = set(...)`), `:407` (discovery trim), `:465`
+ `:493` (tracking equivalents).
*Fix:* keep the stored value an insertion-ordered **list**: membership-check via a
set, append only unseen IDs in feed order, trim oldest-first with the same `[-1000:]`
/ `[-500:]`. On-disk format unchanged (still a JSON list) — existing
`pacer_seen.json` loads as-is; ordering becomes meaningful from the first new run.
*Verify:* unit tests: trim keeps the *newest* N; previously-seen IDs still suppress;
round-trips through `_stash_seen`/`commit_seen`; legacy (unordered) file loads and
upgrades cleanly. **No live `python pacer.py`** (its `__main__` can trigger Sonnet).
*Priority:* Medium. *Effort:* Small.

2.3b **CFTC COT: prior-*week* comparison, not prior-file** — `cftc_cot.py`. **(R2)**
*What:* `_load_prior_week` loads the newest cache file; on the 2nd/3rd run within the
same report week that file *is* the current report, so `spec_net_change` computes
current-minus-itself = **0**. Monday shows the true WoW; Tuesday/Wednesday silently
show zeros to Opus and the reader.
*Where:* `cftc_cot.py:123–132` (`_load_prior_week`), consumed at `:162`, `:177–179`.
*Fix:* parse the current report's `report_date` first, then load the newest cache
file whose date is **strictly earlier** than it (restructure `fetch_cot_data` to
select the prior file after the first row parse). Same-date-only cache → no prior →
`wow_change=None` ("n/a"), which is honest.
*Verify:* unit tests with fixture cache files: same-date file skipped in favor of an
older one; only-same-date → None; empty cache dir → None; correct WoW math against a
genuine prior week.
*Priority:* Low-Medium. *Effort:* Small.

**Stage 2.3 verification plan:** `ruff` + full `pytest` green (~+8 tests). Both fixes
are pure-local state logic — no network, no Claude. No paid steps.

### Stage 2.4 — Weekly-summary bundle (operator-approved output changes)

2.4a **Preamble strip** — `digest.generate_weekly_summary`. **(R4)**
*What:* pass 2 (`digest.py:643`) and midday (`midday.py:249`) strip any model prose
before the first `<div`; the weekly path returns Opus text raw, so a chatty preamble
would land at the top of the emailed HTML.
*Fix:* apply the same `find("<div")` strip before returning.
*Verify:* unit test (mocked response with preamble → stripped; without → unchanged).

2.4b **Save the weekly to disk** — `digest.main` Friday block. **(R5)**
*What:* the only copy of the weekly wrap is the sent email (the 7/10 first-run
template check had to be done from the inbox).
*Fix:* write `digests/weekly_YYYY-MM-DD.html` before sending (mirror
`save_daily_digest`; non-fatal try/except like the daily save).
*Verify:* unit test with mocked generate/send → file exists with the HTML.

2.4c **Weekly subject line (operator-specified)** — `digest.send_digest_email` + the
Friday block. **(R6)**
*What:* the 📊 weekly currently reuses the daily "Daily Inbox Digest" subject.
*Fix:* add an optional `subject=` override to `send_digest_email` (default None →
today's daily format via the Stage-1.2a constant). The weekly passes
**`📊 Weekly Research Wrap — Week of Monday, July 6`** style — em dash matching the
daily subject's house style; the Monday date comes from a small shared
`_week_monday()` helper (also used by `_get_week_digests`), day number rendered
without a leading zero (the daily subject's `{day}` pattern, not `%d`).
Reply-bot coupling: none — its Gmail query matches "Re: 📬 Daily Inbox Digest", which
the 📊 weekly has never matched; that stays true.
*Verify:* unit test on the subject builder (exact format, correct Monday for a fixed
date); existing daily-subject tests byte-identical.

**Stage 2.4 verification plan:** `ruff` + full `pytest` green (~+4 tests). Live
confirmation (subject renders, file saved, email looks right) **rides along with the
next natural Friday run** — normal production spend, no dedicated paid run.
*Priority:* Low-Medium. *Effort:* Small.

### Stage 2.5 — 13D unattended-login guard **(R8)**

2.5a **Fail fast instead of prompting when headless** — `thirteen_d.py` (+ tiny
`config.py` helper).
*What:* the last "interactive prompt inside an unattended run" hang risk, same
failure family F1a-1 fixed for Gmail: when the 13D session is missing or expires
mid-run, `_do_manual_login` launches a **headed** Chromium and blocks on `input()`.
On the server (S4U, session 0) that's best-case an EOFError-driven skip, worst-case a
hang until the 3h task limit kills the **entire digest run** — one dead session costs
the whole day. HANDOFF §7.2 already says the 13D re-login "will eventually" be
needed; this makes that inevitable event a graceful skip instead of a run-killer.
*Where:* `thirteen_d.py:106–140` (`_download_pdf` entry + the mid-run
login-redirect path at `:124–139`); env helper currently at `digest.py:87–89`.
*Fix:*
- Move the `_unattended()` env check to `config.py` (avoids a circular import —
  digest already imports thirteen_d). `digest._unattended` becomes a thin delegate so
  its existing tests and callers are untouched.
- In `_download_pdf`: if unattended and no session file → print a loud
  `"13D session missing — manual re-login required (skipping WILTW)"` and return None
  **before** any Playwright work; on the mid-run login-redirect, same message, close
  the browser, return None instead of calling `_do_manual_login`.
- Attended behavior (flag unset) byte-identical.
*Verify:* unit tests: flag set + no session → returns None and a monkeypatched
`_do_manual_login` boom never fires; flag unset → login path reached (mocked);
`digest._unattended` delegation keeps `test_gmail_auth.py` green. O3 already treats a
wiltw zero-streak as a degradation signal — no new alerting needed.
*Residual (accepted):* the true server-side behavior (session-0 stdin, headed-launch
failure mode) is only provable at deploy. **Deploy-checklist addition:** on the box,
temporarily rename `thirteen_d_session.json`, trigger a run, confirm the loud skip
line in the log and no hang.
*Priority:* Medium-High (deploy-relevant). *Effort:* Small.

**Stage 2.5 verification plan:** `ruff` + full `pytest` green (~+4 tests). No
Playwright launched in tests, no Claude. No paid steps.

### Stage 2.6 — PyPDF2 → pypdf bump + index rebuild + eval re-baseline **(P1)**

2.6a **Dependency swap with measured revalidation** — `requirements.txt` + `search.py`.
*What:* PyPDF2 3.0.1 is officially unmaintained (pypdf is its renamed, active
continuation) and sits in the daily indexing path. The 3.3 review ungated this bump
(extraction is clean on the real corpus; "no motivating problem" — the motivation is
dependency hygiene before the box runs unattended for months).
*Where:* `requirements.txt:16`; `search.py:109` (`from PyPDF2 import PdfReader`) and
the ImportError message at `:111`.
*Fix + ordered verification (all free/offline):*
1. **Back up** `archive/index.faiss` + `archive/chunk_metadata.json` (plain file copy
   — this is the rollback).
2. Swap the pin to `pypdf==<current stable at implementation>`; import becomes
   `from pypdf import PdfReader`; update the ImportError text.
3. **Extraction diff:** run `_extract_pdf_text` old-vs-new over every
   `archive/*/pdfs/*.pdf` (the real 10-unique-PDF corpus) and review the diffs —
   expectation is near-identical text (pypdf is the same extraction lineage).
4. Full `python search.py --rebuild`; note the chunk count vs the current baseline
   (**3,948 vectors / 7 days** after the 7/10 run — small drift is expected only if
   extraction text differs).
5. `python tools/eval_retrieval.py --save post_pypdf` — **gate: hit@1 .846 /
   hit@3 1.0 / MRR .904 identical, or the delta goes to the operator for sign-off
   before anything is kept** (per HANDOFF constraint).
6. `ruff` + full `pytest` green.
*Rollback:* restore the two backed-up index files + revert the pin/import.
*Priority:* Medium. *Effort:* Medium (the work is verification discipline, not code).

**Stage 2.6 verification plan:** steps 3–6 above — extraction diff, rebuild, eval
harness, ruff+pytest. Entirely local; **no Claude calls**. This is the only stage
that can move the eval, and it carries the explicit operator gate. Do it **last** so
every other stage's test additions are already green underneath it.

---

## Sequencing summary

| Order | Stage | Items | Output change? |
|---|---|---|---|
| 1 | 1.1 Dead code | fred cache, dollar branches, dead loop, rank default | none |
| 2 | 1.2 Duplication/tooling | subject constant, watchlist import, ruff pin | none |
| 3 | 1.3 Wrappers | `exit /b 0` ×4 | none (exit code only) |
| — | *Phase 1 done → operator confirms → HANDOFF update (incl. stale §4 row)* | | |
| 4 | 2.1 Tests first | feeds, assemble-pin, archive | none (additive) |
| 5 | 2.2 Small correctness | funds escaping, auctions label/guard, COT find_contract, 13D download path | escaped HTML; honest labels |
| 6 | 2.3 State fixes | PACER ordered eviction, COT prior-week | fewer dupes; true WoW |
| 7 | 2.4 Weekly bundle | preamble strip, save-to-disk, new subject | **visible (approved)** |
| 8 | 2.5 13D guard | unattended fail-fast | unattended-only |
| 9 | 2.6 pypdf | dep bump + rebuild + re-baseline | none expected (eval-gated) |

**Budget note:** $0 of the ~$4.50 credit is needed by this spec. Test count grows
from 180 to roughly **~215–225** by completion.
