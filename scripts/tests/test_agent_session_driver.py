"""Unit tests for the agent-session send/receive driver.

The driver drives a persistent claude TUI session (never `claude -p`). Live
verification (MO-5b) showed two realities the old mock missed:
  * claude's TUI does NOT echo literal ```json fences — replies render inline
    after a `●`, and a large payload soft-wraps. Pane-scraping the JSON is
    unreliable.
  * `send-keys <text> Enter` in ONE call types the text but the Enter is
    swallowed (bracketed-paste). The message must be pasted, then submitted.

So the driver now:
  * submits via bracketed paste — `load-buffer` (stdin) + `paste-buffer -p` +
    a SEPARATE `send-keys Enter` after a settle delay (multi-line safe).
  * tells the agent to WRITE the JSON to a per-turn file (unique nonce path);
    the driver polls for that file to exist + parse, and that IS the payload.
    The unique path makes a prior turn's reply structurally impossible to
    mistake for this one.

The fake tmux below models that: paste stages the message, `send-keys Enter`
makes the "agent" write the file the message names.

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
import urllib.request
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DRIVER_CM = REPO / "apps/n8n-01/manifests/agent-session-driver.yaml"
FIXTURES = REPO / "scripts/tests/fixtures/stoa"

SEND_REQ = json.loads((FIXTURES / "agent_session_send_request.json").read_text())
RECV_KEYS = set(json.loads((FIXTURES / "agent_session_receive_response.json").read_text()))

PAYLOAD = {"schema_version": "1.0", "series_id": "series-x", "episode_id": "ep-012",
           "characters": ["char-a", "char-b"], "clips": []}

# Fake tmux: load-buffer stages the message, paste-buffer holds it, send-keys
# Enter makes the "agent" write FAKE_PAYLOAD to the file the message names.
FAKE_TMUX = r'''#!/usr/bin/env python3
import sys, os, re
D = os.environ["FAKE_DIR"]
def p(n): return os.path.join(D, n)
a = sys.argv[1:]
cmd = a[0] if a else ""
open(p("calls.log"), "a").write(cmd + " " + " ".join(a[1:]) + "\n")
if cmd == "has-session":
    try: code = int((open(p("has.code")).read().strip() or "0"))
    except Exception: code = 0
    sys.exit(code)
if cmd == "new-session":
    open(p("new.log"), "a").write(" ".join(a) + "\n"); sys.exit(0)
if cmd == "load-buffer":
    open(p("buffer.txt"), "w").write(sys.stdin.read()); sys.exit(0)
if cmd == "paste-buffer":
    buf = open(p("buffer.txt")).read() if os.path.exists(p("buffer.txt")) else ""
    open(p("pending.txt"), "w").write(buf); sys.exit(0)
if cmd == "send-keys":
    if "Enter" in a and os.environ.get("FAKE_NO_REPLY") != "1":
        msg = open(p("pending.txt")).read() if os.path.exists(p("pending.txt")) else ""
        m = re.search(r"to the file (\S+)", msg)
        if m:
            outfile = m.group(1)
            os.makedirs(os.path.dirname(outfile), exist_ok=True)
            open(outfile, "w").write(os.environ.get("FAKE_PAYLOAD", "{}"))
    sys.exit(0)
if cmd == "capture-pane":
    sys.stdout.write(open(p("pane.txt")).read() if os.path.exists(p("pane.txt")) else "")
    sys.exit(0)
sys.exit(0)
'''


def _driver_script() -> str:
    doc = next(d for d in yaml.safe_load_all(DRIVER_CM.read_text())
               if d and d.get("kind") == "ConfigMap")
    return doc["data"]["agent-session"]


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    return port


@pytest.fixture
def harness(tmp_path):
    bindir = tmp_path / "bin"; bindir.mkdir()
    drv = bindir / "agent-session"; drv.write_text(_driver_script())
    drv.chmod(drv.stat().st_mode | stat.S_IEXEC)
    faketmux = bindir / "tmux"; faketmux.write_text(FAKE_TMUX)
    faketmux.chmod(faketmux.stat().st_mode | stat.S_IEXEC)
    fdir = tmp_path / "fake"; fdir.mkdir()

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["FAKE_DIR"] = str(fdir)
    env["STOA_TURN_DIR"] = str(tmp_path / "turns")
    env["STOA_OUT_DIR"] = str(tmp_path / "out")
    env["STOA_POLL_S"] = "0.05"
    env["STOA_SETTLE_S"] = "0"
    env["FAKE_PAYLOAD"] = json.dumps(PAYLOAD)

    def run(req, session_exists=True, no_reply=False):
        (fdir / "has.code").write_text("0" if session_exists else "1")
        e = dict(env)
        if no_reply:
            e["FAKE_NO_REPLY"] = "1"
        p = subprocess.run([sys.executable, str(drv), "send", json.dumps(req)],
                           capture_output=True, text=True, env=e, timeout=30)
        return p

    return types.SimpleNamespace(drv=drv, env=env, fdir=fdir, run=run)


def test_receive_shape_matches_contract(harness):
    out = json.loads(harness.run(SEND_REQ).stdout)
    assert set(out) == RECV_KEYS, f"keys {set(out)} != contract {RECV_KEYS}"
    assert out["status"] == "ok"
    assert out["session_id"] == SEND_REQ["session_id"]
    assert out["agent"] == "claude"
    assert out["payload"] == PAYLOAD, "payload must come from the file the agent wrote"


def test_submits_via_bracketed_paste_not_send_keys_text(harness):
    harness.run(SEND_REQ)
    calls = (harness.fdir / "calls.log").read_text()
    assert "load-buffer" in calls and "paste-buffer" in calls, "must paste the message"
    # The message must NOT be typed as send-keys literal text (the swallowed-Enter
    # bug): the only send-keys call is the bare Enter submit.
    sk_lines = [l for l in calls.splitlines() if l.startswith("send-keys")]
    assert sk_lines, "must submit with send-keys Enter"
    assert all("Enter" in l for l in sk_lines), f"send-keys must only send Enter, got {sk_lines}"


def test_payload_from_file_not_pane(harness):
    # The driver never depends on ```json fences (real claude renders inline) —
    # the payload comes from the file. No pane content is needed for success.
    out = json.loads(harness.run(SEND_REQ).stdout)
    assert out["status"] == "ok" and out["payload"] == PAYLOAD


def test_unique_file_per_turn(harness):
    # Each turn names a fresh nonce'd outfile, so a prior turn's reply can't be
    # mistaken for this one. Both succeed; the turn advances.
    a = json.loads(harness.run(SEND_REQ).stdout)
    b = json.loads(harness.run(SEND_REQ).stdout)
    assert a["status"] == "ok" and b["status"] == "ok"
    assert b["turn"] == a["turn"] + 1


def test_auto_creates_missing_session(harness):
    out = json.loads(harness.run(SEND_REQ, session_exists=False).stdout)
    assert out["status"] == "ok"
    newlog = (harness.fdir / "new.log").read_text()
    assert SEND_REQ["session_id"] in newlog
    # The session must be able to write its output file unprompted (file writes
    # only — not a full permissions bypass).
    assert "acceptEdits" in newlog


def test_timeout_when_no_file(harness):
    req = dict(SEND_REQ, timeout_s=0.3)
    out = json.loads(harness.run(req, no_reply=True).stdout)
    assert out["status"] != "ok"


def test_http_server_serves_session_send(harness):
    port = _free_port()
    (harness.fdir / "has.code").write_text("0")
    env = dict(harness.env); env["STOA_SESSION_PORT"] = str(port)
    proc = subprocess.Popen([sys.executable, str(harness.drv), "serve"],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try:
                with urllib.request.urlopen(base + "/healthz", timeout=1) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        else:
            raise AssertionError("server did not become ready")
        body = json.dumps(SEND_REQ).encode()
        req = urllib.request.Request(base + "/session/send", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            out = json.loads(r.read())
        assert out["status"] == "ok" and out["payload"] == PAYLOAD
    finally:
        proc.terminate(); proc.wait(timeout=5)
