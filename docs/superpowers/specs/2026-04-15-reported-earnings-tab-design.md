# Reported Earnings Tab — Design

**Date:** 2026-04-15
**Status:** Draft — pending implementation plan

## Purpose

Add a "Reported" tab to the earnings calendar dashboard that tracks companies which have just reported earnings in the current season. It mirrors the existing Upcoming tab's layout and filtering, but surfaces actuals vs. estimates, stock reaction around the print, and the one-week post-earnings change in NTM consensus EPS.

The goal is to answer, at a glance: *of the companies that have already printed this season, who beat, who sold off anyway, and whose numbers are getting marked up after the call?*

## Scope

**In scope**
- New "Reported" tab on `output/dashboards/earnings.html`, switchable with the existing Upcoming view via a tab pill in the header.
- Rolling 45-day window: a company is on the Reported tab if its most recent earnings date is within the last 45 days.
- Per-company card showing actuals vs. consensus for the same metric set already tracked in the Upcoming card, plus three stock-reaction numbers in the header and one NTM EPS revision number in the footer.
- Data extension in `scripts/pull_earnings.py` that pulls the new fields from Bloomberg on every run. No persistent tracker file — every run recomputes from Bloomberg history.

**Out of scope**
- Multi-quarter history beyond the rolling 45-day window.
- Guidance vs. actual comparisons (future extension; guidance data is often missing).
- Revenue revisions, out-year estimate changes, analyst up/down counts (simpler: one NTM EPS delta only).
- Any change to the Upcoming tab's layout, data, or behavior.

## Architecture

### Data flow

```
pull_earnings.py  ─┬─>  [existing phases] ──>  snapshot.companies[]
                   └─>  [new reported phase] ─> snapshot.reported[]
                                                       │
                                                       ▼
                            output/snapshots/earnings_YYYY-MM-DD.json
                                                       │
                                                       ▼
                            output/dashboards/earnings.html
                               ├── Upcoming tab (reads .companies)
                               └── Reported tab (reads .reported)
```

One snapshot file, two views. The dashboard routes a company to the Reported tab if it appears in `reported[]`; otherwise it stays on the Upcoming tab.

### Snapshot schema addition

A new top-level key `reported` is added alongside the existing `companies` key:

```json
{
  "snapshot_date": "2026-04-15",
  "companies": [ ... existing ... ],
  "reported": [
    {
      "ticker": "JPM",
      "group": "Portfolio",
      "earnings_date": "2026-04-14",
      "earnings_time": "Bef-mkt",
      "metrics": [
        {
          "name": "EPS",
          "actual": 5.82,
          "consensus": 5.375,
          "surprise": 0.0827,
          "yoy": "+30%"
        },
        { "name": "Revenue", "actual": 49850, "consensus": 48792.08, "surprise": 0.0217, "yoy": "+13%" },
        { "name": "NII", "actual": null, "consensus": null, "surprise": null, "yoy": null }
      ],
      "stock": {
        "d1": -0.008,
        "w1": 0.014,
        "w1_vs_spx": 0.006
      },
      "ntm_eps_chg": 0.018
    }
  ]
}
```

Notes:
- `metrics[]` is the same list of metrics used in the Upcoming card for this ticker, pulled from `config/earnings_metrics.json`. Rows with no available actual show `null` and render as "—" in the UI.
- `stock.d1` / `stock.w1` / `stock.w1_vs_spx` are decimals. Any can be `null` if the post-earnings window has not fully elapsed.
- `ntm_eps_chg` is `null` until seven calendar days have passed since `earnings_date`.

## Component: `pull_earnings.py` new phase

A new phase `[9/10] Reported actuals & post-earnings moves` runs after the existing `[8/8] Earnings history` phase. The phase builds the `reported[]` list.

### Steps

1. **Identify reported tickers.** For every ticker in `PORTFOLIO + WATCHLIST`, determine the most recent earnings date ≤ today. Reuse the data already pulled in the existing earnings-date phase; the "last reported" date is the most recent entry in `earnings_history[0]` or can be pulled directly via `LAST_ANNOUNCED_EARNINGS_DT`. Keep tickers where this date is within the last 45 days.

2. **Pull actuals.** For each reported ticker, for each metric in its config, pull the actual reported value using the same Bloomberg field used for `prior_year` in the Upcoming phase. Use `fiscal_period_override` pointing at the just-reported fiscal quarter. The existing `EPS_OVERRIDES` map is reused verbatim so AMZN/GOOG/META/TSM/APO special cases get the same treatment.

3. **Pull pre-earnings consensus.** For each metric, call `blp.bdh(ticker, <BEST_* field>, start=earnings_date-3d, end=earnings_date-1d, BEst_Fperiod=<just-reported quarter>)`. Take the last value in the window — that's the consensus going into the print. A 3-day window handles long weekends and holidays.

4. **Compute surprise.** `surprise = actual / consensus − 1`, stored as a decimal. `null` if either leg is missing.

5. **Pull stock reaction.** One batched `blp.bdh([ticker, 'SPX Index'], 'PX_LAST', start=earnings_date-2d, end=earnings_date+10d)` per ticker. Compute:
   - `d1` = close(earnings_date or next trading day) / close(prior trading day) − 1
   - `w1` = close(+5 trading days from report) / close(prior trading day) − 1
   - `w1_vs_spx` = ticker `w1` − SPX `w1` over the same window
   - Fields are `null` if the required window has not elapsed.

6. **Pull NTM EPS change.** `blp.bdh(ticker, 'BEST_EPS', start=earnings_date-2d, end=earnings_date+10d, BEst_Fperiod='NTM')`. Take the value on the last trading day ≤ earnings_date as the pre baseline and the value on the first trading day ≥ earnings_date+7 as the post value. `ntm_eps_chg = post / pre − 1`. `null` if the post date has not arrived.

7. **Y/Y.** Computed client-side from the actual vs. `prior_year` already present in the existing `metrics[]` for the matching fiscal period. Re-using existing values avoids a second pull.

8. **Persist.** Append each reported record to `snapshot['reported']`. No separate file.

### Error handling

Each ticker's pull is wrapped in a try/except that logs the ticker and the exception, then continues. One bad ticker must not abort the phase. This matches how the existing earnings-history phase treats non-US overrides.

### Cost

Roughly 3 BDH calls per reported ticker per run (actuals batch, consensus batch, stock+NTM batch) × ~6–15 tickers in-window. Comfortably under xbbg's throughput.

## Component: `earnings.html` Reported tab

### Tab switcher

A two-pill tab switcher is added to the left of the existing filter chips in the header row:

```
[Upcoming]  [Reported]   Change ▼   Portfolio | Watchlist | All   RANGE: ...
```

- Active pill gets the accent color.
- Tab state persists in `localStorage` under a new key `earnings_tab` (`"upcoming"` or `"reported"`).
- Switching is a client-side re-render — no refetch.

### Lane layout

Four columns, newest week on the left:

```
This week   Last week   2 weeks ago   3+ weeks ago
(Apr 13–19)  (Apr 6–12)  (Mar 30–Apr 5)  (≤ 45 days)
```

- Week boundaries are Monday–Sunday relative to `snapshot_date`.
- Companies within a lane sort by earnings_date descending, then ticker.
- The 4th lane is an open bucket for anything 22–45 days old so the column count is fixed.

### Card layout

Mirrors the Upcoming card structure. Differences:

**Header strip** replaces the "Confirmed / X days" pill with:

```
JPM    Reported Tue, Apr 14    1D: -0.8%    1W: +1.4%    1W vs SPX: +0.6%
```

- Stock numbers colored green positive / red negative.
- `1W vs SPX` rendered slightly bolder.
- If a value is `null` (window not yet elapsed), show "—".

**Metric table** uses four columns instead of the Upcoming tab's five:

| METRIC  | ACTUAL | CONS  | SURPRISE | Y/Y  |
|---------|--------|-------|----------|------|
| EPS     | 5.82   | 5.38  | +8.2%    | +30% |
| Revenue | 49,850 | 48,792| +2.2%    | +13% |
| NII     | —      | —     | —        | —    |

- Rows come from the same metric list the Upcoming card uses for this ticker.
- `SURPRISE` uses the same color thresholds as the existing beat/miss coloring in `earnings_history`.
- Missing metrics render with "—" so the row grid stays stable across tickers.

**Footer row** replaces the existing "Last 4 quarters beat/miss" block with a single line:

```
NTM EPS change (1W post): +1.8%
```

- Same color treatment as SURPRISE.
- If `ntm_eps_chg` is `null`, show `NTM EPS change (1W post): pending` in muted gray.

### Filter chips

- Same three options as Upcoming: Portfolio / Watchlist / All.
- Filter state is shared with the Upcoming tab via the existing `earnings_filter` localStorage key.

### Zoom ranges

Zoom chips on the Reported tab are replaced with: 1 Week / 2 Weeks / 1 Month (default) / 45 Days. State persists in a new `earnings_reported_zoom` localStorage key, independent of the Upcoming tab's zoom.

### Empty state

If `snapshot.reported[]` is empty for the active filter + zoom:

> No earnings reported in the last 45 days. Check the Upcoming tab.

## Error & missing-data handling

- **Missing actual for a metric** — row renders with "—" in ACTUAL and SURPRISE. Card still shows.
- **Missing consensus** — SURPRISE shows "—". Actual and Y/Y still show.
- **Post-earnings window not yet elapsed** — stock `w1` fields and `ntm_eps_chg` show "—" or "pending". Card still shows with whatever is available.
- **Ticker-level pull failure** — logged and skipped. The ticker simply does not appear on the Reported tab that day.

## Testing

The existing project has no automated test harness for the earnings dashboard. Verification for this feature is:

1. Run `python scripts/pull_earnings.py` after the change and confirm a successful exit and that the new snapshot file has a non-empty `reported[]` array.
2. Open the hosted dashboard (after push) and check JPM's reported card: actuals match the press release, surprise % matches the beat column, 1D/1W stock numbers match Bloomberg.
3. Check a company reported <7 days ago (if any): confirm NTM EPS change shows "pending" and the 1W stock fields render as "—".
4. Toggle filter chips and zoom chips — confirm state persists across tab switches the way the Upcoming tab already does.
5. Toggle between Upcoming and Reported — confirm no refetch occurs (client-side re-render) and the active tab persists across reloads.

## Open questions

None at this time. All scoping questions resolved during brainstorming.
