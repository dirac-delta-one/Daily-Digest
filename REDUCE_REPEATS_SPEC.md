# REDUCE_REPEATS_SPEC — Cross-Section Repetition Reduction

> Spec for the 15 candidate changes identified 2026-07-22 to reduce repetition
> across bullets/sections in the daily digest. Numbering matches the original
> idea list (groups A–E). **Status column below is the decision surface — mark
> Build / Skip / Later per item; nothing here is committed to until chosen.**
>
> Evidence baseline (2026-07-22, "signals" = tickers + bps/%/$ figures appearing
> in 2+ sections of one digest): Opus production run **13/87 duplicated** (8 of
> 13 involving Top Takeaways); Fable test run **8/91** (worst case: $CRWV
> narrated in 3 analytic sections). Both models repeat; the shape differs.
> Measurement script: the ad-hoc `repetition_check.py` (session scratchpad),
> productized as Idea 12 below.

## Decision checklist

| # | Idea | Type | Cost/yr | Effort | Status |
|---|---|---|---|---|---|
| 1 | Sequential-exclusion rule | Prompt | $0 | S | **BUILT 2026-07-22** |
| 2 | Cross-reference device (→ §N) | Prompt | $0 | S | **BUILT 2026-07-22** |
| 3 | Top Takeaways redefinition (variant a or b) | Prompt | $0 | S | **BUILT 2026-07-23 (variant a); upgraded same day to "self-contained §1" (a+), PENDING JARED SIGN-OFF** |
| 4 | One-number-one-place rule | Prompt | $0 | S | **BUILT 2026-07-23** |
| 5 | Plan-first nudge (Fable) | Prompt | $0 | S | **BUILT 2026-07-22** |
| 6 | Bullet caps on §2–5 | Prompt | $0 | S | **BUILT 2026-07-23 (soft cap)** |
| 7 | Multi-source merge, mechanical form | Prompt | $0 | S | **BUILT 2026-07-23** |
| 8 | De-prescribe (ALTERNATIVE to 1/2/4 stacking) | Prompt | $0 | S | |
| 9 | Pass-2 dedup mandate first + concrete method | Prompt | $0 | S | **BUILT 2026-07-22** |
| 10 | Dedicated dedup pass 2.5 | Code+LLM | ~$75–110 | M | |
| 11 | Deterministic tripwire gating 10 | Code | ~$0–20 | M | |
| 12 | Standing repetition metric + log line | Code | $0 | S–M | **BUILT 2026-07-22** |
| 13 | WSJ/FT appended-section dedupe | Code | $0 | M | **BUILT 2026-07-22** |
| 14 | Memory storyline "only if changed" rule | Prompt | $0 | S | **BUILT 2026-07-23** |
| 15 | Merge overlapping sections | Prompt/structural | $0 | M | **ATTEMPTED 2026-07-23 — REVERTED** (see section) |

Effort: S = <1h, M = 1–3h (incl. tests). All items keep `ruff` + `pytest` green
and respect HANDOFF §2/§6 constraints.

## Global constraints (apply to every item)

- **G1 — One prompt revision, one validation.** Ideas 1–9, 14, 15 all edit the
  pinned `SYSTEM_PROMPT` / pass-2 instruction in `digest.py`. If several are
  chosen, land them as a SINGLE batched edit validated by ONE test run
  (~$2.70 on Fable to acohen, or free-check on the next 08:00 live run) — not
  one run per idea. The SYSTEM_PROMPT is §6-adjacent (heavily pinned, feeds
  `_assemble_digest_html` string-matching); every revision must keep the
  template skeleton byte-stable (header div, `<h2>` section pattern, `<li>`
  shape).
- **G2 — TEAM/FULL parity.** SYSTEM_PROMPT is shared by both variants and both
  passes; all prompt edits automatically apply to both. Pass-2 instruction text
  lives in the non-cached trailing block (no cache-prefix risk). Any
  SYSTEM_PROMPT change invalidates the prompt cache once (first run re-writes
  it) — expected, not a cost concern.
- **G3 — Measure before/after.** Idea 12 is the yardstick for all others.
  Recommended sequencing regardless of selection: ship 12 first (or same
  commit), so every other item's effect shows up as a number within days.
- **G4 — Fable prompting doctrine.** Fable follows instructions strongly AND
  degrades under over-prescription. Ideas 1–7+9 add rules; Idea 8 replaces
  rules with one principle. **8 is mutually exclusive with stacking 1+2+4** —
  pick a philosophy (see Idea 8).
- **G5 — Testing protocol.** Prompt-only ideas need a generation to validate
  (permission-gated); code-only ideas (11, 12, 13) validate offline for $0.
  Unit tests accompany every code change; prompt changes get template-shape
  assertions where feasible (existing `tests/test_assemble_digest.py` pattern).

---

## A. Prompt / structure

### Idea 1 — Sequential-exclusion rule (generalize the Bloomberg pattern)

**What.** The Bloomberg section instruction already contains the strongest
anti-repetition device in the prompt: *"Only items NOT already covered in
sections 1–6 — if a Bloomberg item earned a spot in an earlier section, it
lives there and must not be restated here."* Promote this to a global rule:
each section may only contain stories no earlier section covered.

**Why it works.** Replaces a judgment call ("single best-fit section") with a
deterministic tie-breaker (document order). Models execute positional rules
far more reliably than semantic ones. Directly attacks the Fable failure mode
($CRWV in §3, §4, AND §5 — under this rule it lands in §3 and is banned from
§4/§5 except as a new-angle clause).

**Implementation.** `digest.py` SYSTEM_PROMPT, Rules block. Replace the current
NO REPETITION rule's core with:

```
- SECTIONS ARE EXCLUSIVE, IN ORDER. Work top-down: once a story has appeared in
  any section, later sections may not re-tell it. If a later section has a
  genuinely NEW angle, give ONLY the new angle in one clause with a pointer to
  the home section (see the cross-reference rule). When a story qualifies for
  several sections, it lives in the EARLIEST qualifying section.
```

Keep the per-section Bloomberg wording (it's now redundant but harmless and
reinforcing). Mirror in the pass-2 checklist (see Idea 9 — implement together).

**Risk.** Top Takeaways is the earliest section, so under earliest-wins the
top stories live in §1 and can't be re-detailed below — but §1's existing
"3-5" cap bounds the drain: overflow stories still land in their topical
sections. Interacts directly with Idea 3 (choose 3's variant first; with 3a
this §1-first behavior is the explicit intent).
**Test.** Template-shape unchanged; validation via test run + Idea 12 score.
**Rollback.** Revert the rule text.

### Idea 2 — Sanctioned cross-reference device

**What.** Give the model an allowed alternative to restating: an inline pointer
`<em>(→ §3)</em>`.

**Implementation.** Two edits in `digest.py` SYSTEM_PROMPT:

1. Rules block, appended to the Idea-1 rule (or standalone if 1 is skipped):

```
- CROSS-REFERENCES: when a bullet must touch a story covered elsewhere, do not
  restate its numbers — reference it: "<em>(→ §2)</em>". Example:
  <li><strong>Data centers:</strong> grid constraints now the binding factor
  on capacity growth <em>(→ §1)</em>; new angle here is X. <span ...>(Source)</span></li>
```

2. Template styling comment: `<!-- Cross-refs: <em>(→ §N)</em> when referencing
   a story covered in another section -->`.

**Interaction.** Amplifies 1 (gives the "later section" a legal move). §N
numbers can shift when sections are omitted/renumbered — instruct the model to
number references against ITS OWN final numbering (it renumbers sections
already, so it knows the mapping). Appended sections (WSJ/FT etc.) are
unnumbered by design — pointers may only target the model's own sections.
**Risk.** Low; worst case is a dangling §N if pass 2 deletes a section
(mitigate: pass-2 line "verify every (→ §N) points at an existing section").
**Rollback.** Remove the rule; pointers stop appearing next run.

### Idea 3 — Redefine Top Takeaways (pick variant a or b)

**Variant (a) — Takeaways owns the top stories.** §1 carries the 3–5 top
stories IN FULL; sections 2–5 may not re-detail them (only new angles via the
Idea-2 pointer). This is earliest-wins (Idea 1) embraced: §1 becomes the deep
section, the body becomes "everything else + new angles."

```
1. **Top Takeaways** — The 3-5 most important stories of the day, with FULL
detail: this is their home section and the ONLY place their numbers appear.
Later sections cover other stories, or add a genuinely new angle in one
clause with a (→ §1) pointer.
```

**Variant (b) — Takeaways is a pointer index.** §1 shrinks to one-line
pointers; detail lives in the body sections.

```
1. **Top Takeaways** — The 3-5 most important stories as ONE-LINE pointers:
lead word, a single decisive fact, and the section where the detail lives,
e.g. "<strong>Oracle:</strong> CDS now ~2x BB CDX — credit repricing ahead of
the agencies <em>(→ §3)</em>". Full detail belongs in the body section, not here.
```

**Trade-off.** (a) preserves the "read §1 and you're done" property (closer to
today's reading flow; recommended); (b) makes §1 skimmable but forces readers
to jump. Both kill the 8-of-13 Opus dupes involving §1. Choose ONE.

**Variant (a+) — "self-contained §1" (BUILT 2026-07-23 evening, operator
request; PENDING JARED SIGN-OFF — revert = `git revert` the commit that added
it).** Variant (a) taken to its conclusion: §1 is COMPLETE per story (all
sources merged, every angle as an indented sub-bullet, contrarian takes as a
`Contrarian:` sub-bullet — carved OUT of §5); later sections carry ZERO §1
content, at most a bare `(→ §1)` pointer; assignment rule = "primary subject
is the §1 story → sub-bullet there; independent story merely triggered by it →
its own section + bare pointer". Template gained the §1-only nested-`<ul>`
pattern; pass-2 check #1 now enforces completeness-and-containment (moves
stray §1 detail UP, not just deletes). Validated test run 2026-07-23:
repetition **0 strong** (first zero; prior best 1), 3 Contrarian: sub-bullets,
flat sections 2–9, complete HTML, $3.70 — pass 1 ran 23.4k output tokens,
which the OLD 20k cap would have truncated (needs the same-day truncation
guard/streaming commit, which precedes this one).
**Implementation.** Replace the §1 instruction in SYSTEM_PROMPT; add matching
pass-2 check ("§1 stories are not re-detailed later" for (a); "§1 bullets are
one line each" for (b)).
**Risk.** (a): §2–5 may feel thin on slow days — acceptable, sections omit when
empty. (b): bigger change to the product jared reads daily; confirm with him.

### Idea 4 — One-number-one-place rule

**What.** The checkable formulation of "no repetition": a specific figure
appears in exactly one section.

**Implementation.** SYSTEM_PROMPT Rules block:

```
- EVERY SPECIFIC FIGURE APPEARS EXACTLY ONCE in the digest — a price, spread,
  yield, price target, % move, or dollar amount is stated in its story's home
  section and nowhere else. If two sections need the same number, the story is
  in the wrong sections — merge per the exclusivity rule.
```

Plus the mirrored pass-2 line (Idea 9's method makes this the verification
target: "list every figure appearing 2+ times; fix each").

**Why separate from 1.** Idea 1 operates on *stories* (semantic identity —
fuzzier); this operates on *figures* (literal identity — mechanically
checkable by pass 2 AND by the Idea-12 metric, which counts exactly this). The
two together give the model a semantic rule and a lint rule.
**Risk.** Occasional legitimate double-use (e.g. the same 10Y yield relevant to
two genuinely different stories) becomes awkward — the escape is the Idea-2
pointer. Low.

### Idea 5 — Plan-first nudge (Fable-specific)

**What.** One line directing Fable's always-on thinking toward a global
story→section allocation before writing.

**Implementation.** SYSTEM_PROMPT, immediately before the SECTIONS list:

```
Before writing, plan: list the day's distinct stories and assign each to
exactly ONE home section. Write from that allocation — the plan is for your
reasoning only; never include it in the output.
```

**Why.** Attacks the root cause (per-section drafting without a global map).
Fable executes planning instructions well; thinking tokens are already being
spent, this just aims them. The "never include it" clause guards against a
plan block leaking into the HTML (same failure class as the changelog leak;
`_strip_to_html` remains the code-side backstop).
**Cost.** Possibly slightly more thinking tokens (billed as output on Fable) —
expect cents/day.
**Interaction.** Synergistic with 1/3/4 (the plan is where exclusivity gets
enforced cheaply). Harmless if 8 is chosen instead.

### Idea 6 — Bullet caps on sections 2–5

**What.** §1 already has "3-5". Cap §2–§5 at ≤5 bullets each.

**Implementation.** Append to each of the four section instructions: "At most
5 bullets — prefer omission over padding." (Exact per-section counts
adjustable; 5 matches today's typical section size, so this binds only on
heavy days.)

**Why.** Padding pressure is a repetition source — when a section wants more
bullets than it has fresh stories, restatement fills the gap.
**Trade-off.** Genuine depth loss on very heavy news days (a 7-story ratings
day loses 2). This is the one Group-A idea with a real functionality cost —
flagging honestly. Mitigation: phrase as soft cap ("more only if each is a
distinct story").
**Risk.** Low. **Rollback.** Delete the clauses.

### Idea 7 — Multi-source merge, mechanical form

**What.** Strengthen "synthesize them" into a countable rule with compound
source tags.

**Implementation.** Replace the current synthesis rule in SYSTEM_PROMPT:

```
- ONE STORY = ONE BULLET, however many sources covered it. Merge multi-source
  coverage into a single bullet with a compound tag — "(FT; Stifel)" — noting
  where sources disagree. Never write per-source bullets for the same story.
```

(The existing "note where they agree or disagree" folds into this.)
**Why.** Same-story-different-source is a distinct duplication channel from
same-story-different-section; Ideas 1/4 don't cover it within a single
section. Compound tags also improve source attribution density.
**Risk.** Minimal; compound tags already appear organically some days.

### Idea 8 — De-prescribe: one principle instead of a rule pile (ALTERNATIVE)

**What.** The opposite bet to 1+2+4+7: per Fable migration doctrine
(over-prescriptive prompts reduce output quality), REPLACE the scattered
anti-repetition clauses with a single positive editorial principle:

```
- EDIT LIKE A NEWSPAPER: disjoint sections, each story told once in its best
  home, each fact stated exactly once. A reader who finishes the digest should
  never feel they read the same thing twice.
```

...and delete: the NO REPETITION block, (if adopted) Ideas 1/4/7's rules.
Idea 2's pointer device and Idea 5's plan nudge remain compatible (they're
affordances, not constraints).

**Decision structure.** 8 vs (1+4+7) is an A/B, not a stack. Recommended
protocol: implement the chosen primary (say 1+2+4+5+7+9), measure ~1 week via
Idea 12; if the score hasn't dropped meaningfully (or format quality degrades),
swap to 8 for a week and compare. The metric makes the A/B cheap — the cost is
calendar time, not money.
**Risk.** Under-specification could regress other pinned behaviors if deletion
is sloppy — delete ONLY repetition-related clauses, nothing else.

### Idea 9 — Pass-2: dedup first, with a concrete method

**What.** Repetition is currently check #3 of 6 in the pass-2 review
instruction. Make it check #1 and give it a mechanical procedure.

**Implementation.** `digest.py` `summarize_with_claude`, pass-2 content block.
Reorder and rewrite:

```
1. DEDUPLICATE — this is the primary review goal. Method: list every ticker
   and every specific figure (price, spread, %, target, $ amount) that appears
   in more than one section of the draft. For each, choose the home section
   (the earliest qualifying one), keep the full detail there, and in every
   other section either delete the mention or reduce it to a one-clause new
   angle with a (→ §N) pointer. Verify every (→ §N) points at a section that
   exists in the final numbering.
   Also confirm there is NO TL;DR / summary box before section 1 — delete it
   if the draft opens with one.
2. Identify any important items that were MISSED — ... (current #1)
3. Check for ERRORS — ... (current #2)
4. Check that every bullet has a source tag. (current #4)
5. Check the FORMAT rules: ... (current #5)
6. Produce a FINAL ENHANCED VERSION ... (current #6)
```

**⚠ Implementation note:** the no-TL;DR guard currently lives inside check #3
(the REPETITION check, the one this idea replaces) — NOT in #5. It must be
carried into the new #1 as shown above, or it silently disappears.

**Why.** The add-bias of pass 2 (5 checks push content in) is structural; at
minimum the dedup check should lead, be concrete, and use the same
figure-based definition as Ideas 4 and 12 so prompt, reviewer, and metric all
measure the same thing.
**Cost.** $0 (same call). **Risk.** Low — trailing block, no cache impact.
**Note.** If Ideas 1/2/4 are skipped, drop the (→ §N) and earliest-wins
phrasing accordingly — 9 must reference only rules that exist.

---

## B. Pipeline / pass structure

### Idea 10 — Dedicated dedup pass 2.5

**What.** A separate LLM call whose ONLY objective is cross-section dedup,
isolating it from pass 2's add-bias. Input: the final digest HTML alone (no
sources — that's what makes it cheap AND focused). Output: the same HTML with
duplicates merged/deleted.

**Implementation sketch.** New function in `digest.py`:

```python
def dedup_digest_html(final_html, cost_label=""):
    """Pass 2.5 (REDUCE_REPEATS Idea 10): single-objective cross-section
    dedup. Sees ONLY the digest (no sources). Guarded: any output that fails
    template sanity returns the input unchanged."""
    # model: SONNET_MODEL (default) — see cost/fidelity tradeoff below
    # prompt: the Idea-9 method verbatim, plus "change NOTHING else; output
    #   ONLY the full corrected HTML from <div to the final closing tag"
    # guards (all-or-nothing, fall back to input on any failure):
    #   out = _strip_to_html(_response_text(resp))
    #   - out startswith '<div' and contains the header anchor
    #     ('border-bottom: 3px double')
    #   - section count (count of '<h2') <= input's, and >= input's - 1
    #   - 0.6 * len(input) <= len(out) <= 1.05 * len(input)
    #   - cost.record("digest dedup pass", ...)
```

**Placement (verified against main()):** call immediately after each
`summarize_with_claude` return, on the generated `digest_html` /
`team_digest_html` BEFORE `_assemble_digest_html`. Ordering facts: alert
evaluation is unaffected either way (it consumes `source_text`, not digest
HTML); the deduped text then flows into assembly → send → `save_daily_digest`
→ the Friday weekly summary, all consistently. Note `ticker_names.collect()`
runs inside `summarize_with_claude` on the pre-dedup text — harmless (name
pairs staged before dedup are still valid pairs). Use `_response_text()` to
read the dedup response (Fable-compatible).

**Cost (per measured token counts — Fable pass-2 outputs ran 7.6–11.6k
tokens).** Sonnet, per variant: ~9–13k in + ~8–12k out ≈ $0.15–0.22; two
variants ≈ $0.30–0.45/day ≈ **$75–110/yr**. Haiku alternative ≈ $15–25/yr but
weaker template fidelity — recommend Sonnet, or either model behind the
Idea-11 tripwire.
**Risk.** Another LLM rewrite of the final email = another changelog-leak-class
surface. Mitigated by the hard fall-back-to-input guards (a failed dedup ships
yesterday's behavior, never a broken email). This is the same guard philosophy
as `_strip_to_html`, tightened.
**Permission.** Adds a new recurring Claude call — needs explicit operator
sign-off on the ~$75/yr (or gate it: Idea 11).
**Test.** Offline: guard unit tests (mutated/truncated outputs fall back).
Live: one permissioned test run.

### Idea 11 — Deterministic tripwire (gates 10; useful alone)

**What.** Code-side repetition scan of the final HTML (no LLM). Two uses:
(a) alone — log/alert when a digest ships with high repetition; (b) as the
gate for Idea 10 — fire the dedup pass only when score ≥ threshold, making
pass 2.5 nearly free on clean days.

**Implementation.** Shares its scorer with Idea 12 (one module —
`repetition.py`):

```python
# repetition.py
SIGNAL_RE = ...  # tickers + bps/% /$ figures (from repetition_check.py)
def section_texts(digest_html) -> dict[title, text]   # skip Snapshot/pre-rendered
def repetition_score(digest_html) -> (n_duplicated, details)
```

In `main()`: compute score per variant; if `score >= REPEAT_TRIPWIRE`
(config.py constant), then (b) invoke `dedup_digest_html` if built, else (a)
append a deterministic alert to the run log (and optionally the O3-style
digest alert box — recommend log-only to start; the alert box is
reader-facing).

**Threshold.** Don't guess: run metric-only (Idea 12) for ~1 week, then set
`REPEAT_TRIPWIRE` at the observed clean-day P75 + margin. ~~Today's data
suggests clean ≈ ≤5, bad ≥ 8, so likely 6–8.~~ *(Stale — that was metric-v1
scale. Under v2 (2026-07-23 recalibration) the clean floor is 1–3 strong;
a v2 tripwire would likely sit at 4–5. Re-derive from a week of v2 data.)*
**Cost.** $0 alone; with 10 gated, expect the pass to fire a minority of days
→ ~$0–20/yr. **Risk.** None (read-only unless gating).
**False positives.** Bare-% collisions ("20%" twice, unrelated) inflate the
score; acceptable for a tripwire, and the ticker-only sub-score can be
weighted higher if needed.

### Idea 12 — Standing repetition metric (build first regardless)

**What.** Productize the measurement: per-run score, logged and persisted, so
every other idea's effect is a tracked number. Zero LLM cost, deterministic.

**Scoring surface (verified).** Score the ASSEMBLED variant HTML
(`final_html` / `team_final_html`, after `_assemble_digest_html`) — and
`save_daily_digest` saves exactly that assembled HTML, so the live metric and
the `digests/*.html` backfill measure the same thing by construction.
Section inventory for the scorer (splits on `<h2>`):
- **Include:** the model's numbered sections (1–9) + the appended
  `WSJ/FT Articles` (reader-facing; Idea 13's target).
- **Exclude:** the five `* Snapshot` tables, `Fed Balance Sheet (H.4.1)`,
  `Fund Position Changes (13F)` and `Bankruptcy Court Activity` (data tables —
  13F holdings legitimately list dozens of tickers that co-occur with digest
  mentions; counting them is pure noise). *Recalibration 2026-07-23 (metric
  v2): also exclude `Recent SEC Filings` and `Rating Actions` — model-written
  but content-MANDATED listings (every filing/action must appear), so a ticker
  discussed analytically + carrying a filing is a structural collision, not
  editorial repetition. Entries carry `"metric": 2`; v1 scores read ~1–3
  strong high. Observed v2 noise floor on story-clean digests: 1–3 strong
  (incidental in-story mentions, numeric coincidences like two unrelated
  $2.2B figures) — judge trends against ≥4 sustained, not single days.*
- The earnings box and the alerts box render without `<h2>` headers, so an
  h2-based splitter never sees them — no explicit handling needed.

**Implementation.**
1. `repetition.py` scorer (shared with 11), ~60 lines + docstring, using the
   include/exclude inventory above.
2. `digest.py` `main()`: after assembly, print
   `Repetition: N signals in 2+ sections (FULL)` / `(team)`, and append
   `{date, variant, n_signals, n_duplicated, details}` to
   `repetition_scores.json` (gitignored state file; add to `.gitignore` +
   HANDOFF §4 caches list; prune entries >180 days, ishares-cache style).
3. `tools/repetition_backfill.py` (optional, S): run the scorer over
   `digests/*.html` (server has the full history; dev has partial) to seed a
   baseline series before any prompt change lands.
4. Tests: scorer unit tests on synthetic HTML (known dupes → known score;
   excluded sections actually excluded; headerless boxes ignored).

**Why first.** Converts the whole effort from vibes to a number — the same
eval-first pattern as `tools/eval_retrieval.py`. Every A/B in this spec
(notably 8 vs 1+4+7) is only decidable with this in place.
**Risk.** None. **Effort.** S–M (M with backfill tool).

---

## C. Appended-section blind spot

### Idea 13 — Dedupe the WSJ/FT appended section against the digest

**What.** The WSJ/FT section is pre-rendered from the Haiku ranking and
appended AFTER generation. The model sees all ~156 headlines as source
material, but never knows WHICH 15 the independent Haiku ranking will append —
so it cannot dedup against the final list. Today's Opus digest showed exactly
this class of dupe (three signals — 75%, 2.8%, 2.6% — in both the digest body
and the appended headlines). Filter code-side.

**Implementation.** Split ranking from rendering in `digest.py`:

1. `build_news_html(articles, exclude_text="")` gains the param; after
   `_rank_news_articles` (Haiku runs ONCE, unchanged), drop articles whose
   title substantially overlaps `exclude_text`:
   - overlap test (deterministic, no LLM): normalized title tokens (lowercase,
     stopwords out, len≥4) — drop if ≥60% of title tokens appear in the digest
     text, OR any $TICK / distinctive proper-noun bigram from the title
     appears in it. Start strict (high bar to drop) — a false drop hides a
     headline; a false keep is just today's status quo.
2. Per-variant rendering: rank once → render twice —
   `news_html = build_news_html(ranked, exclude_text=team_text or full_text)`
   per variant, so the FULL digest (which covers more stories, incl. Substack)
   filters more aggressively than TEAM. Requires `_rank_news_articles` to be
   hoisted out of `build_news_html` into `main()` — NOTE on F10: HANDOFF §11.C
   records "hoist Haiku news-ranking out of build_news_html" as DECLINED. That
   decline was churn-avoidance with the rationale "never move it into the free
   `python news.py` path". This idea reverses F10's letter (the hoist happens)
   while fully respecting its rationale (ranking stays inside digest.py's paid
   path; `news.py` untouched) — and unlike F10, there is now a functional
   reason. Record the supersession in HANDOFF §11.C if built.
3. Optional softer variant: instead of dropping, demote matched headlines
   under a "Also covered above" sub-list. Recommend plain drop first —
   simpler, and the digest already covered the story.
4. Log: `WSJ/FT: dropped K of 15 ranked headlines already covered in digest`.

**Cost.** $0. **Risk.** Over-dropping on generic titles — mitigated by the
strict threshold + log line to watch. Fully unit-testable offline (synthetic
digest + titles).
**Effort.** M.

---

## D. Cross-day repetition

### Idea 14 — Memory storylines: mention only on change

**What.** Day-over-day repetition: memory context re-injects up to 59 active
storylines every run, inviting re-mention of unchanged stories.

**Implementation.** `digest.py` SYSTEM_PROMPT, replace the memory usage rule's
second half:

```
- If cross-digest memory is provided, use it to add context about EVOLVING
  stories (e.g., "tracking since Mar 28: redemptions now at 40.7%, up from 32%
  last week"). Mention a tracked storyline ONLY when today's sources add a
  development; an unchanged storyline is omitted entirely — never re-summarized
  "for continuity". Cite the original source, never the memory system.
```

**Why here.** Adjacent to (not identical with) the within-digest problem, but
it's the same reader experience ("I read this yesterday"). Zero cost, small.
**Risk.** A slow-moving story the reader WANTS re-surfaced (e.g. an approaching
catalyst date) could go quiet — the "development" bar covers approaching
catalysts if sources mention them, which they typically do. Watch via jared
feedback rather than metric (Idea 12 doesn't measure cross-day).

---

## E. Structural (bigger swing — flagged, not recommended as first move)

### Idea 15 — Merge overlapping sections

**What.** Fewer buckets = fewer boundaries to duplicate across. Concretely:
dissolve §4 (Themes & Sector Trends) and §5 (Contrarian / Surprising) as
standalone homes; their content lives in §1–§3 with inline markers — a
"Contrarian:" lead word (already natural under the lead-word rule) and theme
bullets folded into Market & Macro or Equity Ideas.

**Implementation.** SYSTEM_PROMPT SECTIONS list: delete §4/§5 instructions;
renumber (the template renumbers dynamically already — "Use these EXACT
numbers" comment must be updated); extend §2/§3 definitions to absorb themes
and contrarian angles; pass-2 checklist references updated. `_assemble_digest_html`
is agnostic (string-matches only the header; appended sections are unnumbered
since the 2026-07-14 fix) — but re-verify with the existing assemble tests.

**Trade-offs.** Highest-leverage structural fix (eliminates the two fuzziest
boundaries entirely) but the biggest change to the product jared reads daily —
§5 Contrarian is a distinctive feature of this digest. Requires his sign-off,
not just operator's. Sequencing: only if Groups A+B underdeliver on the
Idea-12 metric after 2+ weeks.
**Risk.** Functionality change by design; contrarian items could lose
prominence inside bigger sections (mitigate: bold "Contrarian:" lead word makes
them scannable). **Rollback.** Revert prompt; next run restores 9 sections.

**⚠ ATTEMPTED 2026-07-23 — test run FAILED, change REVERTED.** One ~$3.58
validated test (9→7 sections, themes → §2/§3, "Contrarian:" lead markers):
(a) BOTH passes hit the then-20,000 max_tokens cap — the merge drove Fable's
thinking+output over it and the emailed digest truncated mid-§6 with no
Rating Actions section at all; (b) §3 bloated to 13 bullets, ignoring its
soft cap; (c) zero "Contrarian:" lead words appeared. The truncation exposed
a latent silent-failure bug (stop_reason never checked) — fixed same day:
caps raised to 32,000 + a truncation guard (loud WARNING, ops-alert entry,
pass-2→pass-1 fallback; `digest._guard_truncation`). Preconditions for any
retry: the guard/cap fix in place (done), a prompt fix for the §3
bloat/marker non-compliance, jared's sign-off — and honestly, with
story-level repetition already at zero on the 9-section stack, the marginal
upside no longer justifies the product change.

---

## Suggested bundles (from the original recommendation)

- **Bundle 1 (free, low-risk core):** 12 → 1 + 2 + 5 + 9 + 13. One prompt
  revision (G1), one validation run, metric live from day one.
- **Bundle 2 (if score doesn't drop):** add 4 + 7, or swap philosophy to 8
  (A/B via the metric, one week each). **BUILT 2026-07-23 — shipped 4+7 (+14)
  after readers noticed repetition in the first Fable production run; Idea 8
  stays the fallback philosophy-swap if 4+7 don't move the metric.**
  - **TL;DR — what Bundle 2 actually changes** (all prompt-only, $0, one batched
    SYSTEM_PROMPT edit + one validation run per G1):
    - **Idea 4 — one-number-one-place:** every specific figure (price, spread,
      yield, target, %, $) appears in EXACTLY ONE section; a repeated number
      means the story is mis-filed. The lint-rule complement to Idea 1's
      story-level exclusivity, and the exact thing the Idea-12 metric counts.
    - **Idea 7 — multi-source merge:** one story = one bullet no matter how many
      sources covered it; merge into a compound tag "(FT; Stifel)" noting
      disagreement; never per-source bullets for the same story.
    - **Idea 8 — de-prescribe (the ALTERNATIVE, not additive):** delete the rule
      pile (NO REPETITION block + Ideas 1/4/7) and replace with ONE editorial
      principle ("edit like a newspaper — each story once, each fact once").
      Mutually exclusive with 4+7 — pick a philosophy and A/B the two via the
      Idea-12 metric, one week each (Idea 2's pointer + Idea 5's plan nudge stay
      either way). The bet: Fable degrades under over-prescription, so fewer
      rules may beat more.
    - **Decision:** run Bundle 1 ~1 week; if STRONG repetition stays ≥3+, ship
      **4+7** first (lowest-risk, additive) and only reach for **8** if 4+7 don't
      move the metric or format quality slips (HANDOFF §11.B).
- **Bundle 3 (escalation):** 11, then 10 gated by it. Permission gate on 10's
  recurring spend.
- **Deferred:** 3 (pick variant with jared), 6 (real depth trade-off),
  14 (cheap, do anytime), 15 (last resort, jared sign-off).
  *(Update 2026-07-23 second batch: 3 shipped as variant (a) — the recommended,
  reading-flow-preserving one; (b) still needs jared if ever wanted. 6 shipped
  as the soft cap. Also added: pointer-echo tightening — a referenced story is
  named once, briefly, never re-narrated with synonyms ("the oil surge (→ §1)…
  the crude spike" class, caught by a reader in the first Bundle-2 test run) —
  mirrored in the pass-2 checklist. Remaining unbuilt: 8 (A/B fallback),
  10+11 (Bundle 3, spend sign-off), 15 (jared sign-off).)*

## Interactions summary

- 1 ⇄ 3: choose 3's variant before finalizing 1's earliest-wins wording.
- 8 ⊻ (1+4+7): alternative philosophies — A/B, don't stack.
- 9 depends on the wording chosen in 1/2/4 (must reference only rules that exist).
- 11 shares code with 12; 10 is best gated by 11.
- 13 is independent of everything (pure code).
- 12 first, always — it's how every other choice gets judged.
