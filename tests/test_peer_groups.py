"""Tests for the peer-group config loader in pull_earnings.

These don't touch Bloomberg — they exercise `_load_peer_tickers`, which reads
config/peer_groups.json and returns a flat, de-duplicated, uppercased list of
peer tickers. The key property under test: a missing or malformed config must
degrade gracefully to an empty list so the pull proceeds with PORTFOLIO +
WATCHLIST only, never crashing. Run with:

    python -m pytest tests/test_peer_groups.py -v
"""
from __future__ import annotations

import json
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

import pull_earnings  # noqa: E402
from pull_earnings import _load_peer_tickers  # noqa: E402


def _point_config_at(monkeypatch, tmp_path, payload):
    """Write `payload` (a str, already-serialized) to a temp config file and
    point the loader's module-level PEER_GROUPS_PATH at it."""
    cfg = tmp_path / "peer_groups.json"
    cfg.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(pull_earnings, "PEER_GROUPS_PATH", str(cfg))


def test_valid_config_returns_tickers_and_skips_comment(monkeypatch, tmp_path):
    _point_config_at(monkeypatch, tmp_path, json.dumps(
        {"hospitals": ["THC", "UHS"], "_comment": "some note"}))
    assert _load_peer_tickers() == ["THC", "UHS"]


def test_non_dict_null_config_returns_empty(monkeypatch, tmp_path):
    # Regression for the Critical bug: valid JSON that is `null` must not crash.
    _point_config_at(monkeypatch, tmp_path, json.dumps(None))
    assert _load_peer_tickers() == []


def test_non_dict_list_config_returns_empty(monkeypatch, tmp_path):
    # Regression for the Critical bug: valid JSON that is a list must not crash.
    _point_config_at(monkeypatch, tmp_path, json.dumps(["THC", "UHS"]))
    assert _load_peer_tickers() == []


def test_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pull_earnings, "PEER_GROUPS_PATH", str(tmp_path / "does_not_exist.json"))
    assert _load_peer_tickers() == []


def test_lowercase_tickers_come_back_uppercased(monkeypatch, tmp_path):
    _point_config_at(monkeypatch, tmp_path, json.dumps({"hospitals": ["thc", "uhs"]}))
    assert _load_peer_tickers() == ["THC", "UHS"]
