"""Bloomberg data extraction via xbbg."""

from datetime import date, timedelta
from xbbg import blp

# Companies requiring USD currency override (estimates default to local currency)
USD_OVERRIDE_TICKERS = {"TSM"}

# Time-offset snapshot columns (days before today). Order determines CSV column order.
SNAPSHOT_OFFSETS = [("-1yr", 365), ("-6m", 180), ("-3m", 90), ("Current", 0)]


def _value_at_or_before(series_by_date, target_date_str):
    """Return the latest value in series on or before target_date_str, or None."""
    best = None
    for d in sorted(series_by_date):
        if d <= target_date_str:
            best = series_by_date[d]
        else:
            break
    return best


def estimate_history(ticker, target_years, lookback_months=24, field="BEST_EPS"):
    """Pull consensus estimate snapshots at today / -3m / -6m / -1yr.

    Args:
        ticker: Bloomberg ticker (e.g. "HCA US Equity" or just "HCA")
        target_years: list of calendar years (e.g. [2025, 2026, 2027])
        lookback_months: unused, retained for API compatibility
        field: Bloomberg estimate field (default "BEST_EPS")

    Returns:
        list of dicts:
        [{"line_item": "CY2026", "Current": 30.77, "-3m": 29.5, "-6m": 28.1, "-1yr": 22.0}, ...]
        Missing snapshots fall back to the nearest available prior data point.
    """
    short_ticker = ticker.split(" ")[0] if " " in ticker else ticker
    if not any(ticker.endswith(s) for s in (" Equity", " Index")):
        ticker = f"{ticker} US Equity"

    today = date.today()
    # Pull a slightly wider window so -1yr has headroom for fallback.
    bdh_start = (today - timedelta(days=400)).strftime("%Y-%m-%d")
    bdh_end = today.strftime("%Y-%m-%d")

    # Equities: absolute-year override ("26Y"). Indices: relative "NBF".
    is_index = ticker.endswith(" Index")
    current_year = today.year

    raw = {ty: {} for ty in target_years}
    for ty in target_years:
        if is_index:
            offset = ty - current_year + 1
            if offset < 1:
                continue
            period = f"{offset}BF"
        else:
            period = f"{ty % 100}Y"
        overrides = [("BEST_FPERIOD_OVERRIDE", period)]
        if short_ticker in USD_OVERRIDE_TICKERS:
            overrides.append(("EQY_FUND_CRNCY", "USD"))
        try:
            df = blp.bdh(
                ticker, field,
                bdh_start, bdh_end,
                periodicitySelection="DAILY",
                nonTradingDayFillMethod="PREVIOUS_VALUE",
                overrides=overrides,
            )
            tbl = df.to_native()
            for d, v in zip(tbl.column("date").to_pylist(), tbl.column("value").to_pylist()):
                try:
                    raw[ty][str(d)] = float(v)
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass

    rows = []
    for ty in target_years:
        row = {"line_item": f"CY{ty}"}
        series = raw[ty]
        if not series:
            rows.append(row)
            continue
        for label, days_back in SNAPSHOT_OFFSETS:
            target = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
            val = _value_at_or_before(series, target)
            if val is not None:
                row[label] = val
        rows.append(row)

    return rows


def estimate_history_csv(ticker, target_years, lookback_months=24, field="BEST_EPS",
                         output_dir="output"):
    """Pull estimate history and save as CSV."""
    import csv
    import os

    rows = estimate_history(ticker, target_years, lookback_months, field)
    clean_ticker = ticker.replace(" US Equity", "").replace(" ", "_")

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{clean_ticker}_estimate_history.csv")

    period_cols = []
    for row in rows:
        for key in row:
            if key != "line_item" and key not in period_cols:
                period_cols.append(key)

    def _sort_key(col):
        q, year = col.split(" ")
        return (int(year), int(q[1]))
    period_cols.sort(key=_sort_key)

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Line Item"] + period_cols)
        for row in rows:
            csv_row = [row["line_item"]]
            for col in period_cols:
                val = row.get(col)
                csv_row.append(str(val) if val is not None else "")
            writer.writerow(csv_row)

    return filepath
