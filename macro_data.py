#!/usr/bin/env python3
"""
Macro Dashboard (FRED only)
Rates, spreads, and economic data with 1D, 1W, 1M changes.
Real-time prices (equities, commodities, crypto) live in market_data.py.
"""

import os
import json
import datetime
from pathlib import Path

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

SCRIPT_DIR = Path(__file__).parent
CACHE_FILE = SCRIPT_DIR / "fred_cache.json"

# FRED series -> (label, unit_type)
# "spread"    -> FRED returns percentage, x100 for bps; change in bps
# "rate"      -> X.XX%; change in bps (x100)
# "breakeven" -> X.XX%; change in bps (x100)
# "count"     -> XXX,XXX; change as +X,XXX
# "cpi"       -> index level; change as +X.X
# "index"     -> plain number; change as +X.XX
FRED_SERIES = {
    "BAMLH0A0HYM2": ("HY OAS",                  "spread"),
    "BAMLC0A0CM":    ("IG OAS",                  "spread"),
    "DGS10":         ("10Y UST",                 "rate"),
    "DGS2":          ("2Y UST",                  "rate"),
    "T10YIE":        ("10Y Breakeven Inflation",  "breakeven"),
    "T5YIE":         ("5Y Breakeven Inflation",   "breakeven"),
    "ICSA":          ("Initial Jobless Claims",   "count"),
    "CPIAUCSL":      ("CPI (monthly)",            "cpi"),
    "DTWEXBGS":      ("Trade-Weighted Dollar",    "index"),
    "DFEDTARU":      ("Fed Funds Upper",          "rate"),
    "SOFR":          ("SOFR",                     "rate"),
}


def _load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(data):
    CACHE_FILE.write_text(json.dumps(data, indent=2))


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
    cache = _load_cache()
    raw_rates = {}

    for series_id, (label, unit) in FRED_SERIES.items():
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

            # Stash raw rates for 2s10s
            if label in ("10Y UST", "2Y UST"):
                raw_rates[label] = {
                    "current": raw_current,
                    "prev_1d": raw_prev_1d,
                    "prev_1w": raw_prev_1w,
                    "prev_1m": raw_prev_1m,
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
                "value": current,
                "date": current_date,
                "chg_1d": chg_1d,
                "chg_1w": chg_1w,
                "chg_1m": chg_1m,
            })

            cache[series_id] = {"label": label, "value": current, "date": current_date}

        except Exception as e:
            print(f"    FRED {series_id} ({label}) error: {e}")

    # Derive 2s10s spread (in bps)
    if "10Y UST" in raw_rates and "2Y UST" in raw_rates:
        ten = raw_rates["10Y UST"]
        two = raw_rates["2Y UST"]

        def _spread(t, tw):
            if t is not None and tw is not None:
                return round((t - tw) * 100, 1)
            return None

        spread_now = _spread(ten["current"], two["current"])
        spread_1d = _spread(ten["prev_1d"], two["prev_1d"])
        spread_1w = _spread(ten["prev_1w"], two["prev_1w"])
        spread_1m = _spread(ten["prev_1m"], two["prev_1m"])

        ten_date = next((r["date"] for r in results if r["label"] == "10Y UST"), str(today))

        insert_idx = next((i + 1 for i, r in enumerate(results) if r["label"] == "2Y UST"), len(results))
        results.insert(insert_idx, {
            "series_id": "DERIVED:DGS10-DGS2",
            "label": "2s10s Spread",
            "unit": "spread",
            "value": spread_now,
            "date": ten_date,
            "chg_1d": round(spread_now - spread_1d, 1) if spread_1d is not None else None,
            "chg_1w": round(spread_now - spread_1w, 1) if spread_1w is not None else None,
            "chg_1m": round(spread_now - spread_1m, 1) if spread_1m is not None else None,
        })

    _save_cache(cache)
    print(f"  Got {len(results)} FRED series (incl. derived).")
    return results


# ======================================================================
# FORMATTING
# ======================================================================

def _fmt_val(label, value, unit):
    if unit == "spread":
        return f"{value:.0f} bps"
    elif unit in ("rate", "breakeven"):
        return f"{value:.2f}%"
    elif unit == "dollar":
        return f"${value:,.2f}"
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
    elif unit == "dollar":
        text = f"+${chg:,.2f}" if chg >= 0 else f"-${abs(chg):,.2f}"
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
        label = item["label"]
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


def build_macro_table_html(data):
    """Render macro data as HTML table with 1D / 1W / 1M columns."""
    if not data:
        return ""

    rows = ""
    footnote_parts = []
    for item in data:
        label = item["label"]
        unit = item["unit"]
        series_id = item.get("series_id", "")
        data_date = item.get("date", "")

        if series_id and data_date:
            footnote_parts.append(f"{series_id} ({data_date})")

        val_str = _fmt_val(label, item["value"], unit)
        cell_1d = _fmt_change_cell(item["chg_1d"], unit, label)
        cell_1w = _fmt_change_cell(item["chg_1w"], unit, label)
        cell_1m = _fmt_change_cell(item["chg_1m"], unit, label)

        td = 'style="padding: 3px 8px; font-size: 12px; border-bottom: 1px solid #eee;'
        rows += (
            f'<tr>'
            f'<td {td}">{label}</td>'
            f'<td {td} text-align: right; font-weight: 600;">{val_str}</td>'
            f'<td {td} text-align: right;">{cell_1d}</td>'
            f'<td {td} text-align: right;">{cell_1w}</td>'
            f'<td {td} text-align: right;">{cell_1m}</td>'
            f'</tr>\n'
        )

    footnote_html = ""
    if footnote_parts:
        footnote_html = (
            '<p style="font-size: 10px; color: #aaa; margin: 4px 0 0; line-height: 1.3;">'
            f'FRED: {", ".join(footnote_parts)}</p>\n'
        )

    th = 'style="padding: 3px 8px; font-size: 11px; color: #888; border-bottom: 2px solid #ccc;'
    html = (
        '<div style="margin-bottom: 24px;">\n'
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 6px; '
        'margin: 0 0 12px;">Macro Dashboard</h2>\n'
        '<table style="border-collapse: collapse; width: 100%;">\n'
        f'<tr>'
        f'<th {th} text-align: left;">Series</th>'
        f'<th {th} text-align: right;">Current</th>'
        f'<th {th} text-align: right;">1D</th>'
        f'<th {th} text-align: right;">1W</th>'
        f'<th {th} text-align: right;">1M</th>'
        f'</tr>\n'
        f'{rows}'
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
