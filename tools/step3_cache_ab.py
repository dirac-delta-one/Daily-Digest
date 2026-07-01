#!/usr/bin/env python3
"""
Step 3 — prompt-caching A/B for the 2-pass digest.

Compares the CURRENT 2-pass structure (pass 2 re-sends all sources+PDFs at full
price) against a RESTRUCTURED + CACHED version (unified system prompt; sources+PDFs
as an identical cached prefix; per-pass instruction in the trailing block, so pass 1
writes the cache and pass 2 reads it).

Proves two things the paid run must confirm:
  (1) the restructured pass-2 final digest is equivalent-quality to the current one,
  (2) the cache actually engages (pass-2 cache_read > 0) and the run is cheaper.

Two input modes, both requested:
  text : the archived 2026-06-30 sources (no inbox PDFs)
  pdf  : same sources + the 4.5MB WILTW PDF injected as a mock inbox attachment
         (exercises the PDF-cache path / the large-input case)

Written in the 2026-07-01 session (validated the restructure now live in
digest.summarize_with_claude — see WORKLOG); preserved in tools/ for future
re-validation (e.g. after a model bump or SYSTEM_PROMPT change). "Baseline" here
is the PRE-restructure 2-pass shape, kept verbatim for comparison. ARCHIVE pins
the frozen A/B input date — repoint it to re-run against a different archived day.

Usage:
  python tools/step3_cache_ab.py          # FREE: build + count_tokens + cost estimate, no generation
  python tools/step3_cache_ab.py --run    # PAID (~$3.50): full baseline-vs-cached, both modes —
                                          # ask permission first per HANDOFF §2
"""

import base64
import json
import sys
import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "archive" / "2026-06-30"
OUT = Path(__file__).parent / "step3_outputs"
OUT.mkdir(exist_ok=True)

sys.path.insert(0, str(REPO))

import anthropic  # noqa: E402
import digest  # noqa: E402  (reuse SYSTEM_PROMPT + _build_source_prompt)
from config import OPUS_MODEL  # noqa: E402
from cost import cost_of  # noqa: E402

MODEL = OPUS_MODEL
MAX_TOKENS = 20000

# --- verbatim from digest.summarize_with_claude (baseline pass 2) ---
BASELINE_REVIEWER_SYSTEM = (
    "You are a senior research analyst reviewing a junior analyst's daily digest. "
    "Your job is to catch anything important that was missed and produce the final version. "
    "Use the exact same HTML template and formatting as the draft. "
    "Do not add filler — only add genuinely important missed items."
)


def _baseline_review_text(draft):
    return (
        "You are reviewing a draft daily research digest against the original source material.\n\n"
        "Below is the DRAFT DIGEST, followed by ALL the original source material it was based on.\n\n"
        "Your job:\n"
        "1. Compare the draft against every source. Identify any important items that were MISSED — "
        "specific data points, trade ideas, tickers, price targets, key arguments, or surprising findings "
        "that should have been included but weren't.\n"
        "2. Check for any ERRORS — wrong numbers, misattributed sources, or mischaracterized arguments.\n"
        "3. Check that every bullet has a source tag.\n"
        "4. Produce a FINAL ENHANCED VERSION of the digest that incorporates anything missed "
        "and fixes any errors. Keep the exact same HTML template and formatting.\n\n"
        "If the draft was already comprehensive, return it mostly unchanged — don't pad it with filler.\n"
        "If you found missed items, weave them into the appropriate sections.\n\n"
        "DRAFT DIGEST:\n"
        "═══════════════════════════════════════\n"
        f"{draft}\n"
        "═══════════════════════════════════════\n\n"
        "ORIGINAL SOURCE MATERIAL:\n"
    )


# --- restructured trailing instructions (same tasks, sources are ABOVE now) ---
CACHED_GENERATE_INSTRUCTION = (
    "Using the source material above, generate today's daily research digest now, "
    "following the template and rules in the system prompt exactly."
)


def _cached_review_text(draft):
    return (
        "Above is all of today's original source material.\n\n"
        "Below is a DRAFT DIGEST you produced from it. Review the draft against the source material above:\n"
        "1. Identify any important items that were MISSED — specific data points, trade ideas, tickers, "
        "price targets, key arguments, or surprising findings that should have been included but weren't.\n"
        "2. Check for any ERRORS — wrong numbers, misattributed sources, or mischaracterized arguments.\n"
        "3. Check that every bullet has a source tag.\n"
        "4. Produce a FINAL ENHANCED VERSION of the digest that incorporates anything missed "
        "and fixes any errors. Keep the exact same HTML template and formatting.\n\n"
        "If the draft was already comprehensive, return it mostly unchanged — don't pad it with filler.\n\n"
        "DRAFT DIGEST:\n"
        "═══════════════════════════════════════\n"
        f"{draft}\n"
        "═══════════════════════════════════════\n"
    )


# ======================================================================
# Build the source content (same as digest.summarize_with_claude)
# ======================================================================

def _load(name):
    return json.loads((ARCHIVE / name).read_text(encoding="utf-8"))


def _build_content(with_pdf):
    """Return the message content array (text block [+ injected PDF])."""
    emails = _load("emails.json")
    for e in emails:
        e["pdfs"] = []  # archived emails store pdf_filenames; prompt reads e["pdfs"]

    prompt = digest._build_source_prompt(
        emails=emails,
        substack_articles=_load("substacks.json"),
        sec_filings=_load("filings.json"),
        market_data=_load("market_data.json"),
        macro_data=_load("macro_data.json"),
        memory_context="",
        earnings=[],
        trace_data=[],
        pacer_entries=_load("pacer_entries.json"),
        rating_actions=_load("rating_actions.json"),
        fund_results=_load("fund_results.json"),
        wiltw=_load("wiltw.json"),
    )
    content = [{"type": "text", "text": prompt}]

    if with_pdf:
        pdf_bytes = (ARCHIVE / "pdfs" / "WILTW_2026-06-25.pdf").read_bytes()
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        content.append({
            "type": "text",
            "text": "\n📎 PDF attachment from: Broker Desk <desk@example.com> — "
                    "Subject: Research note — File: research.pdf",
        })
        content.append({
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
        })
    return content


def _cached_shared(content):
    """Copy content and put a cache breakpoint on the last shared block."""
    shared = [dict(b) for b in content]
    shared[-1] = {**shared[-1], "cache_control": {"type": "ephemeral"}}
    return shared


def _strip_to_html(text):
    i = text.find("<div")
    return text[i:] if i > 0 else text


def _usage_row(label, usage):
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    inp = usage.input_tokens
    out = usage.output_tokens
    usd = cost_of(MODEL, inp, out, cr, cw)
    print(f"    {label:<22s} in={inp:>7,} out={out:>6,} "
          f"cache_w={cw:>7,} cache_r={cr:>7,}  ${usd:.3f}")
    return usd


# ======================================================================
# The two structures
# ======================================================================

def run_baseline(client, content):
    r1 = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                system=digest.SYSTEM_PROMPT,
                                messages=[{"role": "user", "content": content}])
    draft = r1.content[0].text
    review = [{"type": "text", "text": _baseline_review_text(draft)}]
    review.extend(content)
    r2 = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                system=BASELINE_REVIEWER_SYSTEM,
                                messages=[{"role": "user", "content": review}])
    final = _strip_to_html(r2.content[0].text)
    return draft, final, r1.usage, r2.usage


def run_cached(client, content):
    shared = _cached_shared(content)
    p1 = shared + [{"type": "text", "text": CACHED_GENERATE_INSTRUCTION}]
    r1 = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                system=digest.SYSTEM_PROMPT,
                                messages=[{"role": "user", "content": p1}])
    draft = r1.content[0].text
    p2 = shared + [{"type": "text", "text": _cached_review_text(draft)}]
    r2 = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                system=digest.SYSTEM_PROMPT,
                                messages=[{"role": "user", "content": p2}])
    final = _strip_to_html(r2.content[0].text)
    return draft, final, r1.usage, r2.usage


# ======================================================================
# Modes
# ======================================================================

def validate():
    """FREE: build both modes, count input tokens, print a spend estimate."""
    client = anthropic.Anthropic()
    print("=== FREE validation (count_tokens only, no generation) ===\n")
    for mode, with_pdf in [("text", False), ("pdf", True)]:
        content = _build_content(with_pdf)
        n_blocks = len(content)
        ct = client.messages.count_tokens(
            model=MODEL, system=digest.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        N = ct.input_tokens
        # rough estimate (out ~6k/pass @ $25/M; draft re-fed ~ small)
        pin, pout = 5.0, 25.0
        base = (2 * N / 1e6) * pin + (2 * 6000 / 1e6) * pout          # 2 passes, full re-send
        cach = (N * 1.25 / 1e6) * pin + (N * 0.1 / 1e6) * pin + (2 * 6000 / 1e6) * pout
        # verify cache_control placement
        shared = _cached_shared(content)
        cc_ok = shared[-1].get("cache_control") == {"type": "ephemeral"} and \
            all("cache_control" not in b for b in shared[:-1])
        print(f"  [{mode}] content blocks={n_blocks}  input_tokens(N)={N:,}  "
              f"cache_control_on_last_block={cc_ok}")
        print(f"        est baseline 2-pass ≈ ${base:.2f} | est cached 2-pass ≈ ${cach:.2f} "
              f"| est ongoing saving/run ≈ ${base - cach:.2f}")
        print(f"        est spend to RUN this mode (baseline+cached) ≈ ${base + cach:.2f}\n")
    print("Grand estimate for --run (both modes) is the sum of the two 'spend to RUN' lines above.")
    print("Nothing spent yet. Re-run with --run to execute the paid A/B.")


def run():
    client = anthropic.Anthropic()
    manifest = []
    print(f"[{datetime.datetime.now()}] Step 3 caching A/B — PAID run\n")
    for mode, with_pdf in [("text", False), ("pdf", True)]:
        content = _build_content(with_pdf)
        print(f"===== MODE: {mode} =====")

        print("  -- baseline (current structure) --")
        b_draft, b_final, b_u1, b_u2 = run_baseline(client, content)
        c_b1 = _usage_row("baseline pass1", b_u1)
        c_b2 = _usage_row("baseline pass2", b_u2)

        print("  -- cached (restructured) --")
        c_draft, c_final, c_u1, c_u2 = run_cached(client, content)
        c_c1 = _usage_row("cached pass1", c_u1)
        c_c2 = _usage_row("cached pass2", c_u2)

        (OUT / f"{mode}_baseline_final.html").write_text(b_final, encoding="utf-8")
        (OUT / f"{mode}_cached_final.html").write_text(c_final, encoding="utf-8")
        (OUT / f"{mode}_baseline_draft.html").write_text(b_draft, encoding="utf-8")
        (OUT / f"{mode}_cached_draft.html").write_text(c_draft, encoding="utf-8")

        base_total = c_b1 + c_b2
        cach_total = c_c1 + c_c2
        cache_read = getattr(c_u2, "cache_read_input_tokens", 0) or 0
        print(f"  MODE {mode}: baseline ${base_total:.3f} vs cached ${cach_total:.3f} "
              f"-> saving ${base_total - cach_total:.3f}/run | pass2 cache_read={cache_read:,}\n")
        manifest.append({
            "mode": mode, "baseline_usd": round(base_total, 4),
            "cached_usd": round(cach_total, 4),
            "saving_usd": round(base_total - cach_total, 4),
            "pass2_cache_read_tokens": cache_read,
            "baseline_final_chars": len(b_final), "cached_final_chars": len(c_final),
        })

    print("=" * 70)
    grand = sum(m["baseline_usd"] + m["cached_usd"] for m in manifest)
    for m in manifest:
        print(f"  {m['mode']:<5s} baseline ${m['baseline_usd']:.3f}  cached ${m['cached_usd']:.3f}  "
              f"save ${m['saving_usd']:.3f}  cache_read={m['pass2_cache_read_tokens']:,}  "
              f"(final chars: base {m['baseline_final_chars']}, cached {m['cached_final_chars']})")
    print(f"\n  GRAND SPEND for this experiment: ${grand:.2f}")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  Outputs (compare *_baseline_final.html vs *_cached_final.html) in: {OUT}")


if __name__ == "__main__":
    if "--run" in sys.argv:
        run()
    else:
        validate()
