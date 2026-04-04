"""Bloomberg data extraction via xbbg."""

from datetime import date
from xbbg import blp

# Companies requiring USD currency override (estimates default to local currency)
USD_OVERRIDE_TICKERS = {"TSM"}


def estimate_history(ticker, target_years, lookback_months=24, field="BEST_EPS"):
    """Pull consensus estimate snapshots at each quarter-end for fixed calendar years.

    Args:
        ticker: Bloomberg ticker (e.g. "HCA US Equity" or just "HCA")
        target_years: list of calendar years (e.g. [2025, 2026, 2027])
        lookback_months: how many months back to pull (default 24)
        field: Bloomberg estimate field (default "BEST_EPS")

    Returns:
        list of dicts in Metrics-extraction shared format:
        [{"line_item": "CY2026", "Q2 2024": 30.77, "Q3 2024": 27.93, ...}, ...]
    """
    short_ticker = ticker.replace(" US Equity", "")
    if not ticker.endswith(" Equity"):
        ticker = f"{ticker} US Equity"

    today = date.today()
    current_year = today.year

    # Build observation year segments covering the lookback period
    start_year = current_year - (lookback_months // 12) - 1
    segments = []
    for obs_year in range(start_year, current_year + 1):
        seg_start = f"{obs_year}-01-01"
        seg_end = f"{obs_year}-12-31"
        if obs_year == start_year:
            # Trim start to match lookback
            start_month = today.month
            seg_start = f"{obs_year}-{start_month:02d}-01"
        if obs_year == current_year:
            seg_end = today.strftime("%Y-%m-%d")
        segments.append((seg_start, seg_end, obs_year))

    # Pull data for each target year using absolute period references.
    # Use "NNY" format (e.g. "26Y" for FY2026) which maps to fixed fiscal years
    # regardless of observation date. Relative offsets (NCY) are off by one year
    # for historical queries and should NOT be used.
    raw = {ty: {} for ty in target_years}
    for seg_start, seg_end, obs_year in segments:
        for ty in target_years:
            # Use two-digit absolute year: "25Y", "26Y", etc.
            period = f"{ty % 100}Y"
            overrides = [("BEST_FPERIOD_OVERRIDE", period)]
            if short_ticker in USD_OVERRIDE_TICKERS:
                overrides.append(("EQY_FUND_CRNCY", "USD"))
            try:
                df = blp.bdh(
                    ticker, field,
                    seg_start, seg_end,
                    periodicitySelection="MONTHLY",
                    nonTradingDayFillMethod="PREVIOUS_VALUE",
                    overrides=overrides,
                )
                tbl = df.to_native()
                dates = [str(d) for d in tbl.column("date").to_pylist()]
                values = tbl.column("value").to_pylist()
                for d, v in zip(dates, values):
                    raw[ty][d] = float(v)
            except Exception:
                pass

    # Build quarter-end snapshots using the last available data point in each quarter.
    # Bloomberg doesn't always return data for the exact quarter-end month,
    # so we take the latest month within each quarter.

    # Determine the range of quarters covered by the data
    all_dates = set()
    for ty in target_years:
        all_dates.update(raw[ty].keys())
    if not all_dates:
        return [{"line_item": f"CY{ty}"} for ty in target_years]

    all_year_months = sorted(set(d[:7] for d in all_dates))
    min_ym, max_ym = all_year_months[0], all_year_months[-1]

    # Build a list of quarters from the data range
    quarter_ends = {1: "03", 2: "06", 3: "09", 4: "12"}
    quarters = []
    for year in range(int(min_ym[:4]), int(max_ym[:4]) + 1):
        for q in range(1, 5):
            ym = f"{year}-{quarter_ends[q]}"
            if ym < min_ym[:5] + "0" or ym > max_ym:
                continue
            quarters.append((year, q, f"Q{q} {year}"))

    def _best_val_for_quarter(series, year, q):
        """Get the last available value within a calendar quarter."""
        q_months = {1: ("01", "02", "03"), 2: ("04", "05", "06"),
                    3: ("07", "08", "09"), 4: ("10", "11", "12")}
        months = q_months[q]
        best_date, best_val = None, None
        for d in sorted(series):
            if d[:4] == str(year) and d[5:7] in months:
                best_date, best_val = d, series[d]
        return best_val

    # Build output rows
    rows = []
    for ty in target_years:
        row = {"line_item": f"CY{ty}"}
        for year, q, label in quarters:
            val = _best_val_for_quarter(raw[ty], year, q)
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
