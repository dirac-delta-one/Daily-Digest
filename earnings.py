#!/usr/bin/env python3
"""
Earnings Calendar
Flags watchlist companies reporting earnings in the next 7 days.
Uses yfinance Ticker.calendar for upcoming earnings dates.
"""

import datetime

# Tickers to check: the SEC watchlist is the single source of truth (a ticker
# added there gets earnings coverage automatically — this was a byte-identical
# copy that could silently drift); callers can still add coverage via
# fetch_earnings_calendar(extra_tickers=...).
from sec_filings import WATCHLIST as EARNINGS_WATCHLIST


def fetch_earnings_calendar(extra_tickers=None):
    """
    Check for upcoming earnings in the next 7 days.

    Args:
        extra_tickers: Optional list of additional tickers to check.

    Returns:
        List of dicts with ticker, company, earnings_date, time_of_day.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance not installed — skipping earnings calendar.")
        return []

    tickers = list(EARNINGS_WATCHLIST)
    if extra_tickers:
        tickers.extend(extra_tickers)
    tickers = list(set(tickers))  # dedupe

    if not tickers:
        print("  No earnings watchlist configured — skipping.")
        return []

    print(f"  Checking earnings calendar for {len(tickers)} tickers...")

    today = datetime.date.today()
    lookahead = today + datetime.timedelta(days=7)

    upcoming = []

    for ticker_str in tickers:
        try:
            ticker = yf.Ticker(ticker_str)
            cal = ticker.calendar

            if cal is None or cal.empty:
                continue

            # yfinance returns calendar as a DataFrame or dict depending on version
            # Try to get earnings date
            earnings_date = None

            if hasattr(cal, "loc"):
                # DataFrame format
                if "Earnings Date" in cal.index:
                    val = cal.loc["Earnings Date"]
                    if hasattr(val, "iloc"):
                        earnings_date = val.iloc[0]
                    else:
                        earnings_date = val
            elif isinstance(cal, dict):
                ed = cal.get("Earnings Date", [])
                if ed:
                    earnings_date = ed[0] if isinstance(ed, list) else ed

            if earnings_date is None:
                continue

            # Convert to date
            if hasattr(earnings_date, "date"):
                ed = earnings_date.date()
            elif isinstance(earnings_date, str):
                ed = datetime.datetime.fromisoformat(earnings_date).date()
            else:
                continue

            if today <= ed <= lookahead:
                # Try to get company name
                info = ticker.info or {}
                company_name = info.get("shortName", info.get("longName", ticker_str))

                upcoming.append({
                    "ticker": ticker_str,
                    "company": company_name,
                    "earnings_date": str(ed),
                    "day_of_week": ed.strftime("%A"),
                })
                print(f"    {ticker_str} ({company_name}): earnings {ed}")

        except Exception:
            # Silently skip — many tickers won't have calendar data
            continue

    # Sort by date
    upcoming.sort(key=lambda x: x["earnings_date"])
    print(f"  Found {len(upcoming)} upcoming earnings in the next 7 days.")
    return upcoming


def format_earnings_for_prompt(earnings):
    """Format earnings calendar as plain text for the Opus prompt."""
    if not earnings:
        return ""

    lines = ["EARNINGS THIS WEEK:"]
    for e in earnings:
        lines.append(f"  ${e['ticker']} ({e['company']}): {e['day_of_week']} {e['earnings_date']}")
    return "\n".join(lines)


def build_earnings_html(earnings):
    """Render earnings as a small callout box."""
    if not earnings:
        return ""

    items = []
    for e in earnings:
        items.append(f"<strong>${e['ticker']}</strong> ({e['day_of_week'][:3]})")

    html = (
        '<div style="background: #f0f7fb; border-left: 4px solid #2980b9; '
        'padding: 10px 14px; margin-bottom: 20px; font-size: 13px;">\n'
        f'<strong>Earnings this week:</strong> {", ".join(items)}\n'
        '</div>\n'
    )

    return html


if __name__ == "__main__":
    earnings = fetch_earnings_calendar()
    if earnings:
        print(format_earnings_for_prompt(earnings))
    else:
        print("No upcoming earnings found.")
