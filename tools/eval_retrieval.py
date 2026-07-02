#!/usr/bin/env python3
"""
Retrieval eval harness (MEMORY_REFACTOR_SPEC Stage 0).

Runs every golden question in tools/eval_golden.json through search.search()
and reports, per question, the rank of the first chunk that satisfies the
item's expectations — then aggregates hit@1/3/5/10 and MRR. Run it before and
after each retrieval change (reranker, hybrid, reindex) to prove the change
helped rather than guess.

Entirely local/free: embeddings run on-device, no Claude calls, no network.

Usage:
  python tools/eval_retrieval.py                 # eval at top_k=10, print report
  python tools/eval_retrieval.py --rerank        # eval the Stage-1 cross-encoder path
  python tools/eval_retrieval.py --hybrid        # eval the Stage-2 BM25+RRF path
  python tools/eval_retrieval.py --top-k 20      # deeper cutoff
  python tools/eval_retrieval.py --save baseline # also write tools/eval_results/<date>_baseline.json
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GOLDEN_FILE = Path(__file__).parent / "eval_golden.json"
RESULTS_DIR = Path(__file__).parent / "eval_results"

sys.path.insert(0, str(REPO))

from search import search  # noqa: E402


def _matches(meta, expect):
    """True if a result chunk satisfies ONE expect entry (all its fields)."""
    if "source_type" in expect and meta.get("source_type") != expect["source_type"]:
        return False
    if "source_name_contains" in expect:
        if expect["source_name_contains"].lower() not in meta.get("source_name", "").lower():
            return False
    if "text_contains_any" in expect:
        text = meta.get("text", "").lower()
        if not any(s.lower() in text for s in expect["text_contains_any"]):
            return False
    return True


def _first_match_rank(results, expects):
    """1-based rank of the first result satisfying any expect entry, or None."""
    for rank, (meta, _score) in enumerate(results, 1):
        if any(_matches(meta, e) for e in expects):
            return rank
    return None


def run_eval(top_k, rerank=False, hybrid=False):
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))["questions"]

    rows = []
    for item in golden:
        results = search(item["question"], top_k=top_k,
                         date_filter=item.get("date_filter"),
                         entity_filter=item.get("entity_filter"),
                         rerank=rerank, hybrid=hybrid)
        rank = _first_match_rank(results, item["expect"])
        top = results[0][0] if results else None
        rows.append({
            "id": item["id"],
            "date_filter": item.get("date_filter") or item.get("entity_filter"),
            "rank": rank,
            "n_results": len(results),
            "top1": (f"{top['source_type']}:{top['source_name'][:40]}" if top else "(none)"),
        })
    return rows


def summarize(rows, top_k):
    n = len(rows)
    ranks = [r["rank"] for r in rows]

    def hit_at(k):
        return sum(1 for r in ranks if r is not None and r <= k) / n

    mrr = sum(1.0 / r for r in ranks if r is not None) / n

    print(f"\n{'id':<22s} {'filter':<12s} {'rank':>5s}  {'top-1 result'}")
    print("-" * 88)
    for r in rows:
        rank_str = str(r["rank"]) if r["rank"] is not None else "MISS"
        filt = r["date_filter"] or ""
        flag = "  <-- MISS" if r["rank"] is None else ""
        print(f"{r['id']:<22s} {filt:<12s} {rank_str:>5s}  {r['top1']}{flag}")

    metrics = {
        "n_questions": n,
        "top_k": top_k,
        "hit@1": round(hit_at(1), 3),
        "hit@3": round(hit_at(3), 3),
        "hit@5": round(hit_at(5), 3),
        "hit@10": round(hit_at(10), 3),
        "mrr": round(mrr, 3),
        "misses": [r["id"] for r in rows if r["rank"] is None],
    }
    print("-" * 88)
    print(f"hit@1={metrics['hit@1']}  hit@3={metrics['hit@3']}  hit@5={metrics['hit@5']}  "
          f"hit@10={metrics['hit@10']}  MRR={metrics['mrr']}  "
          f"({n} questions, top_k={top_k})")
    if metrics["misses"]:
        print(f"misses: {', '.join(metrics['misses'])}")
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--rerank", action="store_true",
                    help="use the Stage-1 cross-encoder rerank path")
    ap.add_argument("--hybrid", action="store_true",
                    help="use the Stage-2 BM25+RRF hybrid path")
    ap.add_argument("--save", metavar="LABEL",
                    help="also write metrics+rows to tools/eval_results/<date>_<LABEL>.json")
    args = ap.parse_args()

    rows = run_eval(args.top_k, rerank=args.rerank, hybrid=args.hybrid)
    metrics = summarize(rows, args.top_k)
    metrics["rerank"] = args.rerank
    metrics["hybrid"] = args.hybrid

    if args.save:
        RESULTS_DIR.mkdir(exist_ok=True)
        out = RESULTS_DIR / f"{datetime.date.today().isoformat()}_{args.save}.json"
        out.write_text(json.dumps({"metrics": metrics, "rows": rows}, indent=2),
                       encoding="utf-8")
        print(f"saved: {out}")


if __name__ == "__main__":
    main()
