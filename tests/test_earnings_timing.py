"""Tests for AMC/BMO classification + the d1/w1 anchor selection.

These tests don't touch Bloomberg — they exercise the pure helpers that
decide whether an earnings entry is an AMC or BMO reporter and how the
price-reaction window should be anchored. Run with:

    python -m pytest tests/test_earnings_timing.py -v
"""
from __future__ import annotations

import os
import sys

# Allow importing from BBG/scripts as the script is when called via cron.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

# Importing pull_earnings has a side effect: it imports xbbg.blp at module
# load time, which can fail without a Bloomberg desktop. Mock xbbg before
# importing.
class _FakeBlp:
    def bdh(self, *a, **kw): raise RuntimeError("blp not available in tests")
    def bdp(self, *a, **kw): raise RuntimeError("blp not available in tests")
    def bds(self, *a, **kw): raise RuntimeError("blp not available in tests")

sys.modules.setdefault("xbbg", type("M", (), {"blp": _FakeBlp()})())
# bloomberg.py imports a constant USD_OVERRIDE_TICKERS — if absent, stub it.
try:
    import bloomberg  # noqa: F401
except ImportError:
    sys.modules["bloomberg"] = type("M", (), {"USD_OVERRIDE_TICKERS": set()})()

from pull_earnings import (  # noqa: E402
    _classify_amc_bmo_heuristic,
    _classify_timing,
    _reaction_anchors,
    _resolve_timing,
    _TIMING_OVERRIDES,
    _timing_from_expected_report_time,
)


# ---------------------------------------------------------------------------
# _classify_amc_bmo_heuristic
# ---------------------------------------------------------------------------

def test_heuristic_picks_amc_when_next_day_move_dwarfs_same_day():
    """APP scenario: Wed close -1.94% (pre-print drift), Thu close +6.5% (reaction)."""
    t_minus_1 = 530.0   # Tuesday close
    t_close = 520.0     # Wednesday close (pre-print drift)
    t1_close = 553.0    # Thursday close (post-print reaction +6.3%)
    assert _classify_amc_bmo_heuristic(t_minus_1, t_close, t1_close) == "AMC"


def test_heuristic_picks_bmo_when_same_day_move_dominates():
    """HCA scenario: Thu close -8.8% on BMO print, Friday small drift."""
    t_minus_1 = 480.0   # Wed close
    t_close = 437.78    # Thu close (post-BMO print, -8.8%)
    t1_close = 439.0    # Fri close (small drift)
    assert _classify_amc_bmo_heuristic(t_minus_1, t_close, t1_close) == "BMO"


def test_heuristic_defaults_to_bmo_when_both_moves_are_small():
    """Quiet quarter: neither day has a big move."""
    assert _classify_amc_bmo_heuristic(100.0, 100.5, 100.8) == "BMO"


def test_heuristic_defaults_to_bmo_when_amc_below_abs_threshold():
    """Next-day move is bigger ratio-wise but absolutely tiny."""
    # +0.1% vs +0.05% — ratio is 2x but absolute is below the 1% threshold.
    assert _classify_amc_bmo_heuristic(100.0, 100.05, 100.15) == "BMO"


def test_heuristic_handles_missing_prices():
    assert _classify_amc_bmo_heuristic(None, 100.0, 105.0) == "BMO"
    assert _classify_amc_bmo_heuristic(100.0, None, 105.0) == "BMO"
    assert _classify_amc_bmo_heuristic(100.0, 100.0, None) == "BMO"


def test_heuristic_handles_zero_division():
    assert _classify_amc_bmo_heuristic(0.0, 100.0, 105.0) == "BMO"
    assert _classify_amc_bmo_heuristic(100.0, 0.0, 105.0) == "BMO"


# ---------------------------------------------------------------------------
# _classify_timing — override + heuristic
# ---------------------------------------------------------------------------

def test_override_wins_over_heuristic():
    """Even when heuristic would say BMO, an AMC override forces AMC."""
    # Skip if APP isn't in the override file (would mean defaults changed).
    if "APP" not in _TIMING_OVERRIDES:
        return
    # Boring price action (small moves both days) — heuristic would say BMO.
    assert _classify_timing("APP", 100.0, 100.2, 100.4) == "AMC"


def test_unknown_ticker_falls_to_heuristic():
    """A ticker with no override and big next-day move → AMC via heuristic."""
    # Use a ticker very unlikely to be in the override file.
    assert _classify_timing("FAKETICKER_XYZ", 100.0, 99.0, 110.0) == "AMC"


def test_bmo_override_resists_amc_heuristic():
    """An explicit BMO override beats the heuristic even when prices look AMC."""
    if "HCA" not in _TIMING_OVERRIDES:
        return
    # HCA is BMO in the override file. Even if prices look AMC-shaped:
    assert _classify_timing("HCA", 100.0, 99.0, 115.0) == "BMO"


def test_app_override_yields_amc():
    """APP is the canonical AMC case in the override file."""
    if "APP" not in _TIMING_OVERRIDES:
        return
    assert _classify_timing("APP", 530.0, 520.0, 553.0) == "AMC"


def test_thc_override_stays_amc_before_t1_close_exists():
    """THC reports after the close; a missing next-day close must not relabel it BMO."""
    assert _TIMING_OVERRIDES.get("THC") == "AMC"
    assert _classify_timing("THC", 100.0, 101.9, None) == "AMC"


def test_bloomberg_expected_report_time_labels_and_clock_times():
    assert _timing_from_expected_report_time("Aft-mkt") == "AMC"
    assert _timing_from_expected_report_time("Bef-mkt") == "BMO"
    assert _timing_from_expected_report_time("16:05") == "AMC"
    assert _timing_from_expected_report_time("06:45") == "BMO"
    assert _timing_from_expected_report_time("3:59 PM") == "BMO"
    assert _timing_from_expected_report_time("4:00 PM") == "AMC"
    assert _timing_from_expected_report_time(None) is None
    assert _timing_from_expected_report_time("TBD") is None


def test_date_matched_bloomberg_time_beats_price_action():
    timing, source = _resolve_timing(
        "NO_OVERRIDE_XYZ",
        100.0,
        102.0,
        102.1,
        expected_report_time="16:05",
    )
    assert timing == "AMC"
    assert source == "bloomberg_expected_report_time"


def test_unknown_timing_remains_pending_until_next_close_exists():
    timing, source = _resolve_timing(
        "NO_OVERRIDE_XYZ",
        100.0,
        102.0,
        None,
    )
    assert timing is None
    assert source == "pending_next_close"


def test_prior_event_timing_survives_bloomberg_schedule_roll_forward():
    timing, source = _resolve_timing(
        "NO_OVERRIDE_XYZ",
        100.0,
        102.0,
        103.0,
        prior_event_timing="AMC",
    )
    assert timing == "AMC"
    assert source == "prior_event"


def test_reaction_anchor_dates_follow_event_timing():
    t_minus_1 = ("2026-07-22", 100.0)
    t_close = ("2026-07-23", 102.0)
    t1_close = ("2026-07-24", 105.0)
    assert _reaction_anchors("AMC", t_minus_1, t_close, t1_close) == (
        t_close,
        t1_close,
    )
    assert _reaction_anchors("BMO", t_minus_1, t_close, t1_close) == (
        t_minus_1,
        t_close,
    )
    assert _reaction_anchors(None, t_minus_1, t_close, t1_close) == (
        (None, None),
        (None, None),
    )


def test_weekend_amc_uses_prior_and_first_subsequent_trading_closes():
    friday = ("2026-07-24", 100.0)
    monday = ("2026-07-27", 105.0)
    tuesday = ("2026-07-28", 106.0)
    assert _reaction_anchors(
        "AMC",
        friday,
        monday,
        tuesday,
        event_date="2026-07-26",
    ) == (friday, monday)
