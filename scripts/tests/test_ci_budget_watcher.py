"""Guard: the ci-budget watcher (spec 2026-10-18 section 4).

Part 1: the pure decision core.
Part 2: the ordered two-forge apply, against fake clients.
Part 3: state, notifications and the heartbeat line.
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FILES = REPO_ROOT / "apps/ci-budget/files"
FIX = Path(__file__).parent / "fixtures/ci_budget"


def _load(name):
    sys.path.insert(0, str(FILES))
    try:
        spec = importlib.util.spec_from_file_location(name, FILES / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(FILES))
    return mod


w = _load("watcher")


def _fx(name):
    return json.loads((FIX / name).read_text())


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


# ---------------------------------------------------------------- part 1


def test_included_minutes_weights_skus():
    items = _fx("usage.json")["usageItems"]
    # Linux 100*1 + Windows 50*2 + macOS 20*10 + Linux 40*1 (storage and
    # copilot are not minutes)
    assert w.included_minutes_used(items) == 440


def test_included_minutes_excludes_public_repos():
    items = _fx("usage.json")["usageItems"]
    assert w.included_minutes_used(items, exclude_repos={"frank-public-thing"}) == 400


def test_included_minutes_unknown_actions_sku_raises():
    items = _fx("usage_unknown_sku.json")["usageItems"]
    with pytest.raises(ValueError, match="ARM Linux"):
        w.included_minutes_used(items)


def test_included_minutes_sku_case_and_separator_insensitive():
    items = [
        {"product": "Actions", "sku": "actions_macos", "quantity": 2, "repositoryName": "r"},
        {"product": "actions", "sku": "ACTIONS WINDOWS", "quantity": 1, "repositoryName": "r"},
    ]
    assert w.included_minutes_used(items) == 22


def test_pinned_share_counts_non_preferred_repos_and_macos():
    items = _fx("usage.json")["usageItems"]
    ex = {"frank-public-thing"}
    # preferred = all three: only herdr's macOS (200 of 400) is pinned
    assert w.pinned_share(items, {"willikins", "vibe-kanban", "herdr-vertical-tabs"}, ex) == 0.5
    # only willikins preferred: vibe 100 + herdr 200 pinned of 400
    assert w.pinned_share(items, {"willikins"}, ex) == 0.75
    assert w.pinned_share([], {"willikins"}) == 0.0


@pytest.mark.parametrize(
    "kw,expect",
    [
        (dict(pct=10), ("github", False)),
        (dict(pct=84.9), ("github", False)),
        (dict(pct=85), ("gitea", True)),
        (dict(pct=99), ("gitea", True)),
        (dict(pct=10, month_stamp="2026-10"), ("gitea", False)),
        (dict(pct=10, month_stamp="2026-09"), ("github", False)),
        (dict(pct=90, month_stamp="2026-10"), ("gitea", False)),
        (dict(pct=90, month_stamp="2026-09"), ("gitea", True)),
        (dict(pct=10, backstop_hit=True), ("gitea", True)),
        (dict(pct=95, pin="github"), ("github", False)),
        (dict(pct=5, pin="gitea"), ("gitea", False)),
        (dict(pct=5, month_stamp="2026-10", pin="github"), ("github", False)),
        (dict(pct=5, backstop_hit=True, pin="github"), ("github", False)),
    ],
)
def test_desired_authority(kw, expect):
    base = dict(pct=0, threshold=85, backstop_hit=False, month_stamp=None, now_month="2026-10", pin=None)
    base.update(kw)
    assert tuple(w.desired_authority(**base)) == expect


NOW = utc(2026, 10, 18, 12, 0)


def _runs():
    return _fx("runs.json")["workflow_runs"]


def _ann():
    a = _fx("annotations.json")
    return {9001: a["spend"], 9002: a["ordinary"], 9003: a["spend"], 9004: a["spend"]}


def test_backstop_hits_selects_recent_spending_limit_failures():
    hits = w.backstop_hits(_runs(), _ann(), NOW, set())
    # 9001: recent + matches (case-insensitive 'Spending Limit').
    # 9002: older than 30 min and not a spending message.
    # 9003: before the UTC month start. 9004: not a failure.
    assert [r["id"] for r in hits] == [9001]


def test_backstop_hits_skips_handled_ids():
    assert w.backstop_hits(_runs(), _ann(), NOW, {9001}) == []


def test_backstop_hits_ignores_runs_older_than_30_minutes():
    assert w.backstop_hits(_runs(), _ann(), utc(2026, 10, 18, 12, 40), set()) == []


def test_backstop_hits_month_start_guard():
    # one minute into the new month: the last-month failure never counts
    runs = [dict(_runs()[2], created_at="2026-09-30T23:59:00Z")]
    assert w.backstop_hits(runs, _ann(), utc(2026, 10, 1, 0, 1), set()) == []
    # a run created at/after the month start does
    runs = [dict(_runs()[2], created_at="2026-10-01T00:00:00Z")]
    assert [r["id"] for r in w.backstop_hits(runs, _ann(), utc(2026, 10, 1, 0, 10), set())] == [9003]
