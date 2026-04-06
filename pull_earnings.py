"""Pull earnings calendar data, consensus estimates, guidance, and revisions from Bloomberg."""

import json
import os
from datetime import date, timedelta

from xbbg import blp

from bloomberg import USD_OVERRIDE_TICKERS

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(SCRIPT_DIR, "output", "snapshots")
METRICS_PATH = os.path.join(SCRIPT_DIR, "earnings_metrics.json")
GUIDANCE_PATH = os.path.join(SCRIPT_DIR, "guidance_overrides.json")
ACTUALS_PATH = os.path.join(SCRIPT_DIR, "actuals_overrides.json")

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


def pull_consensus(bbg_tickers, metrics_config):
    """Pull consensus estimates for each ticker's configured metrics.

    Uses 1BQ (next quarter) period override for quarterly estimates,
    and 1BF for annual estimates.

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
            overrides_q = [("BEST_FPERIOD_OVERRIDE", "1FQ")]
            overrides_a = [("BEST_FPERIOD_OVERRIDE", "1BF")]
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


def pull_prior_year(bbg_tickers, metrics_config):
    """Pull prior-year actuals for y/y computation.

    Uses -3BQ (same quarter last year) and 0BF (last reported annual).

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
            overrides_q = [("BEST_FPERIOD_OVERRIDE", "-3FQ")]
            overrides_a = [("BEST_FPERIOD_OVERRIDE", "0BF")]
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

            # Pull quarterly guidance (1BQ)
            q_guidance = None
            try:
                fields = [gf["high"], gf["low"]]
                overrides = [("BEST_FPERIOD_OVERRIDE", "1FQ")]
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

            # Pull annual guidance (1BF)
            a_guidance = None
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
                    a_guidance = {"low": vals[gf["low"]], "high": vals[gf["high"]]}
            except Exception:
                pass

            result[bt][metric_name] = {"quarterly": q_guidance, "annual": a_guidance}

    return result


def pull_revisions(bbg_tickers):
    """Pull 4-week EPS revision counts using BEST_EEPS_CUR_YR fields.

    Returns {bbg_ticker: {up: int, down: int}}.
    """
    fields = ["BEST_EEPS_CUR_YR_4WUP", "BEST_EEPS_CUR_YR_4WDN"]
    result = {}
    for i in range(0, len(bbg_tickers), 50):
        batch = bbg_tickers[i:i + 50]
        try:
            df = blp.bdp(batch, fields)
            for row in df.rows():
                ticker, field, value = row[0], row[1], row[2]
                if ticker not in result:
                    result[ticker] = {"up": 0, "down": 0}
                try:
                    val = int(float(value))
                except (ValueError, TypeError):
                    val = 0
                if field == "BEST_EEPS_CUR_YR_4WUP":
                    result[ticker]["up"] = val
                elif field == "BEST_EEPS_CUR_YR_4WDN":
                    result[ticker]["down"] = val
        except Exception as e:
            print(f"  WARNING: revisions batch failed: {e}")
    # Fill missing tickers
    for bt in bbg_tickers:
        if bt not in result:
            result[bt] = {"up": 0, "down": 0}
    return result


def pull_eps_4wk_change(bbg_tickers):
    """Pull 4-week EPS estimate % change using BDH.

    Compares current FY EPS estimate to the estimate 4 weeks ago.
    Returns {bbg_ticker: float_pct_change or None}.
    """
    today = date.today()
    four_weeks_ago = today - timedelta(days=28)
    result = {}
    for bt in bbg_tickers:
        short = bt.split(" ")[0]
        overrides = [("BEST_FPERIOD_OVERRIDE", "1BF")]
        if short in USD_OVERRIDE_TICKERS:
            overrides.append(("EQY_FUND_CRNCY", "USD"))
        try:
            df = blp.bdh(bt, "BEST_EPS", four_weeks_ago.strftime("%Y-%m-%d"),
                         today.strftime("%Y-%m-%d"),
                         periodicitySelection="WEEKLY", overrides=overrides)
            tbl = df.to_native()
            vals = [float(v) for v in tbl.column("value").to_pylist()]
            if len(vals) >= 2 and vals[0] != 0:
                pct = (vals[-1] - vals[0]) / abs(vals[0]) * 100
                result[bt] = round(pct, 2)
            else:
                result[bt] = None
        except Exception:
            result[bt] = None
    return result


def pull_earnings_history(bbg_tickers, actuals_data):
    """Pull last 4 quarters' EPS/Rev beats and stock reactions.

    Uses:
    1. Earnings dates from BDS ERN_ANN_DT_AND_PER
    2. Pre-earnings consensus from BDH with ABSOLUTE period override (e.g. '25Q4')
    3. Actuals from actuals_overrides.json (parsed from Call-extraction project)
    4. Stock price reaction from BDH PX_LAST

    Returns {bbg_ticker: [{"quarter": "Q4'25", "eps_beat_pct": 8.2, ...}, ...]}.
    """
    result = {}
    for bt in bbg_tickers:
        short = bt.split(" ")[0]
        history = []
        ticker_actuals = actuals_data.get(short, [])

        # Build lookup: quarter label -> actuals dict
        actuals_by_q = {}
        for a in ticker_actuals:
            actuals_by_q[a["quarter"]] = a

        # Get earnings dates
        try:
            df = blp.bds(bt, "ERN_ANN_DT_AND_PER")
            quarters = []
            for row in df.rows():
                period = str(row[3]) if len(row) > 3 else str(row[2])
                if ":Q" in period:
                    quarters.append({"date": str(row[2]), "period": period})
            quarters = quarters[:4]  # last 4
        except Exception:
            result[bt] = []
            continue

        usd_ovr = [("EQY_FUND_CRNCY", "USD")] if short in USD_OVERRIDE_TICKERS else []

        for q in quarters:
            try:
                earn_dt = date.fromisoformat(q["date"])
            except (ValueError, TypeError):
                continue

            # Quarter label: "2025:Q4" -> "Q4'25"
            parts = q["period"].split(":")
            yr = parts[0][2:] if len(parts[0]) == 4 else parts[0]
            qlabel = f"{parts[1]}'{yr}" if len(parts) > 1 else q["period"]

            # Absolute period override: "2025:Q4" -> "25Q4"
            abs_period = f"{yr}{parts[1]}" if len(parts) > 1 else None

            # Pre-earnings consensus estimate via BDH with absolute period
            # Use BEST_EPS_GAAP for EPS to match GAAP actuals from Call-extraction
            pre_start = (earn_dt - timedelta(days=10)).strftime("%Y-%m-%d")
            pre_end = (earn_dt - timedelta(days=1)).strftime("%Y-%m-%d")
            est_eps = est_rev = None
            if abs_period:
                for field, target in [("BEST_EPS_GAAP", "est_eps"), ("BEST_SALES", "est_rev")]:
                    try:
                        ovr = [("BEST_FPERIOD_OVERRIDE", abs_period)] + usd_ovr
                        df2 = blp.bdh(bt, field, pre_start, pre_end,
                                      periodicitySelection="DAILY", overrides=ovr)
                        tbl = df2.to_native()
                        vals = [float(v) for v in tbl.column("value").to_pylist()]
                        if vals:
                            if target == "est_eps":
                                est_eps = vals[-1]
                            else:
                                est_rev = vals[-1]
                    except Exception:
                        pass

            # Actuals from Call-extraction
            act = actuals_by_q.get(qlabel, {})
            act_eps = act.get("EPS")
            act_rev = act.get("Revenue")

            # Stock price reaction
            stock_rxn = None
            try:
                pre_dt = (earn_dt - timedelta(days=3)).strftime("%Y-%m-%d")
                post_end = (earn_dt + timedelta(days=2)).strftime("%Y-%m-%d")
                df4 = blp.bdh(bt, "PX_LAST", pre_dt, post_end)
                tbl = df4.to_native()
                dates = [str(d) for d in tbl.column("date").to_pylist()]
                vals = [float(v) for v in tbl.column("value").to_pylist()]
                pre_price = post_price = None
                earn_str = q["date"]
                for d, v in zip(dates, vals):
                    if d < earn_str:
                        pre_price = v
                    elif d >= earn_str and post_price is None:
                        post_price = v
                if pre_price and post_price:
                    stock_rxn = round((post_price - pre_price) / pre_price * 100, 1)
            except Exception:
                pass

            # Compute beat/miss percentages
            eps_beat = None
            if est_eps is not None and act_eps is not None and est_eps != 0:
                eps_beat = round((act_eps - est_eps) / abs(est_eps) * 100, 1)
            rev_beat = None
            if est_rev is not None and act_rev is not None and est_rev != 0:
                rev_beat = round((act_rev - est_rev) / abs(est_rev) * 100, 1)

            history.append({
                "quarter": qlabel,
                "eps_beat_pct": eps_beat,
                "rev_beat_pct": rev_beat,
                "stock_rxn": stock_rxn,
            })

        result[bt] = history

    return result


def pull_prior_year_annual_eps(bbg_tickers):
    """Pull prior FY actual EPS using IS_EPS (reported) for annual y/y.

    Returns {bbg_ticker: float or None}.
    """
    data = _bdp_batch(bbg_tickers, "IS_EPS")
    result = {}
    for bt in bbg_tickers:
        val = data.get(bt, {}).get("IS_EPS")
        try:
            result[bt] = float(val) if val is not None else None
        except (ValueError, TypeError):
            result[bt] = None
    return result


def compute_yoy(current, prior, fmt):
    """Compute y/y change. Returns string like '+12%' or '+40bps' or None.

    No decimal places for double-digit changes.
    """
    if current is None or prior is None:
        return None
    if fmt == "percent":
        bps = (current - prior) * 100
        sign = "+" if bps >= 0 else ""
        return f"{sign}{bps:.0f}bps"
    else:
        if prior == 0:
            return None
        pct = (current - prior) / abs(prior) * 100
        sign = "+" if pct >= 0 else ""
        if abs(pct) >= 10:
            return f"{sign}{pct:.0f}%"
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
    position = (consensus - low) / (high - low)
    if position > 0.85:
        return "above"
    elif position < 0.15:
        return "below"
    else:
        return "mid"


def load_guidance_overrides():
    """Load guidance_overrides.json if it exists. Returns dict or empty dict."""
    if os.path.exists(GUIDANCE_PATH):
        with open(GUIDANCE_PATH) as f:
            return json.load(f)
    return {}


def main():
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    config = load_metrics_config()
    field_map = config["_field_map"]
    guidance_overrides = load_guidance_overrides()

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
    print("\n[5/7] Revision counts...")
    revisions_data = pull_revisions(bbg_tickers)

    # Step 6: EPS 4-week % change
    print("\n[6/8] EPS 4-week change...")
    eps_4wk_data = pull_eps_4wk_change(bbg_tickers)

    # Step 7: Prior FY actual EPS (for annual y/y)
    print("\n[7/8] Prior FY actual EPS...")
    prior_fy_eps = pull_prior_year_annual_eps(bbg_tickers)

    # Step 8: Earnings history (beats/misses + stock reactions)
    print("\n[8/8] Earnings history (last 4 quarters)...")
    actuals_data = {}
    if os.path.exists(ACTUALS_PATH):
        with open(ACTUALS_PATH) as f:
            actuals_data = json.load(f)
    history_data = pull_earnings_history(bbg_tickers, actuals_data)

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
        eps_4wk_pct = eps_4wk_data.get(bt)
        prior_fy_eps_val = prior_fy_eps.get(bt)
        history = history_data.get(bt, [])

        # Merge guidance from Bloomberg API and Call-extraction overrides
        go = guidance_overrides.get(short, {})
        go_q = go.get("quarterly", {})
        go_a = go.get("annual", {})

        # Build quarterly metrics
        metrics = []
        for metric_name in ticker_metrics:
            fmt_info = field_map.get(metric_name, {})
            fmt = fmt_info.get("format", "number")
            cons_q = consensus.get(metric_name, {}).get("quarterly")
            prior_q = prior.get(metric_name, {}).get("quarterly")
            # Capex: Bloomberg returns negative, show as positive
            if metric_name == "Capex":
                if cons_q is not None:
                    cons_q = abs(cons_q)
                if prior_q is not None:
                    prior_q = abs(prior_q)
            # Bloomberg guidance first, then call-extraction override
            guide_q = guidance.get(metric_name, {}).get("quarterly")
            if not guide_q and metric_name in go_q:
                guide_q = go_q[metric_name]

            metrics.append({
                "name": metric_name,
                "consensus": cons_q,
                "guidance_low": guide_q["low"] if guide_q else None,
                "guidance_high": guide_q["high"] if guide_q else None,
                "prior_year": prior_q,
                "yoy": compute_yoy(cons_q, prior_q, fmt),
                "vs_guide": compute_vs_guide(cons_q, guide_q),
            })

        # Build annual metrics (only for metrics that have annual data)
        annual_metrics = []
        for metric_name in ticker_metrics:
            fmt_info = field_map.get(metric_name, {})
            fmt = fmt_info.get("format", "number")
            cons_a = consensus.get(metric_name, {}).get("annual")
            prior_a = prior.get(metric_name, {}).get("annual")
            # Capex: show as positive
            if metric_name == "Capex":
                if cons_a is not None:
                    cons_a = abs(cons_a)
                if prior_a is not None:
                    prior_a = abs(prior_a)
            # For annual EPS: use IS_EPS (actual reported) as prior if available
            if metric_name == "EPS" and prior_a is None and prior_fy_eps_val is not None:
                prior_a = prior_fy_eps_val
            guide_a = guidance.get(metric_name, {}).get("annual")
            if not guide_a and metric_name in go_a:
                guide_a = go_a[metric_name]

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
            "eps_4wk_pct": eps_4wk_pct,
            "earnings_history": history,
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
