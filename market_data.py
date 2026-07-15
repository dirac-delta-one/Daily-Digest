#!/usr/bin/env python3
"""
Yahoo Finance data: the Market / Private Credit / AI snapshot sections (plus
the Yahoo rows of the Corporate Credit Snapshot), with 1D, 1W, 1M changes.
FRED data lives exclusively in macro_data.py.

2026-07-15 (jared's snapshot redesign): tickers carry a `section` tag; each
section renders its own snapshot table (Gold dropped, per the same request).
"""

import time

# Yahoo Finance tickers -> (label, unit_type, section)
# section: "market" / "private" / "ai" render their own tables;
#          "credit" rows are embedded in macro_data's Corporate Credit table.
YAHOO_TICKERS = {
    # --- Market Snapshot ---
    "^GSPC":     ("S&P 500",              "dollar", "market"),
    "^VIX":      ("VIX",                  "index",  "market"),
    "CL=F":      ("WTI Crude",            "dollar", "market"),
    "DX-Y.NYB":  ("DXY",                  "index",  "market"),
    "BTC-USD":   ("BTC",                  "dollar", "market"),
    # --- Corporate Credit Snapshot (Yahoo rows; OAS rows are FRED) ---
    "IGLB":      ("IGLB (Long-Term IG)",  "dollar", "credit"),
    "IGIB":      ("IGIB (Intermediate IG)", "dollar", "credit"),
    # --- Private Credit Snapshot ---
    "^RUT":      ("Russell 2000",         "index",  "private"),
    "ARCC":      ("ARCC (Ares Capital)",  "dollar", "private"),
    "OTF":       ("OTF (Blue Owl Tech)",  "dollar", "private"),
    "BKLN":      ("BKLN (Senior Loan ETF)", "dollar", "private"),
    # (BKLN trailing yield is appended as a derived row in fetch_market_data)
    # --- AI Snapshot ---
    "^IXIC":     ("Nasdaq Composite",     "index",  "ai"),
    "000660.KS": ("SK Hynix (KRW)",       "won",    "ai"),
    "ORCL":      ("Oracle",               "dollar", "ai"),
    "CRWV":      ("CoreWeave",            "dollar", "ai"),
}

# BBG-DATA-LICENSE WISHLIST (jared 2026-07-15; none has a free source — add
# these rows if a Bloomberg Data License / terminal feed ever lands):
#   Private Credit: S&P BDC index (SPBDCUP), BCRED '32 G-spread,
#                   ARCC '32 G-spread
#   AI:             SpaceX equity mark, SpaceX '56 G-spread,
#                   Oracle '66 G-spread, QTS G-spread,
#                   CoreWeave '32 bond price, Core Scientific '31 bond price


def _close_series(frame, tickers):
    """Per-ticker non-empty Close series from a yf.download frame (handles the
    flat single-ticker column shape as well as the multi-ticker MultiIndex)."""
    import pandas as pd

    out = {}
    close = frame["Close"]
    if isinstance(close, pd.Series):  # single-ticker flat frame
        s = close.dropna()
        if len(s) and len(tickers) == 1:
            out[tickers[0]] = s
        return out
    for t in tickers:
        try:
            s = close[t].dropna()
        except Exception:
            continue
        if len(s):
            out[t] = s
    return out


def fetch_market_data():
    """Fetch Yahoo Finance data with 1D, 1W, 1M changes."""
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance not installed — skipping market data.")
        return []

    print("  Fetching market data...")

    results = []

    tickers_str = " ".join(YAHOO_TICKERS.keys())
    try:
        data = yf.download(tickers_str, period="1mo", progress=False, threads=True)
    except Exception as e:
        print(f"  Yahoo Finance error: {e}")
        return []

    series_by_ticker = _close_series(data, list(YAHOO_TICKERS))

    # Yahoo sometimes throttles part of a threaded batch (observed 2026-07-15
    # when the batch grew 6 -> 15 tickers): the failed tickers come back as
    # empty columns and their rows would silently vanish. One unthreaded
    # retry for just the empty ones recovers them.
    missing = [t for t in YAHOO_TICKERS if t not in series_by_ticker]
    if missing:
        print(f"  Retrying {len(missing)} empty ticker(s): {' '.join(missing)}")
        time.sleep(2)
        try:
            retry = yf.download(" ".join(missing), period="1mo",
                                progress=False, threads=False)
            series_by_ticker.update(_close_series(retry, missing))
        except Exception as e:
            print(f"  Yahoo retry failed: {e}")

    for ticker, (label, unit, section) in YAHOO_TICKERS.items():
        try:
            series = series_by_ticker.get(ticker)
            if series is None:
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

            # 1M change: ~21 trading days ago (or earliest in the series).
            # >= 21, not 20: iloc[-21] needs 21 rows — at exactly 20 the old
            # guard threw IndexError and the silent except dropped the whole
            # row (latent since the original; surfaced 2026-07-15 when a
            # 1mo window returned exactly 20 US trading days).
            prev_1m = None
            if len(series) >= 21:
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
                "section": section,
                "chg_1d": chg_1d, "pct_1d": pct_1d,
                "chg_1w": chg_1w, "pct_1w": pct_1w,
                "chg_1m": chg_1m, "pct_1m": pct_1m,
                "source": f"Yahoo Finance: {ticker}",
                "as_of": as_of,
            })

        except Exception:
            continue

    # BKLN trailing 12M distribution yield (Private Credit Snapshot) — a
    # level-only row (no free daily history for the yield, so no 1D/1W/1M).
    try:
        info = yf.Ticker("BKLN").info
        y = info.get("dividendYield")
        if y:
            if y < 1:  # Yahoo sometimes returns a fraction (0.0659) vs 6.59
                y *= 100
            results.append({
                "label": "BKLN Trailing Yield",
                "value": float(y),
                "unit": "pct",
                "section": "private",
                "chg_1d": None, "pct_1d": None,
                "chg_1w": None, "pct_1w": None,
                "chg_1m": None, "pct_1m": None,
                "source": "Yahoo Finance: BKLN",
                "as_of": "",
            })
    except Exception as e:
        print(f"  BKLN yield fetch failed ({e}) — row skipped.")

    print(f"  Got {len(results)} market data points.")
    return results


# ======================================================================
# FORMATTING
# ======================================================================

def _fmt_value(label, value, unit):
    if unit == "dollar":
        if label in ("BTC", "S&P 500"):
            return f"${value:,.0f}"
        else:
            return f"${value:,.2f}"
    elif unit == "won":
        return f"₩{value:,.0f}"
    elif unit == "pct":
        return f"{value:.2f}%"
    elif unit == "index":
        return f"{value:,.2f}"
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
    elif unit == "won":
        dollar_str = ""  # KRW levels too large for a change figure, just show %
    elif unit == "index":
        dollar_str = f"{chg:+,.2f}"
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
    """The Market Snapshot table (S&P, VIX, WTI, DXY, BTC)."""
    return _build_yahoo_table(data, "market", "Market Snapshot")


def build_private_credit_html(data):
    """The Private Credit Snapshot table (RTY, ARCC, OTF, BKLN + its yield)."""
    return _build_yahoo_table(data, "private", "Private Credit Snapshot")


def build_ai_html(data):
    """The AI Snapshot table (Nasdaq, SK Hynix, Oracle, CoreWeave)."""
    return _build_yahoo_table(data, "ai", "AI Snapshot")


def table_rows_html(rows):
    """Bare <tr> rows for the given items — also embedded by macro_data's
    Corporate Credit table (its IGLB/IGIB rows are Yahoo data)."""
    html = ""
    for item in rows:
        label = item["label"]
        unit = item["unit"]

        val_str = _fmt_value(label, item["value"], unit)
        cell_1d = _fmt_change_cell(item["chg_1d"], item["pct_1d"], unit, label)
        cell_1w = _fmt_change_cell(item["chg_1w"], item["pct_1w"], unit, label)
        cell_1m = _fmt_change_cell(item["chg_1m"], item["pct_1m"], unit, label)

        td = 'style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee;'
        html += (
            f'<tr>'
            f'<td {td}">{label}</td>'
            f'<td {td} text-align: right; font-weight: 600;">{val_str}</td>'
            f'<td {td} text-align: right;">{cell_1d}</td>'
            f'<td {td} text-align: right;">{cell_1w}</td>'
            f'<td {td} text-align: right;">{cell_1m}</td>'
            f'</tr>\n'
        )
    return html


def _build_yahoo_table(data, section, title):
    """Render one section's rows as an HTML table with 1D / 1W / 1M columns."""
    data = [r for r in data if r.get("section") == section]
    if not data:
        return ""

    rows = table_rows_html(data)

    sources_seen = {}
    for item in data:
        source = item.get("source", "")
        as_of = item.get("as_of", "")
        if source:
            ticker = source.replace("Yahoo Finance: ", "")
            date_only = as_of.split(" ")[0] if as_of else ""
            sources_seen.setdefault(date_only, []).append(ticker)

    # Footnote
    footnote_parts = []
    for dt, tickers in sources_seen.items():
        suffix = f", as of {dt}" if dt else ""
        footnote_parts.append(f"Yahoo Finance: {' '.join(tickers)}{suffix}")
    footnote = " | ".join(footnote_parts)
    footnote_html = (
        f'<p style="font-size: 10px; color: #aaa; margin: 4px 0 0; line-height: 1.3;">'
        f'{footnote}</p>\n'
    ) if footnote else ""

    th = 'style="padding: 4px 8px; font-size: 11px; color: #888; border-bottom: 2px solid #ccc;'
    html = (
        '<div style="margin-bottom: 24px;">\n'
        '<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 6px; '
        f'margin: 0 0 12px;">{title}</h2>\n'
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
