# Daily Digest — Deployment

**TLDR:** how to set up the automated digest on a Windows machine.

Any code changes should first reference `HANDOFF.md`. For running/rerunning the digest,
managing alerts, and monitoring/failure handling, see `OPERATOR_GUIDE.md`.

> **The box must stay logged-in-and-locked as the run user** (OneDrive sync and the per-user
> browser caches depend on it).

---

## What you're deploying

Everything runs through one dedicated Google account, **`acorn.research.bot@gmail.com`** ("the
bot"): research sources are forwarded into its inbox, digests send from it, and reply questions
are read from it. Three entry points, all Python, all scheduled via `run_*.bat` wrappers using
Task Scheduler:

- `digest.py` — the morning job (fetches sources, prompts Claude, generates a
  **full** and a **team** digest, emails both, archives raw content, indexes it into FAISS
  (a local vector-search index), updates memory, and sends the weekly summaries on Fridays).
- `reply_monitor.py` — long-running daemon (answers emailed replies to digests by retrieving
  from that index + archive; also the write path for the email-managed alerts/watchlist).
- `run_alert.py` — invoked by the wrappers on nonzero exit (failure alert) and by the 9 AM
  watchdog.

## Prerequisites (install / confirm first)

- Windows 10/11, staying always-on (no sleep/hibernate; wake allowed for tasks)
- **Python 3.12** (`py -3.12 --version`)
- **Git**
- Correct **time zone** (digest ~8 AM ET)
- ~2 GB disk for the embedding stack + growing `archive/`

## 1 — Cloning the repo

```powershell
git clone https://github.com/dirac-delta-one/Daily-Digest.git
Set-Location Daily-Digest
```

## 2 — venv + dependencies

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 3 — Moving gitignored files onto the machine

### 3a — Secrets & credentials

All gitignored; account-bound (not machine-bound). Copy from a working install or regenerate.

| File / var | What it is | Binds to | Expiry / rotation |
|---|---|---|---|
| `credentials.json` | Google OAuth **client** | the Cloud project | Long-lived. Rotate only if leaked (regenerate the OAuth client, re-download, re-consent). |
| `token.json` | Gmail **access/refresh** token | the bot Gmail account | Durable **only in Production** publishing status. Rotate when Google revokes it (see 3b). |
| `substack_cookie.txt` | Substack session (`substack.sid`) | jared's Substack account | Expires in **weeks**. Auto-renews via OTP; manual paste is the fallback (OPERATOR_GUIDE How-To). |
| `thirteen_d_session.json` | Playwright storage state | jared's **paid** 13D account | Expires in **weeks–months**. Manual re-login only — **requires Jared's 13D credentials; no free/alternative account.** |
| `ANTHROPIC_API_KEY` (env) | Claude API key | the bot's Anthropic account | No expiry. Rotate if leaked. Billing is **firm-paid, auto-reload ON** (confirmed 2026-08-03) — no manual top-ups; the failure mode is the reload card expiring. |
| `FRED_API_KEY` (env) | FRED data key | free FRED account (registered on the bot Gmail, per the departing operator 2026-08-03) | Stable, free. No rotation. |
| `SUBSTACK_EMAIL` (env) | inbox the Substack OTP code arrives at | — | Config value, not a secret. |

**⚠** To set up a new environment, copy credentials from the server (the only machine holding
them since 2026-08-03) or regenerate. Gmail 2FA backup codes were emailed to jared on the
thread where `acorn.research.bot@gmail.com` was created.

### 3b — The Gmail token

The single highest-risk credential. Two rules:

1. **The OAuth app MUST be in "Production" publishing status.**
2. **Regenerating the token needs a browser** (copy `token.json` to the server)

**Symptom of a dead token:** `invalid_grant` in the log, or a "run FAILED" alert mentioning
auth. **Fix:** on a browser machine, delete `token.json`, run `python digest.py` (or a Gmail
metadata call) to trigger consent as `acorn.research.bot@gmail.com`, verify `getProfile`
returns the bot, copy the new `token.json` to the server. Never re-consent in Testing mode.

**Creating the OAuth client from scratch** (only if no working `credentials.json` exists
anywhere): in the [Google Cloud Console](https://console.cloud.google.com/), create/select a
project, enable the **Gmail API**, then **APIs & Services → Credentials → Create Credentials →
OAuth client ID → Desktop app** — download the JSON as `credentials.json` in the project root,
and set the consent screen to Production status before minting the token. Note: Google no
longer allows re-downloading an existing client's secret — a new machine that can't copy the
file gets a *new* Desktop client and mints its own token. **Deleting an OAuth client revokes
every token issued under it** — don't delete an old client while any instance still uses it.

### 3c — The bot Google account has MFA

The bot account (`acorn.research.bot@gmail.com`) has 2-Step Verification enabled. The MFA email is sarmstrong@acorninv.com and the phone number is Jared's cell.

### 3d — `env.bat` (the `run_*.bat` wrappers `call` it)

Set at the **machine/system** level so non-interactive tasks see them. Required:
`ANTHROPIC_API_KEY`, `DIGEST_TO_TEAM`. Recommended: `FRED_API_KEY`, `SUBSTACK_EMAIL`. Leave
`DIGEST_TO` **unset** in production (it defaults to the owner). `DIGEST_UNATTENDED=1` is set
machine-wide by `setup_tasks.ps1`; `PYTHONUTF8=1` by the wrappers (logs contain Unicode and
crash under cp1252 — set it yourself when running scripts by hand).

```bat
set ANTHROPIC_API_KEY=sk-ant-...
set FRED_API_KEY=...                  REM Macro Dashboard + Fed balance sheet
set SUBSTACK_EMAIL=owner@gmail.com    REM Substack renews via a one-time code emailed here
set DIGEST_TO_TEAM=teammate@acorninv.com   REM REQUIRED in production — without it the run
REM freezes indexing+memory as a privacy guard (OPERATOR_GUIDE: "Team config missing")
REM TEST machines ONLY — route all digest/alert/reply email to yourself
REM (leave UNSET in production; defaults to the production owner):
set DIGEST_TO=you@acorninv.com
```

### 3e — Seed state (only when rebuilding an existing install)

All caches/state self-seed when missing — a fresh machine needs **no** state copy. When
**restoring** a failed server, copy the OneDrive backup's contents back in (`archive\`, `digests\`,
the memory files, caches, the search index) — the restore procedure is
`OPERATOR_GUIDE.md` → "Backups & restore".

## 4 — Sanity check

```powershell
check.bat                                     # ruff + the full offline suite (502 tests, $0)
.\.venv\Scripts\python.exe news.py            # any free fetcher runs standalone, $0
```

## 5 — Manual test run (the full end-to-end chain)

**⚠ A full run costs ~$7 of Claude and SENDS REAL EMAIL — set `DIGEST_TO` to your own address
and `DIGEST_TO_TEAM=` (empty) first** (the HANDOFF §8 testing protocol; empty team is the
correct test state — a "Team config missing" footer notice on the FULL email is expected).

```powershell
.\.venv\Scripts\python.exe digest.py
```

The first-ever run opens a browser for Google OAuth (authorize as the bot account) and
authenticates Substack via the emailed one-time code. Confirm: the digest email arrived and
renders; `digests\<date>.html` was saved; the log ends with a cost summary.

## 6 — Register the scheduled tasks

Register from an **elevated** PowerShell in the repo folder, logged in as the run user:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_tasks.ps1 -StoredPassword   # -DryRun to preview
```

**⚠ `-StoredPassword` is REQUIRED on an AzureAD-joined box** — the bare S4U default registers
all four tasks without error and then silently never launches them (`Start-ScheduledTask`
returns no error; `LastRunTime` stays at the 11/30/1999 sentinel — HANDOFF's Post-mortem
library, 07-20 entry). It prompts once for the run user's Windows password and registers, under
folder `\DailyDigest\`:

| Task | When | What |
|---|---|---|
| MorningDigest | Mon–Fri 08:00 | Build + email the FULL and TEAM digests |
| Watchdog | Mon–Fri 09:00 | Alert if the morning digest never completed |
| Backup | Mon–Fri 09:45 | Copy state off-box to OneDrive |
| ReplyMonitor | at startup, always on | Answer emailed reply questions |

All run whether or not a user is logged on, with wake/catch-up/network-required settings, and
the script sets `DIGEST_UNATTENDED=1` machine-wide so a dead Gmail token fails fast instead of
hanging. Verify with `Get-ScheduledTask -TaskPath "\DailyDigest\"`.

**Cutover rule:** exactly ONE reply daemon and ONE digest instance may run anywhere — disable
the old machine's tasks AND its reply monitor the same day a new box goes live (two pollers
race on the shared bot inbox; two digests double-send). Note a `git pull` never deregisters a
task — removing one is a manual `Unregister-ScheduledTask`.

## 7 — Limitations

The box must stay powered, awake, and **logged-in-and-locked** as the run user. Sessions still need occasional human care: Substack auto-renews via OTP; **13D eventually needs a manual re-login** (`OPERATOR_GUIDE.md` How-To).

## 8 — Updating the code (git pull)

```powershell
git pull
```

Reinstall dependencies only when `requirements.txt` changed
(`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`). **If the pull touched
`reply_monitor.py`/`alert_commands.py` (or recipients changed in `env.bat`), restart the
daemon:** `schtasks /End /TN \DailyDigest\ReplyMonitor; schtasks /Run /TN \DailyDigest\ReplyMonitor`
— it holds old code until restarted. Digest-path-only pulls need no restart (each morning run
is a fresh process).
