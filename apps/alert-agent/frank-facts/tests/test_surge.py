"""Tests for surge.compute() — hour-of-day baseline + tier classification.

8 stats_query calls (current hour + 7 historical) go through the _http_get seam;
we drive them with a sequential side-effect list.
"""
from __future__ import annotations
import json
import itertools

import pytest

from frank_facts import facts, surge


def _seq_seam(counts):
    """Return an _http_get replacement that yields stats responses in order."""
    it = iter(counts)
    def seam(url, params=None, headers=None, timeout=15):
        return json.dumps({"data": {"result": [{"value": [0, str(next(it))]}]}})
    return seam


def test_tier_none_when_normal(monkeypatch):
    # current 30; baseline median of [25,30,35,28,32,30,29] = 30 → ratio 1 → None
    monkeypatch.setattr(facts, "_http_get", _seq_seam([30, 25, 30, 35, 28, 32, 30, 29]))
    r = surge.compute()
    assert r["current"] == 30 and r["baseline"] == 30 and r["tier"] is None


def test_tier_major_on_10x(monkeypatch):
    # current 600; baseline median ~30 → ratio 20 → Major (above abs floor)
    monkeypatch.setattr(facts, "_http_get", _seq_seam([600, 30, 30, 30, 30, 30, 30, 30]))
    r = surge.compute()
    assert r["tier"] == "Major" and r["ratio"] >= 10


def test_tier_notable_on_3x(monkeypatch):
    monkeypatch.setattr(facts, "_http_get", _seq_seam([120, 30, 40, 35, 30, 45, 40, 30]))
    r = surge.compute()
    assert r["tier"] == "Notable"


def test_abs_floor_suppresses_tiny_traffic(monkeypatch):
    """Below SURGE_ABS_FLOOR, no tier even at a huge ratio (baseline-of-1 artifact)."""
    monkeypatch.setenv("SURGE_ABS_FLOOR", "50")
    monkeypatch.setattr(facts, "_http_get", _seq_seam([20, 0, 0, 0, 0, 0, 0, 0]))
    r = surge.compute()
    assert r["current"] == 20 and r["tier"] is None  # 20 < 50 floor
