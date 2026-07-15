# Maintaining Daily Digest — Developer Guide

> The "how to run this without the person who built it" guide. Audience: a developer inheriting the
> project cold. `OPERATIONS.md` is the non-technical operator runbook (what emails mean + three
> manual fixes); this is its technical companion — secrets, rotation, every known failure case with
> a fix, and how to change the code safely.
>
> **Read order for a cold start:** `HANDOFF.md` §1–§6 (state + constraints + do-NOT-touch) → this
> file → `WORKLOG.md` (the full "why" behind any decision) → `NEXT_STEPS_SPEC.md §5` (deploy).

---

## 1. Mental model in 60 seconds

Four entry points, all Python, all scheduled via `run_*.bat` wrappers → Task Scheduler:

- `digest.py` — the morning job. Fetches ~17 sources, builds a 2-pass Opus prompt, generates a
  **full** and a **team** digest, emails both, archives raw content, indexes it into FAISS, updates
  memory, and (Fridays) sends a weekly wrap.
- `midday.py` — intraday materiality check (Sonnet); emails only if warranted.
- `reply_monitor.py` — long-running daemon; answers emailed replies to digests via RAG over the
  archive.
- `run_alert.py` — invoked by the wrappers on nonzero exit (failure alert) and by the 9 AM watchdog
  (`--check-completed`); deliberately self-contained (imports nothing that could have failed).

**Where state lives:** `archive/<date>/` (raw content per run) + `archive/index.faiss` +
`archive/chunk_metadata.json` (the search index); `memory.json` / `substack_memory.json` (evolving
storylines); `*_cache.json`, `pacer_seen.json`, `source_counts.json` (per-source caches/state);
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
| `thirteen_d_session.json` | Playwright storage state | jared's 13D account | Expires in **weeks–months**. Manual re-login only (§4). |
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

**13D / WILTW missing.** The 13D session expired (no auto-renewal — interactive login only). The
digest skips WILTW gracefully. **Fix:** on the server, `.venv\Scripts\python.exe thirteen_d.py
--login`, log into client.13d.com in the browser that opens, press ENTER in the terminal.

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
re-creation watch, `NEXT_STEPS_SPEC.md §5`), the revert lever is named in
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
| When you touch the project | Add a few golden-set questions for new archive days, incl. cross-day ones (`NEXT_STEPS_SPEC.md §F3`) — the eval only stays meaningful if it compounds. |
| At ~30–50k index vectors, or when replies feel slow | Work the index-growth ladder: (1) vectorized subset scan ✅ done → (2) date-windowed retrieval default → (3) prune old days from the live index → (4) IVF. Detail in `HANDOFF.md §5`. |
| Post-deploy | Off-box backups of `archive/`, `memory.json`, `substack_memory.json`, the two index files, state JSONs, `digests/`. |

---

## 6. Changing the code safely

- **Read `HANDOFF.md §6` first.** Several blunt-looking pieces are intentional and load-bearing
  (the module-level argv parse, the conservative PDF cleaner, Opus-written §9, the reply daemon
  loop, the parked rerank/hybrid mechanisms, `IndexFlatIP`). Don't "fix" them.
- **Cost discipline (`HANDOFF.md §8`).** Prefer unit tests. When a Claude-calling path must run, run
  **once** on a **small** input, **with permission**, and route all email to a test address — never
  the production recipients, never a loop. `count_tokens` calls are free. Substack/13D scraping is
  free to test (flat subscriptions, no Claude call — except 13D's embedded summary).
- **The gate:** `check.bat` = `ruff check` + `pytest` (336 tests). Both must pass before commit.
- **The eval harness:** `tools/eval_retrieval.py` + `tools/eval_golden.json` measure retrieval
  quality (current baseline: hit@1 0.897 / hit@3 1.0 / MRR 0.937, zero misses,
  `tools/eval_results/2026-07-15_post_index_filter.json`). Re-run and compare after any change to
  chunking, embedding, indexing, or the reply path. Rebuild the index with `python search.py
  --rebuild` after extraction/chunking changes.
- **Module convention:** source fetchers expose `fetch_X()` / `format_X_for_prompt()` /
  `build_X_html()`. A new source is one module in that shape plus a row in `digest.py`'s fetch
  registry (pinned by `tests/test_source_registry.py` / `test_digest_prompt.py`).
- **Commits:** work on a branch, not `main`. Keep the WORKLOG habit — a dated entry explaining what
  changed and *why* is how the next person (or you, in six months) stays oriented.

---

## 7. If you're stuck

Everything needed to pick this up cold is in the repo. Start with `HANDOFF.md §1`, then the
`WORKLOG.md` entry for whatever you're touching (it records the reasoning, the alternatives
considered, and what was measured). The git history is the complete record. Nothing about this
system lives only in someone's head — which is the whole point of these docs.
