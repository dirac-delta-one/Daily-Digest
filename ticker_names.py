#!/usr/bin/env python3
"""
Ticker → issuer-name glossary for the digest prompt (operator 2026-07-22).

Why: the SYSTEM_PROMPT requires "$TICK (Name)" pairing but forbids Opus from
guessing names not present in the source material (anti-hallucination). Broker
run lists cite bond-desk shorthand ($BRASKM, $VMED) with no name in sight, so
those stayed bare. This module injects verified names INTO the prompt so the
no-guessing rule is satisfied instead of relaxed.

Two name sources, merged at build time (learned wins — its names come from
research prose and read better than SEC registry titles):
- SEC company_tickers.json titles, via sec_filings.company_names() — a
  non-downloading accessor: it exposes the map the fetch phase already loaded,
  so prompt-building never touches the network (and unit tests stay hermetic).
- ticker_names_cache.json — pairings the digest itself printed ("$TICK (Name)")
  whose name string appears verbatim in that day's source text. The validation
  mirrors the prompt's no-guessing rule: a name Opus hallucinated (absent from
  sources) is never cached, so one bad pairing can't poison future digests.

Cache-write discipline (TEAM_DIGEST_SPEC): the TEAM prompt must stay a
byte-identical prefix of the FULL prompt, and both variants build their
glossary from this cache. A write between the two generations would fork the
prefix and break the shared prompt cache — so capture only STAGES pairs in
memory (collect()); digest.main() calls commit() once, after both variants.

Substack provenance is fine here (operator 2026-07-22): a ticker→name mapping
is public metadata, not paid content, so pairs learned from Substack prose may
serve future TEAM digests. Tickers appearing only inside PDF attachments are
not seen (PDFs ride as document blocks, not prompt text) — accepted.
"""

import json
import re
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "ticker_names_cache.json"  # gitignored (*_cache.json)

MAX_GLOSSARY_LINES = 80

# Caps tokens Opus (or a source) may $-prefix that are not issuers — never
# learned, never emitted. Keep sorted-ish for scanability.
NON_TICKERS = frozenset({
    "A", "AA", "AAA", "ABS", "AI", "B", "BB", "BBB", "BDC", "BN", "CCC",
    "CDS", "CDX", "CLO", "CMBS", "CNY", "CPI", "DM", "EM", "EPS", "ETF",
    "EU", "EUR", "FED", "FOMC", "GBP", "GDP", "GSIB", "HY", "IG", "IPO",
    "JPY", "LBO", "LIBOR", "LME", "M", "MBS", "MM", "MOM", "NAV", "NII",
    "OAS", "PIK", "PT", "QE", "QOQ", "QT", "REIT", "RMBS", "SOFR", "UK",
    "US", "USD", "UST", "VIX", "YOY", "YTD",
})

# Suffix tokens kept uppercase when title-casing SEC registry names.
_KEEP_UPPER = frozenset({
    "LLC", "LP", "PLC", "NV", "SA", "AG", "SE", "AB", "ASA", "USA",
    "ADR", "II", "III", "IV",
})

# $-prefixed ticker anywhere; bare caps tokens are matched only against the
# learned cache (small + curated — matching them against the 10k-entry SEC
# registry would hit ordinary uppercase words like ALL/IT/ON).
_DOLLAR_TICK_RE = re.compile(r"\$([A-Z][A-Z0-9.]{0,7})\b")
_BARE_TOKEN_RE = re.compile(r"\b([A-Z][A-Z0-9]{2,7})\b")

# "$TICK (Name)" as rendered in a tag-stripped digest. Non-greedy, no nesting.
_PAIR_RE = re.compile(r"\$([A-Z][A-Z0-9.]{0,7})\s*\(([^()]{2,60}?)\)")

# Reverse form "Name ($TICK)" — up to 4 capitalized words directly before the
# parenthesized ticker (e.g. "Gray Media ($GTN)"). Same source-text validation
# applies, so an over-greedy capture ("in Gray Media") just fails validation.
_PAIR_REV_RE = re.compile(
    r"\b((?:[A-Z][\w&.'’-]*\s+){0,3}[A-Z][\w&.'’-]*)\s*\(\$([A-Z][A-Z0-9.]{0,7})\)")

_TAG_RE = re.compile(r"<[^>]+>")

_cache = None          # lazy-loaded {ticker: name}
_pending = {}          # pairs staged by collect(), merged by commit()


def _load_cache():
    global _cache
    if _cache is None:
        try:
            _cache = {str(k).upper(): str(v)
                      for k, v in json.loads(CACHE_PATH.read_text(encoding="utf-8")).items()}
        except Exception:
            _cache = {}
    return _cache


def _titlecase_registry_name(name):
    """SEC titles arrive ALL-CAPS ("ORACLE CORP", "BRASKEM SA /ADR/") — make
    them readable without mangling entity suffixes."""
    name = re.sub(r"\s*/([A-Z]{2,3})/?\s*$", "", name.strip())  # trailing /DE/, /ADR/
    words = []
    for w in name.split():
        words.append(w if w.upper() in _KEEP_UPPER or "&" in w else w.capitalize())
    return " ".join(words)


def known_names(sec_names=None):
    """Merged {ticker: display name}: learned cache over title-cased SEC
    registry names. `sec_names` is sec_filings.company_names() (or None)."""
    merged = {}
    for t, n in (sec_names or {}).items():
        t = t.upper()
        if t not in NON_TICKERS and n:
            merged[t] = _titlecase_registry_name(n)
    merged.update(_load_cache())
    return merged


def extract_tickers(text):
    """Tickers present in `text`: any $-prefixed caps token, plus bare caps
    tokens that are keys of the LEARNED cache (see _BARE_TOKEN_RE note).
    Includes tickers with no known name — build_glossary filters those."""
    found = {t for t in _DOLLAR_TICK_RE.findall(text) if t not in NON_TICKERS}
    learned = _load_cache()
    if learned:
        found |= {t for t in _BARE_TOKEN_RE.findall(text)
                  if t in learned and t not in NON_TICKERS}
    return found


def build_glossary(text, sec_names=None, exclude=frozenset()):
    """(glossary block text or "", set of tickers emitted) for the tickers in
    `text` with a known name. Sorted + capped, so identical inputs give
    byte-identical output (the TEAM/FULL shared-prefix requirement)."""
    names = known_names(sec_names)
    ticks = sorted(t for t in extract_tickers(text)
                   if t in names and t not in exclude)
    if not ticks:
        return "", set()
    if len(ticks) > MAX_GLOSSARY_LINES:
        print(f"  Ticker glossary capped at {MAX_GLOSSARY_LINES} "
              f"(dropped {len(ticks) - MAX_GLOSSARY_LINES}).")
        ticks = ticks[:MAX_GLOSSARY_LINES]
    lines = "\n".join(f"${t} = {names[t]}" for t in ticks)
    block = (
        "TICKER GLOSSARY — issuer names for tickers appearing in today's sources\n"
        "(verified against the SEC registry and prior digests; treat these as source\n"
        'material when rendering "$TICK (Name)"):\n' + lines
    )
    return block, set(ticks)


def collect(digest_text, source_text, known=None):
    """Stage "$TICK (Name)" pairs found in a generated digest, keeping only
    names that appear verbatim in `source_text` (the full prompt text — NOT
    the truncated alert window). No disk write here — see module docstring."""
    text = _TAG_RE.sub(" ", digest_text or "")
    hay = (source_text or "").lower()
    staged = 0
    pairs = _PAIR_RE.findall(text)
    pairs += [(t, n) for n, t in _PAIR_REV_RE.findall(text)]
    for tick, raw_name in pairs:
        if tick in NON_TICKERS:
            continue
        name = raw_name.split(",")[0].strip()
        # "/" = multi-issuer parenthetical ("Corebridge/Equitable"); an
        # all-caps short name is ticker-shaped junk like "$ABC (ABC)" — but
        # mixed case matching the ticker is a real name (Teva/$TEVA).
        if (len(name) < 2 or "$" in name or "/" in name
                or (name.isupper() and len(name) <= 8)):
            continue
        # Proper-noun guard: a company name starts with a capital. This is what
        # rejects descriptive parentheticals the model sometimes writes in the
        # name slot — "$SDZSW (potential USD issuer)", "$VTRS (already
        # crossover)" (observed on Fable 5, 2026-07-22) — which the source-text
        # check below would otherwise wave through (the PHRASE is in the
        # sources; it just isn't a name). Rare lowercase brands (eBay) are the
        # accepted cost. A leading "$"/"(" is already screened above.
        if not name[:1].isupper():
            continue
        if name.lower() not in hay:
            continue  # not in sources -> possibly hallucinated -> never cache
        if known and known.get(tick, "").lower() == name.lower():
            continue  # already known as-is
        if _pending.get(tick, "").lower() != name.lower():
            _pending[tick] = name
            staged += 1
    return staged


def commit():
    """Merge staged pairs into the cache file. Called once per run by
    digest.main() AFTER both variants have generated (never between them —
    that would fork the shared prompt-cache prefix)."""
    if not _pending:
        return 0
    cache = dict(_load_cache())
    changed = 0
    for t, n in _pending.items():
        if cache.get(t) != n:
            cache[t] = n
            changed += 1
    _pending.clear()
    if changed:
        try:
            CACHE_PATH.write_text(
                json.dumps(dict(sorted(cache.items())), indent=1, ensure_ascii=False),
                encoding="utf-8")
            global _cache
            _cache = cache
        except Exception as e:
            print(f"  Ticker-name cache write failed: {e}")
            return 0
    return changed
