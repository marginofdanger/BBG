"""Pull earnings calendar data, consensus estimates, guidance, and revisions from Bloomberg."""

import json
import os
from datetime import date, timedelta

from xbbg import blp

from bloomberg import USD_OVERRIDE_TICKERS

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SNAPSHOT_DIR = os.path.join(REPO_ROOT, "output", "snapshots")
METRICS_PATH = os.path.join(REPO_ROOT, "config", "earnings_metrics.json")
GUIDANCE_PATH = os.path.join(REPO_ROOT, "config", "guidance_overrides.json")
ACTUALS_PATH = os.path.join(REPO_ROOT, "config", "actuals_overrides.json")

PORTFOLIO = ["HCA", "UNH", "TSM", "AVGO", "NVDA", "META", "AMZN", "JPM", "APO", "PGR", "CVNA", "APP", "VEEV"]
WATCHLIST = ["FICO", "GOOG", "MU", "HOOD", "TDG", "GE", "LRCX", "DASH", "UBER", "LLY", "MSFT", "V",
             "BX", "BKNG", "HLT", "IBKR", "NET", "COST", "TSLA", "TMO", "COF", "AON", "MC"]

# Non-US tickers that need explicit Bloomberg identifiers
BBG_OVERRIDES = {"MC": "MC FP Equity"}

# Ticker-specific overrides for EPS actuals/estimates
# eps_ticker: which BBG ticker to pull actuals from
# eps_field: override the default IS_DILUTED_EPS field
# eps_mult: multiplier for the actual (e.g., ADR ratio)
# skip_usd_est: if True, don't apply USD override on estimates (compare in native ccy)
# est_field: override the default BEST_EPS_GAAP estimate field
# prior_fy_field: override IS_EPS for prior FY actual
EPS_OVERRIDES = {
    # Megacaps: sell-side adds back SBC but companies don't → use GAAP-to-GAAP
    "AMZN US Equity": {"eps_field": "IS_DILUTED_EPS", "est_field": "BEST_EPS_GAAP"},
    "GOOG US Equity": {"eps_ticker": "GOOGL US Equity", "eps_field": "IS_DILUTED_EPS",
                       "est_field": "BEST_EPS_GAAP"},
    "META US Equity": {"eps_field": "IS_DILUTED_EPS", "est_field": "BEST_EPS_GAAP"},
    # ADR: convert from Taiwan-listed shares
    "TSM US Equity":  {"eps_ticker": "2330 TT Equity", "eps_mult": 5, "skip_usd_est": True},
    # Alt manager: use distributable earnings
    "APO US Equity":  {"eps_field": "IS_DISTRIBUTABLE_INCOME_PER_UNIT",
                       "prior_fy_field": "IS_DISTRIBUTABLE_INCOME_PER_UNIT"},
}


def _bbg_ticker(short):
    """Convert short ticker to Bloomberg format."""
    return BBG_OVERRIDES.get(short, f"{short} US Equity")


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
    fields = ["EXPECTED_REPORT_DT", "EXPECTED_REPORT_TIME", "EXPECTED_REPORT_TYP"]
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
        status = str(info.get("EXPECTED_REPORT_TYP", "")).strip()
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
    2. Pre-earnings consensus from BDH BEST_EPS/BEST_SALES with absolute period override
    3. Actuals from BDH IS_COMP_EPS_ADJUSTED/IS_COMP_SALES quarterly (fallback: actuals_overrides.json)
    4. Stock price reaction from BDH PX_LAST

    Returns {bbg_ticker: [{"quarter": "Q4'25", "eps_beat_pct": 8.2, ...}, ...]}.
    """
    # Uses module-level EPS_OVERRIDES for ticker-specific config

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

        # Pre-pull quarterly actuals via BDH (one call per field per ticker)
        eps_actuals_by_date = {}  # {date_str: float}
        rev_actuals_by_date = {}
        lookback_start = (date.today() - timedelta(days=550)).strftime("%Y-%m-%d")
        lookback_end = date.today().strftime("%Y-%m-%d")
        eps_ovr = EPS_OVERRIDES.get(bt, {})
        eps_ticker = eps_ovr.get("eps_ticker", bt)
        eps_field = eps_ovr.get("eps_field", "IS_COMP_EPS_ADJUSTED")
        eps_mult = eps_ovr.get("eps_mult", 1)
        skip_usd_est = eps_ovr.get("skip_usd_est", False)
        eps_est_field = eps_ovr.get("est_field", "BEST_EPS")
        # Don't pass USD override when pulling from a different ticker (e.g., 2330 TT)
        eps_act_ovr = [] if eps_ticker != bt else usd_ovr
        for field in [eps_field]:
            try:
                df_act = blp.bdh(eps_ticker, field, lookback_start, lookback_end,
                                 periodicitySelection="QUARTERLY", overrides=eps_act_ovr)
                tbl = df_act.to_native()
                for d, v in zip(tbl.column("date").to_pylist(),
                                tbl.column("value").to_pylist()):
                    try:
                        eps_actuals_by_date[str(d)] = float(v) * eps_mult
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass
        # Revenue: IS_COMP_SALES works for both financials and non-financials
        for field in ["IS_COMP_SALES", "SALES_REV_TURN"]:
            try:
                df_act = blp.bdh(bt, field, lookback_start, lookback_end,
                                 periodicitySelection="QUARTERLY", overrides=usd_ovr)
                tbl = df_act.to_native()
                for d, v in zip(tbl.column("date").to_pylist(),
                                tbl.column("value").to_pylist()):
                    try:
                        rev_actuals_by_date[str(d)] = float(v)
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass
            if rev_actuals_by_date:
                break  # Use first field that returns data

        # Sort actuals dates for matching to earnings announcement dates
        eps_dates_sorted = sorted(eps_actuals_by_date.keys())
        rev_dates_sorted = sorted(rev_actuals_by_date.keys())

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

            # Pre-earnings consensus estimates via BDH with absolute period
            pre_start = (earn_dt - timedelta(days=10)).strftime("%Y-%m-%d")
            pre_end = (earn_dt - timedelta(days=1)).strftime("%Y-%m-%d")
            earn_str = q["date"]
            est_eps = est_rev = None
            est_usd = usd_ovr if not skip_usd_est else []
            if abs_period:
                if eps_est_field != "BEST_EPS":
                    # Custom estimate field (e.g., APO) — use directly
                    try:
                        ovr = [("BEST_FPERIOD_OVERRIDE", abs_period)] + est_usd
                        df2 = blp.bdh(bt, eps_est_field, pre_start, pre_end,
                                      periodicitySelection="DAILY", overrides=ovr)
                        tbl = df2.to_native()
                        vals = [float(v) for v in tbl.column("value").to_pylist()]
                        if vals:
                            est_eps = vals[-1]
                    except Exception:
                        pass
                else:
                    # Auto-select: pull both BEST_EPS and BEST_EPS_GAAP,
                    # pick whichever is closer to the comparable actual
                    est_adj = est_gaap = None
                    for fld in ["BEST_EPS", "BEST_EPS_GAAP"]:
                        try:
                            ovr = [("BEST_FPERIOD_OVERRIDE", abs_period)] + est_usd
                            df2 = blp.bdh(bt, fld, pre_start, pre_end,
                                          periodicitySelection="DAILY", overrides=ovr)
                            tbl = df2.to_native()
                            vals = [float(v) for v in tbl.column("value").to_pylist()]
                            if vals:
                                if fld == "BEST_EPS":
                                    est_adj = vals[-1]
                                else:
                                    est_gaap = vals[-1]
                        except Exception:
                            pass
                    # Match actuals first to inform estimate selection
                    _act = None
                    for d in reversed(eps_dates_sorted):
                        if d < earn_str:
                            _act = eps_actuals_by_date[d]
                            break
                    if _act is not None and est_adj is not None and est_gaap is not None:
                        est_eps = est_gaap if abs(_act - est_gaap) <= abs(_act - est_adj) else est_adj
                    else:
                        est_eps = est_adj if est_adj is not None else est_gaap

                # Revenue estimate
                try:
                    ovr = [("BEST_FPERIOD_OVERRIDE", abs_period)] + usd_ovr
                    df2 = blp.bdh(bt, "BEST_SALES", pre_start, pre_end,
                                  periodicitySelection="DAILY", overrides=ovr)
                    tbl = df2.to_native()
                    vals = [float(v) for v in tbl.column("value").to_pylist()]
                    if vals:
                        est_rev = vals[-1]
                except Exception:
                    pass

            # Actuals: Bloomberg IS_DILUTED_EPS (primary), Call-extraction (fallback)
            act_eps = act_rev = None
            for d in reversed(eps_dates_sorted):
                if d < earn_str:
                    act_eps = eps_actuals_by_date[d]
                    break
            for d in reversed(rev_dates_sorted):
                if d < earn_str:
                    act_rev = rev_actuals_by_date[d]
                    break

            # Fallback to Call-extraction actuals if Bloomberg didn't return data
            if act_eps is None or act_rev is None:
                act = actuals_by_q.get(qlabel, {})
                if act_eps is None:
                    act_eps = act.get("EPS")
                if act_rev is None:
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
            "earnings_time": "",
            "metrics": [],
            "stock": {"d1": None, "w1": None, "w1_vs_spx": None},
            "ntm_eps_chg": None,
        }

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
                    earn_str = last["date"].isoformat()
                    latest_idx = -1
                    for i, d in enumerate(dates_col):
                        if d <= earn_str:
                            latest_idx = i
                        else:
                            break
                    if latest_idx >= 0:
                        try:
                            raw = float(vals_col[latest_idx])
                            actual = raw * eps_mult if metric_name == "EPS" else raw
                            if metric_name == "Capex" and actual is not None:
                                actual = abs(actual)
                        except (ValueError, TypeError):
                            actual = None
                    if latest_idx >= 4:
                        try:
                            prior_val = float(vals_col[latest_idx - 4])
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
                spx_post = spx_by_date.get(w1_day) if w1_day else None
                if spx_pre and spx_post:
                    spx_w1 = (spx_post - spx_pre) / spx_pre
                    record["stock"]["w1_vs_spx"] = round(
                        record["stock"]["w1"] - spx_w1, 4)
        except Exception:
            pass

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

        reported.append(record)

    reported.sort(key=lambda r: r["earnings_date"], reverse=True)
    return reported


def pull_prior_year_annual_eps(bbg_tickers):
    """Pull prior FY actual EPS using IS_EPS (reported) for annual y/y.

    Respects EPS_OVERRIDES for tickers with non-standard EPS fields.
    Returns {bbg_ticker: float or None}.
    """
    # Batch pull IS_COMP_EPS_ADJUSTED for tickers without overrides
    standard = [bt for bt in bbg_tickers if "prior_fy_field" not in EPS_OVERRIDES.get(bt, {})]
    data = _bdp_batch(standard, "IS_COMP_EPS_ADJUSTED") if standard else {}
    result = {}
    for bt in bbg_tickers:
        ovr = EPS_OVERRIDES.get(bt, {})
        if "prior_fy_field" in ovr:
            # Pull custom field individually (e.g., APO distributable earnings)
            try:
                df = blp.bdp(bt, ovr["prior_fy_field"])
                for row in df.rows():
                    result[bt] = float(row[2]) if row[2] is not None else None
            except Exception:
                result[bt] = None
        else:
            val = data.get(bt, {}).get("IS_COMP_EPS_ADJUSTED")
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
    print("\n[1/9] Earnings dates...")
    dates_data = pull_earnings_dates(bbg_tickers)

    # Step 2: Consensus estimates
    print("\n[2/9] Consensus estimates...")
    consensus_data = pull_consensus(bbg_tickers, config)

    # Step 3: Prior-year actuals
    print("\n[3/9] Prior-year actuals...")
    prior_data = pull_prior_year(bbg_tickers, config)

    # Step 4: Guidance
    print("\n[4/9] Guidance ranges...")
    guidance_data = pull_guidance(bbg_tickers, config)

    # Step 5: Revisions
    print("\n[5/9] Revision counts...")
    revisions_data = pull_revisions(bbg_tickers)

    # Step 6: EPS 4-week % change
    print("\n[6/9] EPS 4-week change...")
    eps_4wk_data = pull_eps_4wk_change(bbg_tickers)

    # Step 7: Prior FY actual EPS (for annual y/y)
    print("\n[7/9] Prior FY actual EPS...")
    prior_fy_eps = pull_prior_year_annual_eps(bbg_tickers)

    # Step 8: Earnings history (beats/misses + stock reactions)
    print("\n[8/9] Earnings history (last 4 quarters)...")
    actuals_data = {}
    if os.path.exists(ACTUALS_PATH):
        with open(ACTUALS_PATH) as f:
            actuals_data = json.load(f)
    history_data = pull_earnings_history(bbg_tickers, actuals_data)

    # Step 9: Reported details (last 45 days)
    print("\n[9/9] Reported actuals & post-earnings moves...")
    group_lookup = {e["bbg"]: e["group"] for e in all_tickers}
    reported_data = pull_reported_details(bbg_tickers, config, group_lookup)

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
        "reported": reported_data,
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
    from _hub_reporting import reporting
    with reporting("pull_earnings.py", changes=["earnings refreshed"]):
        main()
