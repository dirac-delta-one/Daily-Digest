# Daily Digest

An automated daily research briefing, which gathers **~17 financial/market sources** every weekday morning. Sources are sent/forwarded to acorn.research.bot@gmail.com, including research PDFs, paid Substack articles, SEC EDGAR, FRED, PACER bankruptcy courts, rating actions, market data, and more. Claude then summarizes the data in a **two-pass flow** and emails two digest variants — **FULL** (includes Jared's paid Substack) and **TEAM** (without). Everything it reads is archived and indexed into a local FAISS store that powers an **email-reply Q&A bot** (reply to any digest
with a question — or manage alerts and the SEC watchlist in plain English). Fridays also send an end of week summary email. The project runs unattended on a dedicated Windows server via Task Scheduler (under Shawn Armstrong's user); the Claude API (~$160–180/month) is the only per-run cost.

## Documentation

| Doc | What it's for |
|---|---|
| `HANDOFF.md` | Engineering continuity — current state, constraints, do-NOT-touch list, risks, condensed session history + post-mortems. **Start here for any code change.** |
| `DEPLOYMENT.md` | Setting up the automated digest on a machine (secrets, env, scheduled tasks). |
| `OPERATOR_GUIDE.md` | Running things by hand, managing alerts/watchlist by email, and every known failure case with its fix. |
| `JPM_SPEC.md` | The one parked workstream (JPM dealer research) — awaiting the owner's re-scope-or-drop decision. |

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