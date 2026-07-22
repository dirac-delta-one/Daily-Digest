#!/usr/bin/env python3
"""
Yahoo Finance data: the Market / Private Credit / AI snapshot sections (plus
the Yahoo rows of the Corporate Credit Snapshot), with 1D, 1W, 1M changes.
FRED data lives exclusively in macro_data.py.

2026-07-15 (jared's snapshot redesign): tickers carry a `section` tag; each
section renders its own snapshot table (Gold dropped, per the same request).
"""

import time

# Yahoo Finance tickers -> (label, unit_type, section, metric)
# section: "market" / "private" / "ai" render their own tables;
#          "credit" rows are embedded in macro_data's Corporate Credit table.
# metric: the measure shown in the table's Metric column (jared 2026-07-16 —
# a value alone doesn't say whether it's a yield, spread, or price).
YAHOO_TICKERS = {
    # --- Market Snapshot ---
    "^GSPC":     ("S&P 500",              "dollar", "market",  "Index"),
    "^VIX":      ("VIX",                  "index",  "market",  "Index"),
    "CL=F":      ("WTI Crude",            "dollar", "market",  "Price"),
    "DX-Y.NYB":  ("DXY",                  "index",  "market",  "Index"),
    "BTC-USD":   ("BTC",                  "dollar", "market",  "Price"),
    # (IGLB/IGIB moved to ishares_data.py 2026-07-16 — jared wanted their
    #  spread, not price; the fund-reported Portfolio OAS is scraped from
    #  ishares.com and rendered in the Corporate Credit Snapshot.)
    # --- Private Credit Snapshot ---
    "^RUT":      ("Russell 2000",         "index",  "private", "Index"),
    "ARCC":      ("ARCC (Ares Capital)",  "dollar", "private", "Share price"),
    "OTF":       ("OTF (Blue Owl Tech)",  "dollar", "private", "Share price"),
    "BKLN":      ("BKLN (Senior Loan)",   "dollar", "private", "ETF price"),
    # (BKLN trailing yield is appended as a derived row in fetch_market_data)
    # --- AI Snapshot ---
    "^IXIC":     ("Nasdaq Composite",     "index",  "ai",      "Index"),
    "SPCX":      ("SpaceX",               "dollar", "ai",      "Share price"),
    "NVDA":      ("NVIDIA",               "dollar", "ai",      "Share price"),
    "TSM":       ("TSMC (ADR)",           "dollar", "ai",      "Share price"),
    "INTC":      ("Intel",                "dollar", "ai",      "Share price"),
    "MU":        ("Micron",               "dollar", "ai",      "Share price"),
    "000660.KS": ("SK Hynix",             "won",    "ai",      "Share price (KRW)"),
    "ORCL":      ("Oracle",               "dollar", "ai",      "Share price"),
    "CRWV":      ("CoreWeave",            "dollar", "ai",      "Share price"),
}

# BBG-DATA-LICENSE WISHLIST (jared 2026-07-15; none has a free source — add
# these rows if a Bloomberg Data License / terminal feed ever lands):
#   Private Credit: S&P BDC index (SPBDCUP), BCRED '32 G-spread,
#                   ARCC '32 G-spread
#   AI:             SpaceX '56 G-spread, Oracle '66 G-spread, QTS G-spread,
#                   CoreWeave '32 bond price, Core Scientific '31 bond price
#   (SpaceX EQUITY came off this list 2026-07-16: it IPO'd June 12, 2026 as
#    Nasdaq SPCX — now a normal Yahoo row above.)


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

    for ticker, (label, unit, section, metric) in YAHOO_TICKERS.items():
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
                "metric": metric,
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
                "label": "BKLN (Senior Loan)",
                "value": float(y),
                "unit": "pct",
                "section": "private",
                "metric": "12M dist. yield",
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


# Non-Yahoo rows (by series_id) mirrored into the Market Snapshot in ADDITION
# to their own snapshot section (jared 2026-07-16: 20Y UST in Market AND
# Rates; HYG/LQD OAS in Market AND Corporate Credit). The rows come from the
# combined macro_data + ishares_data fetch lists digest passes in.
MARKET_FRED_EXTRAS = ("DGS20", "ISHARES:HYG", "ISHARES:LQD")


def build_market_table_html(data, fred_data=None):
    """The Market Snapshot table (S&P, VIX, WTI, DXY, BTC + the FRED/iShares
    extras above when `fred_data` — the combined macro_data + ishares_data
    fetch result — is provided). The footnote cites only the sources whose
    rows actually landed: DGS20 → FRED; ISHARES:* → the fund-reported note
    (same wording as the Corporate Credit table's)."""
    extra_rows, footnote_suffix, note_suffix = "", "", ""
    if fred_data:
        import macro_data
        extras = [r for r in fred_data if r.get("series_id") in MARKET_FRED_EXTRAS]
        if extras:
            extra_rows = macro_data.table_rows_html(extras)
            if any(not str(r["series_id"]).startswith("ISHARES:") for r in extras):
                footnote_suffix = " · FRED"
            if any(str(r["series_id"]).startswith("ISHARES:") for r in extras):
                note_suffix = " · Portfolio OAS rows = fund-reported (ishares.com)"
    return _build_yahoo_table(data, "market", "Market Snapshot",
                              extra_rows_html=extra_rows,
                              footnote_suffix=footnote_suffix,
                              note_suffix=note_suffix)


def build_private_credit_html(data):
    """The Private Credit Snapshot table (RTY, ARCC, OTF, BKLN + its yield)."""
    return _build_yahoo_table(data, "private", "Private Credit Snapshot")


def build_ai_html(data):
    """The AI Snapshot table (Nasdaq, SK Hynix, Oracle, CoreWeave)."""
    return _build_yahoo_table(data, "ai", "AI Snapshot")


def table_rows_html(rows):
    """Bare <tr> rows for the given items — also embedded by macro_data's
    Corporate Credit table (its IGLB/IGIB rows are Yahoo data).
    Columns: name | metric | value | 1D | 1W | 1M (jared 2026-07-16)."""
    html = ""
    for item in rows:
        label = item["label"]
        unit = item["unit"]
        metric = item.get("metric", "")

        val_str = _fmt_value(label, item["value"], unit)
        cell_1d = _fmt_change_cell(item["chg_1d"], item["pct_1d"], unit, label)
        cell_1w = _fmt_change_cell(item["chg_1w"], item["pct_1w"], unit, label)
        cell_1m = _fmt_change_cell(item["chg_1m"], item["pct_1m"], unit, label)

        td = 'style="padding: 4px 8px; font-size: 12px; border-bottom: 1px solid #eee;'
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


def _build_yahoo_table(data, section, title, extra_rows_html="", footnote_suffix="",
                       note_suffix=""):
    """Render one section's rows as an HTML table with 1D / 1W / 1M columns.
    Footnote shape matches macro_data's: sources (suffix) before the as-of
    date, definitions (note_suffix) trailing after it."""
    data = [r for r in data if r.get("section") == section]
    if not data:
        return ""

    rows = table_rows_html(data)

    # Footnote — minimal: one source line + the latest "as of" across rows.
    # (No per-ticker enumeration; the rows already name each instrument. This
    # replaced a per-date grouping that produced a long, fragmented line when
    # instruments carried different as-of timestamps.)
    dates = [item["as_of"].split(" ")[0] for item in data if item.get("as_of")]
    latest = max(dates) if dates else ""
    footnote = ("Source: Yahoo Finance" + footnote_suffix
                + (f", as of {latest}" if latest else "") + note_suffix)
    footnote_html = (
        '<p style="font-size: 10px; color: #aaa; margin: 4px 0 0; line-height: 1.3;">'
        f'{footnote}</p>\n'
    )

    th = 'style="padding: 4px 8px; font-size: 11px; color: #888; border-bottom: 2px solid #ccc;'
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


def format_market_data_for_prompt(data):
    if not data:
        return ""

    lines = ["MARKET DATA SNAPSHOT (Yahoo Finance):"]
    for item in data:
        # Label + metric so short row names stay unambiguous in the prompt
        # (e.g. "BKLN (Senior Loan) ETF price" vs "... 12M dist. yield").
        label = f"{item['label']} {item.get('metric', '')}".strip()
        val_str = _fmt_value(item["label"], item["value"], item["unit"])

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
