#!/usr/bin/env python3
"""
Content monitor (efficiency O3, 2026-07-09).

The try/except-everywhere design means a silently-broken source (expired
Substack cookie, dead 13D session, changed feed) yields an empty section, not
a crash — invisible unless someone reads the logs. This module records each
run's per-source item counts to a small rolling JSON and flags any source
that is NORMALLY nonzero but has now been zero for several consecutive runs.

"Normally nonzero" is data-driven, not a hardcoded list: a source qualifies
only if it was nonzero in at least half of the runs BEFORE the current zero
streak. That self-calibrates the noisy cases — 13F fund filings (quarterly,
share too low), CFTC COT (zero on its Thu/Fri skip days, but a 3-zero streak
can't happen on a Mon-Thu schedule unless it is genuinely broken).

digest.main calls record_and_check() after the fetch phase and merges any
signals into the same red ALERT box as the Fed-stress check — no second
email, and the warning arrives in context. The signal repeats each run until
the source recovers (deliberate: an unresolved outage should keep nagging).
"""

import datetime
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
COUNTS_FILE = SCRIPT_DIR / "source_counts.json"

KEEP_RUNS = 30       # rolling history length
STREAK = 3           # consecutive zero runs that trigger a signal
MIN_HISTORY = 3      # runs needed BEFORE the streak to judge "normally nonzero"
NORMAL_SHARE = 0.5   # nonzero share of prior runs required to qualify

# Fixed-cardinality sources (CLEANUP_SPEC 2.4): their expected item counts are
# known exactly (6 Yahoo tickers, 11 FRED series + derived 2s10s, 6 H.4.1
# series), so a PARTIAL failure is detectable — the 2026-07-14 run returned 1
# of 6 market tickers and the zero-streak rule couldn't see it. Deliberately
# NOT extended to volume-variable sources (news, emails, ratings...), where a
# floor would false-positive on quiet days.
EXPECTED_MIN = {"market_data": 6, "macro_data": 12, "fed_bs": 6}


def _load_history(path=None):
    path = path or COUNTS_FILE
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def record_counts(counts, path=None):
    """Append this run's {source: item_count} to the rolling history.

    One entry per run (not per day — a same-day rerun appends a second entry,
    which is correct: the streak logic cares about consecutive runs).
    Returns the updated history.
    """
    path = path or COUNTS_FILE
    history = _load_history(path)
    history.append({
        "date": datetime.date.today().isoformat(),
        "counts": {k: int(v) for k, v in counts.items()},
    })
    history = history[-KEEP_RUNS:]
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return history


def check_degradation(history):
    """Signals for sources at zero for the last STREAK runs that were
    normally nonzero before. Returns a list of human-readable strings."""
    if len(history) < STREAK + MIN_HISTORY:
        return []

    recent, earlier = history[-STREAK:], history[:-STREAK]
    signals = []
    for key in sorted(recent[-1]["counts"]):
        recent_vals = [run["counts"].get(key) for run in recent]
        if any(v is None or v != 0 for v in recent_vals):
            continue  # streak broken (or source too new to judge)

        earlier_vals = [run["counts"][key] for run in earlier if key in run["counts"]]
        if len(earlier_vals) < MIN_HISTORY:
            continue
        nonzero_share = sum(1 for v in earlier_vals if v > 0) / len(earlier_vals)
        if nonzero_share >= NORMAL_SHARE:
            signals.append(
                f"{key}: 0 items for {STREAK} straight runs (was nonzero in "
                f"{nonzero_share:.0%} of the prior {len(earlier_vals)} runs) — "
                "check its session/cookie/feed"
            )

    # Expected-count floors for the fixed-cardinality sources: same streak
    # shape, keyed on "below floor" instead of "zero". A source already
    # reported by the zero rule above is skipped (no double signal).
    for key, floor in sorted(EXPECTED_MIN.items()):
        if any(s.startswith(f"{key}:") for s in signals):
            continue
        recent_vals = [run["counts"].get(key) for run in recent]
        if any(v is None or v >= floor for v in recent_vals):
            continue  # streak broken (or source missing from a recent run)
        earlier_vals = [run["counts"][key] for run in earlier if key in run["counts"]]
        if len(earlier_vals) < MIN_HISTORY:
            continue
        met_share = sum(1 for v in earlier_vals if v >= floor) / len(earlier_vals)
        if met_share >= NORMAL_SHARE:
            signals.append(
                f"{key}: below its expected minimum of {floor} for {STREAK} "
                f"straight runs (latest {recent_vals[-1]}; met the floor in "
                f"{met_share:.0%} of the prior {len(earlier_vals)} runs) — "
                "partial source failure"
            )
    return signals


def record_and_check(counts, path=None):
    """Record this run's counts, then evaluate the streak rule. The one call
    digest.main makes."""
    return check_degradation(record_counts(counts, path))


if __name__ == "__main__":
    history = _load_history()
    print(f"{len(history)} recorded run(s) in {COUNTS_FILE.name}")
    for run in history[-5:]:
        nonzero = {k: v for k, v in run["counts"].items() if v}
        print(f"  {run['date']}: {len(nonzero)}/{len(run['counts'])} sources nonzero")
    signals = check_degradation(history)
    print("\nDegradation signals:" if signals else "\nNo degradation signals.")
    for s in signals:
        print(f"  {s}")
