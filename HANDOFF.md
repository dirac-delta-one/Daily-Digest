# Daily Digest — Project Handoff

> Handoff for continuing a code-quality/refactor effort on this repo. Read this in full before
> making changes. The "Do NOT touch" section exists because several blunt-looking pieces of code
> are intentional and battle-tested — treat them as constraints, not bugs.

---

## 1. Objective & current state

**What it is:** A solo-operator Python automation that runs daily on a schedule. It gathers ~17
financial/market data sources (Gmail inbox + PDF attachments, paid Substack subs, SEC EDGAR, FRED,
Yahoo Finance, Octus, PACER, FINRA TRACE, 13F filings, rating actions, Treasury auctions, CFTC COT,
Fed balance sheet, FDIC, WSJ/FT RSS, 13D WILTW), summarizes them with Claude in a **two-pass**
flow (draft → review/enhance), emails an HTML "Daily Research Digest," archives all raw content to
disk, and indexes it into a local FAISS vector store that powers an **email-reply Q&A bot**.

**Current state:** Working and in daily production on *jared's* machine. It is being refactored on
the current machine (operator `acohen@acorninv.com`, Windows user `KimCohen`). Git branch:
`ava-updates`. The codebase is healthy: consistent module conventions, defensive `try/except`
around every source, sensible secret hygiene. No rewrite is warranted — only incremental,
low-risk improvements.

**Status (updated — Phases 0–1 done, offline):** The dev machine is stood up (Python 3.12 venv at `.venv`, all
deps + Playwright chromium installed) and **Phase 0 cleanup is complete, committed (`1f400f6`), and
validated without any secrets** — `ruff` clean, all 24 modules import/compile, 13 free fetchers run,
plus `pacer` pure-function asserts and a `search` index round-trip (incl. the 0.3 re-index path). The
LLM/Gmail/paid-scraper paths are import/compile-verified only and await a credentialed run — see §11
"Needs Testing." **Phase 1** (cost-pricing fix + model centralization in `config.py`, plus
HTML-escaping the pre-built sections) is also code-complete and unit-tested offline (committed
`f78ef45`).

**Stage-1 §7.1 machine de-hardcoding (offline-tested, no secrets — uncommitted):** the `.bat` wrappers
and `setup_tasks.bat` now use `%~dp0` + the project `.venv` + `PYTHONUTF8=1`; `DIGEST_RECIPIENTS`
is `DIGEST_TO`-env-driven (defaults to jared); acohen is on the reply-bot allow-list and reply
recipient; README paths/Substack notes updated. The User-Agent contact string is intentionally
**kept as jared** (see §7.1.6). Per-change history is in `WORKLOG.md`.

**End goal:** Stop depending on jared's personal computer. Migrate to a **dedicated, always-on
standalone Windows machine acting as a server** that runs the digest, midday alert, and reply
monitor unattended 24/7. The work happens in three stages: (1) get it running on the current dev
machine (`KimCohen`) for refactoring/testing — see §7; (2) apply the Phase 0–3 improvements; (3)
deploy to the dedicated Windows server — see §7.2. Stage 3 is the definition of "done."

**Module convention:** nearly every source module exposes `fetch_X()` (gather),
`format_X_for_prompt()` (text for the Opus prompt), and `build_X_html()` (pre-rendered HTML section).
`digest.py` orchestrates: fetch all → build prompt → 2-pass Claude → assemble HTML → send → archive
→ index → update memory → (Fridays) weekly summary.

---

## 2. Key constraints

- **Keep the model at `claude-opus-4-6`** for now; mark it as upgradeable (current latest is
  `claude-opus-4-8`, same API surface, $5/$25 vs 4.6's same $5/$25). Sonnet (`claude-sonnet-4-6`)
  and Haiku (`claude-haiku-4-5`) usages are already current.
- **This is a working single-operator tool.** Explicitness and tuned heuristics have real value;
  prefer small, reversible changes over architecture-level refactors.
- **Test between every phase.** Route all test output **locally or to `acohen@acorninv.com`** —
  never to the config recipients (jared's addresses) during testing.
- **External tooling falls into three cost tiers — know which before testing:**
  - **Pay-per-query (the only real per-call cost): the Anthropic/Claude API.** Token-billed across
    the 2-pass Opus digest, Haiku (news ranking), Sonnet (Octus ranking, PACER size-filter, midday),
    and Opus (13D summary, memory, alerts, reply bot). This is the *only* thing that costs money per
    run — **ask explicit permission before any test that calls Claude**, run once on a small input,
    and never loop the full digest.
  - **Flat paid subscriptions (already paid; zero marginal cost per run): Octus, Substack, 13D
    Research.** Scraped via saved login/cookies — no per-query charge, so free to test repeatedly.
    Only cautions: scraping etiquette / rate-limits, and that sessions expire and need a manual
    re-login. Octus and 13D *also* fire a small embedded Claude call (Octus = Sonnet ranking,
    13D = Opus summary) — that's a Claude cost, not a subscription cost; Substack has none.
  - **Free (no charge): everything else.** No-key public APIs — SEC EDGAR, Yahoo Finance, WSJ/FT &
    Google News RSS, Treasury, CFTC, FDIC, FINRA TRACE, PACER court RSS — plus local compute (FAISS +
    sentence-transformer embeddings). Also free but key/auth-gated: **Gmail API** (quota-limited,
    never billed) and **FRED** (free key). "Needs a key" ≠ "costs money": only the Claude key maps to
    per-use billing. *PACER nuance:* real PACER document retrieval is pay-per-page, but this code
    reads only the **free** court RSS feeds, so there are no PACER charges as written.
- **Don't burn tokens.** Never loop the full digest repeatedly. For LLM-touching paths, run once
  with permission, on a small input.

---

## 3. Terminology

- **Two-pass / pass 1 / pass 2:** Opus generates a draft digest (pass 1), then a second Opus call
  reviews the draft against the *same* source material and produces the final (pass 2). This is
  intentional and valued — keep it.
- **Cross-digest memory:** `memory.json`, an Opus-maintained running summary of evolving storylines
  injected into the next day's prompt (`memory.py`).
- **Archive / indexing / embedding:** After each run, raw content is saved to `archive/<date>/`,
  then chunked, **embedded** (text → 384-dim vectors via `sentence-transformers`) and **indexed**
  into a **FAISS** store (`search.py`). The reply-bot embeds an incoming question, finds nearest
  chunks, and feeds them to Opus.
- **Reply monitor:** `reply_monitor.py`, a long-running poller that answers email replies to digests
  via RAG over the archive.
- **Midday alert:** `midday.py`, an intraday materiality check that emails only if something
  important broke since the morning digest.

---

## 4. Relevant files

| File | Role |
|---|---|
| `digest.py` | Main orchestrator: Gmail, prompt build, 2-pass Claude, assembly, send, weekly. Config at top (lines ~48–64): `HOURS_LOOKBACK`, `MAX_EMAILS`, `MAX_PDF_SIZE_MB`, `DIGEST_RECIPIENTS`, `CLAUDE_MODEL`. |
| `substack.py` | API/cookie-based Substack scraper (magic-link auto-login via Gmail). Uses `substack_cookie.txt`. |
| `octus.py` | Playwright scraper (intel + primary deals). Uses `octus_session.json`. |
| `search.py` | FAISS index + chunking + embeddings + hybrid search. CLI: `--rebuild`, `--index <date>`. |
| `reply_monitor.py` | Email-reply RAG bot. Hardcoded recipient + `from:` allow-list. |
| `midday.py` | Intraday materiality alert (Sonnet). Imports from `digest.py`. |
| `memory.py`, `alerts.py`, `archive.py` | Cross-digest memory, plain-English alerts, raw-content archiver. |
| Source fetchers (free APIs) | `news.py`, `ratings.py`, `market_data.py`, `macro_data.py`, `sec_filings.py`, `treasury_auctions.py`, `cftc_cot.py`, `fed_balance_sheet.py`, `fdic_monitor.py`, `earnings.py`, `trace_data.py`, `fund_tracking.py`, `thirteen_d.py`, `fed_research.py`, `pacer.py`. |
| `*.bat`, `setup_tasks.bat` | Windows Task Scheduler wiring. **Hardcoded to jared's paths — see §7.** |
| `grab_session.py` | Stale manual helper (writes Playwright session for Substack, which no longer uses it). |

**Gitignored, account-bound secrets** (must exist on the machine; copy or regenerate):
`credentials.json`, `token.json` (Gmail), `substack_cookie.txt`, `octus_session.json`,
`thirteen_d_session.json`, `env.bat`, plus caches (`*_cache.json`, `pacer_seen.json`, `memory.json`).

**Env vars used:** `ANTHROPIC_API_KEY` (required), `FRED_API_KEY` (macro + fed balance sheet),
`SUBSTACK_EMAIL` (Substack magic-link). Note: `SUBSTACK_PASSWORD` appears in the README but is **not
used** by current code (Substack is cookie/magic-link based) — README is stale on this point.

---

## 5. Risks

- **Silent degradation:** the `try/except`-everywhere design means a broken source yields an empty
  section, not a crash. Failures are invisible without reading logs.
- **LLM-output coupling:** `_assemble_digest_html` finds insertion points by string-matching the
  Opus-generated HTML. Stable in practice (heavily-pinned prompt) but brittle if the template drifts.
- **HTML correctness:** scraped text/URLs are interpolated raw into the emailed HTML; special chars
  (`<`, `&`, `"`) can break rendering (low security risk — self-sent, client-sanitized).
- **Account binding:** the whole pipeline authenticates against *jared's* Gmail/Substack/Octus via
  the secret files above. Running on a new machine reuses those identities unless re-provisioned.
- **PDF extraction quality (reply-bot only):** PyPDF2 can fragment text; `_clean_pdf_text` patches
  this aggressively. Do not change without measuring against real archived PDFs.

---

## 6. Do NOT "fix" these — intentional / load-bearing

Investigated and confirmed as deliberate. Changing them adds risk for no benefit:

- **Module-level `--email_time=` argv parse** (`digest.py:51–57`): must run before the `def`s
  because `HOURS_LOOKBACK` is captured as a default-arg value at definition time. Correct placement.
- **`_clean_pdf_text` aggressive regexes** (`search.py:117–136`): likely rescue logic for
  PyPDF2 character-fragmentation on this corpus. Measure before touching (see Phase 3).
- **`build_ratings_html` unused in main flow** (`digest.py:1086` sets `ratings_html=""`):
  deliberate product decision ("Octus has better coverage"). Keep the function.
- **`_is_recent` returns `True` on unparseable dates** (news/ratings/substack): intentional
  over-inclusion; Opus curates downstream.
- **`reply_monitor` `while True` daemon:** deliberate (a `--once` mode also exists). Not a bug.
- **FAISS `IndexFlatIP`:** exact and correct for personal scale; revisit only at 100k+ chunks.

---

## 7. Machine migration

Two moves: **7.1** get it running on the current dev machine (do FIRST, before any testing), and
**7.2** the eventual deployment to a dedicated always-on Windows server (the end goal).

### 7.1 Dev machine (current — `KimCohen`)

The project is wired to jared's machine. Required to run here:

1. **`run_digest.bat`, `run_midday.bat`, `run_reply_monitor.bat`** — replace
   `cd /d C:\Users\jared\Daily-Digest` with `cd /d %~dp0` (script's own dir), and replace the
   hardcoded `C:\Users\jared\AppData\...\python.exe` with the current Python path (or a venv).
2. **`setup_tasks.bat`** — replace the three `C:\Users\jared\Daily-Digest\run_*.bat` targets in the
   `schtasks /TR` lines with `%~dp0run_*.bat`.
3. **`README.md`** — update the Task Scheduler example paths; drop the stale `SUBSTACK_PASSWORD` /
   Playwright-login Substack instructions (now cookie/magic-link).
4. **`env.bat`** (gitignored) — create on this machine with `ANTHROPIC_API_KEY`, `FRED_API_KEY`,
   `SUBSTACK_EMAIL`.
5. **Secret files** — copy `credentials.json`, `token.json`, `substack_cookie.txt`,
   `octus_session.json`, `thirteen_d_session.json` from jared's machine, OR re-provision (Gmail
   OAuth re-consent, Substack magic-link, Octus/13D manual login). These bind to *accounts*, not the
   machine.
6. **`EDGAR_USER_AGENT` / `USER_AGENT` contact string** (`sec_filings.py:27`, `pacer.py:27`,
   `trace_data.py:17`, `fund_tracking.py:19`) — SEC/PACER want a real contact. **Decision
   (2026-06-19): KEEP `jtramontano@acorninv.com`.** It's only a courtesy contact for the scraped
   servers' admins (SEC/PACER fair-access), not a credential, and jared stays the account
   identity anyway. This item is a **no-op** — do not switch it to acohen.
7. **Test-recipient override — send FROM jared, TO `acohen@acorninv.com`.** Gmail sends as the
   *authenticated* account (`service.users().messages().send(userId="me", ...)`), so mail goes out
   **from whichever Google account `token.json` belongs to**. The agreed test setup copies **jared's**
   `credentials.json` + `token.json`, so test emails are sent **from jared's mailbox**; the `To:` is
   overridden to **`acohen@acorninv.com`** so acohen receives them and jared's real
   `DIGEST_RECIPIENTS` do **not**. (Side effect: a copy lands in jared's *Sent* folder. If the mail
   must instead originate from acohen's own account, re-provision Gmail OAuth under acohen rather than
   copying jared's token.)

   For all testing, send to `acohen@acorninv.com`, not `DIGEST_RECIPIENTS` (jared). Recommended: make
   the recipient env-driven (e.g. `DIGEST_RECIPIENTS = os.environ.get("DIGEST_TO", "...").split(",")`)
   so tests set `DIGEST_TO` without editing code. To exercise the reply-bot, also add
   `acohen@acorninv.com` to the `from:` allow-list in `reply_monitor.py` (`check_for_replies`,
   ~line 182) and the recipient in `send_reply` (~line 463).

**Status (2026-06-19):** Items 1–3 and 7 applied in code and **offline-tested** — `ruff` +
`py_compile` clean; `DIGEST_TO` override confirmed (default→jared, override→acohen,
whitespace-stripped, inherited by `midday.py`/`reply_monitor.py`); and `run_digest.bat` executed up
to the credential check (`%~dp0` + project `.venv` + `mkdir logs` + non-fatal missing `env.bat` all
work, `PYTHONUTF8=1` verified — the `→` in the log is valid UTF-8, no cp1252 crash). Uncommitted.
Item 6 is a no-op (User-Agent contact kept as jared). Items 4 (`env.bat` with keys +
`DIGEST_TO=acohen`) and 5 (copy the gitignored secret files) remain manual operator steps — still
pending (no secrets yet). The remaining **full end-to-end (credentialed) verification is tracked in
§11**.

**Verify migration:** run a free standalone fetcher (e.g. `python news.py`) and confirm Gmail auth
works via a metadata-only call before anything else.

### 7.2 Dedicated Windows server (the end goal)

After the refactor (Phases 0–3) is validated on the dev machine, deploy to a **standalone,
always-on Windows machine that runs the three jobs unattended 24/7** — replacing jared's PC. Make
the codebase location-independent first (Phase 0–1 already remove the jared hardcodes via `%~dp0`
and `config.py`), then provision the server:

1. **Always-on + headless:** the box must stay powered, awake (disable sleep/hibernate), and survive
   reboots. The **reply monitor is a continuous process** — it only works while the machine is up,
   so an always-on server is what makes it reliable (today it's `ONSTART` on a personal PC).
2. **Run whether or not anyone is logged in:** create the scheduled tasks with
   `schtasks /RU <serviceacct> /RP <pw>` (or "Run whether user is logged on or not" + "Run with
   highest privileges"). `setup_tasks.bat` currently assumes an interactive session — update it.
   Confirm Playwright/Chromium (Octus, 13D) runs headless under a non-interactive session.
3. **Secrets/identity on the server:** install the §7.1 secret files and `env.bat` there. **Decide
   whose Gmail/Substack/Octus the server uses** — keep jared's identities (copy `token.json`,
   `credentials.json`, sessions) or re-provision to a service/`acohen` account. Set env vars at the
   **machine/system** level (not user) so non-interactive tasks see them.
4. **Reliability & observability:** rotate `logs/`; add failure alerting (e.g. email `acohen@` if a
   run errors or a key section is empty N days running) since no one is watching the console; verify
   sessions auto-renew (Substack magic-link via Gmail; Octus/13D will eventually need a manual
   re-login — document that).
5. **Time zone & schedule:** set the server TZ correctly (digest ~8 AM ET, midday ~1 PM ET, weekly
   summary keys off Friday in `digest.py`).
6. **Resources:** the embedding stack (`sentence-transformers` + `faiss-cpu` + torch, ~GB) plus a
   growing `archive/` need adequate disk/RAM; plan backups of `archive/`, `memory.json`, and the
   FAISS index.

This is a deployment/ops task, not a code refactor — schedule it **after** Phases 0–3 land, and make
each piece location- and account-independent as you go so the server install is pure configuration.

---

## 8. Testing protocol (applies between every phase)

- **Free, no permission needed:** offline unit tests of pure functions, and standalone fetchers that
  hit only free APIs: `python news.py`, `market_data.py`, `macro_data.py`, `sec_filings.py`,
  `ratings.py`, `treasury_auctions.py`, `cftc_cot.py`, `fed_balance_sheet.py`, `fdic_monitor.py`,
  `earnings.py`, `trace_data.py`, `fund_tracking.py`.
- **Requires permission (costs money/credits):**
  - Any path that calls Claude — full `digest.py`, `memory.py`, `alerts.py`, `midday.py`,
    `reply_monitor.py`, Octus/news ranking, **and `python pacer.py`** (its `__main__` can trigger
    Sonnet via the size filter when new filings exist).
  - Octus (`octus.py`) and Substack (`substack.py`) scraping — **flat subscriptions, no per-query
    cost; free to test** (see the cost tiers in §2). The Claude cost in the Octus path is its Sonnet
    *ranking* step (noted above); Substack scraping itself makes no Claude call.
- **Token discipline:** prefer unit tests; when an LLM path must run, run **once** on a **small**
  input (e.g. temporarily lower `MAX_EMAILS`), never in a loop. Do not re-run the full 2-pass digest
  to verify cosmetic changes — assert on intermediate functions instead.
- **Always** redirect email output to `acohen@acorninv.com` (or render HTML to a local file) during
  tests.
- **Deferred — FRED-dependent sources (test later):** `FRED_API_KEY` is optional and is **not** set
  on the dev machine (KimCohen). `macro_data.py` and `fed_balance_sheet.py` skip silently without it,
  so a "full" test run currently omits the Macro Dashboard + Fed Balance Sheet sections. Provision a
  FRED key and test those two sources separately, later.

---

## 9. Next steps — change spec (phased)

Each item: **what / where / fix / verify**. Do phases in order; test (per §8) between each.
Within a phase, items are ordered simplest-first. Priorities reflect the final reassessment.

### Phase 0 — Cleanup (zero output change, no LLM needed)

> ✅ **DONE** — committed `1f400f6`. All of 0.1–0.6 applied, plus `ruff.toml`, pinned
> `requirements.txt`, and `.venv/` gitignored. Validated without secrets (see §11 + `WORKLOG.md`).
> The `ruff format` whitespace pass in 0.5 was intentionally **not** run (only `ruff check` + fixes),
> so no separate format commit was needed.

0.1 **Remove vestigial import** — `pacer.py:240–241` `from search import search as _unused`.
Delete the two lines.
*Verify:* `python -c "import pacer"` succeeds; ruff clean.

0.2 **Remove dead 1-week cache branch** — `market_data.py:79–80`. The `elif ... "value_1w" in
prior_cache[label]` path can never fire (`value_1w` is never written by `_save_cache`), and
`period="1mo"` always returns ≥6 rows so the primary path always handles 1W. Delete the dead `elif`.
Do **not** "repair" it — the case doesn't occur.
*Verify:* `python market_data.py` still prints 1D/1W/1M.

0.3 **Remove duplicate model load** — `search.py:561` calls `_get_model()` a second time inside the
re-index branch (already called at ~549). Remove the redundant call; reuse the existing `model`.
*Verify:* `python search.py --index <an-already-indexed-date>` runs; embeddings identical.

0.4 **Pin dependencies** — `requirements.txt` has no version pins. Pin current resolved versions
(e.g. via `pip freeze` into a lockfile or pinned `requirements.txt`). Do **not** change PyPDF2 yet.
*Verify:* clean install in a fresh venv; `python news.py` runs.

0.5 **Add linting** — add `ruff` config; run `ruff check`. If applying `ruff format`, do it as a
**separate, isolated commit** (whitespace-only) to keep behavior diffs clean.
*Verify:* `ruff check` passes; no behavioral diff.

0.6 *(optional)* **Delete `grab_session.py`** — stale (writes a Substack Playwright session no longer
used). Confirm with user; it's inert either way.

**Test Phase 0:** ruff clean + free standalone fetchers run. No LLM, no email.

### Phase 1 — Low-complexity correctness/observability fixes

> ✅ **DONE (offline)** — `config.py` added; 1.1 + 1.2 applied and unit-tested without secrets,
> committed `f78ef45`. The optional end-to-end render check awaits credentials (see §11).

1.1 **Fix cost-estimate pricing + centralize model** — `digest.py:607–608` uses `15`/`75` per MTok
(stale original-Opus pricing); Opus 4.6 is **$5 / $25**. Create `config.py`:
```python
OPUS_MODEL = "claude-opus-4-6"   # TODO: upgradeable to claude-opus-4-8 (same API surface)
SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5"
OPUS_PRICE_IN, OPUS_PRICE_OUT = 5.0, 25.0  # $/MTok
```
Import `OPUS_MODEL` in the 5 files that hardcode `claude-opus-4-6` (`digest.py`, `memory.py`,
`alerts.py`, `reply_monitor.py`, `thirteen_d.py`); use the price constants in the cost calc.
*Verify:* unit-check the cost math against known token counts; no API call needed.

1.2 **HTML-escape build-step inputs** — all `build_*_html` interpolate scraped text/URLs raw:
`octus.py` (`build_deals_table_html`), `digest.py` (`build_news_html`), `ratings.py`,
`pacer.py` (`build_pacer_html`), `alerts.py`. Add a shared helper:
```python
import html
def esc(s): return html.escape(s or "", quote=True)
def safe_href(u): return esc(u) if (u or "").startswith(("http://","https://")) else "#"
```
Wrap every interpolated text value with `esc()` and every `href` with `safe_href()`. Scrapers
already unescape entities upstream, so this is double-encode-safe.
*Verify:* offline unit tests feeding titles/URLs containing `<`, `&`, `"`, and `javascript:` —
assert escaped output and neutralized scheme. No email send required.

**Test Phase 1:** offline unit tests for 1.1 and 1.2. Optionally, **with permission**, one
small end-to-end `digest.py` run (lowered `MAX_EMAILS`, recipient = `acohen@acorninv.com`) to
confirm the assembled email still renders.

### Phase 2 — Medium-complexity quality / cost (each independent)

> **Status (2026-06-19, uncommitted):** 2.2 / 2.3 / 2.4 ✅ done + offline-tested (see `WORKLOG.md`).
> **2.1 NOT done** — verified counterproductive as specced. Prompt caching is a strict prefix match
> over `tools → system → messages`; pass 1 and pass 2 use *different* `system` prompts (and pass 2
> puts the shared content after a review block), so they share no cacheable prefix → 0 cache reads
> plus a wasted ~1.25× cache-write on pass 1 = **net cost increase**. Making it cache needs an
> identical system + shared-content-first restructure that changes pass 2 and touches the §6
> load-bearing `SYSTEM_PROMPT`. **Decision (2026-06-19): 2.1 dropped.** Phase 2 is complete with
> 2.2 / 2.3 / 2.4.

2.1 **Prompt caching across passes** — `digest.py:summarize_with_claude`. Pass 1 and pass 2 send the
same `content` (text + PDFs); add `cache_control: {"type":"ephemeral"}` to the last shared content
block so pass 2 reads the prefix from cache. Output is unchanged (caching only affects cost/latency).
Keep the shared content as a byte-identical suffix in both calls.
*Verify (permission required):* one digest run; assert `response.usage.cache_read_input_tokens > 0`
on pass 2. Recipient = `acohen@acorninv.com`.

2.2 **JSON-fence parse helper** — the strip-```json-fences + `json.loads` block is copied in
`digest.py`, `octus.py`, `alerts.py`, `memory.py`, `pacer.py`, `reply_monitor.py`. Extract one
`claude_utils.parse_json_response(text)`. (Optional stronger version: switch `alerts.py`/`memory.py`
to structured outputs `output_config.format` to drop fence-stripping entirely.)
*Verify:* offline unit tests of the helper against fenced/unfenced/garbage inputs.

2.3 **RSS dedup (news + ratings only)** — extract shared `fetch_feed`/`parse_date`/`is_recent` into
`feeds.py`. Do **not** fold in `pacer.py` (genuinely different feed shape).
*Verify:* `python news.py` and `python ratings.py` produce the same items as before.

2.4 **Embedding-model singleton** — `search.py` `_get_model()` is called per `search()`; make it a
module-level lazy singleton so the long-running `reply_monitor` loads it once per process.
*Verify:* `python search.py "<query>"` returns same results; model loads once.

**Test Phase 2:** offline tests for 2.2/2.3/2.4; 2.1 needs one permissioned digest run.

### Phase 3 — Larger / conditional (do only if justified; tests recommended first)

3.1 **De-risk the 19-arg functions** — `_build_source_prompt` / `summarize_with_claude` take 19
positional args (misroute footgun). Convert to keyword-only or a single dict. This is the
high-value, low-risk slice of the original "source registry" idea; the **full registry refactor of
`main()` is optional** and only pays off if new sources are still being added.
*Verify:* end-to-end digest output is byte-identical to a saved baseline (permission required, once).

3.2 **Consolidate HTML strippers / Gmail body extractors** — `_HTMLStripper` (×3, intentionally
divergent) and the Gmail body extractors (×3, two mergeable). Only with unit tests that pin each
call site's current extraction behavior, since this feeds embeddings/prompts.

3.3 **PDF extraction review (C6 + PyPDF2→pypdf)** — measure `_clean_pdf_text` against real
`archive/*/pdfs/`: diff cleaned vs. raw, see how often the aggressive single-char-join rules fire.
Only then decide to gate them behind a fragmentation heuristic and/or switch PyPDF2→pypdf/pymupdf.
*Verify:* compare retrieval quality on a few known questions before/after.

3.4 **Targeted tests** — add `pytest` for the bug-prone pure functions: `pacer._extract_case_info`,
`_is_corporate_entity`, `_is_chapter_11_filing`; `reply_monitor._extract_question`,
`_extract_digest_date`; `search._chunk_text`; market/macro change math.

3.5 **Conditional, low priority:**
- `_assemble_digest_html` placeholder approach — **only if** archived digests show real section
  misplacement (no evidence yet; the fix risks the tuned SYSTEM_PROMPT).
- PACER company-sizing search API (`pacer.py:_search_company_size`) — Google scraping is fragile but
  degrades gracefully. A free-tier search API (e.g. Brave) or dropping the web step are options;
  low priority, low volume.

**Test Phase 3:** unit tests first; any end-to-end run is permissioned, once, to `acohen@`.

---

## 10. Quick reference — verdict summary

- **Genuine, do:** 0.1–0.5, 1.1, 1.2, 2.2, 2.3, 2.4, (3.1 de-risk args, 3.4 tests).
- **Conditional / measure first:** 3.2, 3.3, 3.5.
- **Withdrawn (intentional — see §6):** module-level argv parse; `_clean_pdf_text` blind edits;
  `build_ratings_html`; `_is_recent` true-on-unparseable; reply-monitor daemon; FAISS index type;
  **2.1 prompt caching (dropped 2026-06-19 — counterproductive as specced; the cache-correct version
  would change output / touch §6)**.
- **Constraint:** keep Opus 4.6 (mark upgradeable); test to `acohen@acorninv.com`; ask permission
  before any **Claude** call (the only pay-per-query cost — Octus/Substack/13D are flat subscriptions,
  free to test; see the §2 cost tiers); don't loop LLM calls.
- **End state ("done"):** running unattended 24/7 on a dedicated always-on Windows server, not
  jared's PC (§7.2) — deploy after Phases 0–3.

---

## 11. Needs Testing (deferred verification)

A running tracker of changes that are verified by inspection + import/compile but whose **runtime**
paths still need a credentialed/permissioned run to confirm. Add a subsection per phase; clear items
once a live run exercises them. The natural catch-all is the single permissioned end-to-end
`digest.py` run (drives `digest`, `substack`, `octus`, `pacer`, `thirteen_d` in one shot), plus
separate `midday.py` and `reply_monitor.py` runs.

### Phase 0 (committed `1f400f6`)

Import/compile-clean, but live execution not yet run (needs Claude key / Gmail creds / paid-scraper
sessions):

- **`digest.py`** — removed unused `os` import + `check_fed_stress` from the import line. Confirm a
  full digest still builds + sends. *(Aside: `check_fed_stress` was imported but never called — Fed
  stress signals aren't wired into the digest; pre-existing, candidate for a later phase.)*
- **`midday.py`** — removed unused imports + dead `today`/`day` locals in `send_alert_email`. Confirm
  a midday run (Sonnet + Gmail) still builds + sends the alert.
- **`reply_monitor.py`** — 4 f-string-prefix cleanups. Confirm a reply-bot run (Opus + Gmail) still
  answers and threads correctly.
- **`octus.py`** — removed unused `time` import. Confirm an Octus scrape + Sonnet ranking still runs
  (needs `octus_session.json`).
- **`substack.py`** — removed unused `json`/`base64` imports + dropped the unused `r =` binding (kept
  the side-effecting `session.get`). Confirm Substack fetch + magic-link login still works (needs
  `substack_cookie.txt`).
- **`thirteen_d.py`** — 2 f-string-prefix cleanups. Confirm a 13D fetch (session + Opus PDF summary)
  still works.
- **`pacer.py`** — removed a dead no-op `try/except` import block in `_search_company_size` + unused
  `datetime` import. Pure parsers are unit-tested; the permission-gated discovery → `_filter_by_size`
  (Sonnet) path was not run live (edit is provably behavior-neutral — just an unexercised path).

**Fully tested in Phase 0, no follow-up needed:** `market_data.py`, `search.py` (incl. the 0.3
re-index branch), `sec_filings.py`, `fund_tracking.py`, `earnings.py`, `treasury_auctions.py`,
`fdic_monitor.py`, `trace_data.py`, `ratings.py`, `fed_research.py`. `cftc_cot.py` ran but skipped on
weekday; `macro_data.py`/`fed_balance_sheet.py` ran but skip without a FRED key (§8 deferred note).

### Phase 1 (committed `f78ef45`)

1.1 (cost pricing + model centralization) and 1.2 (HTML escaping) are **fully unit-tested offline** —
no deferred verification of their own logic. Two notes for the eventual credentialed run:

- **Optional end-to-end render check** (per §9 Phase 1 test): one small permissioned `digest.py` run
  to `acohen@` to confirm the assembled email still renders with the now-escaped sections.
- `digest.py`, `memory.py`, `alerts.py`, `reply_monitor.py`, `thirteen_d.py` now `import config`; the
  live run will also exercise that wiring in the credentialed paths (already listed under Phase 0).

### Stage 1 — §7.1 machine de-hardcoding (uncommitted)

**Offline-verified (done 2026-06-19):** `ruff` + `py_compile` clean; `DIGEST_TO` env override
(default→jared, override→acohen, whitespace-stripped, inherited by `midday.py`/`reply_monitor.py`);
`run_digest.bat` executed to the credential check (`%~dp0` + project `.venv` + `mkdir logs` +
non-fatal missing `env.bat`; `digest.py` fails fast at missing `credentials.json` — no network/no
Claude); `PYTHONUTF8=1` confirmed (UTF-8 log, no cp1252 crash).

**TODO — full end-to-end de-hardcoding test (needs secrets; one permissioned run each):** once
`env.bat` (incl. `DIGEST_TO=acohen@acorninv.com`) and the secret files are installed, run each
wrapper for real and confirm:
- `run_digest.bat` → builds + sends a digest **to acohen** (FROM jared), writes `logs\digest.log`,
  archives + indexes, no path/encoding errors. *(Permissioned — Claude calls.)*
- `run_midday.bat` → midday check runs and emails **to acohen** only if material (or `--force`).
- `run_reply_monitor.bat` → starts headless, picks up an acohen reply (allow-list), answers **to
  acohen** and threads correctly; confirm the `while True` loop survives under the scheduled task.
- `setup_tasks.bat` → registers the three tasks with `%~dp0` paths (run on the target machine —
  not executed anywhere yet; it creates real scheduled tasks).
- Confirm non-interactive scheduled runs see `PYTHONUTF8`/env vars and that Playwright/Chromium
  runs headless under Task Scheduler (Octus / 13D).
