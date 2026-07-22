"""Claude OAuth credential-expiry check for the alert-agent.

The agent's login credential (`/home/agent/.claude/.credentials.json`, on the
`alert-agent-home` PVC) carries a `refreshTokenExpiresAt` epoch-ms field — a hard
~30-day clock. It expired silently once (2026-07-18) and the C&C bot went dead for
3 days with no signal. This runs daily in the `agent` container (supercronic) and:

  - ALWAYS prints a `cred-expiry-check …` heartbeat line to stdout → supercronic →
    VictoriaLogs, watched by a Grafana dead-man rule (checker-died backstop);
  - sends a plain-text Telegram warning (via `tg_bridge.bridge.tg_send`) when the
    token is <=7 days from expiry, escalating at <=3 / <=1 / expired.

`evaluate_expiry` is a pure function (unit-tested); `run_cred_check` is the thin
runner the bin wrapper calls.
"""
from __future__ import annotations
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from tg_bridge import bridge

CRED_PATH = os.environ.get("CRED_PATH", "/home/agent/.claude/.credentials.json")
DAY_MS = 86_400_000


@dataclass
class Verdict:
    days_left: int | None
    tier: str            # ok | notice | soon | urgent | expired | error
    should_warn: bool
    message: str         # plain text (no < > &) — the Telegram contact is plain-text
    heartbeat: str       # single stable line → VictoriaLogs


def _tier(days_left: int) -> str:
    if days_left <= 0:
        return "expired"
    if days_left <= 1:
        return "urgent"
    if days_left <= 3:
        return "soon"
    if days_left <= 7:
        return "notice"
    return "ok"


def _message(tier: str, days_left: int | None, exp_iso: str | None) -> str:
    # Plain text only — no < > & (Telegram contact renders plain; keep the invariant).
    if tier == "error":
        return ("alert-agent credential check FAILED to read a valid Claude token "
                f"(at {CRED_PATH}). Re-login may be needed: attach the agent tmux and run /login.")
    when = f" (expires {exp_iso})" if exp_iso else ""
    if tier == "expired":
        return (f"alert-agent Claude token EXPIRED{when}. The command-and-control bot "
                "is or will be dead. Re-login now: attach the agent tmux and run /login.")
    if tier == "urgent":
        return (f"alert-agent Claude token expires in {days_left} day{when}. "
                "Re-login today: attach the agent tmux and run /login.")
    if tier == "soon":
        return (f"alert-agent Claude token expires in {days_left} days{when}. "
                "Re-login soon: attach the agent tmux and run /login.")
    # notice
    return (f"alert-agent Claude token expires in {days_left} days{when}. "
            "Plan a re-login (attach the agent tmux and run /login).")


def _now_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def evaluate_expiry(creds_text: str | None, now_ms: int) -> Verdict:
    """Pure: map a credentials-file body + a clock to a Verdict. A missing/unparseable
    file or an absent/non-int `refreshTokenExpiresAt` → tier 'error' (should_warn True) —
    a broken credential is itself alarming, never a silent skip."""
    exp_ms = None
    if creds_text is not None:
        try:
            exp_ms = json.loads(creds_text).get("refreshTokenExpiresAt")
        except (ValueError, TypeError, AttributeError):
            exp_ms = None
    if not isinstance(exp_ms, (int, float)) or isinstance(exp_ms, bool):
        hb = (f"cred-expiry-check days_left=unknown tier=error "
              f"refresh_expires=unknown ts={_now_iso(now_ms)}")
        return Verdict(None, "error", True, _message("error", None, None), hb)

    days_left = math.floor((exp_ms - now_ms) / DAY_MS)
    tier = _tier(days_left)
    exp_iso = _now_iso(int(exp_ms))
    hb = (f"cred-expiry-check days_left={days_left} tier={tier} "
          f"refresh_expires={exp_iso} ts={_now_iso(now_ms)}")
    return Verdict(days_left, tier, tier != "ok", _message(tier, days_left, exp_iso), hb)


def _read_cred() -> str | None:
    """Read the credentials file body, or None if it does not exist (a missing file is
    a real problem the check must warn about, not crash on)."""
    try:
        with open(CRED_PATH, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def run_cred_check(now_ms: int | None = None) -> None:
    """Daily runner: emit the heartbeat ALWAYS, warn on threshold. A tg_send transport
    error is swallowed (logged to stderr) so a send failure never suppresses the
    heartbeat that the dead-man rule depends on. `now_ms` is injectable for tests."""
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    v = evaluate_expiry(_read_cred(), now_ms)
    print(v.heartbeat, flush=True)
    if v.should_warn:
        try:
            bridge.tg_send(v.message)
        except Exception as exc:  # noqa: BLE001 — a send failure must not kill the heartbeat
            print(f"WARN cred-expiry-check: tg_send failed: {exc}", file=sys.stderr)
