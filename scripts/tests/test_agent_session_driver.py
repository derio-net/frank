"""Unit tests for the agent-session send/receive driver.

The driver drives the persistent claude tmux session (never `claude -p`): it
sends a message, waits for a NEW fenced-JSON reply (not a prior turn's), and
emits the agent_session.receive.response shape with a per-session turn counter.
tmux is mocked: send-keys makes the agent "respond" (the reply pane replaces the
baseline pane), capture-pane echoes the current pane — so the count-based
new-block detection is actually exercised.

Contract source of truth:
docs/superpowers/specs/2026-06-14-stoa-frank-infra-design.md
Shape fixtures: scripts/tests/fixtures/stoa/
"""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DRIVER_CM = REPO / "apps/n8n-01/manifests/agent-session-driver.yaml"
FIXTURES = REPO / "scripts/tests/fixtures/stoa"

SEND_REQ = json.loads((FIXTURES / "agent_session_send_request.json").read_text())
RECV_KEYS = set(json.loads((FIXTURES / "agent_session_receive_response.json").read_text()))

NEW_REPLY = """\
I'll write the episode and decompose it.

```json
{"schema_version": "1.0", "series_id": "series-x", "episode_id": "ep-012",
 "characters": ["char-a", "char-b"], "clips": []}
```
Done.
"""

PRIOR_TURN = """\
(previous turn still in the pane)
```json
{"schema_version": "1.0", "episode_id": "ep-OLD", "clips": []}
```
"""


def _driver_script() -> str:
    doc = next(
        d for d in yaml.safe_load_all(DRIVER_CM.read_text())
        if d and d.get("kind") == "ConfigMap"
    )
    return doc["data"]["agent-session"]


@pytest.fixture
def driver(tmp_path):
    """Materialize the driver + a fake tmux on PATH; return a runner.

    The fake tmux models a real session: `capture-pane` echoes the pane file;
    `send-keys` simulates the agent replying by overwriting the pane with the
    reply text. So a capture BEFORE send sees only the baseline, and captures
    AFTER send see the reply — exactly the timing the driver must handle.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    drv = bindir / "agent-session"
    drv.write_text(_driver_script())
    drv.chmod(drv.stat().st_mode | stat.S_IEXEC)

    pane = tmp_path / "pane.txt"
    reply = tmp_path / "reply.txt"
    sendlog = tmp_path / "sendkeys.log"
    faketmux = bindir / "tmux"
    faketmux.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$1\" in\n"
        "  has-session) exit 0 ;;\n"
        f"  send-keys) shift; echo \"$*\" >> '{sendlog}'; cat '{reply}' > '{pane}' ;;\n"
        f"  capture-pane) cat '{pane}' 2>/dev/null ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    faketmux.chmod(faketmux.stat().st_mode | stat.S_IEXEC)
    turns = tmp_path / "turns"

    def run(req, initial_pane="", reply_pane=NEW_REPLY):
        pane.write_text(initial_pane)
        reply.write_text(reply_pane)
        env = dict(os.environ)
        env["PATH"] = f"{bindir}:{env['PATH']}"
        env["STOA_TURN_DIR"] = str(turns)
        env["STOA_POLL_S"] = "0.05"
        p = subprocess.run(
            [sys.executable, str(drv), "send", json.dumps(req)],
            capture_output=True, text=True, env=env, timeout=30,
        )
        return p, sendlog

    return run


def test_send_keys_carries_the_message(driver):
    p, sendlog = driver(SEND_REQ)
    assert p.returncode == 0, p.stderr
    assert "decompose" in sendlog.read_text()


def test_receive_shape_matches_contract(driver):
    p, _ = driver(SEND_REQ)
    out = json.loads(p.stdout)
    assert set(out) == RECV_KEYS, f"keys {set(out)} != contract {RECV_KEYS}"
    assert out["status"] == "ok"
    assert out["session_id"] == SEND_REQ["session_id"]
    assert out["agent"] == "claude"
    assert out["payload"]["episode_id"] == "ep-012"


def test_returns_new_reply_not_prior_turn(driver):
    """C1 regression: a prior turn's json is already in the pane; the driver
    must wait for and return THIS turn's reply, not the stale one."""
    p, _ = driver(SEND_REQ, initial_pane=PRIOR_TURN, reply_pane=PRIOR_TURN + NEW_REPLY)
    out = json.loads(p.stdout)
    assert out["status"] == "ok"
    assert out["payload"]["episode_id"] == "ep-012", "must not return the prior turn's payload"


def test_turn_counter_persists_and_increments(driver):
    p1, _ = driver(SEND_REQ)
    p2, _ = driver(SEND_REQ)
    t1 = json.loads(p1.stdout)["turn"]
    t2 = json.loads(p2.stdout)["turn"]
    assert t2 == t1 + 1, f"turn must advance across calls (got {t1} then {t2})"


def test_timeout_when_no_new_reply(driver):
    # The agent produces no new json block within the window.
    req = dict(SEND_REQ, timeout_s=0.2)
    p, _ = driver(req, initial_pane="thinking...", reply_pane="thinking... still no json")
    out = json.loads(p.stdout)
    assert out["status"] != "ok", "no new reply within timeout must NOT be ok"
