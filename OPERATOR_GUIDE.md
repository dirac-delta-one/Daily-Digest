# Daily Digest — Operator Guide

**TLDR:** what the automated digest emails mean, the few manual actions you may ever need, and
every known failure case with its fix. The scheduled runs normally do everything — you only
need this page when an alert email arrives, a run was missed, or you want to change what the
digest watches. Written for the person who receives the alerts (jtramontano@acorninv.com as of
8/7/2026). For code changes see `HANDOFF.md`; for setting up a machine see `DEPLOYMENT.md`.

| Task | When | What it does |
|---|---|---|
| MorningDigest | Mon–Fri 08:00 | Builds + emails the Daily Research Digest |
| Watchdog | Mon–Fri 09:00 | Emails an alert if the morning digest never completed |
| Backup | Mon–Fri 09:45 | Copies the day's data off-box to OneDrive (see "Backups & Restore") |
| ReplyMonitor | at startup, always on | Answers questions you email as replies to a digest |

To check they're registered/running (PowerShell): `Get-ScheduledTask -TaskPath "\DailyDigest\"`

Everything flows through one dedicated Google account, **`acorn.research.bot@gmail.com`**: research sources are forwarded into its inbox, digests send from it, and your
replies are read by it.

**Alerts & the SEC watchlist are managed by replying to any digest in plain English** ("watch for CLO downgrade news until July 28th", "add CRWV to the watchlist", "what alerts are set up?") — the bot confirms within ~5 minutes. Alerts are personal to each recipient; the watchlist is shared.

**Onboarding someone new** = add their @acorninv.com address to `DIGEST_TO_TEAM` in the server's `env.bat` — they start with no alerts and set up their own by replying to their first digest.

---

## How To: rerun a missed or failed digest

Double-click `run_digest.bat` in the project folder on the server (or run it from PowerShell).
It runs the exact same chain as the 08:00 task and emails everyone as normal. (Don't know
where the project folder is? Task Scheduler → `\DailyDigest\MorningDigest` → its Action shows
the full path.)

Two things worth knowing:
- **After a FAILED run this is the intended recovery** — a failed run saved nothing, so the
  rerun still covers everything since the last successful digest.
- **You can also just wait**: the next morning's run automatically widens its window to cover
  the gap (a Monday digest covers the whole weekend the same way). Skipping a rerun loses
  nothing except that day's delivery.

## How To: re-login to 13D (when the WILTW session expires)

13D Research's weekly "What I Learned This Week" (WILTW) report is one of the digest's paid
sources, scraped from client.13d.com under a saved login session. 

When that session expires:
on the server, open a terminal in the project folder and run
`.venv\Scripts\python.exe thirteen_d.py --login` — a browser opens; log in to client.13d.com,
then press ENTER in the terminal. Until this is done, WILTW is simply skipped (the digest
still sends).

*Note:* WILTW publishes on Thursdays and takes occasional multi-week breaks. A
`Report not found` line in the log on a non-publishing week is normal. Only a `Session expired — re-login required` line means the
login actually died. 

Note: After a multi-week break the degradation notice can't arm until WILTW logs one
nonzero week again (a long break looks "normally zero" to the monitor), so confirm the first
post-break report arrived yourself.

**Who can do this:** the login uses 13D's PAID subscription account (Jared's). Only someone with those credentials can refresh the session.

## How To: paste a fresh Substack cookie (only if auto-renewal fails)

It renews itself via a login code Substack emails to Jared's gmail, auto-forwarded to the bot. This manual fallback
is only for when a degradation notice names `substack`, or `[preview only…]` markers appear
where full article text used to be: log in to substack.com in a browser as Jared's Substack
account, copy the `substack.sid` cookie value (browser dev tools → Application → Cookies),
and paste it as the only contents of `substack_cookie.txt` in the project folder.

---

## Question: what does each email mean?

- **🚨 Daily Digest run FAILED — …** — the morning run crashed; the email body shows the last
  ~40 log lines. Usually transient (network); if it repeats two days running, get a developer
  to read `logs\digest_<date>.log`. If the body mentions **credit/quota**, the firm-paid
  auto-reload card failed — fix the payment method at console.anthropic.com (the bot
  account's login).
- **🚨 Daily Digest MISSING — no completed run — …** — the 9 AM watchdog: the run hung or never
  started (machine off/asleep, network down at wake, or a login/consent prompt is blocking —
  DEPLOYMENT §3b). Check the machine is on.
- **Grey "⚙️ System notices" footer at the BOTTOM of your [FULL] digest** — system-health
  notices, visible only on the FULL digest, never the team's. The ones to know:
  - **"Source degradation: <source>: 0 items for 3 straight runs…"** — a data source silently
    died. `substack` → the cookie How-To. `wiltw` → the 13D How-To. `pacer_rss_<court>` → that
    court's RSS feed died court-side; nothing to fix locally, and worth ~a week of watching
    before calling it permanent. Anything else →
    developer (likely a feed/endpoint change).
  - **"Output truncated"** — a generation pass hit its token cap; the digest may be missing
    trailing sections. One-off is fine; recurring → developer.
  - **"Team config missing"** — the server lost the `DIGEST_TO_TEAM` setting in `env.bat`; the
    team digest isn't going out and memory/search updates are paused as a privacy guard.
    Restore the line in `env.bat` (sample in `DEPLOYMENT.md`); the next run self-heals.

- **"backup FAILED"** — the 09:45 off-box copy couldn't find its OneDrive folder; see
  "Backups & Restore" below.
- **No digest AND no failure email** — check the machine; if it ran fine (log ends clean), the
  email may be **quarantined by mail security**: Abnormal AI flagged a digest once; IT
  allowlisted `acorn.research.bot@gmail.com` org-wide for Outlook. A newly-added **non-Outlook**
  recipient needs their own allowlisting — and note the failure alerts share the same sender,
  so quarantine can silence both signals at once.
- **The reply bot answered the same question twice** — two daemon instances are running
  somewhere (they race on the shared inbox). Exactly ONE may exist anywhere; find and kill the
  extra (e.g. an old machine that was never decommissioned).

## Question: is it safe to rerun the digest multiple times?

Yes — nothing breaks, recipients just get another email. Details worth knowing: a rerun after
a **failure** produces the normal full digest (the failed attempt saved nothing). A second run
after a **successful** send produces a much thinner digest — each run only covers the time
since the last saved digest — so there's rarely a reason to do it. Court-filing entries from a
crashed run can reappear in the rerun; that's deliberate (the system prefers repeating an entry
over silently losing one).

## Question: who gets each email?

- **[FULL]** goes to the owner address (`DIGEST_TO`, default jtramontano) — it
  includes Substack content and the grey system-notices footer
  when there's something to report.
- **[TEAM]** goes to everyone in `DIGEST_TO_TEAM` (in the server's `env.bat`) — same
  digest minus Substack, each copy with that person's own alert box.
- **🚨 failure/watchdog alerts** go to the operator.
- Weekly wraps follow the same FULL/team split every Friday.

## Question: where do things live?

- Sent digests: `digests\<date>.html` (and `…_team.html`)
- Everything the system read that day: `archive\<date>\`
- Logs: `logs\` (30-day rotation).
- **Bot-account security emails live in a "Gmail Alerts" folder**, not the inbox: Google's
  account emails about MFA/2-Step Verification are auto-filtered out of the inbox.
- **Reply answers feel slow or repetitive?** Developer item, not urgent — `HANDOFF.md §5`
  (index growth, benchmarked: nothing expected before ~late 2027) / `§11.B` (dedup).

---

## Backups & Restore

**What's backed up, and where.** Every weekday at ~09:45 (just after the morning digest) a
scheduled task (`Backup`) copies the system's DATA to OneDrive — into
`…\OneDrive - Acorn Investment\DailyDigest-Backup\`. It copies the things that can't be
recreated: `archive\` (every day's gathered source material), `digests\` (the sent digests),
the memory files (the evolving storylines), the caches, the search index, and the run `logs\`.
It deliberately does **not** copy any passwords, keys, or logins — those never leave the server.

**How it gets off the server.** The task just copies the files into the OneDrive folder on the
machine; **OneDrive then uploads them to Acorn's cloud on its own**, the same way any file you
drop into OneDrive syncs. So the safety copy ends up in the cloud, not only on the server's
disk. (The task itself never touches the internet — it only copies files locally; OneDrive does
the uploading.)

**What it depends on.** OneDrive only uploads while the server is **logged in** (locked is fine
— that's how it's kept). If the server were ever fully signed out, the copies would still be
made on disk but wouldn't upload to the cloud until someone logs in again. If the OneDrive
folder can't be found at all, the backup sends a **"backup FAILED"** alert rather than fail
silently. It also never deletes anything from the backup, so a problem on the server can't wipe
the saved history.

**Is it working? (worth a glance every few weeks.)** The task can confirm only that it wrote
the files on the server — it can't confirm they reached the cloud. So occasionally open
OneDrive (the web site, or the cloud icon in the system tray) and check the
`DailyDigest-Backup` folder is there and recently updated. If OneDrive shows a sync error, sort
that out (a standard OneDrive issue) — the data is safe on the server in the meantime.

**How to restore (if the server's disk fails):** follow `DEPLOYMENT.md` §9 — the normal
machine setup plus copying this backup back in. (The secrets were **not** backed up, on
purpose; DEPLOYMENT covers re-supplying them.)
