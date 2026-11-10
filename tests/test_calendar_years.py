"""Tests for the calendar-year roll in pull_estimates.

These don't touch Bloomberg. Run with:

    python -m pytest tests/test_calendar_years.py -v
"""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

# Importing pull_estimates imports xbbg.blp at module load; mock it first.
class _FakeBlp:
    def bdh(self, *a, **kw): raise RuntimeError("blp not available in tests")
    def bdp(self, *a, **kw): raise RuntimeError("blp not available in tests")
    def bds(self, *a, **kw): raise RuntimeError("blp not available in tests")

sys.modules.setdefault("xbbg", type("M", (), {"blp": _FakeBlp()})())
try:
    import bloomberg  # noqa: F401
except ImportError:
    sys.modules["bloomberg"] = type("M", (), {"USD_OVERRIDE_TICKERS": set()})()

from pull_estimates import calendar_years  # noqa: E402


def test_calendar_years_covers_fy2_after_roll():
    assert calendar_years(date(2026, 11, 6)) == [2025, 2026, 2027, 2028]
    assert calendar_years(date(2027, 3, 5)) == [2025, 2026, 2027, 2028, 2029]
