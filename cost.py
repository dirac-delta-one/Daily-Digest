#!/usr/bin/env python3
"""
Per-run Claude cost accounting (Phase A1).

A small module-level accumulator: every Claude call site records its token usage
via record(), and the entry points (digest, reply_monitor) print a
per-run total via summary(). Previously only the two Opus digest passes were
priced, so the reported cost understated the real per-run spend (memory, alerts,
13D, and the Sonnet/Haiku ranker calls were uncounted). Prices live in config.py.

This module only measures — it changes no behavior and makes no API calls.
"""

from config import (
    FABLE_PRICE_IN, FABLE_PRICE_OUT,
    OPUS_PRICE_IN, OPUS_PRICE_OUT,
    SONNET_PRICE_IN, SONNET_PRICE_OUT,
    HAIKU_PRICE_IN, HAIKU_PRICE_OUT,
)

_PRICES = {
    "fable": (FABLE_PRICE_IN, FABLE_PRICE_OUT),
    "opus": (OPUS_PRICE_IN, OPUS_PRICE_OUT),
    "sonnet": (SONNET_PRICE_IN, SONNET_PRICE_OUT),
    "haiku": (HAIKU_PRICE_IN, HAIKU_PRICE_OUT),
}

# list of recorded calls this process; reset() clears it (e.g. per reply)
_calls = []


def _tier(model):
    """Map a model id to a price tier. Defaults to fable (most expensive) so an
    unrecognized id never silently undercounts."""
    m = (model or "").lower()
    if "haiku" in m:
        return "haiku"
    if "sonnet" in m:
        return "sonnet"
    if "opus" in m:
        return "opus"
    return "fable"


def cost_of(model, input_tokens, output_tokens, cache_read=0, cache_write=0):
    """USD for one call. Cache reads bill ~0.1x input; writes ~1.25x input."""
    pin, pout = _PRICES[_tier(model)]
    return (
        (input_tokens / 1_000_000) * pin
        + (output_tokens / 1_000_000) * pout
        + (cache_read / 1_000_000) * pin * 0.1
        + (cache_write / 1_000_000) * pin * 1.25
    )


def record(label, model, usage):
    """Record one call's usage. `usage` is an Anthropic response.usage (or None)."""
    if usage is None:
        return
    _calls.append({
        "label": label,
        "model": model,
        "in": getattr(usage, "input_tokens", 0) or 0,
        "out": getattr(usage, "output_tokens", 0) or 0,
        "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    })


def reset():
    """Clear recorded calls (call at the start of a discrete unit of work)."""
    _calls.clear()


def summary():
    """Return (text, total_usd) summarizing every recorded call."""
    if not _calls:
        return "  (no Claude calls recorded)", 0.0

    lines = []
    total = 0.0
    for c in _calls:
        usd = cost_of(c["model"], c["in"], c["out"], c["cache_read"], c["cache_write"])
        total += usd
        lines.append(
            f"    {c['label']:<24s} {_tier(c['model']):>6s}  "
            f"{c['in']:>8,} in + {c['out']:>6,} out  ${usd:.3f}"
        )
    lines.append(f"  TOTAL Claude cost this run: ${total:.2f} ({len(_calls)} call(s))")
    return "\n".join(lines), total
