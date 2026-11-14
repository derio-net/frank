"""The update/security lifecycle's pre-phase-7 state is quiet, not weakened (frank#913 follow-up).

Phase 7 hands over the credentials (gated on frank#912). Until then four pieces are degraded BY
DESIGN. Each fix here must go away on its own the moment the phase-7 operation lands, and must
never mask a failure that happens AFTER it:

1. tailscale sidecar with no auth key idles instead of crash-looping into an interactive login;
2. the heartbeat dead-man's switches arm only once the thing they watch has reported;
3. renovate's ExternalSecret stops degrading the app only while the CronJob is still suspended;
4. trivy's hand-made token Secret has a generate-and-apply script an operator can run now.
"""
import os
import re
import signal
import stat
import subprocess
import textwrap
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "apps/cluster-update-fr/manifests/deployment.yaml"
HOP_SCAN = ROOT / "apps/hop-scan/manifests/cronjob.yaml"
RENOVATE = ROOT / "apps/renovate/manifests"
RULES_CM = ROOT / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
CONTAINERBOOT = "/usr/local/bin/containerboot"


def _docs(path):
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _sidecar(path):
    for d in _docs(path):
        if d["kind"] == "Deployment":
            pod = d["spec"]["template"]["spec"]
        elif d["kind"] == "CronJob":
            pod = d["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        else:
            continue
        return next(c for c in pod["initContainers"] if c["name"] == "tailscale")
    raise AssertionError(path)


# ---- 1. the sidecar idles while there is no key -------------------------------------------

def _script(path):
    ts = _sidecar(path)
    cmd = ts.get("command")
    assert cmd and cmd[:2] == ["/bin/sh", "-c"] and len(cmd) == 3, \
        f"{path.name}: tailscale needs the idle-until-keyed wrapper, or it crash-loops into an interactive login"
    assert not ts.get("args"), "the wrapper takes no args"
    return cmd[2]


def test_both_sidecars_carry_the_same_wrapper():
    assert _script(DEPLOY) == _script(HOP_SCAN)


KEYFILE = "/ts-authkey/authkey"


def _run(script, tmp_path, key=None, poll=None):
    """Run the wrapper with the key file under tmp_path; containerboot is a stub that echoes."""
    fake = tmp_path / "containerboot"
    fake.write_text('#!/bin/sh\necho "STARTED key=$TS_AUTHKEY"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    keyfile = tmp_path / "authkey"
    if key is not None:
        keyfile.write_text(key)
    assert CONTAINERBOOT in script and KEYFILE in script
    script = script.replace(CONTAINERBOOT, str(fake)).replace(KEYFILE, str(keyfile))
    if poll:  # test speed only: the manifest polls every 10s
        script = script.replace("sleep 10", f"sleep {poll}")
    return subprocess.Popen(["/bin/sh", "-c", script], env={"PATH": os.environ["PATH"]},
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def test_no_key_idles_and_stops_cleanly_on_sigterm(tmp_path):
    for key in (None, ""):  # an optional volume is absent, or the file exists but is empty
        p = _run(_script(DEPLOY), tmp_path, key)
        time.sleep(1.0)
        assert p.poll() is None, "must idle, not exit (an exit is a restart loop)"
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=10)
        assert p.returncode == 0, "SIGTERM must end it at once, not after the grace period"
        assert "STARTED" not in out, "must not start containerboot (that is the interactive login)"
        assert "no auth key yet" in out


def test_a_key_that_appears_later_is_picked_up_by_the_running_wrapper(tmp_path):
    """The phase-7 path: the pod is already up and idle when the Secret is created."""
    for path in (DEPLOY, HOP_SCAN):
        p = _run(_script(path), tmp_path, key=None, poll="0.2")
        time.sleep(0.8)
        assert p.poll() is None, "idling before the key exists"
        (tmp_path / "authkey").write_text("tskey-late")   # the kubelet projects the new Secret
        out, _ = p.communicate(timeout=10)
        assert p.returncode == 0 and "STARTED key=tskey-late" in out, out
        (tmp_path / "authkey").unlink()


def test_with_a_key_present_at_start_it_becomes_containerboot(tmp_path):
    p = _run(_script(HOP_SCAN), tmp_path, "tskey-abc")
    out, _ = p.communicate(timeout=10)
    assert p.returncode == 0 and "STARTED key=tskey-abc" in out


def test_the_key_is_an_optional_volume_only_the_sidecar_mounts():
    for path in (DEPLOY, HOP_SCAN):
        ts = _sidecar(path)
        assert "TS_AUTHKEY" not in {e["name"] for e in ts["env"]}, "env is resolved once at start"
        assert {"name": "ts-authkey", "mountPath": "/ts-authkey", "readOnly": True} in ts["volumeMounts"]
        assert ts["restartPolicy"] == "Always" and ts["securityContext"]["runAsUser"] == 65531
        for d in _docs(path):
            if d["kind"] not in ("Deployment", "CronJob"):
                continue
            pod = (d["spec"]["template"] if d["kind"] == "Deployment" else d["spec"]["jobTemplate"]["spec"]["template"])["spec"]
            (vol,) = [v for v in pod["volumes"] if v["name"] == "ts-authkey"]
            assert vol["secret"]["secretName"] == "frank-updater-tailscale" and vol["secret"]["optional"] is True
            assert vol["secret"]["items"] == [{"key": "authkey", "path": "authkey"}]
            others = [c for c in pod["containers"] + pod["initContainers"] if c["name"] != "tailscale"]
            assert all("ts-authkey" not in {m["name"] for m in c.get("volumeMounts", [])} for c in others)


# ---- 2. heartbeat rules arm only once the watched thing has reported -----------------------

def _rules():
    doc = yaml.safe_load(yaml.safe_load(RULES_CM.read_text())["data"]["alert-rules.yaml"])
    return {r["uid"]: r for g in doc["groups"] for r in g["rules"]}


def _q(rule, ref):
    return next(d for d in rule["data"] if d["refId"] == ref)


def test_report_rule_fires_only_for_a_metric_that_existed():
    rule = _rules()["life-report-heartbeat-stale"]
    expr = _q(rule, "A")["model"]["expr"]
    assert "cluster_update_last_report_timestamp_seconds" in expr
    # "has it EVER reported" looks back through the whole retention (1 month), and only a
    # series that existed there turns the vanished-metric branch into a stale reading.
    assert re.search(r"count\(last_over_time\(cluster_update_last_report_timestamp_seconds\[30d\]\)\)\s*>\s*0", expr)
    assert "vector(1e9)" in expr
    assert rule["noDataState"] == "OK", "never reported = nothing to be stale, so NoData must not fire"
    assert rule["labels"]["severity"] == "critical", "armed, it stays as loud as before"


def _logs_expr(rule, ref):
    return _q(rule, ref)["model"]["expr"]


NO_KUBECONFIG = "skipped: no hop-readonly-kubeconfig"


def _hb(status, healthy):
    return f'hop-scan heartbeat {{"status": "{status}", "healthy": {str(healthy).lower()}}}'


def _matches(expr, line):
    pos, neg = [], []
    for m in re.finditer(r'(NOT )?_msg:"((?:[^"\\]|\\.)*)"', expr):
        (neg if m.group(1) else pos).append(m.group(2).replace('\\"', '"'))
    return all(p in line for p in pos) and not any(n in line for n in neg)


def test_hop_scan_stale_rule_is_armed_by_the_first_configured_heartbeat():
    rule = _rules()["life-hop-scan-heartbeat-stale"]
    assert rule["condition"] == "F"
    assert _q(rule, "C")["model"]["conditions"][0]["evaluator"] == {"type": "lt", "params": [1]}
    arm = _q(rule, "D")
    assert arm["relativeTimeRange"]["from"] >= 30 * 86400 - 3600, "gate looks back through VictoriaLogs retention (30d)"
    assert arm["datasourceUid"] == _q(rule, "A")["datasourceUid"]
    assert _q(rule, "E")["model"]["type"] == "reduce"
    f = _q(rule, "F")["model"]
    assert f["type"] == "math" and "$C" in f["expression"] and "$E" in f["expression"]
    expr = _logs_expr(rule, "D")
    # the by-design "no kubeconfig yet" heartbeat does not arm it; a blind-but-configured one does
    assert not _matches(expr, _hb(NO_KUBECONFIG, False))
    assert _matches(expr, _hb("skipped: hop kube API unreachable", False))
    assert _matches(expr, _hb("ok", True))
    assert rule["noDataState"] == "OK" and rule["labels"]["severity"] == "critical"


def test_hop_scan_unhealthy_rule_ignores_only_the_not_yet_configured_state():
    rule = _rules()["life-hop-scan-unhealthy"]
    expr = _logs_expr(rule, "A")
    assert not _matches(expr, _hb(NO_KUBECONFIG, False)), "phase 7 has not run: by design, not an incident"
    for blind in ("skipped: hop kube API unreachable", "ok"):
        assert _matches(expr, _hb(blind, False)), blind
    assert not _matches(expr, _hb("ok", True))
    assert rule["labels"]["severity"] == "critical" and rule["for"] == "0s"


# ---- 3. renovate: the dormant stack does not degrade the app, until it is switched on ------

def _renovate():
    docs = []
    for f in sorted(RENOVATE.glob("*.yaml")):
        docs += _docs(f)
    return ({d["kind"]: d for d in docs if d["kind"] in ("CronJob", "ExternalSecret")})


def test_renovate_externalsecret_health_is_ignored_exactly_while_the_cronjob_is_suspended():
    d = _renovate()
    suspended = d["CronJob"]["spec"].get("suspend") is True
    ann = d["ExternalSecret"]["metadata"].get("annotations", {})
    ignored = ann.get("argocd.argoproj.io/ignore-healthcheck") == "true"
    assert ignored == suspended, (
        "the ExternalSecret's SecretSyncedError may be hidden from ArgoCD only while the CronJob "
        "is suspended; phase 7 unsuspends it and the annotation must go in the same commit")


# ---- 4. trivy token bootstrap ----------------------------------------------------------------

SCRIPT = ROOT / "scripts/trivy-token/bootstrap.sh"


def test_trivy_token_script_is_safe_and_names_both_secrets():
    text = SCRIPT.read_text()
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    assert text.startswith("#!/usr/bin/env bash") and "set -euo pipefail" in text and "set +x" in text
    for needle in ("trivy-operator-trivy-config", "trivy-system", "trivy-server-token", "hop-scan",
                   "trivy.serverToken", "TRIVY_TOKEN", "sops encrypt", "kubectl apply --server-side"):
        assert needle in text, needle
    # one random token shared by both namespaces, never on argv
    assert text.count("openssl rand") == 1
    assert not re.search(r"echo .*\$token|--from-literal", text), "the token must not be echoed or put on argv"
    assert "secrets/trivy/" in text


def test_trivy_secrets_are_sops_only_and_never_argocd_managed():
    for yml in (ROOT / "apps/trivy-operator/manifests").rglob("*.yaml"):
        for d in _docs(yml):
            assert not (d["kind"] == "Secret" and d["metadata"]["name"] in
                        ("trivy-operator-trivy-config", "trivy-server-token")), yml
