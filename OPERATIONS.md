# Daily Digest — Operations Runbook

> For the person who receives the alerts (jared) — no code knowledge assumed.
> One page: what each email means and the three manual fixes you may ever need.
> Written 2026-07-15 ahead of the server handoff; the technical companion
> docs are HANDOFF.md / WORKLOG.md (for a developer).

## What runs, when (Windows Task Scheduler, folder `\DailyDigest\`)

| Task | When | What it does |
|---|---|---|
| MorningDigest | Mon–Fri 08:00 | Builds + emails the Daily Research Digest (your FULL version and the team version) |
| Watchdog | Mon–Fri 09:00 | Emails an alert if the morning digest never completed |
| Backup | Mon–Fri 09:45 | Copies the day's data off-box to OneDrive (see "Backups & restore" below) |
| ReplyMonitor | at startup, always on | Answers questions you email as replies to a digest |

To check they're registered/running (PowerShell):
`Get-ScheduledTask -TaskPath "\DailyDigest\"`
To re-run the digest by hand: double-click `run_digest.bat` in the project folder.

## The emails you might get, and what to do

- **🚨 Daily Digest run FAILED — …** — the morning run crashed; the email body
  shows the last log lines. Usually transient (network); if it repeats two days
  running, get a developer to read `logs\digest_<date>.log`.
- **🚨 Daily Digest MISSING — no completed run — …** — the 9 AM watchdog: the
  run hung or never started (machine off/asleep, or a login prompt is blocking —
  see the two manual fixes below). Check the machine is on; re-run
  `run_digest.bat` by hand.
- **Red "⚠️ ALERTS" box at the top of a digest** — market/content alerts only
  (your configured alert triggers, Fed stress signals, and "Watch item
  expiring"/"expired" notices for timed alerts/watchlist tickers — reply to
  renew those). Nothing in the red box is a system problem.
- **"⚙️ Digest operational alerts — …"** (separate email, arrives just after
  the digest) — system-health notices. The two to know:
  - **"Source degradation: <source>: 0 items for 3 straight runs…"** — a data
    source silently died. `substack` → do the Substack cookie fix below.
    `wiltw` → do the 13D re-login below. Anything else → developer.
  - **"Team config missing"** — the server lost the `DIGEST_TO_TEAM` setting in
    `env.bat`; the team digest isn't going out and memory/search updates are
    paused as a privacy guard. Restore the line in `env.bat` (see the sample in
    README) or get a developer.
- **"(TEST drill)" anywhere in a subject** — it's a drill, not a real failure.

## The three manual fixes

1. **13D re-login** (needed every time the 13D session expires — weeks/months):
   on the server, open a terminal in the project folder and run
   `.venv\Scripts\python.exe thirteen_d.py --login` — a browser opens; log in to
   client.13d.com, then press ENTER in the terminal. Until this is done, WILTW
   is simply skipped (the digest still sends).
   *Note:* WILTW publishes on Thursdays and takes occasional multi-week breaks. A
   `Report not found` line in the log on a non-publishing week is NORMAL — the
   session is fine, there just isn't a report yet. Only a `Session expired —
   re-login required` line means the login actually died. If you know a report is
   due, you can refresh the session ahead of time with the same `--login` command.
   **Who can do this:** the login uses 13D's PAID subscription account (Jared's).
   Only someone with those credentials can refresh the session — there is no free
   or alternative account, and a new signup would have no access to WILTW. If the
   session dies and Jared is unavailable, WILTW simply stays skipped until he
   re-logs in; the digest is otherwise unaffected.
2. **Substack cookie paste** (only if auto-renewal fails — it renews itself via
   a login code emailed to your gmail and auto-forwarded to the bot): log in to
   substack.com in a browser, copy the `substack.sid` cookie value (browser dev
   tools → Application → Cookies), paste it as the only contents of
   `substack_cookie.txt` in the project folder.
3. **API credit top-up**: the digest stops generating when the Anthropic
   account hits $0 (you'd see run-FAILED alerts mentioning credit/quota).
   Expected burn: roughly **$90–140/month** (~$4–6/weekday for both digest
   versions + Friday wraps + your reply questions) since 2026-07-22, when
   digest generation moved to a stronger, ~2x-priced model (Claude Fable 5) —
   this range is an estimate; the first live week's cost lines will firm it
   up. Check/top up at console.anthropic.com (the bot account's login).

## Managing alerts & the SEC watchlist (by email — no code needed)

The digest watches two configurable lists: **thematic alerts** (plain-English
triggers checked every morning — e.g. "Any new Chapter 11 filing with over
$500M in liabilities" — hits show in the red ⚠️ ALERTS box) and the **SEC
watchlist** (tickers whose SEC filings and earnings dates are monitored).

**To change either, just reply to any digest email** in plain English from
your work address. The bot understands things like:

- "For the next two weeks, watch for anything on Argentina sovereign debt"
- "Until July 28th, look out for CLO downgrade news"
- "Add CRWV to the watchlist" / "stop watching MSTR"
- "Watch WOLF through earnings, say until Aug 10"
- "Extend the Argentina alert to end of August"
- "Remove the insider selling alert"
- "What alerts are set up right now?"

You'll get a confirmation reply within ~5 minutes stating exactly what
changed; the change takes effect on the next morning's digest. Anyone who
receives a digest can do this, and everyone shares the same lists. Items with
a time limit expire on their own: on the last active day the digest shows a
**"Watch item expiring"** advance warning (renew by reply before coverage
lapses), and the first digest after the end date shows a one-line
**"Watch item expired"** notice — reply to renew if you still want it. If the bot isn't sure what you meant, it replies asking
you to rephrase instead of guessing (and a reply that's just a question is
answered normally — asking questions hasn't changed).

## Where things live (on the server, in the project folder)

- Sent digests: `digests\<date>.html` (and `…_team.html`); everything the
  system read that day: `archive\<date>\`; logs: `logs\` (30-day rotation).
- Asking questions: **reply to any digest email** from your work address —
  the bot answers you in-thread within ~5 minutes. Team members can reply to
  their digests the same way. (Replies can also manage the alerts and the SEC
  watchlist — see the section above.)
- **Bot-account security emails live in a "Gmail Alerts" folder**, not the
  inbox: Google's account emails about MFA/2-Step Verification and sign-in
  alerts for `acorn.research.bot@gmail.com` are auto-filtered there (filter
  added 2026-07-17 — they were being read into the digest as "source emails").
  Because they skip the inbox, the digest will NOT surface them — so if you
  ever suspect something is off with the bot account (an unexpected sign-in,
  a recovery-info change), log into the bot's Gmail and check the **Gmail
  Alerts** label directly. The filter lives on the Google account itself
  (nothing to set up on the server) — just don't delete it.
- Known slow burn (developer item, not urgent): the search index grows daily
  and will get gradually slower after several months (~2026 Q4 at current
  rates); a developer should revisit per HANDOFF §14 when replies feel slow.
- **Off-box backup:** the day's data is copied to OneDrive every weekday — see
  the **"Backups & restore"** section below.

## Backups & restore

**What's backed up, and where.** Every weekday at ~09:45 (just after the morning
digest) a scheduled task (`Backup`) copies the system's DATA to OneDrive — into
`…\OneDrive - Acorn Investment\DailyDigest-Backup\`. It copies the things that
can't be recreated: `archive\` (every day's gathered source material), `digests\`
(the sent digests), the memory files (the evolving storylines), the caches, the
search index, and the run `logs\`. It deliberately does **not** copy any
passwords, keys, or logins — those never leave the server.

**How it gets off the server.** The task just copies the files into the OneDrive
folder on the machine; **OneDrive then uploads them to Acorn's cloud on its own**,
the same way any file you drop into OneDrive syncs. So the safety copy ends up in
the cloud, not only on the server's disk. (The task itself never touches the
internet — it only copies files locally; OneDrive does the uploading.)

**What it depends on.** OneDrive only uploads while the server is **logged in**
(locked is fine — that's how it's kept). If the server were ever fully signed
out, the copies would still be made on disk but wouldn't upload to the cloud
until someone logs in again. If the OneDrive folder can't be found at all, the
backup sends a **"backup FAILED"** alert rather than fail silently. It also never
deletes anything from the backup, so a problem on the server can't wipe the
saved history.

**Is it working? (worth a glance every few weeks.)** The task can confirm only
that it wrote the files on the server — it can't confirm they reached the cloud.
So occasionally open OneDrive (the web site, or the cloud icon in the system
tray) and check the `DailyDigest-Backup` folder is there and recently updated.
If OneDrive shows a sync error, sort that out (a standard OneDrive issue) — the
data is safe on the server in the meantime.

**How to restore (if the server's disk fails):**
1. Set the project up fresh on a machine per `README.md` (install Python + deps).
2. Re-supply the secrets — they were **not** backed up, on purpose: the Gmail
   login, Substack cookie, 13D session, and `env.bat`. See `MAINTENANCE.md §2`.
3. Copy the contents of `DailyDigest-Backup\` (from OneDrive) back into the
   project folder.

The archive, memory, and search index all come back, and the system continues
from the last backup. *(Developer detail — the copy mechanism, what's included,
and the safety flags — is in `run_backup.bat`'s comments and the 2026-07-20
WORKLOG entry.)*

## If something breaks beyond the three fixes above

Any developer can pick the project up cold: everything they need is in the
project folder — start with `HANDOFF.md` §1 (state + constraints), then
`WORKLOG.md` (every change ever made, and why). The git history is the full
record. Nothing about the system lives only in someone's head.
