"""Guard: the cred-expiry check is actually wired into the deployed surface —
the crontab entry, the bin wrapper, and the kustomization generators. A pure unit
test of cred_expiry.py can pass while the check never runs in the pod; this pins
the wiring so that can't regress silently."""
from __future__ import annotations
import os

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # apps/alert-agent


def _read(rel: str) -> str:
    with open(os.path.join(APP, rel), encoding="utf-8") as fh:
        return fh.read()


def test_crontab_has_daily_cred_expiry_check():
    cron = _read("manifests/files/.crontab")
    line = next((ln for ln in cron.splitlines()
                 if "cred-expiry-check" in ln and not ln.lstrip().startswith("#")), None)
    assert line is not None, "no cred-expiry-check cron line"
    assert line.split()[:5] == ["0", "9", "*", "*", "*"]              # daily 09:00
    assert line.endswith("/opt/alert-agent-bin/cred-expiry-check")


def test_bin_wrapper_exists_and_calls_runner():
    body = _read("handlers/cred-expiry-check")
    assert body.startswith("#!/usr/bin/env python3")
    assert "from handlers.cred_expiry import run_cred_check" in body
    assert "run_cred_check()" in body


def test_kustomization_registers_module_and_wrapper():
    k = _read("kustomization.yaml")
    assert "handlers/handlers/cred_expiry.py" in k                    # module in handlers CM
    assert "cred-expiry-check=handlers/cred-expiry-check" in k        # wrapper in bin CM
