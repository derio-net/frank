#!/usr/bin/env python3
"""Emit a Headscale API-key expiry heartbeat for Frank's Grafana alerts."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

MARKER = "headscale-api-key-expiry-check"


def parse_expiration(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate_keys(payload: dict, expected: set[str], warn_days: int, now: datetime) -> dict:
    keys = {item["prefix"]: item for item in payload.get("apiKeys", [])}
    missing = expected - keys.keys()
    if missing:
        return {"verdict": "error", "alert": True, "reason": "expected-key-missing"}

    days_left = [int((parse_expiration(keys[p]["expiration"]) - now).total_seconds() // 86400) for p in expected]
    minimum = min(days_left)
    return {
        "verdict": "warn" if minimum <= warn_days else "ok",
        "alert": minimum <= warn_days,
        "reason": "expiry-threshold" if minimum <= warn_days else "none",
        "min_days_left": minimum,
    }


def heartbeat(result: dict, checked: int) -> str:
    fields = [
        MARKER,
        f"verdict={result['verdict']}",
        f"alert={str(result['alert']).lower()}",
        f"reason={result['reason']}",
        f"checked={checked}",
    ]
    if "min_days_left" in result:
        fields.append(f"min_days_left={result['min_days_left']}")
    fields.append(f"ts={datetime.now(timezone.utc).isoformat()}")
    return " ".join(fields)


def main() -> int:
    expected = {p.strip() for p in os.environ["EXPECTED_PREFIXES"].split(",") if p.strip()}
    try:
        request = urllib.request.Request(
            os.environ["API_URL"],
            headers={"Authorization": f"Bearer {os.environ['API_KEY']}"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
        result = evaluate_keys(
            payload,
            expected,
            int(os.environ.get("WARN_DAYS", "30")),
            datetime.now(timezone.utc),
        )
    except Exception as exc:
        result = {"verdict": "error", "alert": True, "reason": type(exc).__name__.lower()}

    print(heartbeat(result, len(expected)), flush=True)
    return 1 if result["verdict"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
