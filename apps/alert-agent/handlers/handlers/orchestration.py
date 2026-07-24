"""surge-gate + digest orchestration.

Cron (supercronic) runs these as FRESH processes each */15 (surge) / daily
(digest), so the edge-trigger + cooldown state is persisted to a file on the PVC
(in-memory would reset every run — the old design only got away with in-memory
because it was a long-lived FastAPI app). The agent (paid, cloud) is woken ONLY
on a real surge escalation or the daily digest; delivery falls back to a
deterministic frank-facts render if the agent times out.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timedelta, timezone

from frank_facts import facts, surge
from tg_bridge import bridge

STATE_PATH = os.environ.get("SURGE_STATE_PATH", os.path.expanduser("~/.alert-agent/surge-state.json"))
COOLDOWN_HOURS = float(os.environ.get("SURGE_COOLDOWN_HOURS", "6"))

# Each autonomous analytical stream drives its OWN agent session — never a shared
# one. The agent-session server keeps a long-lived claude session per id and only
# resets its context after IDLE_RESET_S of idleness, so sharing let a prior wake's
# narrative (the resolved #594 incident) bleed into a later, unrelated triage
# (frank#599). The digest stream is also guaranteed-fresh this way: its 24h cadence
# always exceeds the server's idle-reset window, so each daily run starts clean.
SURGE_SESSION_ID = "alert-agent-surge"
DIGEST_SESSION_ID = "alert-agent-digest"

_RANK = {None: 0, "Notable": 1, "Major": 2}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_state(path: str = STATE_PATH) -> dict:
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state: dict, path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, path)


def should_escalate(verdict: dict, state: dict, now: datetime,
                    cooldown_hours: float = COOLDOWN_HOURS) -> tuple[bool, dict]:
    """Edge-trigger (notify on a RISING tier) + cooldown floor (same tier re-notifies
    only after `cooldown_hours`). tier None re-arms. Pure → easy to test."""
    rank = _RANK.get(verdict.get("tier"), 0)
    last_rank = state.get("last_rank", 0)
    last_ts = state.get("last_ts")
    if rank == 0:
        return False, {"last_rank": 0, "last_ts": last_ts}  # re-arm, keep ts
    if rank > last_rank:
        return True, {"last_rank": rank, "last_ts": now.isoformat()}  # rising edge
    if last_ts and (now - datetime.fromisoformat(last_ts)) >= timedelta(hours=cooldown_hours):
        return True, {"last_rank": rank, "last_ts": now.isoformat()}  # cooldown elapsed
    return False, state


def _render_surge(sheet: dict, verdict: dict) -> str:
    """Deterministic surge summary (the fallback when the agent times out)."""
    paths = ", ".join(f"{p['path']}({p['count']})" for p in sheet.get("top_paths", [])[:3]) or "n/a"
    refs = ", ".join(f"{r['name']}({r['count']})" for r in sheet.get("top_referrers", [])[:3]) or "n/a"
    return (f"Blog traffic surge ({verdict.get('tier')}): {verdict.get('current')} req/h vs "
            f"baseline {verdict.get('baseline')} (x{verdict.get('ratio', 0):.1f}). "
            f"Top paths: {paths}. Top referrers: {refs}.")


def run_surge(now: datetime | None = None) -> bool:
    """The */15 gate. Returns True iff it woke the agent."""
    now = now or _utcnow()
    verdict = surge.compute()
    escalate, new_state = should_escalate(verdict, load_state(), now)
    save_state(new_state)
    if not escalate:
        print(f"surge (suppressed): tier={verdict.get('tier')} current={verdict.get('current')}")
        return False
    sheet = facts.build_for_surge(now - timedelta(hours=1), now)
    fallback = _render_surge(sheet, verdict)
    prompt = ("A blog traffic surge tripped the deterministic gate. Investigate and explain it "
              "using ONLY the facts below: attribute the source from top_referrers and "
              "top_user_agents and cite specifics; if the facts do not show it, say the source "
              "is undetermined. Never name a source the facts do not support. "
              "Reply as JSON {\"text\": \"<a few short lines or a compact plain-text table>\"} — "
              "the table goes inside text.\n\n"
              f"verdict={json.dumps(verdict)}\nfacts={json.dumps(sheet)}")
    resp = bridge.session_send(prompt, session_id=SURGE_SESSION_ID)
    bridge.deliver(resp, fallback)
    return True


def _render_digest(sheet: dict) -> str:
    """Deterministic digest summary (the fallback)."""
    crit = sum(r["count"] for r in sheet.get("falco_critical_rules", []))
    return (f"Daily digest: {sheet.get('edge_requests_total', 0)} edge requests, "
            f"{sheet.get('blog_pageviews', 0)} blog pageviews, "
            f"{sheet.get('crowdsec_decisions', 0)} CrowdSec decisions, "
            f"{crit} Falco-Critical events.")


def run_digest(now: datetime | None = None) -> None:
    """The daily digest — always wakes the agent once; delivery falls back."""
    now = now or _utcnow()
    until = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since = until - timedelta(days=1)
    sheet = facts.build_for_digest(since, until, now)
    fallback = _render_digest(sheet)
    prompt = ("Write the daily Frank digest (traffic + security) from ONLY the facts below — "
              "concise, notable items only, no speculation. "
              "Reply as JSON {\"text\": \"<a compact plain-text table or a few short lines>\"} — "
              "the table goes inside text.\n\n"
              f"facts={json.dumps(sheet)}")
    resp = bridge.session_send(prompt, session_id=DIGEST_SESSION_ID)
    bridge.deliver(resp, fallback)
