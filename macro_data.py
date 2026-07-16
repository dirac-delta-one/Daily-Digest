#!/usr/bin/env python3
"""
FRED data: the Rates Snapshot + Corporate Credit Snapshot digest sections,
plus prompt-only macro series, all with 1D, 1W, 1M changes.
Real-time prices (equities, commodities, crypto) live in market_data.py.

2026-07-15 (jared's snapshot redesign): the old "Macro Dashboard" table is
retired. The FRED series now carry a `section` tag — "rates" and "credit"
render as their own snapshot tables; "prompt" series (CPI, claims, …) are
fetched only for the Opus prompt so the §2 Market & Macro prose keeps citing
them (operator decision 2026-07-15).
"""

import os
import datetime

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# FRED series -> (label, unit_type, section, metric)
# "spread"    -> FRED returns percentage, x100 for bps; change in bps
# "rate"      -> X.XX%; change in bps (x100)
# "breakeven" -> X.XX%; change in bps (x100)
# "count"     -> XXX,XXX; change as +X,XXX
# "cpi"       -> index level; change as +X.X
# "index"     -> plain number; change as +X.XX
# section: "rates" / "credit" -> that snapshot table; "prompt" -> prompt only.
# metric: the measure shown in the table's Metric column (jared 2026-07-16 —
# a value alone doesn't say whether it's a yield, spread, or price).
FRED_SERIES = {
    # --- Rates Snapshot ---
    "DGS2":          ("2Y UST",   "rate",      "rates", "Yield"),
    "DGS10":         ("10Y UST",  "rate",      "rates", "Yield"),
    "DGS20":         ("20Y UST",  "rate",      "rates", "Yield"),
    "DGS30":         ("30Y UST",  "rate",      "rates", "Yield"),
    "T10YIE":        ("10Y",      "breakeven", "rates", "Breakeven inflation"),
    "DFII10":        ("10Y",      "rate",      "rates", "Real yield (TIPS)"),
    "DFII30":        ("30Y",      "rate",      "rates", "Real yield (TIPS)"),
    "SOFR":          ("SOFR",     "rate",      "rates", "Overnight rate"),
    # (derived, inserted in fetch: 2s20s after DGS30; 30Y breakeven
    #  = DGS30 - DFII30 after DFII10; 2s10s stays prompt-only)
    # --- Corporate Credit Snapshot (ICE BofA index OAS — the free analogs of
    #     the Bloomberg LF98/LUAC/LU3A/LU1A/LUBA/BCBA/BCBH/BCAU OAS tickers) ---
    "BAMLH0A0HYM2":  ("HY",   "spread", "credit", "Index OAS"),
    "BAMLC0A0CM":    ("IG",   "spread", "credit", "Index OAS"),
    "BAMLC0A1CAAA":  ("AAA",  "spread", "credit", "Index OAS"),
    "BAMLC0A3CA":    ("A",    "spread", "credit", "Index OAS"),
    "BAMLC0A4CBBB":  ("BBB",  "spread", "credit", "Index OAS"),
    "BAMLH0A1HYBB":  ("BB",   "spread", "credit", "Index OAS"),
    "BAMLH0A2HYB":   ("B",    "spread", "credit", "Index OAS"),
    "BAMLH0A3HYC":   ("CCC",  "spread", "credit", "Index OAS"),
    # BBG-DATA-LICENSE UPGRADE (jared 2026-07-15/16): true G-spreads for
    # HYG/LQD/IGLB/IGIB if a Bloomberg Data License ever lands — until then
    # all four ship as fund-reported portfolio OAS via ishares_data.py.
    # --- Prompt-only (the retired Macro Dashboard's other series) ---
    "T5YIE":         ("5Y",                     "breakeven", "prompt", "Breakeven inflation"),
    "ICSA":          ("Initial Jobless Claims", "count",     "prompt", "Weekly count"),
    "CPIAUCSL":      ("CPI (monthly)",          "cpi",       "prompt", "Index level"),
    "DTWEXBGS":      ("Trade-Weighted Dollar",  "index",     "prompt", "Index"),
    "DFEDTARU":      ("Fed Funds Upper",        "rate",      "prompt", "Rate"),
}

# Raw series stashed during fetch to compute the derived rows below.
_DERIVED_INPUTS = ("DGS2", "DGS10", "DGS20", "DGS30", "DFII30")


def fetch_macro_data():
    """Fetch all FRED series with current, 1D, 1W, and 1M values."""
    if not FRED_API_KEY:
        print("  FRED_API_KEY not set — skipping macro data.")
        return []

    try:
        from fredapi import Fred
    except ImportError:
        print("  fredapi not installed — skipping macro data.")
        return []

    print("  Fetching FRED macro data...")
    fred = Fred(api_key=FRED_API_KEY)
    today = datetime.date.today()
    start = today - datetime.timedelta(days=45)

    results = []
    raw_rates = {}

    for series_id, (label, unit, section, metric) in FRED_SERIES.items():
        try:
            data = fred.get_series(series_id, observation_start=start)
            data = data.dropna()

            if len(data) < 1:
                continue

            raw_current = float(data.iloc[-1])
            current_date = str(data.index[-1].date())

            # Previous day
            raw_prev_1d = float(data.iloc[-2]) if len(data) >= 2 else None

            # ~1 week ago
            week_ago = today - datetime.timedelta(days=7)
            raw_prev_1w = None
            for i in range(len(data) - 1, -1, -1):
                if data.index[i].date() <= week_ago:
                    raw_prev_1w = float(data.iloc[i])
                    break

            # ~1 month ago
            month_ago = today - datetime.timedelta(days=30)
            raw_prev_1m = None
            for i in range(len(data) - 1, -1, -1):
                if data.index[i].date() <= month_ago:
                    raw_prev_1m = float(data.iloc[i])
                    break

            # Stash raw series for the derived rows (2s10s/2s20s/30Y breakeven)
            if series_id in _DERIVED_INPUTS:
                raw_rates[series_id] = {
                    "current": raw_current,
                    "prev_1d": raw_prev_1d,
                    "prev_1w": raw_prev_1w,
                    "prev_1m": raw_prev_1m,
                    "date": current_date,
                }

            # Convert spreads to bps
            if unit == "spread":
                current = raw_current * 100
                prev_1d = raw_prev_1d * 100 if raw_prev_1d is not None else None
                prev_1w = raw_prev_1w * 100 if raw_prev_1w is not None else None
                prev_1m = raw_prev_1m * 100 if raw_prev_1m is not None else None
            else:
                current = raw_current
                prev_1d = raw_prev_1d
                prev_1w = raw_prev_1w
                prev_1m = raw_prev_1m

            chg_1d = (current - prev_1d) if prev_1d is not None else None
            chg_1w = (current - prev_1w) if prev_1w is not None else None
            chg_1m = (current - prev_1m) if prev_1m is not None else None

            results.append({
                "series_id": series_id,
                "label": label,
                "unit": unit,
                "section": section,
                "metric": metric,
                "value": current,
                "date": current_date,
                "chg_1d": chg_1d,
                "chg_1w": chg_1w,
                "chg_1m": chg_1m,
            })

        except Exception as e:
            print(f"    FRED {series_id} ({label}) error: {e}")

    # Derived rows: A - B per horizon. unit "spread" -> value/changes in bps
    # (x100); unit "breakeven" -> value in %, changes as decimal diffs (the
    # formatters x100 to bps), matching the fetched rate/breakeven rows.
    for label, metric, a_id, b_id, unit, section, after_id in (
        ("2s20s", "Curve spread",        "DGS20", "DGS2",   "spread",    "rates",  "DGS30"),
        ("30Y",   "Breakeven inflation", "DGS30", "DFII30", "breakeven", "rates",  "DFII10"),
        ("2s10s", "Curve spread",        "DGS10", "DGS2",   "spread",    "prompt", None),
    ):
        row = _derived_row(label, raw_rates.get(a_id), raw_rates.get(b_id),
                           unit=unit, section=section, metric=metric,
                           series_id=f"DERIVED:{a_id}-{b_id}")
        if row is None:
            continue
        insert_idx = next((i + 1 for i, r in enumerate(results)
                           if r["series_id"] == after_id), len(results))
        results.insert(insert_idx, row)

    print(f"  Got {len(results)} FRED series (incl. derived).")
    return results


def _derived_row(label, a, b, *, unit, section, series_id, metric=""):
    """A - B across current/1D/1W/1M from two stashed raw series (both in %).
    "spread" scales values AND changes to bps; anything else keeps % values
    with decimal-diff changes (formatters convert those to bps). Returns None
    when either input series is missing."""
    if not a or not b:
        return None
    scale = 100 if unit == "spread" else 1

    def _diff(key):
        if a.get(key) is None or b.get(key) is None:
            return None
        return round((a[key] - b[key]) * scale, 4)

    value = _diff("current")
    if value is None:
        return None
    return {
        "series_id": series_id,
        "label": label,
        "unit": unit,
        "section": section,
        "metric": metric,
        "value": value,
        "date": a["date"],
        "chg_1d": round(value - _diff("prev_1d"), 4) if _diff("prev_1d") is not None else None,
        "chg_1w": round(value - _diff("prev_1w"), 4) if _diff("prev_1w") is not None else None,
        "chg_1m": round(value - _diff("prev_1m"), 4) if _diff("prev_1m") is not None else None,
    }


# ======================================================================
# FORMATTING
# ======================================================================

def _fmt_val(label, value, unit):
    if unit == "spread":
        return f"{value:.0f} bps"
    elif unit in ("rate", "breakeven"):
        return f"{value:.2f}%"
    elif unit == "count":
        return f"{value:,.0f}"
    elif unit == "cpi":
        return f"{value:.1f}"
    elif unit == "index":
        return f"{value:.2f}"
    return f"{value:.2f}"


def _fmt_change_cell(chg, unit, label):
    """Format a change value as HTML with color."""
    if chg is None:
        return '<span style="color: #999;">\u2014</span>'

    # Color: spreads/claims up = bad (red)
    invert = unit == "spread" or "Claims" in label
    if chg > 0:
        color = "#c0392b" if invert else "#27ae60"
    elif chg < 0:
        color = "#27ae60" if invert else "#c0392b"
    else:
        color = "#666"

    # Format based on unit
    if unit == "spread":
        text = f"{chg:+.0f} bps"
    elif unit in ("rate", "breakeven"):
        bps = chg * 100
        text = f"{bps:+.0f} bps"
    elif unit == "count":
        text = f"{chg:+,.0f}"
    elif unit == "cpi":
        text = f"{chg:+.1f}"
    elif unit == "index":
        text = f"{chg:+.2f}"
    else:
        text = f"{chg:+.2f}"

    return f'<span style="color: {color}; font-weight: 600;">{text}</span>'


def format_macro_for_prompt(data):
    if not data:
        return ""

    lines = ["FRED MACRO DATA (current | 1D | 1W | 1M):"]
    for item in data:
        # Label + metric so short row names stay unambiguous in the prompt
        # (e.g. "10Y Breakeven inflation" vs "10Y Real yield (TIPS)").
        label = f"{item['label']} {item.get('metric', '')}".strip()
        unit = item["unit"]
        val_str = _fmt_val(label, item["value"], unit)

        def _chg_str(chg):
            if chg is None:
                return "n/a"
            if unit == "spread":
                return f"{chg:+.0f} bps"
            elif unit in ("rate", "breakeven"):
                return f"{chg*100:+.0f} bps"
            elif unit == "count":
                return f"{chg:+,.0f}"
            elif unit == "cpi":
                return f"{chg:+.1f}"
            return f"{chg:+.2f}"

        d1 = _chg_str(item["chg_1d"])
        w1 = _chg_str(item["chg_1w"])
        m1 = _chg_str(item["chg_1m"])
        lines.append(f"  {label}: {val_str} | 1D: {d1} | 1W: {w1} | 1M: {m1}")

    return "\n".join(lines)


def build_rates_table_html(data):
    """The Rates Snapshot table (jared's 2026-07-15 snapshot redesign)."""
    return _build_fred_table(
        [r for r in data if r.get("section") == "rates"], "Rates Snapshot")


def build_credit_table_html(data, yahoo_data=None):
    """The Corporate Credit Snapshot: FRED ICE BofA OAS rows + the Yahoo IG
    ETF rows (IGLB/IGIB) from market_data, rendered as one table."""
    extra_rows, extra_footnote = "", ""
    if yahoo_data:
        import market_data
        credit_rows = [r for r in yahoo_data if r.get("section") == "credit"]
        extra_rows = market_data.table_rows_html(credit_rows)
        tickers = " ".join(r["source"].replace("Yahoo Finance: ", "")
                           for r in credit_rows if r.get("source"))
        if tickers:
            extra_footnote = f" | Yahoo Finance: {tickers}"
    credit_rows = [r for r in data if r.get("section") == "credit"]
    suffix = " — OAS = ICE BofA index option-adjusted spreads"
    if any(str(r.get("series_id", "")).startswith("ISHARES:") for r in credit_rows):
        suffix += "; Portfolio OAS rows = fund-reported (ishares.com)"
    return _build_fred_table(
        credit_rows,
        "Corporate Credit Snapshot",
        extra_rows_html=extra_rows,
        footnote_suffix=f"{suffix}{extra_footnote}",
    )


def table_rows_html(rows):
    """Bare <tr> rows for the given FRED items — also embedded by
    market_data's Market Snapshot table (its 20Y UST row is FRED data).
    Columns: name | metric | value | 1D | 1W | 1M (jared 2026-07-16)."""
    html = ""
    for item in rows:
        label = item["label"]
        unit = item["unit"]
        metric = item.get("metric", "")

        val_str = _fmt_val(label, item["value"], unit)
        cell_1d = _fmt_change_cell(item["chg_1d"], unit, label)
        cell_1w = _fmt_change_cell(item["chg_1w"], unit, label)
        cell_1m = _fmt_change_cell(item["chg_1m"], unit, label)

        td = 'style="padding: 3px 8px; font-size: 12px; border-bottom: 1px solid #eee;'
        html += (
            f'<tr>'
            f'<td {td}">{label}</td>'
            f'<td {td} color: #888;">{metric}</td>'
            f'<td {td} text-align: right; font-weight: 600;">{val_str}</td>'
            f'<td {td} text-align: right;">{cell_1d}</td>'
            f'<td {td} text-align: right;">{cell_1w}</td>'
            f'<td {td} text-align: right;">{cell_1m}</td>'
            f'</tr>\n'
        )
    return html


def _build_fred_table(data, title, extra_rows_html="", footnote_suffix=""):
    """Render FRED rows as an HTML table with 1D / 1W / 1M columns."""
    if not data and not extra_rows_html:
        return ""

    rows = table_rows_html(data)
    footnote_parts = []
    for item in data:
        series_id = item.get("series_id", "")
        data_date = item.get("date", "")
        if series_id and data_date:
            footnote_parts.append(f"{series_id} ({data_date})")

    footnote_html = ""
    if footnote_parts or footnote_suffix:
        footnote_html = (
            '<p style="font-size: 10px; color: #aaa; margin: 4px 0 0; line-height: 1.3;">'
            f'FRED: {", ".join(footnote_parts)}{footnote_suffix}</p>\n'
        )

    th = 'style="padding: 3px 8px; font-size: 11px; color: #888; border-bottom: 2px solid #ccc;'
    html = (
        '<div style="margin-bottom: 24px;">\n'
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 6px; '
        f'margin: 0 0 12px;">{title}</h2>\n'
        '<table style="border-collapse: collapse; width: 100%;">\n'
        f'<tr>'
        f'<th {th} text-align: left;">Name</th>'
        f'<th {th} text-align: left;">Metric</th>'
        f'<th {th} text-align: right;">Level</th>'
        f'<th {th} text-align: right;">1D</th>'
        f'<th {th} text-align: right;">1W</th>'
        f'<th {th} text-align: right;">1M</th>'
        f'</tr>\n'
        f'{rows}'
        f'{extra_rows_html}'
        '</table>\n'
        f'{footnote_html}'
        '</div>\n'
    )
    return html


if __name__ == "__main__":
    data = fetch_macro_data()
    if data:
        print(format_macro_for_prompt(data))
    else:
        print("No macro data fetched.")
