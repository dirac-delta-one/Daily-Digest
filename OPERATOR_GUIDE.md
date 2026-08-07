# Operator Guide — Daily Research Digest

**TLDR:** what the automated digest emails mean and the few manual actions you may ever need —
no code knowledge assumed. The scheduled runs normally do everything (digest Mon–Fri 08:00 ·
watchdog 09:00 · off-box backup 09:45 · the reply bot always on) — you only need this page when
an alert email arrives, a run was missed, or you want to change what the digest watches.
Written for the person who receives the alerts (jared). For code changes see `HANDOFF.md`; for
setting up a machine see `DEPLOYMENT.md`.

| Task | When | What it does |
|---|---|---|
| MorningDigest | Mon–Fri 08:00 | Builds + emails the Daily Research Digest (your FULL version and the team version; Fridays add the weekly wraps) |
| Watchdog | Mon–Fri 09:00 | Emails an alert if the morning digest never completed |
| Backup | Mon–Fri 09:45 | Copies the day's data off-box to OneDrive (see "Backups & restore") |
| ReplyMonitor | at startup, always on | Answers questions you email as replies to a digest |

To check they're registered/running (PowerShell): `Get-ScheduledTask -TaskPath "\DailyDigest\"`

---

## Everything you need to know about alerts & the SEC watchlist

The digest watches two configurable lists: **thematic alerts** (plain-English triggers checked
every morning — e.g. "Any new Chapter 11 filing with over $500M in liabilities" — hits show in
the red ⚠️ ALERTS box) and the **SEC watchlist** (tickers whose SEC filings and earnings dates
are monitored).

**Alerts are personal; the watchlist is shared.** Each person's alerts are their own: only you
see them (your digest's alert box is yours alone), only you can add/remove/list them, and
nobody else's alerts appear in your digest. The SEC watchlist is one shared list the whole team
can edit. **Onboarding someone new** = add their @acorninv.com address to `DIGEST_TO_TEAM` in
the server's `env.bat` — they start with no alerts and set up their own by replying to their
first digest.

**To change either, just reply to any digest email** in plain English from your work address.
The bot understands things like:

- "For the next two weeks, watch for anything on Argentina sovereign debt"
- "Until July 28th, look out for CLO downgrade news"
- "Add CRWV to the watchlist" / "stop watching MSTR"
- "Watch WOLF through earnings, say until Aug 10"
- "Extend the Argentina alert to end of August"
- "Remove the insider selling alert"
- "What alerts are set up right now?"

You'll get a confirmation reply within ~5 minutes stating exactly what changed; the change
takes effect on the next morning's digest. Anyone who receives a digest can do this. Items
with a time limit expire on their own: on the last active day the digest shows a **"Watch item
expiring"** advance warning (renew by reply before coverage lapses), and the first digest after
the end date shows a one-line **"Watch item expired"** notice — reply to renew if you still
want it. If the bot isn't sure what you meant, it replies asking you to rephrase instead of
guessing (and a reply that's just a question is answered normally — asking questions is the
same channel).

---

## How To: rerun a missed or failed digest

Double-click `run_digest.bat` in the project folder on the server (or run it from PowerShell).
It runs the exact same chain as the 08:00 task and emails everyone as normal.

Two things worth knowing:
- **After a FAILED run this is the intended recovery** — a failed run saved nothing, so the
  rerun still covers everything since the last successful digest.
- **You can also just wait**: the next morning's run automatically widens its window to cover
  the gap (a Monday digest covers the whole weekend the same way). Skipping a rerun loses
  nothing except that day's delivery — on the one live crash so far (2026-07-29) the operator
  deliberately let Thursday absorb it.

## How To: re-login to 13D (when the WILTW session expires — weeks/months)

On the server, open a terminal in the project folder and run
`.venv\Scripts\python.exe thirteen_d.py --login` — a browser opens; log in to client.13d.com,
then press ENTER in the terminal. Until this is done, WILTW is simply skipped (the digest
still sends).

*Note:* WILTW publishes on Thursdays and takes occasional multi-week breaks. A
`Report not found` line in the log on a non-publishing week is NORMAL — the session is fine,
there just isn't a report yet. Only a `Session expired — re-login required` line means the
login actually died. If you know a report is due, you can refresh the session ahead of time
with the same `--login` command.

**Who can do this:** the login uses 13D's PAID subscription account (Jared's). Only someone
with those credentials can refresh the session — there is no free or alternative account, and
a new signup would have no access to WILTW. If the session dies and Jared is unavailable,
WILTW simply stays skipped until he re-logs in; the digest is otherwise unaffected.

## How To: paste a fresh Substack cookie (only if auto-renewal fails)

It renews itself via a login code emailed to the owner's gmail and auto-forwarded to the bot —
this manual fallback is only for when the degradation notice names `substack`: log in to
substack.com in a browser, copy the `substack.sid` cookie value (browser dev tools →
Application → Cookies), paste it as the only contents of `substack_cookie.txt` in the project
folder.

## How To: fix API billing (only if the auto-reload card dies)

The Anthropic account is **firm-paid with auto-reload ON** (confirmed 2026-08-03), so there is
**no manual monthly top-up** — the only failure mode is the auto-reload payment itself failing
(e.g. an expired card), which shows up as run-FAILED alerts mentioning credit/quota. Fix at
console.anthropic.com (the bot account's login). Expected burn: roughly **$160–180/month**
(re-baselined 2026-07-30 from real cost lines): weekdays run **$6.5–8.5** (the high end is a
Monday covering the weekend), plus roughly **$4–4.50** extra on Fridays for the two weekly
wraps; reply questions add a little on top.

## How To: bring in code that was updated elsewhere

Routine code updates are a plain pull between runs:

```powershell
git pull
```

**One rule:** if the pull touched `reply_monitor.py` or `alert_commands.py` (or you changed
recipients in `env.bat`), restart the reply daemon — it holds old code until restarted:

```powershell
schtasks /End /TN \DailyDigest\ReplyMonitor; schtasks /Run /TN \DailyDigest\ReplyMonitor
```

Pulls touching only the morning-digest code need no restart (each morning run is a fresh
process). Reinstall dependencies only if `requirements.txt` changed
(`.venv\Scripts\pip install -r requirements.txt`).

---

## Question: what does each email mean?

- **🚨 Daily Digest run FAILED — …** — the morning run crashed; the email body shows the last
  log lines. Usually transient (network); if it repeats two days running, get a developer to
  read `logs\digest_<date>.log`.
- **🚨 Daily Digest MISSING — no completed run — …** — the 9 AM watchdog: the run hung or never
  started (machine off/asleep, or a login prompt is blocking). Check the machine is on; rerun
  by hand (How To above) or let tomorrow absorb it.
- **Red "⚠️ ALERTS" box at the top of a digest** — market/content alerts only (your configured
  alert triggers, Fed stress signals, and "Watch item expiring"/"expired" notices — reply to
  renew those). Nothing in the red box is a system problem.
- **Grey "⚙️ System notices" footer at the BOTTOM of your [FULL] digest** (since 2026-07-28;
  replaces the old separate ⚙️ email — you asked for one email, not two) — system-health
  notices, visible only on the FULL digest, never the team's. The ones to know:
  - **"Source degradation: <source>: 0 items for 3 straight runs…"** — a data source silently
    died. `substack` → the cookie How-To. `wiltw` → the 13D How-To. `pacer_rss_<court>` → that
    court's RSS feed died (court-side; nothing to fix locally — a developer can check for a
    replacement). Anything else → developer.
  - **"Output truncated"** — a generation pass hit its token cap; the digest may be missing
    trailing sections. One-off is fine; recurring → developer.
  - **"Team config missing"** — the server lost the `DIGEST_TO_TEAM` setting in `env.bat`; the
    team digest isn't going out and memory/search updates are paused as a privacy guard.
    Restore the line in `env.bat` (sample in `DEPLOYMENT.md`) or get a developer.

  No footer = nothing to report (the normal state).
- **"backup FAILED"** — the 09:45 off-box copy couldn't find its OneDrive folder; see
  "Backups & restore" below.
- **"(TEST drill)" anywhere in a subject** — it's a drill, not a real failure.

## Question: is it safe to rerun the digest multiple times?

Yes — nothing breaks, recipients just get another email. Details worth knowing: a rerun after
a **failure** produces the normal full digest (the failed attempt saved nothing). A second run
after a **successful** send produces a much thinner digest — each run only covers the time
since the last saved digest — so there's rarely a reason to do it. Court-filing entries from a
crashed run can reappear in the rerun; that's deliberate (the system prefers repeating an entry
over silently losing one).

## Question: who gets each email?

- **Your [FULL] digest** goes to the owner address (`DIGEST_TO`, default jtramontano) — it
  includes Substack content and your personal alert box, plus the grey system-notices footer
  when there's something to report.
- **The team digest** goes to everyone in `DIGEST_TO_TEAM` (in the server's `env.bat`) — same
  digest minus Substack, each copy with that person's own alert box.
- **🚨 failure/watchdog alerts** go to the operator (you).
- Weekly wraps follow the same FULL/team split every Friday.

## Question: where do things live on the server?

- Sent digests: `digests\<date>.html` (and `…_team.html`); everything the system read that
  day: `archive\<date>\`; logs: `logs\` (30-day rotation).
- Asking questions: **reply to any digest email** from your work address — the bot answers
  in-thread within ~5 minutes. (Replies also manage the alerts and watchlist — see above.)
- **Bot-account security emails live in a "Gmail Alerts" folder**, not the inbox: Google's
  account emails about MFA/2-Step Verification and sign-in alerts for
  `acorn.research.bot@gmail.com` are auto-filtered there (filter added 2026-07-17 — they were
  being read into the digest as "source emails"). Because they skip the inbox, the digest will
  NOT surface them — so if you ever suspect something is off with the bot account (an
  unexpected sign-in, a recovery-info change), log into the bot's Gmail and check the **Gmail
  Alerts** label directly. The filter lives on the Google account itself — just don't delete it.
- Known slow burn (developer item, NOT urgent — **nothing is due in August**): the search index
  grows daily (~1,000–1,400 entries/weekday; 20,157 on 2026-07-30) and in theory gets slower as
  it does. A benchmark run 2026-07-30 showed the slowdown is negligible for years: search stays
  well under a tenth of a second even at 10x today's size, and the reply bot's answer time is
  dominated by the AI call, not the search. **Do nothing unless reply answers actually start to
  feel slow (or the server runs low on memory) — realistically not before late 2027.** If that
  ever happens, a developer (or a Claude Code session pointed at HANDOFF §5) has the fix recipe
  ready. Not an outage risk; answers never become wrong, only slower.

## Question: what happens if something breaks beyond this page?

Any developer can pick the project up cold: everything they need is in the project folder —
start with `HANDOFF.md` (state + constraints at the top, then the condensed Session history for
the "why" behind any decision; the full dated narrative is in git history). Nothing about the
system lives only in someone's head.

---

## Backups & restore

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

**How to restore (if the server's disk fails):**
1. Set the project up fresh on a machine per `DEPLOYMENT.md`.
2. Re-supply the secrets — they were **not** backed up, on purpose: the Gmail login, Substack
   cookie, 13D session, and `env.bat`. See `DEPLOYMENT.md` step 3.
3. Copy the contents of `DailyDigest-Backup\` (from OneDrive) back into the project folder.

The archive, memory, and search index all come back, and the system continues from the last
backup. *(Developer detail — the copy mechanism, what's included, and the safety flags — is in
`run_backup.bat`'s comments and HANDOFF's Session history, 07-20 entry.)*
