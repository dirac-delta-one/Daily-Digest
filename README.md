# Daily Research Digest

An automated daily research briefing for a credit/distressed investment desk. Once a day it gathers
~17 financial/market sources, summarizes them with Claude in a two-pass flow, and emails a
structured HTML digest. It also archives everything it reads into a local search index that powers
an **email-reply Q&A bot**, and sends an intraday materiality alert when something important breaks.

Runs unattended on a Windows machine via Task Scheduler. Single-operator tool; Python 3.12.

---

## What it produces

Each run (weekday mornings) sends two variants of the digest:

- **Full digest** → the primary recipient: includes paid Substack content and a personal
  cross-story memory layer.
- **Team digest** → colleagues: identical *minus* Substack (kept private to the owner). This is the
  variant indexed for the Q&A bot, so a teammate's question can never surface the owner's private
  Substack content.

Alongside the morning digest:

- **Midday alert** (`midday.py`) — checks for material developments since the morning and emails
  *only* if something warrants it (silent most days).
- **Reply Q&A bot** (`reply_monitor.py`) — reply to any digest email with a question and it answers
  in-thread within ~5 minutes, using RAG over everything archived. Answers are tiered: the owner
  sees Substack-derived context, teammates get the Substack-free view.
- **Friday weekly wrap** — a synthesized summary of the week's digests.

## Sources

Gmail inbox + forwarded research PDFs, paid Substack subscriptions, SEC EDGAR filings, FRED macro
data, the Fed balance sheet (H.4.1), Yahoo Finance market data, an earnings calendar, PACER
bankruptcy court RSS, 13F fund position changes, rating-agency actions (Moody's/S&P/Fitch),
central-bank & research feeds, Treasury auctions, CFTC Commitments of Traders, FDIC bank failures,
WSJ/FT RSS, and the 13D "What I Learned This Week" report.

Only the **Anthropic (Claude) API** costs money per run. Substack and 13D are flat paid
subscriptions. Everything else is free public data (SEC, Yahoo, FRED, Treasury, CFTC, FDIC, RSS)
plus local compute (FAISS + sentence-transformer embeddings).

---

## Setup (one-time)

### 1. Install dependencies

```bash
cd Daily-Digest
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
playwright install chromium                      # for the 13D scraper
```

### 2. Google Cloud (Gmail) credentials

1. In the [Google Cloud Console](https://console.cloud.google.com/), create/select a project and
   enable the **Gmail API**.
2. **APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app**. Download
   the JSON and save it as `credentials.json` in the project root.
3. **APIs & Services → OAuth consent screen:** for unattended/server use, the app must be in
   **"Production" publishing status** — Testing-mode refresh tokens expire after 7 days and will
   break a headless server weekly. Publish the app, then mint the token (step 4). The resulting
   `token.json` is durable; copy that exact file to the server rather than re-consenting there.

### 3. Environment variables — `env.bat`

Create `env.bat` in the project root (gitignored). The `run_*.bat` wrappers `call` it:

```bat
set ANTHROPIC_API_KEY=sk-ant-...
set FRED_API_KEY=...                  REM Macro Dashboard + Fed balance sheet
set SUBSTACK_EMAIL=owner@gmail.com    REM Substack renews via a one-time code emailed here
REM Team-digest recipients (the Substack-free variant). REQUIRED in production:
REM a missing value pauses digest indexing + memory as a privacy guard and raises an in-digest alert.
set DIGEST_TO_TEAM=teammate@acorninv.com
REM On a TEST machine, route ALL digest/alert/reply email to yourself instead of the
REM production recipients (leave UNSET in production — defaults to the production owner):
set DIGEST_TO=you@example.com
```

`PYTHONUTF8=1` is set automatically by the `run_*.bat` wrappers (logs contain Unicode and crash
under the default Windows cp1252 console). Set it yourself when running a script by hand:
`set PYTHONUTF8=1`.

### 4. First run

```bash
.venv\Scripts\python digest.py
```

The first run opens a browser for Google OAuth (authorize as the sending account), authenticates
Substack via an emailed one-time code, and sends a digest. Confirm it arrives and renders, then
proceed to scheduling.

---

## Scheduling (Windows Task Scheduler)

The repo ships four wrappers — `run_digest.bat`, `run_midday.bat`, `run_reply_monitor.bat`,
`run_watchdog.bat` — each of which `cd`s to its own folder (`%~dp0`), sets `PYTHONUTF8=1`, calls
`env.bat`, runs the project `.venv` Python, and writes a date-stamped log under `logs\` with a
30-day prune. No hardcoded paths.

Register all four tasks with `setup_tasks.ps1`, from an **elevated** PowerShell in the repo folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_tasks.ps1   # add -DryRun to preview
```

It registers, under Task Scheduler folder `\DailyDigest\`:

| Task | When | What |
|---|---|---|
| MorningDigest | Mon–Fri 08:00 | Build + email the full and team digests |
| Watchdog | Mon–Fri 09:00 | Alert if the morning digest never completed |
| MiddayAlert | Mon–Fri 13:00 | Alert only if something material broke |
| ReplyMonitor | at startup, always on | Answer emailed reply questions |

All run whether or not a user is logged on, with wake/catch-up/network-required settings, and the
script sets `DIGEST_UNATTENDED=1` machine-wide so a dead Gmail token fails fast instead of hanging.
Verify with `Get-ScheduledTask -TaskPath "\DailyDigest\"`.

---

## Configuration

Top of `digest.py`: `HOURS_LOOKBACK` (24), `MAX_EMAILS` (50), `MAX_PDF_SIZE_MB` (5), the email-body
prompt budgets, `MAX_FETCH_WORKERS` (6). Recipients are env-driven (`DIGEST_TO` / `DIGEST_TO_TEAM`).
Model IDs and pricing are centralized in `config.py`. Top of `substack.py`: `MAX_ARTICLES_PER_PUB`,
`MAX_ARTICLE_CHARS`, and the `SUBSCRIPTIONS` list.

## Cost

Roughly **$45–55/month** in steady state (two digest variants + Friday wraps + answered reply
questions); individual daily runs land around **$1.50–$2.00** depending on PDF/article volume. Every
entry point prints a per-call cost summary at the end of its run. Monitor at
[console.anthropic.com](https://console.anthropic.com).

---

## Secret & state files (gitignored)

Account-bound — must exist on the machine; copy from a working install or regenerate:

- `credentials.json` — Google OAuth client
- `token.json` — Gmail auth token (the durable **production** token; see setup step 2)
- `substack_cookie.txt` — Substack session (auto-renews; manual paste is the fallback)
- `thirteen_d_session.json` — 13D login session (manual re-login when it expires)
- `env.bat` — environment variables (above)
- State/caches: `memory.json`, `substack_memory.json`, `*_cache.json`, `pacer_seen.json`,
  `source_counts.json`, and the `archive/` tree (raw content + the FAISS index).

---

## Documentation

| Doc | Audience | Contents |
|---|---|---|
| `README.md` | anyone | this file — what it is, setup, scheduling |
| `HANDOFF.md` | developer | current state, constraints, "do NOT touch," risks, remaining work |
| `NEXT_STEPS_SPEC.md` | developer | forward roadmap + the **server deploy & cutover checklist** (§5) |
| `MAINTENANCE.md` | developer | keeping it running: secrets, rotation, failure cases & fixes |
| `OPERATIONS.md` | operator (non-technical) | what each email means + the three manual fixes |
| `WORKLOG.md` | developer | the full dated history of every change and why |
| `ava_refactor.md` | owner | summary of what the refactor delivered, with metrics |

**Project status:** DEPLOYED & LIVE — running unattended on the dedicated Windows server since
2026-07-20 (see `DEPLOY_PROGRESS.md`). Work happens on the `main` branch. Remaining work is
post-deploy hardening/handoff only.
