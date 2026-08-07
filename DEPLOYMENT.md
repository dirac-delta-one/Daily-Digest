# Daily Digest — Deployment

**TLDR:** how to set up the automated digest on a Windows machine.

Any code changes should first reference `HANDOFF.md`. For running/rerunning the digest,
managing alerts, and monitoring/failure handling, see `OPERATOR_GUIDE.md`.

> **The box must stay logged-in-and-locked as the run user** (OneDrive sync and the per-user browser caches depend on it).

---

## What You're Deploying

Everything runs through one dedicated Google account, **`acorn.research.bot@gmail.com`**: research sources are forwarded into its inbox, digests send from it, and reply questions
are read from it. Three entry points, all Python, all scheduled via `run_*.bat` wrappers using
Task Scheduler:

- `digest.py` — the morning job (fetches sources, prompts Claude, generates a
  **full** and a **team** digest, emails both, archives raw content, indexes it into FAISS, updates memory, and sends the weekly summaries on Fridays).
- `reply_monitor.py` — long-running daemon (answers emailed replies to digests by retrieving
  from that index + archive; also the write path for the email-managed alerts/watchlist).
- `run_alert.py` — invoked by the wrappers on nonzero exit (failure alert) and by the 9am watchdog.

## Prerequisites

- Windows 10/11
- **Python 3.12** (`py -3.12 --version`)
- **Git**
- Correct **time zone** (EST)
- ~2 GB disk for the embedding stack + growing `archive/`

## 1 — Cloning the Repository

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

## 3 — Moving gitignored Files onto the Machine

### 3a — Secrets & Credentials

All gitignored; account-bound (not machine-bound). Copy from a working install or regenerate.

| File / var | What it is | Binds to | Expiry / rotation |
|---|---|---|---|
| `credentials.json` | Google OAuth **client** | the Cloud project | Rotate only if leaked |
| `token.json` | Gmail **access/refresh** token | the bot Gmail account | Durable only in Production publishing status. Rotate when Google revokes it (see 3b). |
| `substack_cookie.txt` | Substack session (`substack.sid`) | Jared's Substack account | Expires in weeks but auto-renews via OTP; manual paste is the fallback (OPERATOR_GUIDE How-To). |
| `thirteen_d_session.json` | Playwright storage state | Jared's **paid** 13D account | Expires in weeks–months and requires manual re-login |
| `ANTHROPIC_API_KEY` (env) | Claude API key | the bot's Anthropic account | Rotate if leaked. Billing is firm-paid with auto-reload on |
| `FRED_API_KEY` (env) | FRED data key | free FRED account (registered with acorn.research.bot@gmail.com) | Stable, free. No rotation. |
| `SUBSTACK_EMAIL` (env) | inbox the Substack OTP code arrives at | — | Config value, not a secret. |

⚠ To set up a new environment, copy credentials from the server or regenerate.

### 3b — The Gmail Token

The single highest-risk credential. Two rules:

1. **The OAuth app MUST be in "Production" publishing status.**
2. **Regenerating the token needs a browser** (copy `token.json` to the server)

**Symptom of a dead token:** `invalid_grant` in the log, or a "run FAILED" alert mentioning auth.

**Fix:** on a browser machine, delete `token.json`, run
`.venv\Scripts\python.exe digest.py` to trigger consent as `acorn.research.bot@gmail.com`
(Ctrl-C once `token.json` appears — letting it continue is a full paid run that sends email)

**Creating the OAuth client from scratch** (only if no working `credentials.json` exists
anywhere): in the [Google Cloud Console](https://console.cloud.google.com/), create/select a
project, enable the **Gmail API**, then **APIs & Services → Credentials → Create Credentials →
OAuth client ID → Desktop app** — download the JSON as `credentials.json` in the project root,
and set the consent screen to Production status before minting the token.

Note: Google no longer allows re-downloading an existing client's secret — and deleting an OAuth client revokes every token issued under it, so never delete the old client while any instance still uses it.

### 3c — acorn.research.bot@gmail.com MFA

The bot account (`acorn.research.bot@gmail.com`) has 2-Step Verification enabled. The MFA email is sarmstrong@acorninv.com and the phone number is Jared's cell.

Gmail 2FA backup codes were emailed to Jared on the
thread where `acorn.research.bot@gmail.com` was created.

### 3d — `env.bat` (the `run_*.bat` wrappers `call` it)

Set at the **machine/system** level so non-interactive tasks see them. Required: `ANTHROPIC_API_KEY`, `DIGEST_TO_TEAM`.

Recommended: `FRED_API_KEY`, `SUBSTACK_EMAIL`. Leave
`DIGEST_TO` **unset** in production (it defaults to the owner). 

`DIGEST_UNATTENDED=1` is set machine-wide by `setup_tasks.ps1`; `PYTHONUTF8=1` by the wrappers (logs contain Unicode and
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

### 3e — Seed State (only when rebuilding an existing install)

All caches/state self-seed when missing — a fresh machine needs **no** state copy. When
**restoring** a failed server, copy the OneDrive backup's contents back in (`archive\`, `digests\`,
the memory files, caches, the search index) — the full restore procedure is §8 below.

## 4 — Sanity Check

```powershell
# ruff + the full offline suite (502 tests, $0)
check.bat                             

# any free fetcher runs standalone, $0
.\.venv\Scripts\python.exe news.py            
```

## 5 — Manual Test Run (the full end-to-end chain)

⚠ A full run costs ~$7 of Claude and sends real email. For a test run, set `DIGEST_TO` to your own address and leave `DIGEST_TO_TEAM` empty (a "Team config missing" notice on the email is then expected).

```powershell
.\.venv\Scripts\python.exe digest.py
```

The first-ever run opens a browser for Google OAuth (authorize as the bot account) and
authenticates Substack via the emailed one-time code. Confirm: the digest email arrived and
renders; `digests\<date>.html` was saved; the log ends with a cost summary.

## 6 — Scheduled Tasks

Register from an **elevated** administrator PowerShell in the repo folder, logged in as the run user:

```powershell
 # -DryRun to preview
powershell -ExecutionPolicy Bypass -File .\setup_tasks.ps1 -StoredPassword 
```

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
the old machine's tasks AND its reply monitor the same day a new box goes live. Note a `git pull` never deregisters a
task.

## 7 — Limitations

The box must stay powered, awake, and **logged-in** as the run user. Sessions still need occasional human care: Substack auto-renews via OTP; **13D eventually needs a manual re-login** (`OPERATOR_GUIDE.md` How-To).

## 8 — Restoring from Backup (if the current server dies)

The system's data is copied to OneDrive every weekday into
`…\OneDrive - Acorn Investment\DailyDigest-Backup\` (what's in it and how it syncs:
`OPERATOR_GUIDE.md` → "Backups & Restore"). To resurrect on a new machine:

1. Do steps 1–6 above (clone, venv, secrets, tasks).
2. The secrets were **not** backed up, on purpose — re-supply them per 3a/3b (copy from the old server if its disk survives, else regenerate).
3. Copy the contents of `DailyDigest-Backup\` (from OneDrive) into the project folder.

The archive, memory files, and search index all come back, and the system continues from the
last backup. Remember the cutover rule (step 6) if the old machine is still partly alive.
