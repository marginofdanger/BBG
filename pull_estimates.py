"""Pull EPS estimate histories and stock returns from Bloomberg, save a timestamped CSV snapshot."""

import csv
import json
import os
from datetime import date

from xbbg import blp

from bloomberg import estimate_history

# ---------------------------------------------------------------------------
# Ticker lists
# ---------------------------------------------------------------------------
PORTFOLIO = ["HCA", "UNH", "TSM", "AVGO", "NVDA", "META", "AMZN", "JPM", "APO", "PGR", "CVNA", "APP", "VEEV"]
WATCHLIST = ["FICO", "GOOG", "MU", "HOOD", "TDG", "GE", "LRCX", "DASH", "UBER", "LLY", "MSFT", "V"]

TARGET_YEARS = [2025, 2026, 2027, 2028]
LOOKBACK_MONTHS = 24
MKTCAP_GAAP_THRESHOLD = 200_000_000_000  # $200B in raw dollars


def _bbg_ticker(ticker):
    """Return Bloomberg-style 'X US Equity' ticker."""
    return f"{ticker} US Equity"


def _bdp_to_dict(df):
    """Convert Narwhals bdp DataFrame (ticker, field, value) to nested dict {ticker: {field: value}}."""
    result = {}
    for row in df.rows():
        ticker, field, value = row[0], row[1], row[2]
        if ticker not in result:
            result[ticker] = {}
        try:
            result[ticker][field] = float(value)
        except (ValueError, TypeError):
            result[ticker][field] = value
    return result


def _determine_eps_field(tickers):
    """Return dict {ticker: ('BEST_EPS_GAAP'|'BEST_EPS', 'GAAP'|'Adj')} based on market cap."""
    bbg_tickers = [_bbg_ticker(t) for t in tickers]
    df = blp.bdp(bbg_tickers, "CUR_MKT_CAP")
    data = _bdp_to_dict(df)
    result = {}
    for t in tickers:
        bt = _bbg_ticker(t)
        mktcap = data.get(bt, {}).get("CUR_MKT_CAP", 0)
        if mktcap > MKTCAP_GAAP_THRESHOLD:
            result[t] = ("BEST_EPS_GAAP", "GAAP")
        else:
            result[t] = ("BEST_EPS", "Adj")
    return result


def _pull_returns(tickers):
    """Pull current price and return fields for all tickers via bdp."""
    fields = ["PX_LAST", "CHG_PCT_YTD", "CHG_PCT_3M", "CHG_PCT_1YR"]
    bbg_tickers = [_bbg_ticker(t) for t in tickers]
    df = blp.bdp(bbg_tickers, fields)
    data = _bdp_to_dict(df)
    result = {}
    for t in tickers:
        bt = _bbg_ticker(t)
        ticker_data = data.get(bt, {})
        result[t] = {f: ticker_data.get(f) for f in fields}
    return result


def _sort_quarter_key(col):
    """Sort key for quarter column like 'Q2 2024'."""
    parts = col.split(" ")
    return (int(parts[1]), int(parts[0][1]))


def _format_pct_change(prev, curr):
    """Format q/q % change as '+3.2%' or '-1.5%'. Returns '' if either value is missing."""
    if prev is None or curr is None or prev == "" or curr == "":
        return ""
    try:
        prev_f, curr_f = float(prev), float(curr)
    except (ValueError, TypeError):
        return ""
    if prev_f == 0:
        return ""
    chg = (curr_f - prev_f) / abs(prev_f) * 100
    sign = "+" if chg >= 0 else ""
    return f"{sign}{chg:.1f}%"


def _build_csv_rows(all_tickers, groups, eps_fields, returns_data):
    """Pull estimates for all tickers and build CSV row dicts."""
    # First pass: collect all quarter columns across all tickers
    all_quarters = set()
    ticker_estimates = {}

    for ticker in all_tickers:
        field, _ = eps_fields[ticker]
        rows = estimate_history(ticker, TARGET_YEARS, LOOKBACK_MONTHS, field)
        ticker_estimates[ticker] = rows
        for row in rows:
            for key in row:
                if key != "line_item":
                    all_quarters.add(key)

    # Sort quarters chronologically
    sorted_quarters = sorted(all_quarters, key=_sort_quarter_key)

    # Build interleaved columns: first quarter has no chg, rest have chg
    interleaved_cols = []
    for i, q in enumerate(sorted_quarters):
        interleaved_cols.append(q)
        if i > 0:
            interleaved_cols.append(f"{q} chg")

    # Build header
    header = ["Ticker", "Group", "EPS Type", "Year"] + interleaved_cols + [
        "Price", "PE", "12m Rev", "Return_YTD", "Return_3m", "Return_12m"
    ]

    # Build rows
    csv_rows = []
    for ticker in all_tickers:
        group = groups[ticker]
        _, eps_label = eps_fields[ticker]
        ret = returns_data.get(ticker, {})
        price = ret.get("PX_LAST")
        estimates = ticker_estimates[ticker]

        for est_row in estimates:
            year_label = est_row.get("line_item", "")
            row_data = [ticker, group, eps_label, year_label]

            # Get the current year's EPS for PE calculation
            current_eps = None
            if year_label == f"CY{date.today().year}":
                # Use the latest quarter's estimate for current year
                for q in reversed(sorted_quarters):
                    if q in est_row:
                        current_eps = est_row[q]
                        break

            prev_val = None
            for i, q in enumerate(sorted_quarters):
                val = est_row.get(q)
                row_data.append(val if val is not None else "")
                if i > 0:
                    row_data.append(_format_pct_change(prev_val, val))
                prev_val = val if val is not None else prev_val

            # Price, PE, 12m Rev
            row_data.append(price if price is not None else "")

            # PE: price / latest estimate for this year row
            pe = ""
            if price is not None:
                latest_eps = None
                for q in reversed(sorted_quarters):
                    if q in est_row and est_row[q] is not None:
                        latest_eps = est_row[q]
                        break
                if latest_eps and float(latest_eps) != 0:
                    pe = round(float(price) / float(latest_eps), 1)
            row_data.append(pe)

            # 12m Rev: year-over-year EPS revision (latest vs same quarter 1 year ago)
            rev_12m = ""
            for q in reversed(sorted_quarters):
                if q in est_row and est_row[q] is not None:
                    latest_q = q
                    latest_val = est_row[q]
                    # Find same quarter 1 year ago
                    parts = latest_q.split(" ")
                    prev_year_q = f"{parts[0]} {int(parts[1]) - 1}"
                    if prev_year_q in est_row and est_row[prev_year_q] is not None:
                        prev_val_12m = est_row[prev_year_q]
                        if float(prev_val_12m) != 0:
                            chg = (float(latest_val) - float(prev_val_12m)) / abs(float(prev_val_12m)) * 100
                            sign = "+" if chg >= 0 else ""
                            rev_12m = f"{sign}{chg:.1f}%"
                    break
            row_data.append(rev_12m)

            # Returns
            ytd = ret.get("CHG_PCT_YTD")
            r3m = ret.get("CHG_PCT_3M")
            r12m = ret.get("CHG_PCT_1YR")
            for r in [ytd, r3m, r12m]:
                if r is not None:
                    sign = "+" if r >= 0 else ""
                    row_data.append(f"{sign}{r:.1f}%")
                else:
                    row_data.append("")

            csv_rows.append(row_data)

    return header, csv_rows


def _update_index(snapshots_dir):
    """Update index.json with sorted list of available snapshot dates."""
    index_path = os.path.join(snapshots_dir, "index.json")
    dates = []
    for f in os.listdir(snapshots_dir):
        if f.endswith(".csv") and len(f) == 14:  # YYYY-MM-DD.csv
            dates.append(f.replace(".csv", ""))
    dates.sort(reverse=True)
    with open(index_path, "w") as fh:
        json.dump(dates, fh, indent=2)
    return index_path


def main():
    today_str = date.today().strftime("%Y-%m-%d")
    snapshots_dir = os.path.join(os.path.dirname(__file__), "output", "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)

    all_tickers = PORTFOLIO + WATCHLIST
    groups = {}
    for t in PORTFOLIO:
        groups[t] = "Portfolio"
    for t in WATCHLIST:
        groups[t] = "Watchlist"

    print(f"[1/4] Determining EPS field per ticker (market cap check)...")
    eps_fields = _determine_eps_field(all_tickers)
    for t in all_tickers:
        field, label = eps_fields[t]
        print(f"  {t:6s} -> {label} ({field})")

    print(f"\n[2/4] Pulling stock returns...")
    returns_data = _pull_returns(all_tickers)
    for t in all_tickers:
        ret = returns_data.get(t, {})
        px = ret.get("PX_LAST", "N/A")
        print(f"  {t:6s}  Price={px}")

    print(f"\n[3/4] Pulling estimate histories (this may take a few minutes)...")
    header, csv_rows = _build_csv_rows(all_tickers, groups, eps_fields, returns_data)

    # Save CSV
    csv_path = os.path.join(snapshots_dir, f"{today_str}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in csv_rows:
            writer.writerow(row)
    print(f"\n[4/4] Saved snapshot: {csv_path}")
    print(f"  Rows: {len(csv_rows)}, Columns: {len(header)}")

    # Update index
    index_path = _update_index(snapshots_dir)
    print(f"  Updated index: {index_path}")

    # Also save to the legacy flat file for backward compat
    legacy_path = os.path.join(os.path.dirname(__file__), "output", "estimate_revisions.csv")
    try:
        with open(legacy_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for row in csv_rows:
                writer.writerow(row)
        print(f"  Updated legacy file: {legacy_path}")
    except PermissionError:
        print(f"  WARNING: Could not update legacy file (file may be open): {legacy_path}")


if __name__ == "__main__":
    main()
