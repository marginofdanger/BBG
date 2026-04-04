"""Pull current prices and returns from Bloomberg. Fast — no estimate history."""

import csv
import json
import os
from datetime import date

from xbbg import blp

# Reuse ticker list and helpers from pull_estimates
from pull_estimates import (
    _build_ticker_list, _bdp_batch, _pull_returns, _pull_fye,
    _determine_eps_fields, SNAPSHOT_DIR,
)

def main():
    today_str = date.today().strftime("%Y-%m-%d")
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    entries = _build_ticker_list()
    all_bbg = [e['bbg'] for e in entries]
    print(f"Total tickers: {len(entries)}")

    print("[1/3] Pulling prices and returns...")
    returns_data = _pull_returns(all_bbg)

    print("[2/3] Pulling EPS fields and FYE for PE calculation...")
    eps_fields = _determine_eps_fields(all_bbg)
    fye_data = _pull_fye(all_bbg)

    # We need the latest estimate snapshot to compute PE
    # Find the most recent estimates CSV
    est_files = sorted(
        [f for f in os.listdir(SNAPSHOT_DIR) if f.startswith('estimates_') and f.endswith('.csv')],
        reverse=True,
    )
    latest_estimates = {}
    if est_files:
        est_path = os.path.join(SNAPSHOT_DIR, est_files[0])
        print(f"  Using estimates from: {est_files[0]}")
        with open(est_path, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                t = row['Ticker']
                yr = row['Year']
                if t not in latest_estimates:
                    latest_estimates[t] = {}
                latest_estimates[t][yr] = row

    print("[3/3] Writing prices CSV...")
    header = ["Ticker", "Group", "Category", "GICS Sector", "GICS Industry",
              "EPS Type", "FYE", "Price", "PE_CY2026", "PE_CY2027", "PE_CY2028",
              "Return_YTD", "Return_3m", "Return_12m"]

    csv_rows = []
    for entry in entries:
        bbg = entry['bbg']
        short = entry['short']
        group = entry['group']
        category = entry.get('category', '')
        _, eps_label = eps_fields.get(bbg, ("BEST_EPS", "Adj"))
        fye_label, _ = fye_data.get(bbg, ("Dec", 0))
        ret = returns_data.get(bbg, {})
        price = ret.get("PX_LAST")

        # For UK stocks, adjust price for PE
        price_for_pe = price
        if price and bbg.endswith(" LN Equity"):
            price_for_pe = price / 100

        # Get GICS from latest estimates
        est_data = latest_estimates.get(short, {})
        any_row = est_data.get('CY2026') or est_data.get('CY2025') or {}
        gics_sector = any_row.get('GICS Sector', '')
        gics_industry = any_row.get('GICS Industry', '')

        # Compute PE for each year using latest estimates
        pes = {}
        for yr in ['CY2026', 'CY2027', 'CY2028']:
            yr_row = est_data.get(yr, {})
            # Find latest non-empty estimate column
            latest_eps = None
            for col in sorted(yr_row.keys(), reverse=True):
                if col.startswith('Q') and ' ' in col and 'chg' not in col and yr_row[col]:
                    try:
                        latest_eps = float(yr_row[col])
                    except (ValueError, TypeError):
                        pass
                    if latest_eps:
                        break
            if price_for_pe and latest_eps and latest_eps != 0:
                pes[yr] = round(price_for_pe / latest_eps, 1)
            else:
                pes[yr] = ''

        row = [
            short, group, category, gics_sector, gics_industry,
            eps_label, fye_label,
            price if price is not None else '',
            pes.get('CY2026', ''), pes.get('CY2027', ''), pes.get('CY2028', ''),
        ]
        for f in ["CHG_PCT_YTD", "CHG_PCT_3M", "CHG_PCT_1YR"]:
            r = ret.get(f)
            if r is not None:
                row.append(f"{'+' if r >= 0 else ''}{r:.1f}%")
            else:
                row.append('')
        csv_rows.append(row)

    csv_path = os.path.join(SNAPSHOT_DIR, f"prices_{today_str}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in csv_rows:
            writer.writerow(row)

    print(f"Saved: {csv_path} ({len(csv_rows)} rows)")

    # Update prices index
    price_dates = sorted(
        [f.replace('prices_', '').replace('.csv', '')
         for f in os.listdir(SNAPSHOT_DIR) if f.startswith('prices_') and f.endswith('.csv')],
        reverse=True,
    )
    idx_path = os.path.join(SNAPSHOT_DIR, "index_prices.json")
    with open(idx_path, "w") as f:
        json.dump(price_dates, f, indent=2)
    print(f"Updated: {idx_path} ({len(price_dates)} snapshots)")


if __name__ == "__main__":
    main()
