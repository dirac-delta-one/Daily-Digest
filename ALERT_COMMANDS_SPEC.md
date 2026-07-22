# ALERT_COMMANDS_SPEC — Email-managed alerts & watchlist

> Users (jared + team) manage the thematic alerts and the SEC watchlist by **replying to any
> digest email** in plain English. The reply monitor classifies each reply as a command or a
> question, applies commands to state files, and sends a confirmation reply. Timed items
> ("for the next two weeks watch for X") expire automatically with a one-line notice in the
> digest. No code or config edits needed by the post-handoff operator.
>
> Decisions locked with the operator 2026-07-22: reply-to-digest channel only; any digest
> recipient is authorized; natural-language parsing (Sonnet) with a confirmation reply;
> expiry = note in digest, then drop.

---

## 0. Why the reply channel (the contamination fix)

Alert-command emails must never appear in the digest body as a source. Replies to the digest
carry `DIGEST_SUBJECT_PREFIX` in their subject, and `config.is_self_artifact()` already
excludes such mail from digest ingestion at **fetch time** (`digest.py` fetch loop) and
**index time** (`search._chunks_for_date`) — live-tested defense in depth. Riding this
channel means **zero new exclusion logic** and zero risk to auto-forwarded research (forwards
don't carry the digest subject). A fresh-email keyword channel was considered and rejected
(needs a new fetch guard; rating-agency subjects legitimately start with "ALERT:").

Authorization also comes free: `reply_monitor._reply_query()` already restricts pollable
senders to exactly `FULL_ACCESS_SENDERS ∪ DIGEST_RECIPIENTS ∪ TEAM_RECIPIENTS` — the agreed
"any digest recipient" audience. No separate auth check is needed (a defensive
`if not asker: skip` stays in the command path).

---

## 1. State files

Both live in the repo root next to the other state JSONs, are **gitignored**, backed up by
O4, and written atomically (write `<name>.tmp`, then `os.replace`). Managed by the new
`alert_commands.py` module — no other module writes them.

### 1a. `alerts_config.json` (existing file, becomes runtime state)

Extends the current schema — existing keys unchanged so `alerts._build_alert_prompt` and its
tests are untouched. New optional per-alert keys:

```json
{
  "alerts": [
    {
      "name": "Large Chapter 11",
      "trigger": "Any new Chapter 11 bankruptcy filing with over $500M in liabilities",
      "priority": "high",
      "expires": null,                 // ISO date; active while today <= expires; null = permanent
      "added_by": "seed",              // email of requester, or "seed" for defaults
      "added_on": "2026-07-22"
    }
  ]
}
```

**Migration footgun (must be handled):** the file is currently **git-tracked**. Committing
its removal (`git rm --cached` + `.gitignore`) makes the server's `git pull` **delete the
working-tree copy**. Fix: `alert_commands.py` carries `DEFAULT_ALERTS` (byte-equivalent to
the current 7 alerts, plus the new metadata keys) and **seeds the file on first load when
missing**. Since the server's copy equals the tracked defaults today, deletion + reseed is
lossless. Same seed-on-missing pattern for `watchlist.json`.

### 1b. `watchlist.json` (new — replaces the hardcoded list in `sec_filings.py`)

```json
{
  "tickers": [
    {"ticker": "PGY", "name": "Pagaya Technologies", "expires": null,
     "added_by": "seed", "added_on": "2026-07-22"}
  ]
}
```

Seeded from `DEFAULT_WATCHLIST` = the current 16 tickers + their comment names
(sec_filings.py lines 33–50). Tickers are stored/compared uppercase.

---

## 2. New module: `alert_commands.py`

Imports only stdlib + `config` + `claude_utils` + `cost` + `anthropic` (no imports of
`digest`/`alerts`/`sec_filings`/`reply_monitor` — it sits below all of them, so every
consumer can import it without cycles).

Exposes module-level `ALERTS_FILE` / `WATCHLIST_FILE` Path constants — the monkeypatch seam
for tests (mirrors `alerts.ALERTS_CONFIG_FILE`, which retires: `alert_commands` becomes the
single owner of the path).

### Loaders (no Claude, no network)

- `load_alerts()` → list of **active** alert dicts (expired filtered out). Seeds defaults if
  the file is missing/unreadable. `alerts._load_alerts_config` delegates to this.
- `load_watchlist()` → list of active ticker strings (uppercase, insertion order preserved).
  Seeds defaults if missing. `sec_filings.WATCHLIST` is built from this at import time.
- `watchlist_names()` → {ticker: name} for entries that have names (available to
  confirmation rendering; NOT wired into the ticker-glossary path in this spec).
- `consume_expired(today=None)` → list of human-readable notice strings for entries (alerts
  and tickers) whose `expires` < today, **removing them from the files** as it returns them.
  Called once per digest run; the remove-on-read gives exactly-one-notice semantics with no
  "notified" flag. Returns `[]` and removes nothing when nothing expired.
- `expiring_today(today=None)` → advance-warning strings for entries whose LAST active day is
  today (`expires == today`), read-only (added 2026-07-22 after the initial build). Renders in
  the digest as "Watch item expiring … reply to renew it now", one day before the expired
  notice — the once-daily digest run makes it fire exactly once.

Note the two horizons: `load_*` treats `today > expires` as inactive (so an expired-but-not-
yet-consumed entry can never fire an alert or a fetch), while `consume_expired` is what
physically prunes and produces the notice.

### Command handling (one Sonnet call per reply email)

- `classify_and_parse(reply_text, today=None)` → dict per the schema below. The prompt
  includes: today's date (for "next two weeks" → absolute ISO), the current active alert
  names, and the current watchlist tickers (so remove/extend targets ground against real
  entries — the model returns the EXACT existing name/ticker it matched, or leaves the
  action out and explains in `clarification`).

  Structured output schema (via `claude_utils.json_schema_output`):

  ```json
  {
    "actions": [
      {"action": "add_alert",     "name": "...", "trigger": "...", "priority": "high|medium|low", "expires": "YYYY-MM-DD|null"},
      {"action": "remove_alert",  "name": "<exact existing name>"},
      {"action": "update_expiry", "kind": "alert|ticker", "target": "<exact existing name or ticker>", "expires": "YYYY-MM-DD|null"},
      {"action": "add_ticker",    "ticker": "ABC", "name": "Company Name|null", "expires": "YYYY-MM-DD|null"},
      {"action": "remove_ticker", "ticker": "<exact existing ticker>"},
      {"action": "list_config"}
    ],
    "question": "string|null",      // any genuine archive question ALSO present in the reply
    "clarification": "string|null"  // set when the user clearly wanted a command but it couldn't be parsed safely
  }
  ```

  `actions=[]`, `question=null`, `clarification=null` ⇒ not a command; the reply proceeds to
  Q&A exactly as today. Model: `SONNET_MODEL`; recorded as `cost.record("alert command-parse", …)`.
  For add_alert the model generates a short 2–4-word `name` (like the existing seven).

- `apply_actions(actions, asker, today=None)` → `(results, changed)` where `results` is a
  list of per-action outcome strings ("Added alert …, expires 2026-08-05", "Removed CRWV
  from watchlist", "No alert named 'X' — active alerts: …") and `changed` is bool.
  Deterministic; failures (unknown target, duplicate ticker, malformed date) become polite
  outcome strings, never exceptions. `list_config` renders the full current state (alerts
  with priority/expiry, watchlist with names/expiry) into the results.
- `build_confirmation_html(results)` → digest-styled HTML (Georgia/680px, like
  `answer_question`'s wrapper) listing what changed, with a one-line footer teaching the
  feature ("Reply to any digest to add/remove alerts or watchlist tickers…").

### Concurrency

Two processes touch these files: the reply monitor (writer, on command) and the digest run
(reader at fetch/eval; writer only in `consume_expired`). Atomic replace keeps every read
consistent. The remaining race — a command landing inside the digest's read-modify-write in
`consume_expired` — is a sub-second window once per day; accepted (same posture as the other
state files). No file locking.

---

## 3. Integration points (every touched file)

| File | Change |
|---|---|
| `alert_commands.py` | NEW — everything in §2. |
| `reply_monitor.py` | New helper `_handle_command(question, asker)` → `None` (not a command — including on `classify_and_parse` exception, so failures fall through to today's Q&A path) or `(confirmation_html, leftover_question)`. `process_replies` calls it after `cost.reset()` (moved up so the parse call lands in the per-reply cost summary) and before `answer_question`: command-only → send confirmation; command + leftover question → `answer_question` HTML appended below the confirmation (one combined reply, one send); clarification-only → `(clarification_html, None)`. Command replies count toward the rate limit (they send mail). The helper is the unit-test seam (§6.6). |
| `alerts.py` | `_load_alerts_config()` body → `return alert_commands.load_alerts()`. Everything else (schema, prompt, eval) unchanged. |
| `sec_filings.py` | Delete the hardcoded list; `WATCHLIST = alert_commands.load_watchlist()` at module level (same name, same list-of-str shape — `earnings.EARNINGS_WATCHLIST is sec_filings.WATCHLIST` identity test stays green). The `DEFAULT_WATCHLIST` ticker+name pairs move to `alert_commands.py`. Also update the two operator-facing "Edit the WATCHLIST in sec_filings.py" messages (empty-watchlist branches, lines ~258/305) to say "add tickers by replying to a digest (or edit watchlist.json)". |
| `tests/conftest.py` | NEW — autouse fixture insulating the suite from live mutable state: pin `sec_filings.WATCHLIST[:]` to the canonical default tickers (in-place, preserving the earnings identity), reset `search._entity_lexicon_cache = None`, and point `alert_commands.ALERTS_FILE`/`WATCHLIST_FILE` at a tmp dir. Without this, `test_search.py:208/219`, `test_memory.py:71/243`, and `test_reply_monitor.py:85` (all assume MSTR/MAIN are watchlist entities) would break the day a user emails "stop watching MSTR" — and stray tests could read/write the real state files. |
| `digest.py` | In the deterministic-signals block (with the Fed-stress / content-monitor siblings, immediately BEFORE `triggered_alerts.extend(deterministic_alerts)` at ~line 1716): `for notice in alert_commands.consume_expired(): deterministic_alerts.append({"name": "Watch item expired", "detail": notice + " Reply to this digest to renew.", "source": "alert commands"})` — rides the existing path into BOTH variants' alert boxes, wrapped in try/except like its siblings. |
| `.gitignore` | Add `alerts_config.json`, `watchlist.json`. |
| git index | `git rm --cached alerts_config.json` (seed-on-missing covers the server's pull-deletion — §1a). |
| `run_backup.bat` | Add `alerts_config.json watchlist.json` to the explicit top-level state-file robocopy list. *(Ride-along while touching this line: add `repetition_scores.json`, added 2026-07-22 but missing from the backup list — it drives the Bundle 2 decision and is irreplaceable. `ticker_names_cache.json` stays un-backed-up deliberately: it self-seeds.)* |
| `OPERATIONS.md` | New user-facing section: how to manage alerts/watchlist by replying to a digest, with example phrasings and what the confirmation looks like. |
| `MAINTENANCE.md` | Note the two state files, seed-on-missing behavior, and where defaults live. |
| `HANDOFF.md` / `WORKLOG.md` | Update after build (state list §4, alerts description, dated worklog entry). |

**Staleness note (accepted):** the digest run is a fresh process every morning, so it always
sees current state. The long-running reply monitor imports `sec_filings.WATCHLIST` only
indirectly via `search.extract_entities`' lazily-cached entity lexicon — a watchlist edit
reaches the reply bot's entity tagging after its next restart. Harmless (retrieval filter
breadth only); not worth cache invalidation.

---

## 4. Command examples (the contract the parse prompt encodes)

| User writes (reply to digest) | Parsed |
|---|---|
| "For the next two weeks watch for anything on Argentina sovereign debt" | add_alert, trigger="Any news on Argentina sovereign debt", expires=today+14 |
| "Until July 28th, look at YYY" | add_alert, expires=2026-07-28 |
| "Add CRWV to the watchlist" / "start watching CoreWeave (CRWV)" | add_ticker CRWV |
| "Watch WOLF through earnings, say until Aug 10" | add_ticker WOLF, expires=2026-08-10 |
| "Stop watching MSTR" | remove_ticker MSTR |
| "Drop the insider selling alert" | remove_alert "Insider selling" (grounded against real names) |
| "Extend the Argentina alert to end of August" | update_expiry alert → 2026-08-31 |
| "What alerts are set up right now?" | list_config |
| "Remove the alert about banks" (two bank-ish alerts exist) | actions=[], clarification names both candidates |
| "What did Grant's say about Wynn?" | actions=[], question set → normal Q&A |

Expiry semantics: **active through the `expires` date inclusive**; the first digest run
after it shows the one-line expiry notice and the entry is gone.

---

## 5. Failure modes

- **Sonnet parse call fails** → fall through to the Q&A path (a command email then gets a
  best-effort Q&A answer or "couldn't identify a question"; nothing is half-applied).
- **State file unreadable/corrupt JSON** → `load_*` logs, reseeds from defaults? **No** —
  reseeding would silently discard user edits. Corrupt file ⇒ log + return defaults
  **in-memory only** (never overwrite a corrupt file; the O4 backup holds the last good
  copy). Seed-on-disk happens only when the file is *missing*.
- **Empty watchlist after removals** → `fetch_recent_filings`/earnings already handle
  `WATCHLIST == []` (existing "no tickers" branches); alerts' watchlist clause is already
  conditional. Confirmation for the last removal appends a heads-up that SEC/earnings
  coverage is now empty.
- **Duplicate add** (ticker already present / alert name collision) → outcome string says
  so; for an alert-name collision the new alert gets a numbered suffix rather than
  overwriting.

---

## 6. Testing plan

**Free (offline, no permission needed)** — new `tests/test_alert_commands.py` +
small additions to existing test files, following the repo's tmp_path/monkeypatch patterns:

1. Seed-on-missing: `load_alerts`/`load_watchlist` on an empty dir create defaults matching
   the current 7 alerts / 16 tickers; a *corrupt* file is left untouched on disk.
2. Expiry filtering: entry with `expires` = yesterday excluded from `load_*`; = today
   included.
3. `consume_expired`: yesterday-expired entry → one notice + removed from file; second call
   → `[]`; today-expiring entry → untouched.
4. `apply_actions`: add/remove/update_expiry/list for both kinds; unknown-target and
   duplicate outcomes; file round-trip; atomic tmp file cleaned up.
5. Parse-prompt construction (no Claude): today's date, existing names, and tickers all
   appear in the prompt string.
6. `reply_monitor._handle_command` with a monkeypatched `alert_commands.classify_and_parse`:
   actions → (confirmation, None); actions+question → (confirmation, leftover);
   clarification-only → (clarification html, None); empty parse → None; parse exception →
   None. (The Gmail-service side of `process_replies` stays untested, as today.)
7. Identity/shape guards stay green: `earnings.EARNINGS_WATCHLIST is sec_filings.WATCHLIST`;
   `alerts._build_alert_prompt` tests unchanged.
8. `digest` expiry-notice wiring: with a stubbed `consume_expired` returning a notice, the
   deterministic alert appears (unit-level, mirroring the Fed-stress test if one exists).

**Permissioned (one live test, ~$0.01, needs explicit go-ahead):** run
`classify_and_parse` once against 3–4 real phrasings (a timed add, a remove, a question) and
eyeball the parses — the only Claude-touching seam. The full email round-trip (reply to a
real digest → confirmation lands) rides the next natural digest day with the operator
watching; it exercises no new Claude paths beyond the parse call already tested.

---

## 7. Out of scope (named so they aren't accidentally built)

- Fresh-email keyword channel (rejected — §0).
- Per-user alert lists — the list is shared; anyone authorized can remove anything.
- Editing an alert's *trigger text* in place (model as remove + add).
- Wiring `watchlist_names()` into the ticker-glossary/prompt path.
- Entity-lexicon cache invalidation in the running reply monitor (§3 staleness note).
- Bot-initiated expiry emails (digest notice only, per decision).
- Any change to `evaluate_alerts`' prompt or the §6 do-not-touch items.

## 8. Build order

1. `alert_commands.py` + tests (loaders, expiry, apply, prompt build).
2. `sec_filings.py` / `alerts.py` delegation + identity tests.
3. `reply_monitor.py` routing + tests.
4. `digest.py` expiry notices + test.
5. `.gitignore` + `git rm --cached` + `run_backup.bat`.
6. Docs (OPERATIONS, MAINTENANCE, HANDOFF, WORKLOG).
7. `check.bat` (ruff + full pytest) green; then the permissioned parse spot-check.

---
---

# PART II — Per-user thematic alerts (design locked 2026-07-22)

> Every thematic alert belongs to exactly ONE user; the SEC watchlist stays fully shared.
> Each digest recipient gets a personalized alert box over an otherwise identical digest.
> Operator-locked decisions: no shared alert baseline; owner-only visibility/editing/listing;
> current 7 alerts migrate to two independent copies (jtramontano@acorninv.com +
> acohen@acorninv.com — "ava" = acohen); apain and ALL future onboarded users start with zero
> thematic alerts; onboarding = add the address to DIGEST_TO_TEAM, everything else self-serve
> by reply; orphaned alerts (owner no longer a recipient) are skipped at eval with a one-time
> ops-email note.

## 9. Data model & migration

`alerts_config.json` entries gain `"owner": "<email, lowercase>"`. Watchlist entries get NO
owner — shared is the whole point.

**Legacy migration (idempotent, in the loader):** any alert entry WITHOUT an `owner` key is
legacy. On the first load that finds one, the payload is migrated in memory — each ownerless
entry is replaced by one copy per `LEGACY_ALERT_OWNERS = ["jtramontano@acorninv.com",
"acohen@acorninv.com"]` — and persisted once (atomic write; skipped if the file is corrupt →
in-memory only, same posture as Part I). This transparently migrates BOTH the dev and server
files on their next run, and any user-added post-Part-I alerts (which also lack owners —
they're duplicated the same way, acceptable for the ~1-day-old feature). `DEFAULT_ALERTS`
becomes the 14 migrated entries (7 × 2 owners) so fresh seeds need no migration.

**Name uniqueness is per-owner** (two owners can each have "Bank failure"); remove/update
match on (owner, name).

## 10. alert_commands.py API changes

- `load_alerts(today=None, owner=None)` — `owner` filters to that owner's active alerts
  (compared lowercase); `None` returns all active (internal/eval use). Runs the §9 migration.
- `owners_with_alerts(today=None)` → set of owner emails having ≥1 active alert (orphan check).
- `classify_and_parse(reply_text, today=None, owner=None)` — the CURRENT ALERTS grounding
  block lists ONLY the owner's alerts (privacy + correct remove/extend grounding). Watchlist
  grounding unchanged (shared).
- `apply_actions(actions, asker, today=None)` — alert actions are owner-scoped to `asker`:
  add_alert stamps `owner=asker`; remove_alert / update_expiry(kind=alert) match within the
  asker's alerts only (unknown-target outcome lists the asker's names only); name-collision
  suffixing is per-owner. list_config renders the asker's alerts + the shared watchlist.
  Ticker actions unchanged (shared).
- `consume_expired(today=None)` / `expiring_today(today=None)` — return shape changes from
  `[str]` to `[{"owner": <email or None>, "notice": str}]`: alert notices carry their owner,
  watchlist notices carry `owner=None` (shared). Semantics (remove-on-read / read-only last
  active day) unchanged.
- `orphan_notices(current_recipients, today=None)` → one-time ops-email lines. Computes
  orphans = owners_with_alerts − current_recipients (lowercased), diffs against
  `payload["_meta"]["known_orphans"]`, persists the updated meta list (add new, drop
  re-recipiented), and returns a notice string per NEW orphan ("N alert(s) owned by X are
  paused — X no longer receives the digest."). Evaluation skip needs no state: the digest only
  evaluates current recipients' alerts by construction.
- Confirmation footer wording: "alerts are personal to you; the watchlist is shared."

## 11. alerts.py — batched per-owner evaluation

- `evaluate_alerts(source_text, watchlist=None, alerts=None)` — gains the optional explicit
  `alerts` list (the batcher passes eval units); `None` keeps loading all active (standalone
  `__main__` behavior).
- NEW `evaluate_owner_alerts(source_text, owner_alerts, watchlist=None)` →
  `{owner: [triggered]}`. Mechanics:
  1. Collect eval UNITS: dedupe identical `(name.lower(), trigger)` across owners (the
     migrated 7×2 collapse back to 7 units — cost stays flat as users onboard).
  2. Name collisions with DIFFERENT triggers get a disambiguated eval name ("Bank failure
     ~2") so the model's name-keyed results can't merge them; the mapping restores each
     owner's real alert name in the fan-out.
  3. ONE `evaluate_alerts(..., alerts=units)` call per invocation; empty union → no call,
     empty dict.
  4. Fan out: each triggered unit's result is copied to every (owner, alert) behind it.
- digest calls it once per tier: FULL recipients' alerts vs `source_text`, TEAM recipients'
  alerts vs `team_source_text` — still ≤2 Claude calls per run regardless of user count.
  FULL/TEAM privacy invariant preserved: a team user's alert detail can never quote Substack.

## 12. digest.py — per-recipient assembly & send

- **Evaluation:** `full_results = evaluate_owner_alerts(source_text, {r: load_alerts(owner=r)
  for r in DIGEST_RECIPIENTS}, WATCHLIST)`; same for TEAM (team_source_text, TEAM_RECIPIENTS)
  when team is active. Owners with zero alerts contribute nothing.
- **Expiry routing:** shared notices (`owner=None`, i.e. watchlist) render in EVERY box and
  the neutral base; owned alert notices render only in that owner's box (and nowhere if the
  owner isn't a recipient — the entry still expires/prunes silently).
- **Boxes:** per-recipient box = `build_alerts_html(own_triggered + deterministic_alerts,
  shared_expiry + own_expiry)`. **Neutral base box** = `build_alerts_html(
  deterministic_alerts, shared_expiry)` — deterministic content signals (Fed stress) are for
  everyone.
- **Neutral base html is the canonical artifact:** `save_daily_digest` (weekly-wrap inputs),
  the archive, the index, and the memory update all consume the neutral-base assembly of
  their variant — personal boxes exist ONLY in sent emails. (Index/memory already use the
  TEAM variant; this just fixes WHICH box that variant carries.)
- **Send loop:** one email per recipient, personalized box, same subject per variant. A
  per-recipient send failure is caught and logged, remaining recipients still send, and the
  run raises at the end if any send failed (so run_alert's failure email fires). commit_seen
  runs only if ALL sends succeeded (conservative: a partial failure re-surfaces PACER entries
  rather than losing them for the failed recipient — same all-or-nothing as today).
- **Ops email:** append `orphan_notices(DIGEST_RECIPIENTS + TEAM_RECIPIENTS)` output.
- **Dev-test behavior:** `DIGEST_TO=acohen` override → the FULL box carries acohen's alerts —
  correct and useful for testing.

## 13. reply_monitor.py

`_handle_command` passes `owner=asker` to `classify_and_parse`. Everything else unchanged
(auth, tiering, rate limit, combined replies).

## 14. Limitations (operator-stated, recorded so they aren't attempted)

- **No forwarding, no attachments.** The command channel reads ONLY the typed top-of-reply
  text (`_extract_question` stops at quote markers); forwarded email bodies below the reply
  and attachments of any kind are never parsed for commands. Creating alerts from forwarded
  research or attached files is out of scope — commands are plain typed sentences.
- Per-user SEC watchlists: explicitly rejected — shared forever.
- Cross-user alert visibility (labeled listing): rejected — own-only everywhere.
- Seeding new users with starter alerts: rejected — start empty, self-serve.

## 15. Tests (all offline unless marked)

1. Migration: legacy 7-entry file → 14 owned entries, persisted once, idempotent on reload;
   corrupt file still never written.
2. Owner scoping: load_alerts(owner=…) filters; apply_actions add stamps asker; remove/update
   can't touch another owner's alert (unknown-target outcome lists own names only);
   list_config shows own alerts + shared watchlist; per-owner name-collision suffix.
3. classify_and_parse grounding: prompt contains the owner's alert names, NOT another
   owner's.
4. evaluate_owner_alerts (Claude call mocked): identical-alert dedupe → 1 unit, result fans
   out to both owners; name-collision-different-trigger → 2 disambiguated units mapped back;
   empty union → no call.
5. Expiry routing: owned alert notice → owner's box only; watchlist notice → all boxes +
   neutral base; consume/expiring return the new dict shape.
6. Orphan notices: first run after an owner leaves recipients → one notice; second run →
   none; owner re-added → meta cleared (a later re-orphaning notices again).
7. digest harness: two TEAM recipients → two team sends with DIFFERENT boxes (each sees own
   alert, not the other's); saved/indexed/memory html = neutral base (no personal alerts);
   partial send failure → remaining sends attempted, run raises, commit_seen NOT called.
8. reply_monitor: owner passed through to classify_and_parse.
9. **Live (small, step-5):** one classify_and_parse with owner grounding (~$0.005) + one
   evaluate_owner_alerts against a ~1-page synthetic source (~$0.02–0.05) validating real
   fan-out. NO full digest run without separate explicit permission.

## 16. Build order

1. alert_commands: schema/migration/owner scoping + tests.
2. alerts.py: evaluate_owner_alerts + tests.
3. digest.py: eval wiring, expiry routing, neutral base, send loop + harness tests.
4. reply_monitor + test.
5. Docs (OPERATIONS wording, HANDOFF, WORKLOG, MAINTENANCE).
6. ruff + pytest; live spot-checks.

## 17. Part-II validation-pass findings (2026-07-22, pre-build)

Verified against the code; corrections folded into the plan:

1. **Neutral-base cascade confirmed:** `final_html`/`team_final_html` are the single artifacts
   feeding repetition scoring, save_daily_digest, archive (digest_html/digest_team_html
   kwargs), the index (reads the archive), and update_memory — so building THEM as the
   neutral base covers all five consumers in one move. Repetition scores therefore rate the
   neutral base (stable/deterministic — an improvement, personal boxes would have made
   scores owner-dependent).
2. **Case: recipient env values are not normalized** (`_recipients_from_env` strips only).
   All owner comparisons lowercase both sides; owner keys in results dicts are lowercase.
3. **Harness impact:** test_digest_main's fixture stubs `digest.evaluate_alerts` — it must
   stub `digest.evaluate_owner_alerts` instead, and the `["SRC", "SRC (team)"]` assertions
   change shape (record source + owner map keys).
4. **Part-I tests written against the global-alert world need updating with the migration:**
   seed count 7 → 14 (owned copies); name-collision suffix is now per-owner (adding "Bank
   failure" as a NEW user no longer collides); list_config shows the asker's alerts only;
   remove-unknown outcome lists own names only.
5. **Orphan notices ride the existing ops_alerts list** (built in the deterministic-signals
   block → the ⚙️ email), as `{"name": "Paused alerts", …}` entries — no new send path.
