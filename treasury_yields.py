#!/usr/bin/env python3
"""
Treasury.gov daily par yield curves (SNAPSHOT_UPDATE §2.1, 2026-07-23).

At the 08:00 run, FRED's rates series are T-2: FRED republishes the Fed's
H.15, which posts ~4:15 PM ET *for the previous business day*. Treasury.gov
publishes the same Daily Par Yield Curve (and Real Yield Curve) same-day
~3:30-4 PM ET — so this source is T-1 at 08:00, one session fresher, and
methodology-identical (FRED's DGS*/DFII* ARE these curves republished; no
value discontinuity on the switch).

Returns pandas Series keyed by the FRED series ids they replace, so
macro_data.fetch_macro_data consumes them transparently and falls back to
FRED per-series when this fetch fails (try/except-everywhere convention).
"""

import datetime
import json
import urllib.request
import xml.etree.ElementTree as ET

from net_utils import unverified_ssl_context
from config import FEED_USER_AGENT

BASE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/"
    "interest-rates/pages/xml?data={dataset}"
    "&field_tdr_date_value_month={month}"
)

# Treasury XML field -> the FRED series id it replaces (verified 2026-07-23
# against the live feeds; values are percents in both sources).
NOMINAL_FIELDS = {
    "BC_2YEAR": "DGS2",
    "BC_10YEAR": "DGS10",
    "BC_20YEAR": "DGS20",
    "BC_30YEAR": "DGS30",
}
REAL_FIELDS = {
    "TC_10YEAR": "DFII10",
    "TC_30YEAR": "DFII30",
}

# SSL context matches treasury_auctions.py (cert chain doesn't validate
# against the default store; HANDOFF §11.C F4 notes the CA-bundle alternative).
_SSL_CTX = unverified_ssl_context()


def _fetch_xml(dataset, month):
    url = BASE_URL.format(dataset=dataset, month=month)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", FEED_USER_AGENT)
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
        return resp.read().decode("utf-8")


def _months_covering(start, end):
    """['YYYYMM', ...] for every month from start's to end's, inclusive."""
    months = []
    cur = datetime.date(start.year, start.month, 1)
    while cur <= end:
        months.append(f"{cur.year}{cur.month:02d}")
        cur = (cur + datetime.timedelta(days=32)).replace(day=1)
    return months


def parse_curve_xml(xml_text, fields):
    """{'YYYY-MM-DD': {series_id: float}} from one month's Atom feed.
    Namespace-agnostic (tag suffix match); 'N/A'/empty cells skipped."""
    out = {}
    root = ET.fromstring(xml_text)
    for entry in (e for e in root.iter() if e.tag.split("}")[-1] == "entry"):
        date, vals = None, {}
        for el in entry.iter():
            tag = el.tag.split("}")[-1]
            if tag == "NEW_DATE" and el.text:
                date = el.text[:10]
            elif tag in fields and el.text not in (None, "", "N/A"):
                try:
                    vals[fields[tag]] = float(el.text)
                except ValueError:
                    pass
        if date and vals:
            out[date] = vals
    return out


def fetch_treasury_series(start_date):
    """{series_id: pandas.Series} for the Rates-Snapshot inputs, from
    start_date to today: DGS2/10/20/30, DFII10/30, plus T10YIE computed as
    DGS10 − DFII10 (that is exactly what FRED's T10YIE is). Raises on total
    failure — the caller falls back to FRED."""
    import pandas as pd

    today = datetime.date.today()
    start_iso = start_date.isoformat()
    by_date = {}
    for dataset, fields in (
        ("daily_treasury_yield_curve", NOMINAL_FIELDS),
        ("daily_treasury_real_yield_curve", REAL_FIELDS),
    ):
        for month in _months_covering(start_date, today):
            parsed = parse_curve_xml(_fetch_xml(dataset, month), fields)
            for d, vals in parsed.items():
                if d >= start_iso:
                    by_date.setdefault(d, {}).update(vals)

    series = {}
    for sid in list(NOMINAL_FIELDS.values()) + list(REAL_FIELDS.values()):
        pts = {d: v[sid] for d, v in by_date.items() if sid in v}
        if pts:
            s = pd.Series(pts)
            s.index = pd.to_datetime(s.index)
            series[sid] = s.sort_index()

    if "DGS10" in series and "DFII10" in series:
        breakeven = (series["DGS10"] - series["DFII10"]).dropna().round(2)
        if len(breakeven):
            series["T10YIE"] = breakeven
    return series


SOFR_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/{n}.json"


def _fetch_sofr_json(n):
    req = urllib.request.Request(SOFR_URL.format(n=n))
    req.add_header("User-Agent", FEED_USER_AGENT)
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_sofr_series(start_date):
    """SOFR from the NY Fed Markets Data API (SNAPSHOT_UPDATE §2.2; free, no
    key). NY Fed publishes each morning ~8:00 AM ET for the prior business
    day — a razor's-edge race against the 08:00 run (it reached FRED at 8:02
    on 2026-07-23, minutes after the fetch). Going direct wins the race most
    days; on days it loses, the value is one print older and the footnote's
    outlier enumeration shows that honestly. Raises on failure — the caller
    falls back to FRED."""
    import pandas as pd

    data = _fetch_sofr_json(60)  # 60 business obs covers the 45-day window
    start_iso = start_date.isoformat()
    pts = {}
    for rr in data.get("refRates", []):
        d, v = rr.get("effectiveDate"), rr.get("percentRate")
        if d and v is not None and d >= start_iso:
            pts[d] = float(v)
    if not pts:
        raise ValueError("NY Fed SOFR: no observations returned")
    s = pd.Series(pts)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


if __name__ == "__main__":
    data = fetch_treasury_series(datetime.date.today() - datetime.timedelta(days=45))
    data["SOFR"] = fetch_sofr_series(datetime.date.today() - datetime.timedelta(days=45))
    for sid, s in data.items():
        print(f"{sid}: {len(s)} obs, latest {s.index[-1].date()} = {s.iloc[-1]}")
