"""Build updated comp sheet from Bloomberg data."""

import os
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, numbers, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from xbbg import blp

SRC = r"C:\Users\AdrianOw\OneDrive - chieftaincapital.com\comp sheet.xlsx"
OUT = r"C:\Users\AdrianOw\Projects\BBG\output\comp_sheet_updated.xlsx"

def bdp_dict(tickers, fields):
    """Pull bdp and return {ticker: {field: value}}."""
    result = {}
    batch_size = 40
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            df = blp.bdp(batch, fields)
            for row in df.rows():
                t, f, v = row[0], row[1], row[2]
                if t not in result: result[t] = {}
                try: result[t][f] = float(v)
                except: result[t][f] = v
        except Exception as e:
            print(f"  WARNING batch {i}: {e}")
    return result

def bdp_with_override(tickers, field, period):
    """Pull bdp with BEST_FPERIOD_OVERRIDE."""
    result = {}
    batch_size = 40
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            df = blp.bdp(batch, field, overrides=[('BEST_FPERIOD_OVERRIDE', period)])
            for row in df.rows():
                t, f, v = row[0], row[1], row[2]
                if t not in result: result[t] = {}
                try: result[t][f] = float(v)
                except: result[t][f] = v
        except Exception as e:
            print(f"  WARNING batch {i}: {e}")
    return result

def main():
    # Load source workbook twice: data_only for reading values, normal for writing
    wb_data = load_workbook(SRC, data_only=True)
    ws_data = wb_data.active
    wb = load_workbook(SRC)
    ws = wb.active

    # Extract tickers and their rows (from data_only version to get computed BBG tickers)
    tickers_info = []
    for row in range(1, ws_data.max_row + 1):
        ticker = ws_data.cell(row, 1).value
        bbg = ws_data.cell(row, 2).value
        if ticker and bbg and 'Equity' in str(bbg):
            tickers_info.append({'row': row, 'ticker': str(ticker), 'bbg': str(bbg)})

    all_bbg = list(set(t['bbg'] for t in tickers_info))
    print(f"Found {len(tickers_info)} ticker rows, {len(all_bbg)} unique tickers")

    # --- Pull data ---
    print("\n[1/2] Pulling prices, market cap, YTD change, balance sheet...")
    snap = bdp_dict(all_bbg, ['PX_LAST', 'CUR_MKT_CAP', 'CHG_PCT_YTD',
                               'NET_DEBT_TO_EBITDA', 'RETURN_ON_INV_CAPITAL',
                               'OPER_MARGIN', 'TRAIL_12M_EBITDA',
                               'TOTAL_EQUITY', 'BS_TOT_LIAB2', 'BS_LT_INVEST',
                               'SHORT_AND_LONG_TERM_DEBT', 'BS_CASH_NEAR_CASH_ITEM',
                               'TRAIL_12M_OPER_INC'])

    # Pull all estimate fields for 2024-2028 using absolute NNY overrides
    YEARS = ['24', '25', '26', '27', '28']
    FIELDS = ['BEST_EPS', 'BEST_SALES', 'BEST_EBIT']

    eps, rev, ebit = {}, {}, {}
    field_map = {'BEST_EPS': eps, 'BEST_SALES': rev, 'BEST_EBIT': ebit}
    key_map = {'BEST_EPS': 'EPS', 'BEST_SALES': 'REV', 'BEST_EBIT': 'EBIT'}

    for field in FIELDS:
        for yr in YEARS:
            period = f'{yr}Y'
            print(f"  [{key_map[field]}] {period}...")
            d = bdp_with_override(all_bbg, field, period)
            store = field_map[field]
            for t in d:
                if t not in store: store[t] = {}
                store[t][f'{key_map[field]}_20{yr}'] = d[t].get(field)

    # --- Update spreadsheet ---
    print("\nUpdating spreadsheet...")

    # Update headers
    # Row 1 (header group row)
    ws.cell(1, 6).value = 'PE'
    ws.cell(1, 10).value = '2026 estimates'
    ws.cell(1, 13).value = 'Growth: 2025-2028'
    ws.cell(1, 20).value = 'Ratio: 2026 PE vs'

    # Row 2 (sub-headers)
    ws.cell(2, 6).value = 2026
    ws.cell(2, 7).value = 2027
    ws.cell(2, 8).value = 2028
    ws.cell(2, 20).value = "25-'28 EPS gwth"

    # Update each ticker row
    for info in tickers_info:
        row = info['row']
        bbg = info['bbg']
        t = info['ticker']

        s = snap.get(bbg, {})
        e = eps.get(bbg, {})
        r = rev.get(bbg, {})
        eb = ebit.get(bbg, {})

        price = s.get('PX_LAST')
        mktcap = s.get('CUR_MKT_CAP')
        if mktcap: mktcap = mktcap / 1e9  # Convert to billions

        eps_26 = e.get('EPS_2026')
        eps_27 = e.get('EPS_2027')
        eps_28 = e.get('EPS_2028')

        rev_26 = r.get('REV_2026')
        ebit_26 = eb.get('EBIT_2026')

        # Col 4: Price
        if price: ws.cell(row, 5).value = price

        # Col 3: Mkt cap (millions)
        if mktcap: ws.cell(row, 4).value = mktcap

        # Col 5-7: PE 2026, 2027, 2028
        if price and eps_26 and eps_26 != 0:
            ws.cell(row, 6).value = price / eps_26
        if price and eps_27 and eps_27 != 0:
            ws.cell(row, 7).value = price / eps_27
        if price and eps_28 and eps_28 != 0:
            ws.cell(row, 8).value = price / eps_28

        # Col 8: Net leverage
        net_levg = s.get('NET_DEBT_TO_EBITDA')
        if net_levg: ws.cell(row, 9).value = net_levg

        # Col 9-11: 2026 estimates - Revenue (billions), Op margin, ROIC
        if rev_26: ws.cell(row, 10).value = rev_26 / 1000
        if rev_26 and ebit_26 and rev_26 != 0:
            ws.cell(row, 11).value = ebit_26 / rev_26  # Op margin = EBIT/Rev
        roic = s.get('RETURN_ON_INV_CAPITAL')
        if roic: ws.cell(row, 12).value = roic / 100

        # Col 12-14: Growth 2025-2028 (Rev, Op inc, EPS)
        rev_25 = r.get('REV_2025')
        rev_28 = r.get('REV_2028')
        ebit_25 = eb.get('EBIT_2025')
        ebit_28 = eb.get('EBIT_2028')
        eps_25 = e.get('EPS_2025')

        def cagr(start, end, years=3):
            if not start or not end or start <= 0 or end <= 0: return None
            return (end / start) ** (1/years) - 1

        val = cagr(rev_25, rev_28)
        if val is not None: ws.cell(row, 13).value = val
        val = cagr(ebit_25, ebit_28)
        if val is not None: ws.cell(row, 14).value = val
        val = cagr(eps_25, eps_28)
        if val is not None: ws.cell(row, 15).value = val

        # Col 16: YTD price change
        ytd = s.get('CHG_PCT_YTD')
        if ytd: ws.cell(row, 17).value = ytd / 100

        # Col 19: Ratio: 2026 PE vs 25-28 EPS growth (PEG ratio)
        try:
            pe_26_val = float(ws.cell(row, 6).value) if ws.cell(row, 6).value else None
            eps_gwth_val = float(ws.cell(row, 15).value) if ws.cell(row, 15).value else None
            if pe_26_val and eps_gwth_val and eps_gwth_val != 0:
                ws.cell(row, 20).value = pe_26_val / (eps_gwth_val * 100)
        except (TypeError, ValueError):
            pass

        # LTM data (cols 27-33)
        ltm_opinc = s.get('TRAIL_12M_OPER_INC')
        debt = s.get('SHORT_AND_LONG_TERM_DEBT')
        equity = s.get('TOTAL_EQUITY')
        cash = s.get('BS_CASH_NEAR_CASH_ITEM')
        lti = s.get('BS_LT_INVEST')

        if ltm_opinc: ws.cell(row, 28).value = ltm_opinc
        if debt: ws.cell(row, 29).value = debt
        if equity: ws.cell(row, 30).value = equity
        if cash: ws.cell(row, 31).value = cash
        if lti: ws.cell(row, 32).value = lti if lti else 0

        # Total capital = Debt + Equity
        if debt and equity:
            ws.cell(row, 33).value = debt + equity
        # ROIC from BBG
        if roic: ws.cell(row, 34).value = roic / 100

        # EPS estimates 2024-2028 (cols 35-39)
        for ci, yr in enumerate(['2024', '2025', '2026', '2027', '2028']):
            val = e.get(f'EPS_{yr}')
            if val: ws.cell(row, 36 + ci).value = val

        # Revenue estimates 2024-2028 (cols 41-45)
        for ci, yr in enumerate(['2024', '2025', '2026', '2027', '2028']):
            val = r.get(f'REV_{yr}')
            if val: ws.cell(row, 42 + ci).value = val

        # EBIT estimates 2024-2028 (cols 47-51)
        for ci, yr in enumerate(['2024', '2025', '2026', '2027', '2028']):
            val = eb.get(f'EBIT_{yr}')
            if val: ws.cell(row, 48 + ci).value = val

        # EV, Net Debt, Mkt cap (cols 53-55)
        if mktcap:
            ws.cell(row, 56).value = mktcap
            net_debt = (debt or 0) - (cash or 0)
            ws.cell(row, 55).value = net_debt
            ws.cell(row, 54).value = mktcap + net_debt

        # LTM EBITDA (col 56)
        ltm_ebitda = s.get('TRAIL_12M_EBITDA')
        if ltm_ebitda: ws.cell(row, 57).value = ltm_ebitda

    # --- Create BBG Formulas sheet ---
    print("Creating BBG Formulas sheet...")
    ws.title = "Data"
    fs = wb.create_sheet("BBG Formulas")

    # Headers
    fs.cell(1, 1).value = "Ticker"
    fs.cell(1, 2).value = "BBG Ticker"
    fs.cell(1, 3).value = "Field"
    fs.cell(1, 4).value = "Override"
    fs.cell(1, 5).value = "Description"
    for c in range(1, 6):
        fs.cell(1, c).font = Font(bold=True)

    frow = 2
    seen_bbg = set()
    for info in tickers_info:
        bbg = info['bbg']
        t = info['ticker']
        if bbg in seen_bbg: continue
        seen_bbg.add(bbg)

        formulas = [
            ("PX_LAST", "", "Last price"),
            ("CUR_MKT_CAP", "", "Market cap (raw)"),
            ("CHG_PCT_YTD", "", "YTD price change %"),
            ("NET_DEBT_TO_EBITDA", "", "Net debt / EBITDA"),
            ("RETURN_ON_INV_CAPITAL", "", "ROIC (LTM)"),
            ("TRAIL_12M_OPER_INC", "", "LTM operating income"),
            ("TRAIL_12M_EBITDA", "", "LTM EBITDA"),
            ("SHORT_AND_LONG_TERM_DEBT", "", "Total debt"),
            ("TOTAL_EQUITY", "", "Total equity"),
            ("BS_CASH_NEAR_CASH_ITEM", "", "Cash & equivalents"),
        ]
        for yr in ['24', '25', '26', '27', '28']:
            formulas.append(("BEST_EPS", f"{yr}Y", f"EPS estimate FY20{yr}"))
            formulas.append(("BEST_SALES", f"{yr}Y", f"Revenue estimate FY20{yr}"))
            formulas.append(("BEST_EBIT", f"{yr}Y", f"EBIT estimate FY20{yr}"))

        for field, override, desc in formulas:
            fs.cell(frow, 1).value = t
            fs.cell(frow, 2).value = bbg
            fs.cell(frow, 3).value = field
            fs.cell(frow, 4).value = override
            fs.cell(frow, 5).value = desc

            # BDH/BDP formula syntax (for reference)
            if override:
                fs.cell(frow, 6).value = f'=BDP("{bbg}","{field}","BEST_FPERIOD_OVERRIDE","{override}")'
            else:
                fs.cell(frow, 6).value = f'=BDP("{bbg}","{field}")'

            fs.cell(frow, 6).font = Font(color="0000FF")  # Blue for formulas
            frow += 1

    fs.cell(1, 6).value = "BDP Formula"
    fs.cell(1, 6).font = Font(bold=True)

    # Auto-width columns
    for col in range(1, 7):
        fs.column_dimensions[get_column_letter(col)].width = 25

    # Save
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    wb.save(OUT)
    print(f"\nSaved: {OUT}")

if __name__ == '__main__':
    main()
