"""Tests for the date-history pure helpers.

These don't touch Bloomberg — they exercise the calendar-quarter binning and
the window/sort logic. Run with:

    python -m pytest tests/test_earnings_date_history.py -v
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

# Importing pull_earnings imports xbbg.blp at module load; mock it first.
class _FakeBlp:
    def bdh(self, *a, **kw): raise RuntimeError("blp not available in tests")
    def bdp(self, *a, **kw): raise RuntimeError("blp not available in tests")
    def bds(self, *a, **kw): raise RuntimeError("blp not available in tests")

sys.modules.setdefault("xbbg", type("M", (), {"blp": _FakeBlp()})())
try:
    import bloomberg  # noqa: F401
except ImportError:
    sys.modules["bloomberg"] = type("M", (), {"USD_OVERRIDE_TICKERS": set()})()

from pull_earnings import _build_date_history, _calendar_quarter  # noqa: E402


# --- _calendar_quarter ---

def test_calendar_quarter_boundaries():
    assert _calendar_quarter(date(2025, 1, 1)) == "2025Q1"
    assert _calendar_quarter(date(2025, 3, 31)) == "2025Q1"
    assert _calendar_quarter(date(2025, 4, 1)) == "2025Q2"
    assert _calendar_quarter(date(2025, 6, 30)) == "2025Q2"
    assert _calendar_quarter(date(2025, 7, 1)) == "2025Q3"
    assert _calendar_quarter(date(2025, 9, 30)) == "2025Q3"
    assert _calendar_quarter(date(2025, 10, 1)) == "2025Q4"
    assert _calendar_quarter(date(2025, 12, 31)) == "2025Q4"


# --- _build_date_history ---

def test_build_filters_future_dates():
    today = date(2026, 6, 23)
    rows = ["2026-04-11", "2026-07-15"]  # second is after today
    out = _build_date_history(rows, today)
    assert [r["date"] for r in out] == ["2026-04-11"]


def test_build_filters_too_old_dates():
    today = date(2026, 6, 23)
    too_old = (today - timedelta(days=1200)).isoformat()
    in_window = (today - timedelta(days=1100)).isoformat()
    out = _build_date_history([too_old, in_window], today)
    assert [r["date"] for r in out] == [in_window]


def test_build_sorts_ascending_and_sets_cq():
    today = date(2026, 6, 23)
    out = _build_date_history(["2025-10-14", "2024-04-12", "2025-01-15"], today)
    assert [r["date"] for r in out] == ["2024-04-12", "2025-01-15", "2025-10-14"]
    assert [r["cq"] for r in out] == ["2024Q2", "2025Q1", "2025Q4"]


def test_build_skips_unparseable_and_trims_time():
    today = date(2026, 6, 23)
    out = _build_date_history(["not-a-date", "", "2025-04-11T00:00:00"], today)
    assert out == [{"date": "2025-04-11", "cq": "2025Q2"}]
