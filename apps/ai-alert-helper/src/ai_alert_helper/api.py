"""FastAPI entrypoints.

- GET  /healthz       — liveness/readiness
- POST /digest        — daily summary (CronJob trigger)
- POST /alert         — Grafana contact-point webhook
- POST /surge-check   — 15-min CronJob computes baseline + maybe sends
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request

from . import ai_adapter, facts, surge, telegram

app = FastAPI(title="ai-alert-helper", version="0.1.5")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/digest")
def digest(dry_run: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    until = since + timedelta(days=1)          # traffic = prior calendar day
    sheet = facts.build_for_digest(since, until, now)  # security runs to now
    if dry_run:
        return {"facts": sheet, "narrative": None}
    narrative = ai_adapter.summarize(sheet)
    telegram.send(f"📊 Yesterday on the Frank blog\n\n{narrative}")
    return {"facts": sheet, "narrative": narrative}


@app.post("/alert")
async def alert(request: Request) -> dict:
    """Grafana webhook payload — flat alerts array."""
    payload: dict[str, Any] = await request.json()
    sent = []
    for a in payload.get("alerts", []):
        labels = a.get("labels", {})
        sheet = facts.build_for_alert(labels)
        narrative = ai_adapter.investigate(labels, sheet)
        urgent = labels.get("severity") == "critical"
        telegram.send(f"🚨 {labels.get('alertname', 'Alert')}\n\n{narrative}", urgent=urgent)
        sent.append({"alertname": labels.get("alertname"), "narrative": narrative})
    return {"processed": sent}


@app.post("/surge-check")
def surge_check() -> dict:
    s = surge.compute()
    if s["tier"] is None:
        return {"triggered": False, **s}
    # Visitor-side cross-check: an URGENT (Major) page requires real human
    # pageviews (GoatCounter). Fail OPEN — if GoatCounter is unreachable we
    # still page, annotated, rather than suppress a possibly-real surge.
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=1)
    visitors = facts.surge_visitor_pageviews(start, now)
    visitor_floor = int(os.environ.get("SURGE_VISITOR_FLOOR", "10"))
    if s["tier"] == "Major" and visitors is not None and visitors < visitor_floor:
        s["tier"] = "Notable"  # edge surge with no visitor confirmation — likely automated
    urgent = s["tier"] == "Major"

    surge_facts = facts.build_for_surge(start, now)
    surge_facts.update(s)
    surge_facts["visitor_pageviews"] = visitors
    surge_facts["visitor_data_available"] = visitors is not None
    narrative = ai_adapter.investigate(
        {"alertname": f"BlogTrafficSurge{s['tier']}"},
        surge_facts,
    )
    note = "" if visitors is not None else "  (visitor data unavailable)"
    telegram.send(
        f"📈 Blog traffic surge — {s['ratio']:.1f}× baseline ({s['tier']}){note}\n\n{narrative}",
        urgent=urgent,
    )
    return {"triggered": True, **s, "visitors": visitors, "narrative": narrative}
