"""FastAPI entrypoints.

- GET  /healthz       — liveness/readiness
- POST /digest        — daily summary (CronJob trigger)
- POST /alert         — Grafana contact-point webhook
- POST /surge-check   — 15-min CronJob computes baseline + maybe sends
- POST /ask           — analyst Q&A (dry_run=true → no Telegram, full trace)

The Telegram analyst poller runs as a lifespan background task — single
replica only (getUpdates exclusivity; strategy: Recreate on the Deployment).
"""
from __future__ import annotations
import asyncio
import contextlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request

from . import ai_adapter, analyst, facts, poller, surge, telegram


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    task = asyncio.create_task(poller.poll_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="ai-alert-helper", version="0.2.0", lifespan=_lifespan)

log = logging.getLogger("ai_alert_helper.surge")

# In-memory surge-notification de-dup. Safe as process-global: the Deployment is
# single-replica, uvicorn runs one worker, and the cron is concurrencyPolicy
# Forbid — so no concurrent /surge-check. A pod restart re-arms (at most one
# extra message). Edge-triggered (notify on a rising tier) + a cooldown floor.
_last_notify: dict = {"tier": None, "at": None}
_TIER_RANK = {None: 0, "Notable": 1, "Major": 2}


def _should_notify(tier: str, now: datetime) -> bool:
    cd = timedelta(hours=float(os.environ.get("SURGE_COOLDOWN_HOURS", "6")))
    rising = _TIER_RANK.get(tier, 0) > _TIER_RANK.get(_last_notify["tier"], 0)
    cooled = _last_notify["at"] is None or (now - _last_notify["at"]) >= cd
    return rising or cooled


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


@app.post("/ask")
async def ask(request: Request, dry_run: bool = False) -> dict:
    """Analyst Q&A over HTTP — the pre-merge verification path. dry_run skips
    Telegram (it always does; the flag is explicit so callers state intent)."""
    payload: dict[str, Any] = await request.json()
    question = str(payload.get("question", "")).strip()
    if not question:
        return {"error": "body must be {\"question\": \"...\"}"}
    out = analyst.answer(question, chat="http")
    return {"question": question, **out, "dry_run": dry_run}


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

    # De-dup BEFORE the expensive work (build_for_surge = 3 LogsQL + GoatCounter;
    # investigate = ~60s LLM). A suppressed tick does none of it.
    if not _should_notify(s["tier"], now):
        log.info("surge suppressed: tier=%s within cooldown", s["tier"])
        return {"triggered": True, "suppressed": True, **s, "visitors": visitors}

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
    _last_notify.update(tier=s["tier"], at=now)
    log.info("surge sent: tier=%s urgent=%s", s["tier"], urgent)
    return {"triggered": True, **s, "visitors": visitors, "narrative": narrative}
