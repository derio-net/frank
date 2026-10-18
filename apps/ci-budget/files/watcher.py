"""ci-budget-watcher: GitHub-minutes budget watcher (spec 2026-10-18 section 4).

Runs as a CronJob (*/10) on stock python:3-alpine with PyYAML. All dates and
months are UTC. This module is split in three layers:

  1. pure decision functions (usage -> minutes, desired authority, backstop);
  2. an ordered two-forge apply driven through small client objects;
  3. state, notifications, heartbeat and the in-cluster clients.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------- layer 1

SKU_MULTIPLIER = {"actions linux": 1, "actions windows": 2, "actions macos": 10}
BACKSTOP_WINDOW = timedelta(minutes=30)
BACKSTOP_NEEDLE = "spending limit"


def _sku(item: dict) -> str:
    return " ".join(str(item.get("sku", "")).lower().replace("_", " ").split())


def _is_actions(item: dict) -> bool:
    return str(item.get("product", "")).lower() == "actions"


def _weighted(item: dict) -> float | None:
    """Included-minute weight of one usage item; None when it is not minutes."""
    sku = _sku(item)
    if sku in SKU_MULTIPLIER:
        return float(item.get("quantity", 0)) * SKU_MULTIPLIER[sku]
    if "storage" in sku:
        return None
    raise ValueError(f"unknown Actions SKU {item.get('sku')!r}: refusing to guess a multiplier")


def included_minutes_used(usage_items, exclude_repos=()) -> float:
    """Included-minute consumption: Linux x1, Windows x2, macOS x10.

    Only Actions SKUs count; an unknown Actions SKU raises. `exclude_repos`
    removes public repos (their minutes are free and never draw on the quota).
    """
    total = 0.0
    for it in usage_items:
        if not _is_actions(it) or it.get("repositoryName") in exclude_repos:
            continue
        wt = _weighted(it)
        if wt is not None:
            total += wt
    return total


def pinned_share(usage_items, preferred_repos, exclude_repos=()) -> float:
    """Share of the weighted minutes that can never fall back to Gitea.

    Pinned = every minute of a repo that is not github-preferred, plus macOS
    minutes of a github-preferred repo.
    """
    total = pinned = 0.0
    for it in usage_items:
        if not _is_actions(it) or it.get("repositoryName") in exclude_repos:
            continue
        wt = _weighted(it)
        if wt is None:
            continue
        total += wt
        if it.get("repositoryName") not in preferred_repos or _sku(it) == "actions macos":
            pinned += wt
    return pinned / total if total else 0.0


def desired_authority(pct, threshold, backstop_hit, month_stamp, now_month, pin):
    """Return (authority, stamp). `stamp` = write CI_BUDGET_MONTH=now_month.

    A pin wins over everything and never stamps.
    """
    if pin:
        return pin, False
    if pct >= threshold or backstop_hit:
        return "gitea", month_stamp != now_month
    if month_stamp == now_month:
        return "gitea", False
    return "github", False


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def backstop_hits(runs, annotations, now, handled_ids):
    """Failed runs from the last 30 min, this UTC month, not yet handled, whose
    annotations say 'spending limit' (case-insensitive).

    `annotations` maps run id -> list of check-run annotation dicts.
    """
    start = month_start(now)
    out = []
    for r in runs:
        if r.get("conclusion") != "failure" or r["id"] in handled_ids:
            continue
        created = parse_ts(r["created_at"])
        if created < start or now - created > BACKSTOP_WINDOW:
            continue
        if any(BACKSTOP_NEEDLE in str(a.get("message", "")).lower() for a in annotations.get(r["id"], [])):
            out.append(r)
    return out
