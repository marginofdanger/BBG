# Historical Earnings Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Historical" tab to the earnings dashboard showing each portfolio/watchlist company's report dates over the last ~3 years as a calendar-quarter matrix.

**Architecture:** A new phase in `scripts/pull_earnings.py` pulls historical report dates from Bloomberg (`ERN_ANN_DT_AND_PER`) and writes a `date_history` key into the snapshot JSON. The static dashboard `output/dashboards/earnings.html` gains a third client-side tab that reads `date_history` and renders a matrix (rows = tickers, columns = calendar quarter of the report date).

**Tech Stack:** Python 3 + xbbg (Bloomberg) for the data pull; vanilla HTML/CSS/JS (no framework, no build step) for the dashboard; pytest for the pure-helper unit tests.

## Global Constraints

- Date binning column = **calendar quarter of the report date** (`YYYYQn`), not the fiscal-period label. Verbatim rule: `cq = f"{d.year}Q{(d.month - 1) // 3 + 1}"`.
- History window = last ~3.25 years: keep rows with `today - 1188 days <= date <= today`.
- `date_history` is keyed by **short ticker** (e.g. `"JPM"`), value = list of `{"date": "YYYY-MM-DD", "cq": "YYYYQn"}` sorted ascending by date.
- Cell content is **date only** — no beat/miss, no reaction coloring, no future dates.
- Range chips on this tab: `1Y / 2Y / 3Y` → `data-days` `365 / 730 / 1095`, default `1095`, persisted in localStorage key `earnings_history_zoom`.
- Tab state persists in the existing `earnings_tab` key (now `upcoming` | `reported` | `historical`); filter state stays shared via `earnings_filter`.
- Do not change Upcoming or Reported behavior. Only `output/dashboards/earnings.html` is the live dashboard (root `earnings.html` is a redirect — leave it alone).
- The dashboard fetches JSON via relative paths, so UI verification must be done over HTTP (a local `http.server`), not `file://`.

---

## File Structure

- **Modify** `scripts/pull_earnings.py` — add two pure helpers (`_calendar_quarter`, `_build_date_history`), one Bloomberg-touching function (`pull_earnings_date_history`), and wire the new phase into `main()`.
- **Create** `tests/test_earnings_date_history.py` — unit tests for the pure helpers (no Bloomberg).
- **Modify** `output/dashboards/earnings.html` — CSS for the matrix, the Historical tab button, range-chip plumbing, `render()` hook, and `renderHistorical()` + small helpers.

---

## Task 1: Date-history pure helpers + unit tests

**Files:**
- Modify: `scripts/pull_earnings.py` (insert after `pull_reported_details`, before `pull_prior_year_annual_eps` — around line 974)
- Test: `tests/test_earnings_date_history.py`

**Interfaces:**
- Produces: `_calendar_quarter(d: date) -> str` returning `"YYYYQn"`; `_build_date_history(date_strings: Iterable, today: date, max_days: int = 1188) -> list[dict]` returning `[{"date": "YYYY-MM-DD", "cq": "YYYYQn"}, ...]` sorted ascending by date.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_earnings_date_history.py`:

```python
"""Tests for the date-history pure helpers.

These don't touch Bloomberg — they exercise the calendar-quarter binning and
the window/sort logic. Run with:

    python -m pytest tests/test_earnings_date_history.py -v
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

# Importing pull_earnings imports xbbg.blp at module load; mock it first.
class _FakeBlp:
    def bdh(self, *a, **kw): raise RuntimeError("blp not available in tests")
    def bdp(self, *a, **kw): raise RuntimeError("blp not available in tests")
    def bds(self, *a, **kw): raise RuntimeError("blp not available in tests")

sys.modules.setdefault("xbbg", type("M", (), {"blp": _FakeBlp()})())
try:
    import bloomberg  # noqa: F401
except ImportError:
    sys.modules["bloomberg"] = type("M", (), {"USD_OVERRIDE_TICKERS": set()})()

from pull_earnings import _build_date_history, _calendar_quarter  # noqa: E402


# --- _calendar_quarter ---

def test_calendar_quarter_boundaries():
    assert _calendar_quarter(date(2025, 1, 1)) == "2025Q1"
    assert _calendar_quarter(date(2025, 3, 31)) == "2025Q1"
    assert _calendar_quarter(date(2025, 4, 1)) == "2025Q2"
    assert _calendar_quarter(date(2025, 6, 30)) == "2025Q2"
    assert _calendar_quarter(date(2025, 7, 1)) == "2025Q3"
    assert _calendar_quarter(date(2025, 9, 30)) == "2025Q3"
    assert _calendar_quarter(date(2025, 10, 1)) == "2025Q4"
    assert _calendar_quarter(date(2025, 12, 31)) == "2025Q4"


# --- _build_date_history ---

def test_build_filters_future_dates():
    today = date(2026, 6, 23)
    rows = ["2026-04-11", "2026-07-15"]  # second is after today
    out = _build_date_history(rows, today)
    assert [r["date"] for r in out] == ["2026-04-11"]


def test_build_filters_too_old_dates():
    today = date(2026, 6, 23)
    too_old = (today - timedelta(days=1200)).isoformat()
    in_window = (today - timedelta(days=1100)).isoformat()
    out = _build_date_history([too_old, in_window], today)
    assert [r["date"] for r in out] == [in_window]


def test_build_sorts_ascending_and_sets_cq():
    today = date(2026, 6, 23)
    out = _build_date_history(["2025-10-14", "2024-04-12", "2025-01-15"], today)
    assert [r["date"] for r in out] == ["2024-04-12", "2025-01-15", "2025-10-14"]
    assert [r["cq"] for r in out] == ["2024Q2", "2025Q1", "2025Q4"]


def test_build_skips_unparseable_and_trims_time():
    today = date(2026, 6, 23)
    out = _build_date_history(["not-a-date", "", "2025-04-11T00:00:00"], today)
    assert out == [{"date": "2025-04-11", "cq": "2025Q2"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_earnings_date_history.py -v`
Expected: FAIL with `ImportError: cannot import name '_build_date_history'`

- [ ] **Step 3: Implement the helpers**

In `scripts/pull_earnings.py`, insert after the `pull_reported_details` function ends (the `return reported` line, ~line 973) and before `def pull_prior_year_annual_eps`:

```python
def _calendar_quarter(d):
    """Calendar quarter of a date as 'YYYYQn' (binning key for the matrix)."""
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _build_date_history(date_strings, today, max_days=1188):
    """Parse, window-filter, bin, and sort a ticker's announcement dates.

    Keeps dates in [today - max_days, today]. Returns a list of
    {"date": "YYYY-MM-DD", "cq": "YYYYQn"} sorted ascending by date.
    Unparseable entries are skipped. max_days defaults to ~3.25 years so the
    3-year view has a little headroom.
    """
    cutoff = today - timedelta(days=max_days)
    out = []
    for s in date_strings:
        try:
            d = date.fromisoformat(str(s)[:10])
        except (ValueError, TypeError):
            continue
        if d > today or d < cutoff:
            continue
        out.append({"date": d.isoformat(), "cq": _calendar_quarter(d)})
    out.sort(key=lambda r: r["date"])
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_earnings_date_history.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/pull_earnings.py tests/test_earnings_date_history.py
git commit -m "feat: date-history pure helpers for Historical tab"
```

---

## Task 2: Bloomberg pull function + wire into `main()`

**Files:**
- Modify: `scripts/pull_earnings.py` (add `pull_earnings_date_history` after the helpers from Task 1; edit `main()` around lines 1075-1113 and 1211-1215)

**Interfaces:**
- Consumes: `_build_date_history` (Task 1), module-level `blp`.
- Produces: `pull_earnings_date_history(bbg_tickers: list[str], today: date, max_days: int = 1188) -> dict[str, list]` keyed by short ticker; new snapshot key `output["date_history"]`.

- [ ] **Step 1: Add the pull function**

In `scripts/pull_earnings.py`, immediately after `_build_date_history` (from Task 1), add:

```python
def pull_earnings_date_history(bbg_tickers, today, max_days=1188):
    """Pull historical earnings announcement dates (last ~3 years) per ticker.

    Reads ERN_ANN_DT_AND_PER (BDS) — the same field the earnings_history and
    reported phases use — and delegates parsing/binning to _build_date_history.

    Returns {short_ticker: [{"date", "cq"}, ...]} sorted ascending by date.
    One bad ticker is logged and yields [], never aborts the phase.
    """
    result = {}
    for bt in bbg_tickers:
        short = bt.split(" ")[0]
        try:
            df = blp.bds(bt, "ERN_ANN_DT_AND_PER")
            date_strings = [str(row[2]) for row in df.rows()]
        except Exception as e:
            print(f"  WARNING: date-history pull failed for {short}: {e}")
            result[short] = []
            continue
        result[short] = _build_date_history(date_strings, today, max_days)
    return result
```

- [ ] **Step 2: Bump the step counters in `main()`**

The phase headers currently read `[N/9]`. Update every one to `/10`. In `scripts/pull_earnings.py`, replace each occurrence of `/9]` with `/10]` in the nine `print()` headers (lines ~1075-1111: "Earnings dates", "Consensus estimates", "Prior-year actuals", "Guidance ranges", "Revision counts", "EPS 4-week change", "Prior FY actual EPS", "Earnings history", "Reported actuals & post-earnings moves").

Example — change:
```python
    print("\n[1/9] Earnings dates...")
```
to:
```python
    print("\n[1/10] Earnings dates...")
```
(and the same for `[2/9]` … `[9/9]`).

- [ ] **Step 3: Add the new phase call**

In `main()`, after the reported phase block (after the `reported_data = pull_reported_details(...)` line, ~line 1113), add:

```python
    # Step 10: Earnings date history (last ~3 years)
    print("\n[10/10] Earnings date history (last 3 years)...")
    date_history_data = pull_earnings_date_history(bbg_tickers, today)
```

- [ ] **Step 4: Add `date_history` to the snapshot output**

In `main()`, change the `output` dict (~lines 1211-1215) from:

```python
    output = {
        "snapshot_date": today_str,
        "companies": companies,
        "reported": reported_data,
    }
```
to:
```python
    output = {
        "snapshot_date": today_str,
        "companies": companies,
        "reported": reported_data,
        "date_history": date_history_data,
    }
```

- [ ] **Step 5: Verify the module still imports and tests pass**

Run: `python -m pytest tests/ -v`
Expected: PASS — all tests in `test_earnings_timing.py` and `test_earnings_date_history.py` (the new function imports cleanly under the xbbg mock; no test exercises the live `blp.bds` call).

> **Note:** a full end-to-end run (`python scripts/pull_earnings.py`) requires a Bloomberg terminal and is run on the user's machine, not in this dev environment. That run is what populates `date_history` in a real snapshot.

- [ ] **Step 6: Commit**

```bash
git add scripts/pull_earnings.py
git commit -m "feat: pull_earnings date-history phase writes date_history to snapshot"
```

---

## Task 3: Historical tab UI (CSS + tab + chips + matrix render)

**Files:**
- Modify: `output/dashboards/earnings.html`

**Interfaces:**
- Consumes: `DATA.date_history` (Task 2), `DATA.companies[].group` (for Portfolio-first ordering), `FILTER`, `TAB`, `render()`, `syncRangeButtonsForTab()`.
- Produces: `renderHistorical()`, helper fns `filteredHistoryTickers()`, `cqLabel()`, `cqStart()`, and the `ZOOM_DAYS_HISTORY` state.

- [ ] **Step 1: Add matrix CSS**

In the `<style>` block, after the "Reported lane headers" rules (after line ~197, before `</style>`), add:

```css
/* Historical matrix */
.hist-wrap {
  overflow-x: auto; background: #fff; border: 1px solid #e2e5e9;
  border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.hist-matrix { border-collapse: collapse; font-size: 11px; white-space: nowrap; }
.hist-matrix th {
  color: #999; font-weight: 600; font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.3px; padding: 8px 10px; text-align: right;
  border-bottom: 1px solid #e2e5e9; background: #fff;
}
.hist-matrix th.hist-ticker-h { text-align: left; }
.hist-matrix td {
  padding: 6px 10px; text-align: right; color: #333;
  border-bottom: 1px solid #f3f4f6;
}
.hist-matrix td.hist-ticker { text-align: left; font-weight: 700; color: #111; }
.hist-matrix td.hist-empty { color: #ccc; }
.hist-matrix tr:hover td { background: #f8fafc; }
/* sticky ticker column */
.hist-matrix th.hist-ticker-h,
.hist-matrix td.hist-ticker { position: sticky; left: 0; background: #fff; z-index: 2; }
.hist-matrix tr:hover td.hist-ticker { background: #f8fafc; }
.hist-matrix tr.hist-group td {
  background: #f1f3f5; color: #6b7280; font-weight: 700; font-size: 9px;
  text-transform: uppercase; letter-spacing: 0.5px; text-align: left;
  position: sticky; left: 0;
}
```

- [ ] **Step 2: Add the Historical tab button**

In the tab switcher (lines ~208-211), change:

```html
    <div class="tab-switcher" id="tab-switcher">
      <button class="active" data-tab="upcoming">Upcoming</button>
      <button data-tab="reported">Reported</button>
    </div>
```
to:
```html
    <div class="tab-switcher" id="tab-switcher">
      <button class="active" data-tab="upcoming">Upcoming</button>
      <button data-tab="reported">Reported</button>
      <button data-tab="historical">Historical</button>
    </div>
```

- [ ] **Step 3: Add the history zoom state variable**

After the `ZOOM_DAYS_REPORTED` lines (~line 242-243), add:

```javascript
let ZOOM_DAYS_HISTORY = parseInt(localStorage.getItem('earnings_history_zoom') || '1095');
```

- [ ] **Step 4: Extend `syncRangeButtonsForTab()` with a historical branch**

Replace the body of `syncRangeButtonsForTab()` (lines ~245-272) with:

```javascript
function syncRangeButtonsForTab() {
  // Range button definitions differ between tabs; rebuild the chip set so the
  // active class and data-days match whichever tab is live.
  const group = document.getElementById('range-group');
  if (TAB === 'historical') {
    group.innerHTML = `
      <button data-days="365">1 Year</button>
      <button data-days="730">2 Years</button>
      <button data-days="1095">3 Years</button>
    `;
    const active = ZOOM_DAYS_HISTORY;
    document.querySelectorAll('#range-group button').forEach(b => {
      b.classList.toggle('active', parseInt(b.dataset.days) === active);
    });
  } else if (TAB === 'reported') {
    group.innerHTML = `
      <button data-days="7">1 Week</button>
      <button data-days="14">2 Weeks</button>
      <button data-days="30">1 Month</button>
      <button data-days="120">4 Months</button>
    `;
    const active = ZOOM_DAYS_REPORTED;
    document.querySelectorAll('#range-group button').forEach(b => {
      b.classList.toggle('active', parseInt(b.dataset.days) === active);
    });
  } else {
    group.innerHTML = `
      <button data-days="7">1 Week</button>
      <button data-days="14">2 Weeks</button>
      <button data-days="30">1 Month</button>
      <button data-days="90">3 Months</button>
    `;
    const active = ZOOM_DAYS;
    document.querySelectorAll('#range-group button').forEach(b => {
      b.classList.toggle('active', parseInt(b.dataset.days) === active);
    });
  }
}
```

- [ ] **Step 5: Route the render and range-chip handler for historical**

Change `render()` (lines ~397-409) from:

```javascript
function render() {
  if (TAB === 'reported') {
    renderReported();
  } else {
```
to:
```javascript
function render() {
  if (TAB === 'historical') {
    renderHistorical();
  } else if (TAB === 'reported') {
    renderReported();
  } else {
```

Then change the range-group click handler (lines ~846-859) from:

```javascript
  if (TAB === 'reported') {
    ZOOM_DAYS_REPORTED = v;
    localStorage.setItem('earnings_reported_zoom', v);
  } else {
    ZOOM_DAYS = v;
    localStorage.setItem('earnings_zoom', v);
  }
```
to:
```javascript
  if (TAB === 'historical') {
    ZOOM_DAYS_HISTORY = v;
    localStorage.setItem('earnings_history_zoom', v);
  } else if (TAB === 'reported') {
    ZOOM_DAYS_REPORTED = v;
    localStorage.setItem('earnings_reported_zoom', v);
  } else {
    ZOOM_DAYS = v;
    localStorage.setItem('earnings_zoom', v);
  }
```

- [ ] **Step 6: Add `renderHistorical()` and its helpers**

Insert immediately before `// --- EVENT LISTENERS ---` (line ~836):

```javascript
// --- HISTORICAL MATRIX ---
function cqLabel(cq) {
  // "2025Q2" -> "Q2 '25"
  const m = /^(\d{4})Q([1-4])$/.exec(cq);
  return m ? `Q${m[2]} '${m[1].slice(2)}` : cq;
}
function cqStart(cq) {
  // "2025Q2" -> Date(2025, 3, 1) (quarter-start, local midnight)
  const m = /^(\d{4})Q([1-4])$/.exec(cq);
  return m ? new Date(parseInt(m[1]), (parseInt(m[2]) - 1) * 3, 1) : null;
}
function filteredHistoryTickers() {
  // Portfolio group first, then Watchlist; alpha within group. Group is read
  // from DATA.companies; tickers absent there default to Watchlist.
  if (!DATA || !DATA.date_history) return [];
  const groupOf = {};
  for (const c of (DATA.companies || [])) groupOf[c.ticker] = c.group;
  let list = Object.keys(DATA.date_history)
    .map(t => ({ ticker: t, group: groupOf[t] || 'Watchlist' }));
  if (FILTER !== 'all') list = list.filter(x => x.group === FILTER);
  const rank = g => (g === 'Portfolio' ? 0 : 1);
  list.sort((a, b) => rank(a.group) - rank(b.group) || a.ticker.localeCompare(b.ticker));
  return list;
}
function renderHistorical() {
  const lanes = document.getElementById('lanes');
  const tl = document.getElementById('mini-timeline');
  const empty = document.getElementById('empty');
  tl.style.display = 'none';

  const dh = DATA.date_history || {};
  const today = new Date(DATA.snapshot_date + 'T00:00:00');
  const cutoff = new Date(today);
  cutoff.setDate(cutoff.getDate() - ZOOM_DAYS_HISTORY);

  const rows = filteredHistoryTickers();

  // Distinct calendar quarters within range across the filtered tickers.
  const cqSet = new Set();
  for (const row of rows) {
    for (const e of (dh[row.ticker] || [])) {
      const start = cqStart(e.cq);
      if (start && start >= cutoff && start <= today) cqSet.add(e.cq);
    }
  }
  const cols = Array.from(cqSet).sort(); // "YYYYQn" sorts chronologically

  if (!rows.length || !cols.length) {
    lanes.style.display = 'none';
    empty.style.display = 'block';
    empty.innerHTML = 'No historical earnings dates in this snapshot. '
      + 'Run <code>python pull_earnings.py</code> to populate the last 3 years.';
    return;
  }
  empty.style.display = 'none';
  lanes.style.display = 'block';

  let html = '<div class="hist-wrap"><table class="hist-matrix">';
  html += '<thead><tr><th class="hist-ticker-h">Ticker</th>';
  for (const cq of cols) html += `<th>${cqLabel(cq)}</th>`;
  html += '</tr></thead><tbody>';

  let lastGroup = null;
  const showDividers = (FILTER === 'all');
  for (const row of rows) {
    if (showDividers && row.group !== lastGroup) {
      html += `<tr class="hist-group"><td colspan="${cols.length + 1}">${row.group}</td></tr>`;
      lastGroup = row.group;
    }
    // cq -> latest date (latest wins if a quarter has >1 print)
    const byCq = {};
    for (const e of (dh[row.ticker] || [])) {
      if (!byCq[e.cq] || e.date > byCq[e.cq]) byCq[e.cq] = e.date;
    }
    html += `<tr><td class="hist-ticker">${row.ticker}</td>`;
    for (const cq of cols) {
      const iso = byCq[cq];
      if (iso) {
        const d = new Date(iso + 'T00:00:00');
        const cell = d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
        const tip = d.toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
        html += `<td title="${tip}">${cell}</td>`;
      } else {
        html += `<td class="hist-empty">&mdash;</td>`;
      }
    }
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  lanes.innerHTML = html;
}
```

- [ ] **Step 7: Verify the empty state over a local server**

The dashboard fetches JSON via relative paths, so it must be served over HTTP.

Run (from the repo root):
```bash
python -m http.server 8000 --directory output
```
Open `http://localhost:8000/dashboards/earnings.html`, click **Historical**.
Expected: the empty-state message "No historical earnings dates in this snapshot…" (the current snapshot has no `date_history` yet). Confirm the tab pill highlights and the range chips switch to 1 Year / 2 Years / 3 Years.

- [ ] **Step 8: Verify the matrix renders with a fixture**

Find the latest snapshot filename:
```bash
python -c "import json;print(json.load(open('output/snapshots/index_earnings.json'))[0])"
```
This prints e.g. `2026-06-19`. Add a temporary `date_history` block to that snapshot. Edit `output/snapshots/earnings_<DATE>.json`: insert this key at the top level (e.g. right after the `"snapshot_date"` line):

```json
  "date_history": {
    "JPM": [
      {"date": "2023-07-14", "cq": "2023Q3"},
      {"date": "2023-10-13", "cq": "2023Q4"},
      {"date": "2024-01-12", "cq": "2024Q1"},
      {"date": "2024-04-12", "cq": "2024Q2"},
      {"date": "2024-07-12", "cq": "2024Q3"},
      {"date": "2024-10-11", "cq": "2024Q4"},
      {"date": "2025-01-15", "cq": "2025Q1"},
      {"date": "2025-04-11", "cq": "2025Q2"},
      {"date": "2026-04-11", "cq": "2026Q2"}
    ],
    "UNH": [
      {"date": "2024-04-16", "cq": "2024Q2"},
      {"date": "2025-04-17", "cq": "2025Q2"}
    ]
  },
```

Reload `http://localhost:8000/dashboards/earnings.html` on the Historical tab and confirm:
- A matrix with a `JPM` row and (under filter **All**) a `UNH` row, columns labelled `Q3 '23 … Q2 '26`.
- JPM cells show the dates (`Jul 14`, `Oct 13`, …); empty bins show `—`. Hovering a cell shows the weekday + full date.
- Toggling **1 Year / 2 Years / 3 Years** shrinks/grows the column count; the active chip persists across reload (`earnings_history_zoom`).
- Toggling **Portfolio / Watchlist / All** filters rows; **All** shows `Portfolio` / `Watchlist` divider rows.
- Switch to Historical, reload — the page reopens on Historical (`earnings_tab`), and Upcoming/Reported still work unchanged.

- [ ] **Step 9: Restore the snapshot fixture**

Undo the temporary edit so the real data is untouched:
```bash
git checkout -- output/snapshots/earnings_<DATE>.json
```
Confirm `git status` shows no change to that snapshot.

- [ ] **Step 10: Commit**

```bash
git add output/dashboards/earnings.html
git commit -m "feat: Historical tab — 3-year report-date matrix"
```

---

## Post-implementation (user action, not a code task)

The Historical tab stays empty until a snapshot containing `date_history` is generated. On the Bloomberg machine, run `python scripts/pull_earnings.py` (or wait for the Friday "BBG Weekly Snapshot" task), then commit + push the new snapshot so GitHub Pages serves it.

---

## Self-Review

**Spec coverage:**
- New Historical pill + client switch → Task 3 Steps 2, 5. ✓
- Matrix (rows = ticker, cols = calendar quarter of report date, date-only cells) → Task 3 Step 6. ✓
- Portfolio-first / Watchlist ordering + All dividers → Task 3 Step 6 (`filteredHistoryTickers`, `hist-group` rows). ✓
- Calendar-quarter binning rule (`YYYYQn`) → Task 1 `_calendar_quarter`; column labels via `cqLabel`. ✓
- ~3.25-year window (1188 days) → Task 1 `_build_date_history`. ✓
- `1Y/2Y/3Y` range chips, default 3Y, key `earnings_history_zoom` → Task 3 Steps 3-5. ✓
- `date_history` snapshot key, keyed by short ticker, sorted ascending → Tasks 1-2. ✓
- New pull phase `[10/10]` + counter bumps → Task 2 Steps 1-4. ✓
- Mini-timeline hidden on tab → Task 3 Step 6 (`tl.style.display = 'none'`). ✓
- Empty-state message → Task 3 Step 6 + verified Step 7. ✓
- Multiple-prints-per-quarter: latest wins → Task 3 Step 6 (`byCq` comparison). ✓
- Snapshot missing `date_history` handled as `{}` → Task 3 Step 6 (`const dh = DATA.date_history || {}`). ✓
- Hover shows weekday/full date → Task 3 Step 6 (`title` attr). ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code; every command has expected output. ✓

**Type consistency:** `date_history` shape `{short: [{date, cq}]}` consistent across Tasks 1-3. `cq` format `YYYYQn` produced by `_calendar_quarter`, consumed by `cqLabel`/`cqStart`/sort. `ZOOM_DAYS_HISTORY` (1095 default) consistent in declaration, `syncRangeButtonsForTab`, click handler, and `renderHistorical`. Function names `renderHistorical`/`filteredHistoryTickers`/`cqLabel`/`cqStart` match between definition and call sites. ✓
