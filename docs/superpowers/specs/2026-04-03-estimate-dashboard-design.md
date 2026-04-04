# Estimate Revision Dashboard — Design Spec

## Overview

A single-page HTML dashboard showing consensus EPS estimate revisions for portfolio holdings and watchlist companies. Reads from pre-generated CSV snapshots. Supports time-travel between historical snapshots via a slider.

## Data Pipeline

### Bloomberg Pull Script (`pull_estimates.py`)

Pulls data and saves a timestamped CSV snapshot:

1. Read tickers from `portfolio/PORTFOLIO.md` (portfolio + watchlist)
2. For each ticker, determine EPS field: `BEST_EPS_GAAP` if market cap > $200B, else `BEST_EPS`
3. Pull 24-month quarterly estimate history for CY2025–CY2028 using `bloomberg.estimate_history()` with absolute period references (`25Y`, `26Y`, etc.)
4. Pull current prices, P/E, and stock returns (YTD, 3mo, 12mo) via `blp.bdp`
5. Save to `BBG/output/snapshots/YYYY-MM-DD.csv`
6. Also save/overwrite `BBG/output/snapshots/latest.csv` as a symlink or copy

### CSV Format

Same as current `estimate_revisions.csv` plus additional columns:

```
Ticker, Group, EPS Type, Year,
Q2 2024, Q3 2024, Q3 2024 chg, Q4 2024, Q4 2024 chg, ..., Q1 2026, Q1 2026 chg,
Price, PE, 12m Rev,
Return_YTD, Return_3m, Return_12m
```

### Snapshot Convention

- Snapshots live in `BBG/output/snapshots/`
- Named by date: `2026-04-03.csv`, `2026-01-03.csv`, etc.
- Dashboard discovers all available snapshots by listing files in the directory
- Since this is a local file (not served), the dashboard will include a file-list JSON or the pull script will generate a `snapshots/index.json` listing all available dates

## Dashboard (`dashboard.html`)

### Tech Stack

- Single HTML file, no build step, no framework
- Vanilla JavaScript for CSV parsing, table rendering, sparklines
- Inline SVG for sparklines
- CSS in `<style>` block
- Light theme

### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ Portfolio Estimate Tracker                            April 3, 2026 │
│ ◄━━━━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━► │
│ Jan 2026    Feb 2026    Mar 2026    ▲ Apr 2026                      │
│                                   current                           │
├─────────────────────────────────────────────────────────────────────┤
│ Portfolio                                                           │
│                                                                     │
│         │     │     │ ── EPS CY2026 ──  │ % chg  │ ── EPS CY2027 ──│
│ Ticker  │Price│ P/E │ cur -3m -6m -1y ▪ │3m 6m 1y│ cur -3m -6m ... │
│ HCA  [A]│ 472 │15.5x│30.4 29.6 28.2 27.9│3% 8% 9%│33.3 32.9 31.4..│
│         │     │     │  ▼ expanded quarterly detail row              │
│ UNH  [G]│ 277 │16.5x│16.8 16.4 16.3 32.0│...     │...              │
│ ...                                                                 │
├─────────────────────────────────────────────────────────────────────┤
│ Watchlist                                                           │
│ ...                                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Columns Per Year (CY2026, CY2027, CY2028)

**Estimate values:**
- Current (latest quarter in the snapshot)
- -3 months
- -6 months
- -1 year

**Sparkline:** Inline SVG, ~80px wide, showing all 8 quarterly data points. Green if latest > earliest, red if latest < earliest. Click to expand.

**% change over last:**
- 3 months
- 6-12 months (mo 3–6 to mo 6–12 range, matching spreadsheet)
- 12 months

Green for positive revisions, red (with parentheses) for negative — matching the spreadsheet convention.

### Left Columns

- Ticker (with [A] or [G] suffix)
- Price
- P/E (on current year forward estimate)

### Right Columns (Stock Performance)

- 12 month return
- YTD return
- 3 month return

### Expanded Row (on sparkline click)

When a sparkline is clicked, a detail row appears below that ticker showing:

```
CY2027: Q2'24: 29.46 → Q3'24: 31.30 (+6.2%) → Q4'24: 30.93 (-1.2%) → ... → Q1'26: 33.33 (+1.5%)
```

All 8 quarterly values with q/q % changes between each. Click again to collapse.

### Time Slider

- Horizontal slider at the top of the page
- Shows all available snapshot dates
- Dragging or clicking loads a different CSV and re-renders the table
- Current position is labeled with the date
- Default position: latest snapshot
- The slider needs to know available dates — the pull script generates `snapshots/index.json` containing `["2026-04-03", "2026-03-03", ...]`

### Visual Style

- **Light theme** — white/light gray background, dark text
- Clean sans-serif font (system font stack)
- Thin borders between sections, light gray row alternation
- Green (#2e7d32) for positive revisions, red (#c62828) for negative
- Negative values shown in parentheses: `(3%)` not `-3%`
- Sparklines: green stroke for upward trend, red for downward
- Sector groupings separated by a thin spacer row (matching spreadsheet layout: Healthcare, Tech, Semis, Financials, Consumer, then Watchlist)

## File Structure

```
BBG/
├── bloomberg.py              # Core Bloomberg data module
├── pull_estimates.py         # Pull script (run to refresh)
├── dashboard.html            # The dashboard
├── output/
│   └── snapshots/
│       ├── index.json        # List of available snapshot dates
│       ├── latest.csv        # Copy of most recent snapshot
│       ├── 2026-04-03.csv
│       ├── 2026-03-03.csv
│       └── ...
└── docs/
```

## Out of Scope

- Live Bloomberg pulls from the dashboard
- Server-side rendering or API
- Automatic refresh scheduling (user runs `pull_estimates.py` manually)
- CY2025 column (actuals, not estimates — could add later)
