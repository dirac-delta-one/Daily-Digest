#!/usr/bin/env python3
"""
Market Snapshot (Yahoo Finance only)
Pulls real-time prices with 1D, 1W, 1M changes.
FRED data lives exclusively in macro_data.py.
"""

import json
import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CACHE_FILE = SCRIPT_DIR / "market_data_cache.json"

# Yahoo Finance tickers -> (label, unit_type)
YAHOO_TICKERS = {
    "^GSPC":    ("S&P 500",   "dollar"),
    "^VIX":     ("VIX",       "index"),
    "CL=F":     ("WTI Crude", "dollar"),
    "DX-Y.NYB": ("DXY",       "index"),
    "GC=F":     ("Gold",      "dollar"),
    "BTC-USD":  ("BTC",       "dollar"),
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


def fetch_market_data():
    """Fetch Yahoo Finance data with 1D, 1W, 1M changes."""
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance not installed — skipping market data.")
        return []

    print("  Fetching market data...")

    prior_cache = _load_cache()
    results = []

    tickers_str = " ".join(YAHOO_TICKERS.keys())
    try:
        data = yf.download(tickers_str, period="1mo", progress=False, threads=True)
        close = data["Close"]
    except Exception as e:
        print(f"  Yahoo Finance error: {e}")
        return []

    for ticker, (label, unit) in YAHOO_TICKERS.items():
        try:
            series = close[ticker].dropna()
            if len(series) < 1:
                continue

            current = float(series.iloc[-1])

            # Timestamp
            ts = series.index[-1]
            as_of = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)

            # 1D change: previous trading day
            prev_1d = float(series.iloc[-2]) if len(series) >= 2 else None

            # 1W change: ~5 trading days ago
            prev_1w = None
            if len(series) >= 6:
                prev_1w = float(series.iloc[-6])
            elif label in prior_cache and "value_1w" in prior_cache[label]:
                prev_1w = prior_cache[label]["value_1w"]

            # 1M change: ~21 trading days ago (or earliest in the series)
            prev_1m = None
            if len(series) >= 20:
                prev_1m = float(series.iloc[-21])
            elif len(series) >= 15:
                prev_1m = float(series.iloc[0])

            def _calc(prev):
                if prev is None or prev == 0:
                    return None, None
                return current - prev, ((current - prev) / abs(prev)) * 100

            chg_1d, pct_1d = _calc(prev_1d)
            chg_1w, pct_1w = _calc(prev_1w)
            chg_1m, pct_1m = _calc(prev_1m)

            results.append({
                "label": label,
                "value": current,
                "unit": unit,
                "chg_1d": chg_1d, "pct_1d": pct_1d,
                "chg_1w": chg_1w, "pct_1w": pct_1w,
                "chg_1m": chg_1m, "pct_1m": pct_1m,
                "source": f"Yahoo Finance: {ticker}",
                "as_of": as_of,
            })

        except Exception:
            continue

    # Cache current + 1w-ago value for next run
    today_cache = {}
    for r in results:
        today_cache[r["label"]] = {
            "value": r["value"],
            "date": str(datetime.date.today()),
        }
    _save_cache(today_cache)

    print(f"  Got {len(results)} market data points.")
    return results


# ======================================================================
# FORMATTING
# ======================================================================

def _fmt_value(label, value, unit):
    if unit == "dollar":
        if label == "BTC":
            return f"${value:,.0f}"
        elif label in ("S&P 500", "Gold"):
            return f"${value:,.0f}"
        else:
            return f"${value:,.2f}"
    elif unit == "index":
        return f"{value:.2f}"
    return f"{value:.2f}"


def _fmt_change_cell(chg, pct, unit, label):
    """Format a change as '$ / %' string with color."""
    if chg is None:
        return '<span style="color: #999;">\u2014</span>'

    # Color: most things up=green, VIX up=red
    invert = label == "VIX"
    if chg > 0:
        color = "#c0392b" if invert else "#27ae60"
    elif chg < 0:
        color = "#27ae60" if invert else "#c0392b"
    else:
        color = "#666"

    # Dollar part
    if unit == "dollar":
        if label == "BTC":
            dollar_str = ""  # BTC too large for $ change, just show %
        elif abs(chg) >= 100:
            dollar_str = f"+${chg:,.0f}" if chg >= 0 else f"-${abs(chg):,.0f}"
        else:
            dollar_str = f"+${chg:,.2f}" if chg >= 0 else f"-${abs(chg):,.2f}"
    elif unit == "index":
        dollar_str = f"{chg:+.2f}"
    else:
        dollar_str = f"{chg:+.2f}"

    # Percent part
    pct_str = f"{pct:+.1f}%" if pct is not None else ""

    # Combine
    if dollar_str and pct_str:
        text = f"{dollar_str} / {pct_str}"
    elif pct_str:
        text = pct_str
    else:
        text = dollar_str

    return f'<span style="color: {color}; font-weight: 600;">{text}</span>'


def build_market_table_html(data):
    """Render market data as HTML table with 1D / 1W / 1M columns."""
    if not data:
        return ""

    rows = ""
    sources_seen = {}
    for item in data:
        label = item["label"]
        unit = item["unit"]
        source = item.get("source", "")
        as_of = item.get("as_of", "")
        if source:
            ticker = source.replace("Yahoo Finance: ", "")
            date_only = as_of.split(" ")[0] if as_of else ""
            sources_seen.setdefault(date_only, []).append(ticker)

        val_str = _fmt_value(label, item["value"], unit)
        cell_1d = _fmt_change_cell(item["chg_1d"], item["pct_1d"], unit, label)
        cell_1w = _fmt_change_cell(item["chg_1w"], item["pct_1w"], unit, label)
        cell_1m = _fmt_change_cell(item["chg_1m"], item["pct_1m"], unit, label)

        td = 'style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee;'
        rows += (
            f'<tr>'
            f'<td {td}">{label}</td>'
            f'<td {td} text-align: right; font-weight: 600;">{val_str}</td>'
            f'<td {td} text-align: right;">{cell_1d}</td>'
            f'<td {td} text-align: right;">{cell_1w}</td>'
            f'<td {td} text-align: right;">{cell_1m}</td>'
            f'</tr>\n'
        )

    # Footnote
    footnote_parts = []
    for dt, tickers in sources_seen.items():
        footnote_parts.append(f"Yahoo Finance: {' '.join(tickers)}, as of {dt}")
    footnote = " | ".join(footnote_parts)
    footnote_html = (
        f'<p style="font-size: 10px; color: #aaa; margin: 4px 0 0; line-height: 1.3;">'
        f'{footnote}</p>\n'
    ) if footnote else ""

    th = 'style="padding: 4px 8px; font-size: 11px; color: #888; border-bottom: 2px solid #ccc;'
    html = (
        '<div style="margin-bottom: 24px;">\n'
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 6px; '
        'margin: 0 0 12px;">Market Snapshot</h2>\n'
        '<table style="border-collapse: collapse; width: 100%;">\n'
        f'<tr>'
        f'<th {th} text-align: left;">Metric</th>'
        f'<th {th} text-align: right;">Level</th>'
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


def format_market_data_for_prompt(data):
    if not data:
        return ""

    lines = ["MARKET DATA SNAPSHOT (Yahoo Finance):"]
    for item in data:
        label = item["label"]
        val_str = _fmt_value(label, item["value"], item["unit"])

        parts = [f"{label}: {val_str}"]
        if item["chg_1d"] is not None:
            parts.append(f"1D: {item['chg_1d']:+.2f} ({item['pct_1d']:+.1f}%)")
        if item["chg_1w"] is not None:
            parts.append(f"1W: {item['chg_1w']:+.2f} ({item['pct_1w']:+.1f}%)")
        if item["chg_1m"] is not None:
            parts.append(f"1M: {item['chg_1m']:+.2f} ({item['pct_1m']:+.1f}%)")
        lines.append(f"  {' | '.join(parts)}")

    return "\n".join(lines)


if __name__ == "__main__":
    data = fetch_market_data()
    if data:
        print(format_market_data_for_prompt(data))
    else:
        print("No market data fetched.")
