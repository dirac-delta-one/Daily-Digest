# Daily Digest — Summary of Changes (the `ava-updates` branch)

> A plain-English record of what changed on the `ava-updates` branch, for the project owner.
> Baseline = the original pipeline on `main` (`2de36d2`, "Daily Digest system — full pipeline",
> 2026-04-05). The branch is **75 commits, +12,898 / −2,243 lines**, spanning 2026-06-19 →
> 2026-07-15. The full dated narrative behind every claim here lives in `WORKLOG.md`; the
> technical state is in `HANDOFF.md`.

---

## The headline

The original was a **working pipeline that ran on one person's PC** — it fetched sources,
summarized them with Claude, and emailed a digest. It had no tests, no cost visibility, no failure
alerting, and would hang or silently drop data on the failure modes a real server hits.

The branch turns that into a **deployable, observable, self-maintaining service** with a full test
suite, cost accounting, automatic failure/degradation alerts, a smarter memory + retrieval layer, a
second (team-safe) digest variant, and a documented server-deploy path. It is now **code-complete
and validated in live runs** — the only remaining work is installing it on the dedicated server.

| | Original (`main`) | Now (`ava-updates`) |
|---|---|---|
| Automated tests | 0 | **336** (green) |
| Cost visibility | none (and the built-in estimate used stale, wrong pricing) | per-call accounting on every run + expected-burn baseline |
| Failure handling | silent — a broken source or dead token produced an empty section or a hang | fail-fast + email alerts (run failed / run missing / source degraded) |
| Retrieval quality (measured) | not measured (no eval harness existed) | eval harness + 29-question golden set; **hit@1 0.897 / hit@3 1.0 / MRR 0.937, zero misses** |
| Machine binding | hardcoded to `C:\Users\jared\…` | fully relative (`%~dp0`); location- and account-independent |
| Digest variants | 1 | 2 (a full version + a Substack-free team version) |
| Deploy readiness | manual, interactive-only | unattended server provisioning script + deploy checklist + runbooks |

---

## 1. Reliability & observability (the biggest practical win)

The original had no way to know when it broke. A week of scheduled runs on a laptop surfaced ~8
distinct failure modes; all are now handled in code:

- **Failure alerting** — any crashed run emails a red alert with the last 40 log lines.
- **Hung-run watchdog** — a 9 AM check emails if the morning digest never completed (catches
  machine-asleep / network-down / login-prompt-blocking cases the failure alert can't).
- **Silent-degradation monitor** — per-source item counts are tracked; a normally-populated source
  that goes to zero for 3 straight runs raises an in-digest alert (catches an expired Substack
  cookie or dead 13D session that the "never crash" design would otherwise swallow).
- **Unattended-consent guard** — a dead Gmail token now fails fast with an alert instead of hanging
  forever on a browser login prompt (the original's worst unattended failure).
- **Durable state** — court-filing "already seen" state is now committed only *after* a successful
  send, so a mid-run crash re-surfaces entries next run instead of silently losing them.
- **Log rotation** — dated logs with a 30-day cleanup (were append-only and unbounded).

## 2. Cost

The original had **no cost tracking** and its only cost estimate used stale pricing ($15/$75 per
million tokens — off by 3×). Now every run prints a per-call breakdown, and several measured
optimizations landed:

- **Cross-digest memory moved to a cheaper model** with near-identical output.
- **Weekly-report summary cache** — stops re-summarizing the same 13D weekly PDF 4–6× per week
  (**~$130–150/year saved**, zero quality impact).
- **Two-pass prompt caching** — the two Opus passes now share a cached source prefix
  (~$0.10/run on text days, up to ~$0.54/run on PDF-heavy days).
- **A model A/B test** (run under permission) confirmed keeping the marquee calls on the top model
  was the right quality call, rather than cutting corners to save pennies.

**Measured result:** live runs cost **~$1.47–$1.58** each; expected steady-state burn is roughly
**$45–55/month** for the *entire* system (two digest variants + Friday wraps + answered reply
questions). The memory layer's own rewrite is a clean before/after: **$0.274 → $0.098 per update,
a 64% reduction** (see §3).

## 3. Memory & retrieval layer

The "memory" is the system's evolving understanding of ongoing stories, injected into each day's
prompt and used to answer follow-up questions. The original rewrote the entire memory every day —
which was expensive **and** lossy (it was caught silently dropping a tracked story and merging three
others in a single day).

- **New story-timeline memory** — updates are now incremental (per-story dated history) instead of
  wholesale rewrites: **64% cheaper** *and* it can no longer silently drop stories.
- **Evaluation harness + golden question set** — retrieval quality is now *measured*, not assumed.
  Two "best-practice" upgrades (a reranker and hybrid search) were built, **measured, and rejected**
  because the data showed they made results worse — a decision made on evidence, not vibes.
- **Smarter reply answers** — question-driven entity/date filtering, same-day-digest exclusion, and
  near-duplicate removal. Final retrieval quality: **hit@1 0.897 / hit@3 1.0 / MRR 0.937, zero
  misses.**

## 4. Speed / efficiency

- **Parallel source fetching** — the ~14 independent web fetches now run concurrently: that phase
  went from **~21s to ~7s (3×)**.
- **Re-indexing without re-embedding** — re-processing a day now reuses stored vectors instead of
  recomputing everything: the retained-content step went from **~209s to ~0.01s** (a full-day
  re-index ~245s → ~36s), and the win grows as the archive grows.

## 5. New capabilities

- **Two digest variants** — a **full** version (with your personal Substack subscriptions) for you,
  and a **Substack-free team version** for colleagues, generated efficiently as a shared cache
  prefix. The team version is the one indexed for the Q&A bot, so teammates' questions can never
  surface your personal Substack content. A privacy guard freezes indexing/memory if the team
  recipient list is ever misconfigured.
- **Forwarded-email attribution** — when research is forwarded in, the system now reads the
  forwarded body and recovers the *original* sender, so the digest and the Q&A bot cite "Bloomberg"
  or "FT" instead of "an internal email."
- **Substack auto-renewal** — the login now renews itself via the one-time code Substack emails
  (read from the inbox), instead of needing a manual cookie paste. (An expired-session drill proved
  the original renewal path had never actually worked.)
- **Q&A storyline router** — reply questions are matched against tracked storylines for better
  context.

## 6. Source coverage changes

- **Substack expanded 11 → 17 publications** after a full account audit (7 unfetched paid pubs
  added, one dead subscription removed).
- **FRED macro + Fed balance-sheet** provisioned and corrected (the original had mislabeled data
  series that were wrong by orders of magnitude).
- **Octus and FINRA TRACE removed** — Octus per owner directive (its stale login would also have
  blocked unattended runs); TRACE because the module had never actually worked and the real data
  costs ~$9k/year for a two-issuer watchlist. Both losses were reviewed and accepted, with the
  practical coverage confirmed to arrive via forwarded broker notes.

## 7. Code quality & testing

- **0 → 336 automated tests**; linting (`ruff`) clean; a one-command `check.bat` gate.
- **Two full cleanup passes** — dead code removed, duplicated logic consolidated into shared
  helpers, machine-specific hardcodes eliminated, HTML-injection escaping added, a data-integrity
  bug fixed (**79 duplicate chunk IDs across 208 chunks → 0**, which had been silently dropping
  distinct content from Q&A answers).
- **PDF-extraction reviewed and corrected** — the original's aggressive "cleanup" rules were
  measured to be the *source* of corruption (gluing real words together in 99% of PDF chunks); they
  were trimmed and the index rebuilt clean.

## 8. Deployment readiness

- **Machine-independent** — every path is relative; recipients and identity are configuration.
- **Unattended provisioning** — a PowerShell script registers all four scheduled tasks with the
  wake/network/run-whether-logged-on settings a headless server needs (the original's setup couldn't
  produce a survivable unattended task).
- **Durable Gmail auth** — the OAuth app was published to production and a non-expiring token minted
  (the original's token would have died weekly under unattended operation).
- **Documentation** — a deploy + cutover checklist, a non-technical operator runbook, and a
  developer maintenance guide (see the other new docs).

---

## What's left

**Deploy to the dedicated always-on server** — the project's definition of "done." Everything else
is complete and validated. The step-by-step is in `NEXT_STEPS_SPEC.md §5`; the ongoing-maintenance
guide is `MAINTENANCE.md`; the day-to-day operator runbook is `OPERATIONS.md`.
