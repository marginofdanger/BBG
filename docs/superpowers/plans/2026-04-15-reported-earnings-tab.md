# Reported Earnings Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Reported" tab to `earnings.html` that tracks companies which reported in the last 45 days, showing actuals vs. consensus for each configured metric, 1D/1W/1W‑vs‑SPX stock reaction, and the 1‑week NTM EPS revision delta. Data ships in a new `reported[]` key of the same daily snapshot JSON.

**Architecture:** Data extension in `scripts/pull_earnings.py` (one new function + one new phase wired into `main()`), written alongside the existing `companies[]` array into `output/snapshots/earnings_YYYY-MM-DD.json`. Dashboard gets a client-side tab switcher plus a new render path that reads `DATA.reported`. No new files beyond the spec itself.

**Tech Stack:** Python 3.13, xbbg (Bloomberg BDP/BDS/BDH), vanilla JS + HTML + CSS (no build step).

**Spec reference:** `docs/superpowers/specs/2026-04-15-reported-earnings-tab-design.md`

---

## File Structure

**Modify:**
- `config/earnings_metrics.json` — add `actual_field` to each entry in `_field_map` so actuals can be pulled for every configured metric (not just EPS/Revenue).
- `scripts/pull_earnings.py` — add `pull_reported_details()` function; call it from `main()`; write `reported` key to snapshot JSON.
- `output/dashboards/earnings.html` — add CSS for reported cards and tab pills; add tab-switcher HTML; add `renderReported()`, `buildReportedCard()`, `filteredReported()`; extend state persistence.

**No new files.**

---

## Task 1: Add `actual_field` to metric config

**Goal:** Map every metric in `_field_map` to the Bloomberg fundamentals field that returns the reported actual, so `pull_reported_details()` can iterate the config instead of hardcoding EPS/Revenue.

**Files:**
- Modify: `config/earnings_metrics.json`

- [ ] **Step 1: Edit `_field_map`**

Replace the existing `_field_map` block with:

```json
"_field_map": {
  "EPS":            { "field": "BEST_EPS",                  "actual_field": "IS_COMP_EPS_ADJUSTED",         "format": "number",  "decimals": 2 },
  "Revenue":        { "field": "BEST_SALES",                "actual_field": "IS_COMP_SALES",                "format": "number",  "decimals": 1, "unit": "B", "divisor": 1000 },
  "EBITDA":         { "field": "BEST_EBITDA",               "actual_field": "EBITDA",                       "format": "number",  "decimals": 1, "unit": "B", "divisor": 1000 },
  "Op. Income":     { "field": "BEST_EBIT",                 "actual_field": "IS_OPER_INC",                  "format": "number",  "decimals": 1, "unit": "B", "divisor": 1000 },
  "Gross Margin":   { "field": "BEST_GROSS_MARGIN",         "actual_field": "GROSS_MARGIN",                 "format": "percent", "decimals": 1 },
  "Op. Margin":     { "field": "BEST_OPR_MARGIN",           "actual_field": "OPER_MARGIN",                  "format": "percent", "decimals": 1 },
  "Capex":          { "field": "BEST_CAPEX",                "actual_field": "CF_CAP_EXPEND_INC_FIX_ASSET",  "format": "number",  "decimals": 1, "unit": "B", "divisor": 1000 },
  "NII":            { "field": "BEST_NET_INTEREST_INCOME",  "actual_field": "NET_INT_INC",                  "format": "number",  "decimals": 1, "unit": "B", "divisor": 1000 },
  "Net Premiums":   { "field": "BEST_NET_PREMIUMS_WRITTEN", "actual_field": "NET_PREMIUM_EARNED",           "format": "number",  "decimals": 1, "unit": "B", "divisor": 1000 },
  "Combined Ratio": { "field": "BEST_COMBINED_RATIO",       "actual_field": "COMBINED_RATIO",               "format": "percent", "decimals": 1 }
}
```

Leave every other key in the file untouched.

- [ ] **Step 2: Verify JSON parses**

Run: `python -c "import json; print(len(json.load(open('config/earnings_metrics.json'))['_field_map']))"`

Expected: `10`

- [ ] **Step 3: Commit**

```bash
git add config/earnings_metrics.json
git commit -m "config: add actual_field to earnings metrics map"
```

---

## Task 2: Scaffold `pull_reported_details()` — ticker filter and return shape

**Goal:** Create the function skeleton that returns a `reported[]` list containing only tickers whose most recent earnings date is within the last 45 days. Later tasks fill in per-ticker data.

**Files:**
- Modify: `scripts/pull_earnings.py` (add new function after `pull_earnings_history`, around line 561)

- [ ] **Step 1: Add the skeleton function**

Add immediately after the `pull_earnings_history` function (after the line `return result` that closes it, around line 561):

```python
def pull_reported_details(bbg_tickers, metrics_config, group_lookup):
    """Pull actuals vs. consensus, stock reaction, and NTM EPS delta for
    tickers that reported in the last 45 days.

    group_lookup: {bbg_ticker: "Portfolio"|"Watchlist"} used to tag records.

    Returns a list of dicts:
        {
          "ticker", "group", "earnings_date", "earnings_time",
          "metrics": [{"name", "actual", "consensus", "surprise", "yoy"}, ...],
          "stock":   {"d1", "w1", "w1_vs_spx"},
          "ntm_eps_chg": float or None,
        }
    """
    field_map = metrics_config["_field_map"]
    today = date.today()
    window_start = today - timedelta(days=45)
    reported = []

    for bt in bbg_tickers:
        short = bt.split(" ")[0]

        # Find the most recent earnings date via ERN_ANN_DT_AND_PER (same source
        # the earnings_history phase uses). Take the newest row whose date is
        # <= today; skip the ticker if nothing falls in the 45-day window.
        try:
            df = blp.bds(bt, "ERN_ANN_DT_AND_PER")
            quarters = []
            for row in df.rows():
                period = str(row[3]) if len(row) > 3 else str(row[2])
                if ":Q" not in period:
                    continue
                try:
                    dt = date.fromisoformat(str(row[2]))
                except (ValueError, TypeError):
                    continue
                quarters.append({"date": dt, "period": period})
        except Exception:
            continue

        past = [q for q in quarters if q["date"] <= today]
        if not past:
            continue
        past.sort(key=lambda q: q["date"], reverse=True)
        last = past[0]
        if last["date"] < window_start:
            continue

        # Absolute period override: "2025:Q4" -> "25Q4"
        parts = last["period"].split(":")
        yr = parts[0][2:] if len(parts[0]) == 4 else parts[0]
        abs_period = f"{yr}{parts[1]}" if len(parts) > 1 else None
        if not abs_period:
            continue

        ticker_metrics = metrics_config.get(short, metrics_config["_default"])

        record = {
            "ticker": short,
            "group": group_lookup.get(bt, ""),
            "earnings_date": last["date"].isoformat(),
            "earnings_time": "",  # filled in Task 3 from existing dates phase
            "metrics": [],        # filled in Task 3
            "stock": {"d1": None, "w1": None, "w1_vs_spx": None},  # Task 4
            "ntm_eps_chg": None,  # Task 5
        }
        reported.append(record)

    return reported
```

- [ ] **Step 2: Wire the function into `main()` with a placeholder call**

In `main()` (around line 695, right after the `history_data = pull_earnings_history(...)` line), add:

```python
    # Step 9: Reported details (last 45 days)
    print("\n[9/9] Reported actuals & post-earnings moves...")
    group_lookup = {e["bbg"]: e["group"] for e in all_tickers}
    reported_data = pull_reported_details(bbg_tickers, config, group_lookup)
```

Also update the earlier phase-header prints so the numerator reflects the new total:

```
[1/9] Earnings dates...
[2/9] Consensus estimates...
[3/9] Prior-year actuals...
[4/9] Guidance ranges...
[5/9] Revision counts...
[6/9] EPS 4-week change...
[7/9] Prior FY actual EPS...
[8/9] Earnings history (last 4 quarters)...
[9/9] Reported actuals & post-earnings moves...
```

- [ ] **Step 3: Write the `reported` key into the output JSON**

In `main()`, find the `output = { ... }` dict assembly (around line 793) and change it to:

```python
    output = {
        "snapshot_date": today_str,
        "companies": companies,
        "reported": reported_data,
    }
```

- [ ] **Step 4: Run the script and verify**

Run: `python scripts/pull_earnings.py`

Expected: exit 0, output includes `[9/9] Reported actuals & post-earnings moves...`, and the saved snapshot contains a top-level `reported` array. Confirm with:

```bash
python -c "import json; d=json.load(open('output/snapshots/earnings_$(date +%Y-%m-%d).json')); print('reported count:', len(d.get('reported', []))); print('tickers:', [r['ticker'] for r in d.get('reported', [])])"
```

At least JPM should appear (reported 2026-04-14). Every record should have empty `metrics`, `stock` all-null, `ntm_eps_chg` null — filled in later tasks.

- [ ] **Step 5: Commit**

```bash
git add scripts/pull_earnings.py
git commit -m "feat: scaffold reported earnings details phase"
```

---

## Task 3: Fill `metrics[]` — actuals, pre-earnings consensus, surprise, y/y

**Goal:** For each reported ticker, pull the actual value, the pre-earnings consensus, and compute surprise % and y/y for every metric in that ticker's config.

**Files:**
- Modify: `scripts/pull_earnings.py` — extend `pull_reported_details`

- [ ] **Step 1: Add metric-pulling logic inside the ticker loop**

Inside `pull_reported_details`, replace the line `record["metrics"] = []  # filled in Task 3` (which was a placeholder in Task 2) — the record is already built but `metrics` is an empty list. Just before `reported.append(record)`, insert:

```python
        usd_ovr = [("EQY_FUND_CRNCY", "USD")] if short in USD_OVERRIDE_TICKERS else []
        eps_ovr = EPS_OVERRIDES.get(bt, {})
        eps_actual_field_override = eps_ovr.get("eps_field")       # e.g. IS_DILUTED_EPS
        eps_estimate_field_override = eps_ovr.get("est_field")     # e.g. BEST_EPS_GAAP
        eps_ticker = eps_ovr.get("eps_ticker", bt)
        eps_mult = eps_ovr.get("eps_mult", 1)
        skip_usd_est = eps_ovr.get("skip_usd_est", False)
        est_usd = [] if skip_usd_est else usd_ovr
        # When actuals come from a different ticker, don't apply USD override
        eps_act_ovr = [] if eps_ticker != bt else usd_ovr

        # Pre-earnings consensus is pulled via BDH over a 10-day window ending
        # the day before earnings. Use the last value (= consensus going in).
        pre_start = (last["date"] - timedelta(days=10)).strftime("%Y-%m-%d")
        pre_end = (last["date"] - timedelta(days=1)).strftime("%Y-%m-%d")
        # Prior-year actuals come from a 550-day BDH window (same pattern the
        # existing earnings_history phase uses), then matched by date.
        lookback_start = (last["date"] - timedelta(days=550)).strftime("%Y-%m-%d")
        lookback_end = last["date"].strftime("%Y-%m-%d")

        for metric_name in ticker_metrics:
            fmt_info = field_map.get(metric_name, {})
            if not fmt_info:
                continue
            fmt = fmt_info.get("format", "number")
            est_field = fmt_info["field"]
            actual_field = fmt_info.get("actual_field")

            # EPS has ticker-specific field overrides
            if metric_name == "EPS":
                if eps_estimate_field_override:
                    est_field = eps_estimate_field_override
                if eps_actual_field_override:
                    actual_field = eps_actual_field_override

            actual = None
            consensus = None
            yoy_str = None

            # --- Actual: BDH quarterly, find the row on/near last["date"] ---
            if actual_field:
                act_ticker = eps_ticker if metric_name == "EPS" else bt
                act_ovr = eps_act_ovr if metric_name == "EPS" else usd_ovr
                try:
                    df_act = blp.bdh(act_ticker, actual_field,
                                     lookback_start, lookback_end,
                                     periodicitySelection="QUARTERLY",
                                     overrides=act_ovr)
                    tbl = df_act.to_native()
                    dates_col = [str(d) for d in tbl.column("date").to_pylist()]
                    vals_col = tbl.column("value").to_pylist()
                    # Pick the latest row whose date is <= the announcement date
                    # (Bloomberg dates quarterly actuals at fiscal-period end).
                    earn_str = last["date"].isoformat()
                    best_val = best_prior = None
                    for d, v in zip(dates_col, vals_col):
                        try:
                            fv = float(v)
                        except (ValueError, TypeError):
                            continue
                        if d <= earn_str:
                            best_prior = best_val
                            best_val = fv
                    if best_val is not None:
                        actual = best_val * eps_mult if metric_name == "EPS" else best_val
                        # Capex: Bloomberg returns negative; show magnitude
                        if metric_name == "Capex" and actual is not None:
                            actual = abs(actual)
                    # Prior-year (4 quarters back) for Y/Y: walk back 4 rows
                    if len(dates_col) >= 5:
                        try:
                            latest_idx = max(
                                i for i, d in enumerate(dates_col)
                                if d <= earn_str
                            )
                            if latest_idx >= 4:
                                prior_raw = vals_col[latest_idx - 4]
                                prior_val = float(prior_raw)
                                if metric_name == "EPS":
                                    prior_val *= eps_mult
                                if metric_name == "Capex":
                                    prior_val = abs(prior_val)
                                yoy_str = compute_yoy(actual, prior_val, fmt)
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    pass

            # --- Pre-earnings consensus: BDH BEST_* with absolute period ---
            try:
                ovr = [("BEST_FPERIOD_OVERRIDE", abs_period)] + est_usd
                df_cons = blp.bdh(bt, est_field, pre_start, pre_end,
                                  periodicitySelection="DAILY", overrides=ovr)
                tbl = df_cons.to_native()
                cvals = [float(v) for v in tbl.column("value").to_pylist()]
                if cvals:
                    consensus = cvals[-1]
                    if metric_name == "Capex":
                        consensus = abs(consensus)
            except Exception:
                pass

            # --- Surprise % ---
            surprise = None
            if actual is not None and consensus not in (None, 0):
                surprise = (actual - consensus) / abs(consensus)

            record["metrics"].append({
                "name": metric_name,
                "actual": actual,
                "consensus": consensus,
                "surprise": surprise,
                "yoy": yoy_str,
            })
```

- [ ] **Step 2: Populate `earnings_time` from existing dates phase**

`pull_reported_details` already takes `bbg_tickers` and `metrics_config`. The existing dates phase output (`dates_data`) has `earnings_time` per ticker but is populated in `main()`, not passed to our function. Rather than plumbing it through, grab the time inline from the most recent earnings — use `ANNOUNCEMENT_TIME` on the reported ticker if available, or leave blank.

Simplest: leave `earnings_time` empty for now (the dashboard already tolerates empty strings). Delete the `"earnings_time": "",  # filled in Task 3...` comment to keep the code clean:

In the record dict initializer, change:
```python
            "earnings_time": "",  # filled in Task 3 from existing dates phase
```
to:
```python
            "earnings_time": "",
```

- [ ] **Step 3: Run and inspect**

```bash
python scripts/pull_earnings.py
python -c "
import json, datetime as dt
d=json.load(open(f'output/snapshots/earnings_{dt.date.today().isoformat()}.json'))
import pprint
jpm=[r for r in d.get('reported',[]) if r['ticker']=='JPM']
pprint.pprint(jpm[0] if jpm else 'JPM not in reported')
"
```

Expected: JPM's `metrics` has rows for EPS, Revenue, NII — each with non-null `actual` and `consensus`, a sensible `surprise` decimal (e.g., ~0.08 for JPM Q1'26), and a y/y string like `+20%`.

If `actual` is null for NII, that's OK — the field may not return for JPM via `NET_INT_INC` — the row still renders as "—" in the UI.

- [ ] **Step 4: Commit**

```bash
git add scripts/pull_earnings.py
git commit -m "feat: reported metrics actuals, consensus, surprise"
```

---

## Task 4: Fill `stock[]` — 1D, 1W, 1W vs SPX

**Goal:** Pull PX_LAST around each reported ticker's earnings date and compute three reaction numbers. SPX comes from a single shared fetch per run.

**Files:**
- Modify: `scripts/pull_earnings.py` — extend `pull_reported_details`

- [ ] **Step 1: Pre-fetch SPX prices once at the top of `pull_reported_details`**

Right after the line `window_start = today - timedelta(days=45)` (near the top of the function), add:

```python
    # Batch one SPX pull covering the whole window (+7 trading days buffer).
    spx_by_date = {}
    try:
        df_spx = blp.bdh("SPX Index", "PX_LAST",
                         (window_start - timedelta(days=7)).strftime("%Y-%m-%d"),
                         (today + timedelta(days=2)).strftime("%Y-%m-%d"))
        tbl = df_spx.to_native()
        for d, v in zip(tbl.column("date").to_pylist(),
                        tbl.column("value").to_pylist()):
            try:
                spx_by_date[str(d)] = float(v)
            except (ValueError, TypeError):
                pass
    except Exception:
        pass
    spx_dates_sorted = sorted(spx_by_date.keys())
```

- [ ] **Step 2: Add a helper for "nth trading day relative to a target"**

Still inside `pull_reported_details`, just after the SPX pre-fetch, add a nested helper:

```python
    def _price_on_or_after(prices_by_date, sorted_dates, target):
        """Return (date_str, price) for the earliest trading day >= target."""
        t = target if isinstance(target, str) else target.isoformat()
        for d in sorted_dates:
            if d >= t:
                return d, prices_by_date[d]
        return None, None

    def _price_on_or_before(prices_by_date, sorted_dates, target):
        """Return (date_str, price) for the latest trading day <= target."""
        t = target if isinstance(target, str) else target.isoformat()
        out = (None, None)
        for d in sorted_dates:
            if d <= t:
                out = (d, prices_by_date[d])
            else:
                break
        return out
```

- [ ] **Step 3: Pull per-ticker stock prices and compute reactions**

Inside the per-ticker loop, after the `for metric_name in ticker_metrics:` block finishes (after the closing of the metrics loop, and before `reported.append(record)`), add:

```python
        # --- Stock reaction: pull a narrow window around earnings_date ---
        try:
            rxn_start = (last["date"] - timedelta(days=4)).strftime("%Y-%m-%d")
            rxn_end = (last["date"] + timedelta(days=14)).strftime("%Y-%m-%d")
            df_rxn = blp.bdh(bt, "PX_LAST", rxn_start, rxn_end)
            tbl = df_rxn.to_native()
            px_by_date = {}
            for d, v in zip(tbl.column("date").to_pylist(),
                            tbl.column("value").to_pylist()):
                try:
                    px_by_date[str(d)] = float(v)
                except (ValueError, TypeError):
                    pass
            px_dates = sorted(px_by_date.keys())

            pre_day, pre_px = _price_on_or_before(
                px_by_date, px_dates, last["date"] - timedelta(days=1))
            d1_day, d1_px = _price_on_or_after(
                px_by_date, px_dates, last["date"])
            # "1W" = 5 trading days after the earnings-day close
            w1_px = None
            if d1_day is not None:
                idx = px_dates.index(d1_day)
                if idx + 5 < len(px_dates):
                    w1_px = px_by_date[px_dates[idx + 5]]
                    w1_day = px_dates[idx + 5]
                else:
                    w1_day = None
            else:
                w1_day = None

            if pre_px and d1_px:
                record["stock"]["d1"] = round((d1_px - pre_px) / pre_px, 4)
            if pre_px and w1_px:
                record["stock"]["w1"] = round((w1_px - pre_px) / pre_px, 4)

            # Relative vs SPX over the same window
            if pre_px and w1_px and spx_dates_sorted:
                _, spx_pre = _price_on_or_before(
                    spx_by_date, spx_dates_sorted, last["date"] - timedelta(days=1))
                _, spx_post = _price_on_or_after(
                    spx_by_date, spx_dates_sorted,
                    (last["date"] + timedelta(days=10)).isoformat())
                # Use the same number of trading days as the ticker: match w1_day
                if w1_day and w1_day in spx_by_date:
                    spx_post = spx_by_date[w1_day]
                if spx_pre and spx_post:
                    spx_w1 = (spx_post - spx_pre) / spx_pre
                    record["stock"]["w1_vs_spx"] = round(
                        record["stock"]["w1"] - spx_w1, 4)
        except Exception:
            pass
```

- [ ] **Step 4: Run and inspect**

```bash
python scripts/pull_earnings.py
python -c "
import json, datetime as dt
d=json.load(open(f'output/snapshots/earnings_{dt.date.today().isoformat()}.json'))
for r in d.get('reported',[]):
    print(r['ticker'], r['earnings_date'], r['stock'])
"
```

Expected: JPM shows a d1 value (e.g., `-0.008`), and if the `w1` window has fully elapsed, w1 and w1_vs_spx are non-null. Otherwise w1/w1_vs_spx stay null (cards will show "—" for those).

- [ ] **Step 5: Commit**

```bash
git add scripts/pull_earnings.py
git commit -m "feat: reported stock reaction (1D, 1W, 1W vs SPX)"
```

---

## Task 5: Fill `ntm_eps_chg`

**Goal:** For each reported ticker, compute NTM EPS consensus change from the trading day before earnings to the trading day on-or-after earnings+7 calendar days.

**Files:**
- Modify: `scripts/pull_earnings.py` — extend `pull_reported_details`

- [ ] **Step 1: Add NTM EPS delta pull**

Still inside the per-ticker loop, after the stock reaction block and before `reported.append(record)`, add:

```python
        # --- NTM EPS consensus delta (day-before -> 7 days after) ---
        try:
            ntm_ovr = [("BEST_FPERIOD_OVERRIDE", "NTM")]
            if short in USD_OVERRIDE_TICKERS and not skip_usd_est:
                ntm_ovr.append(("EQY_FUND_CRNCY", "USD"))
            ntm_start = (last["date"] - timedelta(days=4)).strftime("%Y-%m-%d")
            ntm_end = (last["date"] + timedelta(days=14)).strftime("%Y-%m-%d")
            df_ntm = blp.bdh(bt, "BEST_EPS", ntm_start, ntm_end,
                             periodicitySelection="DAILY", overrides=ntm_ovr)
            tbl = df_ntm.to_native()
            ntm_by_date = {}
            for d, v in zip(tbl.column("date").to_pylist(),
                            tbl.column("value").to_pylist()):
                try:
                    ntm_by_date[str(d)] = float(v)
                except (ValueError, TypeError):
                    pass
            ntm_dates = sorted(ntm_by_date.keys())

            # Pre: latest trading day <= earnings_date - 1 day
            _, ntm_pre = _price_on_or_before(
                ntm_by_date, ntm_dates, last["date"] - timedelta(days=1))
            # Post: earliest trading day >= earnings_date + 7 days
            _, ntm_post = _price_on_or_after(
                ntm_by_date, ntm_dates, last["date"] + timedelta(days=7))
            if ntm_pre and ntm_post and ntm_pre != 0:
                record["ntm_eps_chg"] = round((ntm_post - ntm_pre) / ntm_pre, 4)
        except Exception:
            pass
```

- [ ] **Step 2: Run and inspect**

```bash
python scripts/pull_earnings.py
python -c "
import json, datetime as dt
d=json.load(open(f'output/snapshots/earnings_{dt.date.today().isoformat()}.json'))
for r in d.get('reported',[]):
    print(r['ticker'], r['earnings_date'], 'ntm_eps_chg:', r['ntm_eps_chg'])
"
```

Expected: for a ticker that reported 7+ calendar days ago (e.g., if any are in the window), `ntm_eps_chg` is a decimal like `0.018` or `-0.005`. JPM reporting 2026-04-14 (today 2026-04-15) will still be `null` until +7 days, which is correct.

- [ ] **Step 3: Commit**

```bash
git add scripts/pull_earnings.py
git commit -m "feat: reported NTM EPS change (1W post)"
```

---

## Task 6: Sort reported list and finalize data phase

**Goal:** Sort `reported[]` by earnings_date descending (newest first) so the dashboard lanes get a predictable order.

**Files:**
- Modify: `scripts/pull_earnings.py`

- [ ] **Step 1: Sort before returning**

At the very end of `pull_reported_details`, just before `return reported`, add:

```python
    reported.sort(key=lambda r: r["earnings_date"], reverse=True)
```

- [ ] **Step 2: Run and verify ordering**

```bash
python scripts/pull_earnings.py
python -c "
import json, datetime as dt
d=json.load(open(f'output/snapshots/earnings_{dt.date.today().isoformat()}.json'))
print([(r['ticker'], r['earnings_date']) for r in d.get('reported',[])])
"
```

Expected: newest earnings_date first.

- [ ] **Step 3: Commit**

```bash
git add scripts/pull_earnings.py
git commit -m "feat: sort reported list newest first"
```

---

## Task 7: Dashboard — CSS for reported cards and tab pills

**Goal:** Add the styles needed for the tab switcher and the reported card's extended header strip.

**Files:**
- Modify: `output/dashboards/earnings.html` — inside the `<style>` block

- [ ] **Step 1: Add new CSS rules**

Add the following block at the end of the `<style>` block (immediately before the closing `</style>` tag, around line 149):

```css
/* Tab switcher */
.tab-switcher { display: flex; gap: 0; margin-right: 12px; }
.tab-switcher button {
  padding: 4px 14px; font-size: 11px; font-weight: 700; border: 1px solid #ccc;
  background: #fff; cursor: pointer; color: #555; text-transform: uppercase;
  letter-spacing: 0.5px;
}
.tab-switcher button:first-child { border-radius: 4px 0 0 4px; }
.tab-switcher button:last-child { border-radius: 0 4px 4px 0; border-left: none; }
.tab-switcher button.active { background: #2563eb; color: #fff; border-color: #2563eb; }

/* Reported card header strip */
.reported-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.reported-head .left { display: flex; align-items: center; gap: 8px; }
.reported-head .reported-badge {
  font-size: 10px; font-weight: 700; color: #6b7280; background: #f1f3f5;
  padding: 2px 8px; border-radius: 4px;
}
.rxn-strip { display: flex; gap: 12px; font-size: 10px; }
.rxn-strip .rxn-item { color: #6b7280; font-weight: 600; }
.rxn-strip .rxn-item .rxn-val { font-weight: 700; }
.rxn-strip .rxn-item .rxn-val.up { color: #16a34a; }
.rxn-strip .rxn-item .rxn-val.down { color: #dc2626; }
.rxn-strip .rxn-item.vs-spx .rxn-val { font-size: 11px; }

/* Reported metrics table reuses .metrics-table with a SURPRISE column */
.metrics-table td.surprise.beat { color: #16a34a; font-weight: 600; }
.metrics-table td.surprise.miss { color: #dc2626; font-weight: 600; }

/* NTM footer */
.ntm-footer {
  margin-top: 10px; border-top: 1px solid #f0f0f0; padding-top: 8px;
  font-size: 10px; color: #6b7280; font-weight: 600;
}
.ntm-footer .val { font-weight: 700; }
.ntm-footer .val.up { color: #16a34a; }
.ntm-footer .val.down { color: #dc2626; }
.ntm-footer .val.pending { color: #9ca3af; font-weight: 500; }

/* Reported lane headers */
.lane-header.reported-this-week { color: #16a34a; border-color: #16a34a; background: #f0fdf4; }
.lane-header.reported-last-week { color: #2563eb; border-color: #2563eb; background: #eff6ff; }
.lane-header.reported-older { color: #6b7280; border-color: #d1d5db; background: #f9fafb; }
```

- [ ] **Step 2: Commit**

```bash
git add output/dashboards/earnings.html
git commit -m "ui: css for reported tab cards and pills"
```

---

## Task 8: Dashboard — add tab switcher HTML and state

**Goal:** Insert the two-pill tab switcher in the header controls, with localStorage persistence.

**Files:**
- Modify: `output/dashboards/earnings.html`

- [ ] **Step 1: Add the tab switcher to the header**

In the `.controls` block (around line 158), insert the tab-switcher div as the **first** child of `.controls`, just after `<div class="controls">`:

```html
    <div class="tab-switcher" id="tab-switcher">
      <button class="active" data-tab="upcoming">Upcoming</button>
      <button data-tab="reported">Reported</button>
    </div>
    <a href="earnings_changes.html" style="font-size:11px;color:#2563eb;text-decoration:none;margin-right:8px;">Changes →</a>
```

Delete the existing standalone `<a href="earnings_changes.html" ...>` line (the old Changes link one row above where you just added the block), so there's only one.

- [ ] **Step 2: Add `TAB` to the top-of-script state block**

Find the state block near line 185 (`let DATA = null; let FILTER = ...`) and change it to:

```js
let DATA = null;
let TAB = localStorage.getItem('earnings_tab') || 'upcoming';
let FILTER = localStorage.getItem('earnings_filter') || 'Portfolio';
let ZOOM_DAYS = parseInt(localStorage.getItem('earnings_zoom') || '30');
let ZOOM_DAYS_REPORTED = parseInt(localStorage.getItem('earnings_reported_zoom') || '30');
```

- [ ] **Step 3: Add a tab-click handler**

In the event-listeners section (around line 582), add a new handler block immediately after the existing `range-group` handler:

```js
document.getElementById('tab-switcher').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  document.querySelectorAll('#tab-switcher button').forEach(b => b.classList.remove('active'));
  e.target.classList.add('active');
  TAB = e.target.dataset.tab;
  localStorage.setItem('earnings_tab', TAB);
  syncRangeButtonsForTab();
  render();
});
```

Then in the INIT section (around line 601), add:

```js
document.querySelectorAll('#tab-switcher button').forEach(b => {
  b.classList.toggle('active', b.dataset.tab === TAB);
});
```

- [ ] **Step 4: Stub `syncRangeButtonsForTab()` for now**

Add the helper function just above `loadData()`:

```js
function syncRangeButtonsForTab() {
  // Range button definitions differ between tabs; rebuild the chip set so the
  // active class and data-days match whichever tab is live.
  const group = document.getElementById('range-group');
  if (TAB === 'reported') {
    group.innerHTML = `
      <button data-days="7">1 Week</button>
      <button data-days="14">2 Weeks</button>
      <button data-days="30">1 Month</button>
      <button data-days="45">45 Days</button>
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

Also update the existing `range-group` click handler so it writes to the right variable depending on tab:

Replace the existing block:
```js
document.getElementById('range-group').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  document.querySelectorAll('#range-group button').forEach(b => b.classList.remove('active'));
  e.target.classList.add('active');
  ZOOM_DAYS = parseInt(e.target.dataset.days);
  localStorage.setItem('earnings_zoom', ZOOM_DAYS);
  render();
});
```
with:
```js
document.getElementById('range-group').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  document.querySelectorAll('#range-group button').forEach(b => b.classList.remove('active'));
  e.target.classList.add('active');
  const v = parseInt(e.target.dataset.days);
  if (TAB === 'reported') {
    ZOOM_DAYS_REPORTED = v;
    localStorage.setItem('earnings_reported_zoom', v);
  } else {
    ZOOM_DAYS = v;
    localStorage.setItem('earnings_zoom', v);
  }
  render();
});
```

And call `syncRangeButtonsForTab()` at init (just before `loadData();`):

```js
syncRangeButtonsForTab();
loadData();
```

- [ ] **Step 5: Verify the page still renders Upcoming correctly**

Open `output/dashboards/earnings.html` in a browser (or via the GitHub Pages URL after pushing — but for this step, open the local file). Confirm:
- Two tab pills show in the header, Upcoming is active.
- Clicking Reported updates pills and the range chips swap to 1W/2W/1M/45d. Nothing renders on the Reported tab yet — that's Task 9.
- Clicking Upcoming restores the original view with 1W/2W/1M/3M chips.
- Filter chips (Portfolio/Watchlist/All) still work.

- [ ] **Step 6: Commit**

```bash
git add output/dashboards/earnings.html
git commit -m "ui: add reported tab switcher with state persistence"
```

---

## Task 9: Dashboard — render the Reported tab (lanes + cards)

**Goal:** Implement `renderReported()`, `filteredReported()`, and `buildReportedCard()` so the Reported tab shows lanes grouped by week-of-report and cards with the header strip, metrics table, and NTM footer.

**Files:**
- Modify: `output/dashboards/earnings.html`

- [ ] **Step 1: Route `render()` by tab**

Replace the existing `render()` function (around line 218) with:

```js
function render() {
  if (TAB === 'reported') {
    renderReported();
  } else {
    const companies = filteredCompanies();
    if (!companies.length) { showEmpty(); return; }
    document.getElementById('empty').style.display = 'none';
    document.getElementById('lanes').style.display = 'flex';
    document.getElementById('mini-timeline').style.display = 'flex';
    renderTimeline(companies);
    renderLanes(companies);
  }
}
```

- [ ] **Step 2: Add `filteredReported()` and `renderReported()`**

Add these functions just below `filteredCompanies()` (around line 217):

```js
function filteredReported() {
  if (!DATA || !Array.isArray(DATA.reported)) return [];
  if (FILTER === 'all') return DATA.reported;
  return DATA.reported.filter(r => r.group === FILTER);
}

function renderReported() {
  const lanes = document.getElementById('lanes');
  const tl = document.getElementById('mini-timeline');
  const empty = document.getElementById('empty');

  // Reported tab has no timeline — hide it
  tl.style.display = 'none';

  const reported = filteredReported();
  const today = new Date(DATA.snapshot_date + 'T00:00:00');
  const cutoff = new Date(today);
  cutoff.setDate(cutoff.getDate() - ZOOM_DAYS_REPORTED);

  const windowed = reported.filter(r => {
    if (!r.earnings_date) return false;
    const d = new Date(r.earnings_date + 'T00:00:00');
    return d >= cutoff && d <= today;
  });

  if (!windowed.length) {
    lanes.style.display = 'none';
    empty.style.display = 'block';
    empty.innerHTML = 'No earnings reported in the selected window. Check the Upcoming tab.';
    return;
  }
  empty.style.display = 'none';
  lanes.style.display = 'flex';

  // Group by Mon-Sun week of earnings_date
  const weeks = {};
  for (const r of windowed) {
    const d = new Date(r.earnings_date + 'T00:00:00');
    const day = d.getDay();
    const mon = new Date(d);
    mon.setDate(d.getDate() - ((day + 6) % 7));
    const key = mon.toISOString().slice(0, 10);
    if (!weeks[key]) weeks[key] = { monday: new Date(mon), items: [] };
    weeks[key].items.push(r);
  }
  // Newest week first
  const sortedWeeks = Object.keys(weeks).sort().reverse();
  const todayMon = new Date(today);
  todayMon.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  const thisWeekKey = todayMon.toISOString().slice(0, 10);
  const lastWeekKey = new Date(todayMon.getTime() - 7 * 86400000).toISOString().slice(0, 10);

  lanes.innerHTML = '';
  for (const key of sortedWeeks) {
    const wk = weeks[key];
    // Sort within lane: newest first, then ticker alpha
    wk.items.sort((a, b) => {
      if (a.earnings_date !== b.earnings_date) return b.earnings_date.localeCompare(a.earnings_date);
      return a.ticker.localeCompare(b.ticker);
    });
    const fri = new Date(wk.monday);
    fri.setDate(fri.getDate() + 4);
    const monLabel = wk.monday.toLocaleDateString('en', { month: 'short', day: 'numeric' });
    const friLabel = fri.toLocaleDateString('en', { month: 'short', day: 'numeric' });

    let headerClass = 'reported-older';
    let headerLabel = `${monLabel} – ${friLabel}`;
    if (key === thisWeekKey) { headerClass = 'reported-this-week'; headerLabel = `This Week · ${monLabel} – ${friLabel}`; }
    else if (key === lastWeekKey) { headerClass = 'reported-last-week'; headerLabel = `Last Week · ${monLabel} – ${friLabel}`; }

    const lane = document.createElement('div');
    lane.className = 'lane';
    lane.innerHTML = `<div class="lane-header ${headerClass}">${headerLabel}<span class="count">(${wk.items.length})</span></div>`;
    for (const r of wk.items) {
      lane.innerHTML += buildReportedCard(r);
    }
    lanes.appendChild(lane);
  }

  // Attach expand/collapse handlers (reuse card pattern)
  lanes.querySelectorAll('.card').forEach(card => {
    card.querySelector('.card-head').addEventListener('click', () => {
      card.classList.toggle('collapsed');
    });
  });
}
```

- [ ] **Step 3: Add `buildReportedCard()`**

Add immediately after `buildCardNoDate()` (around line 580):

```js
function formatPct(v, digits) {
  if (v == null) return '&mdash;';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(digits != null ? digits : 1)}%`;
}
function signClass(v) {
  if (v == null) return '';
  return v >= 0 ? 'up' : 'down';
}

function buildReportedCard(r) {
  const dateObj = new Date(r.earnings_date + 'T00:00:00');
  const dateLabel = dateObj.toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric' });

  let html = `<div class="card" id="reported-${r.ticker}">`;

  // Header strip
  html += `<div class="card-head reported-head">`;
  html += `<div class="left">`;
  html += `<span class="ticker">${r.ticker}</span>`;
  html += `<span class="reported-badge">Reported ${dateLabel}</span>`;
  html += `</div>`;
  html += `<div class="rxn-strip">`;
  html += `<span class="rxn-item">1D <span class="rxn-val ${signClass(r.stock && r.stock.d1)}">${formatPct(r.stock && r.stock.d1)}</span></span>`;
  html += `<span class="rxn-item">1W <span class="rxn-val ${signClass(r.stock && r.stock.w1)}">${formatPct(r.stock && r.stock.w1)}</span></span>`;
  html += `<span class="rxn-item vs-spx">vs SPX <span class="rxn-val ${signClass(r.stock && r.stock.w1_vs_spx)}">${formatPct(r.stock && r.stock.w1_vs_spx)}</span></span>`;
  html += `</div>`;
  html += `</div>`;

  // Collapsed summary
  html += `<div class="card-summary">`;
  const epsM = (r.metrics || []).find(m => m.name === 'EPS');
  if (epsM && epsM.surprise != null) {
    html += `<span>EPS surprise ${formatPct(epsM.surprise)}</span>`;
  } else {
    html += `<span>—</span>`;
  }
  html += `<span class="expand-icon">&#9656;</span>`;
  html += `</div>`;

  // Body
  html += `<div class="card-body">`;
  html += `<table class="metrics-table">`;
  html += `<tr><th>Metric</th><th>Actual</th><th>Cons.</th><th>Surprise</th><th>Y/Y</th></tr>`;
  for (const m of (r.metrics || [])) {
    const surCls = m.surprise == null ? '' : (m.surprise >= 0 ? 'beat' : 'miss');
    html += `<tr>`;
    html += `<td class="metric-name">${m.name}</td>`;
    html += `<td class="consensus">${m.actual != null ? formatMetric(m.name, m.actual) : '&mdash;'}</td>`;
    html += `<td class="consensus" style="font-weight:500;color:#6b7280">${m.consensus != null ? formatMetric(m.name, m.consensus) : '&mdash;'}</td>`;
    html += `<td class="surprise ${surCls}">${m.surprise != null ? formatPct(m.surprise) : '&mdash;'}</td>`;
    html += `<td class="yoy ${yoyClass(m.yoy)}">${m.yoy || '&mdash;'}</td>`;
    html += `</tr>`;
  }
  html += `</table>`;

  // NTM EPS footer
  html += `<div class="ntm-footer">NTM EPS change (1W post): `;
  if (r.ntm_eps_chg == null) {
    html += `<span class="val pending">pending</span>`;
  } else {
    html += `<span class="val ${signClass(r.ntm_eps_chg)}">${formatPct(r.ntm_eps_chg)}</span>`;
  }
  html += `</div>`;

  html += `</div></div>`;
  return html;
}
```

- [ ] **Step 4: Verify end-to-end**

Open `output/dashboards/earnings.html` in a browser. Click the **Reported** pill. Confirm:
- At least one lane appears (JPM in "This Week" or "Last Week" depending on the snapshot date).
- The card header shows "JPM · Reported Tue, Apr 14" plus three rxn-strip items (1D / 1W / vs SPX). If w1 isn't computed yet, those show "—".
- The metrics table shows EPS, Revenue, NII rows with ACTUAL / CONS / SURPRISE / Y/Y columns.
- The footer shows "NTM EPS change (1W post): pending" for JPM (since today is 2026-04-15 and earnings were 2026-04-14, less than 7 days post).
- Clicking the card header collapses/expands it.
- Zoom chips (1W / 2W / 1M / 45d) filter the reported list by date.
- Switching back to Upcoming restores the original view identically.
- Refresh the page — the active tab, filter, and zoom persist.

- [ ] **Step 5: Commit**

```bash
git add output/dashboards/earnings.html
git commit -m "ui: render reported tab with lanes and cards"
```

---

## Task 10: Push and verify on GitHub Pages

**Goal:** Get the feature live so the user can see it on the hosted dashboard.

- [ ] **Step 1: Push**

```bash
git push
```

- [ ] **Step 2: Verify hosted version**

Wait ~1 minute for GitHub Pages to rebuild. Open `https://marginofdanger.github.io/BBG/output/dashboards/earnings.html` (or navigate from the user's existing tab), hard-refresh, click Reported, confirm the tab populates with JPM and any other tickers that reported in the last 45 days.

- [ ] **Step 3: Report completion**

Summarize to the user: which tickers appeared in Reported, which stock-reaction fields are non-null, and which are "pending" awaiting the +7 day window.

---

## Notes for the implementing engineer

- **No automated tests.** This codebase has no test suite for the earnings dashboard. Verification is manual (run script, inspect JSON, open HTML). Do not invent a test harness — the spec explicitly acknowledges this.
- **Don't touch the Upcoming tab's data or layout.** Every change is additive. If you find yourself editing existing `companies[]` code or `renderLanes()` for Upcoming, stop and reconsider.
- **Don't commit `__pycache__`, copy-pasted xlsx files, or `.claude/` directories.** Stage only the three files listed in File Structure.
- **If a Bloomberg field returns no data for a ticker (e.g., NII for GOOG), let the row render as "—".** Missing data is expected and handled downstream.
- **Bloomberg BDH calls already use try/except in the existing code.** Mirror that defensive pattern. A single bad ticker must not abort the phase.
- **`_price_on_or_before` / `_price_on_or_after` are nested helpers** defined inside `pull_reported_details`. Keep them scoped there; don't promote to module-level unless another caller needs them.
- **Push after every successful run of `pull_earnings.py`.** GitHub Pages serves committed files — local snapshots don't reach the user otherwise.
