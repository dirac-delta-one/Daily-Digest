#!/usr/bin/env python3
"""
Group B cost A/B — Opus 4.8 vs Sonnet 4.6 on four embedded/secondary Claude calls.

Faithfulness principle: isolate the MODEL as the only variable. For each call we
build the real input ONCE from the 2026-06-30 archive, then run the ACTUAL
production code path with only the model constant swapped, with every side effect
disabled (no email send, no memory.json write). Outputs + per-call cost are
captured to tools/ab_outputs/ (gitignored) for side-by-side review.

Written in the 2026-07-01 session (verdict: keep all four calls on Opus — see
WORKLOG); preserved in tools/ for future re-runs (e.g. re-testing 13D on Sonnet
with a tightened length prompt after a model bump). ARCHIVE pins the frozen A/B
input date — repoint it to re-run against a different archived day.

PAID: every invocation makes real Claude calls (~$1.89 for "all" on the
2026-06-30 inputs) — ask permission first per HANDOFF §2.

Run:  python tools/groupb_ab.py [alerts|memory|13d|reply|all]
"""

import json
import sys
import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "archive" / "2026-06-30"
OUT = Path(__file__).parent / "ab_outputs"
OUT.mkdir(exist_ok=True)

sys.path.insert(0, str(REPO))

from config import OPUS_MODEL, SONNET_MODEL  # noqa: E402
import cost  # noqa: E402

PAIRS = [("opus", OPUS_MODEL), ("sonnet", SONNET_MODEL)]

# Accumulate a run manifest: list of dicts {call, model_tier, model, usd, chars, out_file}
MANIFEST = []


def _load(name):
    return json.loads((ARCHIVE / name).read_text(encoding="utf-8"))


def _run_one(call, tier, model, fn):
    """Run fn() with cost isolation; fn returns the output text (str)."""
    cost.reset()
    print(f"\n  [{call} / {tier} / {model}] running...")
    out = fn()
    text, usd = cost.summary()
    out_str = out if isinstance(out, str) else json.dumps(out, indent=2, ensure_ascii=False, default=str)
    out_file = OUT / f"{call}_{tier}.txt"
    out_file.write_text(out_str, encoding="utf-8")
    print(text)
    MANIFEST.append({
        "call": call, "tier": tier, "model": model,
        "usd": round(usd, 4), "chars": len(out_str), "out_file": out_file.name,
    })
    return out_str


# ======================================================================
# ALERTS — alerts.evaluate_alerts(source_text), model swapped
# ======================================================================

def _reconstruct_source_text():
    """Rebuild the digest source material via the real prompt builders.

    (Substack moved out of _build_source_prompt into the trailing
    _build_substack_block — TEAM_DIGEST_SPEC; concatenated here so the
    reconstructed source matches the FULL variant's view.)"""
    import digest
    emails = _load("emails.json")
    for e in emails:            # archived emails use pdf_filenames; prompt reads e["pdfs"]
        e["pdfs"] = []
    prompt = digest._build_source_prompt(
        emails=emails,
        sec_filings=_load("filings.json"),
        market_data=_load("market_data.json"),
        macro_data=_load("macro_data.json"),
        memory_context="",       # not snapshotted for this date; identical for both models
        earnings=[],
        pacer_entries=_load("pacer_entries.json"),
        rating_actions=_load("rating_actions.json"),
        fund_results=_load("fund_results.json"),
        wiltw=_load("wiltw.json"),
    )
    substack_block = digest._build_substack_block(_load("substacks.json"))
    return prompt + ("\n\n" + substack_block if substack_block else "")


def run_alerts():
    import alerts
    source_text = _reconstruct_source_text()
    print(f"  alerts source_text: {len(source_text):,} chars (truncated to 50k in eval)")
    for tier, model in PAIRS:
        alerts.CLAUDE_MODEL = model
        _run_one("alerts", tier, model, lambda: alerts.evaluate_alerts(source_text))


# ======================================================================
# MEMORY — memory.update_memory(digest_html), _save_memory disabled
# ======================================================================

def run_memory():
    import memory
    memory._save_memory = lambda *a, **k: None   # never touch memory.json
    digest_html = (ARCHIVE / "digest.html").read_text(encoding="utf-8")
    for tier, model in PAIRS:
        memory.CLAUDE_MODEL = model
        _run_one("memory", tier, model, lambda: memory.update_memory(digest_html))


# ======================================================================
# 13D — thirteen_d._summarize_pdf(pdf_bytes), model swapped
# ======================================================================

def run_13d():
    import thirteen_d
    pdf_bytes = (ARCHIVE / "pdfs" / "WILTW_2026-06-25.pdf").read_bytes()
    print(f"  WILTW PDF: {len(pdf_bytes)/1024/1024:.2f} MB")
    for tier, model in PAIRS:
        thirteen_d.CLAUDE_MODEL = model
        _run_one("13d", tier, model, lambda: thirteen_d._summarize_pdf(pdf_bytes))


# ======================================================================
# REPLY — answer model swapped; retrieval context frozen so only the
#         answer model varies (extract queries + search run ONCE).
# ======================================================================

REPLY_QUESTION = "What is the state of private credit in H1 2026?"
REPLY_DIGEST_DATE = "2026-06-30"


def run_reply():
    import reply_monitor
    # One real query-extract (Sonnet), then freeze it so both answer runs share
    # byte-identical retrieved context — isolating the answer model.
    cost.reset()
    queries = reply_monitor._extract_search_queries(REPLY_QUESTION)
    qtext, qusd = cost.summary()
    print(f"  query-extract (shared): {queries}")
    print(qtext)
    MANIFEST.append({"call": "reply-queryextract", "tier": "sonnet",
                     "model": SONNET_MODEL, "usd": round(qusd, 4),
                     "chars": 0, "out_file": ""})
    reply_monitor._extract_search_queries = lambda *a, **k: queries

    for tier, model in PAIRS:
        reply_monitor.REPLY_MODEL = model
        _run_one("reply", tier, model,
                 lambda: reply_monitor.answer_question(REPLY_QUESTION, digest_date=REPLY_DIGEST_DATE))


# ======================================================================

RUNNERS = {"alerts": run_alerts, "memory": run_memory, "13d": run_13d, "reply": run_reply}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    order = ["alerts", "memory", "13d", "reply"] if which == "all" else [which]
    print(f"[{datetime.datetime.now()}] Group B A/B — running: {order}")
    for name in order:
        try:
            RUNNERS[name]()
        except Exception as e:
            print(f"  !! {name} FAILED: {e}")
            import traceback
            traceback.print_exc()

    # Manifest + grand total
    print("\n" + "=" * 70)
    print("A/B COST MANIFEST")
    print("=" * 70)
    grand = 0.0
    for m in MANIFEST:
        grand += m["usd"]
        print(f"  {m['call']:<20s} {m['tier']:>6s}  ${m['usd']:<7.4f}  "
              f"{m['chars']:>6d} chars  -> {m['out_file']}")
    print(f"\n  GRAND TOTAL (both models, all calls): ${grand:.2f}")
    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")
    print(f"  Outputs in: {OUT}")


if __name__ == "__main__":
    main()
