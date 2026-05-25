"""Surge detection — hour-of-day baseline computed in Python.

LogsQL has no `quantile_over_time`, so we issue 8 queries (current hour +
7 historical hours-of-day) and compute the median in Python. Cheap at our
volume (~8 queries, total ~50ms).
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from statistics import median

from . import facts


def _hour_count(when: datetime) -> int:
    """Probe-free blog edge request count in the 1h window ending at `when`."""
    start = (when - timedelta(hours=1)).isoformat()
    end = when.isoformat()
    query = f'_time:[{start},{end}] {facts.edge_filter(host="blog.derio.net")} | stats count() as c'
    return facts._logsql_count(query)


def compute() -> dict:
    """Return {window_end, current, baseline, ratio, tier}.

    tier ∈ {None, "Notable", "Major"} — Major still requires a visitor-side
    cross-check that the caller (api.py /surge-check) performs against
    GoatCounter before sending an URGENT message.
    """
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current = _hour_count(now)
    historical = [_hour_count(now - timedelta(days=d)) for d in range(1, 8)]
    baseline = int(median(historical)) or 1  # avoid divide-by-zero on dead-blog days
    ratio = current / baseline if current else 0.0
    # Absolute floor: a baseline forced to 1 on a quiet hour must not manufacture
    # a high ratio from a trickle of requests. No tier below the floor.
    abs_floor = int(os.environ.get("SURGE_ABS_FLOOR", "50"))
    tier: str | None = None
    if current < abs_floor:
        tier = None
    elif ratio >= 10:
        tier = "Major"
    elif ratio >= 3:
        tier = "Notable"
    return {
        "window_end": now.isoformat(),
        "current": current,
        "baseline": baseline,
        "ratio": ratio,
        "tier": tier,
    }
