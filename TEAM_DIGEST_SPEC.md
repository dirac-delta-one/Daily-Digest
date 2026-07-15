# Team Digest Spec — Substack becomes jared-personal

> Status: **BUILT 2026-07-13 (Stages 1–4; operator-approved same day) + post-build
> spec audit PASSED** (found/fixed: midday dual-list send; the full-variant alert
> window carve — alerts.py's 50k cap would otherwise blind jared's alert box to
> the tail-positioned Substack; story-context cap; save isolation).
> `ruff` clean, `pytest` 238 → **277**; free verifications green (retrieval eval
> metric-identical 0.846/1.0/0.904; team-asker exclusions verified on the live
> index). **ALL THREE PAID VALIDATIONS PASSED 2026-07-13 ($1.81 — WORKLOG entry):**
> substack-memory delta ($0.045, store seeded); reply A/B at both tiers ($0.23,
> full cites Junk Bond Investor, team zero substack citations); digest structure
> A/B ($1.53) — cross-variant cache hit exactly as designed (full pass 1 read the
> team-written 28,403-token prefix, wrote only the 7,311-token substack tail;
> full 2-pass $0.41 vs $0.57 old = net SAVING), old-vs-new output equivalence
> PASS with Substack integration undiminished, team render PASS. The A/B also
> live-proved the pre-cleanse memory leak into a team digest — the Stage-5
> cleanse is load-bearing, and main() now warns loudly if team generation runs
> with TEAM_ACTIVATION_DATE unset.
> **Stage 5 ACTIVATED 2026-07-13 (pilot: acohen on `DIGEST_TO_TEAM`).**
> Done: env var set; `TEAM_ACTIVATION_DATE = "2026-07-13"`; memory cleanse
> applied (52 → 32 shared stories; 20 substack-sourced stories migrated,
> shared context verified marker-clean; backups `*_prestage5.bak`); the
> shared substack heuristic upgraded to word-level matching ("Krugman
> Substack" class of misses); reply allow-list + Abnormal already covered
> acohen; `substack_memory.json` gitignored.
> **✅ TRACK COMPLETE — the first activated run (2026-07-13, $1.47, GREEN)
> closed the run-day items:** sent team digest greps CLEAN (0/20 markers vs
> 10 in the full control); indexed digest chunks come from digest_team.html;
> cross-variant cache confirmed in production (full pass 1 = 36 uncached
> tokens); per-variant alerts diverged exactly as designed (a substack-
> memory-sourced alert fired only in jared's box); eval re-baselined at
> 0.846/0.962/0.897 (snapshot `2026-07-13_post_team_activation.json` — the
> one slip is a stale relative-time golden question, not a regression).
> Deploy note: the server's env.bat must carry `DIGEST_TO_TEAM` too.
>
> Written 2026-07-13; v2 same day after a consistency review against the codebase
> (changes from v1 are marked **[v2]** — the big one is §1's indexing flip, which
> closes a substack leak through digest-prose chunks). Companion to `HANDOFF.md` /
> `WORKLOG.md`.

## 0. Requirement + operator decisions (2026-07-13)

Jared's Substack subscriptions are personal, so Substack summary/analysis may only
reach him. Everyone else gets a Substack-free digest (and weekly wrap). Decisions:

- **13D WILTW stays team-wide** (only Substack is personal).
- **Complete separation** — the team variant is its own Opus generation with Substack
  absent from the source prompt (Substack is woven through TL;DR/Takeaways/Themes, so
  post-hoc stripping is impossible); the team alert box is evaluated on the team
  source text (never the full one).
- **Separate Substack memory layer** (`substack_memory.json`) rather than letting
  substack storylines live in the shared `memory.json`.
- **Reply bot: reply to the asker only** (today `send_reply` broadcasts every answer
  to all DIGEST_RECIPIENTS), and **asker-aware content access** (non-jared askers get
  substack-free answers).
- **Team recipient list is EMPTY for now** — production audience is jared only. The
  team pipeline is built and gated on a non-empty list, so it costs ~$0/day until a
  team recipient is actually added.

## 1. Architecture

Two variants of the daily digest (and Friday wrap):

| | FULL (jared) | TEAM |
|---|---|---|
| Source prompt | today's, Substack included, + substack-memory context | same minus Substack articles and substack-memory |
| Alert box | LLM eval on full source | LLM eval on team source |
| Memory feed | feeds `memory.json` **only while the team variant isn't generated** (list empty) **[v2]** | feeds `memory.json` once generated |
| Saved | `digests/<date>.html` | `digests/<date>_team.html` |
| Archived | `archive/<date>/digest.html` | `archive/<date>/digest_team.html` |
| Indexed (FAISS) | only while it's the sole variant | **yes, once generated — the team digest becomes THE indexed digest [v2]** |
| Sent to | `DIGEST_TO` (default jtramontano + bot — unchanged env semantics) | `DIGEST_TO_TEAM` (default empty ⇒ generation skipped) |
| Weekly wrap | from full dailies → full list | from team dailies → team list |

**[v2] Why the team digest gets indexed, not the full one (v1 had this backwards):**
digest chunks carry `source_type="digest"`, and the FULL digest's prose *embeds*
substack analysis — indexing it would leak substack content to team askers through
digest chunks even with `substack`-type chunks excluded. Flipping it costs jared
almost nothing: raw substack articles are indexed independently from `substacks.json`
(source_type `substack`, full text), and his storyline context comes from
`substack_memory.json` — only the substack-*woven digest prose* drops out of his
retrieval. Historical digest chunks (all pre-activation days) still contain substack
prose; §Stage-5 handles them with a date-bounded exclusion.

**Memory model:**
- `memory.json` (team/base memory) — substack-free once the team variant feeds it;
  context injected into BOTH prompts. Fed by the full digest only while the team
  variant isn't generated (exactly today's behavior), with the accumulated
  contamination cleansed at activation (Stage 5).
- `substack_memory.json` (new) — same v2 story-timeline machinery, fed daily from
  the day's Substack articles directly (not from the digest — no double-tracking of
  team stories); its context block goes ONLY into the full prompt, labeled so Opus
  keeps citing the original pubs. **[v2]** Input capped (~first 3k chars/article) —
  story deltas don't need full text, and 17 pubs uncapped could spike the call to
  ~$0.30 on heavy days. Extra cost ≈ $0.05–0.15/day.
- Known accepted trade-off: a story covered by both Substack and team sources
  develops parallel timelines in the two stores.

**Prompt-cache economics (Stage 4):** the team content (source text + inbox PDFs) is
the shared prefix; the full variant appends its extra material — substack articles
**and the substack-memory context block [v2]** — as trailing blocks after the shared
cache breakpoint (both must sit in the tail or the prefix diverges and the cache is
lost). Run order: team pass 1 (cache write) → team pass 2 (read) → full pass 1
(reads the shared prefix, writes prefix+substack) → full pass 2 (read). Extra cost
when team is live ≈ **+$0.35–0.60/day** (vs +$0.7–1.0 without prefix sharing) +
~$0.5–0.7 Fridays for the second wrap. Moving substack out of mid-prompt changes
prompt bytes for jared's variant → one permissioned output-equivalence check (the
Group-C method) before it ships.

**Midday alert:** unchanged logic — its sources (inbox, WSJ/FT, EDGAR, ratings)
contain no Substack. Sends to full + team lists combined.

**Ops details [v2]:** `pacer.commit_seen()` and the `digest_sent_at.txt` completion
marker (O2 watchdog) move to after the LAST send of the run; O3 records one set of
counts per run as today.

## 2. Stages

### Stage 1 — Recipient split (config; behavior-neutral today)
*What:* `digest.DIGEST_RECIPIENTS` keeps its name and env var (`DIGEST_TO`) as the
FULL list — **midday.py and reply_monitor.py import it by that name [v2]**, and
`run_alert.py` independently reads the same env var, so not renaming keeps every
consumer and existing test working. Add `TEAM_RECIPIENTS` (env `DIGEST_TO_TEAM`,
default empty).
*Verify:* unit tests for the new override; existing DIGEST_TO tests untouched.

### Stage 2 — Reply bot: asker-only + asker-aware access
*What:*
- **[v2]** `check_for_replies` currently does NOT capture the sender — extract the
  `From` header and carry it through the reply tuple.
- `send_reply` addresses the asker instead of broadcasting to all recipients.
- New `config.FULL_ACCESS_SENDERS` (jared's addresses + the bot) decides access
  level per asker.
- Non-full-access askers: retrieval excludes `substack`-type chunks — new
  `search(exclude_source_types=[...])` in `_filter_ids` (the §14.F parked
  source_type filter; this is its production trigger) — **plus, [v2], digest-type
  chunks dated before the team-activation date** (all pre-activation digests are
  full digests with substack woven in; the activation date lands in config at
  Stage 5). The verbatim digest context loads `digest_team.html` when it exists;
  before activation it is omitted entirely (acceptable: the only non-jared asker
  today is the operator). The storyline router skips substack-memory stories and
  (best-effort until activation) `memory.json` stories whose sources look like
  Substack pubs.
- Full-access askers: byte-identical to today.
*Verify:* unit tests (filter incl. the date bound, access routing, asker-only
addressing, From extraction); one permissioned reply validation (~$0.15) via the
Group-B isolation method.
*Open item:* acohen's access level — default spec is team-level; add acohen to
`FULL_ACCESS_SENDERS` to flip.

### Stage 3 — Substack memory layer
*What:* generalize `memory.py`'s store path (load/save/context/update take a store
param; `memory.json` behavior byte-identical — the substack store starts fresh, no
v1-migration path needed) + a substack store updated daily from the fetched articles
(capped input per §1); context block appended to the full prompt only. Until
activation, `memory.json` keeps being fed by the (only) full digest; Stage 2's
router guard covers the interim reply-bot surface.
*Verify:* unit tests (store isolation, context injection targets, v2 contract
untouched); one permissioned substack-delta run (~$0.10).

### Stage 4 — Team generation (gated on non-empty TEAM_RECIPIENTS)
*What:* when `TEAM_RECIPIENTS` is non-empty, `main()` generates the team variant
first (2-pass, team alert eval), then the full variant over the shared cache prefix;
saves/archives/sends per the §1 table (archive.py gains the `digest_team.html`
write); **`index_daily_content` indexes the team digest** and `memory.json`'s feed
switches to the team digest — both only when the team variant is generated, else
everything stays on the full digest exactly as today **[v2]**; Friday builds both
wraps (`_get_week_digests` gains a variant param; the team wrap needs ≥2 team
dailies, so the first partial week self-skips).
*Verify:* offline tests (variant routing, gating, save/archive filenames, weekly
loader variant selection); one permissioned A/B day validating output-equivalence of
the restructured full prompt + cache engagement + both variants' render (~$2–3).

### Stage 5 — Activation checklist (runs when the first team recipient is added)
One-time, operator-driven:
- Set `DIGEST_TO_TEAM`; record the activation date in config (drives the Stage-2
  date-bounded digest-chunk exclusion).
- Cleanse `memory.json`: move stories whose sources are Substack pubs into
  `substack_memory.json` — **[v2]** a *heuristic* script (story `sources` are
  model-written strings matched against pub names) + operator eyeball, not fully
  deterministic.
- **[v2]** Add the team recipients to the reply bot's `from:` allow-list (hardcoded
  in `check_for_replies`) — without this their replies are ignored entirely.
- Recipient-side Abnormal/mail-security allowlisting of the bot sender for any
  non-acorn.com recipient (the §7.2-7 runbook item; acorn.com Outlook inboxes are
  already covered).
- **[v2]** Re-run the retrieval eval and re-baseline: the indexed-digest corpus
  changes character (team digest replaces full), and several golden-set items
  accept digest-type matches.
- Confirm the first live team digest is Substack-free end-to-end (grep the sent
  HTML for the configured pub names).

## 3. Cost summary

| State | Extra cost vs today |
|---|---|
| Now (team list empty) | ~$0.05–0.15/day (substack memory delta only) |
| Team live, daily | +$0.35–0.60/day (cached team 2-pass + team alert eval ~$0.10) |
| Team live, Fridays | additional ~$0.5–0.7 (team wrap) |
| One-time validation | ~$2.50–3.50 across Stages 2–4 |

## 4. Out of scope / unchanged

Fetchers, S1 registry, O3/O2/O1, PACER logic, 13D (team-wide per decision), midday
logic, FAISS substrate, SYSTEM_PROMPT structure (only the substack source-block
placement moves, §6-adjacent and validated), run_alert.
