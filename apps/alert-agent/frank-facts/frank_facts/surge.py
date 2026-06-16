"""Surge detection — hour-of-day baseline computed in Python (stdlib-only port).

LogsQL has no `quantile_over_time`, so we issue 8 queries (current hour + 7
historical hours-of-day) and compute the median in Python.
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
    cross-check (GoatCounter) that the caller performs before an URGENT message.
    """
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    current = _hour_count(now)
    historical = [_hour_count(now - timedelta(days=d)) for d in range(1, 8)]
    baseline = int(median(historical)) or 1  # avoid divide-by-zero on dead-blog days
    ratio = current / baseline if current else 0.0
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
