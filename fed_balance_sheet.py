#!/usr/bin/env python3
"""
Fed Balance Sheet (H.4.1)
Pulls weekly Fed balance sheet data from FRED.
Flags discount window usage and emergency lending as stress signals.
"""

import os
import datetime

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# Series to track — verified against FRED
# Values in millions of dollars
BALANCE_SHEET_SERIES = {
    "WALCL":       "Total Assets",
    "WDTGAL":      "Discount Window",
    "WTREGEN":     "Treasury Holdings",
    "WSHOMCB":     "MBS Holdings",
    "RRPONTSYD":   "ON RRP",
    "WORAL":       "Repos",
}

# Threshold for stress alert (in millions)
DISCOUNT_WINDOW_ALERT_MM = 5000  # $5B


def fetch_fed_balance_sheet():
    """Fetch latest Fed balance sheet data from FRED."""
    if not FRED_API_KEY:
        print("  FRED_API_KEY not set — skipping Fed balance sheet.")
        return []

    try:
        from fredapi import Fred
    except ImportError:
        print("  fredapi not installed — skipping Fed balance sheet.")
        return []

    print("  Fetching Fed balance sheet (H.4.1)...")
    fred = Fred(api_key=FRED_API_KEY)
    start = datetime.date.today() - datetime.timedelta(days=60)

    results = []

    for series_id, label in BALANCE_SHEET_SERIES.items():
        try:
            data = fred.get_series(series_id, observation_start=start)
            data = data.dropna()

            if len(data) < 1:
                continue

            current = float(data.iloc[-1])
            current_date = str(data.index[-1].date())

            prior = float(data.iloc[-2]) if len(data) >= 2 else None
            wow_change = (current - prior) if prior is not None else None

            # 4-week ago
            four_wk = None
            target = datetime.date.today() - datetime.timedelta(days=28)
            for i in range(len(data) - 1, -1, -1):
                if data.index[i].date() <= target:
                    four_wk = float(data.iloc[i])
                    break
            mom_change = (current - four_wk) if four_wk is not None else None

            results.append({
                "series_id": series_id,
                "label": label,
                "value_mm": current,
                "date": current_date,
                "wow_change": wow_change,
                "mom_change": mom_change,
            })

        except Exception as e:
            print(f"    FRED {series_id} error: {e}")

    print(f"  Got {len(results)} balance sheet series.")
    return results


def check_fed_stress(results):
    """Check for stress signals. Returns list of triggered signals."""
    signals = []
    for r in results:
        if r["label"] == "Discount Window":
            if r["value_mm"] > DISCOUNT_WINDOW_ALERT_MM:
                signals.append(
                    f"Discount window at ${r['value_mm']/1000:.1f}B "
                    f"(threshold: ${DISCOUNT_WINDOW_ALERT_MM/1000:.0f}B)"
                )
            if r["wow_change"] is not None and r["wow_change"] > 2000:
                signals.append(
                    f"Discount window surged +${r['wow_change']/1000:.1f}B week-over-week"
                )
    return signals


def format_fed_bs_for_prompt(results):
    if not results:
        return ""

    date = results[0].get("date", "")
    lines = [f"FED BALANCE SHEET (H.4.1, as of {date}):"]
    for r in results:
        val = r["value_mm"]
        # Format in trillions or billions
        if val > 500_000:
            val_str = f"${val/1_000_000:.2f}T"
        elif val > 1000:
            val_str = f"${val/1000:.1f}B"
        else:
            val_str = f"${val:.0f}M"

        wow = ""
        if r["wow_change"] is not None:
            chg = r["wow_change"]
            if abs(chg) > 1000:
                wow = f" (WoW: {'+' if chg > 0 else ''}{chg/1000:.1f}B)"
            else:
                wow = f" (WoW: {'+' if chg > 0 else ''}{chg:.0f}M)"

        lines.append(f"  {r['label']:<25s} {val_str:>10s}{wow}")

    return "\n".join(lines)


def build_fed_bs_table_html(results):
    if not results:
        return ""

    date = results[0].get("date", "") if results else ""

    rows = ""
    for r in results:
        val = r["value_mm"]
        if val > 500_000:
            val_str = f"${val/1_000_000:.2f}T"
        elif val > 1000:
            val_str = f"${val/1000:.1f}B"
        else:
            val_str = f"${val:.0f}M"

        wow = r.get("wow_change")
        if wow is not None:
            if abs(wow) > 1000:
                wow_str = f"{'+' if wow > 0 else ''}{wow/1000:.1f}B"
            else:
                wow_str = f"{'+' if wow > 0 else ''}{wow:.0f}M"
            color = "#c0392b" if wow > 0 and "Discount" in r["label"] else "#666"
            if "Total" in r["label"] or "Treasury" in r["label"] or "MBS" in r["label"]:
                color = "#27ae60" if wow < 0 else "#666"  # QT = assets declining = green
            wow_cell = f'<span style="color: {color}; font-weight: 600;">{wow_str}</span>'
        else:
            wow_cell = '<span style="color: #999;">\u2014</span>'

        rows += (
            f'<tr>'
            f'<td style="padding: 3px 10px 3px 0; font-size: 12px; border-bottom: 1px solid #eee;">{r["label"]}</td>'
            f'<td style="padding: 3px 10px; font-size: 12px; border-bottom: 1px solid #eee; text-align: right; font-weight: 600;">{val_str}</td>'
            f'<td style="padding: 3px 0 3px 10px; font-size: 12px; border-bottom: 1px solid #eee; text-align: right;">{wow_cell}</td>'
            f'</tr>\n'
        )

    html = (
        '<div style="margin-bottom: 24px;">\n'
        f'<h2 style="font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 6px; '
        f'margin: 0 0 12px;">Fed Balance Sheet (H.4.1)</h2>\n'
        '<table style="border-collapse: collapse; width: 100%;">\n'
        '<tr>'
        '<th style="padding: 3px 10px 3px 0; font-size: 11px; color: #888; text-align: left; border-bottom: 2px solid #ccc;">Series</th>'
        '<th style="padding: 3px 10px; font-size: 11px; color: #888; text-align: right; border-bottom: 2px solid #ccc;">Level</th>'
        '<th style="padding: 3px 0 3px 10px; font-size: 11px; color: #888; text-align: right; border-bottom: 2px solid #ccc;">WoW Chg</th>'
        '</tr>\n'
        f'{rows}'
        '</table>\n'
        f'<p style="font-size: 10px; color: #aaa; margin: 4px 0 0;">FRED H.4.1 data, as of {date}</p>\n'
        '</div>\n'
    )
    return html


if __name__ == "__main__":
    results = fetch_fed_balance_sheet()
    if results:
        print(format_fed_bs_for_prompt(results))
        stress = check_fed_stress(results)
        if stress:
            print("\nSTRESS SIGNALS:")
            for s in stress:
                print(f"  {s}")
    else:
        print("No Fed balance sheet data.")
