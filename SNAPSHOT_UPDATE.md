# SNAPSHOT_UPDATE — Snapshot-table data freshness: lag inventory, free upgrades, BBG DL

> Planning spec, written 2026-07-23 (read-only investigation session; no code changed).
> Extends HANDOFF §11.B "Snapshot-table T-1 lag — LOOK INTO". Status: **NOT STARTED** —
> this doc is the investigation output + option map; implementation decisions pending.
>
> **Headline finding (new, verified today): the Rates and Corporate Credit snapshots are
> T-2 at the 08:00 run, not T-1 as previously believed.** The "treasury yields are wrong"
> complaint is almost certainly this: on a Thursday-morning digest the yields are
> Tuesday's — all of Wednesday's session is missing. There is a free fix for the
> Treasury rows (source switch, identical methodology). Details and evidence below.
>
> §4 is the **requested-vs-shipped substitution register**: several rows are free
> stand-ins for data jared actually asked for. If a paid service (BBG DL) ever lands,
> §4 is the cutover map to the data he actually wants.

---

## 0. Framing: what "live" can even mean at 08:00 ET

The digest generates at 08:00 ET, 90 minutes before the US equity open. Freshness at
that moment falls into four classes, and no vendor changes which class a row is in:

| Class | Meaning | Rows |
|---|---|---|
| **Live-capable** | The instrument trades at 8 AM (24h/overnight markets) | Cash Treasuries/TIPS, WTI, DXY, BTC, (VIX via Cboe global-hours calc), index futures |
| **T-1 is the ceiling** | The freshest real daily value is *last night's close* — either the market is closed pre-open, or the number is published once per day in arrears | US equities & indices, Treasury.gov par yields, SOFR, ICE/BBG index OAS, fund-reported OAS, BVAL EOD |
| **Same-day close (foreign session already over)** | The 8 AM ET run is *after* that market's close | SK Hynix (KRX closes ~2:30 AM ET) |
| **Structurally slower** | Weekly/monthly publications | Fed H.4.1 balance sheet (weekly, Thu 4:30 PM — out of scope here), prompt-only CPI/claims |

Also note: the 1D/1W/1M change columns are close-to-close math. Mixing a *live intraday*
level into a table whose change columns are close-based muddies what "1D" means — a
reason to prefer "consistent T-1 closes, loudly labeled" over live values for most rows.

---

## 1. Current lag, row by row

### 1.1 Rates Snapshot (`macro_data.py` FRED_SERIES, section "rates") — **T-2 ⚠**

Source today: FRED, which republishes the Fed's **H.15 release — published each business
day ~4:15 PM ET for the PREVIOUS business day.** Verified 2026-07-23 via the FRED API:

- `DGS10` obs 07-21 first available **07-22** (last_updated 07-22 16:16 ET); obs 07-20
  first available 07-21; obs 07-17 first available 07-20 — a next-business-day vintage,
  every time.
- Therefore at 08:00 on day D the freshest FRED value is **D-2** (Thursday's run shows
  Tuesday). This is one session STALER than last night's close.

| Row | Series | Freshness at 08:00 today |
|---|---|---|
| 2Y / 10Y / 20Y / 30Y UST | DGS2/10/20/30 | **T-2** |
| 10Y breakeven | T10YIE | **T-2** (derived from DGS10−DFII10 upstream) |
| 10Y / 30Y real yield (TIPS) | DFII10/DFII30 | **T-2** |
| 30Y breakeven (derived in code) | DGS30 − DFII30 | **T-2** |
| 2s20s (derived in code) | DGS20 − DGS2 | **T-2** |
| SOFR | SOFR | **Effectively T-2.** NY Fed publishes day-D's SOFR ~8:00 AM on D+1; it hit FRED at **8:02 AM** today — minutes after the run fetches. (Also: "today's SOFR" never exists at 8 AM — the freshest possible print is *yesterday's* overnight rate, published this morning.) |

### 1.2 Corporate Credit Snapshot (FRED BAML rows + `ishares_data.py`) — **T-2 / T-1**

| Row | Source | Freshness at 08:00 |
|---|---|---|
| HY / IG / AAA / A / BBB / BB / B / CCC index OAS | ICE BofA via FRED (BAML*) | **T-2.** Yesterday's close publishes to FRED the *next morning* ~9–10 AM ET (verified: 07-22's HY OAS arrived 07-23 10:13 AM ET — two hours after the run). |
| HYG / LQD / IGLB / IGIB portfolio OAS | ishares.com scrape (fund-reported) | **T-1** (fund-reported prior close; e.g. the 7/17 digest carried ISHARES:HYG as of 7/16). Also §11.A(i): fragile scrape. |

### 1.3 Market Snapshot (`market_data.py`, Yahoo) — **mixed T-1 / same-day**

| Row | Ticker | Freshness at 08:00 |
|---|---|---|
| S&P 500 | ^GSPC | **T-1 close** (market opens 9:30; this is the pre-open ceiling) |
| VIX | ^VIX | **Likely same-day** — Cboe disseminates VIX every 15 seconds during global trading hours, **3:00 AM–9:15 AM ET** (verified 2026-07-23), so a live value exists at 8 AM; past 8 AM-run footnotes show ^VIX carrying the run-day date. Whether the Yahoo daily-bar route captures it: VERIFY with per-row timestamps (below). |
| WTI Crude | CL=F | **Same-day, near-live** (trades ~24h; the in-progress daily bar comes through — past 8 AM footnotes show run-day dates) |
| DXY | DX-Y.NYB | **Same-day, near-live** (FX ~24h) |
| BTC | BTC-USD | **Same-day, near-live** (24/7) |

Caveat: `market_data.py` stores `as_of` as DATE-only (~line 124), so "same-day" can't be
distinguished from "same-day 6:00 AM" vs "moment of fetch" in the current logs — the
HANDOFF §11.B(b) per-row timestamp logging item settles this from a real 08:00 run.

### 1.4 Private Credit Snapshot (Yahoo) — **T-1**

| Row | Ticker | Freshness at 08:00 |
|---|---|---|
| Russell 2000 | ^RUT | T-1 close |
| ARCC, OTF | equities | T-1 close |
| BKLN | ETF | T-1 close |
| BKLN trailing yield (derived) | dividends/price | Trailing-12M by construction — not a lag problem |

### 1.5 AI Snapshot (Yahoo) — **T-1 except Korea**

| Row | Ticker | Freshness at 08:00 |
|---|---|---|
| Nasdaq Composite | ^IXIC | T-1 close |
| SPCX, NVDA, TSM (ADR), INTC, MU, ORCL, CRWV | US equities | T-1 close |
| SK Hynix | 000660.KS | **Same-day close is available** (KRX session ends ~2:30 AM ET) but past footnotes are inconsistent (7/16 run: same-day; 7/17 run: T-1) — Yahoo may lag KRX daily bars. VERIFY with per-row timestamps. |

### 1.6 Labeling defect found in passing

`macro_data._build_fred_table` footnote uses **`max(dates)`** across rows
(`macro_data.py:361`). Because SOFR's date can be one day fresher than the DGS rows',
the rates table can print "as of 07-22" while every yield row is 07-21. The one
freshness label that exists **overstates** freshness. Fix: `min(dates)`, or per-row/
outlier enumeration like the market-table footnote already does.

(Related: HANDOFF §11.B's "verified: 7/22 run rendered rates as of 2026-07-21" was
evidently checked against the local *dev test* digest — run in the evening, after the
4:15 PM H.15 update — not the server's 08:00 production email, which per the vintage
evidence must have shown 07-20. Confirm once against the actual received email.)

---

## 2. Free upgrades (no new spend; none of this needs Claude to test)

Ordered by impact:

1. **Treasury rows: switch FRED → Treasury.gov direct. T-2 → T-1. The big win.**
   - Treasury publishes the **Daily Par Yield Curve** and **Daily Par Real Yield Curve**
     on treasury.gov same day ~3:30–4 PM ET (free XML/CSV interest-rate feeds, no key).
   - **Methodology-identical:** FRED's DGS *is* Treasury's CMT par yield republished via
     H.15 — same numbers, one day earlier. No value discontinuity, no reader-visible
     methodology change.
   - Covers every Rates-Snapshot input: nominal 2/10/20/30 (and 2s20s), real 10/30, and
     breakevens become computed nominal−real in code (T10YIE is exactly DGS10−DFII10, so
     the number matches; the 30Y breakeven is already computed in code today).
   - Implementation shape: a small `treasury_yields.py`-style fetcher (or a branch in
     `macro_data.py`) feeding the same row dicts; 1D/1W/1M need ~45 days of history —
     Treasury's feeds serve full-month/period files, so history is available. Keep FRED
     as fallback on fetch failure (try/except-everywhere convention).
2. **SOFR: fetch from the NY Fed Markets Data API instead of FRED** (free, no key;
   publishes ~8:00 AM ET). Turns "T-2 by a 2-minute race" into T-1 *most* days, but
   08:00:xx is still a razor's edge — either fetch SOFR late in the run, retry once, or
   accept occasional T-2 with honest labeling. Marginal value; do only if touching the
   module anyway.
3. **Footnote fixes (labeling, zero data change):** `min(dates)` (or per-row dates) in
   `_build_fred_table`; promote the as-of framing prominently per HANDOFF §11.B(a)
   ("Prior close — as of Tue 7/22" at table or section level). This is the cheapest way
   to kill "the data is wrong" complaints for the rows that are legitimately T-1.
4. **Per-row timestamp logging** (§11.B(b)): store time-of-day alongside `as_of` in
   `market_data.py` and log per row; read one real 08:00 production run to confirm the
   same-day rows (VIX, WTI, DXY, BTC, SK Hynix). A run at any other hour cannot
   reproduce 8 AM market state.
5. **ICE BofA OAS: no free upgrade exists at 08:00.** FRED is the free redistribution
   channel and receives yesterday's close ~9–10 AM — after the run, structurally. Free
   options are all product changes, not source swaps: run later (rejected — breaks the
   pre-market briefing), or accept T-2 with honest labeling ("as of <date>, published
   T+1").
6. **US equities/indices: no free upgrade worth taking.** Yahoo's quote endpoints do
   expose premarket prices free, but premarket prints are thin/noisy and would corrupt
   the close-to-close 1D/1W/1M columns. Futures rows (ES=F/NQ=F/RTY=F are on Yahoo,
   free, near-live at 8 AM) are possible but change *what the table reports* — a product
   decision for jared, not a data fix.

**Net effect if 1–4 ship:** every Rates row moves to last-night's-close (the industry
standard for a morning note), the same-day rows are confirmed and labeled as live-ish,
the credit-index rows are honestly labeled T-2→"prior close, published T+1", and nothing
about the tables' meaning changes.

### 2.7 Freshest FREE option per laggy row (researched 2026-07-23)

Every currently-lagged row, with the most up-to-date free source that exists — split
into **robust** (official publisher / stable API; recommendable) vs **fragile**
(page-scrape of a quote site; possible but a §5-of-HANDOFF-style silent-breakage risk
and ToS-gray — adopt only as a deliberately-optional layer with fallback):

| Laggy row(s) | Today at 08:00 | Freshest robust free | Freshest fragile free | Verdict |
|---|---|---|---|---|
| UST 2/10/20/30, TIPS, breakevens, 2s20s | T-2 (FRED/H.15) | **Treasury.gov daily curves → T-1** (§2.1) | **Live on-the-run yields exist free**: CNBC quote pages (US10Y etc., sourced from **Tradeweb** — updates overnight, i.e. genuinely live at 8 AM; also TradingView TVC:US10Y). Scrape-only, no API. Notably these match what readers see on terminals better than CMT does. | Ship Treasury.gov (robust T-1). CNBC/Tradeweb scrape = optional live layer ONLY if T-1 still draws complaints; needs the same as-of labeling + graceful degradation as ishares_data |
| SOFR | T-2 (8:02 race) | **NY Fed Markets Data API → T-1** most days (§2.2) | — | Optional; do if touching the module |
| ICE BofA OAS ×8 | T-2 (FRED, ~9–10 AM arrival) | **None fresher exists.** Re-searched: every free channel (TradingView, tracker sites) republishes FRED; ICE's own registered platform is unverified-and-likely-unredistributable (§4 row 2) | — | Accept T-2 + honest label (§2.5); T-1 needs BBG DL |
| HYG/LQD/IGLB/IGIB portfolio OAS | T-1 (fund-reported) | None fresher — the fund publishes once daily | — | Already at its ceiling |
| US equities & indices (S&P, Russell, Nasdaq, NVDA…) | T-1 close (pre-open ceiling for a *close*) | — (no official free live source pre-open) | Yahoo **futures tickers** (ES=F/NQ=F/RTY=F — near-live at 8 AM, same free API already used) = different instrument, product decision. Yahoo **premarket quotes** (quote endpoint carries `preMarketPrice`) = thin/noisy, corrupts close-to-close 1D/1W/1M math | Keep T-1 closes + prominent labeling; futures rows only with jared's sign-off |
| VIX | Same-day (likely) | Cboe disseminates live 3:00–9:15 AM ET; Yahoo appears to carry it (free, already in use) | — | Confirm via per-row timestamps (§2.4); no source change needed |
| SK Hynix | Same-day close available, footnotes inconsistent | Yahoo **quote endpoint** (vs the daily-bar download, which may lag KRX bars) — same free API, different call | — | Diagnose with §2.4 timestamps first; switch fetch style only if bars prove laggy |
| BKLN trailing yield | Trailing-12M by construction | n/a | n/a | Not a lag problem |

Summary: **the only laggy rows where a fresher free source exists are the Treasury/SOFR
rows (robust, §2.1–2.2) and — via fragile scraping only — live on-the-run yields.** The
ICE OAS rows are the one group that is stuck at T-2 without paid data; everything else
is already at its structural ceiling and needs labeling, not sourcing.

---

## 3. What Bloomberg Data License adds (and doesn't)

Context: DL is Bloomberg's request/response enterprise data product — end-of-day,
**intraday, and snapshot** pricing requests (a scheduled 08:00 snapshot pull fits DL's
model exactly; streaming real-time is a different product, B-PIPE, not needed here).
Caveats: real-time exchange-sourced quotes add per-exchange licensing fees; third-party
index content (ICE BofA, S&P) can require separate redistribution consent; DL pricing is
negotiated/per-security (no public rate card). **Working estimate for our usage:
≈ $20k/yr (operator, 2026-07-23)** — the anchor §3.1's cheaper alternatives are
measured against.

| Row group | With BBG DL at 08:00 | Verdict |
|---|---|---|
| **Treasury yields / TIPS / breakevens** | **Genuinely LIVE** — cash Treasuries trade overnight (Tokyo/London); BBG has live on-the-run quotes at 8 AM. Also removes the CMT-vs-on-the-run few-bps gap readers see against their terminals. | **The one true "live" upgrade DL buys — and the only ROBUST live source.** (Treasury.gov already gets these rows to T-1 free; a fragile CNBC/Tradeweb scrape could get live free — §2.7.) |
| SOFR | No change — it's a published benchmark, not a traded quote; BBG carries the same 8 AM print. | No benefit |
| **ICE BofA index OAS** | **T-1, not live** — index-level OAS (ICE's, and Bloomberg's own LF98/LUAC family) is computed at the close; DL delivers last night's values by early morning. One session fresher than FRED, never intraday. Live intraday credit = CDX indices (a *different instrument*) or bond-level IBVAL. | T-2 → **T-1** |
| HYG/LQD/IGLB/IGIB spreads | Swaps the fragile ishares.com scrape for licensed data AND upgrades fund-reported portfolio OAS → the **true G-spreads jared asked for** (§11.A(i)). Value is EOD-derived → T-1 at 8 AM. Intraday BVAL (IBVAL, ~15-sec pricing) covers ~30k **IG USD** credit securities — potentially live-ish for the IG funds' constituents, but index/basket-level aggregation is still an EOD calc. | Quality + robustness upgrade; **T-1**, not live |
| **§11.A wishlist** (S&P BDC index SPBDCUP; BCRED '32 / ARCC '32 / SpaceX '56 / Oracle '66 / QTS G-spreads; CoreWeave '32 + Core Scientific '31 prices) | **Coverage: yes — this is the only way to get these rows at all** (no free source exists; re-verified 2026-07-23, see §4). Liveness: BVAL evaluated pricing is EOD → **T-1** at 8 AM. IG names (Oracle '66; plausibly the BDC bonds) may qualify for intraday IBVAL; HY names (CoreWeave, Core Scientific) EOD only. SPBDCUP is a third-party S&P index — EOD-calculated + possible S&P redistribution consent. | New coverage, mostly T-1 |
| US equities & indices (NVDA, ORCL, S&P, VIX, …) | **No liveness change** — the market is closed at 8 AM for any vendor. BBG adds premarket quotes and futures, same product-decision caveat as the free route. | No benefit for this problem |
| WTI / DXY / BTC / SK Hynix | Already live/same-day free via Yahoo; BBG adds only robustness (licensed feed vs. free API). | Marginal |

**Bottom line on BBG DL:** it does NOT deliver "all snapshots live on the day of the
run" — nothing does, because most rows are structurally T-1-or-worse at 8 AM. What DL
uniquely buys is (a) the **wishlist rows** (its real justification), (b) **robust live
8 AM Treasury quotes** (nice, but Treasury.gov gets 95% of the reader-visible fix for
free, and a fragile scrape could even get live free — §2.7), and (c) T-2→T-1 on the
**credit index OAS** rows (the one lag the free stack can't close at any fragility
level — §2.7). If the wishlist isn't wanted, DL is hard to justify for freshness alone.

### 3.1 Cheaper paid alternatives (vs the ≈$20k/yr BBG DL estimate; researched 2026-07-23)

No single cheaper vendor replaces DL — the needs split into lanes sold separately.
What each lane costs and covers:

**Lane A — per-bond prices for the wishlist: FINRA TRACE, direct. ~$6k/yr.**
FINRA's actual fee schedule (finra.org/filing-reporting/trace/pricing; all fees are
**per data set** — BTDS = corporates, a separate **144A** set, plus ATDS/SPDS/TSDS):
- Continuous real-time vendor feed: **$1,500/mo per set** → $18k/yr for corporates
  alone, $36k/yr with 144A — NOT cheaper than BBG. Skip.
- **Snapshot Real-Time feed: $250/mo per set (once-daily delivery)** → BTDS + 144A =
  **$500/mo = $6k/yr**. A once-daily file of the day's TRACE prints is *exactly* the
  shape a morning digest needs: T-1 last-trade prices for CoreWeave '32 / Core
  Scientific '31 and computable T-1 G-spreads (trade yield − §2.1 Treasury.gov curve)
  for the bond wishlist. The 144A set matters: BCRED '32, QTS, SpaceX '56 are likely
  144A-traded.
- This also reconciles the HANDOFF §11.A "$9k/yr, rejected 2026-07-13" note — that
  sizing predates this fee-schedule read; the right configuration today is the $6k/yr
  snapshot pair, and the earlier rejection ("for a 2-issuer watchlist") should be
  re-decided against the full 7-bond wishlist.
- **Structural caveat vs BVAL:** TRACE is *actual trade prints*, not evaluated marks.
  Illiquid names may not print for days/weeks — rows must render "last traded <date>"
  and tolerate gaps. BBG's BVAL marks every bond every day; TRACE doesn't. That's the
  real quality gap the $14k/yr difference buys.
- TSDS (Treasury set) exists too, but Treasury.gov already covers T-1 yields free.

**Lane B — live-at-8AM market data: Databento CME Standard, $179/mo ≈ $2.1k/yr.**
Cash **on-the-run US Treasuries trade on CME Globex (BrokerTec)** since the 2021
migration, so one licensed CME feed carries live 8 AM Treasury prices PLUS ES/NQ/RTY
index futures, CL (WTI), and SOFR futures. Caveats: price→yield for cash Treasuries
needs coupon/maturity reference data + bond math in code (heavier lift than a quote
page); verify BrokerTec on-the-run coverage in Databento's catalog before committing;
futures rows remain a product decision (§2.7). This is the robust, licensed version of
everything the fragile scrapes offer.

**Lane C — credit index OAS: no cheap option exists.** ICE Data Indices sells only via
direct sales quote (no public price; enterprise-typical). The OAS rows realistically
stay FRED T-2 (free) or get fixed inside a BBG/ICE decision — no mid-priced vendor
carries licensed ICE BofA or Bloomberg index OAS.

**Lane D — resellers (e.g. Finnhub's bonds/TRACE API): not a shortcut.** Bond-tier
pricing is quote-only (not public), and since it's TRACE redistribution its cost floor
is FINRA's own fees — a convenience layer over Lane A, not a saving. Worth a quote only
if FINRA's direct vendor-agreement onboarding proves too heavy for a solo operator.

**The composite "cheap stack" vs BBG DL:**

| | Cheap stack (~$8k/yr) | BBG DL (~$20k/yr) |
|---|---|---|
| Components | TRACE Snapshot BTDS+144A ($6k) + Databento CME ($2.1k) + free tier (Treasury.gov, NY Fed, Cliffwater pending sign-off) | One vendor |
| Wishlist bond prices/G-spreads | T-1, **trade-print based — gaps on illiquid names** | T-1 evaluated (BVAL) — every bond, every day; IG names intraday-capable |
| Live 8 AM Treasury yields | Yes (BrokerTec via Databento, bond math in code) | Yes (turnkey fields) |
| Credit index OAS | **Still FRED T-2** | T-1 (BBG's own index family — also closes §4 row 2) |
| ETF G-spreads (HYG/LQD/IGLB/IGIB) | **No** (stays ishares scrape) | Yes |
| S&P BDC index | No (Cliffwater substitute, free) | Yes (+S&P consent) |
| Integration effort | 2 vendor onboardings + bond math + gap handling | 1 onboarding, standard fields |

Decision frame: if the priority is *wishlist bond visibility + fresher rates*, the
cheap stack delivers ~80% of the reader-visible value at ~40% of the cost. If the
priority is *evaluated G-spreads, index OAS parity with terminals, and one-vendor
simplicity*, that's what the extra ~$12k buys. A middle path also exists: **start with
Lane A alone ($6k/yr)** — the wishlist bonds are the only data money alone can unlock —
and revisit DL if trade-print gaps annoy.

---

## 4. Requested vs. shipped — the substitution register (paid-cutover map)

Several snapshot rows are **free stand-ins for data jared actually requested**; other
requested rows ship nothing at all because no free source existed. This register is the
authoritative map (compiled from the in-code comment blocks: `macro_data.py:41/:51`,
`ishares_data.py` header, `market_data.py:46`, HANDOFF §11.A). **If a paid service is
ever licensed, cut over to the "actually wanted" column — don't keep the substitutes.**

| # | Actually requested (jared) | What ships today instead | On paid cutover, switch to | Free source for the requested data? (researched 2026-07-23) |
|---|---|---|---|---|
| 1 | **True G-spreads** for HYG / LQD / IGLB / IGIB (2026-07-15/16) | Fund-reported **portfolio OAS** scraped from ishares.com (`ishares_data.py`) — approximate metric AND fragile scrape | BVAL-derived G-spreads via BBG DL | **No.** ETF-basket G-spreads need constituent-level bond pricing + curve math; no free provider publishes them. Confirmed still-none. |
| 2 | **Bloomberg index OAS family** (LF98 / LUAC / LU3A / LU1A / LUBA / BCBA / BCBH / BCAU) | **ICE BofA index OAS** via FRED (`macro_data.py:41` — "the free analogs") — close analog but a different index family, and T-2 at 08:00 (§1.2) | The actual Bloomberg index OAS tickers (EOD → T-1 at 08:00) | **FRED is the free channel and it's T-2 at 08:00.** ICE's own index platform (indices.theice.com) has registered access, but earlier-than-FRED availability at 8 AM is unverified and redistribution terms likely forbid it — low-priority verify, don't count on it. |
| 3 | **S&P BDC Index (SPBDCUP)** | **Nothing** (spglobal publisher page bot-blocks (403); BIZD ETF proxy explicitly DECLINED). The ^RUT/ARCC/OTF rows are adjacent coverage, not substitutes | SPBDCUP via DL (note: third-party S&P index — redistribution consent + EOD-calculated, T-1 at best) | **Partial — real finding:** the **Cliffwater BDC Index (CWBDC)** publishes **free, daily, no paywall/registration** at bdcs.com (price + total return, downloadable history). It's a *different* index (cap-weighted over listed BDCs — arguably the industry-standard BDC benchmark now), so adopting it instead of SPBDCUP is **jared's sign-off**, not a drop-in. S&P's own levels: subscription/vendor only. |
| 4 | **BCRED '32 + ARCC '32 G-spreads** (Private Credit) | **Nothing** (ARCC equity row is adjacent, not a substitute) | BVAL G-spreads via DL (IG BDC bonds plausibly IBVAL-eligible → intraday) | **No** — see per-bond findings below. |
| 5 | **SpaceX '56 / Oracle '66 / QTS G-spreads** (AI) | **Nothing** (SPCX / ORCL equity rows are adjacent, not substitutes; QTS is private — no equity row possible) | BVAL G-spreads via DL | **No** — see per-bond findings below. |
| 6 | **CoreWeave '32 + Core Scientific '31 bond prices** (AI) | **Nothing** (CRWV equity row adjacent) | BVAL prices via DL (HY → EOD BVAL, T-1) | **No** — see per-bond findings below. |
| 7 | *(not an explicit request, but same shape)* On-the-run market Treasury yields — what readers compare against on their terminals | **CMT par yields** (Treasury's official curve, via FRED today; via Treasury.gov after §2.1) — a few bps off on-the-run quotes by methodology | Live on-the-run quotes via DL | CMT *is* the robust free option. Live on-the-run yields do exist free via scrape (CNBC quote pages, Tradeweb-sourced — detail in §2.7) but are fragile and methodology-inconsistent with the 1D/1W/1M close-based columns — optional last-resort layer only. |

**Per-bond data (rows 4–6) — free-source research findings (2026-07-23):**

- **FINRA TRACE remains the only authoritative free-ish channel, and it still doesn't
  work for us.** The free-with-user-agreement Fixed Income API datasets are
  **aggregates only** (Weekly Treasury Aggregates, Market Breadth & Sentiment, Capped
  Volume) — no per-CUSIP end-of-day prices/yields. Per-security TRACE data is the paid
  vendor datafeed (the $9k/yr rejected 2026-07-13), and the free finra.org bond-center
  *web* lookup was already judged too fragile to scrape (that judgment stands).
- **German retail exchanges (Börse Frankfurt / Stuttgart)** show bond quotes on free web
  pages, but there is no free API (market data is a commercial product), the pages are
  scrape-fragile, EUR-venue prints for USD credits are thin/unrepresentative, and 144A
  names (BCRED, QTS, SpaceX '56) are likely not listed at all. Not recommended.
- **Third-party bond APIs (Finnhub, Cbonds)** put bond endpoints behind paid tiers.
- **The math is not the blocker.** Given any bond yield, G-spread = yield − interpolated
  Treasury (computable in code from the §2.1 Treasury.gov curve). The missing piece is a
  robust free per-bond price/yield feed — which does not exist. **The wishlist verdict
  ("none has a free source") is re-confirmed.**

---

## 5. Recommended sequence (all pre-BBG steps are $0 and Claude-free to test)

1. ~~Treasury.gov source switch for the Rates Snapshot (T-2 → T-1)~~ **DONE 2026-07-23**
   (`treasury_yields.py`; per-series FRED fallback; rows carry `source`; live-verified) — §2.1
2. ~~Footnote fixes~~ **DONE 2026-07-23** (majority-date + per-date outlier enumeration
   replaced `max(dates)` — `market_data.as_of_label`, shared by both table builders;
   every snapshot table now carries an explicit lag note) — §2.3
3. Per-row timestamp logging — **code half DONE 2026-07-23**
   (`market_data._freshness_summary` logs "Freshness: same-day bars: … |
   prior-session: …" each fetch; Yahoo daily bars carry no intraday time, so
   bar-date vs run-date is the signal). **REMAINING: read the line from a real
   08:00 server log** (first one after deploy) to settle VIX/WTI/DXY/BTC/
   SK Hynix same-day status — §2.4
4. ~~NY Fed SOFR direct~~ **DONE 2026-07-23** (`treasury_yields.fetch_sofr_series`,
   FRED fallback; wins the 8:00 AM race most days, outlier-enumerated in the
   footnote when it loses) — §2.2
5. ~~Label the ICE OAS rows honestly~~ **DONE 2026-07-23** (Corporate Credit footnote:
   "published the morning after each close (two sessions behind at an 08:00 send)") — §2.5
6. ~~Ask jared: Cliffwater BDC Index as the BDC-index row?~~ **DONE 2026-07-23 —
   jared APPROVED; shipped same day** (`cliffwater_data.py`: bdcs.com's own static
   `/docs/bdcs/ChartData.json` — full daily history, T-1, no key; row renders in the
   Private Credit Snapshot labeled Cliffwater, never S&P; registry-fetched → O3
   zero-streak coverage; the JSON also carries CWBDC_Yield + PremDis if more rows
   are ever wanted) — §4 row 3
7. Paid data: decide on the §11.A wishlist first — freshness alone doesn't carry any
   paid option. Then pick a lane: **TRACE Snapshot ($6k/yr) alone**, the **cheap stack
   (~$8k/yr)**, or **BBG DL (~$20k/yr)** — comparison table in §3.1. Whichever is
   licensed, execute the **§4 cutover map** (swap every substitute for the requested
   data) — §3, §3.1, §4

Contingency (not a numbered step): if T-1 Treasury closes STILL draw staleness
complaints after 1–3 ship, the only free escalation is the fragile CNBC/Tradeweb
live-yield scrape (§2.7) — take it only with ishares_data-style graceful degradation,
and prefer jumping to BBG DL if the wishlist is wanted anyway.

Testing notes: everything in 1–6 is free-API work (HANDOFF §8 "free" tier — no
permission needed); validate rendered HTML to a local file, and remember the
`env.bat` DIGEST_TO footgun for any full-run test. A real 08:00 server run is the only
valid check for the same-day-row questions (VIX / SK Hynix / WTI-DXY-BTC timestamps).

## 6. Evidence appendix (gathered 2026-07-23)

- FRED API `series` metadata: `DGS10` last_updated **2026-07-22 16:16 ET** with latest
  obs **2026-07-21**; `BAMLH0A0HYM2` last_updated **2026-07-23 10:13 ET** with latest
  obs 2026-07-22; `SOFR` last_updated **2026-07-23 08:02 ET** with latest obs 2026-07-22.
- FRED API vintages (ALFRED realtime): DGS10 obs 07-21→first available 07-22; 07-20→
  07-21; 07-17→07-20; 07-16→07-17; 07-15→07-16. Next-business-day, every time.
- Local dev digests: `digests/2026-07-22.html` rates footnote "as of 2026-07-21"
  (evening dev run — post-H.15, hence T-1); `digests/2026-07-23.html` rates footnote
  "as of 2026-07-22" while DGS rows could only be 07-21 at run time → the `max(dates)`
  masking in §1.6 (SOFR's fresher date wins the footnote).
- Production 8 AM footnotes (pre-cutover dev-box runs): 7/16 digest — ^GSPC "as of
  2026-07-15" but ^VIX/CL=F/DX-Y.NYB/BTC-USD "as of 2026-07-16" → the 24/7-class rows
  already come through same-day at 8 AM; equities T-1 as expected.
- §4 free-source research (web, 2026-07-23): FINRA Developer Center Fixed Income API
  lists only aggregate datasets (Weekly Treasury Aggregates / Market Breadth &
  Sentiment / Capped Volume) — no per-CUSIP EOD pricing in the free tier
  (developer.finra.org; finra.org/finra-data/fixed-income; TRACE per-security data =
  paid vendor datafeed). Börse Frankfurt/Stuttgart market data = commercial product,
  no free API. Finnhub/Cbonds bond endpoints = paid tiers. Cliffwater BDC Index:
  bdcs.com publishes CWBDC price + total return daily, free, no registration,
  downloadable history ("index returns generally will be published daily"; calculated
  from publicly-available closing share prices, reconstituted quarterly). S&P DJI:
  SPBDCUP levels via subscription/major vendors only; spglobal.com/spdji index page
  bot-blocks automated fetch (the previously-recorded 403).
- §3.1 paid-alternatives research (web, 2026-07-23): FINRA TRACE fee schedule
  (finra.org/filing-reporting/trace/pricing) — Vendor Real-Time Data Feed $1,500/mo
  continuous OR $250/mo daily Snapshot, charged **per data set** (BTDS / ATDS / SPDS /
  144A / TSDS); professional display $60/mo/terminal. Databento: CME usage-based live
  pricing retired 2025-04-16; Standard plan $179/mo (licensed CME distributor);
  BrokerTec US Treasuries are CME market-data products (cash Treasuries on Globex).
  ICE Data Indices: direct-sales quote only, no public pricing, no free plan. Finnhub
  bonds/TRACE tier: pricing not public (quote required).
- §2.7 fresher-free research (web, 2026-07-23): CNBC quotes US Treasury yields sourced
  from Tradeweb (cnbc.com/quotes/US10Y — live incl. overnight; no API, scrape only);
  TradingView TVC:US10Y similar. ICE BofA OAS: all free channels found (TradingView,
  tracker sites) republish FRED — nothing arrives before FRED's ~9–10 AM update; note
  FRED now serves only a rolling ~3-year window for BAML series (fine for the 45-day
  fetch). Cboe VIX: disseminated every 15 seconds during global trading hours
  2:00–8:15 AM CT (= 3:00–9:15 AM ET; Cboe announcements) — a live VIX exists at the
  08:00 run. Yahoo quote endpoint exposes preMarketPrice and near-live futures
  (ES=F/NQ=F/RTY=F) on the API already in use.
