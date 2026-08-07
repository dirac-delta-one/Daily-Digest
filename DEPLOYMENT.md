# Daily Research Digest — Deployment

**TLDR:** how to set up the automated digest on a Windows machine as well as every known failure case
and its corresponding fix. The scheduled tasks fetch ~17 sources, generate and email the digests via Claude,
and answer emailed replies.

Any code changes should first reference `HANDOFF.md`. For running/rerunning the digest and
managing alerts, see `OPERATOR_GUIDE.md`.

> **The box must stay logged-in-and-locked as the run user** (OneDrive sync and the per-user
> browser caches depend on it — lock with Win+L, never sign out).

---

## What you're deploying — the 60-second mental model

Three entry points, all Python, all scheduled via `run_*.bat` wrappers → Task Scheduler:

- `digest.py` — the morning job. Fetches ~17 sources, builds a 2-pass prompt (generation model =
  Claude Fable 5 since 2026-07-22, `config.FABLE_MODEL`; satellites stay on Opus), generates a
  **full** and a **team** digest, emails both, archives raw content, indexes it into FAISS,
  updates memory, and (Fridays) sends the weekly wraps.
- `reply_monitor.py` — long-running daemon; answers emailed replies to digests via RAG over the
  archive. Also the write path for the email-managed watch config: replies that are
  alert/watchlist commands ("watch for X until Aug 15") are parsed by Sonnet in
  `alert_commands.py`, applied to the state files, and confirmed in-thread. **Thematic alerts
  are per-user** (each alert has one owner; each recipient gets their own email with a
  personalized alert box; the archived/indexed copy carries a neutral box). The SEC watchlist
  is shared.
- `run_alert.py` — invoked by the wrappers on nonzero exit (failure alert) and by the 9 AM
  watchdog (`--check-completed`); deliberately self-contained (imports nothing that could have
  failed). Also drives the weekday `Backup` task's off-box copy alerting.

**Where state lives:** `archive/<date>/` (raw content per run) + `archive/index.faiss` +
`archive/chunk_metadata.json` (the search index); `memory.json` / `substack_memory.json`
(evolving storylines); `*_cache.json`, `pacer_seen.json`, `source_counts.json` (per-source
caches/state); `alerts_config.json` / `watchlist.json` (the email-managed alerts + SEC
watchlist — **seeded from `alert_commands.py` defaults when missing**, written atomically; if
one is corrupted the code runs on built-in defaults without overwriting it — restore from the
O4 backup); `digests/<date>.html` (sent digests); `logs/` (30-day rotation).

**Cost:** only the Claude API costs money per run (`HANDOFF.md §2` cost tiers). Everything else
is free public data or flat subscriptions. **Never loop a Claude-calling path to test it.**

## Prerequisites (install / confirm first)

- Windows 10/11, staying always-on (no sleep/hibernate; wake allowed for tasks)
- **Python 3.12** (`py -3.12 --version` → 3.12.x — 3.14 lacked torch/faiss wheels at bring-up)
- **Git**
- Correct **time zone** (digest ~8 AM ET; the weekly wrap keys off Friday)
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
.\.venv\Scripts\python.exe -m playwright install chromium   # for the 13D scraper
```

## 3 — Moving gitignored files onto the machine

### 3a — Secrets & credentials

All gitignored; account-bound (not machine-bound). Copy from a working install or regenerate.

| File / var | What it is | Binds to | Expiry / rotation |
|---|---|---|---|
| `credentials.json` | Google OAuth **client** | the Cloud project | Long-lived. Rotate only if leaked (regenerate the OAuth client, re-download, re-consent). |
| `token.json` | Gmail **access/refresh** token | the bot Gmail account | Durable **only in Production** publishing status. Rotate when Google revokes it (see 3b). |
| `substack_cookie.txt` | Substack session (`substack.sid`) | jared's Substack account | Expires in **weeks**. Auto-renews via OTP; manual paste is the fallback (Monitoring, below). |
| `thirteen_d_session.json` | Playwright storage state | jared's **paid** 13D account | Expires in **weeks–months**. Manual re-login only — **requires Jared's 13D credentials; no free/alternative account.** |
| `ANTHROPIC_API_KEY` (env) | Claude API key | the bot's Anthropic account | No expiry. Rotate if leaked. Billing is **firm-paid, auto-reload ON** (confirmed 2026-08-03) — no manual top-ups; the failure mode is the reload card expiring. |
| `FRED_API_KEY` (env) | FRED data key | free FRED account (registered on the bot Gmail, per the departing operator 2026-08-03) | Stable, free. No rotation. |
| `SUBSTACK_EMAIL` (env) | inbox the Substack OTP code arrives at | — | Config value, not a secret. |

**⚠ The SERVER holds the only live copy of every secret since 2026-08-03** — the dev machine's
copies (`credentials.json`, `token.json`, `substack_cookie.txt`, `thirteen_d_session.json`,
`jpm_session.json`, `env.bat`) were deliberately deleted at the operator's departure. To stand
up a new environment, copy from the server or regenerate per this section. Gmail 2FA backup
codes: in the vault, and also emailed to jared on the thread where
`acorn.research.bot@gmail.com` was created. *(`credentials_JARED.json`, an obsolete dev backup,
was already deleted 2026-07-27.)*

### 3b — The Gmail token: the one that bites you

The single highest-risk credential. Two rules:

1. **The OAuth app MUST be in "Production" publishing status.** In Testing mode, refresh tokens
   die after **7 days** → the digest breaks weekly, and a headless server can't do the
   interactive re-consent to recover. This was live-confirmed on the accrual week (day 7). The
   app is already published; keep it that way.
2. **Regenerating the token needs a browser** (interactive consent), so do it on a machine that
   has one, then copy `token.json` to the server. On the server, `DIGEST_UNATTENDED=1` makes a
   dead token **fail fast with an alert** instead of hanging on a consent prompt.

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

### 3c — The bot Google account has MFA: keep it TEAM-OWNED

The bot account (`acorn.research.bot@gmail.com`) has 2-Step Verification enabled (set up during
the 2026-07 server deploy). **The MFA method must be owned by the team, not one person** — a
shared TOTP secret in a password manager, passkeys/security keys held by 2+ admins, or a shared
phone number. If it's tied to a departing person's device, the team loses the ability to
re-authenticate the bot account (e.g. to mint a new `token.json`). Note: enabling/changing MFA
can trigger a ~48h Google lockout of *interactive* sign-in — existing OAuth refresh tokens keep
working through it (a running instance is unaffected), but you can't mint a fresh token until
it clears.

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
set DIGEST_TO_TEAM=teammate@acorninv.com   REM REQUIRED in production (load-bearing, below)
REM TEST machines ONLY — route all digest/alert/reply email to yourself
REM (leave UNSET in production; defaults to the production owner):
set DIGEST_TO=you@acorninv.com
```

**`DIGEST_TO_TEAM` is load-bearing:** since team activation, a run *without* it is treated as
misconfigured — the digest still sends, but indexing + memory are frozen (a privacy guard so
Substack prose can't leak to team askers) and an alert fires. If the team variant is ever
deliberately retired, set `config.TEAM_ACTIVATION_DATE = None` (otherwise the guard freezes
indexing forever).

### 3e — Seed state (only when rebuilding an existing install)

All caches/state self-seed when missing — a fresh machine needs **no** state copy. When
**restoring** a failed server, copy the O4 backup's contents back in (`archive\`, `digests\`,
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

The box must stay powered, awake, and **logged-in-and-locked** as the run user (OneDrive
uploads and the per-user Playwright/HuggingFace caches depend on the login; lock with Win+L,
never sign out). Sessions still need occasional human care: Substack auto-renews via OTP;
**13D eventually needs a manual re-login** (`OPERATOR_GUIDE.md` How-To).

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

---

## Monitoring & Failure Handling

Observability is built in: dated log rotation with a 30-day prune (O1), the 09:00 hung-run
watchdog (O2), the per-source zero-streak content monitor (O3 → the grey "System notices"
footer on FULL sends), and the 09:45 off-box backup with its own failure alert (O4). Every
failure below announces itself; **symptom → cause → fix**, ordered roughly by frequency:

**Run FAILED alert (red email, log tail attached).** The run crashed (nonzero exit). Usually a
transient network blip — check `logs\digest_<date>.log`. If it repeats two days running, debug
the traceback. The alert email itself contains the last 40 log lines.

**Run MISSING alert (9 AM watchdog).** The morning run hung or never started — machine
off/asleep, network was down at wake, or a login prompt is blocking. Confirm the machine is on
and awake, check for a blocking consent (3b), rerun `run_digest.bat` by hand.

**"Source degradation: <source>: 0 items for 3 straight runs" (System-notices footer).** A
normally-populated source silently died. `substack` → renew the cookie (below). `wiltw` → 13D
re-login (below). `pacer_rss_<court>` → that court's RSS feed died (court-side; a ~week of
watching before calling it permanent — the txsb lesson). Anything else → read that fetcher's
log block; likely a feed/endpoint change.

**Substack dead / degraded.** Symptom: `substack` degradation notice, or `[preview only…]`
markers where full text used to be. It auto-renews via the OTP code Substack emails (read from
the bot inbox — requires jared's `no-reply@substack.com` auto-forward to be live and
`SUBSTACK_EMAIL` set). **Manual fallback:** log into substack.com in a browser, copy the
`substack.sid` cookie value (dev tools → Application → Cookies), paste it as the *only*
contents of `substack_cookie.txt`. *Note:* the 9 custom-domain pubs get full text only via
Substack's unauthenticated per-post API (the auth cookie is `.substack.com`-scoped); if
Substack closes that, they degrade to previews — accepted, visible via the markers.

**13D / WILTW missing.** Two distinct causes — read the log to tell them apart:
- `Report not found` = the session is **authenticated** but no report exists at that date.
  WILTW publishes Thursdays and takes **periodic multi-week breaks** (e.g. the Q2 2026 break —
  the 7/02 report's own footnote announced the next as 7/16). Normal; the digest skips
  gracefully.
- `Session expired — re-login required` (a redirect to the login page) = the session actually
  died. No auto-renewal — interactive login only. **Fix:**
  `.venv\Scripts\python.exe thirteen_d.py --login`, log into client.13d.com in the browser that
  opens, press ENTER. **Credentials:** 13D is a **paid subscription and the account is
  Jared's** — only he (or a holder of those credentials) can perform the `--login`. There is no
  free tier and a new bot-email account would have **no WILTW access**, so this is not a fix a
  developer can do alone. If Jared is unavailable when the session dies, WILTW stays skipped
  (non-fatal, 1 of ~17 sources) until he re-logs in. Long-term ownership (keep it Jared's vs.
  transfer/re-purchase under the bot) is a billing decision for Acorn, not a code task.

Session note: 13D auth is a **server-side session** (`thirteen_d_session.json` holds a `user`
session-cookie with no client-visible expiry), so you can't tell staleness from the file — only
a live request shows it. To de-risk a known-upcoming report, run `--login` proactively.
**O3 caveat:** the content monitor will NOT alert on a WILTW outage if `wiltw` has been 0
across the whole recorded window (a long break makes it look "normally zero"), so after a break
ends, manually confirm WILTW returns (`source_counts.json` → `wiltw > 0`) rather than trusting
the degradation alert. Once it logs one nonzero day, O3 can catch future zero-streaks.

**"Team config missing" notice.** The environment lost `DIGEST_TO_TEAM` (3d). That run skipped
indexing + memory on purpose. Restore the line in `env.bat`; the next run self-heals.

**Digest not delivered / quarantined.** A mail-security product (Abnormal AI) flagged the
digest as malicious once (new sender + emoji subject + link-dense HTML). IT allowlisted
`acorn.research.bot@gmail.com` org-wide for Outlook. If a **non-Outlook** recipient is added
and doesn't receive digests, get their mail security to allowlist the bot — the failure alerts
share the sender, so quarantine can silence both signal paths at once.

**API credit exhausted.** "run FAILED" alerts mentioning credit/quota. Billing is firm-paid
with auto-reload ON (2026-08-03), so this should only happen if the reload payment itself fails
(e.g. card expired) — fix at console.anthropic.com (the bot account's billing). Expected burn
~$160–180/month (re-baselined 2026-07-30; the ~$45–55 figure predates Fable 5 + cross-day
context).

**Reply bot double-answering / racing.** Exactly ONE reply daemon may run anywhere — two poll
the same inbox and race (mark-as-read isn't atomic). This only happens if a second instance was
left running (e.g. an old machine wasn't decommissioned at cutover). Kill the extra.

**Reply answers feel repetitive / slow.** Repetitive → paraphrase-level dedup may be needed
(`HANDOFF.md §11.B`). Slow → the FAISS index has grown; see the index-growth ladder
(`HANDOFF.md §5` — benchmarked 2026-07-30, no action expected before ~late 2027).

**Memory anomalies.** If a "new" story is actually a resolved story restated (the
resolved-story re-creation watch, `HANDOFF.md §11.B`), the revert lever is named in
`memory._story_index_for_prompt`. If `memory.json` is ever corrupted, each `archive/<date>/`
directory snapshots that day's `memory.json` / `substack_memory.json` for recovery — copy the
last good one back.

**PACER duplicates.** After a crashed run, previously-seen court entries can re-appear next run
(by design — `commit_seen()` only fires after a successful send, choosing duplication over
silent loss). Harmless; no action.

### Routine maintenance calendar

| Cadence | Task |
|---|---|
| Continuous (automatic) | Failure/watchdog/degradation alerts; log rotation (30-day); the O4 off-box backup (glance at the OneDrive web folder every few weeks to confirm it's uploading). |
| Every few weeks (reactive) | Substack cookie — usually auto-renews; paste manually if the degradation notice fires. |
| Weeks–months (reactive) | 13D re-login when the WILTW session actually expires. |
| Occasionally | Glance at the Anthropic billing page — auto-reload is ON, so the only thing to catch is a failing reload card (a credit/quota run-FAILED alert is the active signal). |
| When you touch the project | Add a few golden-set questions for new archive days, incl. cross-day ones — the retrieval eval only stays meaningful if it compounds. |
| At ~200k index vectors (~late 2027), or when replies actually feel slow | Work the index-growth ladder (`HANDOFF.md §5`): (1) vectorized subset scan ✅ done → (2) date-windowed retrieval default (⚠ eval-gate it) → (3) prune old days → (4) IVF. *(Benchmarked 2026-07-30: flat search is milliseconds even at 10x the old tripwire — no action expected in 2026.)* |
