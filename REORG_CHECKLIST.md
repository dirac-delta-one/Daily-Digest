# Repo Reorg Checklist (src/ layout) — execution runbook

> **Status: PLAN, not started.** Written 2026-07-27 in response to "the repo is messy — flat
> root, no `src/`." The reorg is *doable* but it is a **coordinated code+server maintenance
> operation, not a `git pull`** — the flat layout is coupled to how the server runs. Do NOT
> attempt it in the current window (operator departs 2026-07-31; JPM in-flight; Monday validation
> pending). Do it only when a maintainer has a dedicated window AND access to re-register server
> tasks if needed (Shawn's Windows password — see §Server). This doc is the safe way to do it
> when that time comes.

## Why this isn't just moving files (the coupling inventory)

Three things assume every module lives at the repo root:

1. **Flat imports** — ~35 modules do `import digest`, `import market_data`, `from config import
   …`; satellites import `digest`. Tests import flat too. Moving modules breaks every one until
   the package is importable.
2. **Task wiring** — `setup_tasks.ps1` registers 4 scheduled tasks (MorningDigest, Watchdog,
   Backup, ReplyMonitor) whose action is `Execute <run_*.bat>` with `-WorkingDirectory <repo>`.
   Each `run_*.bat` does `cd /d %~dp0` then `.venv\Scripts\python.exe <entrypoint>.py`. If an
   entry point moves, the wrapper breaks and the task fails **silently** on its next fire.
3. **⚠ THE KILLER — module-relative data paths.** 26 modules compute `SCRIPT_DIR =
   Path(__file__).parent` and address state/secrets/data as `SCRIPT_DIR / "…"`. The server holds
   its **own untracked copies** of all of these (they are gitignored — a pull never moves them):

   - Secrets: `token.json`, `credentials.json`, `env.bat`, `substack_cookie.txt`,
     `thirteen_d_session.json`, `jpm_session.json`
   - State/caches: `memory.json`, `substack_memory.json`, `memory_v1_backup.json`,
     `alerts_config.json`, `watchlist.json`, `pacer_seen.json`, `source_counts.json`,
     `repetition_scores.json`, `ishares_oas_cache.json`, `ticker_names_cache.json`,
     `wiltw_cache.json`
   - Data dirs: `archive/` (**contains the FAISS vector index `archive/index.faiss` + metadata**),
     `digests/`, `logs/`, `jpm_recon/`

   If code moves to `src/` while `SCRIPT_DIR` still means "the module's folder," every one of
   those paths now points at `src/…` — but the server's files are at the repo root. **A pull
   moves the code, not the server's untracked data**, so the pulled code reads/writes the wrong
   place: Gmail auth fails, memory/index/caches appear empty, and it all breaks on a headless box
   with (post-7/31) no one to notice. This is the single most important hazard.

## The de-risking key: anchor data paths to the repo ROOT *first*

Do the reorg in **two phases**. Phase 0 is behavior-neutral and pull-safe on its own; it removes
the killer so Phase 1 becomes a normal change.

### Phase 0 — decouple data location from code location — ✅ DONE 2026-07-27 (`config.REPO_ROOT`)

**Shipped.** `config.REPO_ROOT` (sentinel-walk anchor: walks up to the dir holding both
`requirements.txt` and `.gitignore`) is now the single source of truth. All 17 production modules
that located root state/secret/data files by module-relative path (`SCRIPT_DIR =
Path(__file__).parent`, plus the four inline `Path(__file__).parent / "…"` anchors in
`reply_monitor`, `ishares_data`, `repetition`, `ticker_names`) now derive from `REPO_ROOT`.
Behavior-neutral (verified: every `SCRIPT_DIR`/anchor == repo root today; `token.json`,
`archive/index.faiss`, all caches resolve unchanged), ruff clean, pytest 478. Deployed as a
normal pull — no task disturbance, no server file migration. **The Phase-1 killer is now
removed**: moving code into `src/` will not move where the code looks for the server's untracked
root files, because they're addressed via `REPO_ROOT`, not the module's folder. (`config.py`
stays at root in the Phase-1 layout, so the anchor stays correct.) Design notes below kept for
reference.

*Original plan (for reference):*

Introduce a single source of truth for the repo root that does NOT change when code moves:

```python
# paths.py (new, at repo root — or in the package with an explicit anchor)
from pathlib import Path
# Anchor to the REPO ROOT regardless of where this file ends up. If paths.py
# lives at root: parent. If it moves into src/, use .parent.parent, or better,
# walk up to the dir containing a sentinel like ".git" / "requirements.txt".
def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for cand in (p.parent, *p.parents):
        if (cand / "requirements.txt").exists() and (cand / ".gitignore").exists():
            return cand
    return p.parent
REPO_ROOT = _repo_root()
```

Then replace every `SCRIPT_DIR = Path(__file__).parent` used for **state/secret/data** with an
import of `REPO_ROOT` (keep `SCRIPT_DIR` only where it genuinely means "next to this module" —
there are none of those today; all 17+ paths are root data). Net effect: `token.json`,
`memory.json`, `archive/`, etc. resolve to the repo root no matter where the module lives.

- **Verify:** `ruff check .` + `pytest` (478) green; a full dev run to `acohen` (permissioned,
  ~$5) writes/reads memory, archive, caches at the same root paths as before — diff the touched
  files vs a pre-change run.
- **Deploy:** normal `git pull` on the server. **No task disturbance, no file migration** — paths
  still resolve to the same root locations. This phase alone is a legitimate, shippable cleanup
  even if Phase 1 never happens.

### Phase 1 — move the modules (the actual reorg)

**Recommended layout (lightest touch that still tidies the root):**
- **Keep at root:** the entry points the `.bat` wrappers invoke — `digest.py`, `run_alert.py`,
  `reply_monitor.py` (and `search.py`'s CLI) — plus `run_*.bat`, `setup_tasks.ps1`, `check.bat`,
  `config.py`/`paths.py`, `requirements*.txt`, `ruff.toml`, `.gitignore`, the docs, and all the
  untracked state/secrets/data dirs.
- **Move to `src/` (a package, e.g. `src/dailydigest/`):** the ~25 library modules
  (`market_data`, `macro_data`, `news`, `ratings`, `sec_filings`, `memory`, `search`,
  `substack`, `thirteen_d`, `jpm_research`, `alert_commands`, `cost`, `archive`, `feeds`,
  `net_utils`, `html_utils`, `ticker_names`, `repetition`, `content_monitor`, the source
  fetchers, …).

Why this layout: the scheduled-task actions call `run_*.bat` → `python.exe digest.py`, and
`digest.py` stays at root, so **the wrapper commands are unchanged and the tasks may NOT need
re-registration at all** (no Shawn-password step) — the biggest server-side risk disappears.
Only the *imports* change.

**Making the package importable without a build step** (avoids `pip install -e .` on the server):
add to the top of each root entry point, before other imports:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))
```
(Or make it a real installed package with `pyproject.toml` + `pip install -e .` — cleaner, but
adds an install step to the server bring-up and to `check.bat`. For a solo tool the sys.path
insert is the pragmatic, pull-friendly choice.)

**Full-package alternative** (heavier): move the entry points into `src/` too and invoke via
`python -m dailydigest.digest`. This forces `.bat` wrapper edits AND task re-registration
(Shawn's password). Only worth it if you want zero code at root; not recommended for the payoff.

## Dev procedure (Phase 1)

1. `git switch -c reorg-src` (never on `main` directly).
2. `git mv` the library modules into `src/dailydigest/` (use `git mv` so history follows). Add
   `src/dailydigest/__init__.py`.
3. Rewrite imports: bare `import market_data` → `from dailydigest import market_data` (or add the
   sys.path insert and keep bare imports — pick one convention and apply everywhere, incl. tests
   and `tools/`).
4. Update `ruff.toml` if it has per-path rules; update `check.bat` if it names paths.
5. `ruff check .` → `pytest` (must stay 478 green) → **one permissioned full dev run to acohen**
   (`DIGEST_TO=acohen@acorninv.com`, `DIGEST_TO_TEAM=` empty — the §8 footgun). Confirm: digest
   sends, memory/archive/index/caches read+write at root, reply bot answers, weekly path imports.
6. Also dry-run `reply_monitor.py --once` and `run_alert.py digest --check-completed` (the
   satellites the daemon/watchdog use).
7. PR/merge to `main`, push.

## Server procedure (Phase 1) — schedule a maintenance window

Because Phase 0 anchored data to root, **no secret/state file migration is needed**. Steps:

1. **Announce a window** and confirm no digest (08:00), backup (09:45), or watchdog (09:00) is
   imminent.
2. **Stop the daemon + pause tasks:** `schtasks /End /TN \DailyDigest\ReplyMonitor`; disable the
   four tasks (or just ensure none fire during the window).
3. `git pull` on the box.
4. **Smoke-test each entry point manually, in order, before re-enabling:**
   - `run_digest.bat` equivalent with `DIGEST_TO=acohen` override (do NOT let it send to jared
     during the test) — or at minimum `python -c "import digest"` + a dry import of every entry.
   - `python reply_monitor.py --once`
   - `python run_alert.py digest --check-completed`
   - `python search.py --rebuild` is NOT needed (index path unchanged) — but confirm
     `search` loads `archive/index.faiss` without re-indexing.
5. **Only if you chose the full-package alternative** (entry points moved): re-run
   `setup_tasks.ps1 -StoredPassword` (needs Shawn's Windows password; S4U-only will silently
   fail to launch per HANDOFF §7.2). Otherwise skip — the wrapper commands are unchanged.
6. Restart the daemon: `schtasks /Run /TN \DailyDigest\ReplyMonitor`; re-enable tasks.
7. **Watch the next real 08:00 run's log** end-to-end before considering it done.

## Rollback

- Dev: it's a branch — abandon it.
- Server: `git reset --hard <pre-reorg-sha>` + restart ReplyMonitor. Because no data moved, the
  old code finds everything exactly where it was. Keep the pre-reorg SHA written down before the
  window.

## Repo-specific gotchas (do not relearn the hard way)

- **`credentials_JARED.json` is NOT clutter** — it's a deliberate dev-machine credentials backup
  (HANDOFF §4: "do NOT copy to the server"), gitignored. Leave it; don't "tidy" it away.
- **`env.bat` footgun** (HANDOFF §8): its `DIGEST_TO` values are the PRODUCTION recipients. Every
  dev test run must override `DIGEST_TO=acohen@acorninv.com` + `DIGEST_TO_TEAM=` empty.
- **ReplyMonitor holds old code until restarted** — any pull touching `reply_monitor.py`/
  `alert_commands.py` needs `schtasks /End`+`/Run` (HANDOFF §1).
- **The FAISS index is inside `archive/`** (`archive/index.faiss` + metadata) — treat `archive/`
  as precious state, never as a scratch dir to relocate casually.
- **Don't reintroduce removed modules** (`octus.py`, `trace_data.py`, `grab_session.py`).
- Flat-at-root is a *legitimate* choice for a solo tool; only do this reorg if the tidiness is
  worth a maintenance window. It buys organization, not capability.
