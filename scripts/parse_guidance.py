"""Parse guidance data from Call-extraction project for the earnings dashboard.

Reads the most recent guidance markdown file for each ticker in the
Call-extraction project, extracts quarterly and annual guidance ranges,
and writes a guidance_overrides.json file consumed by pull_earnings.py.
"""

import json
import os
import re
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CALL_EXTRACTION_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "Call-extraction", "companies")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "guidance_overrides.json")
ACTUALS_PATH = os.path.join(SCRIPT_DIR, "actuals_overrides.json")

# Tickers to extract guidance for (portfolio + watchlist)
TICKERS = [
    "HCA", "UNH", "TSM", "AVGO", "NVDA", "META", "AMZN", "JPM", "APO", "PGR",
    "CVNA", "APP", "VEEV", "FICO", "GOOG", "MU", "HOOD", "TDG", "GE", "LRCX",
    "DASH", "UBER", "LLY", "MSFT", "V",
]


def _parse_dollar_value(text):
    """Parse a dollar value string into a number (in millions).

    Handles: $173.5B, $19.1B, $1.745B, $5.0B, $836M, $7.5B, ~$200B
    Returns value in millions.
    """
    text = text.strip().replace(",", "").replace("~", "").replace("$", "")
    m = re.match(r'([\d.]+)\s*(B|b|billion|M|m|million|T|t|trillion)?', text)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "").upper()
    if unit.startswith("B"):
        return val * 1000  # billions -> millions
    elif unit.startswith("T"):
        return val * 1000000  # trillions -> millions
    elif unit.startswith("M"):
        return val  # already millions
    else:
        # No unit — could be raw number. If > 1000, likely millions already.
        # If < 100, likely per-share (EPS).
        return val


def _parse_eps_value(text):
    """Parse an EPS value. Returns float."""
    text = text.strip().replace(",", "").replace("~", "").replace("$", "")
    m = re.match(r'([\d.]+)', text)
    if not m:
        return None
    return float(m.group(1))


def _parse_percent_value(text):
    """Parse a percentage value. Returns float."""
    text = text.strip().replace("~", "").replace("%", "")
    m = re.match(r'([\d.]+)', text)
    if not m:
        return None
    return float(m.group(1))


def _extract_range(line, parse_fn):
    """Extract a low-high range from a guidance line.

    Handles patterns like:
    - $173.5B to $178.5B
    - $173.5B--$178.5B
    - $173.5B–$178.5B
    - $34.6B–$35.8B
    - ~$19.1B (single value)
    - $7.1B, +/- $400M
    - 63%–65%
    - $78.0B, +/- 2%

    Returns (low, high) or None.
    """
    # Pattern: X to/--/– Y (with optional $, ~, %)
    m = re.search(r'[\$~]*([\d.,]+\s*[BMT%]?)\s*(?:to|--|–|—)\s*[\$~]*([\d.,]+\s*[BMT%]?)', line, re.IGNORECASE)
    if m:
        low = parse_fn(m.group(1))
        high = parse_fn(m.group(2))
        if low is not None and high is not None:
            return (low, high)

    # Pattern: X, +/- Y (dollar amount)
    m = re.search(r'[\$~]*([\d.,]+\s*[BMT]?),?\s*\+/-\s*[\$~]*([\d.,]+\s*[BMT]?)', line, re.IGNORECASE)
    if m:
        mid = parse_fn(m.group(1))
        delta = parse_fn(m.group(2))
        if mid is not None and delta is not None:
            return (mid - delta, mid + delta)

    # Pattern: X%, +/- N bps (margin with basis point delta)
    m = re.search(r'([\d.]+)%,?\s*\+/-\s*([\d.]+)\s*bps', line, re.IGNORECASE)
    if m:
        mid = float(m.group(1))
        delta_bps = float(m.group(2)) / 100  # bps to percentage points
        return (mid - delta_bps, mid + delta_bps)

    # Pattern: X, +/- N% (percentage of midpoint)
    m = re.search(r'[\$~]*([\d.,]+\s*[BMT]?),?\s*\+/-\s*([\d.]+)%', line, re.IGNORECASE)
    if m:
        mid = parse_fn(m.group(1))
        pct = float(m.group(2)) / 100
        if mid is not None:
            return (mid * (1 - pct), mid * (1 + pct))

    # Single value with ~
    m = re.search(r'~\s*[\$]*([\d.,]+\s*[BMT]?)', line, re.IGNORECASE)
    if m:
        val = parse_fn(m.group(1))
        if val is not None:
            return (val, val)

    return None


def _find_quarterly_guidance_section(content):
    """Find the 'Quarterly Guidance' section and return its lines.

    Matches patterns like:
    - ## Quarterly Guidance (Q1 2026)
    - ## Q1 FY2026 Guidance (Oct–Dec 2025 Quarter)
    - ## FQ1 2026 Guidance
    """
    lines = content.split("\n")
    in_section = False
    section_lines = []
    for line in lines:
        if re.match(r'^##\s+(?:Quarterly Guidance|(?:F?Q\d)\s+(?:FY)?\d{4}\s+Guidance)', line, re.IGNORECASE):
            in_section = True
            continue
        elif re.match(r'^##\s+', line) and in_section:
            break  # Next section
        elif in_section:
            section_lines.append(line)
    return section_lines


def _find_annual_guidance_section(content):
    """Find the 'Full Year Guidance' section and return its lines."""
    lines = content.split("\n")
    in_section = False
    section_lines = []
    for line in lines:
        if re.match(r'^##\s+Full Year.*(?:Guidance|Outlook)', line, re.IGNORECASE):
            in_section = True
            continue
        elif re.match(r'^##\s+', line) and in_section:
            break
        elif in_section:
            section_lines.append(line)
    return section_lines


def _classify_metric(label):
    """Classify a metric label into our standard names. Returns (name, parse_fn) or None."""
    label_lower = label.lower()

    if any(x in label_lower for x in ["eps", "earnings per share", "non-gaap eps", "non-gaap diluted eps"]):
        return ("EPS", _parse_eps_value)
    if any(x in label_lower for x in ["net sales", "total revenue", "revenue"]):
        # Avoid matching "revenue growth" which is a percentage
        if "growth" in label_lower or "cagr" in label_lower:
            return None
        return ("Revenue", _parse_dollar_value)
    if "adjusted ebitda" in label_lower or label_lower.startswith("ebitda"):
        if "margin" in label_lower:
            return ("EBITDA Margin", _parse_percent_value)
        return ("EBITDA", _parse_dollar_value)
    if "gross margin" in label_lower or "non-gaap gross margin" in label_lower:
        return ("Gross Margin", _parse_percent_value)
    if "operating margin" in label_lower:
        return ("Op. Margin", _parse_percent_value)
    if "operating income" in label_lower:
        if "margin" in label_lower:
            return ("Op. Margin", _parse_percent_value)
        return ("Op. Income", _parse_dollar_value)
    if "capex" in label_lower or "capital expenditure" in label_lower:
        return ("Capex", _parse_dollar_value)
    if "net interest income" in label_lower or label_lower == "nii":
        return ("NII", _parse_dollar_value)

    return None


def _extract_metrics_from_lines(lines):
    """Extract guidance metrics from a list of markdown lines.

    Returns {metric_name: {"low": float, "high": float}}.
    """
    result = {}
    for line in lines:
        # Match lines like: - **Label:** value
        m = re.match(r'^-\s+\*\*([^*]+)\*\*:?\s*(.*)', line)
        if not m:
            continue
        label = m.group(1).strip().rstrip(":")
        value_text = m.group(2).strip()

        classified = _classify_metric(label)
        if not classified:
            continue
        metric_name, parse_fn = classified

        # Skip if we already have this metric (first occurrence wins)
        if metric_name in result:
            continue

        rng = _extract_range(value_text, parse_fn)
        if rng:
            result[metric_name] = {"low": rng[0], "high": rng[1]}

    return result


def _find_actuals_section(content):
    """Find the 'Actuals (Reported)' section and return its lines.

    Matches patterns like:
    - ## Q4 2025 Actuals (Reported)
    - ## Q4 FY2026 Actuals (Reported)
    """
    lines = content.split("\n")
    in_section = False
    section_lines = []
    for line in lines:
        if re.match(r'^##\s+(?:F?Q\d)\s+(?:FY)?\d{4}\s+Actuals', line, re.IGNORECASE):
            in_section = True
            continue
        elif re.match(r'^##\s+', line) and in_section:
            break
        elif in_section:
            section_lines.append(line)
    return section_lines


def _extract_single_values_from_lines(lines):
    """Extract single metric values (not ranges) from markdown lines.

    For actuals, we want the first number in the value text.
    Returns {metric_name: float_value}.
    """
    result = {}
    for line in lines:
        m = re.match(r'^-\s+\*\*([^*]+)\*\*:?\s*(.*)', line)
        if not m:
            continue
        label = m.group(1).strip().rstrip(":")
        value_text = m.group(2).strip()

        classified = _classify_metric(label)
        if not classified:
            continue
        metric_name, parse_fn = classified

        if metric_name in result:
            continue

        # Extract the first number from the value text
        val = parse_fn(value_text)
        if val is not None:
            result[metric_name] = val

    return result


def _extract_quarter_id(content):
    """Extract the reporting quarter ID from the header.

    Looks for: **Reporting Quarter:** Q4 2025
    Or the actuals section header: ## Q4 2025 Actuals
    Returns string like 'Q4 2025' or None.
    """
    # Try header first
    m = re.search(r'\*\*Reporting Quarter:\*\*\s*(?:Fiscal\s+)?([FQ]\d\s+(?:FY)?\d{4})', content)
    if m:
        return m.group(1).strip()
    # Try actuals section header
    m = re.search(r'^##\s+(F?Q\d\s+(?:FY)?\d{4})\s+Actuals', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None


def extract_actuals(ticker):
    """Extract reported actuals from ALL Call-extraction guidance files for a ticker.

    Returns list of {"quarter": "Q4'25", "eps": float, "revenue": float, ...}.
    """
    ticker_dir = os.path.join(CALL_EXTRACTION_DIR, ticker, "guidance")
    if not os.path.isdir(ticker_dir):
        return []

    files = sorted(Path(ticker_dir).glob("*guidance.md"))
    results = []

    for f in files:
        content = f.read_text(encoding="utf-8")
        actuals_lines = _find_actuals_section(content)
        if not actuals_lines:
            continue

        values = _extract_single_values_from_lines(actuals_lines)
        if not values:
            continue

        # Get quarter ID
        quarter_id = _extract_quarter_id(content)
        if not quarter_id:
            # Try to derive from filename: Q4_2025_guidance.md -> Q4 2025
            stem = f.stem.replace("_guidance", "")
            parts = stem.split("_")
            if len(parts) >= 2:
                quarter_id = f"{parts[0]} {parts[1]}"

        if quarter_id:
            # Normalize: "Q4 2025" -> "Q4'25", "FQ4 2025" -> "FQ4'25"
            m2 = re.match(r'(F?Q\d)\s+(?:FY)?(\d{4})', quarter_id)
            if m2:
                q = m2.group(1)
                yr = m2.group(2)[2:]  # "2025" -> "25"
                quarter_label = f"{q}'{yr}"
            else:
                quarter_label = quarter_id
        else:
            quarter_label = f.stem

        results.append({
            "quarter": quarter_label,
            "source_file": f.name,
            **{k: v for k, v in values.items()},
        })

    return results


def extract_guidance(ticker):
    """Extract guidance from the most recent Call-extraction file for a ticker.

    Returns {"quarterly": {metric: {low, high}}, "annual": {metric: {low, high}}} or None.
    """
    ticker_dir = os.path.join(CALL_EXTRACTION_DIR, ticker, "guidance")
    if not os.path.isdir(ticker_dir):
        return None

    # Find most recent guidance file
    files = sorted(Path(ticker_dir).glob("*guidance.md"))
    if not files:
        return None

    latest = files[-1]
    content = latest.read_text(encoding="utf-8")

    quarterly_lines = _find_quarterly_guidance_section(content)
    annual_lines = _find_annual_guidance_section(content)

    quarterly = _extract_metrics_from_lines(quarterly_lines)
    annual = _extract_metrics_from_lines(annual_lines)

    if not quarterly and not annual:
        return None

    return {
        "source_file": str(latest.name),
        "quarterly": quarterly,
        "annual": annual,
    }


def main():
    print("Parsing guidance from Call-extraction project...\n")
    overrides = {}
    all_actuals = {}

    for ticker in TICKERS:
        # Guidance
        result = extract_guidance(ticker)
        if result:
            overrides[ticker] = result
            q_metrics = list(result["quarterly"].keys())
            a_metrics = list(result["annual"].keys())
            print(f"  {ticker}: quarterly={q_metrics}, annual={a_metrics} (from {result['source_file']})")
        else:
            print(f"  {ticker}: (no guidance found)")

        # Actuals
        actuals = extract_actuals(ticker)
        if actuals:
            all_actuals[ticker] = actuals
            for a in actuals:
                metrics = [k for k in a if k not in ("quarter", "source_file")]
                print(f"    actuals {a['quarter']}: {metrics}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(overrides, f, indent=2)
    print(f"\nSaved: {OUTPUT_PATH} ({len(overrides)} companies)")

    with open(ACTUALS_PATH, "w") as f:
        json.dump(all_actuals, f, indent=2)
    print(f"Saved: {ACTUALS_PATH} ({len(all_actuals)} companies)")


if __name__ == "__main__":
    main()
