# Daily Digest — Project Handoff

> Continuity doc for this repo. Read §1 (state) and §2 (constraints) before making changes.
> The "Do NOT touch" section (§6) exists because several blunt-looking pieces of code are
> intentional and battle-tested — treat them as constraints, not bugs.
>
> **Companion docs:** `WORKLOG.md` = the full dated narrative of every change ever made and why
> (the archive — start here for the *why* behind anything below). `OPERATIONS.md` = the jared-facing
> runbook; `MAINTENANCE.md` = the developer keep-it-running guide. **Active spec:**
> `REDUCE_REPEATS_SPEC.md` (anti-repetition, 15 ideas; Bundle 1 BUILT 2026-07-22, Bundle 2+ pending
> a week of live `repetition_scores.json` data — see its decision checklist; retire it after that
> decision).
> *(Retired/deleted, once built and distilled, to keep the doc set lean — all preserved in
> git history: `ALERT_COMMANDS_SPEC.md` (retired 2026-07-22 same-day-as-built: email-managed
> alerts/watchlist Parts I+II incl. per-user alerts — everything shipped + live-spot-checked;
> how-it-works → §4 rows + OPERATIONS + MAINTENANCE §1, build narrative + design decisions →
> WORKLOG 2026-07-22 entries; remaining live validation = first real command reply on the server,
> debugged from code/WORKLOG if needed, not the spec);
> `DEPLOY_PROGRESS.md` (2026-07-21; live cutover-resume doc → folded into §1 + WORKLOG 07-20/21);
> `NEXT_STEPS_SPEC.md` (the forward roadmap + deploy/cutover checklist — every track done, the deploy
> executed; live watch items → §1/§11.B, deploy record → WORKLOG 07-20/21); and the completed-track
> specs `CLEANUP_SPEC.md` / `CLEANUP_REFACTOR_SPEC.md` / `TEAM_DIGEST_SPEC.md` → intent distilled in
> §1 "Retired specs" + §1a + §9.)* This file was condensed 2026-07-15 (F22 pass);
> the pre-condensation version with all superseded/DONE narrative is in git history.

---

## 1. Objective & current state

**What it is:** A solo-operator Python automation that runs daily on a schedule. It gathers ~17
financial/market data sources (Gmail inbox + forwarded research PDFs, paid Substack subs, SEC
EDGAR, FRED macro, Fed balance sheet, Yahoo Finance, earnings calendar, PACER, 13F filings, rating
actions, central-bank research, Treasury auctions, CFTC COT, FDIC, WSJ/FT RSS, 13D WILTW),
summarizes them with Claude in a **two-pass** flow (draft → review/enhance), emails an HTML "Daily
Research Digest" (that's the in-email H1; the *subject line* is "📬 Daily Inbox Digest" =
`config.DIGEST_SUBJECT_PREFIX`, which the reply bot's Gmail query anchors on — search sent mail by
the latter), archives all raw content to disk, and indexes it into a local FAISS vector store
that powers an **email-reply Q&A bot**. Since 2026-07-13 each run produces **two variants** — a
FULL digest (with Substack) and a Substack-free TEAM digest (see §1a).

**Current state — DEPLOYED & LIVE (server cutover completed 2026-07-20).** The dedicated Windows
server (`ShawnArmstrong`) is the SOLE instance, running unattended: four scheduled tasks Ready under
a **stored-password** principal (MorningDigest 08:00 / Watchdog 09:00 / Backup 09:45 / ReplyMonitor;
the MiddayAlert task was removed 2026-07-21), `DIGEST_UNATTENDED=1` machine-wide, production digests
delivered from the box, the reply daemon polling. Code is `ruff` clean, `pytest` **395 green**,
retrieval eval baseline **hit@1 0.897 / hit@3 1.0 / MRR 0.937, zero misses**
(`tools/eval_results/2026-07-15_post_index_filter.json`). Operator `acohen@acorninv.com`; **Jared's
instance is decommissioned.** **Digest generation runs on Claude Fable 5 since 2026-07-22**
(`config.FABLE_MODEL` → `digest.CLAUDE_MODEL`; alerts/13D/reply bot stay on Opus) — expect ~$2.5–3.5
per FULL 2-pass run at Fable's $10/$50 rates (accurately tiered in `cost.py`).

**Branch: work on `main`.** `ava-updates` existed only to keep refactor work off `main` while Jared
ran production from `main`; that's retired, the server tracks `main`, so **`main` is now the
working/authoritative branch** — commit and deploy from it. `ava-updates` is frozen/behind and can
be deleted at will.

**What remains → SERVER PULL + ReplyMonitor RESTART + the 2026-07-23 debut run + a week of
repetition data.** Soak day 2 GREEN (Wed 7/22 08:00: both variants, no changelog leak; watchdog
silent). TWO large dev sessions followed on 7/22 (ALL COMMITTED on `main` through `f90e4ed`,
`pytest` **440**, ruff clean; full detail in the three WORKLOG 2026-07-22 entries):

*Session 1 (morning):* **Fable 5 model switch** for digest generation (+ thinking-block
`_response_text` fix + real cost tier), **ticker glossary** (`ticker_names.py`), **format changes**
(bolded lead words — since narrowed: tickers bold ONLY as a bullet's lead word; M&M restatement
filter; TL;DR box REMOVED), **PACER embedded-`<a>` strip fix**, **REDUCE_REPEATS Bundle 1**
(+ `repetition.py` metric → `repetition_scores.json`).

*Session 2 (afternoon/evening — the alerts overhaul, ALERT_COMMANDS_SPEC Parts I+II):*
**email-managed alerts & watchlist** (reply to a digest in plain English; Sonnet parse +
confirmation replies; `alert_commands.py` owns `alerts_config.json` — now untracked — +
new `watchlist.json`, both seed-on-missing); **expiry lifecycle** ("expiring" advance warning on
the last active day + "expired" notice next day, below an `<hr>` in the alert box, no source tag);
**ops-alert split** (config guard + source degradation → a separate ⚙️ operator email; red box =
content only); **per-user thematic alerts** (every alert has ONE owner, owner-only
visibility/editing; the old 7 migrated to jared+acohen copies — the server file self-migrates on
first post-pull run; per-recipient sends with personalized alert boxes; neutral base is what's
saved/archived/indexed/memory-fed; batched eval keeps ≤2 Claude calls/run; orphaned owners →
one-time ops note); **(WSJ) tag red**; **reply-channel teaching footer** (in the alert box, or
standalone when no box). Live-validated cheaply: parse seam 5+3 calls ($0.05 total), real
fan-out eval, 4 formatting sample emails to acohen.

**Server DEPLOYED same evening (2026-07-22 night, two pulls):** pulled through the
spec-retirement commit, `alert_commands.py` smoke run seeded both state files fresh (the pull
deletes the formerly-tracked `alerts_config.json`; seed-on-missing recreated it pre-migrated —
14 owned alerts + 16 tickers verified), **ReplyMonitor restarted**, and the **live command
round-trip PASSED** (operator replied "what alerts are set up?" from her inbox → confirmation
email listing her 7 alerts + the shared watchlist). A same-night follow-up — the list_config
reply reformat (expiry-bucket grouping, watchlist bullets, priority tag hidden; 3 approved
samples) — was pushed, pulled, and the ReplyMonitor restarted again. **The server is fully
current with `main`; the email-command path is live-validated end to end.** (Durable rule: any
pull touching `reply_monitor.py`/`alert_commands.py` needs `schtasks /End` + `/Run` on
`\DailyDigest\ReplyMonitor` — the daemon holds old code until restarted.)

**What's next:** the Thu 2026-07-23 08:00 run is still the biggest-change debut since deploy
(first production Fable run + first per-recipient sends). Read its log closely: THREE individual
"Digest sent successfully" lines (jared FULL; apain + acohen TEAM), the "14 owned alert(s) …
-> 7 eval unit(s)" line, two `Repetition:` lines, ~2x cost lines (~$2.5–3.5); in the emails —
per-user alert boxes (apain's has no personal alerts), teaching footer everywhere, red (WSJ)
tags; the 09:45 backup log's state-file line now carries alerts_config/watchlist/
repetition_scores. Then: **~1 week of repetition scores → Bundle 2 decision**
(`REDUCE_REPEATS_SPEC.md` checklist; watch STRONG only). Drop `acohen` from `DIGEST_TO_TEAM` at
the **2026-07-31** departure — the orphan-notice mechanism will flag her paused alerts in the ops
email once. Finish the soak while a fixer still exists.

**Key operational facts a fresh session needs (all detailed in WORKLOG 2026-07-20):**
- **Scheduled tasks run under a STORED PASSWORD, not S4U.** S4U registered fine but the AzureAD box
  silently refused to *launch* the tasks; `setup_tasks.ps1 -StoredPassword` (needs Shawn's Windows
  password) is the working path. Re-register that way, never the bare S4U default.
- **The server's Gmail token is the dev laptop's copied token pair (Plan B)** — the MFA lockout was
  never resolved, just routed around; refresh-token auth works through it. MFA is team-owned (backup
  codes in the vault; recovery phone = a teammate staying past 7/31).
- **O4 backup = state-only `robocopy` into `%OneDriveCommercial%\DailyDigest-Backup`** (weekday
  09:45), which OneDrive syncs off-box; works because the server is kept logged-in-and-locked.
- **Live watches (detail in §11.B):** memory active-count climbing (73→82→87 across 7/17/20/21;
  budget trims — `M of N` with M<N is expected); first 30-day aging batch ~7/30 is the decision
  point on archival (operator still present); resolved-story re-creation + Substack-via-email
  boundary both passed live but stay on watch.

**Closed tracks (detail is in `WORKLOG.md` under the dated entry):**

| Track | Outcome | WORKLOG date |
|---|---|---|
| Refactor Phases 0–3 + Opus 4.6→4.8 + model/UA centralization + A1 cost accounting + A2 structured outputs + §7.1 de-hardcoding | All done & committed | 2026-06-19 → 06-30 |
| Credentialed bring-up + first live end-to-end run ($1.52 → acohen) | Green; identity flipped to the bot | 2026-06-30 |
| Cost refactor (13D summary cache, memory→Sonnet, 2-pass prompt caching; Group B Opus↔Sonnet A/B) | Done; A/B verdict = keep all four on Opus | 2026-07-01 |
| Memory / retrieval refactor (Stages 0–5) | v2 story-timeline memory + reply router; **rerank + hybrid parked permanently** (lost the eval); 3b skipped | 2026-07-01 → 07-09 |
| Accrual week (6/6 green) + F1a deploy-blocking code fixes | Consent guard, `setup_tasks.ps1`, PACER seen-state durability, O2 watchdog | 2026-07-06 → 07-09 |
| Efficiency batch (S1 registry, E1 parallel fetch, E2 reconstruct-reindex, O1 log rotation, O2 watchdog, O3 content monitor) | Built; **E3 Gmail-batch skipped** (not the bottleneck) | 2026-07-09 → 07-10 |
| 3.3 PDF-extraction review + PyPDF2→pypdf 6.14.2 + index rebuild | Aggressive clean rules were the damage; trimmed; eval identical | 2026-07-09/10 |
| Friday live validation run | GREEN, $1.58, checklist 9/9; first v2 memory delta + first weekly wrap | 2026-07-10 |
| OAuth production publish + durable production `token.json` | Done; **this token.json is the one the server gets** | 2026-07-10 |
| §13 coverage-gap closures (TRACE module removed, Octus/HY-new-issue accepted, forwarding-completeness audit) | Resolved (§13) | 2026-07-13 |
| Substack ownership audit (11→17 pubs) + dead-cookie fix + auto-renewal reworked to OTP-code flow | Live-validated | 2026-07-13/14 |
| `TEAM_DIGEST_SPEC` — dual FULL/TEAM variants | Built + activated (pilot: acohen) | 2026-07-13 |
| Forwarding-visibility fix (read + attribute forwarded senders) + F3 golden-set refresh (26→29 Q) | Shipped, live-validated | 2026-07-14 |
| Second-pass cleanup (`CLEANUP_SPEC`, 5 stages; tests 307→336; chunk_id dupes→0; TEAM leak guard code-enforced; @acorninv.com-only receiving) | Done, $0 spend | 2026-07-14/15 |

**Retired specs — intent & deliverables folded in here (files deleted 2026-07-21; full text in git
history).** All three were completed-and-committed spec docs kept "for reference"; their content is
captured above (closed-tracks table + §9 + §1a) and distilled here so nothing depends on the files:
- **`CLEANUP_REFACTOR_SPEC.md`** — the 2026-07-10 full-codebase review, 9 stages (Phases 0–3:
  dead-code removal e.g. the write-only FRED/market caches, correctness/HTML-escaping, quality/cost,
  tests/consolidation). Behavior-neutral; `pytest` 180→227; pypdf eval metric-identical; $0 Claude.
  Excluded HANDOFF §6 do-NOT-fix items and `_assemble_digest_html`'s string-match (pinned, not
  changed). Superseded detail lives in §9 + WORKLOG 2026-06-19→07-10.
- **`TEAM_DIGEST_SPEC.md`** — the dual FULL/TEAM variant work (Substack = jared-personal; team gets a
  Substack-free digest that is the indexed one; per-variant alert-window carve; cross-variant prompt
  cache; TEAM_ACTIVATION_DATE guard). Built + activated 2026-07-13. **Full living description is
  §1a** — that section is authoritative, not this bullet.
- **`CLEANUP_SPEC.md`** — the 2026-07-14 second-pass review, 5 stages (chunk_id dedup 208→0, memory
  budget guard, index-side self-artifact filter, Substack-via-email boundary, `check.bat` QoL) +
  the deploy/cutover checklist (was `NEXT_STEPS_SPEC §5`, also retired — deploy record in WORKLOG
  07-20/21) + the OPERATIONS runbook. `pytest`
  307→336; eval improved to 0.897/1.0/0.937 zero misses; $0 Claude. Declined items (F7/F8/F9/F10/F11,
  type-hints, CI) are recorded in §11.C. Detail in WORKLOG 2026-07-14/15.

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
post-activation run without it is code-treated as misconfigured (warn + a separate ⚙️ operational
alert email to the operator channel + digest chunks un-indexed + memory frozen; escape hatch = set
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
- **Test between every phase.** Route all test output **locally or to `acohen@acorninv.com`** —
  never to the config recipients (jared's addresses) during testing.
- **External tooling falls into three cost tiers — know which before testing:**
  - **Pay-per-query (the only real per-call cost): the Anthropic/Claude API.** Token-billed across
    the 2-pass **Fable** digest (~$2.5–3.5/run since 2026-07-22) plus the **Fable** Friday weekly
    wrap (shares `digest.CLAUDE_MODEL`), Haiku (news ranking), Sonnet (PACER size-filter, reply
    query-extract, memory), and Opus (13D summary, alerts, reply answers).
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
| `alerts.py`, `archive.py`, `cost.py`, `claude_utils.py`, `content_monitor.py`, `run_alert.py` | Plain-English alerts; raw-content archiver; per-run cost accounting; JSON/structured-output helpers; O3 source-count degradation monitor; failure-alert + O2 completion watchdog. |
| `alert_commands.py` | Email-managed alerts + SEC watchlist (ALERT_COMMANDS_SPEC, 2026-07-22; Part II same day): owns `alerts_config.json`/`watchlist.json` (seed-on-missing, atomic writes, expiry, the Part-II owner migration), the Sonnet command classify/parse (owner-grounded), deterministic apply + confirmation HTML, expiry lifecycle (`consume_expired`/`expiring_today`, owner-attributed), and `orphan_notices`. **Thematic alerts are per-user** (owner-only visibility/editing; jared + acohen own the migrated originals; new users start empty); the watchlist is shared. Reply-channel = contamination-safe (`is_self_artifact()` exclusion). |
| `ticker_names.py` | Ticker→issuer-name glossary for the prompt (2026-07-22): SEC registry titles + a learned cache of digest-rendered "$TICK (Name)" pairs validated against that day's sources. Staged collect() / single post-variants commit() so the TEAM/FULL cache prefix can't fork mid-run. |
| `repetition.py` | Cross-section repetition metric (REDUCE_REPEATS Idea 12, 2026-07-22): deterministic scorer over assembled digest HTML, logged per run + persisted to `repetition_scores.json`. The yardstick for all anti-repetition prompt work. |
| Source fetchers (free APIs) | `news.py`, `ratings.py`, `market_data.py`, `macro_data.py`, `sec_filings.py`, `treasury_auctions.py`, `cftc_cot.py`, `fed_balance_sheet.py`, `fdic_monitor.py`, `earnings.py`, `fund_tracking.py`, `thirteen_d.py`, `fed_research.py`, `pacer.py`. |
| `net_utils.py`, `feeds.py`, `html_utils.py` | Shared EDGAR fetch + unverified-SSL context; RSS feed/date/recency helpers; HTML strippers + Gmail body extractor + `parse_forwarded_from`. |
| `run_*.bat`, `setup_tasks.ps1`, `check.bat` | Task Scheduler wiring: 4 `%~dp0`-relative wrappers (dated logs + 30-day prune, clean `exit /b 0`) + the PowerShell provisioning script (run-whether-logged-on, wake/catch-up/network, the 09:00 watchdog, `DIGEST_UNATTENDED`). `check.bat` = ruff + pytest. |

**Removed modules (history in WORKLOG):** `octus.py` (2026-06-29), `trace_data.py` (2026-07-13),
`grab_session.py` (Phase 0). Don't reintroduce references.

**Gitignored, account-bound secrets** (must exist on the machine; copy or regenerate):
`credentials.json`, `token.json` (Gmail — the durable *production* token minted 2026-07-10),
`substack_cookie.txt`, `thirteen_d_session.json`, `env.bat`, plus caches/state (`*_cache.json`
incl. `ticker_names_cache.json`, `pacer_seen.json`, `memory.json`, `substack_memory.json`,
`source_counts.json`, `repetition_scores.json`, and — email-managed, self-seeding from
`alert_commands.py` defaults if absent — `alerts_config.json` + `watchlist.json`).
*(`credentials_JARED.json` is a dev-machine backup only — do NOT copy it to the server.)*

**Env vars:** `ANTHROPIC_API_KEY` (required), `FRED_API_KEY` (macro + fed balance sheet),
`SUBSTACK_EMAIL` (Substack OTP-code renewal), `DIGEST_TO` (full-digest recipient override — leave
UNSET in production so it defaults to jtramontano@acorninv.com), `DIGEST_TO_TEAM` (the Substack-free
TEAM digest's recipients — **must be set on the server**; empty = team generation skipped).

---

## 5. Risks

- **Silent degradation:** the `try/except`-everywhere design means a broken source yields an empty
  section, not a crash. Mitigated by the O3 content monitor (per-source zero-streak → the separate
  ⚙️ operational-alerts email since 2026-07-22; the digest's red box carries content alerts only)
  but still: read logs.
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
- **Index growth (F13, measured 2026-07-15):** the FAISS index grows ~600–1,500 chunks/weekday since
  the forwarding body extracts landed; the §6 "~100k revisit" ceiling arrives in ~3–8 months of
  Mon–Fri operation, not years. Degradation is gradual (slower search/reindex/startup), never wrong
  answers. **Tripwire: revisit at ~30–50k vectors or when reply-bot latency is felt.** Escalation
  ladder (cheapest first): ✅ vectorized subset scan (done) → date-windowed retrieval default →
  prune-and-archive old days → IVF. Also noted in OPERATIONS.md for the post-handoff owner.

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
  AND MRR, no new misses). Detail in §14.

---

## 7. Machine migration

### 7.1 Dev machine (`KimCohen`) — ✅ DONE

Location + identity de-hardcoding complete: `.bat`/`setup_tasks.ps1` use `%~dp0` + project `.venv`
+ `PYTHONUTF8=1`; recipients are `DIGEST_TO`/`DIGEST_TO_TEAM`-env-driven; the SEC/PACER User-Agent
contact and the recipient/allow-list point at the bot `acorn.research.bot@gmail.com`; all secret
files are installed and working. The email identity flipped to the bot 2026-06-30 (jared's
rule-based forwards flow into the bot inbox; `token.json` = the bot sends + reads inbox; Substack
renewal reads the forwarded OTP code from the bot inbox). The Substack *account* stays jared's — an
optional end-state flip to the bot is his call (§13). Full history in WORKLOG.

### 7.2 Dedicated Windows server (the end goal — the remaining work)

**The server is DEPLOYED and LIVE** (cutover 2026-07-20; see §1). The executed deploy/cutover
step-by-step was `NEXT_STEPS_SPEC §5` (retired 2026-07-21 — in git history; the deploy narrative is
in WORKLOG 07-20/21). For a rebuild, README (setup + scheduling) + MAINTENANCE §2 (secrets) +
OPERATIONS "Backups & restore" are the path. Requirements the deploy implemented:

1. **Always-on + headless:** stays powered, awake (no sleep/hibernate), survives reboots. The reply
   monitor is a continuous process — an always-on server is what makes it reliable.
2. **Run whether or not anyone is logged in:** `setup_tasks.ps1` registers all four tasks via
   `Register-ScheduledTask` with S4U run-whether-logged-on + the wake/catch-up/network settings that
   `schtasks` can't set. Run it **as administrator** on the server.
3. **Secrets/identity on the server:** install the §4 secret files + `env.bat` at the
   **machine/system** level so non-interactive tasks see them. **Copy the durable production
   `token.json`** (minted 2026-07-10; a Testing-mode token dies after 7 days and a headless server
   can't re-consent). `env.bat` must carry `DIGEST_TO_TEAM` + `SUBSTACK_EMAIL`; copy the fresh
   `substack_cookie.txt` + `substack_memory.json`.
4. **Reliability & observability — all code halves DONE:** dated log rotation + 30-day prune (O1);
   failure alerting (`run_alert.py`, nonzero exit → red alert email with log tail); source-empty
   content monitor (O3 → the separate ⚙️ ops-alert email, arms after ~6 runs); hung-run watchdog
   (`run_alert.py digest --check-completed`, its 09:00 task registered by `setup_tasks.ps1`).
   Sessions still need occasional human care: Substack auto-renews (OTP-code via Gmail); **13D will
   eventually need a manual re-login** — documented in OPERATIONS.md.
5. **Time zone & schedule:** set the server TZ correctly (digest ~8 AM ET, weekly
   summary keys off Friday).
6. **Resources & backups:** the embedding stack + growing `archive/` need ~2 GB disk; O4 backups
   (`archive/`, `memory.json`, `substack_memory.json`, the two index files, state JSONs, `digests/`)
   land directly on the box at deploy — no laptop interim (single-copy risk accepted until then).

**Field findings from the 2026-07-06→09 accrual week (the "why" behind the §5 checklist; all code
fixes DONE):** unattended-consent hang → `DIGEST_UNATTENDED=1` fails fast (SystemExit 3);
OAuth Testing-mode 7-day token death → published to production + durable token; `schtasks` can't set
`WakeToRun`/`StartWhenAvailable`/`RunOnlyIfNetworkAvailable` → `setup_tasks.ps1`; network-down
wake/logon race → `RunOnlyIfNetworkAvailable` + O2 watchdog; PACER seen-state lost on failed runs →
stash-in-memory + `commit_seen()` only after a successful send; Abnormal AI quarantined the 7/2
digest as malicious → **IT allowlisted `acorn.research.bot@gmail.com` org-wide for Outlook** (covers
acohen + jtramontano; re-verify only if a non-Outlook recipient is added). WILTW posts after 8 AM
Thursdays → picked up by the next scheduled run (no fix needed).

**Cutover rule (from §5):** exactly ONE reply daemon and ONE digest instance may run anywhere —
disable jared's machine's tasks AND his reply monitor the same day the server goes live (two pollers
race on the shared bot inbox; two digests double-send).

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
  `acohen@acorninv.com` (or render HTML to a local file) during tests. For reply/memory testing,
  drive `answer_question()` / `update_memory()` directly on archived inputs (avoids racing the
  production reply monitor on the shared bot inbox; needs no live Gmail injection).
- **⚠ Dev `env.bat` FOOTGUN (found 2026-07-22):** its comment says `DIGEST_TO` is a "test-recipient
  override," but its VALUES are the production recipients (jtramontano + apain + acohen). Any manual
  dev run MUST explicitly override: `DIGEST_TO=acohen@acorninv.com` and `DIGEST_TO_TEAM=` (empty —
  which also triggers the §1a misconfig guard: FULL-only, memory frozen, digest chunks un-indexed —
  the correct state for a dev test run; a separate ⚙️ ops-alert email carrying "Team config
  missing" is expected — since 2026-07-22 it no longer appears in the digest itself). Loading `env.bat` from PowerShell: parse the `set` lines (see WORKLOG 2026-07-22) —
  bare `call env.bat` fails under `NoDefaultCurrentDirectoryInExePath`.

---

## 9. Change-spec history (Phases 0–3) — ✅ ALL DONE

The original phased refactor (Phase 0 cleanup → Phase 1 correctness/escaping → Phase 2 quality/cost
→ Phase 3 tests/consolidation) plus A1 cost accounting, A2 structured outputs, the Opus 4.8 upgrade,
and the §7.1 de-hardcoding are all committed and validated. Per-item detail and the commit hashes
are in `WORKLOG.md` (2026-06-19 → 06-30 entries). Nothing here is open.

---

## 10. Open coverage gaps (§13 residuals)

The 2026-06-30 → 07-14 source-coverage audit is closed. What remains:

- **13D session** will expire and need a **manual re-login** (interactive; unattended runs skip
  gracefully via the R8 guard and O3 flags the WILTW zero-streak). Procedure in OPERATIONS.md.
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
  - **(ii) Completely missing — no free source at all (BBG is the only way to get them):**
    - **S&P BDC index (SPBDCUP)** — publisher page bot-blocked (403); BIZD proxy declined.
    - **BCRED '32 / ARCC '32 G-spreads**, **SpaceX '56 G-spread**, **Oracle '66 G-spread**,
      **QTS G-spread** — no free issuer-level spread source.
    - **CoreWeave '32 + Core Scientific '31 bond prices** — bond-level data = TRACE ($9k/yr,
      rejected 2026-07-13; FINRA's free per-CUSIP web lookup judged too fragile to scrape).

  *(SpaceX **equity** came off the list 2026-07-16 — it IPO'd June 12, 2026 (Nasdaq: SPCX) and is
  now a normal Yahoo row in the AI Snapshot.)*
- **`_assemble_digest_html` string-match insertion** — revisit only **if** archived digests show
  real section misplacement; the fix risks the tuned `SYSTEM_PROMPT` (§6). *(The numbering-collision
  member of this family was already fixed 2026-07-14 — appended sections are unnumbered.)*
- **PACER company-sizing search (`pacer._search_company_size`)** — Google scraping is fragile but
  degrades gracefully. Options if it ever breaks: a free-tier search API (e.g. Brave) or drop the
  web step. Low priority, low volume.
- **Index growth** — see §5 (F13 ladder + tripwire).

### B. Watch → trigger → fix (implement only if the output says otherwise)
- **Snapshot-table T-1 lag — LOOK INTO (flagged 2026-07-23, prompted by a "treasury yields are
  wrong" comment).** At the 08:00 run, effectively EVERY Snapshot-table row is prior-trading-session
  (T-1) data, not live: FRED rows (Rates + Corporate Credit OAS) publish a day in arrears; Yahoo
  rows (Market/Private Credit/AI + the IGLB/IGIB credit-ETF rows) are daily closes and the US
  session hasn't opened at 8 AM; iShares portfolio OAS (HYG/LQD) is fund-reported T-1. The values
  are correct and each table already prints a subtle 10px-gray "as of <date>" footnote
  ([macro_data.py:361](macro_data.py:361), [market_data.py:343](market_data.py:343)) — so it's
  stale-but-labeled, not a data bug (verified: 7/22 run rendered rates "as of 2026-07-21", ~a few
  bps off BBG because CMT par yields ≠ BBG on-the-run). Open questions to resolve before any fix:
  (a) make the as-of/prior-close framing PROMINENT section-wide (both builders already compute the
  date — styling/labeling change, no data change); (b) confirm which if any 24/7 rows (BTC, and
  likely WTI/DXY) carry a same-day value at 8 AM — `market_data` stores `as_of` DATE-only
  ([market_data.py:124](market_data.py:124)), so add per-row timestamp logging and read a real 08:00
  production run to settle it (a run at any other hour can't reproduce 8 AM — the market's open
  state differs). Everything here is free to test (no Claude). Not started.
- **Repetition score (REDUCE_REPEATS Bundles 1+2 + second batch, shipped 2026-07-22/23).** Every
  run logs `Repetition: N strong + M weak signal(s)` and appends to `repetition_scores.json`
  (server-side). Shipped 2026-07-23 after readers noticed repetition in the first Fable production
  run: ideas 4+7+14, then a second batch (idea 3 variant (a), idea 6 soft caps, pointer-echo
  tightening) — two ~$3.35 validated test runs to acohen. **Metric recalibrated same day (v2):**
  the content-mandated sections (SEC Filings, Rating Actions) are excluded like the data tables —
  structural ticker collisions were inflating STRONG past the old ≥3 threshold on digests with
  ZERO story-level repetition. Entries carry `"metric": 2` since then; v1 entries (server history
  ≤7/23 morning) read ~1–3 strong HIGH — not 1:1 comparable. **v2 decision rule:** observed noise
  floor on repetition-clean digests is 1–3 strong (incidental in-story ticker mentions + numeric
  coincidences the regex can't distinguish); escalate only on SUSTAINED ≥4 or continued reader
  complaints → A/B the idea-8 de-prescribe (one week each arm), then Bundle 3 (idea 11 tripwire,
  idea 10 dedup pass — needs spend sign-off). Weak (bare-%) collisions stay ignorable. NOTE:
  pytest used to append junk zero-score entries to the real `repetition_scores.json` (any test
  driving `digest.main()`); fixed 2026-07-23 in `tests/conftest.py` — if the server ever ran
  `check.bat` before pulling that fix, prune the zero entries before reading the series.
- **Ticker-name learned cache (`ticker_names_cache.json`, 2026-07-22).** Self-seeds from each run
  ("Ticker-name cache: learned N" log line; 12 entries after day one). Watch: a wrong issuer name
  appearing in a digest → inspect/delete the bad cache entry (the proper-noun + source-text guards
  should prevent this; one descriptive-phrase class was already caught and guarded in tests).
- **First production Fable run (2026-07-23) cost re-baseline.** Expect roughly 2x Opus per-run cost
  in the daily cost summary; after a week, update OPERATIONS' monthly burn estimate from observed
  numbers (it was pre-updated to a ~$90–140/mo guess).
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
- **Memory-store growth** — contexts are budget-bounded in code (60 stories / 45k chars; byte-
  identical until the store outgrows it). Ride-along watch on the next natural runs: resolved-story
  re-creation (the Sonnet index lists resolved stories as bare id slugs) + the "Memory context: N
  chars / M of K active" log line. Revert lever named in `memory._story_index_for_prompt`. The
  ~90-day archive-to-side-file idea stays available if the *store* itself ever needs shrinking.
- **Parked retrieval mechanisms (rerank / hybrid)** — see §6. Re-test kit: `tools/eval_retrieval.py`
  + `tools/eval_golden.json` (29 questions; grow the golden set as archive days accrue —
  cadence in `MAINTENANCE.md §5`).

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
