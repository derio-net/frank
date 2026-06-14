"""Unit tests for the agent-session send/receive driver.

The driver drives the persistent claude tmux session (never `claude -p`): it
sends a message, waits for a NEW fenced-JSON reply (not a prior turn's), and
emits the agent_session.receive.response shape with a per-session turn counter.
It exposes the same core as `agent-session serve` (HTTP POST /session/send, what
content-factory's n8n calls) and `agent-session send` (CLI).

tmux is mocked: send-keys makes the agent "respond" (the reply pane replaces the
baseline pane); has-session is controllable so auto-create can be exercised.

Contract source of truth:
docs/superpowers/specs/2026-06-14-stoa-frank-infra-design.md
Shape fixtures: scripts/tests/fixtures/stoa/
"""
import json
import os
import socket
import stat
import subprocess
import sys
import time
import types
import urllib.error
import urllib.request
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


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def harness(tmp_path):
    """Materialize the driver + a controllable fake tmux on PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    drv = bindir / "agent-session"
    drv.write_text(_driver_script())
    drv.chmod(drv.stat().st_mode | stat.S_IEXEC)

    pane = tmp_path / "pane.txt"
    reply = tmp_path / "reply.txt"
    sendlog = tmp_path / "sendkeys.log"
    newlog = tmp_path / "newsession.log"
    hasfile = tmp_path / "has.code"  # exit code for has-session (default 0)
    faketmux = bindir / "tmux"
    faketmux.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$1\" in\n"
        f"  has-session) exit $(cat '{hasfile}' 2>/dev/null || echo 0) ;;\n"
        f"  new-session) shift; echo \"$*\" >> '{newlog}' ;;\n"
        f"  send-keys) shift; echo \"$*\" >> '{sendlog}'; cat '{reply}' > '{pane}' ;;\n"
        f"  capture-pane) cat '{pane}' 2>/dev/null ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    faketmux.chmod(faketmux.stat().st_mode | stat.S_IEXEC)
    turns = tmp_path / "turns"

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["STOA_TURN_DIR"] = str(turns)
    env["STOA_POLL_S"] = "0.05"

    def run(req, initial_pane="", reply_pane=NEW_REPLY, session_exists=True):
        pane.write_text(initial_pane)
        reply.write_text(reply_pane)
        hasfile.write_text("0" if session_exists else "1")
        p = subprocess.run(
            [sys.executable, str(drv), "send", json.dumps(req)],
            capture_output=True, text=True, env=env, timeout=30,
        )
        return p

    return types.SimpleNamespace(
        drv=drv, env=env, pane=pane, reply=reply, sendlog=sendlog,
        newlog=newlog, hasfile=hasfile, run=run,
    )


def test_send_keys_carries_the_message(harness):
    p = harness.run(SEND_REQ)
    assert p.returncode == 0, p.stderr
    assert "decompose" in harness.sendlog.read_text()


def test_receive_shape_matches_contract(harness):
    out = json.loads(harness.run(SEND_REQ).stdout)
    assert set(out) == RECV_KEYS, f"keys {set(out)} != contract {RECV_KEYS}"
    assert out["status"] == "ok"
    assert out["session_id"] == SEND_REQ["session_id"]
    assert out["agent"] == "claude"
    assert out["payload"]["episode_id"] == "ep-012"


def test_returns_new_reply_not_prior_turn(harness):
    """C1 regression: a prior turn's json is already in the pane; the driver
    must wait for and return THIS turn's reply, not the stale one."""
    out = json.loads(
        harness.run(SEND_REQ, initial_pane=PRIOR_TURN, reply_pane=PRIOR_TURN + NEW_REPLY).stdout
    )
    assert out["status"] == "ok"
    assert out["payload"]["episode_id"] == "ep-012", "must not return the prior turn's payload"


def test_auto_creates_missing_session(harness):
    """The session_id the caller sends (e.g. content-factory's name) is
    auto-created if absent — the driver is agnostic to the chosen name."""
    out = json.loads(harness.run(SEND_REQ, session_exists=False).stdout)
    assert out["status"] == "ok"
    newlog = harness.newlog.read_text()
    assert SEND_REQ["session_id"] in newlog, "missing session must be auto-created"


def test_turn_counter_persists_and_increments(harness):
    t1 = json.loads(harness.run(SEND_REQ).stdout)["turn"]
    t2 = json.loads(harness.run(SEND_REQ).stdout)["turn"]
    assert t2 == t1 + 1, f"turn must advance across calls (got {t1} then {t2})"


def test_timeout_when_no_new_reply(harness):
    req = dict(SEND_REQ, timeout_s=0.2)
    out = json.loads(
        harness.run(req, initial_pane="thinking...", reply_pane="thinking... still no json").stdout
    )
    assert out["status"] != "ok", "no new reply within timeout must NOT be ok"


def test_http_server_serves_session_send(harness):
    """`agent-session serve` answers POST /session/send — the shape n8n calls."""
    port = _free_port()
    harness.pane.write_text("")
    harness.reply.write_text(NEW_REPLY)
    harness.hasfile.write_text("0")
    env = dict(harness.env)
    env["STOA_SESSION_PORT"] = str(port)
    proc = subprocess.Popen(
        [sys.executable, str(harness.drv), "serve"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        # Wait for readiness via /healthz.
        for _ in range(50):
            try:
                with urllib.request.urlopen(base + "/healthz", timeout=1) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        else:
            raise AssertionError("server did not become ready")
        # POST a send-request like the n8n httpRequest node does.
        body = json.dumps(SEND_REQ).encode()
        req = urllib.request.Request(
            base + "/session/send", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            out = json.loads(r.read())
        assert set(out) == RECV_KEYS
        assert out["status"] == "ok"
        assert out["payload"]["episode_id"] == "ep-012"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
