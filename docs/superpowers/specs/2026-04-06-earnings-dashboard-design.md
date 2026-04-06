# Earnings Dashboard — Design Spec

**Date:** 2026-04-06
**Status:** Draft

## Overview

A standalone earnings calendar dashboard that shows upcoming earnings dates for portfolio and watchlist holdings, with consensus estimates, company guidance, y/y growth, and revision momentum. Organized as weekly swim lanes with expandable company cards.

## Scope

- **In scope:** Portfolio (13 holdings) and watchlist (12 companies) only
- **Out of scope:** Extended watchlist, indices, historical earnings results, post-earnings analysis

## Data Pipeline

### Source

Bloomberg via `xbbg`, extending the existing pull infrastructure.

### New Script: `pull_earnings.py`

Pulls the following per ticker:

**Earnings calendar:**
- `EXPECTED_REPORT_DT` — next earnings date
- `EXPECTED_REPORT_TIME` — BMO / AMC / DMT
- `EARN_ANN_DT_STATUS` — "Confirmed" or "Projected"

**Consensus estimates (1BF = next quarter, 2BF = next annual):**
- `BEST_EPS` (or `BEST_EPS_GAAP` for mega-caps >$200B, matching existing logic)
- `BEST_SALES`
- `BEST_EBITDA`
- `BEST_OPER_INCOME`
- `BEST_GROSS_MARGIN`
- `BEST_OPR_MARGIN`
- Additional per-ticker fields defined in `earnings_metrics.json`

**Revisions:**
- `BEST_EPS_NUMUP` and `BEST_EPS_NUMDN` at 4-week window

**Guidance:**
- `GUIDANCE_EPS_HIGH`, `GUIDANCE_EPS_MID`, `GUIDANCE_EPS_LOW`
- `GUIDANCE_REVENUE_HIGH`, `GUIDANCE_REVENUE_MID`, `GUIDANCE_REVENUE_LOW`
- Quarterly and annual periods

**Prior-year actuals (for y/y computation):**
- Same estimate fields with 0BF or BDH for the year-ago quarter

### Configuration: `earnings_metrics.json`

Maps each ticker to the metrics displayed on its card. Each metric has a display name and a Bloomberg field (or null if not available via BDP and must be sourced from guidance overrides):

```json
{
  "_field_map": {
    "EPS": "BEST_EPS",
    "Revenue": "BEST_SALES",
    "EBITDA": "BEST_EBITDA",
    "Op. Income": "BEST_OPER_INCOME",
    "Gross Margin": "BEST_GROSS_MARGIN",
    "Op. Margin": "BEST_OPR_MARGIN",
    "Capex": "BEST_CAPEX",
    "Net Premiums": "BEST_NET_PREMIUMS_WRITTEN",
    "Combined Ratio": "BEST_COMBINED_RATIO",
    "NII": "BEST_NET_INTEREST_INCOME",
    "Provisions": "BEST_PROVISION_FOR_LOAN_LOSSES"
  },
  "_default": ["EPS", "Revenue"],
  "JPM": ["EPS", "Revenue", "NII", "Provisions"],
  "UNH": ["EPS", "Revenue", "Med. Loss Ratio", "Optum Rev"],
  "TSM": ["EPS", "Revenue", "Gross Margin", "Op. Margin", "Capex"],
  "META": ["EPS", "Revenue", "DAP", "ARPP", "Capex", "Op. Margin"],
  "AMZN": ["EPS", "Revenue", "AWS Revenue", "Op. Income", "AWS Margin", "Capex"],
  "NVDA": ["EPS", "Revenue", "Data Center Rev", "Gross Margin"],
  "AVGO": ["EPS", "Revenue", "AI Revenue", "Gross Margin"],
  "HCA": ["EPS", "Revenue", "Same-Store Admissions", "Rev per Adj Admission"],
  "APP": ["EPS", "Revenue", "Software Platform Rev", "EBITDA"],
  "VEEV": ["EPS", "Revenue", "Subscription Rev", "Billings"],
  "CVNA": ["EPS", "Revenue", "Retail Units", "GPU per Unit"],
  "APO": ["EPS", "FRE", "SRE", "AUM"],
  "PGR": ["EPS", "Net Premiums", "Combined Ratio", "Policies in Force"]
}
```

Metrics not in `_field_map` (e.g., "DAP", "AWS Revenue", "Retail Units") are company-specific KPIs that Bloomberg doesn't carry as standard consensus fields. These show consensus as "—" unless a value is provided in an optional `guidance_overrides.json` file for manual fill-in.

### Output: `output/snapshots/earnings_YYYY-MM-DD.json`

```json
{
  "snapshot_date": "2026-04-06",
  "companies": [
    {
      "ticker": "JPM",
      "group": "Portfolio",
      "earnings_date": "2026-04-11",
      "earnings_time": "BMO",
      "date_confirmed": true,
      "revisions_4wk": { "up": 5, "down": 0 },
      "metrics": [
        {
          "name": "EPS",
          "period": "Q1 2026",
          "consensus": 4.62,
          "guidance_low": 4.50,
          "guidance_high": 4.80,
          "prior_year": 4.12,
          "yoy_pct": 12.1
        },
        {
          "name": "Revenue",
          "period": "Q1 2026",
          "consensus": 42.8,
          "consensus_unit": "B",
          "guidance_low": 42.0,
          "guidance_high": 43.5,
          "prior_year": 39.6,
          "yoy_pct": 8.1
        }
      ],
      "annual_metrics": [
        {
          "name": "EPS",
          "period": "FY 2026",
          "consensus": 18.75,
          "guidance_low": 18.00,
          "guidance_high": 19.50,
          "prior_year": 17.20,
          "yoy_pct": 9.0
        }
      ]
    }
  ]
}
```

## UI Design

### Page Layout

- **Header bar:** Title ("Earnings Calendar"), last-refreshed timestamp, filter toggle (Portfolio / Watchlist), zoom slider (1 week to full quarter, default 30 days)
- **Mini timeline:** Thin horizontal bar spanning the full quarter. Tick marks at each earnings date, colored by urgency. Clickable — scrolls swim lanes to the selected week.
- **Swim lanes:** Horizontal row of weekly columns. Each column header shows week range and company count. Current week is visually highlighted. Horizontal scroll for overflow.

### Visual Style

- Light mode (white background, light borders, subtle shadows)
- Same font stack as existing dashboard (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`)
- Color palette:
  - Red (#dc2626): urgency <5 days, negative revisions, consensus below guidance
  - Amber (#d97706): urgency <14 days, mixed revisions, consensus at guidance edge
  - Green (#16a34a): urgency 14d+, positive revisions, consensus above guidance, positive y/y
  - Blue (#2563eb): next-week lane accent
  - Gray (#6b7280): later weeks, n/a values

### Card Design

Each company card contains:

**Header row:**
- Ticker (bold, 15px)
- Date + BMO/AMC badge
- Days-until badge: red (<5d), amber (<14d), green (14d+)
- Confirmed/tentative indicator: solid dot = confirmed, hollow dashed circle + italic date with "(est)" = projected
- If earnings date shifted vs prior snapshot: small "moved from [date]" note

**Revision badge:**
- Shows up/down count over 4 weeks
- Green background if net positive, amber if mixed, red if net negative

**Metrics table:**
| Column | Description |
|--------|-------------|
| Metric | Name of the line item |
| Guidance | Low – High range (or "—" if none) |
| Cons. | Consensus estimate |
| Y/Y | Percentage or bps change vs year-ago quarter |
| vs Guide | "above" / "mid" / "below" / "n/a" — where consensus sits within the guided range |

**Quarterly metrics first**, then a separator row "Full Year 20XX" for annual guidance items.

### Interactivity

**Zoom slider:**
- Default: 30 days
- Left: tighten to current week
- Right: expand to full quarter (~90 days)
- Swim lanes add/remove dynamically

**Filter toggle:**
- Portfolio / Watchlist — controls which tickers appear
- Persists in localStorage

**Mini timeline:**
- Click a section to scroll swim lanes to that week

**Card expand/collapse:**
- Cards start expanded when ≤3 companies in a lane
- When 4+ in a lane, cards collapse to summary row (ticker, date, EPS consensus, revision badge)
- Click to expand/collapse

**No routing, no modals.** Single scrollable page.

### Data Refresh

- No live polling
- Run `python pull_earnings.py` to generate a new JSON snapshot
- Reload the page to pick up the latest snapshot
- "Last updated" timestamp in header shows snapshot date

## File Structure

```
BBG/
  pull_earnings.py          # New — Bloomberg data pull
  earnings_metrics.json     # New — per-ticker metric config
  earnings.html             # New — standalone dashboard
  output/snapshots/
    earnings_2026-04-06.json  # Dated snapshot output
```

## Tech Stack

- **Data pull:** Python 3 + xbbg (same as existing pipeline)
- **Dashboard:** Vanilla HTML/CSS/JS, no framework, no build step
- **Serving:** `python -m http.server` (local only)
- **Data format:** JSON snapshots loaded via `fetch()`
