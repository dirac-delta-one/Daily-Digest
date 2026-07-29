# JPM Markets Research — Integration Spec

> **Status: DESIGN / PHASE 0 (2026-07-27).** New source: J.P. Morgan Markets institutional
> research (`markets.jpmorgan.com`), accessed with jared's dealer credentials. First of a
> planned family of dealer-research sources (JPM first). No code wired into the digest yet —
> this doc is the plan; build proceeds in the phases below.

## Objective

Pull J.P. Morgan Markets research (jared's institutional entitlement) into the daily digest,
the same way the free API sources and the Substack/13D authenticated sources already flow in.
Access is credentialed + MFA-gated; the MFA access code auto-forwards from jared's mailbox to
the bot inbox (`acorn.research.bot@gmail.com`), so an unattended run can complete the login.

## Distribution decision (operator, 2026-07-27): **FULL + TEAM**

JPM research is distributed to the **whole team**, i.e. treated like the free sources, NOT
walled to jared's FULL variant the way Substack is.

> ⚠️ **Recorded caveat.** `markets.jpmorgan.com` is stamped "FOR INSTITUTIONAL & PROFESSIONAL
> CLIENTS ONLY." jared's access is a personal/firm institutional entitlement; redistributing its
> research to other recipients may exceed JPM's terms of use. The operator weighed this and chose
> FULL+TEAM (it is the firm's JPM relationship and the firm's risk to accept). **If this ever
> needs to flip to jared-only**, the Substack machinery is the drop-in pattern: add JPM's
> sender/source markers to the `_SUBSTACK_EMAIL_DOMAINS`-style boundary and the
> `summarize_with_claude` team-prefix exclusion, and it becomes FULL-only + jared-personal-memory
> like Substack. Until then, JPM content rides the shared/team prompt prefix and IS indexed for
> team-tier reply retrieval.

## Login flow (mapped 2026-07-27, read-only recon)

- **⚠️ CORRECTED 2026-07-29 — the entry is NOT the bare root; the gateway is RESOURCE-SCOPED.**
  Opening `https://share-login.jpmorgan.com/` with no resource identifier returns a JPM-branded
  **"Bad Request"** page (recon: `jpm_recon/landing.html`, 721 bytes, title
  `Bad Request | J.P. Morgan`; the only cookies set are `geo_country`, `geo_region` and —
  the tell — **`resourceName`**). The 7/27 "root works" reading was wrong: what the operator
  opened successfully in her own browser almost certainly carried history/cookies or the full
  link. `_login_root` no longer strips path+query — it preserves them (only the known-dead
  `/sessionExpire` path is stripped). **BLOCKER → the human step: get jared's ORIGINAL entitled
  share link** (from his JPM email or bookmark — expect something like
  `https://share-login.jpmorgan.com/<path>?resourceName=…`) and put THAT in `env.bat` as
  `JPM_LINK`. Until then no login attempt can succeed, and none should be made.
  Expected flow once the real link is used: landing (button and/or T&C acceptance) → login form
  → username + password → (MFA access code only sometimes — the device may be remembered) →
  entitled research.
- ⚠️ **The Playwright BUNDLED Chromium is 400'd by the gateway** (2026-07-29): identical URL
  rendered fine in the desktop browser. `_launch_browser` now drives the machine's installed
  Chrome/Edge via Playwright's `channel`. **No automation-hiding flags** — deliberate: if JPM
  refuses openly-automated real Chrome as well, that is an approach decision for jared (ask JPM
  for entitled feed/API access, or keep this human-in-the-loop), not an evasion problem to
  engineer around. *(Note both 7/29 attempts hit error pages BEFORE any form existed, so
  **no auth attempts were spent** — the block budget is untouched.)*
- ⚠️ **Do NOT log in via `markets.jpmorgan.com/login`** — it authenticates but dead-ends at "You
  do not have appropriate entitlement to access this resource" (learned 2026-07-27: jared is
  entitled to the shared resource behind the gateway, not the full markets platform).
- ⚠️ **JPM blocks an IP after repeated auth attempts** (operator's IP blocked 2026-07-27 after
  ~3 tries in quick succession). Discipline for all future work: **one attempt per run, never
  retry a failed login, wait hours between attempts**; the unattended module must fail-soft and
  skip (13D-style), never loop. The server's IP is separate from the dev machine's, so a dev-side
  block doesn't poison production — but the same one-attempt rule applies there.
- Selectors are defensive (13D-style) + a landing-button click; the authenticated/entitled-page
  DOM is captured by `jpm_recon/` on the next successful run.
- This is a **browser SSO flow, not a JSON API** → Playwright module modeled on `thirteen_d.py`
  (drive a real browser, persist `storage_state`), NOT the clean-API `substack.py` client.
- Playwright 1.60.0 is already installed in the venv (13D uses it).

## Secrets (installed in `env.bat` 2026-07-27 — gitignored, machine-level on the server)

- `JPM_USERNAME` — login username/email.
- `JPM_PASSWORD` — login password.
- `JPM_LINK` — **must be jared's FULL entitled share link, path and query included** (2026-07-29:
  the gateway is resource-scoped; a bare host = "Bad Request"). The dev `env.bat` currently holds
  the dead `https://share-login.jpmorgan.com/sessionExpire` — replace it with the real link.
- Plus a saved session: `jpm_session.json` (Playwright storage_state, gitignored like
  `thirteen_d_session.json`). Copy to the server the same way as the other secret files.

## MFA access code (reuse Substack's proven pattern)

The forwarded code email is read from the bot inbox exactly like Substack's OTP (freshness-gated
on `since_epoch`, sender-scoped Gmail query). **Sample captured 2026-07-27** (from the first login
attempt):
- **From:** `authe.noreply@jpmchase.com`
- **Subject:** `Your Authentication Code from JPMorgan Chase`
- **Body:** "Your Authentication Code is `NNNNNNNN` and is available…" — **8 digits, in the BODY**
  (not the subject); expires in 10 minutes.

`jpm_research.read_jpm_code()` implements the reader (`from:authe.noreply@jpmchase.com
newer_than:1h`, regex `Authentication Code is (\d{6,8})`, since_epoch freshness gate). The Phase-3
digest exclusion filter keys on the same sender/subject.

## Credential-handling boundary (why the first login is human-run)

Claude (the assistant) must not type jared's password into a login field — that is a prohibited
action, and the repo already respects it: `thirteen_d._do_manual_login` opens a headed browser
and a **human** logs in, then the saved session is reused headless. Substack never types a
password (passwordless OTP). So:

- **The assistant writes the code; the assistant does not run the password-entry step.**
- **Phase 1's first login is human-run + headed** (operator/jared types the password, handles
  the code). This is the safest first contact with a live bank SSO (no lockout from
  blind-guessed selectors) AND it captures: a working session, the real password/MFA page DOM,
  and the first code-email sample.
- **Unattended automation (Phase 1b+)** — the *server's scheduled task* reads `JPM_PASSWORD` from
  env and drives login + auto-reads the forwarded code. That is the deployed system operating on
  its own stored credential (same category as the server running Substack's auto-login unattended),
  not the assistant typing a password. Built only AFTER Phase 1 reveals the real pages + code
  format.

## Build phases

**Phase 0 — DONE (2026-07-27):** recon (login flow mapped to the username page); secrets
installed; this spec; distribution decision recorded.

**Phase 1 — session capture (headed, human-run):** `jpm_research.py --login` opens a headed
browser to `JPM_LINK`/login, the operator logs in as jared (types password + enters the
forwarded code), the module saves `jpm_session.json` gated on an authenticated-cookie check
(13D's anti-clobber guard) and dumps the post-login landing DOM to scratchpad for scraper design.
Deliverables out of this run: valid session + real DOM + first code-email sample.

**Phase 1b — automate the login:** using the Phase 1 DOM + code-email sample, add the
defensive automated path (env creds → username → password → auto-read code via the Substack
helper → save session). Refresh-on-expiry + unattended graceful-skip like 13D's `R8` guard.

**Phase 2 — scraper:** decide WHAT to pull (which research feeds/analysts/products — needs the
authenticated site in hand) and extract it (`fetch_jpm_research()` → prompt text + optional
PDFs, macro-source-shaped so it flows through the existing fetch registry).

**Phase 3 — digest integration + email filter:**
- Add `jpm_research` to `digest.SOURCE_FETCHERS`; feed its text/PDFs into the prompt; add a
  `format_jpm_for_prompt` and (if needed) a rendered section.
- **Auto-filter JPM access-code emails from the digest** (operator flagged): the forwarded code
  emails are inbox mail, so without a guard they'd become digest source material. Add a
  self-artifact-style exclusion in `digest._fetch_emails` keyed on the code email's real
  sender/subject (from the Phase 1 sample) — mirror the `config.is_self_artifact` /
  Substack-email-boundary pattern. Also exclude them from indexing.
- O3 content-monitor entry so a silent JPM outage (expired session, layout change) surfaces.

**Phase 4 — server deploy:** install `jpm_session.json` + the env keys on the box; `playwright
install chromium` if not already present; confirm the scheduled task can complete the unattended
login (or falls back gracefully). 13D's "manual re-login eventually needed" caveat applies.

## Open decisions (need answers before Phase 2/3)

1. **What research to pull?** JPM Markets is vast (Global Research, Eye on the Market, sector
   notes, AI Search). A daily "what's new" list? Specific analysts/desks jared follows? A
   particular landing feed? — needs the authenticated site to scope.
2. **Volume / token budget** — dealer research is long; may need per-note summarization (a Haiku
   pre-pass) before it hits the digest prompt, like the PACER/size-filter pattern.
3. **Session longevity** — does JPM remember the device (MFA every N days, like 13D) or every
   login? Determines how often the forwarded-code path is exercised. Answered by Phase 1.

## Risks

- **Account lockout** from repeated failed automated logins against a live bank SSO — mitigated
  by human-run Phase 1 and defensive/single-attempt automation with generous waits.
- **Session fragility / layout drift** — SSO and research pages can change; Playwright selectors
  are brittle. Defensive multi-selector logic (13D-style) + O3 monitoring + graceful skip.
- **Entitlement/ToS** — see the distribution caveat above.
- **Unattended MFA** — if the auto-forward ever stops, unattended login fails; must skip
  gracefully (never hang a headless run — the 13D `input()`-on-server hazard).
