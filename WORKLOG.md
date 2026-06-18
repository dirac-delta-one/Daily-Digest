# Work Log

Running log of everything done in the Daily-Digest refactor, phase by phase (newest on top).
Companion to `HANDOFF.md` (the plan/spec) and its §11 "Needs Testing" (deferred verification).

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
