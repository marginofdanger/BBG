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
WATCHLIST_CORE = ["FICO", "GOOG", "MU", "HOOD", "TDG", "GE", "LRCX", "DASH", "UBER", "LLY", "MSFT", "V",
                  "BX", "BKNG", "HLT", "IBKR", "NET", "COST", "TSLA", "TMO", "COF", "AON", "MC"]

# Non-US tickers that need explicit Bloomberg identifiers
BBG_OVERRIDES = {"MC": "MC FP Equity"}

CALENDAR_YEARS = [2025, 2026, 2027, 2028]
LOOKBACK_CORE = 24   # months for portfolio + core watchlist
LOOKBACK_EXT = 12    # months for extended watchlist
MKTCAP_GAAP_THRESHOLD = 200_000_000_000
Q1_FYE_SHIFT = 1

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EXTENDED_WATCHLIST_PATH = os.path.join(REPO_ROOT, "config", "extended_watchlist.json")
SNAPSHOT_DIR = os.path.join(REPO_ROOT, "output", "snapshots")


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
        # Indices only support BEST_EPS, not BEST_EPS_GAAP
        if bt.endswith(' Index'):
            result[bt] = ("BEST_EPS", "Adj")
            continue
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
            'short': t, 'bbg': BBG_OVERRIDES.get(t, f'{t} US Equity'),
            'group': 'Watchlist', 'category': '', 'lookback': LOOKBACK_CORE,
        })

    # Extended watchlist — split indices into their own group
    seen = {e['short'] for e in entries}
    for item in _load_extended_watchlist():
        if item['ticker'] in seen:
            continue
        seen.add(item['ticker'])
        is_index = item.get('category') == 'Indices'
        entries.append({
            'short': item['ticker'], 'bbg': item['bbg'],
            'group': 'Indices' if is_index else 'Extended',
            'category': item.get('category', ''),
            'lookback': LOOKBACK_CORE if is_index else LOOKBACK_EXT,
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
            # estimate_history() accepts "HCA" or "HCA US Equity"
            # Pass the full Bloomberg ticker so it works for international tickers too
            rows = estimate_history(bbg, fiscal_years, lookback, field)
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

    header = ["Ticker", "Group", "Category", "GICS Sector", "GICS Industry", "EPS Type", "FYE", "Metric", "Year"] + \
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
        # UK stocks: price is in pence, convert to GBP for PE calculation
        price_for_pe = price
        if price and bbg.endswith(" LN Equity"):
            price_for_pe = price / 100
        estimates = ticker_estimates.get(short, [])

        for est_row in estimates:
            year_label = est_row.get("line_item", "")
            row_data = [short, group, category, gics_sector, gics_industry, eps_label, fye_label, "EPS", year_label]

            prev_val = None
            for i, q in enumerate(sorted_quarters):
                val = est_row.get(q)
                row_data.append(val if val is not None else "")
                if i > 0:
                    row_data.append(_format_pct_change(prev_val, val))
                prev_val = val if val is not None else prev_val

            # Price
            row_data.append(price if price is not None else "")

            # PE (use price_for_pe which is adjusted for pence)
            pe = ""
            if price_for_pe:
                latest_eps = None
                for q in reversed(sorted_quarters):
                    if q in est_row and est_row[q] is not None:
                        latest_eps = est_row[q]
                        break
                if latest_eps and float(latest_eps) != 0:
                    pe = round(float(price_for_pe) / float(latest_eps), 1)
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

    # --- Revenue estimates for portfolio + peer companies ---
    print("\n[6b/6] Pulling revenue estimates for portfolio and peer companies...")

    # Collect all tickers that need revenue: portfolio + all peers
    PEER_TICKERS = set()
    PEER_MAP = {
        'HCA': ['THC', 'UHS', 'CYH', 'DVA', 'DGX'],
        'UNH': ['CI', 'ELV', 'HUM', 'CNC', 'MOH'],
        'TSM': ['005930', '000660', 'INTC', 'MU', 'GFS', 'LRCX', 'AMAT', 'ASML'],
        'AVGO': ['QCOM', 'MRVL', 'AMD', 'TXN', 'ADI'],
        'NVDA': ['AMD', 'INTC', 'AVGO', 'MRVL', 'ARM', '2454'],
        'META': ['GOOG', 'PINS', 'SNAP', 'RDDT', 'TTD'],
        'AMZN': ['GOOG', 'MSFT', 'SHOP', 'BKNG', 'EBAY', 'WMT', 'COST'],
        'JPM': ['GS', 'BAC', 'MS', 'WFC', 'C'],
        'APO': ['BX', 'KKR', 'ARES', 'CG', 'OWL', 'BAM', 'BN'],
        'PGR': ['ALL', 'TRV', 'CB', 'AIG', 'ACGL', 'KMPR'],
        'CVNA': ['KMX', 'AN', 'CPRT', 'GPI', 'SAH', 'LAD'],
        'APP': ['RDDT', 'TTD', 'PINS', 'DASH', 'U'],
        'VEEV': ['CRM', 'WDAY', 'NOW', 'DDOG', 'GWRE', 'INTU'],
    }
    for peers in PEER_MAP.values():
        PEER_TICKERS.update(peers)

    rev_entries = [e for e in entries if e['short'] in set(PORTFOLIO) | PEER_TICKERS]
    for entry in rev_entries:
        short = entry['short']
        bbg = entry['bbg']
        fye_label, fye_offset = fye_data.get(bbg, ("Dec", 0))
        fiscal_years = [cy + fye_offset for cy in CALENDAR_YEARS]
        print(f"  {short} (BEST_SALES)...")

        try:
            rev_rows = estimate_history(bbg, fiscal_years, entry['lookback'], "BEST_SALES")
        except Exception as e:
            print(f"    WARNING: {short} revenue: {e}")
            rev_rows = [{"line_item": f"CY{y}"} for y in fiscal_years]

        if fye_offset:
            for row in rev_rows:
                li = row.get("line_item", "")
                if li.startswith("CY"):
                    fy = int(li[2:])
                    row["line_item"] = f"CY{fy - fye_offset}"

        gics = gics_data.get(bbg, {})
        gics_sector = gics.get("GICS_SECTOR_NAME", "")
        gics_industry = gics.get("GICS_INDUSTRY_GROUP_NAME", "")
        ret = returns_data.get(bbg, {})
        price = ret.get("PX_LAST")

        for est_row in rev_rows:
            year_label = est_row.get("line_item", "")
            row_data = [short, entry['group'], entry.get('category', ''),
                        gics_sector, gics_industry, '', fye_label, "Revenue", year_label]

            prev_val = None
            for i, q in enumerate(sorted_quarters):
                val = est_row.get(q)
                row_data.append(val if val is not None else "")
                if i > 0:
                    row_data.append(_format_pct_change(prev_val, val))
                prev_val = val if val is not None else prev_val

            # Price, PE (N/A for revenue), 12m Rev
            row_data.append(price if price is not None else "")
            row_data.append("")  # PE not applicable

            # 12m revision
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

            for f in ["CHG_PCT_YTD", "CHG_PCT_3M", "CHG_PCT_1YR"]:
                r = ret.get(f)
                if r is not None:
                    row_data.append(f"{'+' if r >= 0 else ''}{r:.1f}%")
                else:
                    row_data.append("")

            csv_rows.append(row_data)

    csv_path = os.path.join(SNAPSHOT_DIR, f"estimates_{today_str}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in csv_rows:
            writer.writerow(row)

    print(f"Saved snapshot: {csv_path}")
    print(f"  Rows: {len(csv_rows)}, Columns: {len(header)}")

    # Update estimates index
    est_dates = sorted(
        [f.replace("estimates_", "").replace(".csv", "")
         for f in os.listdir(SNAPSHOT_DIR) if f.startswith("estimates_") and f.endswith(".csv")],
        reverse=True,
    )
    idx_path = os.path.join(SNAPSHOT_DIR, "index_estimates.json")
    with open(idx_path, "w") as fh:
        json.dump(est_dates, fh, indent=2)
    print(f"Updated: {idx_path}")

    # Also generate a prices snapshot
    print("\nGenerating prices snapshot...")
    import subprocess
    subprocess.run(["python", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pull_prices.py")])

    print("Done.")


if __name__ == "__main__":
    main()
