# Deploy Progress — Server Cutover (LIVE — started 2026-07-15)

> Live status of the §7.2 server deployment, written so a **fresh conversation can resume cold.**
> Read this + `HANDOFF.md §1`. Companions: `NEXT_STEPS_SPEC.md §5` (the generic deploy/cutover
> checklist), `OPERATIONS.md` (operator runbook), `MAINTENANCE.md` (secrets/failure modes).
> **Mark this DONE / delete it once the server is live and has soaked cleanly.**

## STATUS: IN PROGRESS — blocked on a ~48h Google lockout
- **Target server:** dedicated always-on Windows box, user `ShawnArmstrong`, repo at
  `C:\Users\ShawnArmstrong\code\Daily-Digest` (cloned from `main` @ merge `1a64778`).
- **Blocker:** enabling MFA on the bot Google account triggered a ~48h lockout of *interactive*
  sign-in. Existing refresh tokens still work (dev laptop confirmed), but the server's `token.json`
  can't be minted (needs interactive consent) until it clears.
- **Timeline:** dev laptop covers interim runs **Thu 7/16 + Fri 7/17** → **cutover Mon 7/20** →
  **first automation Tue 7/21**. (Lockout is "48h" from ~7/15, so it may clear as early as Fri 7/17
  — you *could* cut over Friday for less interim/re-sync; Monday is the chosen conservative date.)
- **Jared is decommissioned** — no longer running his own instance. The server will be the ONLY
  instance, so the "exactly one digest / one reply daemon" cutover concern is already satisfied.

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

## Blocked on the 48h lockout ⏳
- `token.json` — needs interactive Gmail consent as the bot.
- `substack_cookie.txt` — OTP auto-renew reads the bot inbox, so it needs the token first; it
  self-renews on the first server run.

## Interim runs — DEV LAPTOP only (Thu 7/16 + Fri 7/17)
Dev (`KimCohen`, `C:\Users\KimCohen\Desktop\git-repos\Daily-Digest`) is fully staged and its token
still works (lockout only blocks interactive login). Each weekday morning:
```
run_digest.bat
```
Produces complete digests (Gmail ✅, WILTW ✅ from 7/16, Substack ✅) to the real recipients
(dev `env.bat`: `DIGEST_TO=jtramontano,acohen`; `DIGEST_TO_TEAM=apain,acohen`), ~$1.5–2.6/run.
**Dev is the authoritative state during the interim — do NOT run the server in parallel.**

**No reply monitor runs anywhere during the interim (operator decision 2026-07-15: accept the
gap).** Jared's daemon died with his decommission; the server's starts at cutover step 6. Note:
the daemon's Gmail query is `is:unread newer_than:1d`, so interim replies are NOT answered late —
they're never answered. If a digest reply arrives Wed–Fri, answer it by hand (or ignore).

## Monday 7/20 — cutover (in this exact order)
0. **Sync CODE to the server** (added 2026-07-15, later session): the digest-format updates
   (anti-repetition prompt, snapshot redesign, market-data 1M-lookback bugfix — see WORKLOG) landed
   on `ava-updates` AFTER the `1a64778` merge the server cloned. Merge `ava-updates` → `main`,
   push, then `git pull` on the server — otherwise the server runs the old format.
1. **Stop running on dev** (its state is now final through Friday).
2. **Re-sync state dev → server:** rebuild the state zip on dev (`archive\` + `memory.json` +
   `substack_memory.json` + the `*_cache.json`/`pacer_seen.json`/`source_counts.json` + `digests\`
   — same as the 2026-07-15 transfer; it's **secrets-free**, so extracting it on the server
   overwrites the stale 7/15 state but leaves the server's `token.json` / `credentials.json` /
   13D session / `env.bat` untouched) → email to bot → download + extract on the server.
3. **Mint `token.json` on the server** (lockout cleared):
   `.\.venv\Scripts\python -c "import digest; digest.get_gmail_service()"` → log in as bot → authorize.
4. **Recheck 13D on the server** — if the dev login collided, re-login:
   `.\.venv\Scripts\python thirteen_d.py --login` (needs Jared's creds).
5. **Server manual run** — `run_digest.bat` = Monday's digest **and** the validation run. Substack
   self-renews (OTP from the now-readable inbox). Verify: both variants deliver; first-run watch-list
   (esp. the Substack-email boundary, watch-item #7); sane cost line; **Anthropic account has credit**
   (top up if needed — expected burn ~$45–55/mo).
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
