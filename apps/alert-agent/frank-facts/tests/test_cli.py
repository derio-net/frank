"""CLI smoke: surge-compute emits the gate verdict; alert reads stdin."""
from __future__ import annotations
import io
import json

import pytest

from frank_facts import cli, surge, facts


def test_surge_compute_emits_verdict(monkeypatch, capsys):
    monkeypatch.setattr(surge, "compute", lambda: {"tier": "Notable", "current": 120, "baseline": 30})
    rc = cli.main(["surge-compute"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["tier"] == "Notable"


def test_alert_reads_stdin(monkeypatch, capsys):
    monkeypatch.setattr(facts, "build_for_alert", lambda a: {"alertname": a["alertname"], "ok": True})
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"alertname": "FalcoCriticalEvent"})))
    rc = cli.main(["alert"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out == {"alertname": "FalcoCriticalEvent", "ok": True}
