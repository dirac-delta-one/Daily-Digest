#!/usr/bin/env python3
"""
Cross-section repetition metric (REDUCE_REPEATS_SPEC Idea 12, 2026-07-22).

Deterministic, $0: counts "signals" — tickers and specific figures (bps / % /
$ amounts) — that appear in 2+ scoreable sections of one assembled digest.
Logged per run and persisted to repetition_scores.json (gitignored state) so
every prompt experiment against repetition is judged by a tracked number, the
same eval-first pattern as tools/eval_retrieval.py.

Scoring surface: the ASSEMBLED variant HTML (what save_daily_digest writes),
so the live metric and any digests/*.html backfill measure the same thing by
construction. Pre-rendered data tables are excluded — 13F holdings and PACER
tables legitimately repeat tickers the digest mentions, so counting them is
noise; the appended WSJ/FT section IS scored (reader-facing repetition, the
target of Idea 13). The earnings and alert boxes render without <h2> headers,
so the h2 splitter never sees them.
"""

import datetime
import json
import re
from pathlib import Path

SCORES_PATH = Path(__file__).parent / "repetition_scores.json"
KEEP_DAYS = 180

# <h2> titles excluded from scoring (substring match).
EXCLUDED_TITLES = (
    "Snapshot",                    # the five pre-rendered market tables
    "Fed Balance Sheet",
    "Fund Position Changes",
    "Bankruptcy Court Activity",
)

# Signals come in two strengths (2026-07-22 smoke-test finding: bare percents
# collide across unrelated stories — "Bitcoin rose 2.5%" vs "CPI items >2.5%"
# — so they are counted separately and reported as "weak"):
#   STRONG — tickers, bps figures, $ amounts: near-certain same-story markers.
#   WEAK   — bare percents: suggestive only.
# The (?<![\d.]) lookbehind stops "10.50%" from also yielding a bogus "50%".
_STRONG_RE = re.compile(
    r"\$[A-Z][A-Z0-9.]{1,7}\b"                    # $TICK
    r"|(?<![\d.])\d{2,4}(?:\.\d+)?\s?bps\b"       # 978 bps / 978bps
    r"|\$\d[\d,.]*(?:bn|B|MM|m|trn)\b"            # $120bn / $500MM
)
_WEAK_RE = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d)?%")   # 40.7% / 20%

_TAG_RE = re.compile(r"<[^>]+>")


def section_texts(digest_html):
    """{h2 title: plain text} for the scoreable sections of an assembled
    digest — the model's numbered sections plus appended WSJ/FT; excluded
    titles (pre-rendered data tables) are dropped."""
    out = {}
    parts = re.split(r"<h2[^>]*>", digest_html or "")
    for p in parts[1:]:
        end = p.find("</h2>")
        if end < 0:
            continue
        title = _TAG_RE.sub(" ", p[:end]).strip()
        if not title or any(x in title for x in EXCLUDED_TITLES):
            continue
        out[title] = _TAG_RE.sub(" ", p[end:])
    return out


def repetition_score(digest_html):
    """(n_strong, n_weak, details) — counts of STRONG (ticker/bps/$) and WEAK
    (bare %) signals found in 2+ scoreable sections. details maps each such
    signal to the sorted section titles containing it, weak ones marked
    "signal (weak)". n_strong is the headline number — weak collisions are
    frequently coincidental."""
    strong, weak = {}, {}
    for title, text in section_texts(digest_html).items():
        for m in _STRONG_RE.findall(text):
            strong.setdefault(m.strip(), set()).add(title)
        for m in _WEAK_RE.findall(text):
            weak.setdefault(m.strip(), set()).add(title)
    details = {k: sorted(v) for k, v in strong.items() if len(v) >= 2}
    n_strong = len(details)
    n_weak = 0
    for k, v in weak.items():
        if len(v) >= 2:
            n_weak += 1
            details[f"{k} (weak)"] = sorted(v)
    return n_strong, n_weak, details


def record_score(variant, digest_html, today=None):
    """Compute, log, and persist one variant's score. Returns n_duplicated,
    or None on failure — never raises (metric must not break a digest run)."""
    try:
        n_strong, n_weak, details = repetition_score(digest_html)
        print(f"  Repetition: {n_strong} strong + {n_weak} weak signal(s) "
              f"in 2+ sections ({variant})")
        today = today or datetime.date.today().isoformat()
        try:
            scores = json.loads(SCORES_PATH.read_text(encoding="utf-8"))
        except Exception:
            scores = []
        scores.append({
            "date": today,
            "variant": variant,
            "n_strong": n_strong,
            "n_weak": n_weak,
            "details": details,
        })
        floor = (datetime.date.today()
                 - datetime.timedelta(days=KEEP_DAYS)).isoformat()
        scores = [s for s in scores if s.get("date", "") >= floor]
        SCORES_PATH.write_text(json.dumps(scores, indent=1), encoding="utf-8")
        return n_strong
    except Exception as e:
        print(f"  Repetition metric failed: {e} — continuing.")
        return None
