# Earnings Calendar Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone earnings calendar dashboard showing upcoming earnings dates for portfolio/watchlist holdings with consensus estimates, company guidance, y/y growth, and revision momentum in a weekly swim-lane layout.

**Architecture:** A new Python script (`pull_earnings.py`) pulls earnings dates, consensus, guidance, revisions, and prior-year actuals from Bloomberg via xbbg, outputting a dated JSON snapshot. A standalone HTML page (`earnings.html`) loads the latest snapshot and renders weekly swim lanes with expandable company cards. A JSON config (`earnings_metrics.json`) controls which metrics appear per ticker.

**Tech Stack:** Python 3 + xbbg, vanilla HTML/CSS/JS, JSON snapshots via fetch()

**Spec:** `docs/superpowers/specs/2026-04-06-earnings-dashboard-design.md`

---

### Task 1: Create the metrics configuration file

**Files:**
- Create: `earnings_metrics.json`

- [ ] **Step 1: Create `earnings_metrics.json`**

```json
{
  "_field_map": {
    "EPS": { "field": "BEST_EPS", "format": "number", "decimals": 2 },
    "Revenue": { "field": "BEST_SALES", "format": "number", "decimals": 1, "unit": "B", "divisor": 1000 },
    "EBITDA": { "field": "BEST_EBITDA", "format": "number", "decimals": 1, "unit": "B", "divisor": 1000 },
    "Op. Income": { "field": "BEST_OPER_INCOME", "format": "number", "decimals": 1, "unit": "B", "divisor": 1000 },
    "Gross Margin": { "field": "BEST_GROSS_MARGIN", "format": "percent", "decimals": 1 },
    "Op. Margin": { "field": "BEST_OPR_MARGIN", "format": "percent", "decimals": 1 },
    "Capex": { "field": "BEST_CAPEX", "format": "number", "decimals": 1, "unit": "B", "divisor": 1000 },
    "NII": { "field": "BEST_NET_INTEREST_INCOME", "format": "number", "decimals": 1, "unit": "B", "divisor": 1000 },
    "Net Premiums": { "field": "BEST_NET_PREMIUMS_WRITTEN", "format": "number", "decimals": 1, "unit": "B", "divisor": 1000 },
    "Combined Ratio": { "field": "BEST_COMBINED_RATIO", "format": "percent", "decimals": 1 },
    "Provisions": { "field": "BEST_PROVISION_FOR_LOAN_LOSSES", "format": "number", "decimals": 2, "unit": "B", "divisor": 1000 }
  },
  "_guidance_fields": {
    "EPS": { "high": "GUIDANCE_EPS_HIGH", "mid": "GUIDANCE_EPS_MID", "low": "GUIDANCE_EPS_LOW" },
    "Revenue": { "high": "GUIDANCE_REVENUE_HIGH", "mid": "GUIDANCE_REVENUE_MID", "low": "GUIDANCE_REVENUE_LOW" }
  },
  "_default": ["EPS", "Revenue"],
  "JPM": ["EPS", "Revenue", "NII", "Provisions"],
  "UNH": ["EPS", "Revenue"],
  "TSM": ["EPS", "Revenue", "Gross Margin", "Op. Margin", "Capex"],
  "META": ["EPS", "Revenue", "Op. Margin", "Capex"],
  "AMZN": ["EPS", "Revenue", "Op. Income", "Capex"],
  "NVDA": ["EPS", "Revenue", "Gross Margin"],
  "AVGO": ["EPS", "Revenue", "Gross Margin"],
  "HCA": ["EPS", "Revenue"],
  "APP": ["EPS", "Revenue", "EBITDA"],
  "VEEV": ["EPS", "Revenue"],
  "CVNA": ["EPS", "Revenue", "EBITDA"],
  "APO": ["EPS", "Revenue"],
  "PGR": ["EPS", "Net Premiums", "Combined Ratio"],
  "FICO": ["EPS", "Revenue"],
  "GOOG": ["EPS", "Revenue", "Op. Margin", "Capex"],
  "MU": ["EPS", "Revenue", "Gross Margin"],
  "HOOD": ["EPS", "Revenue"],
  "TDG": ["EPS", "Revenue", "EBITDA"],
  "GE": ["EPS", "Revenue", "Op. Margin"],
  "LRCX": ["EPS", "Revenue", "Gross Margin"],
  "DASH": ["EPS", "Revenue", "EBITDA"],
  "UBER": ["EPS", "Revenue", "EBITDA"],
  "LLY": ["EPS", "Revenue"],
  "MSFT": ["EPS", "Revenue", "Op. Income", "Capex"],
  "V": ["EPS", "Revenue"]
}
```

- [ ] **Step 2: Commit**

```bash
git add earnings_metrics.json
git commit -m "feat: add earnings metrics configuration for per-ticker display"
```

---

### Task 2: Create `pull_earnings.py` — earnings date and metadata pull

**Files:**
- Create: `pull_earnings.py`

This task builds the script incrementally. The script reuses `_bdp_batch` and ticker lists from `pull_estimates.py`.

- [ ] **Step 1: Create `pull_earnings.py` with imports and ticker setup**

```python
"""Pull earnings calendar data, consensus estimates, guidance, and revisions from Bloomberg."""

import json
import os
from datetime import date, timedelta

from xbbg import blp

from bloomberg import USD_OVERRIDE_TICKERS

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(SCRIPT_DIR, "output", "snapshots")
METRICS_PATH = os.path.join(SCRIPT_DIR, "earnings_metrics.json")

PORTFOLIO = ["HCA", "UNH", "TSM", "AVGO", "NVDA", "META", "AMZN", "JPM", "APO", "PGR", "CVNA", "APP", "VEEV"]
WATCHLIST = ["FICO", "GOOG", "MU", "HOOD", "TDG", "GE", "LRCX", "DASH", "UBER", "LLY", "MSFT", "V"]


def _bbg_ticker(short):
    """Convert short ticker to Bloomberg format."""
    if short == "TSM":
        return "TSM US Equity"
    return f"{short} US Equity"


def _bdp_batch(bbg_tickers, fields, batch_size=50):
    """Pull bdp in batches. Returns {bbg_ticker: {field: value}}."""
    result = {}
    if isinstance(fields, str):
        fields = [fields]
    for i in range(0, len(bbg_tickers), batch_size):
        batch = bbg_tickers[i:i + batch_size]
        try:
            df = blp.bdp(batch, fields)
            for row in df.rows():
                ticker, field, value = row[0], row[1], row[2]
                if ticker not in result:
                    result[ticker] = {}
                try:
                    result[ticker][field] = float(value)
                except (ValueError, TypeError):
                    result[ticker][field] = value
        except Exception as e:
            print(f"  WARNING: bdp batch failed: {e}")
    return result


def load_metrics_config():
    """Load earnings_metrics.json. Returns the full config dict."""
    with open(METRICS_PATH) as f:
        return json.load(f)


def pull_earnings_dates(bbg_tickers):
    """Pull earnings dates, times, and confirmation status.

    Returns {bbg_ticker: {date, time, confirmed}}.
    """
    fields = ["EXPECTED_REPORT_DT", "EXPECTED_REPORT_TIME", "EARN_ANN_DT_STATUS"]
    data = _bdp_batch(bbg_tickers, fields)
    result = {}
    for bt in bbg_tickers:
        info = data.get(bt, {})
        raw_date = info.get("EXPECTED_REPORT_DT", "")
        # Bloomberg returns dates as "MM/DD/YYYY" or datetime-like strings
        earnings_date = ""
        if raw_date:
            raw_str = str(raw_date).strip()
            # Try ISO format first (YYYY-MM-DD), then MM/DD/YYYY
            if len(raw_str) >= 10 and raw_str[4] == "-":
                earnings_date = raw_str[:10]
            elif "/" in raw_str:
                parts = raw_str.split("/")
                if len(parts) == 3:
                    earnings_date = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
        status = str(info.get("EARN_ANN_DT_STATUS", "")).strip()
        result[bt] = {
            "date": earnings_date,
            "time": str(info.get("EXPECTED_REPORT_TIME", "")).strip(),
            "confirmed": status.lower() == "confirmed",
        }
    return result
```

- [ ] **Step 2: Add consensus estimate pull function**

Append to `pull_earnings.py`:

```python
def pull_consensus(bbg_tickers, metrics_config):
    """Pull consensus estimates for each ticker's configured metrics.

    Uses 1BF (next quarter) period override for quarterly estimates,
    and 1BF on the annual override for annual estimates.

    Returns {bbg_ticker: {metric_name: {"quarterly": value, "annual": value}}}.
    """
    field_map = metrics_config["_field_map"]
    result = {}

    for bt in bbg_tickers:
        short = bt.split(" ")[0]
        ticker_metrics = metrics_config.get(short, metrics_config["_default"])
        result[bt] = {}

        for metric_name in ticker_metrics:
            if metric_name not in field_map:
                result[bt][metric_name] = {"quarterly": None, "annual": None}
                continue

            bbg_field = field_map[metric_name]["field"]
            overrides_q = [("BEST_FPERIOD_OVERRIDE", "1BF")]
            overrides_a = [("BEST_FPERIOD_OVERRIDE", "1BA")]
            if short in USD_OVERRIDE_TICKERS:
                overrides_q.append(("EQY_FUND_CRNCY", "USD"))
                overrides_a.append(("EQY_FUND_CRNCY", "USD"))

            q_val = None
            a_val = None
            try:
                df = blp.bdp(bt, bbg_field, overrides=overrides_q)
                for row in df.rows():
                    try:
                        q_val = float(row[2])
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass

            try:
                df = blp.bdp(bt, bbg_field, overrides=overrides_a)
                for row in df.rows():
                    try:
                        a_val = float(row[2])
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass

            result[bt][metric_name] = {"quarterly": q_val, "annual": a_val}

    return result
```

- [ ] **Step 3: Add prior-year actuals pull function**

Append to `pull_earnings.py`:

```python
def pull_prior_year(bbg_tickers, metrics_config):
    """Pull prior-year actuals for y/y computation.

    Uses 0BF (last reported quarter) and 0BA (last reported annual).

    Returns {bbg_ticker: {metric_name: {"quarterly": value, "annual": value}}}.
    """
    field_map = metrics_config["_field_map"]
    result = {}

    for bt in bbg_tickers:
        short = bt.split(" ")[0]
        ticker_metrics = metrics_config.get(short, metrics_config["_default"])
        result[bt] = {}

        for metric_name in ticker_metrics:
            if metric_name not in field_map:
                result[bt][metric_name] = {"quarterly": None, "annual": None}
                continue

            bbg_field = field_map[metric_name]["field"]
            overrides_q = [("BEST_FPERIOD_OVERRIDE", "0BF")]
            overrides_a = [("BEST_FPERIOD_OVERRIDE", "0BA")]
            if short in USD_OVERRIDE_TICKERS:
                overrides_q.append(("EQY_FUND_CRNCY", "USD"))
                overrides_a.append(("EQY_FUND_CRNCY", "USD"))

            q_val = None
            a_val = None
            try:
                df = blp.bdp(bt, bbg_field, overrides=overrides_q)
                for row in df.rows():
                    try:
                        q_val = float(row[2])
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass

            try:
                df = blp.bdp(bt, bbg_field, overrides=overrides_a)
                for row in df.rows():
                    try:
                        a_val = float(row[2])
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass

            result[bt][metric_name] = {"quarterly": q_val, "annual": a_val}

    return result
```

- [ ] **Step 4: Add guidance pull function**

Append to `pull_earnings.py`:

```python
def pull_guidance(bbg_tickers, metrics_config):
    """Pull company guidance ranges.

    Returns {bbg_ticker: {metric_name: {"quarterly": {low, high}, "annual": {low, high}}}}.
    """
    guidance_fields = metrics_config.get("_guidance_fields", {})
    result = {}

    for bt in bbg_tickers:
        short = bt.split(" ")[0]
        ticker_metrics = metrics_config.get(short, metrics_config["_default"])
        result[bt] = {}

        for metric_name in ticker_metrics:
            if metric_name not in guidance_fields:
                result[bt][metric_name] = {"quarterly": None, "annual": None}
                continue

            gf = guidance_fields[metric_name]

            # Pull quarterly guidance (1BF)
            q_guidance = None
            try:
                fields = [gf["high"], gf["low"]]
                overrides = [("BEST_FPERIOD_OVERRIDE", "1BF")]
                if short in USD_OVERRIDE_TICKERS:
                    overrides.append(("EQY_FUND_CRNCY", "USD"))
                df = blp.bdp(bt, fields, overrides=overrides)
                vals = {}
                for row in df.rows():
                    try:
                        vals[row[1]] = float(row[2])
                    except (ValueError, TypeError):
                        pass
                if gf["high"] in vals and gf["low"] in vals:
                    q_guidance = {"low": vals[gf["low"]], "high": vals[gf["high"]]}
            except Exception:
                pass

            # Pull annual guidance (1BA)
            a_guidance = None
            try:
                fields = [gf["high"], gf["low"]]
                overrides = [("BEST_FPERIOD_OVERRIDE", "1BA")]
                if short in USD_OVERRIDE_TICKERS:
                    overrides.append(("EQY_FUND_CRNCY", "USD"))
                df = blp.bdp(bt, fields, overrides=overrides)
                vals = {}
                for row in df.rows():
                    try:
                        vals[row[1]] = float(row[2])
                    except (ValueError, TypeError):
                        pass
                if gf["high"] in vals and gf["low"] in vals:
                    a_guidance = {"low": vals[gf["low"]], "high": vals[gf["high"]]}
            except Exception:
                pass

            result[bt][metric_name] = {"quarterly": q_guidance, "annual": a_guidance}

    return result
```

- [ ] **Step 5: Add revisions pull function**

Append to `pull_earnings.py`:

```python
def pull_revisions(bbg_tickers):
    """Pull 4-week EPS revision counts.

    Returns {bbg_ticker: {up: int, down: int}}.
    """
    fields = ["BEST_EPS_NUMUP", "BEST_EPS_NUMDN"]
    # 4-week revision window: use BEST_ESTIMATE_REVISION_PERIOD override
    overrides = [("BEST_FPERIOD_OVERRIDE", "1BF")]
    result = {}
    for bt in bbg_tickers:
        short = bt.split(" ")[0]
        ovr = list(overrides)
        if short in USD_OVERRIDE_TICKERS:
            ovr.append(("EQY_FUND_CRNCY", "USD"))
        try:
            df = blp.bdp(bt, fields, overrides=ovr)
            vals = {}
            for row in df.rows():
                try:
                    vals[row[1]] = int(float(row[2]))
                except (ValueError, TypeError):
                    vals[row[1]] = 0
            result[bt] = {
                "up": vals.get("BEST_EPS_NUMUP", 0),
                "down": vals.get("BEST_EPS_NUMDN", 0),
            }
        except Exception:
            result[bt] = {"up": 0, "down": 0}
    return result
```

- [ ] **Step 6: Add the main function that assembles and outputs JSON**

Append to `pull_earnings.py`:

```python
def compute_yoy(current, prior, fmt):
    """Compute y/y change. Returns string like '+12.1%' or '+40bps' or None."""
    if current is None or prior is None:
        return None
    if fmt == "percent":
        # Margin-type: express change in basis points
        bps = (current - prior) * 100
        sign = "+" if bps >= 0 else ""
        return f"{sign}{bps:.0f}bps"
    else:
        if prior == 0:
            return None
        pct = (current - prior) / abs(prior) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"


def compute_vs_guide(consensus, guidance):
    """Determine where consensus sits vs guidance range. Returns string."""
    if consensus is None or guidance is None:
        return "n/a"
    low, high = guidance["low"], guidance["high"]
    if high == low:
        if consensus > high:
            return "above"
        elif consensus < low:
            return "below"
        return "at guide"
    # Position within range: 0 = at low, 1 = at high
    position = (consensus - low) / (high - low)
    if position > 0.85:
        return "above"
    elif position < 0.15:
        return "below"
    else:
        return "mid"


def main():
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    config = load_metrics_config()
    field_map = config["_field_map"]

    # Build ticker list
    all_tickers = []
    for t in PORTFOLIO:
        all_tickers.append({"short": t, "bbg": _bbg_ticker(t), "group": "Portfolio"})
    for t in WATCHLIST:
        all_tickers.append({"short": t, "bbg": _bbg_ticker(t), "group": "Watchlist"})

    bbg_tickers = [e["bbg"] for e in all_tickers]

    print(f"Pulling earnings data for {len(all_tickers)} tickers...")

    # Step 1: Earnings dates
    print("\n[1/5] Earnings dates...")
    dates_data = pull_earnings_dates(bbg_tickers)

    # Step 2: Consensus estimates
    print("\n[2/5] Consensus estimates...")
    consensus_data = pull_consensus(bbg_tickers, config)

    # Step 3: Prior-year actuals
    print("\n[3/5] Prior-year actuals...")
    prior_data = pull_prior_year(bbg_tickers, config)

    # Step 4: Guidance
    print("\n[4/5] Guidance ranges...")
    guidance_data = pull_guidance(bbg_tickers, config)

    # Step 5: Revisions
    print("\n[5/5] Revision counts...")
    revisions_data = pull_revisions(bbg_tickers)

    # Assemble JSON
    companies = []
    for entry in all_tickers:
        bt = entry["bbg"]
        short = entry["short"]
        ticker_metrics = config.get(short, config["_default"])

        earnings = dates_data.get(bt, {})
        consensus = consensus_data.get(bt, {})
        prior = prior_data.get(bt, {})
        guidance = guidance_data.get(bt, {})
        revisions = revisions_data.get(bt, {"up": 0, "down": 0})

        # Build quarterly metrics
        metrics = []
        for metric_name in ticker_metrics:
            fmt_info = field_map.get(metric_name, {})
            fmt = fmt_info.get("format", "number")
            cons_q = consensus.get(metric_name, {}).get("quarterly")
            prior_q = prior.get(metric_name, {}).get("quarterly")
            guide_q = guidance.get(metric_name, {}).get("quarterly")

            metrics.append({
                "name": metric_name,
                "consensus": cons_q,
                "guidance_low": guide_q["low"] if guide_q else None,
                "guidance_high": guide_q["high"] if guide_q else None,
                "prior_year": prior_q,
                "yoy": compute_yoy(cons_q, prior_q, fmt),
                "vs_guide": compute_vs_guide(cons_q, guide_q),
            })

        # Build annual metrics (only for metrics that have annual guidance or estimates)
        annual_metrics = []
        for metric_name in ticker_metrics:
            fmt_info = field_map.get(metric_name, {})
            fmt = fmt_info.get("format", "number")
            cons_a = consensus.get(metric_name, {}).get("annual")
            prior_a = prior.get(metric_name, {}).get("annual")
            guide_a = guidance.get(metric_name, {}).get("annual")

            # Only include if there's annual data
            if cons_a is not None or guide_a is not None:
                annual_metrics.append({
                    "name": metric_name,
                    "consensus": cons_a,
                    "guidance_low": guide_a["low"] if guide_a else None,
                    "guidance_high": guide_a["high"] if guide_a else None,
                    "prior_year": prior_a,
                    "yoy": compute_yoy(cons_a, prior_a, fmt),
                    "vs_guide": compute_vs_guide(cons_a, guide_a),
                })

        companies.append({
            "ticker": short,
            "group": entry["group"],
            "earnings_date": earnings.get("date", ""),
            "earnings_time": earnings.get("time", ""),
            "date_confirmed": earnings.get("confirmed", False),
            "revisions_4wk": revisions,
            "metrics": metrics,
            "annual_metrics": annual_metrics,
        })

    # Sort by earnings date (soonest first, blanks last)
    companies.sort(key=lambda c: c["earnings_date"] if c["earnings_date"] else "9999-12-31")

    output = {
        "snapshot_date": today_str,
        "companies": companies,
    }

    path = os.path.join(SNAPSHOT_DIR, f"earnings_{today_str}.json")
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {path}")

    # Update index
    files = sorted(
        [fn.replace("earnings_", "").replace(".json", "")
         for fn in os.listdir(SNAPSHOT_DIR)
         if fn.startswith("earnings_") and fn.endswith(".json")],
        reverse=True,
    )
    idx_path = os.path.join(SNAPSHOT_DIR, "index_earnings.json")
    with open(idx_path, "w") as f:
        json.dump(files, f, indent=2)
    print(f"Updated: {idx_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Test the script runs**

Run: `python pull_earnings.py`

Expected: The script connects to Bloomberg, pulls data for 25 tickers, and creates `output/snapshots/earnings_2026-04-06.json`. Check the JSON file has the expected structure with companies sorted by earnings date.

- [ ] **Step 8: Commit**

```bash
git add pull_earnings.py
git commit -m "feat: add pull_earnings.py for earnings calendar data from Bloomberg"
```

---

### Task 3: Build `earnings.html` — page shell and data loading

**Files:**
- Create: `earnings.html`

- [ ] **Step 1: Create `earnings.html` with page structure and styles**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Earnings Calendar</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #f8f9fa; color: #1a1a1a; font-size: 13px; padding: 20px 24px;
}

/* Header */
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header h1 { font-size: 20px; font-weight: 700; }
.header .updated { font-size: 11px; color: #888; margin-top: 2px; }
.controls { display: flex; align-items: center; gap: 12px; }
.controls label { font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.btn-group { display: flex; gap: 0; }
.btn-group button {
  padding: 4px 12px; font-size: 11px; border: 1px solid #ccc; background: #fff;
  cursor: pointer; color: #555;
}
.btn-group button:first-child { border-radius: 4px 0 0 4px; }
.btn-group button:last-child { border-radius: 0 4px 4px 0; }
.btn-group button + button { border-left: none; }
.btn-group button.active { background: #2563eb; color: #fff; border-color: #2563eb; }
.zoom-wrap { display: flex; align-items: center; gap: 6px; }
.zoom-wrap input[type=range] { width: 100px; }
.zoom-label { font-size: 10px; color: #888; min-width: 50px; }

/* Mini timeline */
.mini-timeline {
  display: flex; align-items: center; gap: 4px; margin-bottom: 20px;
  padding: 8px 16px; background: #fff; border-radius: 8px; border: 1px solid #e2e5e9;
}
.mini-timeline .month-label { font-size: 10px; color: #888; min-width: 30px; }
.mini-timeline .track {
  flex: 1; height: 4px; background: #e8e8e8; border-radius: 2px; position: relative; cursor: pointer;
}
.mini-timeline .tick {
  position: absolute; width: 6px; height: 10px; border-radius: 1px; top: -3px; cursor: pointer;
}
.mini-timeline .tick.confirmed { background: #2563eb; }
.mini-timeline .tick.tentative { background: transparent; border: 1.5px dashed #2563eb; }
.mini-timeline .tick:hover { transform: scale(1.5); }
.mini-timeline .tick .tip {
  display: none; position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
  background: #333; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: 9px; white-space: nowrap;
}
.mini-timeline .tick:hover .tip { display: block; }

/* Swim lanes */
.lanes { display: flex; gap: 16px; overflow-x: auto; padding-bottom: 16px; }
.lane { min-width: 340px; flex: 1; max-width: 420px; }
.lane-header {
  font-size: 12px; font-weight: 700; padding: 8px 12px; margin-bottom: 10px;
  border-bottom: 2px solid; border-radius: 4px 4px 0 0;
}
.lane-header.this-week { color: #d97706; border-color: #d97706; background: #fffbeb; }
.lane-header.next-week { color: #2563eb; border-color: #2563eb; background: #eff6ff; }
.lane-header.later { color: #6b7280; border-color: #d1d5db; background: #f9fafb; }
.lane-header .count { font-weight: 400; color: #999; font-size: 11px; margin-left: 4px; }

/* Cards */
.card {
  background: #fff; border-radius: 8px; padding: 14px; margin-bottom: 10px;
  border: 1px solid #e2e5e9; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.card:hover { border-color: #93c5fd; box-shadow: 0 2px 8px rgba(37,99,235,0.08); }
.card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ticker { font-weight: 700; font-size: 15px; color: #111; }
.date-badge { font-size: 10px; color: #666; background: #f1f3f5; padding: 2px 8px; border-radius: 4px; margin-left: 8px; }
.date-tentative { font-style: italic; }
.date-tentative::after { content: " (est)"; font-size: 9px; color: #999; }
.confirmed-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #2563eb; margin-right: 4px; vertical-align: middle; }
.tentative-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; border: 1.5px dashed #2563eb; margin-right: 4px; vertical-align: middle; }
.urgency {
  font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px;
}
.urgency.hot { background: #fef2f2; color: #dc2626; }
.urgency.soon { background: #fffbeb; color: #d97706; }
.urgency.normal { background: #f0fdf4; color: #16a34a; }
.revisions {
  font-size: 10px; font-weight: 600; padding: 4px 8px; border-radius: 4px;
  display: inline-block; margin-bottom: 8px;
}
.revisions.positive { background: #f0fdf4; color: #16a34a; }
.revisions.mixed { background: #fffbeb; color: #d97706; }
.revisions.negative { background: #fef2f2; color: #dc2626; }

/* Metrics table */
.metrics-table { width: 100%; font-size: 11px; border-collapse: collapse; }
.metrics-table th {
  text-align: left; color: #999; font-weight: 600; font-size: 10px;
  text-transform: uppercase; letter-spacing: 0.3px; padding: 4px 0; border-bottom: 1px solid #f0f0f0;
}
.metrics-table th:not(:first-child) { text-align: right; }
.metrics-table td { padding: 5px 0; border-bottom: 1px solid #f8f8f8; }
.metrics-table td:not(:first-child) { text-align: right; }
.metric-name { color: #444; font-weight: 500; }
.guidance { color: #999; font-size: 10px; }
.consensus { color: #111; font-weight: 600; }
.yoy { font-size: 10px; font-weight: 600; }
.yoy.up { color: #16a34a; }
.yoy.down { color: #dc2626; }
.vs-guide { font-size: 10px; font-weight: 600; }
.vs-guide.above { color: #16a34a; }
.vs-guide.mid { color: #d97706; }
.vs-guide.below { color: #dc2626; }
.vs-guide.na { color: #999; }
.section-label {
  font-size: 9px; color: #aaa; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.5px; padding: 6px 0 2px;
}

/* Collapsed card */
.card.collapsed .card-body { display: none; }
.card.collapsed { cursor: pointer; }
.card-summary {
  display: none; align-items: center; justify-content: space-between;
  font-size: 11px; color: #666;
}
.card.collapsed .card-summary { display: flex; }
.card-summary .expand-icon { color: #999; }

/* Empty state */
.empty { text-align: center; padding: 60px 20px; color: #999; font-size: 14px; }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Earnings Calendar</h1>
    <div class="updated" id="updated"></div>
  </div>
  <div class="controls">
    <label>Show:</label>
    <div class="btn-group" id="filter-group">
      <button class="active" data-filter="all">All</button>
      <button data-filter="Portfolio">Portfolio</button>
      <button data-filter="Watchlist">Watchlist</button>
    </div>
    <div class="zoom-wrap">
      <label>Zoom:</label>
      <input type="range" id="zoom" min="7" max="90" value="30">
      <span class="zoom-label" id="zoom-label">30 days</span>
    </div>
  </div>
</div>

<div class="mini-timeline" id="mini-timeline">
  <!-- populated by JS -->
</div>

<div class="lanes" id="lanes">
  <!-- populated by JS -->
</div>

<div class="empty" id="empty" style="display:none">
  No earnings data found. Run <code>python pull_earnings.py</code> to generate a snapshot.
</div>

<script>
// DATA LOADING
let DATA = null;
let FILTER = localStorage.getItem('earnings_filter') || 'all';
let ZOOM_DAYS = parseInt(localStorage.getItem('earnings_zoom') || '30');

async function loadData() {
  try {
    const idxResp = await fetch('output/snapshots/index_earnings.json');
    if (!idxResp.ok) { showEmpty(); return; }
    const dates = await idxResp.json();
    if (!dates.length) { showEmpty(); return; }

    const dataResp = await fetch(`output/snapshots/earnings_${dates[0]}.json`);
    if (!dataResp.ok) { showEmpty(); return; }
    DATA = await dataResp.json();

    document.getElementById('updated').textContent = `Last updated: ${DATA.snapshot_date}`;
    render();
  } catch (e) {
    console.error(e);
    showEmpty();
  }
}

function showEmpty() {
  document.getElementById('empty').style.display = 'block';
  document.getElementById('lanes').style.display = 'none';
  document.getElementById('mini-timeline').style.display = 'none';
}

// FILTERING
function filteredCompanies() {
  if (!DATA) return [];
  if (FILTER === 'all') return DATA.companies;
  return DATA.companies.filter(c => c.group === FILTER);
}

// RENDERING — see Task 4 for full implementation
function render() {
  const companies = filteredCompanies();
  if (!companies.length) { showEmpty(); return; }
  document.getElementById('empty').style.display = 'none';
  document.getElementById('lanes').style.display = 'flex';
  document.getElementById('mini-timeline').style.display = 'flex';
  renderTimeline(companies);
  renderLanes(companies);
}

function renderTimeline(companies) {
  // Placeholder — implemented in Task 4
}

function renderLanes(companies) {
  // Placeholder — implemented in Task 4
}

// EVENT LISTENERS
document.getElementById('filter-group').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  document.querySelectorAll('#filter-group button').forEach(b => b.classList.remove('active'));
  e.target.classList.add('active');
  FILTER = e.target.dataset.filter;
  localStorage.setItem('earnings_filter', FILTER);
  render();
});

document.getElementById('zoom').addEventListener('input', e => {
  ZOOM_DAYS = parseInt(e.target.value);
  document.getElementById('zoom-label').textContent = ZOOM_DAYS + ' days';
  localStorage.setItem('earnings_zoom', ZOOM_DAYS);
  render();
});

// INIT
document.getElementById('zoom').value = ZOOM_DAYS;
document.getElementById('zoom-label').textContent = ZOOM_DAYS + ' days';
document.querySelectorAll('#filter-group button').forEach(b => {
  b.classList.toggle('active', b.dataset.filter === FILTER);
});
loadData();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify the page loads**

Run: `python -m http.server 8000` from the BBG directory. Open `http://localhost:8000/earnings.html`. If no JSON snapshot exists yet, the empty state should display. If `earnings_*.json` exists, it should load without errors (though lanes won't render yet).

- [ ] **Step 3: Commit**

```bash
git add earnings.html
git commit -m "feat: earnings.html page shell with styles, data loading, and controls"
```

---

### Task 4: Build `earnings.html` — swim lane rendering and card markup

**Files:**
- Modify: `earnings.html` (replace the placeholder `renderTimeline` and `renderLanes` functions)

- [ ] **Step 1: Implement `renderTimeline`**

Replace the `renderTimeline` placeholder function in the `<script>` section of `earnings.html`:

```javascript
function renderTimeline(companies) {
  const container = document.getElementById('mini-timeline');
  container.innerHTML = '';

  const today = new Date(DATA.snapshot_date + 'T00:00:00');
  // Timeline spans from today to today + 90 days (full quarter)
  const end = new Date(today); end.setDate(end.getDate() + 90);

  // Month labels
  const months = [];
  let cursor = new Date(today.getFullYear(), today.getMonth(), 1);
  while (cursor <= end) {
    months.push(new Date(cursor));
    cursor.setMonth(cursor.getMonth() + 1);
  }

  // Build the track
  const totalDays = (end - today) / 86400000;

  let html = `<span class="month-label">${months[0].toLocaleDateString('en', {month:'short'})}</span>`;
  html += `<div class="track" id="timeline-track">`;

  for (const c of companies) {
    if (!c.earnings_date) continue;
    const d = new Date(c.earnings_date + 'T00:00:00');
    const offset = (d - today) / 86400000;
    if (offset < 0 || offset > totalDays) continue;
    const pct = (offset / totalDays * 100).toFixed(1);
    const cls = c.date_confirmed ? 'confirmed' : 'tentative';
    html += `<div class="tick ${cls}" style="left:${pct}%" data-ticker="${c.ticker}">`;
    html += `<span class="tip">${c.ticker} ${c.earnings_date}</span>`;
    html += `</div>`;
  }

  html += `</div>`;
  html += `<span class="month-label">${months[months.length - 1].toLocaleDateString('en', {month:'short'})}</span>`;

  container.innerHTML = html;
}
```

- [ ] **Step 2: Implement helper functions for card rendering**

Add these functions before `renderLanes` in the `<script>`:

```javascript
function daysUntil(dateStr, snapshotDate) {
  const d = new Date(dateStr + 'T00:00:00');
  const today = new Date(snapshotDate + 'T00:00:00');
  return Math.ceil((d - today) / 86400000);
}

function urgencyClass(days) {
  if (days < 5) return 'hot';
  if (days < 14) return 'soon';
  return 'normal';
}

function revisionsClass(rev) {
  const net = rev.up - rev.down;
  if (net > 0 && rev.down === 0) return 'positive';
  if (net < 0 && rev.up === 0) return 'negative';
  return 'mixed';
}

function formatGuidance(low, high) {
  if (low == null && high == null) return '&mdash;';
  if (low === high) return formatNum(low);
  return `${formatNum(low)} &ndash; ${formatNum(high)}`;
}

function formatNum(v) {
  if (v == null) return '&mdash;';
  // Abbreviate billions
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}B`;
  if (Math.abs(v) >= 1) return v.toFixed(2);
  return v.toString();
}

function vsGuideClass(vs) {
  if (vs === 'above') return 'above';
  if (vs === 'mid' || vs === 'at guide') return 'mid';
  if (vs === 'below') return 'below';
  return 'na';
}

function yoyClass(yoy) {
  if (!yoy) return '';
  return yoy.startsWith('-') ? 'down' : 'up';
}
```

- [ ] **Step 3: Implement `renderLanes`**

Replace the `renderLanes` placeholder:

```javascript
function renderLanes(companies) {
  const container = document.getElementById('lanes');
  container.innerHTML = '';

  const today = new Date(DATA.snapshot_date + 'T00:00:00');
  const cutoff = new Date(today);
  cutoff.setDate(cutoff.getDate() + ZOOM_DAYS);

  // Filter to companies within the zoom window
  const visible = companies.filter(c => {
    if (!c.earnings_date) return false;
    const d = new Date(c.earnings_date + 'T00:00:00');
    return d >= today && d <= cutoff;
  });

  if (!visible.length) {
    container.innerHTML = '<div class="empty">No earnings in this window. Try zooming out.</div>';
    return;
  }

  // Group by ISO week (Mon–Sun)
  const weeks = {};
  for (const c of visible) {
    const d = new Date(c.earnings_date + 'T00:00:00');
    // Get Monday of this week
    const day = d.getDay();
    const mon = new Date(d);
    mon.setDate(d.getDate() - ((day + 6) % 7));
    const key = mon.toISOString().slice(0, 10);
    if (!weeks[key]) weeks[key] = { monday: new Date(mon), companies: [] };
    weeks[key].companies.push(c);
  }

  const sortedWeeks = Object.keys(weeks).sort();
  const todayMon = new Date(today);
  todayMon.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  const todayMonKey = todayMon.toISOString().slice(0, 10);

  for (const key of sortedWeeks) {
    const week = weeks[key];
    const fri = new Date(week.monday);
    fri.setDate(fri.getDate() + 4);
    const monLabel = week.monday.toLocaleDateString('en', { month: 'short', day: 'numeric' });
    const friLabel = fri.toLocaleDateString('en', { month: 'short', day: 'numeric' });

    let headerClass = 'later';
    if (key === todayMonKey) headerClass = 'this-week';
    else if (key <= new Date(todayMon.getTime() + 7 * 86400000).toISOString().slice(0, 10)) headerClass = 'next-week';

    const lane = document.createElement('div');
    lane.className = 'lane';

    const isThisWeek = key === todayMonKey;
    const headerLabel = isThisWeek ? `This Week &middot; ${monLabel} – ${friLabel}` : `${monLabel} – ${friLabel}`;

    lane.innerHTML = `<div class="lane-header ${headerClass}">${headerLabel}<span class="count">(${week.companies.length})</span></div>`;

    const autoCollapse = week.companies.length > 3;

    for (const c of week.companies) {
      lane.innerHTML += buildCard(c, autoCollapse);
    }

    container.appendChild(lane);
  }

  // Attach expand/collapse handlers
  container.querySelectorAll('.card.collapsed').forEach(card => {
    card.addEventListener('click', () => {
      card.classList.remove('collapsed');
    });
  });
  container.querySelectorAll('.card:not(.collapsed) .card-head').forEach(head => {
    head.style.cursor = 'pointer';
    head.addEventListener('click', () => {
      head.closest('.card').classList.toggle('collapsed');
    });
  });
}

function buildCard(c, collapsed) {
  const days = daysUntil(c.earnings_date, DATA.snapshot_date);
  const urg = urgencyClass(days);
  const rev = c.revisions_4wk;
  const revCls = revisionsClass(rev);
  const dotCls = c.date_confirmed ? 'confirmed-dot' : 'tentative-dot';
  const dateCls = c.date_confirmed ? '' : 'date-tentative';

  const dateObj = new Date(c.earnings_date + 'T00:00:00');
  const dateLabel = dateObj.toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric' });
  const timeLabel = c.earnings_time || '';

  let html = `<div class="card${collapsed ? ' collapsed' : ''}">`;

  // Header
  html += `<div class="card-head">`;
  html += `<div><span class="${dotCls}"></span><span class="ticker">${c.ticker}</span>`;
  html += `<span class="date-badge ${dateCls}">${dateLabel}${timeLabel ? ' &middot; ' + timeLabel : ''}</span></div>`;
  html += `<span class="urgency ${urg}">${days} DAY${days !== 1 ? 'S' : ''}</span>`;
  html += `</div>`;

  // Collapsed summary
  const epsMetric = c.metrics.find(m => m.name === 'EPS');
  const epsStr = epsMetric && epsMetric.consensus != null ? `EPS: ${epsMetric.consensus.toFixed(2)}` : '';
  html += `<div class="card-summary">`;
  html += `<span>${epsStr}</span>`;
  html += `<span class="revisions ${revCls}" style="margin:0">&#9650;${rev.up}/&#9660;${rev.down}</span>`;
  html += `<span class="expand-icon">&#9656;</span>`;
  html += `</div>`;

  // Card body (hidden when collapsed)
  html += `<div class="card-body">`;

  // Revisions
  html += `<div class="revisions ${revCls}">&#9650; ${rev.up} up / &#9660; ${rev.down} down (4wk)</div>`;

  // Quarterly metrics table
  html += `<table class="metrics-table">`;
  html += `<tr><th>Metric</th><th>Guidance</th><th>Cons.</th><th>Y/Y</th><th>vs Guide</th></tr>`;

  for (const m of c.metrics) {
    html += `<tr>`;
    html += `<td class="metric-name">${m.name}</td>`;
    html += `<td class="guidance">${formatGuidance(m.guidance_low, m.guidance_high)}</td>`;
    html += `<td class="consensus">${m.consensus != null ? formatNum(m.consensus) : '&mdash;'}</td>`;
    html += `<td class="yoy ${yoyClass(m.yoy)}">${m.yoy || '&mdash;'}</td>`;
    html += `<td class="vs-guide ${vsGuideClass(m.vs_guide)}">${m.vs_guide}</td>`;
    html += `</tr>`;
  }

  // Annual metrics
  if (c.annual_metrics && c.annual_metrics.length) {
    html += `<tr><td colspan="5" class="section-label">Full Year</td></tr>`;
    for (const m of c.annual_metrics) {
      html += `<tr>`;
      html += `<td class="metric-name">${m.name} (FY)</td>`;
      html += `<td class="guidance">${formatGuidance(m.guidance_low, m.guidance_high)}</td>`;
      html += `<td class="consensus">${m.consensus != null ? formatNum(m.consensus) : '&mdash;'}</td>`;
      html += `<td class="yoy ${yoyClass(m.yoy)}">${m.yoy || '&mdash;'}</td>`;
      html += `<td class="vs-guide ${vsGuideClass(m.vs_guide)}">${m.vs_guide}</td>`;
      html += `</tr>`;
    }
  }

  html += `</table>`;
  html += `</div>`; // card-body
  html += `</div>`; // card

  return html;
}
```

- [ ] **Step 4: Test with sample data**

Create a sample JSON file for testing without Bloomberg:

```bash
# Create a sample earnings JSON for visual testing
python -c "
import json, os
sample = {
  'snapshot_date': '2026-04-06',
  'companies': [
    {
      'ticker': 'JPM', 'group': 'Portfolio',
      'earnings_date': '2026-04-11', 'earnings_time': 'BMO', 'date_confirmed': True,
      'revisions_4wk': {'up': 5, 'down': 0},
      'metrics': [
        {'name': 'EPS', 'consensus': 4.62, 'guidance_low': 4.50, 'guidance_high': 4.80, 'prior_year': 4.12, 'yoy': '+12.1%', 'vs_guide': 'mid'},
        {'name': 'Revenue', 'consensus': 42800, 'guidance_low': 42000, 'guidance_high': 43500, 'prior_year': 39600, 'yoy': '+8.1%', 'vs_guide': 'mid'},
        {'name': 'NII', 'consensus': 23100, 'guidance_low': 23000, 'guidance_high': 23000, 'prior_year': 22400, 'yoy': '+3.1%', 'vs_guide': 'above'},
        {'name': 'Provisions', 'consensus': 2850, 'guidance_low': 2600, 'guidance_high': 3000, 'prior_year': 2410, 'yoy': '+18.3%', 'vs_guide': 'mid'}
      ],
      'annual_metrics': [
        {'name': 'EPS', 'consensus': 18.75, 'guidance_low': 18.00, 'guidance_high': 19.50, 'prior_year': 17.20, 'yoy': '+9.0%', 'vs_guide': 'mid'},
        {'name': 'NII', 'consensus': 91200, 'guidance_low': 90000, 'guidance_high': 90000, 'prior_year': 87700, 'yoy': '+4.0%', 'vs_guide': 'above'}
      ]
    },
    {
      'ticker': 'UNH', 'group': 'Portfolio',
      'earnings_date': '2026-04-10', 'earnings_time': 'BMO', 'date_confirmed': True,
      'revisions_4wk': {'up': 1, 'down': 2},
      'metrics': [
        {'name': 'EPS', 'consensus': 7.29, 'guidance_low': 7.05, 'guidance_high': 7.45, 'prior_year': 6.88, 'yoy': '+6.0%', 'vs_guide': 'mid'},
        {'name': 'Revenue', 'consensus': 109200, 'guidance_low': 108000, 'guidance_high': 110000, 'prior_year': 99300, 'yoy': '+10.0%', 'vs_guide': 'mid'}
      ],
      'annual_metrics': [
        {'name': 'EPS', 'consensus': 29.72, 'guidance_low': 29.50, 'guidance_high': 30.00, 'prior_year': 27.80, 'yoy': '+6.9%', 'vs_guide': 'mid'}
      ]
    },
    {
      'ticker': 'PGR', 'group': 'Portfolio',
      'earnings_date': '2026-04-16', 'earnings_time': 'AMC', 'date_confirmed': False,
      'revisions_4wk': {'up': 4, 'down': 0},
      'metrics': [
        {'name': 'EPS', 'consensus': 4.15, 'guidance_low': None, 'guidance_high': None, 'prior_year': 3.40, 'yoy': '+22.1%', 'vs_guide': 'n/a'},
        {'name': 'Net Premiums', 'consensus': 19800, 'guidance_low': None, 'guidance_high': None, 'prior_year': 16780, 'yoy': '+18.0%', 'vs_guide': 'n/a'},
        {'name': 'Combined Ratio', 'consensus': 87.5, 'guidance_low': None, 'guidance_high': None, 'prior_year': 89.3, 'yoy': '-180bps', 'vs_guide': 'n/a'}
      ],
      'annual_metrics': []
    },
    {
      'ticker': 'TSM', 'group': 'Portfolio',
      'earnings_date': '2026-04-17', 'earnings_time': 'BMO', 'date_confirmed': True,
      'revisions_4wk': {'up': 7, 'down': 0},
      'metrics': [
        {'name': 'EPS', 'consensus': 2.05, 'guidance_low': None, 'guidance_high': None, 'prior_year': 1.49, 'yoy': '+37.6%', 'vs_guide': 'n/a'},
        {'name': 'Revenue', 'consensus': 25400, 'guidance_low': 25000, 'guidance_high': 25800, 'prior_year': 18870, 'yoy': '+34.6%', 'vs_guide': 'mid'},
        {'name': 'Gross Margin', 'consensus': 58.1, 'guidance_low': 57.0, 'guidance_high': 59.0, 'prior_year': 55.5, 'yoy': '+260bps', 'vs_guide': 'mid'},
        {'name': 'Op. Margin', 'consensus': 47.3, 'guidance_low': 46.5, 'guidance_high': 48.5, 'prior_year': 45.1, 'yoy': '+220bps', 'vs_guide': 'mid'},
        {'name': 'Capex', 'consensus': 9800, 'guidance_low': None, 'guidance_high': None, 'prior_year': 7000, 'yoy': '+40.0%', 'vs_guide': 'n/a'}
      ],
      'annual_metrics': [
        {'name': 'Capex', 'consensus': 40200, 'guidance_low': 38000, 'guidance_high': 42000, 'prior_year': 29800, 'yoy': '+34.9%', 'vs_guide': 'mid'}
      ]
    },
    {
      'ticker': 'META', 'group': 'Portfolio',
      'earnings_date': '2026-04-23', 'earnings_time': 'AMC', 'date_confirmed': False,
      'revisions_4wk': {'up': 6, 'down': 1},
      'metrics': [
        {'name': 'EPS', 'consensus': 5.28, 'guidance_low': None, 'guidance_high': None, 'prior_year': 4.59, 'yoy': '+15.0%', 'vs_guide': 'n/a'},
        {'name': 'Revenue', 'consensus': 41200, 'guidance_low': 39500, 'guidance_high': 41800, 'prior_year': 36155, 'yoy': '+14.0%', 'vs_guide': 'above'},
        {'name': 'Op. Margin', 'consensus': 38.5, 'guidance_low': None, 'guidance_high': None, 'prior_year': 39.7, 'yoy': '-120bps', 'vs_guide': 'n/a'},
        {'name': 'Capex', 'consensus': 14500, 'guidance_low': None, 'guidance_high': None, 'prior_year': 9800, 'yoy': '+48.0%', 'vs_guide': 'n/a'}
      ],
      'annual_metrics': [
        {'name': 'Capex', 'consensus': 62100, 'guidance_low': 60000, 'guidance_high': 65000, 'prior_year': 45000, 'yoy': '+38.0%', 'vs_guide': 'mid'}
      ]
    },
    {
      'ticker': 'AMZN', 'group': 'Portfolio',
      'earnings_date': '2026-04-24', 'earnings_time': 'AMC', 'date_confirmed': False,
      'revisions_4wk': {'up': 8, 'down': 1},
      'metrics': [
        {'name': 'EPS', 'consensus': 1.38, 'guidance_low': None, 'guidance_high': None, 'prior_year': 1.14, 'yoy': '+21.1%', 'vs_guide': 'n/a'},
        {'name': 'Revenue', 'consensus': 154600, 'guidance_low': 151000, 'guidance_high': 155500, 'prior_year': 140500, 'yoy': '+10.0%', 'vs_guide': 'above'},
        {'name': 'Op. Income', 'consensus': 16200, 'guidance_low': 13000, 'guidance_high': 17500, 'prior_year': 12650, 'yoy': '+28.1%', 'vs_guide': 'above'},
        {'name': 'Capex', 'consensus': 24500, 'guidance_low': None, 'guidance_high': None, 'prior_year': 18600, 'yoy': '+31.7%', 'vs_guide': 'n/a'}
      ],
      'annual_metrics': [
        {'name': 'Capex', 'consensus': 96000, 'guidance_low': 100000, 'guidance_high': 100000, 'prior_year': 72000, 'yoy': '+33.3%', 'vs_guide': 'below'}
      ]
    },
    {
      'ticker': 'MSFT', 'group': 'Watchlist',
      'earnings_date': '2026-04-29', 'earnings_time': 'AMC', 'date_confirmed': True,
      'revisions_4wk': {'up': 5, 'down': 2},
      'metrics': [
        {'name': 'EPS', 'consensus': 3.22, 'guidance_low': None, 'guidance_high': None, 'prior_year': 2.94, 'yoy': '+9.5%', 'vs_guide': 'n/a'},
        {'name': 'Revenue', 'consensus': 68500, 'guidance_low': 67700, 'guidance_high': 68700, 'prior_year': 61900, 'yoy': '+10.7%', 'vs_guide': 'above'},
        {'name': 'Op. Income', 'consensus': 30200, 'guidance_low': None, 'guidance_high': None, 'prior_year': 27600, 'yoy': '+9.4%', 'vs_guide': 'n/a'},
        {'name': 'Capex', 'consensus': 21000, 'guidance_low': None, 'guidance_high': None, 'prior_year': 14000, 'yoy': '+50.0%', 'vs_guide': 'n/a'}
      ],
      'annual_metrics': []
    }
  ]
}
os.makedirs('output/snapshots', exist_ok=True)
with open('output/snapshots/earnings_2026-04-06.json', 'w') as f:
    json.dump(sample, f, indent=2)
with open('output/snapshots/index_earnings.json', 'w') as f:
    json.dump(['2026-04-06'], f)
print('Sample data written.')
"
```

Open `http://localhost:8000/earnings.html` and verify:
- Header shows "Last updated: 2026-04-06"
- Filter buttons work (All / Portfolio / Watchlist)
- Swim lanes appear grouped by week: "This Week" (JPM, UNH), "Apr 14–18" (PGR, TSM), "Apr 21–25" (META, AMZN), etc.
- Cards show ticker, date, urgency badge, revision badge, metrics table with guidance, consensus, y/y, vs guide
- PGR shows dashed tentative dot and "(est)" on the date
- JPM/UNH show solid confirmed dots
- Zoom slider changes visible weeks
- Mini timeline shows tick marks

- [ ] **Step 5: Commit**

```bash
git add earnings.html
git commit -m "feat: earnings.html swim lane rendering with cards, timeline, and interactivity"
```

---

### Task 5: Visual polish and edge cases

**Files:**
- Modify: `earnings.html`

- [ ] **Step 1: Fix `formatNum` to handle different scales properly**

The current `formatNum` function needs to handle the revenue values (stored in millions from Bloomberg) correctly. Replace it in `earnings.html`:

```javascript
function formatNum(v) {
  if (v == null) return '&mdash;';
  const abs = Math.abs(v);
  if (abs >= 1000) return `$${(v / 1000).toFixed(1)}B`;
  if (abs >= 1) {
    // Determine decimals: margins show 1 decimal, EPS shows 2
    if (abs < 100) return v.toFixed(2);
    return `$${v.toFixed(0)}M`;
  }
  return v.toFixed(2);
}
```

- [ ] **Step 2: Add no-earnings-date handling**

Some tickers may not have an earnings date set yet. In `renderLanes`, after the zoom filter, add a section at the bottom for tickers with no date. Add this after the lane-rendering loop:

```javascript
// Add "No Date" section for companies without earnings dates
const noDate = companies.filter(c => !c.earnings_date);
if (noDate.length) {
  const lane = document.createElement('div');
  lane.className = 'lane';
  lane.innerHTML = `<div class="lane-header later">No Date Set<span class="count">(${noDate.length})</span></div>`;
  for (const c of noDate) {
    lane.innerHTML += buildCardNoDate(c);
  }
  container.appendChild(lane);
}
```

Add the `buildCardNoDate` function:

```javascript
function buildCardNoDate(c) {
  const rev = c.revisions_4wk;
  const revCls = revisionsClass(rev);
  let html = `<div class="card">`;
  html += `<div class="card-head">`;
  html += `<div><span class="ticker">${c.ticker}</span>`;
  html += `<span class="date-badge" style="color:#999">TBD</span></div>`;
  html += `</div>`;
  html += `<div class="card-body">`;
  html += `<div class="revisions ${revCls}">&#9650; ${rev.up} up / &#9660; ${rev.down} down (4wk)</div>`;
  html += `<table class="metrics-table">`;
  html += `<tr><th>Metric</th><th>Guidance</th><th>Cons.</th><th>Y/Y</th><th>vs Guide</th></tr>`;
  for (const m of c.metrics) {
    html += `<tr>`;
    html += `<td class="metric-name">${m.name}</td>`;
    html += `<td class="guidance">${formatGuidance(m.guidance_low, m.guidance_high)}</td>`;
    html += `<td class="consensus">${m.consensus != null ? formatNum(m.consensus) : '&mdash;'}</td>`;
    html += `<td class="yoy ${yoyClass(m.yoy)}">${m.yoy || '&mdash;'}</td>`;
    html += `<td class="vs-guide ${vsGuideClass(m.vs_guide)}">${m.vs_guide}</td>`;
    html += `</tr>`;
  }
  html += `</table></div></div>`;
  return html;
}
```

- [ ] **Step 3: Test edge cases**

In the browser:
- Set zoom to 7 days — only "This Week" lane should appear
- Set zoom to 90 days — all weeks should show
- Toggle Portfolio filter — META, AMZN, JPM, etc. should show; MSFT should hide
- Toggle Watchlist filter — only MSFT should show
- Verify tentative dates (PGR, META, AMZN) show dashed dot and "(est)"
- Verify confirmed dates (JPM, UNH, TSM, MSFT) show solid dot

- [ ] **Step 4: Commit**

```bash
git add earnings.html
git commit -m "fix: earnings dashboard number formatting, no-date handling, edge cases"
```

---

### Task 6: Clean up sample data and final verification

**Files:**
- Modify: cleanup only

- [ ] **Step 1: Remove the sample data file**

The sample data was only for visual testing. Remove it so the real `pull_earnings.py` output is used:

```bash
rm output/snapshots/earnings_2026-04-06.json
rm output/snapshots/index_earnings.json
```

(These will be regenerated by running `pull_earnings.py` against Bloomberg.)

- [ ] **Step 2: Run `pull_earnings.py` against Bloomberg**

```bash
python pull_earnings.py
```

Expected: Script runs through 5 steps, pulls data for 25 tickers, saves JSON to `output/snapshots/earnings_YYYY-MM-DD.json`.

- [ ] **Step 3: Verify the live dashboard**

Open `http://localhost:8000/earnings.html` with the real Bloomberg data. Verify:
- Earnings dates are populated and reasonable
- Consensus values appear for standard metrics (EPS, Revenue)
- Guidance ranges appear where Bloomberg has coverage (may be spotty)
- Y/Y percentages are computed correctly
- Revision counts look reasonable

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: earnings calendar dashboard — complete with pull script, config, and UI"
```
