# Work Log

Running log of everything done in the Daily-Digest refactor, phase by phase (newest on top).
Companion to `HANDOFF.md` (the plan/spec) and its §11 "Needs Testing" (deferred verification).

---

## Current state (2026-06-19)

All refactor work to date is **committed** and validated **without secrets**; the integrated
pipeline has not yet run end-to-end. Commits in order: Phase 0 `1f400f6` → Phase 1 `f78ef45` →
de-hardcoding `e7b9a6c` → Phase 2 `d9dfd50` → A1 `a04f892` → Phase 3 `004722b`. Offline state:
`ruff` clean, all modules import/compile, free fetchers run, `pytest` 34 green.

**Everything doable + verifiable offline is done.** What's left is gated on secrets — see
`HANDOFF.md` §11 (ordered test plan once secrets land) and §12 (path to "done"). Headline remaining:
the first credentialed `digest.py` run (validates the whole stack), then the do-and-test items
(A2, 3.1, 3.3, Group B cost A/B), then §7.2 deploy.

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
