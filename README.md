# Daily Research Digest

An automated daily research briefing for a credit/distressed investment desk. Every weekday
morning it gathers **~17 financial/market sources** (inbox + forwarded research PDFs, paid
Substack, SEC EDGAR, FRED, PACER bankruptcy courts, rating actions, market data, and more),
summarizes them with Claude in a **two-pass flow**, and emails two digest variants — **FULL**
(with the owner's paid Substack) and **TEAM** (without). Everything it reads is archived and
indexed into a local FAISS store that powers an **email-reply Q&A bot** (reply to any digest
with a question — or manage alerts and the SEC watchlist in plain English). Fridays add a
weekly wrap. Runs unattended on a dedicated Windows server via Task Scheduler; the Claude API
(~$160–180/month) is the only per-run cost.

**Status:** LIVE & fully unattended since 2026-07-20; handoff closed 2026-08-07 with the first
unattended week validated green. Work happens on `main`. The server holds the only live
credentials.

## Documentation

| Doc | What it's for |
|---|---|
| `HANDOFF.md` | Engineering continuity — current state, constraints, do-NOT-touch list, risks, condensed session history + post-mortems. **Start here for any code change.** |
| `DEPLOYMENT.md` | Setting up the automated digest on a machine (secrets, env, scheduled tasks) + monitoring and every known failure case with its fix. |
| `OPERATOR_GUIDE.md` | Running things by hand + managing alerts/watchlist by email (non-technical). |
| `JPM_SPEC.md` | The one parked workstream (JPM dealer research) — awaiting the owner's re-scope-or-drop decision. |

## Quick start

Run via the project venv (`.venv\Scripts\python.exe`); deps install with
`pip install -r requirements.txt`. Full machine setup (OAuth, `env.bat`, scheduled tasks):
`DEPLOYMENT.md`.

```bash
check.bat
```

runs ruff + the full offline test suite (502 tests, no network, no cost). The standalone
fetchers are also free to run (`python news.py`, `market_data.py`, `sec_filings.py`, …).

**⚠ A full `python digest.py` run costs real money (~$7 of Claude) and SENDS REAL EMAIL to the
production recipients unless `DIGEST_TO` is overridden to your own address** — read HANDOFF §8
(testing protocol + the `env.bat` footgun) before running anything that calls Claude. The reply
bot has a safe single-poll mode: `python reply_monitor.py --once`.

## Repo layout

- **Flat root, deliberately** (a solo-operator tool; the module map is HANDOFF §4).
  `digest.py` orchestrates: fetch all sources → build prompt → 2-pass Claude → assemble HTML →
  send → archive → index → memory → (Fri) weekly wrap. `config.py` centralizes models/pricing/
  identities; `search.py` = FAISS index + retrieval; `memory.py` = cross-digest story memory;
  `reply_monitor.py` = the Q&A/alert-command daemon; `run_*.bat` + `setup_tasks.ps1` = the
  scheduled-task wiring.
- `archive/` · `digests/` · `logs/` + all secrets/state (`token.json`, `env.bat`, caches) are
  **gitignored** — data and credentials never enter git. Caches self-seed; secrets must be
  installed (DEPLOYMENT §3a).

## Tests & lint

```bash
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m pytest -q
```

Both are wrapped by `check.bat`. The suite is offline by design — Claude-calling paths are
permission-gated and never exercised by tests (HANDOFF §2/§8).
