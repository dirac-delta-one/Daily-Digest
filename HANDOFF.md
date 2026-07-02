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

**Status (current):** **LIVE-validated end-to-end** on the bot identity (2026-06-30) and now being
*optimized*. `ruff` clean, `pytest` **60** green. The **cost refactor is complete** (2026-07-01 — the
Group B A/B kept all Opus; then landed the 13D summary cache, memory→Sonnet, and 2-pass prompt caching;
see §11 / §14 + `WORKLOG`). The **next major track is the memory / retrieval refactor**, scoped + reviewed
in **`MEMORY_REFACTOR_SPEC.md`** (eval harness → reranker → hybrid search → entity metadata → System A↔B
convergence) — **Stages 0–1 built 2026-07-01** (eval harness + baseline; reranker mechanism + the
date-filter fix — the reply-bot rerank opt-in is deferred until the archive is deep enough for the
eval to discriminate); **Stage 2 (hybrid BM25 + caching) is next**. Other open items: the
**§7.2 server deploy** (the definition of
"done"), the **§13** coverage gaps, and the data-gated **3.3** PDF review — see **§11 / §12 / §13 / §14**.

> ➡️ **Group B cost A/B — DONE 2026-07-01 (quality verdict: keep all four calls on Opus).**
> The permissioned A/B (~$1.89) ran all four embedded/secondary calls through Opus 4.8 and Sonnet 4.6 on
> real 2026-06-30 inputs. Reply (Sonnet render bug: ```html fence + full HTML doc) and 13D (Sonnet blew
> the 500–800-word cap) have quality catches. Full results in `WORKLOG.md` (2026-07-01) and §11 / §14.A.
>
> ➡️ **Cost refactor steps 1–2 — DONE 2026-07-01** (`pytest` **60** green): (1) **13D WILTW summary cache**
> (`wiltw_cache.json`) — stops re-summarizing the same weekly PDF 4–6×/week (~$130–150/yr, zero quality
> impact); (2) **memory → Sonnet** — a *cost* follow-up (memory output near-identical, ~$0.16/run);
> (3) **2-pass digest prompt caching** — restructured so pass 1 writes the source/PDF prefix to cache and
> pass 2 reads it (~$0.10/run text-day, ~$0.54/run PDF-day). Validated output-equivalent + cache-engaging
> via a permissioned before/after; supersedes the old §14.E "2.1 dropped" finding.
>
> ➡️ **NEXT MAJOR TRACK — the memory / retrieval refactor, scoped + reviewed in `MEMORY_REFACTOR_SPEC.md`
> (Stages 0–1 built 2026-07-01; Stage 2 next).** Improves the RAG reply bot (reranker → hybrid search →
> entity/date metadata) and converges the two "memory" systems (the cross-digest `memory.json`
> storylines vs. the FAISS archive) so it can "piece together" across time. Mostly local/free to build
> + test. The 2026-07-01 review restructured the spec (Stage 3 split into 3a metadata / 3b conditional
> reindex) and surfaced two latent `search()` findings: the post-retrieval date-filter scaling bug
> (**fixed in Stage 1**) and the per-call index reload (→ Stage 2). Stage 1's reranker is built +
> param-gated but the **reply-bot opt-in is deferred** — the 1-day-archive eval can't discriminate
> (digest-chunk duplication artifact; see the spec's Stage 1 notes and WORKLOG). **Other open
> tracks:** §7.2 server deploy (= "done"), §13 coverage gaps.

**Phase 0–3 refactor commits (pre-live-run history):**

| Commit | What |
|---|---|
| `1f400f6` | **Phase 0** — cleanup, `ruff`, pinned deps, dead-code removal, `grab_session.py` deleted |
| `f78ef45` | **Phase 1** — `config.py` (models + pricing), cost-pricing fix, `OPUS_MODEL` centralized, HTML-escaped the scraped `build_*_html` |
| `e7b9a6c` | **Stage-1 §7.1 de-hardcoding** — `.bat`/`setup_tasks.bat` use `%~dp0` + project `.venv` + `PYTHONUTF8=1`; recipients `DIGEST_TO`-env-driven; reply-bot allow-list/recipient include acohen |
| `d9dfd50` | **Phase 2** — 2.2 `claude_utils.parse_json_response`, 2.3 `feeds.py`, 2.4 `search` embedding singleton (2.1 prompt caching **dropped** — §9/§10) |
| `a04f892` | **A1** — `cost.py` per-run cost accounting across *all* Claude calls |
| `004722b` | **Phase 3** — 3.4 `tests/` + `pytest`, 3.2 `html_utils.py` HTML/Gmail-extractor consolidation |
| `5d041f0` | **Docs** — consolidated §1 status / §11 / §12 + `WORKLOG.md` snapshot |

**Post-live optimization session (committed 2026-06-30, commits `62002e0`→`543065a`):**
- **Opus 4.6 → 4.8** upgrade (pricing re-verified against the claude-api reference: still $5/$25).
- **Centralized in `config.py`:** the Sonnet/Haiku model IDs (were scattered literals) and the two
  User-Agent strings (`USER_AGENT` contact for EDGAR/PACER; `FEED_USER_AGENT` for RSS/data feeds).
- **Dead code removed:** new `net_utils.py` (dedup of the EDGAR fetch + the unverified-SSL context);
  `fed_research` date helpers → `feeds`; `market_data` write-only cache; `reply_monitor.SCRIPT_DIR`;
  and `build_ratings_html` (§9 is Opus-written — §6/§14.D).
- **3.1** — `_build_source_prompt` / `summarize_with_claude` are now **keyword-only** (misroute-proof).
- **Fed-stress alert → numeric:** `check_fed_stress` ($25B/$10B) wired into `digest.main` (merged into
  the alert box); the stale `$5B` LLM rule removed from `alerts_config.json` (§14.D).
- **SYSTEM_PROMPT §9** made an explicit Opus-owned section (fixed a latent "do NOT generate §9"
  contradiction — Opus writes §9 Rating Actions from the data).
- **A2 structured outputs** (`output_config.format`) on all 5 JSON call sites — guaranteed-valid JSON,
  no silent parse-drops; live-confirmed on Opus 4.8 / Sonnet 4.6 / Haiku 4.5 (§11 "Cost/efficiency").
- Test suite 34 → **56**; `ruff` clean. Full detail in `WORKLOG.md` (2026-06-30 entries).

**Update (2026-06-30) — newest:**
- **System is LIVE-validated end-to-end.** First credentialed run of the whole stack succeeded, all
  → acohen: `digest.py` **$1.52** (sent, rendered, archived, 629-chunk FAISS index, `memory.json`
  updated), `reply_monitor.py --once` **$0.20** (high-quality RAG answer, threaded back),
  `midday.py --force` **$0.01** (Sonnet → NO_ALERT, correct). ~$1.73 of the $20 spent. This clears the
  §11 backlog steps 0–3; full detail in WORKLOG (2026-06-30).
- **FRED provisioned + tested** — `FRED_API_KEY` in `env.bat`; `macro_data.py` (12 series) and
  `fed_balance_sheet.py` (6 series) now active. ⚠️ **But** the Fed-balance-sheet series labels are wrong
  by magnitude (see §13 "Data bugs") — needs a series-ID audit before that section is trusted.
- **Octus removal validated live** (the digest ran Octus-free, no hang).

**Update (2026-06-29):**
- **Email identity → `acorn.research.bot@gmail.com`.** The recipient/allow-list personal-gmail and the
  SEC/PACER scraping User-Agent now point at the bot; the bot's Gmail OAuth is provisioned and verified
  (it reads its own inbox — jared forwards research in — and sends/replies as the bot). See §7 item 8.
- **Octus removed.** `octus.py` + `octus_session.json` deleted; all wiring stripped from `digest.py`,
  `archive.py`, `search.py` (Jared's directive to stop using Octus; the stale login also would have
  *blocked an unattended run* on its interactive re-login prompt). Lost: the Octus Intelligence feed and
  the Primary Deal Tracker. The new-issue HY deal table has **no free replacement**; the distressed
  *news* is partly covered by PACER + ratings + the credit Substacks. Existing archived Octus data is
  left intact (still searchable). *(Note: the free RSS rating data still flows, and **Opus writes the
  §9 Rating Actions section from it** — confirmed in the 2026-06-30 run. There was never a missing
  section; the dead `build_ratings_html` raw-table renderer was removed 2026-06-30 — see §6 / §14.D.)*
- **Anthropic key** ($20 credit) is in `env.bat` — the first credentialed run is unblocked.

**Credential bring-up — COMPLETE (2026-06-30).** The 2026-06-21 blockers below are all resolved;
this block is retained only as a record of how the bring-up landed:
- The `get_gmail_service` RefreshError hardening + `tests/test_gmail_auth.py` are **committed**
  (`1b714e1`); suite is **36** green.
- **All secret files are present and working** on the dev machine: `credentials.json`; `token.json`
  (re-provisioned as the bot `acorn.research.bot@gmail.com` and OAuth-verified — the dead copied
  refresh token that returned `invalid_grant` on 2026-06-21 has been replaced); `substack_cookie.txt`
  (validated); `thirteen_d_session.json` (healthy, exercised in the live run); and `env.bat`
  (`ANTHROPIC_API_KEY` = the $20 key, `FRED_API_KEY`, `DIGEST_TO=acohen`, `PYTHONUTF8=1`).
  `octus_session.json` is **gone** (Octus removed 2026-06-29).
- The Anthropic-key blocker is **cleared**, and the first small permissioned run plus the §11 ordered
  test plan (steps 0–3 and 5) have **executed green** (see the 2026-06-30 update above). **Step 4**
  (the `.bat` / `setup_tasks.bat` scheduling test) is the only §11 item left, deferred to the §7.2
  server deploy.

**End goal:** Stop depending on jared's personal computer. Migrate to a **dedicated, always-on
standalone Windows machine acting as a server** that runs the digest, midday alert, and reply
monitor unattended 24/7. The work happens in three stages:
1. **Get it running on the current dev machine (`KimCohen`)** for refactoring/testing — ✅ **DONE**
   (§7.1; secrets installed, first live end-to-end run green 2026-06-30).
2. **Apply the Phase 0–3 improvements** — ✅ **DONE and committed**: Phase 0 cleanup, Phase 1
   correctness/escaping, Phase 2 quality/cost, Phase 3.2/3.4, **3.1** (digest-core keyword-only
   refactor), **A2** (structured outputs, live-confirmed 2026-06-30), the §7.1 de-hardcoding, A1 cost
   accounting, the Gmail hardening, and the **Opus 4.8 upgrade + model/User-Agent centralization +
   dead-code cleanup**. The optional *do-and-test* items remaining: **3.3** PDF-extraction review and
   **3.5** (conditional). (**Group B** Opus→Sonnet cost A/B is **done** — 2026-07-01, kept all Opus.)
3. **Deploy to the dedicated Windows server** — ⬜ **the remaining work** (§7.2), and the definition
   of "done."

**Module convention:** nearly every source module exposes `fetch_X()` (gather),
`format_X_for_prompt()` (text for the Opus prompt), and `build_X_html()` (pre-rendered HTML section).
`digest.py` orchestrates: fetch all → build prompt → 2-pass Claude → assemble HTML → send → archive
→ index → update memory → (Fridays) weekly summary.

---

## 2. Key constraints

- **Opus is now `claude-opus-4-8`** (upgraded from 4.6 on operator's instruction — same API
  surface, same $5/$25 pricing). All model IDs are centralized in `config.py`
  (`OPUS_MODEL` / `SONNET_MODEL` / `HAIKU_MODEL`); every Claude call site imports them, so a future
  model bump is a one-line change in `config.py`. Sonnet (`claude-sonnet-4-6`) and Haiku
  (`claude-haiku-4-5-20251001`) are current.
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
  - **Flat paid subscriptions (already paid; zero marginal cost per run): Substack, 13D
    Research.** (Octus was **removed 2026-06-29** — see §1.) Scraped via saved login/cookies — no
    per-query charge, so free to test repeatedly. Only cautions: scraping etiquette / rate-limits,
    and that sessions expire and need a manual re-login. 13D *also* fires a small embedded Claude
    call (Opus summary) — that's a Claude cost, not a subscription cost; Substack has none.
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
| `search.py` | FAISS index + chunking + embeddings + hybrid search. CLI: `--rebuild`, `--index <date>`. |
| `reply_monitor.py` | Email-reply RAG bot. Hardcoded recipient + `from:` allow-list. |
| `midday.py` | Intraday materiality alert (Sonnet). Imports from `digest.py`. |
| `memory.py`, `alerts.py`, `archive.py` | Cross-digest memory, plain-English alerts, raw-content archiver. |
| Source fetchers (free APIs) | `news.py`, `ratings.py`, `market_data.py`, `macro_data.py`, `sec_filings.py`, `treasury_auctions.py`, `cftc_cot.py`, `fed_balance_sheet.py`, `fdic_monitor.py`, `earnings.py`, `trace_data.py`, `fund_tracking.py`, `thirteen_d.py`, `fed_research.py`, `pacer.py`. |
| `*.bat`, `setup_tasks.bat` | Windows Task Scheduler wiring. **Hardcoded to jared's paths — see §7.** |
| `grab_session.py` | Stale manual helper (writes Playwright session for Substack, which no longer uses it). |

**Gitignored, account-bound secrets** (must exist on the machine; copy or regenerate):
`credentials.json`, `token.json` (Gmail), `substack_cookie.txt`,
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
- **Rating Actions §9 is Opus-written, not pre-rendered.** Opus writes the digest's §9 "Rating Actions"
  from the rating data (SYSTEM_PROMPT), unlike other sources which pre-render their HTML section. The
  old `build_ratings_html` raw-table renderer was **removed as dead code 2026-06-30** (zero references;
  it would have *duplicated* Opus's §9; recoverable from git). **Gotcha:** don't "restore" a ratings
  table without also suppressing Opus's §9, or you'll get two §9 sections. (§14.D)
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
6. **`EDGAR_USER_AGENT` / `USER_AGENT` contact string** (`sec_filings.py:27`, `pacer.py:29`,
   `trace_data.py:17`, `fund_tracking.py:19`) — SEC/PACER want a real contact. ~~Decision
   (2026-06-19): KEEP `jtramontano@acorninv.com`.~~ **SUPERSEDED 2026-06-29 (see item 8): the
   contact is now `acorn.research.bot@gmail.com`.** It's only a courtesy contact for the scraped
   servers' admins (SEC/PACER fair-access), not a credential.
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

8. **Email-identity migration → `acorn.research.bot@gmail.com`** (decision 2026-06-29; overrides the
   "keep jared" stance of items 6–7). A dedicated bot account becomes the system identity: it is the
   SEC/PACER scraping contact, it replaces jared's personal gmail in the recipient/allow-list, and it
   will *eventually* be the authenticated Gmail mailbox that sends and reads.

   **Done now (code, committed on `ava-updates`):**
   - Swapped `jaredtramontano@gmail.com` → `acorn.research.bot@gmail.com` in the `DIGEST_RECIPIENTS`
     default (`digest.py`) and the reply `from:` allow-list (`reply_monitor.py`). *(Testing still
     routes to acohen via `DIGEST_TO`; this only changes the production default — jared's **work**
     address `jtramontano@acorninv.com` is unchanged.)*
   - Switched the scraping User-Agent contact to the bot in `sec_filings.py`, `pacer.py`,
     `trace_data.py`, `fund_tracking.py` (behavior-neutral courtesy contact).

   **NOT done — the sender/mailbox flip is deferred (operator; plan-only).** The authenticated Gmail
   account is both the *sender* and the *inbox that gets summarized*. Flipping it to the bot makes the
   digest read the **bot's (empty) inbox**. Of all ~17 sources, only these are tied to the
   authenticated account and **must be migrated to the bot first**:

   | Source to migrate | Why it's tied to the mailbox |
   |---|---|
   | **Inbox emails** (`fetch_recent_emails`, `in:inbox`) — forwarded research PDFs, broker/market commentary, **Bloomberg** (digest §7) | 100% the authenticated inbox; the bot's inbox is empty until these subscriptions/forwards point at it. This curated PDF layer is **not** replicated by any automated source — it's the high-value loss. |
   | **Substack** (`substack.py`) | `substack_cookie.txt` is Substack-account-tied (works until it expires); **auto-renewal** reads the authenticated inbox for the magic link, so renewal needs the bot to be the Substack account + `SUBSTACK_EMAIL=bot`. |

   **Unaffected by the flip** (own keys/sessions or free public APIs — keep working regardless of which
   account sends): SEC EDGAR, 13F fund tracking, WSJ/FT, rating actions, central-bank research, PACER,
   market data, earnings, FRED macro + Fed balance sheet, Treasury auctions, CFTC COT, FINRA TRACE,
   FDIC, 13D WILTW (own session), Octus (own session).

   **Flip sequence (when ready):** (a) forward research email + move Substack subscriptions to the bot
   → (b) OAuth re-provision as the bot (remove `token.json`, run consent as
   `acorn.research.bot@gmail.com`; add it as a **test user** in the `credentials.json` Cloud project if
   you hit "access blocked") → (c) sender, replies, and the read inbox all become the bot. Keep
   `token.json` = jared until (a) is in place so the inbox source never goes dark mid-transition.

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
   **machine/system** level (not user) so non-interactive tasks see them. **Critical for Gmail:**
   the Google OAuth app must be in **"production" publishing status** — Testing-mode refresh tokens
   expire after 7 days and would break the digest weekly under unattended operation. (We saw a
   *copied* `token.json` already rejected with `invalid_grant`; `get_gmail_service` now re-consents
   on refresh failure instead of crashing, but a headless server can't do an interactive consent —
   so a non-expiring production token is the real requirement.)
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
  - Substack (`substack.py`) scraping — **flat subscription, no per-query cost; free to test**
    (see the cost tiers in §2). Substack scraping itself makes no Claude call.
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

> **Status (committed `d9dfd50`):** 2.2 / 2.3 / 2.4 ✅ done + offline-tested (see `WORKLOG.md`).
> **2.1 (prompt caching) dropped** — counterproductive as specced; rationale moved to §14.E. Phase 2
> is complete with 2.2 / 2.3 / 2.4.

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

**Test Phase 2:** offline tests for 2.2/2.3/2.4.

### Phase 3 — Larger / conditional (do only if justified; tests recommended first)

> **Status:** 3.1 / 3.2 / 3.4 ✅ done (committed `004722b` + 2026-06-30); suite now **41 tests**.
> **3.3 and 3.5 are deferred / conditional — moved to §14 (Flagged / Deferred)** so this breakdown
> shows only completed cleanup.

3.1 **De-risk the 19-arg functions** — ✅ **DONE 2026-06-30.** `_build_source_prompt` /
`summarize_with_claude` (17 same-typed source args, a misroute footgun) are now **keyword-only**
(`def f(*, ...)`); both call sites pass named args. The **full registry refactor of `main()` was
left out** (optional; only pays off if new sources are still being added).
*Verified offline:* `tests/test_digest_prompt.py` pins the keyword-only contract (positional → `TypeError`),
per-source routing (a sentinel per source lands in its own section), and determinism — no permissioned
run required (the change is a mechanical signature swap).

3.2 **Consolidate HTML strippers / Gmail body extractors** — ✅ **DONE** (commit `004722b`). New
`html_utils.py` consolidates the search/sec_filings `_HTMLStripper` + the digest/reply_monitor Gmail
body extractor (substack's divergent ones left alone); pinned by `tests/test_html_utils.py`.

3.4 **Targeted tests** — ✅ **DONE** (commit `004722b`). `pytest` for the bug-prone pure functions:
`pacer._extract_case_info`, `_is_corporate_entity`, `_is_chapter_11_filing`;
`reply_monitor._extract_question`, `_extract_digest_date`; `search._chunk_text`; market/macro math.

*(3.3 PDF-extraction review and 3.5 conditional items → §14.A / §14.B.)*

**Test Phase 3:** unit tests first; any end-to-end run is permissioned, once, to `acohen@`.

---

## 10. Quick reference — verdict summary

- **Done (cleanup phases — see §9):** Phase 0 (0.1–0.6), 1.1, 1.2, 2.2, 2.3, 2.4, 3.1, 3.2, 3.4 —
  plus the §7.1 de-hardcoding, A1 cost accounting, the Opus 4.8 upgrade + model/UA centralization +
  dead-code cleanup.
- **Flagged / deferred (fine for now — see §14):** 3.3 (PDF review), 3.5 (conditional). **Cost work
  done 2026-07-01:** Group B A/B (kept all Opus), the 13D summary cache, memory→Sonnet, and **Group C
  (2-pass prompt caching)**. **A2 structured outputs — done + live-confirmed 2026-06-30.** The low-value
  dedups are all done (§14.C), and both former
  "decisions" are resolved (Fed alert → numeric; `build_ratings_html` clarified — §9 is already
  Opus-written, so left off) (§14.D). 2.1 prompt caching dropped (§14.E).
- **Do NOT fix (intentional / load-bearing — see §6):** module-level argv parse; `_clean_pdf_text`
  blind edits; `_is_recent` true-on-unparseable; reply-monitor daemon; FAISS index type.
- **Constraint:** Opus is `claude-opus-4-8` (upgraded from 4.6); model IDs centralized in
  `config.py`; test to `acohen@acorninv.com`; ask permission
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

**✅ EXECUTED 2026-06-30 (see WORKLOG).** Steps 0–3 + 5 below are DONE and green — the credentialed
`digest.py` / `reply_monitor.py --once` / `midday.py --force` runs all passed → acohen, and the FRED
sources are live. **Step 4 remains** (the `.bat` wrappers + `setup_tasks.bat`), to be done with the
§7.2 deploy. Original plan retained below for reference.

**Once secrets land — ordered test plan (one pass validates the whole committed stack):**

0. **Provision** (§7.1.4–5): create `env.bat` with `ANTHROPIC_API_KEY` (+ optional `FRED_API_KEY`,
   `SUBSTACK_EMAIL`) and **`DIGEST_TO=acohen@acorninv.com`**; copy jared's `credentials.json` /
   `token.json` / `octus_session.json` / `thirteen_d_session.json` / `substack_cookie.txt`. Sanity:
   `python news.py` + a Gmail metadata-only call before anything paid. **Note (2026-06-21):** a
   *copied* `token.json` may be dead (refresh token → `invalid_grant`); if so, remove it and do a
   fresh OAuth consent as the mailbox owner (jared — the digest reads his inbox as a source).
   `get_gmail_service` now re-consents automatically on refresh failure instead of crashing. The
   Octus session may also need a `--login` refresh (its cookies expire).
1. **One small permissioned `digest.py` run** (lower `MAX_EMAILS`, recipient = acohen). This single
   run exercises almost everything deferred below: the 2-pass Opus flow + now-escaped sections (P1);
   the Gmail / Substack / Octus / PACER / 13D credentialed paths (P0); the `config` / `claude_utils`
   / `feeds` / `html_utils` wiring (P2 / 3.2); and the **A1 cost summary** (confirm the printed total
   looks sane). Confirm: email renders, `archive/<date>/` + FAISS index written, `memory.json`
   updated, no path/encoding errors.
2. **`python midday.py --force`** → Sonnet materiality check + Gmail send to acohen.
3. **`python reply_monitor.py --once`** → reply from acohen, RAG answer threads back to acohen.
4. **The `.bat` wrappers** end-to-end + `setup_tasks.bat` on the target machine (Stage-1 detail below).
5. **FRED sources:** set `FRED_API_KEY`, then `python macro_data.py` + `python fed_balance_sheet.py`
   (skipped silently without the key today).

**Then the deferred do-AND-test items** (each its own small permissioned run — see §12): 3.3
PDF-extraction review. (The Group B cost A/B is **done** — 2026-07-01, kept all Opus. A2 structured
outputs and 3.1 digest-core arg refactor are **done** — A2 live-confirmed 2026-06-30, 3.1 offline.)
Per-area detail follows.

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

### Stage 1 — §7.1 machine de-hardcoding (committed `e7b9a6c`)

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

### Phase 2 & 3 (committed `d9dfd50`, `004722b`)

2.2 / 2.3 / 2.4 and 3.4 / 3.2 are **fully offline-tested** (unit tests + `pytest` 34 green + live
free-RSS runs); no deferred verification of their own logic. The credentialed `digest.py` run
(step 1 above) will additionally exercise the `claude_utils` / `feeds` / `html_utils` wiring in the
live paths. 2.1 was dropped (no test needed).

### Cost/efficiency optimizations (A1 committed `a04f892`; A2 done 2026-06-30)

- **A1 — per-run cost accounting (`cost.py`)** — code-complete + offline-tested (pricing math +
  multi-tier aggregation). The live behavior (the end-of-run cost summary printed by `digest.py` /
  `midday.py` / `reply_monitor.py`) will be exercised by the eventual credentialed run — just
  confirm the printed totals look sane. Measurement only, no logic risk.
- **A2 — structured outputs (`output_config.format`) — ✅ DONE + live-confirmed 2026-06-30.** All 5
  JSON call sites now pass `output_config=json_schema_output(SCHEMA)` so Claude returns
  guaranteed-valid JSON — no fence-stripping, no silent parse-failure drops (the key win for
  alerts/memory). Support confirmed live on Opus 4.8 / Sonnet 4.6 / Haiku 4.5 via the native
  `output_config=` kwarg (SDK 0.109.2; no `extra_body` needed). Schemas (in `claude_utils`
  `json_schema_output` / `wrapped_array_schema`): alerts → object with a `results` array (nullable
  `detail`/`source` via `["string","null"]`); memory → nested story object; the 3 rankers (news/Haiku,
  pacer/Sonnet, reply/Sonnet) → object with a wrapped `indices`/`queries` array (structured outputs
  want a top-level object, so array returns are wrapped + unwrapped after parse). All 5 exercised live
  on small inputs (~$0.04 total); offline unit tests in `tests/test_claude_utils.py`.
- **Group B — Opus→Sonnet cost A/B — ✅ DONE 2026-07-01 (ran ~$1.89; decision: KEEP ALL FOUR ON OPUS).**
  Operator chose to A/B all four. Single-call results: alerts $0.098 vs $0.042; memory $0.278 vs $0.116;
  13D $0.721 vs $0.425; reply $0.139 vs $0.065. **Quality findings:** reply Sonnet was **malformed**
  (```html fence + full `<!DOCTYPE html>` doc → broken email); 13D Sonnet **blew the 500–800-word cap**
  (~1,900 words, would bloat the digest 3×); memory near-identical (Opus kept 2 more credit stories —
  Wynn downgrade, PE debt-like deals); alerts identical (0/7). **Decision: keep all four on Opus** —
  quality catches on reply/13D, savings too small on memory/alerts (~$0.06–0.16/run vs a ~$1.50/day
  system). **No code changes *from the A/B itself*.** 13D→Sonnet is only viable *with a tightened length
  prompt*; reply must stay Opus. Detail in WORKLOG (2026-07-01). The original plan is retained below for
  reference. **Cost follow-up (2026-07-01):** a separate cost refactor then landed the 13D **summary
  cache** (biggest win, orthogonal to model choice) and moved **memory → Sonnet** for cost (near-identical
  output) — so memory now runs Sonnet; alerts/13D/reply stay Opus.

  The plan was: move the *embedded/secondary* Opus calls to **Sonnet 4.6** ($3/$15 vs Opus 4.8 $5/$25 ≈
  **40% cheaper/call**) **where quality holds**. **Not** the main 2-pass digest (stays Opus — the marquee
  output) and **not** the news/pacer rankers (already Haiku/Sonnet). Four candidates, with live-run cost
  + est. saving:

  | Call | Location | Live cost (2026-06-30) | ~Saving |
  |---|---|---|---|
  | **13D WILTW summary** | `thirteen_d._summarize_pdf` (`CLAUDE_MODEL`) | **$0.65** (the run's cost driver — 4.7MB PDF) | ~$0.26/run |
  | **Reply answer** (RAG) | `reply_monitor.answer_question` (`REPLY_MODEL`) | **$0.20**/reply | ~$0.08/reply |
  | **Memory update** | `memory.update_memory` (`CLAUDE_MODEL`) | small | ~$0.04/run |
  | **Alerts eval** | `alerts.evaluate_alerts` (`CLAUDE_MODEL`) | small | ~$0.01/run |

  Realistic savings ≈ **$0.30–0.35/digest** (mostly 13D) + ~$0.08/reply — modest in absolute terms
  (system runs ~$1.50/day) but compounds on the always-on server. **The A/B has no automated metric —
  it's a per-call judgment:** run the *same real input* (from the archive — `source_text` for alerts,
  the archived `WILTW_2026-06-25.pdf` for 13D, a real reply question over the FAISS index) through
  **both Opus and Sonnet**, compare outputs side-by-side + cost delta, decide per call. The A/B run
  itself costs ~$1.50 (it runs both models on real inputs incl. the 4.7MB PDF). The swap is trivial +
  low-risk once decided (models are centralized in `config.py`; structured outputs already work on
  Sonnet — A2). **Recommended scoping:** A/B **alerts + 13D + memory** (where the money + safety are),
  and **keep reply on Opus** (most quality-visible, only $0.08/reply). **Ask the operator which calls to
  A/B before running** — options: all four / alerts+13D+memory / just alerts+memory (skip the pricey
  13D compare) / other.
- ✅ **Group C — 2-pass prompt-caching restructure — DONE 2026-07-01** (the cache-correct version of the
  dropped 2.1). Validated output-equivalent + cache-engaging; see §14.A and WORKLOG. *(A "conditional
  pass 2" skip-on-thin-days variant remains a separate, undone option, §3/§6-constrained.)*

---

## 12. Path from here (next steps)

Everything safely doable/verifiable offline is committed (Phases 0–2, de-hardcoding, A1, 3.4, 3.2).
The remaining work is gated on secrets. In order:

1. **Provision secrets on the dev machine** (§7.1.4–5). Decide identity first: the agreed plan is
   **keep jared's** (copy `credentials.json` / `token.json` / sessions / cookie; mail goes FROM jared,
   TO acohen via `DIGEST_TO`) — *or* re-provision Gmail/Substack/Octus/13D under acohen. Set env vars
   in `env.bat` (machine/system level for the eventual server).
2. **First credentialed end-to-end run** — the §11 ordered test plan. Validates the whole committed
   stack at once and clears the §11 backlog. **Ask permission before the Claude calls; run once, on a
   small input, to acohen** (never `DIGEST_RECIPIENTS`/jared during testing).
3. **Do-and-test the deferred items** (each permissioned, once): **3.3** `_clean_pdf_text` review vs
   real archived PDFs (once the broker-research PDFs forward in — the archive has only a 13D PDF today).
   (Cost work **done 2026-07-01**: the Group B A/B (kept all Opus), the 13D summary cache, memory→Sonnet,
   and **Group C 2-pass prompt caching**. A "conditional pass 2" skip-on-thin-days variant remains
   optional — §3/§6. **A2 (structured outputs, live-confirmed 2026-06-30) and 3.1 are already done.**)
4. **§7.2 deploy** to the dedicated always-on Windows server — the definition of "done": always-on +
   headless, runs whether or not anyone is logged in, machine-level env vars, headless
   Playwright/Chromium, log rotation + failure alerting, correct TZ, and backups of `archive/` +
   `memory.json` + the FAISS index.

---

## 13. Open source-coverage gaps (flagged 2026-06-30)

Flagged after the **first live credentialed digest run succeeded** ($1.52, sent to acohen from the bot;
all sources flowed, Octus-free). Each item below is a real gap in what the digest currently captures.

### Missing secrets (fixable)
- [x] **`FRED_API_KEY` provisioned + tested 2026-06-30** → the **Macro Dashboard** (12 series: HY/IG
  OAS, 2Y/10Y + derived 2s10s, breakevens, jobless claims, CPI, SOFR, dollar) and the **Fed Balance
  Sheet (H.4.1)** (6 series) are now active. ⚠️ See the `fed_balance_sheet` series-label bug under
  "Data bugs" below — audit before trusting that section.
- [ ] **`SUBSTACK_EMAIL` blank** → Substack runs on the saved cookie today, but **auto-renewal will fail
  when the cookie expires** (the magic link is delivered to the account that owns the subs — jared's —
  not the bot). Decide the Substack ownership/renewal path before the cookie dies, or Substack silently
  goes empty.

### Data bugs
- [x] **`fed_balance_sheet.py` mislabeled FRED series — FIXED 2026-06-30** (verified against the FRED
  API). Corrected `BALANCE_SHEET_SERIES`: "Treasury Holdings" `WTREGEN` → **`WSHOTSL`** (SOMA U.S.
  Treasuries, ~$4.49T); "Discount Window" `WDTGAL` → **`WLCFLPCL`** (primary credit, ~$7.9B) — both old
  IDs were actually the Treasury General Account (~$900B). Also fixed an **ON RRP units bug**:
  `RRPONTSYD` is published in *billions*, so the map now carries a per-series scale (×1000) to keep the
  table in millions (was showing $4M instead of ~$3.5B). Re-ran clean: Total $6.74T / USTs $4.49T /
  MBS $1.96T / Discount Window $7.9B / ON RRP $3.5B / Repos $4M. Also **retuned `check_fed_stress`** the
  same day: the old $5B level (calibrated against the mislabeled $900B TGA, so it always tripped) →
  **$25B absolute + $10B WoW-surge** thresholds (`DISCOUNT_WINDOW_ALERT_MM` / `DISCOUNT_WINDOW_SURGE_MM`),
  sized to genuine primary-credit stress (SVB-era spiked ~$150B); now silent at the ~$8B baseline.
  **Wired into the digest 2026-06-30** — `check_fed_stress(fed_bs)` now runs in `digest.main` and merges
  any signal into the red alert box (the stale LLM `alerts_config.json` "Fed stress signal" rule was
  removed, so the threshold lives only in code). Pinned by `tests/test_fed_stress.py`.

### Forwarding completeness (verify with jared)
The inbox layer = whatever jared forwards to `acorn.research.bot@gmail.com`. The first run's window had
6 broker HTML notes, **0 PDFs, no Bloomberg**. Confirm the full set is forwarding:
- [ ] **Research PDFs** — the digest sends PDF attachments straight to Opus (a marquee feature). Confirm
  PDF-bearing research is forwarded **and the attachments survive forwarding** (some forwards drop/inline them).
- [ ] **Bloomberg emails** (`bloomberg.net`) — the digest has a dedicated §7 Bloomberg section; none seen yet.
- [ ] **Non-Substack newsletters** (Grant's, Greenmantle, etc. — cited in the SYSTEM_PROMPT) — only appear if forwarded.

### Genuinely unreplaced sources (no current substitute)
- [ ] **Octus — HY new-issue Primary Deal Tracker** (removed 2026-06-29). **No free replacement** for the
  primary/new-issue leveraged-finance pipeline (entity / yield ≥ 8% / price talk / rating / bookrunners).
  TRACE is secondary-market; SEC S-1/424B lack the HY pricing color. Would need a different paid feed or a
  custom scraper. *(Octus Intelligence — the distressed/restructuring news — is ~partly covered by
  PACER + ratings + the credit Substacks.)*
- [ ] **FINRA TRACE bond data — effectively broken** (pre-existing, NOT caused by the Octus removal).
  `trace_data.py` returns 0 with "non-JSON response (may need API registration)"; the public
  Morningstar/FINRA endpoint isn't usable as written, so watchlist secondary bond-trade data is absent.
  Needs FINRA TRACE API registration or a different data source.

### Latent maintenance (works now, will need a human later)
- [ ] **13D session** + **Substack cookie** will expire and need a manual re-login (13D's is interactive).
- [ ] **polymathinvestor.com** Substack returns 403 (lapsed/blocked sub) — contributing nothing; degrades gracefully.

---

## 14. Flagged / deferred — code changes that are fine for now

A single place for everything that's been **flagged but intentionally not done**, so §9's phase
breakdown reflects only *completed* cleanup. *(Distinct from §6 "Do NOT fix" — those are load-bearing
and meant to stay untouched permanently. Items here are "fine for now, maybe later.")*

**Status (2026-06-30): the offline, behavior-neutral cleanup is COMPLETE** (§14.C all done), and both
open product decisions (§14.D) are now resolved. Everything that remains needs either **(A)** a
permissioned Claude run, or is **(B)** genuine *wait-and-see* (do only if a problem actually appears).

### A. Deferred do-and-test (need a permissioned Claude run or more data)
- ✅ **A2 — structured outputs — DONE + live-confirmed 2026-06-30.** All 5 JSON call sites
  (alerts/memory + the 3 rankers) use `output_config.format` for guaranteed-valid JSON — no more silent
  parse-failure drops. Confirmed live on Opus 4.8 / Sonnet 4.6 / Haiku 4.5 (~$0.04). Detail: §11
  "Cost/efficiency."
- **3.3 — PDF-extraction review (`_clean_pdf_text`; PyPDF2→pypdf)** — measure the aggressive
  single-char-rejoin regexes against real `archive/*/pdfs/` (how often they fire, cleaned-vs-raw diff,
  retrieval quality before/after), then decide whether to gate them behind a fragmentation heuristic
  and/or switch the PDF lib. **Gated on data:** the archive holds only one PDF today (a 13D report),
  not the broker-research corpus these rules target — revisit once research PDFs forward in. Also gates
  the `PyPDF2 3.0.1` pin (don't bump first). `_clean_pdf_text` is measure-before-touch per §6.
- ✅ **Group B — embedded Opus → Sonnet cost A/B — DONE 2026-07-01.** Ran all four (memory, alerts, 13D,
  reply) through both models (~$1.89). A/B quality verdict: **keep all four on Opus** — reply Sonnet
  render bug (```html fence + full HTML doc), 13D Sonnet over-length (~1,900 words), memory/alerts savings
  too small. **Cost follow-up (2026-07-01):** a separate refactor then added the 13D **summary cache** and
  moved **memory → Sonnet** for cost (near-identical output). Full results in §11 and WORKLOG (2026-07-01).
- ✅ **Group C (prompt-caching restructure) — DONE 2026-07-01** (the cache-correct version of dropped
  2.1). The 2-pass digest now shares a cached source/PDF prefix across both passes (unified `system`;
  per-pass instruction after the `cache_control` breakpoint). Validated output-equivalent + cache-engaging
  via a permissioned before/after (~$3.5); ~$0.10/run text-day, ~$0.54/run PDF-day (mostly latent until
  §13 PDF-forwarding flows). Detail in WORKLOG (2026-07-01). *(A "conditional pass 2" — skip pass 2 on
  thin days — remains a separate, undone option if ever justified.)*

### B. Conditional — do only if a real problem appears (no evidence yet)
- **3.5a — `_assemble_digest_html` placeholder approach** — sections are injected by string-matching
  the Opus HTML. Only revisit **if** archived digests show real section misplacement; the fix risks
  the tuned `SYSTEM_PROMPT` (§6).
- **3.5b — PACER company-sizing search (`pacer._search_company_size`)** — Google scraping is fragile
  but degrades gracefully. Options: a free-tier search API (e.g. Brave) or dropping the web step. Low
  priority, low volume.

### C. Low-value cleanup
✅ **Done 2026-06-30** — three "nice-to-have" dedups consolidated, behavior-neutral (`ruff` clean,
`pytest` 41 green, + live free-fetcher smoke):
- `fed_research._parse_date` / `_is_recent` → now import `feeds.is_recent` (only the date helpers were
  dupes; the divergent `fed_research._fetch_feed` stays, per HANDOFF 2.3).
- The two EDGAR `_make_request` (`sec_filings.py` + `fund_tracking.py`) → shared **`net_utils.edgar_get`**
  (sec_filings parses JSON; fund_tracking takes raw text + 20s timeout — both via the one fetcher).
- The duplicated unverified-SSL context (`treasury_auctions.py` + `cftc_cot.py`) →
  **`net_utils.unverified_ssl_context`**.
- The bare RSS/data-feed User-Agent `"DailyDigest/1.0"` (in 7 files; distinct from the SEC/PACER
  contact UA) → one **`config.FEED_USER_AGENT`**. `feeds.fetch_feed` defaults to it (news/ratings
  dropped their redundant local copy); `fed_research` / `cftc_cot` / `fdic_monitor` /
  `treasury_auctions` import it.

**Left as-is (intentional — NOT a wait-and-see; genuinely not duplication):**
- **`news._clean_html` vs the inline `re.sub(r'<[^>]+>', …)` strips** in `ratings.py` / `fed_research.py`
  — NOT consolidated: `news._clean_html` also unescapes HTML entities while the inline strips don't, so
  merging would change what's fed to Opus/embeddings (§3.2 left these divergent for exactly this reason).
  Extracting a one-line `re.sub` would also add indirection for no real gain.

### D. Decisions (both resolved 2026-06-30)
- ✅ **RESOLVED 2026-06-30 via option (b)** — the discount-window stress alert. The stale LLM
  `alerts_config.json` "Fed stress signal" rule (was "$5B / +$2B WoW", would mis-fire daily against the
  corrected ~$8B baseline) was **removed**, and the numeric `fed_balance_sheet.check_fed_stress`
  ($25B / $10B) is now **wired into `digest.main`** — deterministic, single-source-of-truth threshold in
  code, merged into the same red alert box, and unit-tested (`tests/test_fed_stress.py`). Qualitative
  Fed events remain covered by the separate LLM "Fed surprise" rule.
- ✅ **RESOLVED 2026-06-30 — `build_ratings_html` removed; §9 stays Opus-written.** The earlier item
  assumed §9 was missing; it isn't — **Opus writes the §9 Rating Actions section itself** from the RSS
  rating data (confirmed in the 2026-06-30 email; curated prose, not a table). The `build_ratings_html`
  raw-table renderer was **dead code** (zero references) and would have *duplicated* §9, so it was
  **deleted** (+ its now-unused `esc`/`safe_href` import; the vestigial `ratings_html` plumbing in
  `_assemble_digest_html` too). Recoverable from git. The **SYSTEM_PROMPT was fixed** to make §9 an
  explicit Opus-owned section (it previously said "do NOT generate §9," which Opus ignored — a latent
  trap). If you ever want the complete raw table over Opus's curation, you'd re-add a renderer *and*
  suppress Opus's §9.

### E. Dropped as specced — later revived cache-correct (Group C, DONE 2026-07-01)
- **2.1 — prompt caching across the two Opus passes.** Counterproductive *as specced*: caching is a
  strict prefix match over `tools → system → messages`; pass 1 and pass 2 used different `system`
  prompts (pass 2 also put the shared content after a review block), so they shared no cacheable
  prefix → 0 cache reads + a wasted ~1.25× cache-write on pass 1 = **net cost increase**. The naive
  version was **dropped (2026-06-19)**. ✅ **SUPERSEDED 2026-07-01:** the *cache-correct* restructure
  (Group C — unify `system`, put the shared source/PDF prefix first with a `cache_control` breakpoint,
  move per-pass instructions after it) **was built and validated** (output-equivalent + cache-engaging;
  pass 2 reads the cached prefix). See §14.A "Group C" and WORKLOG (2026-07-01).
