# Sticky tickers + Rev / Op-inc growth columns — Design

**Date:** 2026-06-23
**Status:** Approved (pending spec review)
**Scope:** `output/dashboards/dashboard.html` (front-end) + `scripts/pull_estimates.py` (data pipeline)

## Goal

On the Portfolio Estimate Tracker dashboard:

1. Pin the **Ticker** (first) column so it stays visible when scrolling right.
2. Add two new column groups to the **right of Returns**:
   - **Rev growth** → `'26`, `'27`, `'28`
   - **Op inc growth** → `'26`, `'27`, `'28`
3. Fill them from Bloomberg consensus estimates, calendar-year adjusted, for **all** main-table rows (Portfolio + core Watchlist + Extended watchlist). Indices are left blank.

## Decisions (confirmed with user)

- **Operating income field:** `BEST_OPP` (Bloomberg consensus Operating Profit). Financials (banks/insurers/asset managers) and indices generally return N/A → those Op-inc cells render blank by design.
- **Row scope:** all main-table rows. Revenue is currently pulled only for Portfolio + named peers; this extends revenue coverage to every name and adds op-income for every name (indices excluded).
- **Data-pull strategy:** Approach A — efficient batched `bdp` snapshot of the current consensus per fiscal period, rather than per-ticker daily `bdh` history.

## Growth definition

For each metric, using the latest ("Current") consensus value per **calendar** year:

```
'26 = CY2026 / CY2025 − 1
'27 = CY2027 / CY2026 − 1
'28 = CY2028 / CY2027 − 1
```

This is the identical formula the existing **Peers tab** already uses for revenue growth
(`revGrow26/27/28` in `renderPeers`). The main-companies render reuses that logic.

Calendar-year adjustment reuses the existing `fye_offset` mechanism in `pull_estimates.py`:
fiscal-year estimates for non-December year-ends are relabelled to the calendar year they
mostly cover (offset of +1 for Jan–Mar FYE).

## Component 1 — Sticky ticker column (CSS, `dashboard.html`)

The first column is vertically sticky in the header only; it is not horizontally pinned today.
Add:

- `td:first-child { position: sticky; left: 0; z-index: 1; }` — body ticker cells pin to the
  left edge. Row backgrounds are already opaque (`.row-even/.row-odd td:first-child`), so cells
  scrolling underneath do not bleed through.
- `thead th:first-child { left: 0; z-index: 3; }` — the top-left header corner pins both
  vertically (already does via `top`) and horizontally, and sits above all other cells so
  scrolling header cells don't slide over it.
- `.group-header td`, `.subgroup-header td` → `position: sticky; left: 0;` so the
  "Portfolio" / "Watchlist" / sub-group section labels stay visible when scrolled right.

**Z-index layering:** corner header (z3) > header row & pinned section labels (z2) >
body ticker cells (z1).

Applies only to the main companies table (`#mainTable`). The Peers / Aggregates / Analysis
tabs are unaffected.

## Component 2 — New columns (JS, `dashboard.html`)

In `render()` / `buildTickerRow()`:

- **Header row 1:** after the `Returns` col-group, add `addTH(h1, 'Rev growth', 3, 'col-group year-sep')`
  and `addTH(h1, 'Op inc growth', 3, 'col-group year-sep')`.
- **Header row 2:** add sortable sub-headers `'26 / '27 / '28` for each group
  (sort keys e.g. `revg26`, `revg27`, `revg28`, `opig26`, `opig27`, `opig28`); first column of
  each group carries the `year-sep` class for the group border.
- **Body:** build a per-ticker lookup of latest revenue and op-income by calendar year
  (mirroring `revByTickerYear` in `renderPeers`), compute the three growth ratios per metric,
  and append six `appendPctCell`-style cells (green/red, `+/−` percent). Store sort values on
  `rowEl._sortData`.
- `totalCols` increases by 6 (currently `6 + displayYears.length * COLS_PER_YEAR + 3`; becomes
  `… + 3 + 6`), so spacer/group-header `colSpan` stays correct.

In `parseCSV()`: add `opIncRows = rows.filter(r => r.Metric === 'OpInc')` alongside the existing
`revRows`, and thread it through `mergeEstimatesWithPrices` / `render` like `revRows`.

**Missing data:** any absent CY value (e.g. op-income for a financial, or a name not yet in a
fresh snapshot) yields a blank cell — never an error.

## Component 3 — Data pipeline (`pull_estimates.py`, Approach A)

Add a helper that pulls **current** consensus for `BEST_SALES` and `BEST_OPP` across all
non-index entries using batched `bdp` with `BEST_FPERIOD_OVERRIDE`:

- For each fiscal-period override in `25Y, 26Y, 27Y, 28Y, 29Y` (covering CY2025–CY2028 across
  both offset 0 and offset +1 names), one batched `bdp` call per metric (batched in groups of
  ~50, as `_bdp_batch` already does). ~10 logical pulls total.
- Per ticker, map fiscal years to calendar years with `fye_offset` (CY = FY − offset), keeping
  CY2025–CY2028.
- Emit CSV rows mirroring the existing Revenue rows: `Metric=Revenue` (now for **all** names)
  and a new `Metric=OpInc`. Only the `Current` snapshot column is populated; the −3m/−6m/−1yr
  columns stay blank (growth needs only Current). Indices are skipped.
- The existing Portfolio+peers revenue pull via `estimate_history` (which feeds the Peers-tab
  revision history) **stays as-is**. To avoid duplicate Revenue rows, the new `bdp` revenue
  emission covers only entries whose ticker is **not** in the existing peer-revenue set
  (`set(PORTFOLIO) | PEER_TICKERS`). Op-income rows are emitted for **all** non-index entries
  (no existing source to collide with).

USD override for `TSM` and the UK-pence / international ticker handling already present in the
file are respected (growth is a ratio, so currency/unit scaling cancels out).

## Data availability / rollout

- Sticky columns + layout: effective the moment the HTML is saved.
- **Rev growth:** populates immediately for Portfolio + peers from the existing
  `estimates_2026-06-19.csv` snapshot; remaining names fill on the next pull.
- **Op inc growth:** blank until the next `pull_estimates.py` run (Bloomberg terminal required;
  run manually or via the Friday "BBG Weekly Snapshot" scheduled task). The dashboard tolerates
  the missing `OpInc` rows gracefully.

## Testing

Open the latest snapshot in the browser and verify:

1. Ticker column and section labels stay pinned while scrolling right; header corner stays put.
2. Rev-growth matches `CYn / CYn−1 − 1` from the CSV for a Dec-FYE name (e.g. NVDA) and a
   non-Dec name (e.g. TSM, or an Oct-FYE name) — confirming calendar adjustment.
3. Financials and indices show blank Op-inc cells; no console errors.
4. Sorting works on each new column; `totalCols`-dependent spacers/headers still span correctly.
5. After a fresh pull, Op-inc growth populates for non-financials and Rev-growth fills the full
   watchlist.

## Out of scope (YAGNI)

- Revision history (−3m/−6m/−1yr) sparklines for revenue/op-income on the main table.
- Op-income / revenue growth on the Peers, Aggregates, or Analysis tabs.
- Any change to EPS columns or other tabs.
