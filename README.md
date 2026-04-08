# BBG

Bloomberg data extraction and earnings/guidance modeling tools. Builds consolidated comp sheets and tracks analyst estimates for equity analysis.

## Key Scripts

| Script | Description |
|--------|-------------|
| `build_comp_sheet.py` | Generates Excel workbooks with live Bloomberg formulas |
| `bloomberg.py` | Core Bloomberg API integration |
| `parse_guidance.py` | Parses company guidance data |
| `pull_estimates.py` | Fetches consensus analyst estimates |
| `pull_prices.py` | Retrieves pricing data |

## Usage

Requires an active Bloomberg Terminal session with `xbbg` API access.

```bash
python build_comp_sheet.py
python pull_estimates.py
```

## Tech Stack

- Python, xbbg (Bloomberg API)
- openpyxl for Excel generation
