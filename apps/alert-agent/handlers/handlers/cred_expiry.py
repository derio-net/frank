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


def _message(tier: str, days_left: int | None, exp_iso: str | None,
             reason: str = "unreadable") -> str:
    # Plain text only — no < > & (Telegram contact renders plain; keep the invariant).
    if tier == "error":
        if reason == "blank-token":
            # Deliberately says nothing about days remaining: the clock is healthy and
            # utterly irrelevant. Mentioning it is what made this failure invisible.
            return ("alert-agent Claude credential has a BLANK refresh token "
                    f"(at {CRED_PATH}) — the token clock still looks healthy but claude "
                    "cannot authenticate, so the command-and-control bot is dead and every "
                    "DM falls back to the deterministic snapshot. Re-login now: attach the "
                    "agent tmux and run /login.")
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


def _error_verdict(now_ms: int, reason: str) -> Verdict:
    """The single constructor for every error-tier Verdict. `reason` is carried into
    the heartbeat as a stable `reason=<slug>` token — the Grafana dead-man rule matches
    only the literal `cred-expiry-check`, so extra fields are safe to add."""
    hb = (f"cred-expiry-check days_left=unknown tier=error reason={reason} "
          f"refresh_expires=unknown ts={_now_iso(now_ms)}")
    return Verdict(None, "error", True, _message("error", None, None, reason), hb)


def _refresh_token_usable(oauth: dict) -> bool:
    """Is there actually a token to refresh with? A non-empty string, nothing else.

    Incident 2026-07-23: claude BLANKS `accessToken`/`refreshToken` to "" when a refresh
    fails (invalid_grant), but leaves `refreshTokenExpiresAt` untouched — so the clock
    read 26 days out while `claude -p` returned "Failed to authenticate: OAuth session
    expired and could not be refreshed". The agent tmux pane died on launch, every DM
    timed out into the deterministic-snapshot fallback, and this check reported tier=ok
    for ~14h. The expiry clock is necessary but never sufficient: the credential must
    also CONTAIN a credential."""
    tok = oauth.get("refreshToken")
    return isinstance(tok, str) and bool(tok.strip())


def evaluate_expiry(creds_text: str | None, now_ms: int) -> Verdict:
    """Pure + TOTAL: map a credentials-file body + a clock to a Verdict, NEVER raising.
    A missing/unparseable file, an absent/non-numeric/non-finite/out-of-range
    `refreshTokenExpiresAt` → tier 'error' (should_warn True) — a broken credential is
    itself alarming, never a silent skip and never an exception."""
    exp_ms = None
    blank_token = False
    if creds_text is not None:
        try:
            doc = json.loads(creds_text)
            # The real claude credentials.json nests the field under `claudeAiOauth`
            # (confirmed live 2026-07-22); accept a top-level field too, defensively.
            oauth = doc.get("claudeAiOauth") if isinstance(doc, dict) else None
            if isinstance(oauth, dict):
                # Only the nested shape is one we have seen live, so it is the only one
                # whose token field we can name. The top-level fallback stays clock-only.
                blank_token = not _refresh_token_usable(oauth)
            if isinstance(oauth, dict) and "refreshTokenExpiresAt" in oauth:
                exp_ms = oauth.get("refreshTokenExpiresAt")
            else:
                exp_ms = doc.get("refreshTokenExpiresAt")
        except (ValueError, TypeError, AttributeError):
            exp_ms = None
    if blank_token:
        # Wins over any clock reading: a blank token is dead NOW, whatever the calendar says.
        return _error_verdict(now_ms, "blank-token")
    # Reject non-numbers, bools (isinstance(True, int) is True), and non-finite
    # floats — json.loads accepts Infinity/NaN by default and math.floor(inf/nan)
    # RAISES, which would crash the runner before it can emit a heartbeat.
    ok = (isinstance(exp_ms, (int, float)) and not isinstance(exp_ms, bool)
          and math.isfinite(exp_ms))
    if ok:
        try:
            days_left = math.floor((exp_ms - now_ms) / DAY_MS)
            tier = _tier(days_left)
            # _now_iso raises ValueError for a finite-but-out-of-range epoch (e.g. a
            # value stored in seconds*1000, or garbage) — treat as error, not a crash.
            exp_iso = _now_iso(int(exp_ms))
        except (ValueError, OverflowError, OSError):
            ok = False
    if not ok:
        return _error_verdict(now_ms, "unreadable")

    hb = (f"cred-expiry-check days_left={days_left} tier={tier} "
          f"refresh_expires={exp_iso} ts={_now_iso(now_ms)}")
    return Verdict(days_left, tier, tier != "ok", _message(tier, days_left, exp_iso), hb)


def _read_cred() -> str | None:
    """Read the credentials file body, or None if it can't be read. ANY read failure
    (missing, permission, is-a-directory → OSError; invalid UTF-8 → UnicodeDecodeError,
    a ValueError) → None → an `error`-tier warning, never an exception that would crash
    the runner before the heartbeat prints."""
    try:
        with open(CRED_PATH, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def run_cred_check(now_ms: int | None = None) -> None:
    """Daily runner: emit the heartbeat ALWAYS, warn on threshold. The heartbeat is
    load-bearing (the Grafana dead-man rule keys on it), so the whole verdict
    computation is wrapped: ANY unexpected error still yields an `error` heartbeat +
    warning rather than a silent crash. A tg_send transport error is swallowed
    (logged) so a send failure can't suppress the heartbeat. `now_ms` injectable."""
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    try:
        v = evaluate_expiry(_read_cred(), now_ms)
    except Exception as exc:  # noqa: BLE001 — never crash before the heartbeat prints
        print(f"WARN cred-expiry-check: evaluate_expiry raised: {exc}", file=sys.stderr)
        v = _error_verdict(now_ms, "unreadable")
    print(v.heartbeat, flush=True)
    if v.should_warn:
        try:
            bridge.tg_send(v.message)
        except Exception as exc:  # noqa: BLE001 — a send failure must not kill the heartbeat
            print(f"WARN cred-expiry-check: tg_send failed: {exc}", file=sys.stderr)
