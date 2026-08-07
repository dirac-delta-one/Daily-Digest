# Operator Guide — Daily Research Digest

**TLDR:** what the automated digest emails mean, the few manual actions you may ever need, and
every known failure case with its fix. The scheduled runs normally do everything (digest
Mon–Fri 08:00 · watchdog 09:00 · off-box backup 09:45 · the reply bot always on) — you only
need this page when an alert email arrives, a run was missed, or you want to change what the
digest watches. Written for the person who receives the alerts (jared); the Monitoring &
Failure Handling section is the more technical half. For code changes see `HANDOFF.md`; for
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
and awake, check for a blocking consent (DEPLOYMENT §3b), rerun `run_digest.bat` by hand.

**"Source degradation: <source>: 0 items for 3 straight runs" (System-notices footer).** A
normally-populated source silently died. `substack` → renew the cookie (How-To above).
`wiltw` → 13D re-login (How-To above). `pacer_rss_<court>` → that court's RSS feed died
(court-side; a ~week of watching before calling it permanent — the txsb lesson). Anything
else → read that fetcher's log block; likely a feed/endpoint change.

**Substack dead / degraded.** Symptom: `substack` degradation notice, or `[preview only…]`
markers where full text used to be. It auto-renews via the OTP code Substack emails (read from
the bot inbox — requires jared's `no-reply@substack.com` auto-forward to be live and
`SUBSTACK_EMAIL` set). **Manual fallback:** the cookie How-To above. *Note:* the 9
custom-domain pubs get full text only via Substack's unauthenticated per-post API (the auth
cookie is `.substack.com`-scoped); if Substack closes that, they degrade to previews —
accepted, visible via the markers.

**13D / WILTW missing.** Two distinct causes — read the log to tell them apart:
- `Report not found` = the session is **authenticated** but no report exists at that date.
  WILTW publishes Thursdays and takes **periodic multi-week breaks** (e.g. the Q2 2026 break —
  the 7/02 report's own footnote announced the next as 7/16). Normal; the digest skips
  gracefully.
- `Session expired — re-login required` (a redirect to the login page) = the session actually
  died. No auto-renewal — the re-login How-To above (Jared's credentials required; there is no
  free tier, so this is not a fix a developer can do alone; WILTW stays skipped — non-fatal,
  1 of ~17 sources — until he re-logs in. Long-term ownership, keep-it-Jared's vs.
  transfer/re-purchase under the bot, is a billing decision for Acorn, not a code task).

Session note: 13D auth is a **server-side session** (`thirteen_d_session.json` holds a `user`
session-cookie with no client-visible expiry), so you can't tell staleness from the file — only
a live request shows it. To de-risk a known-upcoming report, run `--login` proactively.
**O3 caveat:** the content monitor will NOT alert on a WILTW outage if `wiltw` has been 0
across the whole recorded window (a long break makes it look "normally zero"), so after a break
ends, manually confirm WILTW returns (`source_counts.json` → `wiltw > 0`) rather than trusting
the degradation alert. Once it logs one nonzero day, O3 can catch future zero-streaks.

**"Team config missing" notice.** The environment lost `DIGEST_TO_TEAM` (DEPLOYMENT §3d). That
run skipped indexing + memory on purpose (a privacy guard so Substack prose can't leak to team
askers). Restore the line in `env.bat`; the next run self-heals. If the team variant is ever
deliberately retired, set `config.TEAM_ACTIVATION_DATE = None` (otherwise the guard freezes
indexing forever).

**Digest not delivered / quarantined.** A mail-security product (Abnormal AI) flagged the
digest as malicious once (new sender + emoji subject + link-dense HTML). IT allowlisted
`acorn.research.bot@gmail.com` org-wide for Outlook. If a **non-Outlook** recipient is added
and doesn't receive digests, get their mail security to allowlist the bot — the failure alerts
share the sender, so quarantine can silence both signal paths at once.

**API credit exhausted.** "run FAILED" alerts mentioning credit/quota. Billing is firm-paid
with auto-reload ON (2026-08-03), so this should only happen if the reload payment itself fails
(e.g. card expired) — the billing How-To above.

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

**Corrupted alerts/watchlist state file.** `alerts_config.json` / `watchlist.json` are written
atomically and seeded from `alert_commands.py` defaults when missing; if one is ever corrupted,
the code runs on built-in defaults **without overwriting the damaged file** — restore it from
the O4 backup (or delete it to accept a fresh default seed).

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
