# Historical Earnings Tab — Design

**Date:** 2026-06-23
**Status:** Draft — pending implementation plan

## Purpose

Add a "Historical" tab to the earnings calendar dashboard (`output/dashboards/earnings.html`),
right of the existing Upcoming / Reported tabs. It shows, for every portfolio and watchlist
company, the dates that company reported earnings over roughly the last three years, laid out
as a matrix so the seasonal reporting pattern is scannable at a glance.

The goal is to answer: *when does each company typically report each quarter?* — a reference for
anticipating the upcoming calendar (e.g. "JPM always prints mid-month; AVGO reports in early
March/June/September/December").

## Scope

**In scope**
- New "Historical" pill in the tab switcher, switchable client-side with Upcoming / Reported.
- A matrix table: one row per ticker, one column per **calendar quarter the company reported in**,
  each cell showing the report date. Columns ordered oldest → newest.
- Rolling ~3-year window (12–13 quarters), with `1Y / 2Y / 3Y` range chips (default 3Y) controlling
  how many quarter-columns render.
- A new data phase in `scripts/pull_earnings.py` that pulls the historical report dates and writes
  a new top-level `date_history` key into the snapshot. No persistent tracker file — every run
  recomputes from Bloomberg.

**Out of scope**
- Beat/miss indicators, stock-reaction coloring, actuals vs. consensus — dates only.
- Future / upcoming dates (those live on the Upcoming tab).
- Any change to the Upcoming or Reported tabs' layout, data, or behavior.
- Backfilling history into existing snapshots from any non-Bloomberg source.

## Key constraint: data does not exist in the repo yet

The snapshot's existing `earnings_history` key keeps only the last 4 quarters and stores
beat/miss/reaction percentages but **not the report dates**. The repo's dated snapshots only go
back to April 2026 (~2.5 months), so there is no 3-year history of report dates anywhere in the
repository. The historical dates exist only in Bloomberg.

Consequence: after implementation, the Historical tab renders **empty until
`python scripts/pull_earnings.py` runs on the Bloomberg machine** (or the Friday "BBG Weekly
Snapshot" scheduled task fires). Once a snapshot with `date_history` is committed and pushed, the
tab populates. This is expected and called out in the verification steps.

## Architecture

### Data flow

```
pull_earnings.py  ─┬─>  [existing phases] ───────>  snapshot.companies[]
                   ├─>  [reported phase] ─────────> snapshot.reported[]
                   └─>  [new date-history phase] ─> snapshot.date_history{}
                                                          │
                                                          ▼
                              output/snapshots/earnings_YYYY-MM-DD.json
                                                          │
                                                          ▼
                              output/dashboards/earnings.html
                                 ├── Upcoming tab   (reads .companies)
                                 ├── Reported tab   (reads .reported)
                                 └── Historical tab (reads .date_history)
```

One snapshot file, three views.

### Snapshot schema addition

A new top-level key `date_history`, keyed by short ticker:

```json
{
  "snapshot_date": "2026-06-23",
  "companies": [ ... existing ... ],
  "reported":  [ ... existing ... ],
  "date_history": {
    "JPM": [
      { "date": "2023-07-14", "cq": "2023Q3" },
      { "date": "2023-10-13", "cq": "2023Q4" },
      { "date": "2024-01-12", "cq": "2024Q1" },
      { "date": "2024-04-12", "cq": "2024Q2" },
      { "date": "2026-04-11", "cq": "2026Q2" }
    ],
    "UNH": [ ... ],
    "...": []
  }
}
```

Notes:
- `date` is the ISO report date from Bloomberg `ERN_ANN_DT_AND_PER`.
- `cq` is the **calendar quarter of the report date** (`YYYYQn`), used by the dashboard to bin the
  date into a matrix column. Binning by report-date calendar quarter (not fiscal-period label)
  makes rows align by *when* companies report, which is the point of the view.
- A ticker with no usable history (e.g. recent IPO, non-US identifier returning nothing) maps to an
  empty array; its row still renders, all cells `—`.

## Component: `pull_earnings.py` new phase

A new phase `[10/10] Earnings date history (last 3 years)` runs after the existing
`[9/9] Reported actuals & post-earnings moves` phase and builds `date_history`. The step counters
in the existing `print()` headers update from `/9` to `/10`.

### Function: `pull_earnings_date_history(bbg_tickers, today)`

Returns `{short_ticker: [{"date": "YYYY-MM-DD", "cq": "YYYYQn"}, ...]}`, sorted ascending by date.

Steps per ticker:
1. `df = blp.bds(bt, "ERN_ANN_DT_AND_PER")` — same field the earnings-history and reported phases
   already use.
2. For each row, parse the announcement date (`row[2]`) and the period string. Keep only rows whose
   date parses, is `<= today`, and is within the last ~3.25 years (`today - 1188 days`) to give a
   little headroom past a strict 3 years.
3. Compute `cq = f"{date.year}Q{(date.month - 1) // 3 + 1}"`.
4. If two rows fall in the same `cq` (rare — a fiscal calendar that prints twice in one calendar
   quarter), keep both entries; the dashboard renders the latest in the cell and the other(s) are
   tolerated (see UI dedup rule below).
5. Sort ascending by date and return.

Error handling: each ticker's BDS pull is wrapped in try/except that logs and continues, exactly
like the existing phases. One bad ticker yields an empty list, never aborts the phase.

Cost: one BDS call per ticker (~37 calls), well within xbbg throughput. (A later optimization could
share the single `ERN_ANN_DT_AND_PER` pull across the history/reported/date-history phases, but that
refactor is out of scope here — keep the new phase self-contained.)

### Wiring in `main()`

- Call `pull_earnings_date_history(bbg_tickers, today)` after the reported phase.
- Add `"date_history": date_history_data` to the assembled `output` dict, keyed by short ticker.
  (`pull_earnings_date_history` returns short-ticker keys directly so no remap is needed.)

## Component: `earnings.html` Historical tab

### Tab switcher

```
[Upcoming]  [Reported]  [Historical]   Changes →   Show: ...   Range: ...
```

- Third button `data-tab="historical"`; active pill gets the accent color.
- Tab state persists in the existing `earnings_tab` localStorage key (now `"upcoming"` |
  `"reported"` | `"historical"`).

### Range chips

`syncRangeButtonsForTab()` gains a third branch. On the Historical tab the chip set becomes:

```
[1 Year]  [2 Years]  [3 Years]   (default 3 Years)
```

- `data-days` values `365 / 730 / 1095`. State persists in a new `earnings_history_zoom`
  localStorage key (default 1095), independent of the other tabs' zoom keys.
- The range bounds how far back columns go: a quarter-column renders only if its quarter-start is
  within `today - zoomDays`.

### Render path

A new `renderHistorical()` function, called from `render()` when `TAB === 'historical'`:

1. Hide the mini-timeline (same as `renderReported`).
2. Build the column set: collect every distinct `cq` across the filtered tickers that falls within
   the active range, sort ascending. Header label: `Q{n} '{yy}` (e.g. `Q2 '26`).
3. Build rows: for each ticker (Portfolio group first, then Watchlist; alpha within group), make a
   `{cq -> date}` lookup from its `date_history`. If multiple dates share a `cq`, the latest wins
   for the cell; tooltip notes the others.
4. Render one `<table class="hist-matrix">`:
   - First column = sticky ticker label.
   - One `<th>` per quarter column.
   - When filter = All, insert a full-width group-divider row (`Portfolio` / `Watchlist`) before
     each group; when a single group is filtered, no divider.
   - Cell text = `Mon DD` (e.g. `Apr 11`); empty bin = muted `—`.
   - `title` attribute on each cell = full weekday + date (e.g. `Fri, Apr 11, 2026`) so hover gives
     the exact day-of-week — useful for spotting "always reports on a Thursday" patterns.
5. Empty state: if no ticker in the active filter has any `date_history` (e.g. snapshot predates this
   feature), show: *"No historical earnings dates in this snapshot. Run `python pull_earnings.py` to
   populate the last 3 years."*

### Styling

New CSS, consistent with the existing palette:
- `.hist-matrix` — `border-collapse`, `font-size: 11px`, horizontal scroll inherited from `.lanes`
  container or its own wrapper with `overflow-x: auto`.
- Sticky first column (`position: sticky; left: 0`) with a white background so ticker labels stay
  visible while scrolling columns.
- Quarter headers reuse the muted uppercase treatment from `.metrics-table th`.
- Group-divider row uses the existing `.section-label` look.
- Empty-cell `—` uses `color: #ccc` (matches the history table's missing-cell style).

The matrix renders into the existing `#lanes` container (cleared and repurposed) so no new
top-level DOM node is required; `renderHistorical` sets `lanes.style.display` appropriately and
writes a single table (or a wrapper div) into it.

## Error & missing-data handling

- **Ticker with empty `date_history`** — row renders with all cells `—`.
- **Snapshot missing the `date_history` key entirely** (older snapshot) — treat as `{}`; show the
  empty-state message.
- **Multiple reports in one calendar quarter** — latest date shown in the cell; tooltip lists all.
- **Quarter with no report for a given ticker** — cell shows `—`.

## Testing / verification

The project has no automated test harness for the dashboard. Verification is manual:

1. **Unit-ish check on the pull:** run `python scripts/pull_earnings.py` on the Bloomberg machine;
   confirm a clean exit and that the new snapshot's `date_history` is a non-empty object with, e.g.,
   ~12 entries for JPM whose dates are plausible (mid-Jan / mid-Apr / mid-Jul / mid-Oct).
2. **Render check:** open the dashboard, click Historical; confirm the matrix shows ticker rows and
   quarter columns, JPM's cells match the snapshot dates, and hover shows the weekday.
3. **Range chips:** toggle 1Y / 2Y / 3Y; confirm the number of columns shrinks/grows and the active
   chip + `earnings_history_zoom` persist across reload.
4. **Filter chips:** toggle Portfolio / Watchlist / All; confirm rows filter and the All view shows
   the group dividers. Confirm filter state stays shared with the other tabs.
5. **Tab persistence:** switch to Historical, reload — confirm it reopens on Historical and the
   other two tabs are unaffected.
6. **Empty state:** load a snapshot without `date_history` (e.g. before re-running the pull) and
   confirm the empty-state message renders rather than a broken table.

## Open questions

None. Layout (matrix), cell content (date only), column binning (calendar quarter of report date),
and range chips (1Y/2Y/3Y) were all resolved during brainstorming.
