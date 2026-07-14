# Forwarding-Visibility Fix — Spec

> **STATUS: APPROVED — all decisions settled (§7), no code written yet.** All three stages are in.
> This spec touches the load-bearing `SYSTEM_PROMPT` (HANDOFF §6) and increases per-run input tokens
> (a real, if small, cost). Build order in §9: Stages 1 & 3 are free/offline; **Stage 2 needs one
> permissioned run to acohen** — that single paid run is the only remaining gate.

---

## 1. Objective

Make **forwarded** emails (everything jared forwards into the bot inbox) properly *seen* and
*attributed* by the **morning digest**, closing the two known limitations recorded in HANDOFF §13.
Today the forwarded content is archived and reply-bot-searchable, but the daily digest effectively
can't read it or classify it by its true source.

Concretely, the motivating failure: a **Bloomberg "Today's News"** email forwarded by jared is
invisible to the digest's §7 Bloomberg section, because (a) the digest sees the outer sender
(`jtramontano@acorninv.com`), not `bloomberg.net`, and (b) only the ~200-char Gmail snippet reaches
the prompt.

---

## 2. Background — the two root causes (verified in code)

**Issue A — only the outer `From:` is known; no embedded-sender parsing.**
`fetch_recent_emails` records `"from" = headers["From"]` (`digest.py:231`), which for a forward is
always jared. Nothing parses the forwarded body's *inner* `From:`. The `SYSTEM_PROMPT` §7 rule —
*"If any emails are from **bloomberg.net**, group them here"* (`digest.py:279`) — therefore can
never fire on a forward, and source attribution for any forwarded publisher is blind to the real
sender.

**Issue B — only the snippet reaches Opus, not the body.**
Each email renders into the prompt as From / Subject / Date / `Preview: {snippet}`
(`digest.py:394`). The full body is fetched (`extract_gmail_body(..., cap=50000)`, `digest.py:228`)
but **deliberately withheld from the prompt** — comment: *"not sent to Opus — too large."* It is
saved to `emails.json` and indexed into FAISS (so the reply bot can retrieve it), but the morning
digest sees only the ~200-char snippet, which for a forward is often jared's forwarding preamble
rather than the actual content.

**Net effect:** forwarded sources are under-represented and mis-attributed in the daily digest,
while remaining fully available to the reply bot (RAG over the archived body). This spec fixes the
digest side; the reply-bot side already works.

---

## 3. Constraints

- **Load-bearing prompt (§6).** Stage 1 changes the `From:` string Opus sees and Stage 2 adds body
  text; both feed the tuned `SYSTEM_PROMPT` / `_assemble_digest_html` coupling. Validate output on a
  permissioned run before trusting.
- **Token cost.** Stage 2 adds input tokens to every run. Estimate + cap in §5. This is the only
  new *cost*; Stage 1 is free.
- **Testing discipline.** Offline unit tests first (free). Any end-to-end digest run is
  **permissioned, once, to `acohen@acorninv.com`** (never the production recipients). Reuse the
  existing archived days for detection unit tests — no live Gmail needed to build/verify the parser.
- **Cache-neutral placement.** The email block is part of the shared prompt prefix that both the
  team and full variants cache against (`_build_source_prompt`). Keep the new body text inside that
  shared block so the cross-variant cache still engages (the added tokens are a one-time cache write
  per run, then cache-read by pass 2 and the full variant).

---

## 4. Stage 1 — Embedded-sender detection (free, offline)

**What:** derive an *effective sender* for forwarded emails by parsing the forwarded body's inner
`From:` line, so the digest can attribute and group by the real source (Bloomberg, etc.).

**Where:**
- New helper `_parse_forwarded_from(body_text)` **in `html_utils.py`** — NOT `digest.py`. Stage 3
  imports it into `search.py`, and `digest.py` already imports from `search.py`
  (`index_daily_content`), so a helper in `digest.py` would create a `digest`↔`search` circular
  import. `html_utils.py` is already imported by both `digest` (`extract_gmail_body`) and `search`
  (`strip_html`), so it's the neutral shared home. Returns `(display_name, email)` or `None`.
- `fetch_recent_emails` (`digest.py:212-237`): add an `"effective_from"` field. Rule:
  - If the outer `From:` matches a small `FORWARDER_ADDRESSES` set (jared's two addresses — define it
    explicitly rather than reusing `FULL_ACCESS_SENDERS`, which includes the bot and is a different
    concept) **or** the subject starts with `FW:` / `Fwd:`, attempt `_parse_forwarded_from(body)`.
  - On a hit, `effective_from = <inner sender>`; else `effective_from = from` (unchanged).
- `_build_source_prompt` (`digest.py:~389`): render the effective sender. Proposal — show both so
  nothing is hidden:
  `From: {effective_from}  (forwarded by {outer_from})` when they differ, else just `From: {from}`.

**Detection details:**
- Body is already HTML-stripped to text by `extract_gmail_body`, so the forward header appears as
  plain lines. Handle both common formats within the first ~2000 chars:
  - **Outlook:** `From: Name <addr@dom>` / `Sent:` / `To:` / `Subject:`
  - **Gmail:** `---------- Forwarded message ---------` then `From: Name <addr@dom>` / `Date:` / …
- Regex: first line matching `^\s*From:\s*(.*?)<?([\w.+-]+@[\w.-]+)>?` after an optional forwarded
  marker. Take the first match only. Guard against matching a quoted signature by requiring it to
  precede a `Subject:`/`Sent:`/`Date:` line within a few lines (a real forward header block).
- Keep it conservative: a miss falls back to the outer `From` (today's behavior) — never worse than
  now.

**§7 rule update:** the SYSTEM_PROMPT §7 line stays semantically the same ("group emails from
bloomberg.net") but now works because Opus sees `bloomberg.net` in the effective `From:`. Optionally
tighten the wording to "from Bloomberg (sender or forwarded-from bloomberg.net)".

**Verify (offline, free):**
- New `tests/test_forwarded_from.py`: Outlook-format and Gmail-format fixtures → correct inner email;
  a direct (non-forward) email → `None` (falls back to outer From); a body that merely quotes
  "From:" in prose → not misdetected.
- Spot-run against real archived `emails.json` days (`archive/2026-07-*/emails.json`) and print the
  detected `effective_from` per email — confirm the Bloomberg forwards resolve to `@bloomberg.net`
  and broker forwards (Stifel/KBW/Barclays/Greenmantle) resolve sensibly. No Claude, no send.

---

## 5. Stage 2 — Capped body extract into the prompt (the paid validation)

**What:** give Opus a bounded slice of each email's **body** (not just the snippet), so forwarded
content is actually readable at digest time.

**Where:** `_build_source_prompt` (`digest.py:~389`). Replace/augment `Preview: {snippet}` with a
capped body extract.

**Design (operator-settled defaults, §7):**
- **Per-email cap** `EMAIL_BODY_PROMPT_CHARS = 4000` for text-bearing emails (replaces the snippet).
- **PDF-carried emails stay lean:** when an email has PDF attachment(s), its analytical content is
  already fed to Opus as the attached document, so the body extract for those is small (`~500`, or
  just the snippet) — spend the token budget where the content actually lives (text-only forwards
  like the Bloomberg "Today's News" roundup and text broker notes), not on "please see attached"
  cover notes.
- **Overall budget cap** `EMAIL_BODY_TOTAL_CHARS = 40000` across all emails in a run (backstop for a
  heavy inbox day). Allocate **forwarded-and-text-bearing first**, then the rest.
- **Replace** the `Preview: {snippet}` line with the body extract; keep showing the Stage-1 effective
  sender.
- **Strip the forwarded-header boilerplate** from the extract when Stage 1 detected it, so the 4000
  chars are real content, not "From:/Sent:/To:/Subject:" lines.
- **"Clearly spam" skip (decision 4):** a conservative `_looks_like_promo(email)` guard drops only
  obvious junk (e.g. unsubscribe-heavy marketing, subscription upsells with no analytical text) —
  errs toward INCLUSION (a false skip loses content; the curated forward inbox rarely has spam). The
  SYSTEM_PROMPT already tells Opus to skip promo, so this is a token-saver, not the primary filter.

**Token / cost estimate (revised caps):**
- Worst case ~40k chars of body ≈ **~10k added input tokens** per run, inside the shared cache prefix.
- Cost: pass-1 cache **write** ≈ 10k × $5/M × 1.25 ≈ **$0.06**; pass-2 + the full variant read it at
  0.1× ≈ negligible. **~$0.05–0.10/run added**, bounded by the total cap. (Context: a run is ~$1.5,
  so ≤~7%.) Operator has accepted this tradeoff for higher-quality forwarded content.

**Verify:**
- Offline: unit-test the capping/budget logic (per-email cap, total budget, body-vs-snippet
  fallback, forwarded-header stripping) — no Claude.
- **One permissioned end-to-end run to acohen** (~$1.5): confirm (a) the §7 Bloomberg section now
  populates from the forwarded BBG email, (b) forwarded broker content is summarized with correct
  `(Bloomberg)` / `(Stifel)` etc. attribution, (c) the printed cost delta matches the estimate, and
  (d) the cross-variant cache still engages (`pass 1 wrote / pass 2 read` line). Eyeball the rendered
  email — no template/numbering regressions.

---

## 6. Stage 3 — propagate effective-sender to the search index (reply-bot attribution)

**Why it exists.** Stages 1–2 fix the *digest*. Stage 3 fixes the *reply bot's* attribution of
forwarded emails. Today the reply bot can already *retrieve* forwarded content (the full body is
indexed), so it can *answer* — but it attributes it to the wrong sender, because:

- `archive.py` writes `emails.json` with the **outer** `from` (jared).
- `search._chunks_for_date` builds each email chunk by prepending a header like
  `From: jtramontano@acorninv.com\nSubject: …` to the body **before embedding**. So the indexed chunk
  text literally says the sender is jared for a forwarded Bloomberg email.

Two consequences: (a) when Opus cites that retrieved chunk it sees "From: jared" and attributes
vaguely ("per an internal email") instead of "(Bloomberg)"; (b) the word "Bloomberg" isn't in the
chunk header, so keyword/entity retrieval for source-named queries ("what did Bloomberg say about
X") is weaker.

**What Stage 3 entails:**
1. **Update the email chunk builder** in `search._chunks_for_date` (`search.py:549-572`). Two lines
   change:
   - the embedded header (`search.py:556`): `From: {effective_sender}\nSubject: …` — because the
     header is part of the embedded chunk `text` (`search.py:557`), the real source becomes
     *searchable* (the token "Bloomberg" is now in the vector's text).
   - the `source_name` metadata (`search.py:554`): derive it from the effective sender — this is the
     label the reply bot surfaces when it *cites* the chunk, so updating the header alone would fix
     retrieval but not attribution.
   - **Read-else-parse precedence:** use `e.get("effective_from")` if present, otherwise call
     `_parse_forwarded_from(body)`. New days already carry the stored field; old days (whose
     `emails.json` predate Stage 1) get re-parsed from their stored body at index time — which is
     what lets a `--rebuild` backfill them.
2. **`archive.py` needs NO change.** `archive_daily_content` already copies every non-`pdfs` key of
   each email into `emails.json` (`archive.py:74`), so the Stage-1 `effective_from` field lands in
   the archive automatically — nothing to add here. (Verified against the current code.)
3. **Backfill the existing archive.** New days pick this up automatically; the ~8 already-indexed
   days keep the old headers until reindexed. Because the change alters the embedded chunk `text`,
   the affected chunks must be **re-embedded** — a metadata-only `--retag` is NOT enough (it rewrites
   tags, not the embedded header/vector). Run a full `python search.py --rebuild` (~4.5k vectors /
   8 days, a few minutes, **free** — local embeddings). Back up `archive/index.faiss` +
   `chunk_metadata.json` first (the pypdf-bump recipe).
4. **Re-baseline the eval.** A rebuild shifts email-chunk text (the header), so re-run
   `tools/eval_retrieval.py` and save a fresh snapshot (same as the pypdf bump on 2026-07-10). The
   golden set's email items match on *body* `text_contains_any`, which the header change doesn't
   touch, so metrics should hold; re-baseline to confirm. Free.

**Cost/effort:** entirely **free** (no Claude), but it's a rebuild + eval re-baseline, so it's more
than a one-liner. **Value:** better forwarded-source *citations* and stronger source-named retrieval
in the reply bot. It does **not** change whether the reply bot can find the content (it already can)
— only how well it names and ranks it.

**Recommendation:** include it — it's the natural completion of the fix (digest *and* reply bot both
attribute forwards correctly), it's free, and the rebuild+re-baseline is a known, low-risk recipe.
The only reason to defer is to keep this change small and skip the reindex for now.

---

## 7. Decisions (operator-settled)

1. **Detection trigger — BOTH:** attempt embedded-From when the subject is `FW:`/`Fwd:` **or** the
   outer sender is a known internal forwarder (jared). OR'd.
2. **Caps — err toward more content** (operator: higher-quality info is worth the cost). Revised in
   §5: per-email **4000** chars, total budget **40000**, and body is fed for text-bearing emails
   (PDF-carried notes stay lean — their content is already fed as the attached document).
3. **Snippet vs body — REPLACE** the snippet with the body extract (snippet is a strict subset).
4. **Scope — ALL emails**, minus a conservative "clearly spam/promo" skip (§5). Direct emails get the
   body extract too, not just forwards.
5. **Stage 3 — IN** (operator, 2026-07-14). Reply-bot attribution of forwarded sources is fixed too;
   includes the full `--rebuild` + eval re-baseline (free).

---

## 8. Risks & rollback

- **Prompt drift:** more body text could shift how Opus structures sections. Mitigated by the
  permissioned eyeball run and the existing `tests/test_assemble_digest.py` pins.
- **Mis-detection:** a false inner-From would mis-attribute one email. Mitigated by the conservative
  guard (must look like a real forward header) and fallback-to-outer-From.
- **Cost creep on heavy days:** bounded by the total-budget cap.
- **Rollback:** both stages are additive and localized to `fetch_recent_emails` /
  `_build_source_prompt` (+ one helper + tests). Revert = drop the helper and restore the
  `Preview: {snippet}` line. No data migration.

---

## 9. Build order

1. **Stage 1** — helper + `effective_from` + unit tests + real-archive spot check (free). Checkpoint.
2. **Stage 2** — capping/budget + spam guard + unit tests (free), then **one permissioned run to
   acohen** (paid, ~$1.5) to validate §7 Bloomberg population, attribution, cost delta, and the
   cross-variant cache. Checkpoint.
3. **Stage 3** — update `search._chunks_for_date` (embedded header + `source_name`, read-else-parse);
   `archive.py` needs no change (auto-passthrough). Then `python search.py --rebuild` + eval
   re-baseline (free). Checkpoint.

Update HANDOFF §13 (flip the two "known accepted limits" to resolved) and WORKLOG on completion.
`ruff` + `pytest` green at every checkpoint.
