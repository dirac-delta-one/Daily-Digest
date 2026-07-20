# Deploy Progress — Server Cutover (LIVE — started 2026-07-15)

> Live status of the §7.2 server deployment, written so a **fresh conversation can resume cold.**
> Read this + `HANDOFF.md §1`. Companions: `NEXT_STEPS_SPEC.md §5` (the generic deploy/cutover
> checklist), `OPERATIONS.md` (operator runbook), `MAINTENANCE.md` (secrets/failure modes).
> **Mark this DONE / delete it once the server is live and has soaked cleanly.**

## STATUS: CUTOVER DAY (Mon 2026-07-20) — two gates, then execute the steps below
- **Target server:** dedicated always-on Windows box, user `ShawnArmstrong`, repo at
  `C:\Users\ShawnArmstrong\code\Daily-Digest` (cloned from `main` @ merge `1a64778`).
- **GATE 1 — Anthropic credit is EXHAUSTED** (hit $0 on the 7/17 run's last call; the team weekly
  wrap failed 400 and was deliberately not regenerated). **Top up at console.anthropic.com
  (bot account) BEFORE step 5** — the manual run dies at pass 1 otherwise. Expected burn
  ~$45–55/month.
- **GATE 2 — the Google MFA lockout has NOT cleared** (extended 48h → **72h** by repeated
  sign-in attempts; still locked Mon ~9:45 AM). Interactive consent is blocked, so the server
  `token.json` cannot be minted the planned way → use **Plan B in step 3** (copy the dev
  laptop's token pair; needs NO interactive sign-in). Refresh tokens are unaffected (the 7/16
  + 7/17 dev runs prove it). Do NOT keep retrying sign-ins — each attempt can extend the window;
  when it does clear, make the first attempt from the DEV machine (a trusted device), and if any
  browser still holds a live bot session, generate **backup codes** from it (also the fix for
  the MFA-must-be-team-owned item).
- **Interim runs: COMPLETE.** Thu 7/16 GREEN $1.78; Fri 7/17 GREEN $3.72 (both variants + FULL
  weekly; WILTW 2026-07-16 fetched + cached; memory budget's first activation, clean; details in
  WORKLOG 2026-07-17→20). Dev state is FINAL through Fri 7/17 — no weekend runs.
- **Jared is decommissioned** — no longer running his own instance. The server will be the ONLY
  instance, so the "exactly one digest / one reply daemon" cutover concern is already satisfied.
  Dev's only scheduled task (MorningDigest) is confirmed Disabled.

## Key decisions / gotchas this session (2026-07-15)
- **Python 3.12, not 3.13.** The server shipped with 3.13; we installed **3.12.7** and built the
  venv on it to match the pinned/tested env (`requirements.txt` is 3.12-resolved). Use 3.12.
- **New OAuth Desktop client** created in Google Cloud for the server — Google no longer lets you
  re-download an existing client's secret, so a fresh Desktop client was made and its JSON saved as
  the server's `credentials.json`. The dev laptop's OLD client + `token.json` keep working
  independently. **Do NOT delete the old client** until the server is confirmed live (deleting a
  client revokes every token issued under it, incl. the dev laptop's).
- **Server `token.json` is minted fresh on the box** and is durable (the app is Production-published;
  the old "never re-consent" caution was Testing-mode-only).
- **Bot Google account now has MFA.** ⚠️ **MFA MUST be team-owned** — shared TOTP in a password
  manager, or passkeys/security keys held by 2+ admins, or a shared phone — **NOT** acohen's
  personal device, since acohen leaves **2026-07-31** (otherwise the team loses the ability to
  re-auth the bot account). Enabling MFA caused the 48h lockout; refresh tokens survived it.
- **Transfer constraints:** RDP copy-paste is disabled on the server. Secrets are **regenerated on
  the box, never emailed** (a safety guardrail correctly blocked bundling secrets for email). Only
  the **non-sensitive state** (archive / memory / caches / digests) was moved, via a zip through the
  bot's Gmail.
- **Production recipients:** `DIGEST_TO` **unset** → full digest to `jtramontano@acorninv.com`;
  `DIGEST_TO_TEAM=apain@acorninv.com,acohen@acorninv.com` (acohen on the team list to monitor during
  soak — **drop acohen at the 7/31 departure**).
- **FRED key** is a static reusable string — reuse the existing value (no FRED account login needed).
- **13D** logged in on BOTH the server and the dev laptop today. If 13D allows only one active
  session per account, the dev login may have invalidated the server's session → **recheck Monday**;
  if WILTW errors on the server, just re-login there. 13D re-login needs **Jared's paid credentials**.

## Done on the server ✅
- Python 3.12.7 venv + `pip install -r requirements.txt` + `playwright install chromium`
- State transferred + verified (10 archived days; `search.py "credit markets"` returns ranked hits →
  torch/faiss/sentence-transformers + the transferred index all work on-box)
- `credentials.json` (the new Desktop client) in the repo root
- `env.bat`: `ANTHROPIC_API_KEY` + `FRED_API_KEY` + `SUBSTACK_EMAIL` + `DIGEST_TO_TEAM` + `PYTHONUTF8`;
  `DIGEST_TO` intentionally unset. ANSI-encoded; verified it loads.
- Free smokes pass: `news.py` (150 articles), `search.py` (index search)

## Interim runs — ✅ COMPLETE (Thu 7/16 + Fri 7/17, dev laptop)
Both GREEN to the real recipients (dev `env.bat`: `DIGEST_TO=jtramontano,acohen`;
`DIGEST_TO_TEAM=apain,acohen`): 7/16 $1.78; 7/17 $3.72 incl. WILTW 2026-07-16 ($0.87, now
cached — the server's first run gets it free) and the FULL weekly wrap. The 7/17 run's LAST
call (team weekly) failed on the exhausted credit — accepted, not regenerated (GATE 1 above).
The reply-monitor gap (no daemon anywhere since 7/15) continues until cutover step 6; interim
replies were never answered (`newer_than:1d` query — they won't be answered late either).
Heads-up for jared if he asks: the 7/17 FULL digest's "possible account-compromise attempt"
note was Opus reading the operator's own MFA-lockout alert emails — not a compromise; those
alerts now auto-file to the "Gmail Alerts" label (filter added 7/17, see NEXT_STEPS §5).

## Monday 7/20 — cutover (in this exact order)
0. **Sync CODE to the server**: the digest-format updates (anti-repetition prompt, snapshot
   redesign, market-data 1M-lookback bugfix, iShares OAS, SPCX — see WORKLOG) landed on
   `ava-updates` AFTER the `1a64778` merge the server cloned (~35 commits). Merge
   `ava-updates` → `main`, push, then `git pull` on the server — otherwise the server runs the
   old format. *(Steps 0, 2, and 4 need no Gmail token — they can run before the gates clear.)*
1. **Stop running on dev** — ✅ effectively done (state final through Fri 7/17; task Disabled).
2. **Re-sync state dev → server:** rebuild the state zip on dev (`archive\` + `memory.json` +
   `substack_memory.json` + the `*_cache.json` (incl. `wiltw_cache.json` + `ishares_oas_cache.json`)
   /`pacer_seen.json`/`source_counts.json` + `digests\` — same as the 2026-07-15 transfer; it's
   **secrets-free**, so extracting it on the server overwrites the stale 7/15 state but leaves the
   server's `token.json` / `credentials.json` / 13D session / `env.bat` untouched) → email to bot
   → download + extract on the server.
3. **Get a working `token.json` onto the server — two routes:**
   - **Plan A (only if the MFA lockout has cleared):** mint fresh on the box —
     `.\.venv\Scripts\python -c "import digest; digest.get_gmail_service()"` → log in as bot →
     authorize (uses the server's NEW OAuth client already staged there).
   - **Plan B (lockout still active — README-sanctioned, no interactive sign-in):** copy the DEV
     laptop's `credentials.json` **and** `token.json` TOGETHER to the server (the durable
     production token is bound to ITS OAuth client — the pair must match; the dev pair replaces
     the server's staged `credentials.json`). Transfer over a **non-email** channel only (USB /
     corporate file share / password-manager secure send — the 7/15 secrets-never-emailed
     guardrail stands; the bot-Gmail zip is for the secrets-free state only). The server then
     authenticates by refresh alone. The server's unused new OAuth client stays in Cloud Console
     — **delete NEITHER client** (deleting one revokes its tokens).
4. **Recheck 13D on the server** — the 7/17 dev WILTW fetch used the DEV session and may have
   collided if 13D is single-session. If WILTW errors, re-login:
   `.\.venv\Scripts\python thirteen_d.py --login` (needs Jared's creds; the save guard refuses
   to persist a not-logged-in state).
5. **Server manual run** — **GATE 1 first: confirm the Anthropic credit top-up is done.** Then
   `run_digest.bat` = Monday's digest **and** the validation run. Substack self-renews (OTP from
   the now-readable inbox). Verify: both variants deliver; first-run watch-list; WILTW comes from
   the synced cache (no download); `Memory context: … of 73 active` line sane (budget now trims —
   expected); sane cost line.
6. **`setup_tasks.ps1` as administrator** — registers the 4 tasks (Morning 08:00 / Watchdog 09:00 /
   Midday 13:00 / ReplyMonitor at startup) + sets `DIGEST_UNATTENDED=1` machine-wide. **Only after
   step 5 passes** — without a working token the tasks just fail, and the failure alert itself needs
   the token to send.

## Tuesday 7/21 — first true automation
- Confirm the 08:00 scheduled run fires + delivers both variants; the 09:00 watchdog stays silent.

## Post-deploy
- **O4 backups** — scheduled off-box copy of `archive\`, `memory.json`, `substack_memory.json`, the
  caches, `digests\`, and the two index files.
- **Watchdog drill** — `run_alert.py digest --check-completed --test` → a "(TEST drill)" email arrives.
- **Hand `OPERATIONS.md` to Jared** — the three manual fixes (13D re-login, substack paste, credit top-up).
- **Retire the dev laptop** — ensure no scheduled task runs there once the server has soaked.
- Optional cleanup: delete the OLD OAuth client in Cloud Console (only after the server is confirmed
  live — it revokes tokens issued under it).

## For whoever resumes in a new conversation
- A fresh conversation on the **dev laptop** reads this repo (branch `ava-updates`) — it has the
  latest code + docs. Confirm `main` also carries this session's commits (13D session-save guard +
  Substack-via-email boundary + docs) before the server relies on them — they were on `main` as of
  merge `1a64778` / commit `412d1ad`.
- The full "why" behind every item above is in `WORKLOG.md` (2026-07-15 entries).
