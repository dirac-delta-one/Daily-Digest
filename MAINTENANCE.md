# Maintaining Daily Digest — Developer Guide

> The "how to run this without the person who built it" guide. Audience: a developer inheriting the
> project cold. `OPERATIONS.md` is the non-technical operator runbook (what emails mean + three
> manual fixes); this is its technical companion — secrets, rotation, every known failure case with
> a fix, and how to change the code safely.
>
> **Read order for a cold start:** `HANDOFF.md` §1–§6 (state + constraints + do-NOT-touch) → this
> file → `WORKLOG.md` (the full "why" behind any decision; the executed deploy/cutover is the
> 2026-07-20/21 entries).

---

## 1. Mental model in 60 seconds

Three entry points, all Python, all scheduled via `run_*.bat` wrappers → Task Scheduler:

- `digest.py` — the morning job. Fetches ~17 sources, builds a 2-pass prompt (generation model =
  Claude Fable 5 since 2026-07-22, `config.FABLE_MODEL`; satellites stay on Opus), generates a
  **full** and a **team** digest, emails both, archives raw content, indexes it into FAISS, updates
  memory, and (Fridays) sends a weekly wrap.
- `reply_monitor.py` — long-running daemon; answers emailed replies to digests via RAG over the
  archive. Also the write path for the email-managed watch config (ALERT_COMMANDS_SPEC,
  2026-07-22): replies that are alert/watchlist commands ("watch for X until Aug 15") are parsed
  by Sonnet in `alert_commands.py`, applied to the state files, and confirmed in-thread.
- `run_alert.py` — invoked by the wrappers on nonzero exit (failure alert) and by the 9 AM watchdog
  (`--check-completed`); deliberately self-contained (imports nothing that could have failed). Also
  drives the weekday `Backup` task's off-box copy alerting.

**Where state lives:** `archive/<date>/` (raw content per run) + `archive/index.faiss` +
`archive/chunk_metadata.json` (the search index); `memory.json` / `substack_memory.json` (evolving
storylines); `*_cache.json`, `pacer_seen.json`, `source_counts.json` (per-source caches/state);
`alerts_config.json` / `watchlist.json` (the email-managed alerts + SEC watchlist — gitignored,
**seeded from `alert_commands.py` defaults when missing**, written atomically; if one is corrupted
the code runs on built-in defaults without overwriting it — restore from the O4 backup);
`digests/<date>.html` (sent digests); `logs/` (30-day rotation).

**Cost:** only the Claude API costs money per run (see `HANDOFF.md §2` cost tiers). Everything else
is free public data or flat subscriptions. **Never loop a Claude-calling path to test it.**

---

## 2. Secrets & credentials

All gitignored; account-bound (not machine-bound). Copy from a working install or regenerate.

| File / var | What it is | Binds to | Expiry / rotation |
|---|---|---|---|
| `credentials.json` | Google OAuth **client** | the Cloud project | Long-lived. Rotate only if leaked (regenerate the OAuth client, re-download, re-consent). |
| `token.json` | Gmail **access/refresh** token | the bot Gmail account | Durable **only in Production** publishing status. Rotate when Google revokes it (see §2a). |
| `substack_cookie.txt` | Substack session (`substack.sid`) | jared's Substack account | Expires in **weeks**. Auto-renews via OTP; manual paste is the fallback (§4). |
| `thirteen_d_session.json` | Playwright storage state | jared's **paid** 13D account | Expires in **weeks–months**. Manual re-login only (§4) — **requires Jared's 13D credentials; no free/alternative account.** |
| `ANTHROPIC_API_KEY` (env) | Claude API key | the bot's Anthropic account | No expiry. Rotate if leaked. Watch the credit balance. |
| `FRED_API_KEY` (env) | FRED data key | free FRED account | Stable, free. No rotation. |
| `SUBSTACK_EMAIL` (env) | inbox the Substack OTP code arrives at | — | Config value, not a secret. |

**Do NOT copy `credentials_JARED.json` to the server** — it's a dev-machine backup only. The server
uses `credentials.json` + the production `token.json`.

### 2a. The Gmail token — the one that bites you

The single highest-risk credential. Two rules:

1. **The OAuth app MUST be in "Production" publishing status.** In Testing mode, refresh tokens die
   after **7 days** → the digest breaks weekly, and a headless server can't do the interactive
   re-consent to recover. This was live-confirmed on the accrual week (day 7). The app is already
   published; keep it that way.
2. **Regenerating the token needs a browser** (interactive consent), so do it on a machine that has
   one, then copy `token.json` to the server. On the server, `DIGEST_UNATTENDED=1` makes a dead
   token **fail fast with an alert** instead of hanging on a consent prompt.

**Symptom of a dead token:** `invalid_grant` in the log, or a "run FAILED" alert mentioning auth.
**Fix:** on a browser machine, delete `token.json`, run `python digest.py` (or a Gmail
metadata call) to trigger consent as `acorn.research.bot@gmail.com`, verify `getProfile` returns the
bot, copy the new `token.json` to the server. Never re-consent in Testing mode.

### 2b. The bot Google account has MFA — keep it TEAM-OWNED

The bot account (`acorn.research.bot@gmail.com`) has 2-Step Verification enabled (set up during the
2026-07 server deploy). **The MFA method must be owned by the team, not one person** — a shared TOTP
secret in a password manager, passkeys/security keys held by 2+ admins, or a shared phone number. If
it's tied to a departing person's device, the team loses the ability to re-authenticate the bot
account (e.g. to mint a new `token.json`). Note: enabling/changing MFA can trigger a ~48h Google
lockout of *interactive* sign-in — existing OAuth refresh tokens keep working through it (a running
instance is unaffected), but you can't mint a fresh token until it clears.

**The server uses its own OAuth client.** Google no longer allows re-downloading an existing OAuth
client's secret, so the server got a *new* Desktop client (its own `credentials.json`) and mints its
own `token.json`. The dev laptop's original client + token are independent. **Deleting an OAuth
client revokes every token issued under it** — don't delete the old client while any instance still
uses it.

---

## 3. Environment variables

Set at the **machine/system** level on the server (so non-interactive tasks see them), via `env.bat`
which the wrappers `call`. Required: `ANTHROPIC_API_KEY`, `DIGEST_TO_TEAM`. Recommended:
`FRED_API_KEY`, `SUBSTACK_EMAIL`. Leave `DIGEST_TO` **unset** in production (it defaults to the
owner). `DIGEST_UNATTENDED=1` is set machine-wide by `setup_tasks.ps1`; `PYTHONUTF8=1` by the
wrappers.

**`DIGEST_TO_TEAM` is load-bearing:** since team activation, a run *without* it is treated as
misconfigured — the digest still sends, but indexing + memory are frozen (a privacy guard so
Substack prose can't leak to team askers) and an alert fires. If the team variant is ever
deliberately retired, set `config.TEAM_ACTIVATION_DATE = None` (otherwise the guard freezes indexing
forever).

---

## 4. Failure cases & fixes

Ordered roughly by how often you'll see them. Each: **symptom → cause → fix.**

**Run FAILED alert (red email, log tail attached).** The run crashed (nonzero exit). Usually a
transient network blip — check `logs\digest_<date>.log`. If it repeats two days running, debug the
traceback. The alert email itself contains the last 40 log lines.

**Run MISSING alert (9 AM watchdog).** The morning run hung or never started — machine
off/asleep, network was down at wake, or a login prompt is blocking. Confirm the machine is on and
awake, check for a blocking consent (§2a), re-run `run_digest.bat` by hand.

**"Source degradation: <source>: 0 items for 3 straight runs" (in-digest red box).** A normally
-populated source silently died. `substack` → renew the cookie (below). `wiltw` → 13D re-login
(below). Anything else → read that fetcher's log block; likely a feed/endpoint change.

**Substack dead / degraded.** Symptom: `substack` degradation alert, or `[preview only…]` markers
where full text used to be. It auto-renews via the OTP code Substack emails (read from the bot inbox
— requires jared's `no-reply@substack.com` auto-forward to be live and `SUBSTACK_EMAIL` set).
**Manual fallback:** log into substack.com in a browser, copy the `substack.sid` cookie value (dev
tools → Application → Cookies), paste it as the *only* contents of `substack_cookie.txt`.
*Note:* the 9 custom-domain pubs get full text only via Substack's unauthenticated per-post API
(the auth cookie is `.substack.com`-scoped); if Substack closes that, they degrade to previews —
accepted, visible via the markers.

**13D / WILTW missing.** Two distinct causes — read the log to tell them apart:
- `Report not found` = the session is **authenticated** but no report exists at that date. WILTW
  publishes Thursdays and takes **periodic multi-week breaks** (e.g. the Q2 2026 break — the 7/02
  report's own footnote announced the next as 7/16). This is normal; the digest skips gracefully.
- `Session expired — re-login required` (a redirect to the login page) = the session actually died.
  No auto-renewal — interactive login only. **Fix:** `.venv\Scripts\python.exe thirteen_d.py
  --login`, log into client.13d.com in the browser that opens, press ENTER.
  **Credentials:** 13D is a **paid subscription and the account is Jared's** — only he (or a holder
  of those credentials) can perform the `--login`. There is no free tier and a new bot-email account
  would have **no WILTW access**, so this is not a fix a developer can do alone. If Jared is
  unavailable when the session dies, WILTW stays skipped (non-fatal, 1 of ~17 sources) until he
  re-logs in. Long-term ownership (keep it Jared's vs. transfer/re-purchase under the bot) is a
  billing decision for Acorn, not a code task.

Session note: 13D auth is a **server-side session** (`thirteen_d_session.json` holds a `user`
session-cookie with no client-visible expiry), so you can't tell staleness from the file — only a
live request shows it. To de-risk a known-upcoming report, run `--login` proactively beforehand.
**O3 caveat:** the content monitor will NOT alert on a WILTW outage if `wiltw` has been 0 across the
whole recorded window (a long break makes it look "normally zero"), so after a break ends, manually
confirm WILTW returns (`source_counts.json` → `wiltw > 0`) rather than trusting the degradation
alert. Once it logs one nonzero day, O3 can catch future zero-streaks.

**"Team config missing" alert.** The environment lost `DIGEST_TO_TEAM` (§3). That run skipped
indexing + memory on purpose. Restore the line in `env.bat`; the next run self-heals.

**Digest not delivered / quarantined.** A mail-security product (Abnormal AI) flagged the digest as
malicious once (new sender + emoji subject + link-dense HTML). IT allowlisted
`acorn.research.bot@gmail.com` org-wide for Outlook. If a **non-Outlook** recipient is added and
doesn't receive digests, get their mail security to allowlist the bot — the failure alerts share the
sender, so quarantine can silence both signal paths at once.

**API credit exhausted.** "run FAILED" alerts mentioning credit/quota. Top up at
console.anthropic.com (the bot account's billing). Expected burn ~$45–55/month.

**Reply bot double-answering / racing.** Exactly ONE reply daemon may run anywhere — two poll the
same inbox and race (mark-as-read isn't atomic). This only happens if a second instance was left
running (e.g. the old machine wasn't decommissioned at cutover). Kill the extra.

**Reply answers feel repetitive / slow.** Repetitive → paraphrase-level dedup may be needed
(`HANDOFF.md §11.B`). Slow → the FAISS index has grown; see the index-growth ladder (§5 below).

**Memory anomalies.** If a "new" story is actually a resolved story restated (the resolved-story
re-creation watch, `HANDOFF.md §11.B`), the revert lever is named in
`memory._story_index_for_prompt`. If `memory.json` is ever corrupted, each `archive/<date>/`
directory snapshots that day's `memory.json` / `substack_memory.json` for recovery — copy the last
good one back.

**PACER duplicates.** After a crashed run, previously-seen court entries can re-appear next run
(by design — `commit_seen()` only fires after a successful send, choosing duplication over silent
loss). Harmless; no action.

---

## 5. Routine maintenance calendar

| Cadence | Task |
|---|---|
| Continuous (automatic) | Failure/watchdog/degradation alerts; log rotation (30-day). Just watch your inbox. |
| Every few weeks (reactive) | Substack cookie — usually auto-renews; paste manually if the degradation alert fires. |
| Weeks–months (reactive) | 13D re-login when the WILTW zero-streak alert fires. |
| Monthly | Glance at the Anthropic credit balance; top up before it hits $0. |
| When you touch the project | Add a few golden-set questions for new archive days, incl. cross-day ones — the eval only stays meaningful if it compounds. |
| At ~30–50k index vectors, or when replies feel slow | Work the index-growth ladder: (1) vectorized subset scan ✅ done → (2) date-windowed retrieval default → (3) prune old days from the live index → (4) IVF. Detail in `HANDOFF.md §5`. |
| Continuous (automatic) since 2026-07-21 | **O4 off-box backup** — `run_backup.bat` (Backup task, weekdays 09:45) robocopies state-only into `%OneDriveCommercial%\DailyDigest-Backup`, synced off-box by OneDrive. Just watch for a "backup FAILED" alert; glance at the OneDrive web folder every few weeks to confirm it's actually uploading. Restore steps in `OPERATIONS.md` → "Backups & restore". *(Re-registering the task needs an **elevated** `setup_tasks.ps1 -StoredPassword` — a non-elevated run fails with `Register-ScheduledTask: Access is denied`.)* |

---

## 6. Changing the code safely

- **Read `HANDOFF.md §6` first.** Several blunt-looking pieces are intentional and load-bearing
  (the module-level argv parse, the conservative PDF cleaner, the model-written §9 Rating Actions,
  the reply daemon loop, the parked rerank/hybrid mechanisms, `IndexFlatIP`). Don't "fix" them.
- **Cost discipline (`HANDOFF.md §8`).** Prefer unit tests. When a Claude-calling path must run, run
  **once** on a **small** input, **with permission**, and route all email to a test address — never
  the production recipients, never a loop. `count_tokens` calls are free. Substack/13D scraping is
  free to test (flat subscriptions, no Claude call — except 13D's embedded summary).
- **The gate:** `check.bat` = `ruff check` + `pytest` (395 tests as of 2026-07-22). Both must pass
  before commit.
- **The eval harness:** `tools/eval_retrieval.py` + `tools/eval_golden.json` measure retrieval
  quality (current baseline: hit@1 0.897 / hit@3 1.0 / MRR 0.937, zero misses,
  `tools/eval_results/2026-07-15_post_index_filter.json`). Re-run and compare after any change to
  chunking, embedding, indexing, or the reply path. Rebuild the index with `python search.py
  --rebuild` after extraction/chunking changes.
- **Module convention:** source fetchers expose `fetch_X()` / `format_X_for_prompt()` /
  `build_X_html()`. A new source is one module in that shape plus a row in `digest.py`'s fetch
  registry (pinned by `tests/test_source_registry.py` / `test_digest_prompt.py`).
- **Alerts & the watchlist — two separate levers.** The top-of-digest alert *triggers* live in
  `alerts_config.json` (plain JSON — add/edit/tune freely, no code, re-read each run). The *ticker
  universe* is `WATCHLIST` in `sec_filings.py` (a Python list — a **code** edit) and is the single
  source of truth for SEC filings, earnings, entity tagging, **and** — since 2026-07-21 — the
  scoping of the two "watchlist"-referencing alerts (Insider selling, Rating downgrade), which
  `digest.py` injects into the alert prompt. So editing that one list updates all four at once. The
  event-based triggers (Large Chapter 11, HY spread blowout, Fed surprise, Bank failure, Distressed
  exchange) are watchlist-independent and fire on the event regardless of ticker. Alerts are
  evaluated **per variant** (FULL sees Substack; TEAM doesn't), so a Substack-sourced alert appears
  only in the owner's box — by design.
- **Commits:** `main` is the working/authoritative branch (since 2026-07-20 — the server tracks it;
  the old `ava-updates` branch was retired with Jared's instance). Commit and deploy from `main`;
  use a short-lived feature branch only for risky in-progress work. Keep the WORKLOG habit — a dated
  entry explaining what changed and *why* is how the next person (or you, in six months) stays
  oriented.

---

## 7. If you're stuck

Everything needed to pick this up cold is in the repo. Start with `HANDOFF.md §1`, then the
`WORKLOG.md` entry for whatever you're touching (it records the reasoning, the alternatives
considered, and what was measured). The git history is the complete record. Nothing about this
system lives only in someone's head — which is the whole point of these docs.
