"""Pull EPS estimate histories and stock returns from Bloomberg, save a timestamped CSV snapshot."""

import csv
import json
import os
from datetime import date

from xbbg import blp

from bloomberg import estimate_history, USD_OVERRIDE_TICKERS

# ---------------------------------------------------------------------------
# Ticker lists
# ---------------------------------------------------------------------------
PORTFOLIO = ["HCA", "UNH", "TSM", "AVGO", "NVDA", "META", "AMZN", "JPM", "APO", "PGR", "CVNA", "APP", "VEEV"]
WATCHLIST_CORE = ["FICO", "GOOG", "MU", "HOOD", "TDG", "GE", "LRCX", "DASH", "UBER", "LLY", "MSFT", "V"]

CALENDAR_YEARS = [2025, 2026, 2027, 2028]
LOOKBACK_CORE = 24   # months for portfolio + core watchlist
LOOKBACK_EXT = 12    # months for extended watchlist
MKTCAP_GAAP_THRESHOLD = 200_000_000_000
Q1_FYE_SHIFT = 1

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENDED_WATCHLIST_PATH = os.path.join(SCRIPT_DIR, "extended_watchlist.json")
SNAPSHOT_DIR = os.path.join(SCRIPT_DIR, "output", "snapshots")


def _bdp_to_dict(df):
    """Convert xbbg bdp result to {ticker: {field: value}}."""
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


def _bdp_batch(bbg_tickers, fields, batch_size=50):
    """Pull bdp in batches to avoid Bloomberg request size limits."""
    result = {}
    for i in range(0, len(bbg_tickers), batch_size):
        batch = bbg_tickers[i:i+batch_size]
        try:
            df = blp.bdp(batch, fields)
            result.update(_bdp_to_dict(df))
        except Exception as e:
            print(f"    WARNING: bdp batch failed: {e}")
    return result


def _determine_eps_fields(bbg_tickers):
    """Return {bbg_ticker: ('BEST_EPS_GAAP'|'BEST_EPS', 'GAAP'|'Adj')} based on market cap."""
    data = _bdp_batch(bbg_tickers, "CUR_MKT_CAP")
    result = {}
    for bt in bbg_tickers:
        mktcap = data.get(bt, {}).get("CUR_MKT_CAP", 0) or 0
        if mktcap > MKTCAP_GAAP_THRESHOLD:
            result[bt] = ("BEST_EPS_GAAP", "GAAP")
        else:
            result[bt] = ("BEST_EPS", "Adj")
    return result


def _pull_fye(bbg_tickers):
    """Pull FYE month. Returns {bbg_ticker: ('Dec', 0)} or ('Jan', 1) etc."""
    data = _bdp_batch(bbg_tickers, "EQY_FISCAL_YR_END")
    month_names = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                   7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
    result = {}
    for bt in bbg_tickers:
        raw = data.get(bt, {}).get("EQY_FISCAL_YR_END", "")
        month = 12
        if raw and "/" in str(raw):
            try:
                month = int(str(raw).split("/")[0])
            except ValueError:
                month = 12
        label = month_names.get(month, 'Dec')
        offset = Q1_FYE_SHIFT if month <= 3 else 0
        result[bt] = (label, offset)
    return result


def _pull_returns(bbg_tickers):
    """Pull price and return fields."""
    fields = ["PX_LAST", "CHG_PCT_YTD", "CHG_PCT_3M", "CHG_PCT_1YR"]
    return _bdp_batch(bbg_tickers, fields)


def _pull_gics(bbg_tickers):
    """Pull GICS sector and industry group."""
    fields = ["GICS_SECTOR_NAME", "GICS_INDUSTRY_GROUP_NAME"]
    return _bdp_batch(bbg_tickers, fields)


def _sort_quarter_key(col):
    parts = col.split(" ")
    return (int(parts[1]), int(parts[0][1]))


def _format_pct_change(prev, curr):
    if prev is None or curr is None or prev == "" or curr == "":
        return ""
    try:
        prev_f, curr_f = float(prev), float(curr)
    except (ValueError, TypeError):
        return ""
    if prev_f == 0:
        return ""
    chg = (curr_f - prev_f) / abs(prev_f) * 100
    return f"{'+' if chg >= 0 else ''}{chg:.1f}%"


def _load_extended_watchlist():
    """Load extended watchlist from JSON. Returns list of {ticker, bbg, category}."""
    if not os.path.exists(EXTENDED_WATCHLIST_PATH):
        return []
    with open(EXTENDED_WATCHLIST_PATH) as f:
        return json.load(f)


def _build_ticker_list():
    """Build the full ticker list with metadata. Returns list of dicts."""
    entries = []

    # Portfolio
    for t in PORTFOLIO:
        entries.append({
            'short': t, 'bbg': f'{t} US Equity',
            'group': 'Portfolio', 'category': '', 'lookback': LOOKBACK_CORE,
        })

    # Core watchlist
    for t in WATCHLIST_CORE:
        entries.append({
            'short': t, 'bbg': f'{t} US Equity',
            'group': 'Watchlist', 'category': '', 'lookback': LOOKBACK_CORE,
        })

    # Extended watchlist
    seen = {e['short'] for e in entries}
    for item in _load_extended_watchlist():
        if item['ticker'] in seen:
            continue
        seen.add(item['ticker'])
        entries.append({
            'short': item['ticker'], 'bbg': item['bbg'],
            'group': 'Extended', 'category': item.get('category', ''),
            'lookback': LOOKBACK_EXT,
        })

    return entries


def main():
    today_str = date.today().strftime("%Y-%m-%d")
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    entries = _build_ticker_list()
    all_bbg = [e['bbg'] for e in entries]
    print(f"Total tickers: {len(entries)} (Portfolio: {sum(1 for e in entries if e['group']=='Portfolio')}, "
          f"Watchlist: {sum(1 for e in entries if e['group']=='Watchlist')}, "
          f"Extended: {sum(1 for e in entries if e['group']=='Extended')})")

    # Step 1: EPS field determination
    print(f"\n[1/6] Determining EPS field per ticker...")
    eps_fields = _determine_eps_fields(all_bbg)

    # Step 2: FYE
    print(f"\n[2/6] Pulling fiscal year end months...")
    fye_data = _pull_fye(all_bbg)

    # Step 3: Returns
    print(f"\n[3/6] Pulling stock returns...")
    returns_data = _pull_returns(all_bbg)

    # Step 4: GICS sectors
    print(f"\n[4/6] Pulling GICS sectors...")
    gics_data = _pull_gics(all_bbg)

    # Step 5: Estimate histories
    print(f"\n[5/6] Pulling estimate histories...")
    all_quarters = set()
    ticker_estimates = {}

    for i, entry in enumerate(entries):
        bbg = entry['bbg']
        short = entry['short']
        field, label = eps_fields.get(bbg, ("BEST_EPS", "Adj"))
        fye_label, fye_offset = fye_data.get(bbg, ("Dec", 0))
        lookback = entry['lookback']

        fiscal_years = [cy + fye_offset for cy in CALENDAR_YEARS]

        if (i + 1) % 25 == 0 or i == 0:
            print(f"  [{i+1}/{len(entries)}] {short}...")

        try:
            # For indices/ETFs, the ticker format is different
            est_ticker = bbg.replace(' Equity', '').replace(' Index', '')
            if bbg.endswith(' Index'):
                est_ticker = bbg  # pass full ticker for indices
            rows = estimate_history(est_ticker, fiscal_years, lookback, field)
        except Exception as e:
            print(f"    WARNING: {short}: {e}")
            rows = [{"line_item": f"CY{y}"} for y in fiscal_years]

        # Relabel fiscal years to calendar years
        if fye_offset:
            for row in rows:
                li = row.get("line_item", "")
                if li.startswith("CY"):
                    fy = int(li[2:])
                    row["line_item"] = f"CY{fy - fye_offset}"

        ticker_estimates[short] = rows
        for row in rows:
            for key in row:
                if key != "line_item":
                    all_quarters.add(key)

    sorted_quarters = sorted(all_quarters, key=_sort_quarter_key)

    # Build CSV
    print(f"\n[6/6] Writing CSV...")
    interleaved_cols = []
    for i, q in enumerate(sorted_quarters):
        interleaved_cols.append(q)
        if i > 0:
            interleaved_cols.append(f"{q} chg")

    header = ["Ticker", "Group", "Category", "GICS Sector", "GICS Industry", "EPS Type", "FYE", "Year"] + \
             interleaved_cols + ["Price", "PE", "12m Rev", "Return_YTD", "Return_3m", "Return_12m"]

    csv_rows = []
    for entry in entries:
        short = entry['short']
        bbg = entry['bbg']
        group = entry['group']
        category = entry.get('category', '')
        gics = gics_data.get(bbg, {})
        gics_sector = gics.get("GICS_SECTOR_NAME", "")
        gics_industry = gics.get("GICS_INDUSTRY_GROUP_NAME", "")
        _, eps_label = eps_fields.get(bbg, ("BEST_EPS", "Adj"))
        fye_label, _ = fye_data.get(bbg, ("Dec", 0))
        ret = returns_data.get(bbg, {})
        price = ret.get("PX_LAST")
        estimates = ticker_estimates.get(short, [])

        for est_row in estimates:
            year_label = est_row.get("line_item", "")
            row_data = [short, group, category, gics_sector, gics_industry, eps_label, fye_label, year_label]

            prev_val = None
            for i, q in enumerate(sorted_quarters):
                val = est_row.get(q)
                row_data.append(val if val is not None else "")
                if i > 0:
                    row_data.append(_format_pct_change(prev_val, val))
                prev_val = val if val is not None else prev_val

            # Price
            row_data.append(price if price is not None else "")

            # PE
            pe = ""
            if price:
                latest_eps = None
                for q in reversed(sorted_quarters):
                    if q in est_row and est_row[q] is not None:
                        latest_eps = est_row[q]
                        break
                if latest_eps and float(latest_eps) != 0:
                    pe = round(float(price) / float(latest_eps), 1)
            row_data.append(pe)

            # 12m Rev
            rev_12m = ""
            for q in reversed(sorted_quarters):
                if q in est_row and est_row[q] is not None:
                    parts = q.split(" ")
                    prev_year_q = f"{parts[0]} {int(parts[1]) - 1}"
                    if prev_year_q in est_row and est_row[prev_year_q] is not None:
                        prev_val_12m = est_row[prev_year_q]
                        if float(prev_val_12m) != 0:
                            chg = (float(est_row[q]) - float(prev_val_12m)) / abs(float(prev_val_12m)) * 100
                            rev_12m = f"{'+' if chg >= 0 else ''}{chg:.1f}%"
                    break
            row_data.append(rev_12m)

            # Returns
            for f in ["CHG_PCT_YTD", "CHG_PCT_3M", "CHG_PCT_1YR"]:
                r = ret.get(f)
                if r is not None:
                    row_data.append(f"{'+' if r >= 0 else ''}{r:.1f}%")
                else:
                    row_data.append("")

            csv_rows.append(row_data)

    csv_path = os.path.join(SNAPSHOT_DIR, f"{today_str}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in csv_rows:
            writer.writerow(row)

    print(f"Saved snapshot: {csv_path}")
    print(f"  Rows: {len(csv_rows)}, Columns: {len(header)}")

    _update_index(SNAPSHOT_DIR)
    print("Done.")


def _update_index(snapshots_dir):
    index_path = os.path.join(snapshots_dir, "index.json")
    dates = sorted(
        [f.replace(".csv", "") for f in os.listdir(snapshots_dir) if f.endswith(".csv") and len(f) == 14],
        reverse=True,
    )
    with open(index_path, "w") as fh:
        json.dump(dates, fh, indent=2)


if __name__ == "__main__":
    main()
