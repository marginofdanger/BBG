# Estimate Revision Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-page HTML dashboard showing consensus EPS estimate revisions for portfolio and watchlist companies, with sparklines, click-to-expand detail rows, and a time slider for historical snapshots.

**Architecture:** Python pull script generates timestamped CSV snapshots with estimate + stock return data. A static HTML dashboard reads the CSV via `fetch()`, renders a spreadsheet-style table with inline SVG sparklines, and supports loading historical snapshots via a slider. Served locally via `python -m http.server` from the BBG directory.

**Tech Stack:** Python 3 + xbbg (Bloomberg), vanilla HTML/CSS/JS, inline SVG sparklines.

---

## File Structure

```
BBG/
├── bloomberg.py              # Existing — core Bloomberg data module (no changes)
├── pull_estimates.py         # NEW — pull script that generates snapshot CSVs
├── dashboard.html            # NEW — the dashboard
└── output/
    └── snapshots/
        ├── index.json        # NEW — list of snapshot dates for the slider
        └── 2026-04-03.csv    # NEW — timestamped snapshot (same format + return cols)
```

---

### Task 1: Pull Script — `pull_estimates.py`

**Files:**
- Create: `BBG/pull_estimates.py`

This script pulls all estimate data + stock returns from Bloomberg and saves a timestamped snapshot CSV.

- [ ] **Step 1: Create `pull_estimates.py`**

```python
"""Pull EPS estimates and stock returns from Bloomberg, save as dated snapshot."""

import csv
import json
import os
import shutil
from datetime import date

from bloomberg import estimate_history, USD_OVERRIDE_TICKERS
from xbbg import blp

PORTFOLIO = ['HCA', 'UNH', 'TSM', 'AVGO', 'NVDA', 'META', 'AMZN', 'JPM', 'APO', 'PGR', 'CVNA', 'APP', 'VEEV']
WATCHLIST = ['FICO', 'GOOG', 'MU', 'HOOD', 'TDG', 'GE', 'LRCX', 'DASH', 'UBER', 'LLY', 'MSFT', 'V']
ALL_TICKERS = PORTFOLIO + WATCHLIST
YEARS = [2025, 2026, 2027, 2028]
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), 'output', 'snapshots')


def get_field_map(tickers):
    """Determine BEST_EPS vs BEST_EPS_GAAP per ticker based on market cap."""
    bbg_tickers = [f'{t} US Equity' for t in tickers]
    df = blp.bdp(bbg_tickers, ['CUR_MKT_CAP']).to_native()
    tks = df.column('ticker').to_pylist()
    vals = df.column('value').to_pylist()
    mktcaps = {}
    for tk, val in zip(tks, vals):
        short = tk.replace(' US Equity', '')
        if val:
            mktcaps[short] = float(val)
    return {t: 'BEST_EPS_GAAP' if mktcaps.get(t, 0) > 200e9 else 'BEST_EPS' for t in tickers}


def get_prices_and_returns(tickers):
    """Pull current price, and stock returns."""
    bbg_tickers = [f'{t} US Equity' for t in tickers]
    fields = ['PX_LAST', 'CHG_PCT_YTD', 'CHG_PCT_3M', 'CHG_PCT_1YR']
    df = blp.bdp(bbg_tickers, fields).to_native()
    tks = df.column('ticker').to_pylist()
    flds = df.column('field').to_pylist()
    vals = df.column('value').to_pylist()
    result = {}
    for tk, fld, val in zip(tks, flds, vals):
        short = tk.replace(' US Equity', '')
        if short not in result:
            result[short] = {}
        if val:
            result[short][fld] = float(val)
    return result


def pull_and_save():
    today_str = date.today().strftime('%Y-%m-%d')
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    print('Getting market caps and field assignments...')
    field_map = get_field_map(ALL_TICKERS)

    print('Pulling stock prices and returns...')
    market_data = get_prices_and_returns(ALL_TICKERS)

    print('Pulling estimate histories...')
    all_results = {}
    for t in ALL_TICKERS:
        f = field_map[t]
        group = 'Portfolio' if t in PORTFOLIO else 'Watchlist'
        print(f'  [{group}] {t} ({f})...')
        rows = estimate_history(t, YEARS, lookback_months=24, field=f)
        all_results[t] = {r['line_item']: r for r in rows}

    # Determine quarter columns from data
    all_quarter_cols = set()
    for t in ALL_TICKERS:
        for cy_data in all_results[t].values():
            for k in cy_data:
                if k != 'line_item':
                    all_quarter_cols.add(k)

    def sort_key(col):
        q, year = col.split(' ')
        return (int(year), int(q[1]))

    quarter_cols = sorted(all_quarter_cols, key=sort_key)

    # Write CSV
    filepath = os.path.join(SNAPSHOT_DIR, f'{today_str}.csv')
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header: estimate cols interleaved with chg cols
        header = ['Ticker', 'Group', 'EPS Type', 'Year', quarter_cols[0]]
        for i in range(1, len(quarter_cols)):
            header += [quarter_cols[i], f'{quarter_cols[i]} chg']
        header += ['Price', 'PE', '12m Rev', 'Return_YTD', 'Return_3m', 'Return_12m']
        writer.writerow(header)

        for group_name, tickers in [('Portfolio', PORTFOLIO), ('Watchlist', WATCHLIST)]:
            for t in tickers:
                md = market_data.get(t, {})
                px = md.get('PX_LAST', 0)
                ret_ytd = md.get('CHG_PCT_YTD', '')
                ret_3m = md.get('CHG_PCT_3M', '')
                ret_12m = md.get('CHG_PCT_1YR', '')
                eps_type = 'GAAP' if field_map[t] == 'BEST_EPS_GAAP' else 'Adj'

                for cy in [f'CY{y}' for y in YEARS]:
                    row = all_results[t].get(cy, {})

                    # Latest EPS for PE calc
                    latest = None
                    for c in reversed(quarter_cols):
                        if row.get(c) is not None:
                            latest = row[c]
                            break
                    pe = round(px / latest, 1) if latest and latest > 0 and px else ''

                    # 12m revision
                    latest_idx = None
                    for i, c in enumerate(reversed(quarter_cols)):
                        if row.get(c) is not None:
                            latest_idx = len(quarter_cols) - 1 - i
                            break
                    rev = ''
                    if latest_idx is not None:
                        prior = None
                        for i in range(max(0, latest_idx - 4), latest_idx):
                            if row.get(quarter_cols[i]) is not None:
                                prior = row[quarter_cols[i]]
                                break
                        if prior and prior != 0:
                            rev = f'{(latest / prior - 1) * 100:+.1f}%'

                    # Build CSV row with interleaved values and q/q changes
                    csv_row = [t, group_name, eps_type, cy]
                    v0 = row.get(quarter_cols[0])
                    csv_row.append(round(v0, 2) if v0 is not None else '')

                    prev_val = v0
                    for i in range(1, len(quarter_cols)):
                        vi = row.get(quarter_cols[i])
                        csv_row.append(round(vi, 2) if vi is not None else '')
                        if vi is not None and prev_val is not None and prev_val != 0:
                            chg = (vi / prev_val - 1) * 100
                            csv_row.append(f'{chg:+.1f}%')
                        else:
                            csv_row.append('')
                        if vi is not None:
                            prev_val = vi

                    csv_row += [
                        round(px, 2) if px else '',
                        pe,
                        rev,
                        f'{ret_ytd:+.1f}%' if isinstance(ret_ytd, float) else '',
                        f'{ret_3m:+.1f}%' if isinstance(ret_3m, float) else '',
                        f'{ret_12m:+.1f}%' if isinstance(ret_12m, float) else '',
                    ]
                    writer.writerow(csv_row)

    print(f'Saved snapshot: {filepath}')

    # Update index.json
    snapshots = sorted(
        [f.replace('.csv', '') for f in os.listdir(SNAPSHOT_DIR) if f.endswith('.csv')],
        reverse=True,
    )
    index_path = os.path.join(SNAPSHOT_DIR, 'index.json')
    with open(index_path, 'w') as f:
        json.dump(snapshots, f, indent=2)
    print(f'Updated index: {index_path} ({len(snapshots)} snapshots)')


if __name__ == '__main__':
    pull_and_save()
```

- [ ] **Step 2: Run it to generate the first snapshot**

Run from the BBG directory (requires Bloomberg terminal running):

```bash
cd /c/Users/AdrianOw/Projects/BBG && PYTHONIOENCODING=utf-8 python pull_estimates.py
```

Expected: Creates `output/snapshots/2026-04-03.csv` and `output/snapshots/index.json`.

- [ ] **Step 3: Verify the CSV has the new return columns**

```bash
head -2 output/snapshots/2026-04-03.csv
```

Expected: Header row ends with `...,Return_YTD,Return_3m,Return_12m` and data row has percentage values.

- [ ] **Step 4: Verify `index.json`**

```bash
cat output/snapshots/index.json
```

Expected: `["2026-04-03"]`

---

### Task 2: Dashboard HTML — Table Structure and CSV Loading

**Files:**
- Create: `BBG/dashboard.html`

Build the core HTML page: CSS, CSV loader, and table renderer. No sparklines or slider yet — just the static table from the latest CSV.

- [ ] **Step 1: Create `dashboard.html` with CSS and CSV loader**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portfolio Estimate Tracker</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8f9fa; color: #1a1a1a; font-size: 12px; }
  .header { padding: 16px 24px; background: #fff; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 16px; font-weight: 600; }
  .header .date { color: #666; font-size: 13px; }

  /* Slider */
  .slider-container { padding: 12px 24px; background: #fff; border-bottom: 1px solid #e0e0e0; }
  .slider-container label { font-size: 11px; color: #888; margin-right: 8px; }
  .slider-container input[type=range] { width: 80%; vertical-align: middle; }
  .slider-container .slider-date { display: inline-block; min-width: 100px; font-weight: 600; font-size: 12px; }

  /* Table */
  .table-wrapper { padding: 12px 24px; overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; min-width: 1400px; font-size: 11px; }
  th, td { padding: 4px 7px; text-align: right; white-space: nowrap; border-bottom: 1px solid #eee; }
  th { background: #f0f0f0; font-weight: 600; color: #555; position: sticky; top: 0; z-index: 1; border-bottom: 2px solid #ccc; }
  td:first-child, th:first-child { text-align: left; position: sticky; left: 0; background: inherit; z-index: 2; }
  th:first-child { z-index: 3; }

  /* Ticker column */
  .ticker { font-weight: 600; color: #1565c0; }
  .eps-tag { font-weight: 400; color: #999; font-size: 10px; }

  /* Group headers */
  .group-header td { background: #e8e8e8; font-weight: 700; font-size: 12px; text-align: left; padding: 8px 7px 4px; border-bottom: 2px solid #ccc; }
  .spacer td { height: 6px; border: none; background: #f8f9fa; }

  /* Year group headers */
  .year-header { text-align: center !important; background: #e0e8f0 !important; font-size: 11px; border-left: 2px solid #ccc; }

  /* Column group borders */
  .col-year-start { border-left: 2px solid #ddd; }

  /* Colors */
  .positive { color: #2e7d32; }
  .negative { color: #c62828; }

  /* Alternating rows */
  .row-even { background: #fff; }
  .row-odd { background: #f7f8fa; }

  /* Sparkline */
  .sparkline { cursor: pointer; vertical-align: middle; }
  .sparkline:hover { opacity: 0.7; }

  /* Expanded detail row */
  .detail-row td { background: #f0f4f8; font-size: 10px; color: #555; padding: 6px 12px; border-bottom: 1px solid #ddd; }
  .detail-row .detail-content { display: flex; gap: 24px; flex-wrap: wrap; }
  .detail-year { margin-bottom: 4px; }
  .detail-year-label { font-weight: 600; color: #333; margin-right: 8px; }
  .detail-val { margin-right: 2px; }
  .detail-chg { font-size: 9px; margin-right: 6px; }
  .detail-current { font-weight: 700; color: #1a1a1a; }

  /* Hide detail rows by default */
  .detail-row { display: none; }
  .detail-row.expanded { display: table-row; }
</style>
</head>
<body>

<div class="header">
  <h1>Portfolio Estimate Tracker</h1>
  <div class="date" id="snapshot-date"></div>
</div>

<div class="slider-container" id="slider-container" style="display:none;">
  <label>Snapshot:</label>
  <input type="range" id="snapshot-slider" min="0" max="0" value="0">
  <span class="slider-date" id="slider-date-label"></span>
</div>

<div class="table-wrapper">
  <table id="main-table">
    <thead id="table-head"></thead>
    <tbody id="table-body"></tbody>
  </table>
</div>

<script>
const YEARS = ['CY2025', 'CY2026', 'CY2027', 'CY2028'];
const ESTIMATE_QUARTERS = [
  'Q2 2024', 'Q3 2024', 'Q4 2024', 'Q1 2025',
  'Q2 2025', 'Q3 2025', 'Q4 2025', 'Q1 2026'
];

// Which quarter columns to show as "current, -3m, -6m, -1y"
// current = last col, -3m = 1 back, -6m = 2 back, -1y = 4 back
const DISPLAY_OFFSETS = [0, 1, 2, 4]; // from the end
const DISPLAY_LABELS = ['current', '-3mo', '-6mo', '-1yr'];

let snapshotDates = [];
let currentData = null;

async function init() {
  try {
    const resp = await fetch('output/snapshots/index.json');
    snapshotDates = await resp.json();
  } catch {
    snapshotDates = [];
  }

  if (snapshotDates.length === 0) {
    document.getElementById('table-body').innerHTML =
      '<tr><td colspan="20">No snapshots found. Run pull_estimates.py first.</td></tr>';
    return;
  }

  // Setup slider
  if (snapshotDates.length > 1) {
    const container = document.getElementById('slider-container');
    container.style.display = 'block';
    const slider = document.getElementById('snapshot-slider');
    slider.max = snapshotDates.length - 1;
    slider.value = 0; // latest is index 0
    slider.addEventListener('input', () => loadSnapshot(snapshotDates[parseInt(slider.value)]));
  }

  loadSnapshot(snapshotDates[0]);
}

async function loadSnapshot(dateStr) {
  document.getElementById('snapshot-date').textContent = formatDate(dateStr);
  document.getElementById('slider-date-label').textContent = formatDate(dateStr);

  const resp = await fetch(`output/snapshots/${dateStr}.csv`);
  const text = await resp.text();
  currentData = parseCSV(text);
  renderTable(currentData);
}

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
}

function parseCSV(text) {
  const lines = text.trim().split('\n');
  const headers = parseCSVLine(lines[0]);
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = parseCSVLine(lines[i]);
    const obj = {};
    headers.forEach((h, idx) => { obj[h] = vals[idx] || ''; });
    rows.push(obj);
  }
  return rows;
}

function parseCSVLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') { inQuotes = !inQuotes; }
    else if (ch === ',' && !inQuotes) { result.push(current.trim()); current = ''; }
    else { current += ch; }
  }
  result.push(current.trim());
  return result;
}

function getEstimateValues(row) {
  // Extract the raw quarterly estimate values (not the chg columns)
  const vals = [];
  for (const q of ESTIMATE_QUARTERS) {
    const v = row[q];
    vals.push(v !== '' && v !== undefined ? parseFloat(v) : null);
  }
  return vals;
}

function getDisplayValues(allVals) {
  // Get values at display offsets from the END of available data
  // Find last non-null index
  let lastIdx = -1;
  for (let i = allVals.length - 1; i >= 0; i--) {
    if (allVals[i] !== null) { lastIdx = i; break; }
  }
  if (lastIdx < 0) return DISPLAY_OFFSETS.map(() => null);
  return DISPLAY_OFFSETS.map(off => {
    const idx = lastIdx - off;
    return idx >= 0 ? allVals[idx] : null;
  });
}

function pctChange(cur, prev) {
  if (cur == null || prev == null || prev === 0) return null;
  return ((cur / prev) - 1) * 100;
}

function fmtPct(val) {
  if (val == null) return '';
  if (val < 0) return `<span class="negative">(${Math.abs(val).toFixed(0)}%)</span>`;
  if (val > 0) return `<span class="positive">${val.toFixed(0)}%</span>`;
  return '0%';
}

function fmtEps(val) {
  if (val == null) return '';
  return val.toFixed(2);
}

function fmtReturnPct(val) {
  if (!val || val === '') return '';
  const str = val.replace('%', '').replace('+', '');
  const num = parseFloat(str);
  if (isNaN(num)) return val;
  if (num < 0) return `<span class="negative">(${Math.abs(num).toFixed(0)}%)</span>`;
  if (num > 0) return `<span class="positive">${num.toFixed(0)}%</span>`;
  return '0%';
}

function makeSparkline(vals, width = 70, height = 16) {
  const valid = vals.filter(v => v !== null);
  if (valid.length < 2) return '';
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const range = max - min || 1;
  const padY = 2;

  const points = [];
  let ptIdx = 0;
  for (let i = 0; i < vals.length; i++) {
    if (vals[i] !== null) {
      const x = valid.length === 1 ? width / 2 : (ptIdx / (valid.length - 1)) * width;
      const y = padY + (1 - (vals[i] - min) / range) * (height - 2 * padY);
      points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      ptIdx++;
    }
  }

  const uptrend = valid[valid.length - 1] >= valid[0];
  const color = uptrend ? '#2e7d32' : '#c62828';

  return `<svg class="sparkline" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/>
  </svg>`;
}

function buildDetailHTML(tickerRows) {
  // Build expanded detail content for all years of a ticker
  let html = '<div class="detail-content">';
  for (const row of tickerRows) {
    const year = row['Year'];
    if (year === 'CY2025') continue; // skip actuals
    const vals = getEstimateValues(row);
    html += `<div class="detail-year"><span class="detail-year-label">${year}:</span>`;
    let prevVal = null;
    for (let i = 0; i < ESTIMATE_QUARTERS.length; i++) {
      if (vals[i] === null) continue;
      const qLabel = ESTIMATE_QUARTERS[i].replace('Q', "Q").replace(' 20', "'");
      const chg = pctChange(vals[i], prevVal);
      const chgHtml = chg !== null
        ? `<span class="detail-chg ${chg >= 0 ? 'positive' : 'negative'}">(${chg >= 0 ? '+' : ''}${chg.toFixed(1)}%)</span>`
        : '';
      const isCurrent = i === ESTIMATE_QUARTERS.length - 1 ||
        (vals.slice(i + 1).every(v => v === null));
      const cls = isCurrent ? 'detail-current' : 'detail-val';
      html += `${i > 0 && prevVal !== null ? ' → ' : ''}<span class="${cls}">${qLabel}: ${vals[i].toFixed(2)}</span> ${chgHtml}`;
      prevVal = vals[i];
    }
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function renderTable(data) {
  // Group rows by ticker
  const tickerGroups = {};
  const tickerOrder = [];
  const tickerMeta = {};
  for (const row of data) {
    const t = row['Ticker'];
    if (!tickerGroups[t]) {
      tickerGroups[t] = [];
      tickerOrder.push(t);
      tickerMeta[t] = { group: row['Group'], epsType: row['EPS Type'] };
    }
    tickerGroups[t].push(row);
  }

  // Build header
  const thead = document.getElementById('table-head');
  // Two header rows: year group row + column label row
  let h1 = '<tr><th rowspan="2">Ticker</th><th rowspan="2">Price</th><th rowspan="2">P/E</th>';
  let h2 = '<tr>';
  for (const yr of ['CY2026', 'CY2027', 'CY2028']) {
    const label = yr.replace('CY', '');
    h1 += `<th class="year-header" colspan="8">EPS estimates: ${label}</th>`;
    for (const dl of DISPLAY_LABELS) {
      h2 += `<th class="${dl === 'current' ? 'col-year-start' : ''}">${dl}</th>`;
    }
    h2 += '<th></th>'; // sparkline
    h2 += '<th>3mo</th><th>mo 6-12</th><th>12mo</th>';
  }
  h1 += '<th class="year-header" colspan="3">Stock performance</th></tr>';
  h2 += '<th class="col-year-start">12mo</th><th>YTD</th><th>3mo</th></tr>';
  thead.innerHTML = h1 + h2;

  // Build body
  const tbody = document.getElementById('table-body');
  let html = '';
  let currentGroup = '';
  let rowIdx = 0;

  for (const t of tickerOrder) {
    const meta = tickerMeta[t];
    const rows = tickerGroups[t];

    // Group separator
    if (meta.group !== currentGroup) {
      if (currentGroup !== '') html += '<tr class="spacer"><td colspan="30"></td></tr>';
      html += `<tr class="group-header"><td colspan="30">${meta.group}</td></tr>`;
      currentGroup = meta.group;
    }

    const rowClass = rowIdx % 2 === 0 ? 'row-even' : 'row-odd';
    const tickerId = `row-${t}`;
    const epsTag = meta.epsType === 'GAAP' ? 'G' : 'A';

    // Get first data row for price/PE (same across years)
    const firstRow = rows[0];
    const price = firstRow['Price'] || '';
    // PE on CY2026 (current year forward)
    const cy26Row = rows.find(r => r['Year'] === 'CY2026');
    const pe = cy26Row ? (cy26Row['PE'] || '') : '';

    html += `<tr class="${rowClass}" id="${tickerId}" onclick="toggleDetail('${t}')">`;
    html += `<td class="ticker" style="background:${rowClass === 'row-even' ? '#fff' : '#f7f8fa'}">${t} <span class="eps-tag">[${epsTag}]</span></td>`;
    html += `<td>${price ? parseFloat(price).toFixed(0) : ''}</td>`;
    html += `<td>${pe ? pe + 'x' : ''}</td>`;

    // Year columns: CY2026, CY2027, CY2028
    for (const yr of ['CY2026', 'CY2027', 'CY2028']) {
      const yearRow = rows.find(r => r['Year'] === yr);
      if (!yearRow) {
        html += '<td class="col-year-start"></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>';
        continue;
      }
      const allVals = getEstimateValues(yearRow);
      const displayVals = getDisplayValues(allVals);

      // Estimate values
      for (let i = 0; i < displayVals.length; i++) {
        const cls = i === 0 ? 'col-year-start' : '';
        html += `<td class="${cls}">${fmtEps(displayVals[i])}</td>`;
      }

      // Sparkline
      html += `<td>${makeSparkline(allVals)}</td>`;

      // % changes: 3mo, 6-12mo, 12mo
      const chg3 = pctChange(displayVals[0], displayVals[1]);
      const chg6_12 = pctChange(displayVals[1], displayVals[2]);
      const chg12 = pctChange(displayVals[0], displayVals[3]);
      html += `<td>${fmtPct(chg3)}</td>`;
      html += `<td>${fmtPct(chg6_12)}</td>`;
      html += `<td>${fmtPct(chg12)}</td>`;
    }

    // Stock performance
    html += `<td class="col-year-start">${fmtReturnPct(firstRow['Return_12m'])}</td>`;
    html += `<td>${fmtReturnPct(firstRow['Return_YTD'])}</td>`;
    html += `<td>${fmtReturnPct(firstRow['Return_3m'])}</td>`;
    html += '</tr>';

    // Detail row (hidden by default)
    html += `<tr class="detail-row" id="detail-${t}"><td colspan="30">${buildDetailHTML(rows)}</td></tr>`;

    rowIdx++;
  }

  tbody.innerHTML = html;
}

function toggleDetail(ticker) {
  const row = document.getElementById(`detail-${ticker}`);
  if (row) row.classList.toggle('expanded');
}

init();
</script>
</body>
</html>
```

- [ ] **Step 2: Start a local server and test**

```bash
cd /c/Users/AdrianOw/Projects/BBG && python -m http.server 8080
```

Open `http://localhost:8080/dashboard.html` in a browser. Verify:
- Table renders with Portfolio and Watchlist sections
- All tickers appear with correct prices, PE, estimates
- Sparklines are visible (green for uptrend, red for downtrend)
- Clicking a row expands the detail row with quarterly history
- Clicking again collapses it

- [ ] **Step 3: Verify the slider works (if multiple snapshots)**

If only one snapshot exists, the slider should be hidden. To test the slider, copy the CSV with a different date:

```bash
cp output/snapshots/2026-04-03.csv output/snapshots/2026-03-03.csv
```

Update `index.json`:
```bash
python -c "import json; json.dump(['2026-04-03','2026-03-03'], open('output/snapshots/index.json','w'))"
```

Reload the page. The slider should appear with two positions. Dragging it should reload data and update the date label.

---

### Task 3: Visual Polish and Verification

**Files:**
- Modify: `BBG/dashboard.html`

Fine-tune after seeing it in the browser. This task covers adjustments that are hard to spec precisely without seeing the rendered output.

- [ ] **Step 1: Check column alignment and widths**

Open the dashboard and verify:
- Estimate columns are properly aligned under their year headers
- Sparklines don't overflow cells
- Group separator rows span the full width
- Sticky first column (ticker) works on horizontal scroll

- [ ] **Step 2: Verify % change formatting**

Check that:
- Positive values show as green numbers: `3%`
- Negative values show as red with parentheses: `(3%)`
- Zero shows as `0%`
- Empty values show as blank

- [ ] **Step 3: Verify sparkline expand/collapse**

Click multiple sparklines rapidly. Ensure:
- Only the clicked row toggles
- Expanded rows have the correct quarterly data
- Q/Q changes are colored correctly in the detail row

- [ ] **Step 4: Test with missing data**

Check tickers that have sparse data (e.g., HOOD, DASH for far-out years). The dashboard should handle missing values gracefully — blank cells, shorter sparklines.

- [ ] **Step 5: Commit everything**

```bash
cd /c/Users/AdrianOw/Projects/BBG
git add pull_estimates.py dashboard.html output/snapshots/
git commit -m "feat: estimate revision dashboard with sparklines and time slider"
```
